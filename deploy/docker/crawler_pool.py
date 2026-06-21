# crawler_pool.py - Smart browser pool with tiered management
import asyncio, json, hashlib, time
from contextlib import suppress
from typing import Dict, Optional
from crawl4ai import AsyncWebCrawler, BrowserConfig
from crawl4ai.browser_adapter import UndetectedAdapter
from utils import load_config, get_container_memory_percent
import logging

logger = logging.getLogger(__name__)
CONFIG = load_config()
USE_UNDETECTED = CONFIG.get("crawler", {}).get("browser", {}).get("use_undetected", False)

# Pool tiers
PERMANENT: Optional[AsyncWebCrawler] = None  # Always-ready default browser
HOT_POOL: Dict[str, AsyncWebCrawler] = {}    # Frequent configs
COLD_POOL: Dict[str, AsyncWebCrawler] = {}   # Rare configs
LAST_USED: Dict[str, float] = {}
USAGE_COUNT: Dict[str, int] = {}
LOCK = asyncio.Lock()

# Config
MEM_LIMIT = CONFIG.get("crawler", {}).get("memory_threshold_percent", 95.0)
BASE_IDLE_TTL = CONFIG.get("crawler", {}).get("pool", {}).get("idle_ttl_sec", 300)
DEFAULT_CONFIG_SIG = None  # Cached sig for default config

# Proactive restart: force-recycle a long-running permanent browser to shed
# accumulated state corruption before it hangs. Default 12h. 0 disables.
RESTART_INTERVAL_SEC = CONFIG.get("crawler", {}).get("pool", {}).get("restart_interval_sec", 12 * 3600)

# Permanent lifecycle bookkeeping (3 state + 1 coordination signal).
# PERMANENT_CFG caches the config passed to init_permanent so restarts can
# rebuild without re-reading config.yml (which may have been edited since
# startup, causing sig divergence).
PERMANENT_CFG: Optional[BrowserConfig] = None
# Monotonic timestamp of the last (re)start. Doubles as the restart epoch:
# _restart_permanent snapshots it on entry and re-checks after acquiring locks
# to skip a restart that a concurrent caller already completed.
PERMANENT_STARTED_AT: float = 0.0
# Serializes all restart triggers so concurrent callers don't stomp each other.
PERMANENT_RESTART_LOCK = asyncio.Lock()
# Coordination signal (one object, two roles):
#   is_set()=True  -> not restarting (default); new requests proceed normally
#   clear()        -> restart in progress; new default-config requests hang on wait()
#   set()          -> restart done; wakes all waiters
# Must start set() so get_crawler never blocks before the first restart.
_RESTART_DONE = asyncio.Event()
_RESTART_DONE.set()
# Last time janitor ran an (idle) health probe. Module-local throttle so it
# doesn't probe on every janitor tick. Monotonic clock (matches
# PERMANENT_STARTED_AT / restart deadline) so NTP jumps don't trick it.
_LAST_HEALTH_PROBE_AT: float = 0.0


def get_pool_snapshot() -> dict:
    """Return a point-in-time snapshot of pool state for monitoring.

    This is intentionally lock-free. Under CPython's GIL, reading
    ``len(dict)``, ``dict.copy()``, and ``x is not None`` are atomic
    operations, so the monitor can safely call this without contending
    on the pool LOCK that is held during slow browser start/close ops.
    The worst case is a slightly stale count, which is acceptable for
    dashboard display purposes.
    """
    return {
        "permanent": PERMANENT,
        "permanent_sig": DEFAULT_CONFIG_SIG,
        "hot_pool": HOT_POOL.copy(),
        "cold_pool": COLD_POOL.copy(),
        "last_used": LAST_USED.copy(),
        "usage_count": USAGE_COUNT.copy(),
    }


def _sig(cfg: BrowserConfig) -> str:
    """Generate config signature."""
    payload = json.dumps(cfg.to_dict(), sort_keys=True, separators=(",",":"))
    return hashlib.sha1(payload.encode()).hexdigest()

def _is_default_config(sig: str) -> bool:
    """Check if config matches default."""
    return sig == DEFAULT_CONFIG_SIG

