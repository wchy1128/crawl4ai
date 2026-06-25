"""
Crawl4AI Regression Tests - Browser Management and Features

Tests browser lifecycle, viewport configuration, wait_for conditions, JavaScript
execution, page interaction, screenshots, iframe processing, overlay removal,
stealth mode, session management, network capture, and anti-bot features using
real browser crawling with no mocking.
"""

import base64
import time

import pytest

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.cache_context import CacheMode


# ---------------------------------------------------------------------------
# Browser lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browser_lifecycle(local_server):
    """Create crawler, start, crawl, and close explicitly without context manager."""
    crawler = AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False))
    await crawler.start()
    try:
        result = await crawler.arun(
            url=local_server + "/",
            config=CrawlerRunConfig(verbose=False),
        )
        assert result.success, f"Crawl failed: {result.error_message}"
        assert len(result.html) > 0, "HTML should be non-empty"
    finally:
        await crawler.close()


@pytest.mark.asyncio
async def test_browser_context_manager(local_server):
    """Verify async with pattern works and cleanup happens without error."""
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(
            url=local_server + "/",
            config=CrawlerRunConfig(verbose=False),
        )
        assert result.success, f"Context manager crawl failed: {result.error_message}"
    # If we get here without exception, cleanup succeeded


# ---------------------------------------------------------------------------
# Viewport configuration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_viewport(local_server):
    """Create BrowserConfig with 1920x1080 viewport and verify crawl succeeds."""
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        viewport_width=1920,
        viewport_height=1080,
    )
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=local_server + "/",
            config=CrawlerRunConfig(verbose=False),
        )
        assert result.success, f"Custom viewport crawl failed: {result.error_message}"


@pytest.mark.asyncio
async def test_small_viewport(local_server):
    """Mobile-like viewport (375x667) should still produce a successful crawl."""
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        viewport_width=375,
        viewport_height=667,
    )
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=local_server + "/",
            config=CrawlerRunConfig(verbose=False),
        )
        assert result.success, f"Small viewport crawl failed: {result.error_message}"


