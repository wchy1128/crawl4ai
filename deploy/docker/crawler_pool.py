# crawler_pool.py - Smart browser pool with tiered management
import asyncio, json, hashlib, time
from contextlib import suppress
from typing import Dict, Optional
from crawl4ai import AsyncWebCrawler, BrowserConfig
from crawl4ai.browser_adapter import UndetectedAdapter
from crawl4ai.async_configs import UntrustedConfigError
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


def _assert_no_config_conflict(cfg: BrowserConfig, sig: str) -> None:
    """拦截与 pool 中已有 crawler 不可共存的浏览器配置冲突。

    必须在持有 LOCK 的情况下调用，保证对三层 pool 的读取是原子的。

    当前规则：
      user_data_dir 在 use_managed_browser / use_persistent_context 模式下是
      Chrome 独占资源（SingletonLock 保证一个目录只能被一个 Chrome 进程持有）。
      两个不同 sig 的 crawler 共用同一目录时，ManagedBrowser.start 的"启动前
      清理"块会 kill 旧进程并删锁，导致 profile 数据损坏与静默故障。
      因此在 pool 层提前拦截：要新建 crawler 时，若其 user_data_dir 已被别的
      sig 占用，直接抛 ValueError，让上层把信息返回给调用方/大模型。

    新增冲突规则（如 cdp_url / debugging_port / proxy 端口冲突）时，在此函数
    内追加分支即可，调用方无需改动。

    判定逻辑：
      - sig 已在三层 pool 中（PERMANENT/HOT_POOL/COLD_POOL）→ 本次会复用已有
        crawler，不会新建实例，不可能产生冲突，直接返回。
      - sig 不在 pool → 本次要新建 crawler。遍历三层 pool 看是否有别的 sig
        占了同一个 user_data_dir，命中则抛错。
    """
    udd = getattr(cfg, "user_data_dir", None)
    # 不消费 user_data_dir 的模式（普通 launch）下，该字段被忽略，不算冲突
    if not udd or not (cfg.use_managed_browser or cfg.use_persistent_context):
        return

    # sig 已在 pool → 复用已有 crawler，不会新建，不可能冲突
    if (PERMANENT and sig == DEFAULT_CONFIG_SIG) or sig in HOT_POOL or sig in COLD_POOL:
        return

    # sig 不在 pool → 要新建 crawler，检查 user_data_dir 是否已被占用
    # 把三层 pool 摊平成 (owner_sig, crawler) 列表统一遍历
    owners = []
    if PERMANENT:
        owners.append((DEFAULT_CONFIG_SIG, PERMANENT))
    owners.extend(HOT_POOL.items())
    owners.extend(COLD_POOL.items())
    for owner_sig, crawler in owners:
        owner_udd = getattr(crawler.browser_config, "user_data_dir", None)
        if owner_udd == udd:
            msg = (
                f"user_data_dir '{udd}' is already owned by another browser "
                f"(owner_sig={owner_sig[:8]}, request_sig={sig[:8]}). "
                f"Sharing a Chrome profile directory across processes would "
                f"corrupt profile data; request rejected."
            )
            logger.error("⛔ [ConfigConflict] %s", msg)
            raise UntrustedConfigError(msg)


async def _is_alive(crawler: AsyncWebCrawler) -> bool:
    """快速活性探测。返回 False 表示底层 browser/context 已死
    （例如用户手动关了浏览器窗口）。best-effort。"""
    try:
        bm = crawler.crawler_strategy.browser_manager
        if bm.browser is not None:
            # CDP / managed_browser 模式：is_connected() 由 transport 维护，可靠
            return bm.browser.is_connected()
        if bm.default_context is not None:
            # persistent_context 模式下 browser=None，只有 default_context。
            # pages 属性是缓存的不触发 IPC；必须调用 cookies() 强制 IPC，
            # 死了的 context 会抛 'Target page, context or browser has been closed'。
            await bm.default_context.cookies()
            return True
        return False
    except Exception:
        return False