async def get_crawler(cfg: BrowserConfig) -> AsyncWebCrawler:
    """Get crawler from pool with tiered strategy."""
    sig = _sig(cfg)

    # ── Permanent browser: lightweight health check before each crawl ──
    # 分层健康检查设计（与库层 async_webcrawler / browser_manager 配合）：
    #   - 轻量 is_connected()（~200μs）每次爬取前在这里做，查 CDP socket
    #     是否还连着（误关闭/崩溃场景），但查不出 renderer 卡死
    #   - 复杂 _probe_browser_health（200ms~8s）由库层在代理+重试全失败后做，
    #     结果写到 AsyncWebCrawler._browser_unhealthy 属性 + crawl_stats
    #     （部署层在 release_crawler / 这里读 crawler 上的标记触发 restart）
    #   - 所有 restart 统一走 _restart_permanent（带 RESTART_LOCK + drain
    #     协议）。多请求并发触发时，其内部 _RESTART_DONE gate 自动去重
    #     成一次（第一个 clear gate + rebuild，其余在 gate 上 wait）
    #
    # 这是单次流程（不循环）：检测一次、restart 一次、进 LOCK 取 PERMANENT。
    # 新 PERMANENT 也断属极端，让请求自然失败，不自我放大（避免屎山）。
    # 检查在 LOCK 外：_restart_permanent 的 Phase 3 重建需拿 LOCK，gate 已
    # 保证此刻无 in-flight restart。
    if _is_default_config(sig):
        # Gate: restart 进行中则等（LOCK 外 wait，否则死锁 _restart_permanent）
        # asyncio.Event 无 spurious wakeup，无需 while 守卫
        await _RESTART_DONE.wait()
        # 轻量检查：断开（误关闭/崩溃）或库层在 AsyncWebCrawler 上打了
        # _browser_unhealthy 标记（renderer 卡死，is_connected() 查不出来）
        _bm = PERMANENT.crawler_strategy.browser_manager if PERMANENT else None
        _bad = (
            _bm is None
            or _bm.browser is None
            or not _bm.browser.is_connected()
            or getattr(PERMANENT, "_browser_unhealthy", False)
        )
        if _bad:
            if PERMANENT is not None:
                PERMANENT._browser_unhealthy = False  # consume the flag
            logger.info("🔌 Permanent browser unhealthy, triggering restart")
            await _restart_permanent(PERMANENT_CFG, trigger="unhealthy")

    async with LOCK:
        # Check permanent browser for default config
        if PERMANENT and _is_default_config(sig):
            LAST_USED[sig] = time.time()
            USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
            if not hasattr(PERMANENT, 'active_requests'):
                PERMANENT.active_requests = 0
            PERMANENT.active_requests += 1
            logger.info("🔥 Using permanent browser")
            return PERMANENT

        # Check hot pool
        if sig in HOT_POOL:
            LAST_USED[sig] = time.time()
            USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
            crawler = HOT_POOL[sig]
            if not hasattr(crawler, 'active_requests'):
                crawler.active_requests = 0
            crawler.active_requests += 1
            logger.info(f"♨️  Using hot pool browser (sig={sig[:8]}, active={crawler.active_requests})")
            return crawler

        # Check cold pool (promote to hot if used 3+ times)
        if sig in COLD_POOL:
            LAST_USED[sig] = time.time()
            USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
            crawler = COLD_POOL[sig]
            if not hasattr(crawler, 'active_requests'):
                crawler.active_requests = 0
            crawler.active_requests += 1

            if USAGE_COUNT[sig] >= 3:
                logger.info(f"⬆️  Promoting to hot pool (sig={sig[:8]}, count={USAGE_COUNT[sig]})")
                HOT_POOL[sig] = COLD_POOL.pop(sig)

                # Track promotion in monitor
                try:
                    from monitor import get_monitor
                    await get_monitor().track_janitor_event("promote", sig, {"count": USAGE_COUNT[sig]})
                except:
                    pass

                return HOT_POOL[sig]

            logger.info(f"❄️  Using cold pool browser (sig={sig[:8]})")
            return crawler

        # Memory check before creating new
        mem_pct = get_container_memory_percent()
        if mem_pct >= MEM_LIMIT:
            logger.error(f"💥 Memory pressure: {mem_pct:.1f}% >= {MEM_LIMIT}%")
            raise MemoryError(f"Memory at {mem_pct:.1f}%, refusing new browser")

        # Create new in cold pool
        logger.info(f"🆕 Creating new browser in cold pool (sig={sig[:8]}, mem={mem_pct:.1f}%)")
        adapter = UndetectedAdapter() if USE_UNDETECTED else None
        crawler = AsyncWebCrawler(config=cfg, thread_safe=False, browser_adapter=adapter) if adapter else AsyncWebCrawler(config=cfg, thread_safe=False)
        await crawler.start()
        crawler.active_requests = 1
        COLD_POOL[sig] = crawler
        LAST_USED[sig] = time.time()
        USAGE_COUNT[sig] = 1
        return crawler