# ---------------------------------------------------------------------------
# wait_for conditions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_css_selector(local_server):
    """Wait for a CSS selector on /js-dynamic and verify dynamic content loaded."""
    config = CrawlerRunConfig(wait_for="css:.js-loaded", verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/js-dynamic", config=config)
        assert result.success, f"wait_for CSS crawl failed: {result.error_message}"
        assert "Dynamic content successfully loaded" in (result.markdown or ""), (
            "Dynamic JS content should appear after waiting for .js-loaded"
        )


@pytest.mark.asyncio
async def test_wait_for_js_function(local_server):
    """Wait for a JS condition on /js-dynamic and verify the counter value."""
    config = CrawlerRunConfig(
        wait_for="js:() => document.getElementById('counter').textContent === '42'",
        verbose=False,
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/js-dynamic", config=config)
        assert result.success, f"wait_for JS crawl failed: {result.error_message}"
        assert "42" in (result.html or ""), (
            "Counter should be set to 42 after JS wait condition is met"
        )


@pytest.mark.asyncio
async def test_wait_for_timeout(local_server):
    """Wait for a non-existent selector with short timeout should not hang forever."""
    config = CrawlerRunConfig(
        wait_for="css:.nonexistent-class",
        wait_for_timeout=500,
        verbose=False,
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        # This may succeed (with timeout warning) or fail, but should not hang
        result = await crawler.arun(url=local_server + "/js-dynamic", config=config)
        # We just verify it returned without hanging; success or failure is acceptable
        assert result is not None, "Should return a result even if wait_for times out"


# ---------------------------------------------------------------------------
# JavaScript execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_js_code_modifies_dom(local_server):
    """Execute JS that adds a DOM element and verify it appears in the result."""
    config = CrawlerRunConfig(
        js_code='document.body.innerHTML += \'<div id="injected">Injected by JS</div>\';',
        verbose=False,
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, f"JS DOM modification crawl failed: {result.error_message}"
        combined = (result.html or "") + (result.markdown or "")
        assert "Injected by JS" in combined, (
            "Injected content should appear in HTML or markdown"
        )
        # A statement-style script (no return) still yields a uniform envelope:
        # { success: True, result: None }. This guards the contract for the most
        # common js_code usage (side effects, not return values).
        entry = result.js_execution_result["results"][0]
        assert isinstance(entry, dict) and entry.get("success") is True, (
            f"side-effect script entry must be a {{success:True,...}} envelope; got {entry!r}"
        )


@pytest.mark.asyncio
async def test_js_code_returns_value(local_server):
    """A bare-top-level `return x;` script MUST carry its value in a strict
    { success, result } envelope.

    Regression guard. robust_execute_user_script wraps the user script inside an
    inner async IIFE and captures its return value into an envelope:

        const __c4a_result = await (async () => { <script> })();
        return { success: true, result: __c4a_result };

    A bare `return x;` lives directly in the inner function body, so its value
    flows out as `__c4a_result` and is carried back under the "result" key.

    Before the fix the wrapper returned the value as a BARE SCALAR (e.g. the raw
    string "Crawl4AI Test Home") with NO envelope, so consumers reading
    results[i]["result"] broke with a TypeError and the per-script schema was
    inconsistent. This test pins the strict envelope shape so that regression
    cannot return: results[0] MUST be a dict with `success` True and `result`
    holding the title. A bare scalar fails the very first isinstance check.

    NOTE on usage contract: the supported way to carry a value back from js_code
    is a top-level `return`. An IIFE/expression like `(() => { return x; })()`
    is NOT supported — its value is unreachable by JS design (the inner function
    body has no return) and is not covered here on purpose.
    """
    config = CrawlerRunConfig(
        js_code="return document.title;",
        verbose=False,
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, f"JS return value crawl failed: {result.error_message}"
        assert result.js_execution_result is not None, (
            "js_execution_result must be populated when js_code runs"
        )
        entry = result.js_execution_result["results"][0]
        assert isinstance(entry, dict), (
            f"result entry must be a {{success, result}} envelope, not a bare scalar; "
            f"got {entry!r} — this is the no-envelope regression"
        )
        assert entry.get("success") is True, f"entry success expected True; got {entry!r}"
        assert "result" in entry, (
            f"entry must carry the value under 'result'; a {{success:True}}-only entry "
            f"means the value was dropped — got {entry!r}"
        )
        assert "Crawl4AI Test Home" in str(entry["result"]), (
            f"expected document.title under 'result'; got {entry['result']!r}"
        )


@pytest.mark.asyncio
async def test_multiple_js_scripts(local_server):
    """A list of bare scripts: each result entry MUST be a { success, result }
    envelope, and a trailing `return` carries the final value back.

    The old version of this test asserted nothing (only result.success), so it
    could not catch the no-envelope regression. Now it pins that every list
    entry is a dict envelope and that the final script's return value flows out.
    """
    config = CrawlerRunConfig(
        js_code=["document.title='A';", "return document.title;"],
        verbose=False,
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, f"Multiple JS scripts crawl failed: {result.error_message}"
        entries = result.js_execution_result["results"]
        assert len(entries) == 2, f"expected 2 per-script results; got {entries!r}"
        for e in entries:
            assert isinstance(e, dict) and e.get("success") is True, (
                f"every list entry must be a {{success:True,...}} envelope; got {e!r}"
            )
        # second script returns the title that the first script set to 'A'
        assert entries[1]["result"] == "A", (
            f"second script should return title 'A'; got {entries[1]!r}"
        )


@pytest.mark.asyncio
async def test_js_code_falsy_return_preserved(local_server):
    """A legitimate falsy return value (0) MUST be preserved in the envelope,
    not swallowed into a bare { success: True }.

    Before the envelope fix the Python layer did `results.append(result if
    result else {"success": True})`: `0` is falsy in Python, so `return 0;`
    collapsed to a {success:True}-only entry and the value 0 was lost. The
    envelope now wraps the value as { success: True, result: 0 } regardless of
    truthiness, which this test pins.
    """
    config = CrawlerRunConfig(js_code="return 0;", verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, f"falsy-return crawl failed: {result.error_message}"
        entry = result.js_execution_result["results"][0]
        assert isinstance(entry, dict) and entry.get("success") is True, (
            f"entry must be a {{success:True,...}} envelope; got {entry!r}"
        )
        assert "result" in entry and entry["result"] == 0, (
            f"legitimate falsy return 0 must be preserved as {{success:True,result:0}}; "
            f"got {entry!r}"
        )


# ---------------------------------------------------------------------------
# Page interaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_full_page(local_server):
    """Crawl /large with scan_full_page=True and verify bottom sections appear."""
    config = CrawlerRunConfig(
        scan_full_page=True,
        scroll_delay=0.05,
        verbose=False,
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/large", config=config)
        assert result.success, f"Full page scan crawl failed: {result.error_message}"
        # The large page has 50 sections; verify some from near the bottom
        combined = (result.html or "") + (result.markdown or "")
        assert "Section 49" in combined, (
            "Scanning the full page should reveal the last section (Section 49)"
        )


# ---------------------------------------------------------------------------
# Screenshot features
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screenshot_basic(local_server):
    """Crawl with screenshot=True, decode base64, and verify PNG header."""
    config = CrawlerRunConfig(screenshot=True, verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, f"Screenshot crawl failed: {result.error_message}"
        assert result.screenshot, "Screenshot should be a non-empty base64 string"
        raw_bytes = base64.b64decode(result.screenshot)
        assert raw_bytes[:4] == b"\x89PNG", (
            "Screenshot should be in PNG format"
        )


@pytest.mark.asyncio
async def test_force_viewport_screenshot(local_server):
    """Crawl /large with force_viewport_screenshot=True; should capture viewport only."""
    config = CrawlerRunConfig(
        screenshot=True,
        force_viewport_screenshot=True,
        verbose=False,
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/large", config=config)
        assert result.success, f"Force viewport screenshot crawl failed: {result.error_message}"
        assert result.screenshot, "Screenshot should be captured"
        raw_bytes = base64.b64decode(result.screenshot)
        assert raw_bytes[:4] == b"\x89PNG", "Viewport screenshot should be PNG"


# ---------------------------------------------------------------------------
# Process iframes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_iframes(local_server):
    """Crawl /iframe-page with process_iframes=True and verify iframe content appears."""
    config = CrawlerRunConfig(process_iframes=True, verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/iframe-page", config=config)
        assert result.success, f"Iframe processing crawl failed: {result.error_message}"
        combined = (result.html or "") + (result.markdown or "")
        # At least one iframe's content should appear
        has_iframe_content = (
            "Iframe 1 content" in combined
            or "Iframe 2 heading" in combined
            or "embedded" in combined.lower()
        )
        assert has_iframe_content, (
            "Iframe content should appear in the result when process_iframes=True"
        )


# ---------------------------------------------------------------------------
# Overlay and popup removal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_overlay_elements(local_server):
    """Crawl with remove_overlay_elements=True; verify it does not break crawling."""
    config = CrawlerRunConfig(remove_overlay_elements=True, verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, (
            f"Overlay removal should not break crawling: {result.error_message}"
        )
        assert len(result.html) > 0, "HTML should still be present after overlay removal"


# ---------------------------------------------------------------------------
# Stealth mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stealth_mode_no_crash(local_server):
    """Stealth mode should not break basic local crawling."""
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        enable_stealth=True,
    )
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=local_server + "/",
            config=CrawlerRunConfig(verbose=False),
        )
        assert result.success, f"Stealth mode crawl failed: {result.error_message}"
        assert "Crawl4AI Test Home" in (result.html or ""), (
            "Stealth mode should still extract content correctly"
        )


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_persistence(local_server):
    """Session state should persist between crawls with the same session_id."""
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        # First crawl: set a JS variable
        config1 = CrawlerRunConfig(
            session_id="persist-test",
            js_code="window.__testVar = 'hello';",
            verbose=False,
        )
        result1 = await crawler.arun(url=local_server + "/", config=config1)
        assert result1.success, f"First session crawl failed: {result1.error_message}"

        # Second crawl: read the JS variable using js_only mode
        config2 = CrawlerRunConfig(
            session_id="persist-test",
            js_only=True,
            js_code="return window.__testVar;",
            verbose=False,
        )
        result2 = await crawler.arun(url=local_server + "/", config=config2)
        assert result2.success, f"Second session crawl failed: {result2.error_message}"

        # Check if testVar persisted. The return value of the second crawl's
        # js_code ("return window.__testVar;") MUST be carried in a strict
        # { success, result } envelope, not just a success flag. Before the fix
        # the value came back as a bare scalar with no envelope; the isinstance +
        # "result" key checks fail on that bare-scalar shape, so the value-loss
        # regression cannot pass silently.
        assert result2.js_execution_result is not None, (
            "js_execution_result must be populated when js_code runs"
        )
        entry = result2.js_execution_result["results"][0]
        assert isinstance(entry, dict), (
            f"result entry must be a {{success, result}} envelope, not a bare scalar; "
            f"got {entry!r}"
        )
        assert entry.get("success") is True, f"entry success expected True; got {entry!r}"
        assert "result" in entry, (
            f"entry must carry the value under 'result'; got {entry!r}"
        )
        assert "hello" in str(entry["result"]), (
            f"Session variable should persist; got result={entry['result']!r}"
        )


# ---------------------------------------------------------------------------
# Delay before return HTML
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delay_before_return(local_server):
    """Crawl with delay_before_return_html=0.5 should succeed and take reasonable time."""
    config = CrawlerRunConfig(delay_before_return_html=0.5, verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        start_time = time.monotonic()
        result = await crawler.arun(url=local_server + "/", config=config)
        elapsed = time.monotonic() - start_time

        assert result.success, f"Delayed crawl failed: {result.error_message}"
        assert elapsed >= 0.4, (
            f"Crawl with 0.5s delay should take at least 0.4s, took {elapsed:.2f}s"
        )


# ---------------------------------------------------------------------------
# Network features
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_network_requests(local_server):
    """Crawl /js-dynamic with capture_network_requests=True and verify list returned."""
    config = CrawlerRunConfig(
        capture_network_requests=True,
        cache_mode=CacheMode.BYPASS,
        verbose=False,
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/js-dynamic", config=config)
        assert result.success, f"Network capture crawl failed: {result.error_message}"
        assert result.network_requests is not None, "network_requests should not be None"
        assert isinstance(result.network_requests, list), (
            "network_requests should be a list"
        )
        assert len(result.network_requests) >= 1, (
            "Should capture at least 1 network request (the page itself)"
        )


@pytest.mark.asyncio
async def test_capture_console_messages(local_server):
    """Crawl with capture_console_messages=True and verify the attribute is a list."""
    config = CrawlerRunConfig(
        capture_console_messages=True,
        cache_mode=CacheMode.BYPASS,
        verbose=False,
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, f"Console capture crawl failed: {result.error_message}"
        assert result.console_messages is not None, (
            "console_messages should not be None when capture is enabled"
        )
        assert isinstance(result.console_messages, list), (
            "console_messages should be a list"
        )


# ---------------------------------------------------------------------------
# Real URL browser tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.network
async def test_real_url_with_wait():
    """Crawl https://quotes.toscrape.com with wait_until='load' and verify content."""
    config = CrawlerRunConfig(wait_until="load", verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url="https://quotes.toscrape.com", config=config)
        assert result.success, f"Real URL crawl failed: {result.error_message}"
        assert len(result.html) > 100, "Real page should have substantial HTML"
        combined = (result.markdown or "") + (result.html or "")
        assert "quote" in combined.lower() or "quotes" in combined.lower(), (
            "Quotes page should contain the word 'quote'"
        )


@pytest.mark.asyncio
@pytest.mark.network
async def test_real_url_screenshot():
    """Crawl https://example.com with screenshot=True and verify PNG captured."""
    config = CrawlerRunConfig(screenshot=True, verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url="https://example.com", config=config)
        assert result.success, f"Real URL screenshot crawl failed: {result.error_message}"
        assert result.screenshot, "Screenshot should be non-empty"
        raw_bytes = base64.b64decode(result.screenshot)
        assert raw_bytes[:4] == b"\x89PNG", "Real URL screenshot should be PNG format"


# ---------------------------------------------------------------------------
# Anti-bot basic check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_magic_mode_no_crash(local_server):
    """Magic mode should not break normal local crawling."""
    config = CrawlerRunConfig(magic=True, verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, (
            f"Magic mode should not break crawling: {result.error_message}"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_empty_page(local_server):
    """Crawling a page with empty body should not crash, even if anti-bot flags it."""
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(
            url=local_server + "/empty",
            config=CrawlerRunConfig(verbose=False),
        )
        # Anti-bot detection may flag near-empty pages as blocked, which is expected
        # behavior. The key assertion is that it returns a result without crashing.
        assert result is not None, "Should return a result even for empty page"
        assert result.html is not None, "HTML should not be None for empty page"
        if not result.success:
            assert "empty" in (result.error_message or "").lower() or "blocked" in (result.error_message or "").lower(), (
                f"Empty page failure should mention empty/blocked content: {result.error_message}"
            )


@pytest.mark.asyncio
async def test_crawl_malformed_html(local_server):
    """Crawling malformed HTML should not crash, even if anti-bot flags it."""
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(
            url=local_server + "/malformed",
            config=CrawlerRunConfig(verbose=False),
        )
        # Anti-bot may flag malformed HTML as blocked due to minimal visible text.
        # The key assertion is that it returns a result without crashing.
        assert result is not None, "Should return a result for malformed HTML"
        assert result.html is not None, "HTML should not be None even for malformed input"
        # The content is present in the HTML even if the crawl is marked as not successful
        assert "Unclosed paragraph" in (result.html or "") or "Malformed" in (result.html or ""), (
            "Some original content should appear in the HTML"
        )


@pytest.mark.asyncio
async def test_multiple_crawls_same_crawler(local_server):
    """A single crawler instance should handle multiple sequential crawls."""
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        urls = [
            local_server + "/",
            local_server + "/products",
            local_server + "/js-dynamic",
        ]
        for url in urls:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(verbose=False),
            )
            assert result.success, f"Sequential crawl of {url} failed: {result.error_message}"


@pytest.mark.asyncio
async def test_screenshot_not_captured_by_default(local_server):
    """Without screenshot=True, result.screenshot should be None or empty."""
    config = CrawlerRunConfig(screenshot=False, verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, f"No-screenshot crawl failed: {result.error_message}"
        assert not result.screenshot, (
            "Screenshot should be None or empty when not requested"
        )


@pytest.mark.asyncio
async def test_js_code_empty_string(local_server):
    """Empty js_code string should not cause errors."""
    config = CrawlerRunConfig(js_code="", verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, (
            f"Empty js_code should not break crawling: {result.error_message}"
        )


@pytest.mark.asyncio
async def test_wait_until_load(local_server):
    """wait_until='load' should wait for full page load including resources."""
    config = CrawlerRunConfig(wait_until="load", verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, f"wait_until=load crawl failed: {result.error_message}"


@pytest.mark.asyncio
async def test_wait_until_networkidle(local_server):
    """wait_until='networkidle' should wait until network is idle."""
    config = CrawlerRunConfig(wait_until="networkidle", verbose=False)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=local_server + "/", config=config)
        assert result.success, f"wait_until=networkidle crawl failed: {result.error_message}"