async def get_crawler(cfg: BrowserConfig) -> AsyncWebCrawler:
    """Get crawler from pool with tiered strategy."""
    global PERMANENT
    sig = _sig(cfg)
    async with LOCK:
        # 拦截配置冲突（命中会抛 ValueError，上层 except Exception 会把信息返回给调用方）
        _assert_no_config_conflict(cfg, sig)
        # Check permanent browser for default config
        if PERMANENT and _is_default_config(sig):
            if not await _is_alive(PERMANENT):
                logger.warning("⚠️ Permanent browser dead (killed externally?), recreating")
                with suppress(Exception):
                    await PERMANENT.close()
                PERMANENT = None
            else:
                LAST_USED[sig] = time.time()
                USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
                if not hasattr(PERMANENT, 'active_requests'):
                    PERMANENT.active_requests = 0
                PERMANENT.active_requests += 1
                logger.info("🔥 Using permanent browser")
                return PERMANENT

        # Check hot pool
        if sig in HOT_POOL:
            crawler = HOT_POOL[sig]
            if not await _is_alive(crawler):
                logger.warning(f"⚠️ Hot pool browser dead (sig={sig[:8]}), recreating")
                with suppress(Exception):
                    await crawler.close()
                HOT_POOL.pop(sig, None)
            else:
                LAST_USED[sig] = time.time()
                USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
                if not hasattr(crawler, 'active_requests'):
                    crawler.active_requests = 0
                crawler.active_requests += 1
                logger.info(f"♨️  Using hot pool browser (sig={sig[:8]}, active={crawler.active_requests})")
                return crawler

        # Check cold pool (promote to hot if used 3+ times)
        if sig in COLD_POOL:
            crawler = COLD_POOL[sig]
            if not await _is_alive(crawler):
                logger.warning(f"⚠️ Cold pool browser dead (sig={sig[:8]}), recreating")
                with suppress(Exception):
                    await crawler.close()
                COLD_POOL.pop(sig, None)
            else:
                LAST_USED[sig] = time.time()
                USAGE_COUNT[sig] = USAGE_COUNT.get(sig, 0) + 1
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

        # Create new (default config → PERMANENT, otherwise cold pool)
        is_default = _is_default_config(sig)
        logger.info(f"🆕 Creating new browser ({'permanent' if is_default else 'cold pool'}, sig={sig[:8]}, mem={mem_pct:.1f}%)")
        adapter = UndetectedAdapter() if USE_UNDETECTED else None
        crawler = AsyncWebCrawler(config=cfg, thread_safe=False, browser_adapter=adapter) if adapter else AsyncWebCrawler(config=cfg, thread_safe=False)
        await crawler.start()
        crawler.active_requests = 1
        if is_default:
            PERMANENT = crawler
        else:
            COLD_POOL[sig] = crawler
        LAST_USED[sig] = time.time()
        USAGE_COUNT[sig] = 1
        return crawler

async def release_crawler(crawler: AsyncWebCrawler):
    """Decrement active request count for a pooled crawler.

    Call this in a finally block after finishing work with a crawler
    obtained via get_crawler() so the janitor knows when it's safe
    to close idle browsers.
    """
    async with LOCK:
        if hasattr(crawler, 'active_requests'):
            crawler.active_requests = max(0, crawler.active_requests - 1)

async def init_permanent(cfg: BrowserConfig):
    """Initialize permanent default browser."""
    global PERMANENT, DEFAULT_CONFIG_SIG
    async with LOCK:
        if PERMANENT:
            return
        DEFAULT_CONFIG_SIG = _sig(cfg)
        logger.info("🔥 Creating permanent default browser")
        adapter = UndetectedAdapter() if USE_UNDETECTED else None
        PERMANENT = AsyncWebCrawler(config=cfg, thread_safe=False, browser_adapter=adapter) if adapter else AsyncWebCrawler(config=cfg, thread_safe=False)
        await PERMANENT.start()
        LAST_USED[DEFAULT_CONFIG_SIG] = time.time()
        USAGE_COUNT[DEFAULT_CONFIG_SIG] = 0

async def close_all():
    """Close all browsers."""
    async with LOCK:
        tasks = []
        if PERMANENT:
            tasks.append(PERMANENT.close())
        tasks.extend([c.close() for c in HOT_POOL.values()])
        tasks.extend([c.close() for c in COLD_POOL.values()])
        await asyncio.gather(*tasks, return_exceptions=True)
        HOT_POOL.clear()
        COLD_POOL.clear()
        LAST_USED.clear()
        USAGE_COUNT.clear()

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

        now = time.time()
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