async def release_crawler(crawler: AsyncWebCrawler):
    """Decrement active request count for a pooled crawler.

    Call this in a finally block after finishing work with a crawler
    obtained via get_crawler() so the janitor knows when it's safe
    to close idle browsers.

    Also consumes the library-reported ``_browser_unhealthy`` flag (set by
    AsyncWebCrawler after all retries fail and a probe confirms the browser
    is hung). When set on the permanent crawler, schedules a restart
    outside LOCK so the request path isn't blocked.
    """
    need_restart = bool(getattr(crawler, "_browser_unhealthy", False))
    is_permanent = crawler is PERMANENT

    async with LOCK:
        if hasattr(crawler, 'active_requests'):
            crawler.active_requests = max(0, crawler.active_requests - 1)
        if need_restart:
            crawler._browser_unhealthy = False  # consume flag inside LOCK

    if need_restart and is_permanent:
        # Restart outside LOCK to avoid self-deadlock with _restart_permanent.
        asyncio.create_task(_restart_permanent(PERMANENT_CFG, trigger="unhealthy"))

def _build_permanent(cfg: BrowserConfig) -> AsyncWebCrawler:
    """Construct the permanent AsyncWebCrawler.

    Single source of truth for construction args — used by both
    init_permanent (first start) and _restart_permanent (rebuild).
    Add new construction params here, not at the call sites.
    """
    adapter = UndetectedAdapter() if USE_UNDETECTED else None
    if adapter:
        return AsyncWebCrawler(config=cfg, thread_safe=False, browser_adapter=adapter)
    return AsyncWebCrawler(config=cfg, thread_safe=False)


async def init_permanent(cfg: BrowserConfig):
    """Initialize permanent default browser (called once at startup).

    Builds PERMANENT and caches cfg / start-time for later restarts.
    Construction is delegated to _build_permanent, shared with
    _restart_permanent to avoid drift.
    """
    global PERMANENT, DEFAULT_CONFIG_SIG, PERMANENT_CFG, PERMANENT_STARTED_AT
    async with LOCK:
        if PERMANENT:
            return
        PERMANENT_CFG = cfg                       # cached for restarts
        DEFAULT_CONFIG_SIG = _sig(cfg)
        logger.info("🔥 Creating permanent default browser")
        PERMANENT = _build_permanent(cfg)
        await PERMANENT.start()
        PERMANENT_STARTED_AT = time.monotonic()   # epoch for timed restart + re-check
        LAST_USED[DEFAULT_CONFIG_SIG] = time.time()
        USAGE_COUNT[DEFAULT_CONFIG_SIG] = 0

async def close_all():
    """Close all browsers."""
    global PERMANENT, PERMANENT_CFG, PERMANENT_STARTED_AT
    async with LOCK:
        tasks = []
        if PERMANENT:
            tasks.append(PERMANENT.close())
        tasks.extend([c.close() for c in HOT_POOL.values()])
        tasks.extend([c.close() for c in COLD_POOL.values()])
        await asyncio.gather(*tasks, return_exceptions=True)
        # Reset PERMANENT so init_permanent()'s `if PERMANENT: return` guard
        # does not short-circuit a later recreation (e.g. after restart).
        PERMANENT = None
        PERMANENT_CFG = None
        PERMANENT_STARTED_AT = 0.0
        HOT_POOL.clear()
        COLD_POOL.clear()
        LAST_USED.clear()
        USAGE_COUNT.clear()


async def _restart_permanent(cfg: BrowserConfig, trigger: str = "manual"):
    """Close and recreate the permanent browser with concurrency safety.

    Three-phase protocol designed so that many concurrent triggers (e.g. 3
    requests all failing at once, or a health-check racing a scheduled
    restart) cause exactly ONE restart:

      Phase 1 — PERMANENT_RESTART_LOCK (mutual exclusion)
          Re-check: if a restart is already in flight (_RESTART_DONE not set),
          another caller owns it — return immediately. Otherwise clear
          _RESTART_DONE so new default-config requests start hanging on
          get_crawler's gate. This lock + the _RESTART_DONE check together
          guarantee only one owner reaches Phase 3.

      Phase 2 — drain OUTSIDE LOCK (so release_crawler can decrement)
          Wait for in-flight requests (active_requests) to finish, up to 30s.
          On timeout we proceed anyway: a stuck request will receive
          "Target closed" and fail — that's the expected outcome, since a
          stuck request is exactly what health-check restarts are for.

      Phase 3 — LOCK + rebuild
          Close the old PERMANENT, build a fresh one via _build_permanent
          (shared with init_permanent), then set _RESTART_DONE to wake
          waiting requests. try/finally guarantees _RESTART_DONE.set() runs
          even if rebuild throws — otherwise all default-config requests
          would hang forever on get_crawler's gate.

    `cfg` is the config to rebuild with. Callers may pass None to reuse the
    cached PERMANENT_CFG (avoids re-reading config.yml, which may have been
    edited since startup).
    """
    global PERMANENT, PERMANENT_CFG, PERMANENT_STARTED_AT, DEFAULT_CONFIG_SIG

    if cfg is None:
        cfg = PERMANENT_CFG
    if cfg is None:
        logger.warning(f"🔄 restart({trigger}): no cached config, skipping")
        return

    async with PERMANENT_RESTART_LOCK:
        # Re-check: if not set, a restart is already running — let that owner finish.
        if not _RESTART_DONE.is_set():
            return
        _RESTART_DONE.clear()  # new default-config requests now hang in get_crawler
        logger.info(f"🔄 Restarting permanent browser (trigger={trigger})")

    # Phase 2: drain in-flight requests WITHOUT holding LOCK.
    # 30s 上限：浏览器卡死时在飞请求不会自然结束，注定等满超时；尽量短以
    # 避免后续请求被 get_crawler 的 gate 卡太久（HTTP 客户端通常 30-60s 超时）。
    # 保留 drain 结构是为了 scheduled restart（浏览器健康）场景下不强杀在飞请求。
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if getattr(PERMANENT, "active_requests", 0) <= 0:
            break
        await asyncio.sleep(0.5)
    if getattr(PERMANENT, "active_requests", 0) > 0:
        logger.warning(
            f"🔄 Drain timed out with {PERMANENT.active_requests} active request(s) "
            f"— forcing restart (in-flight requests will fail)"
        )

    # Phase 3: rebuild under LOCK. try/finally guarantees _RESTART_DONE.set()
    # even if PERMANENT.start() throws — without it, all default-config
    # requests would hang forever on get_crawler's gate.
    async with LOCK:
        try:
            if PERMANENT:
                with suppress(Exception):
                    await PERMANENT.close()
                PERMANENT = None
            PERMANENT_CFG = cfg
            DEFAULT_CONFIG_SIG = _sig(cfg)
            logger.info("🔥 Recreating permanent default browser")
            PERMANENT = _build_permanent(cfg)
            await PERMANENT.start()
            PERMANENT_STARTED_AT = time.monotonic()  # new epoch
            LAST_USED[DEFAULT_CONFIG_SIG] = time.time()
            USAGE_COUNT[DEFAULT_CONFIG_SIG] = 0
            logger.info(f"🔄 Permanent browser restarted (trigger={trigger})")
        except Exception as e:
            # Rebuild failed. Leave PERMANENT in whatever state it ended in
            # (likely None) and log; get_crawler will fall through to the
            # HOT/COLD pool path so requests still get served.
            logger.error(
                f"🔄 Permanent browser restart FAILED ({trigger}): {e} "
                f"— requests will fall through to other pools"
            )
            # Don't re-raise: a failed restart should not crash the caller
            # (e.g. janitor). The next unhealthy trigger will retry.
        finally:
            _RESTART_DONE.set()  # wake waiting get_crawler callers, no matter what


async def reset_permanent(cfg: Optional[BrowserConfig] = None):
    """Restart the permanent browser (thin wrapper over _restart_permanent).

    Kept as the public entry for the ``/actions/restart_browser`` endpoint
    and any external caller. Defaults to the cached PERMANENT_CFG when cfg
    is None.
    """
    await _restart_permanent(cfg, trigger="manual")

async def janitor():
    """Adaptive cleanup based on memory pressure."""
    while True:
        mem_pct = get_container_memory_percent()

        # Adaptive intervals and TTLs
        if mem_pct > 80:
            interval, cold_ttl, hot_ttl = 10, 30, 120
        elif mem_pct > 60:
            interval, cold_ttl, hot_ttl = 30, 60, 300
        else:
            interval, cold_ttl, hot_ttl = 60, BASE_IDLE_TTL, BASE_IDLE_TTL * 2

        await asyncio.sleep(interval)

        now_mono = time.monotonic()
        now = time.time()  # wall-clock for LAST_USED TTL comparisons

        # ── Proactive permanent-browser maintenance (BEFORE the LOCK block) ──
        # _restart_permanent acquires LOCK internally during its rebuild phase,
        # so these MUST run outside `async with LOCK` to avoid a self-deadlock.
        if PERMANENT:
            # 1) Scheduled restart: shed accumulated state corruption before the
            #    browser hangs. Bounded by RESTART_INTERVAL_SEC (0 disables).
            if (RESTART_INTERVAL_SEC > 0
                    and now_mono - PERMANENT_STARTED_AT > RESTART_INTERVAL_SEC):
                logger.info(
                    f"🕐 Scheduled restart: permanent ran "
                    f"{(now_mono - PERMANENT_STARTED_AT)/3600:.1f}h "
                    f"(limit {RESTART_INTERVAL_SEC/3600:.1f}h)"
                )
                await _restart_permanent(PERMANENT_CFG, trigger="scheduled")
            # 2) Periodic health probe — every 300s, regardless of busy state.
            #    The original `active_requests == 0` gate was the root cause
            #    of the 7.5h unrecovered hang: it never held while a request
            #    was stuck on a wedged browser. Removing the busy-state check
            #    entirely is the fix — any state-dependent gate (including
            #    "busy_for > N seconds") reintroduces a variant of the same bug.
            #
            #    Safe because:
            #    - Task 1's wait_for guarantees probe returns within ~12s
            #    - probe uses default_context.new_page() creating a NEW page;
            #      about:blank + Date.now() doesn't touch network/CPU/GPU and
            #      doesn't interfere with in-flight crawl pages on the same context
            #    - 300s throttle keeps overhead at ~0.07% (200ms probe / 300s)
            elif now_mono - _LAST_HEALTH_PROBE_AT > 300:
                # mark throttle first so a slow probe doesn't re-trigger
                globals()["_LAST_HEALTH_PROBE_AT"] = now_mono
                try:
                    bm = PERMANENT.crawler_strategy.browser_manager
                    if (hasattr(bm, "_probe_browser_health")
                            and not await bm._probe_browser_health()):
                        logger.warning("🩺 Health probe FAILED — triggering restart")
                        await _restart_permanent(PERMANENT_CFG, trigger="health_check")
                except Exception as e:
                    logger.warning(f"🩺 Permanent health probe error: {e}")

        async with LOCK:
            # Clean cold pool
            for sig in list(COLD_POOL.keys()):
                if now - LAST_USED.get(sig, now) > cold_ttl:
                    crawler = COLD_POOL[sig]
                    if getattr(crawler, 'active_requests', 0) > 0:
                        continue  # still serving requests, skip
                    idle_time = now - LAST_USED[sig]
                    logger.info(f"🧹 Closing cold browser (sig={sig[:8]}, idle={idle_time:.0f}s)")
                    with suppress(Exception):
                        await crawler.close()
                    COLD_POOL.pop(sig, None)
                    LAST_USED.pop(sig, None)
                    USAGE_COUNT.pop(sig, None)

                    # Track in monitor
                    try:
                        from monitor import get_monitor
                        await get_monitor().track_janitor_event("close_cold", sig, {"idle_seconds": int(idle_time), "ttl": cold_ttl})
                    except:
                        pass

            # Clean hot pool (more conservative)
            for sig in list(HOT_POOL.keys()):
                if now - LAST_USED.get(sig, now) > hot_ttl:
                    crawler = HOT_POOL[sig]
                    if getattr(crawler, 'active_requests', 0) > 0:
                        continue  # still serving requests, skip
                    idle_time = now - LAST_USED[sig]
                    logger.info(f"🧹 Closing hot browser (sig={sig[:8]}, idle={idle_time:.0f}s)")
                    with suppress(Exception):
                        await crawler.close()
                    HOT_POOL.pop(sig, None)
                    LAST_USED.pop(sig, None)
                    USAGE_COUNT.pop(sig, None)

                    # Track in monitor
                    try:
                        from monitor import get_monitor
                        await get_monitor().track_janitor_event("close_hot", sig, {"idle_seconds": int(idle_time), "ttl": hot_ttl})
                    except:
                        pass

            # Log pool stats
            if mem_pct > 60:
                logger.info(f"📊 Pool: hot={len(HOT_POOL)}, cold={len(COLD_POOL)}, mem={mem_pct:.1f}%")
