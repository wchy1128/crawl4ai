"""
Regression tests for flatten_shadow_dom feature.

Covers:
- Fast-path: pages without shadow DOM return outerHTML directly (no content loss)
- Normal path: pages with shadow DOM correctly extract shadow content
- Regression: svelte.dev-like pages (scoped CSS, no shadow DOM) — the original bug
"""

import re

import pytest

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


# ---------------------------------------------------------------------------
# Fast-path — pages WITHOUT shadow DOM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flatten_no_shadow_page(local_server):
    """No-shadow page with flatten_shadow_dom=True should return full content."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/no-shadow",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )
        assert result.success, f"Crawl failed: {result.error_message}"
        html = result.html or ""
        assert "Documentation" in html, "Sidebar nav should be present"
        assert "Getting Started" in html, "Section heading should be present"
        assert "API Overview" in html, "Second section should be present"
        assert "Install the package" in html, "List items should be present"


@pytest.mark.asyncio
async def test_flatten_no_shadow_content_parity(local_server):
    """flatten_shadow_dom=True vs False should yield near-identical content on no-shadow page."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result_off = await crawler.arun(
            url=local_server + "/no-shadow",
            config=CrawlerRunConfig(flatten_shadow_dom=False, verbose=False),
        )
        result_on = await crawler.arun(
            url=local_server + "/no-shadow",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )

    assert result_off.success and result_on.success, "Both crawls should succeed"
    html_off = result_off.html or ""
    html_on = result_on.html or ""

    # HTML lengths should be very close (within 2% or 50 chars)
    len_diff = abs(len(html_off) - len(html_on))
    max_len = max(len(html_off), len(html_on))
    assert len_diff <= max(50, max_len * 0.02), (
        f"HTML length disparity: off={len(html_off)} on={len(html_on)} diff={len_diff}"
    )

    # All key text content should be present in both
    for text in [
        "Documentation",
        "Introduction",
        "Getting Started",
        "Install the package",
        "API Overview",
        "List all users",
    ]:
        assert text in html_on, f"'{text}' should be in flatten_shadow_dom=True output"
        assert text in html_off, f"'{text}' should be in flatten_shadow_dom=False output"


@pytest.mark.asyncio
async def test_flatten_home_page(local_server):
    """Home page (no shadow DOM) with flatten_shadow_dom=True should preserve all content."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )
        assert result.success, f"Crawl failed: {result.error_message}"
        html = result.html or ""
        assert "Crawl4AI Test Home" in html, "Title should be present"
        assert "Features Overview" in html, "h2 should be present"
        assert "Code Example" in html, "Code section should be present"
        assert "Internal Links" in html, "Internal links section should be present"
        assert "Footer content" in html, "Footer should be present"


@pytest.mark.asyncio
async def test_flatten_products_page(local_server):
    """Products page (no shadow DOM) with flatten_shadow_dom=True should preserve all products."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/products",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )
        assert result.success, f"Crawl failed: {result.error_message}"
        html = result.html or ""
        for product in [
            "Wireless Mouse", "Mechanical Keyboard", "USB-C Hub",
            "Monitor Stand", "Webcam HD",
        ]:
            assert product in html, f"'{product}' should be present"


@pytest.mark.asyncio
async def test_flatten_large_page(local_server):
    """Large page (50 sections) with flatten_shadow_dom=True should include last sections."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/large",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )
        assert result.success, f"Crawl failed: {result.error_message}"
        html = result.html or ""
        assert "Section 0" in html, "First section should be present"
        assert "Section 49" in html, "Last section should be present"


@pytest.mark.asyncio
async def test_flatten_empty_page(local_server):
    """Empty page with flatten_shadow_dom=True should not crash."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/empty",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )
        assert result is not None, "Should return a result"
        assert result.html is not None, "HTML should not be None"


@pytest.mark.asyncio
async def test_flatten_malformed(local_server):
    """Malformed HTML with flatten_shadow_dom=True should not crash."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/malformed",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )
        assert result is not None, "Should return a result"
        assert result.html is not None, "HTML should not be None"


@pytest.mark.asyncio
async def test_flatten_multiple_crawls(local_server):
    """Multiple sequential crawls with flatten_shadow_dom=True should all succeed."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        urls = [
            local_server + "/",
            local_server + "/products",
            local_server + "/no-shadow",
            local_server + "/tables",
            local_server + "/links-page",
        ]
        for url in urls:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
            )
            assert result.success, f"Sequential crawl of {url} failed: {result.error_message}"
            assert result.html and len(result.html) > 0, f"HTML should be non-empty for {url}"


@pytest.mark.asyncio
async def test_flatten_js_dynamic(local_server):
    """JS dynamic page with flatten_shadow_dom=True should include JS-loaded content."""
    config = CrawlerRunConfig(
        flatten_shadow_dom=True,
        wait_for="css:.js-loaded",
        verbose=False,
    )
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/js-dynamic",
            config=config,
        )
        assert result.success, f"Crawl failed: {result.error_message}"
        combined = (result.html or "") + (result.markdown or "")
        assert "Dynamic content successfully loaded" in combined, (
            "JS-loaded content should appear"
        )
        assert "Item A" in combined, "Dynamic list items should be present"


@pytest.mark.asyncio
async def test_flatten_html_length_reasonable(local_server):
    """flatten_shadow_dom=True should not produce absurdly short or long HTML."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/no-shadow",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )
        assert result.success, f"Crawl failed: {result.error_message}"
        html = result.html or ""
        assert len(html) > 1000, f"HTML too short ({len(html)} chars), content likely missing"
        assert len(html) < 100000, f"HTML suspiciously large ({len(html)} chars)"


# ---------------------------------------------------------------------------
# Shadow DOM pages — normal path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flatten_shadow_dom_page(local_server):
    """Page with shadow DOM + flatten_shadow_dom=True should capture shadow content."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/shadow-dom",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )
        assert result.success, f"Crawl failed: {result.error_message}"
        html = result.html or ""
        assert "Content Inside Open Shadow Root" in html, (
            "Open shadow root content should be captured"
        )
        assert "Regular Light DOM Content" in html, (
            "Regular light DOM content should still be present"
        )
        assert "Hello from light DOM!" in html, (
            "Slotted light DOM content should appear"
        )


@pytest.mark.asyncio
async def test_flatten_shadow_dom_closed_root(local_server):
    """Closed shadow root should become accessible via init script patching."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/shadow-dom",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )
        assert result.success, f"Crawl failed: {result.error_message}"
        html = result.html or ""
        assert "Content Inside Closed Shadow Root" in html, (
            "Closed shadow root content should be captured"
        )
        assert "Closed shadow item A" in html, (
            "Closed shadow list items should be captured"
        )


@pytest.mark.asyncio
async def test_flatten_shadow_dom_custom_element(local_server):
    """Custom elements with shadow DOM should have their content captured."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/shadow-dom",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )
        assert result.success, f"Crawl failed: {result.error_message}"
        html = result.html or ""
        assert "Custom Card Title" in html, (
            "Custom element slotted title should appear"
        )
        assert "Custom card body text" in html, (
            "Custom element slotted body should appear"
        )
        assert "Default Title" in html, (
            "Fallback slot content should appear when no slot provided"
        )


@pytest.mark.asyncio
async def test_flatten_shadow_dom_improves_content(local_server):
    """flatten_shadow_dom=True should capture MORE content than False on shadow DOM pages."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result_off = await crawler.arun(
            url=local_server + "/shadow-dom",
            config=CrawlerRunConfig(flatten_shadow_dom=False, verbose=False),
        )
        result_on = await crawler.arun(
            url=local_server + "/shadow-dom",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )

    assert result_off.success and result_on.success, "Both crawls should succeed"
    html_off = result_off.html or ""
    html_on = result_on.html or ""

    assert len(html_on) >= len(html_off) * 0.9, (
        f"Flattened HTML shouldn't be drastically shorter: "
        f"off={len(html_off)} on={len(html_on)}"
    )
    assert "Content Inside Open Shadow Root" in html_on, (
        "Shadow content should be in flattened output"
    )


# ---------------------------------------------------------------------------
# Regression — the original svelte.dev bug
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regression_svelte_like_page_no_content_loss(local_server):
    """The original bug: svelte-like pages (scoped CSS, no shadow DOM)
    lost content with flatten_shadow_dom=True. The fast-path fixes this."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        result = await crawler.arun(
            url=local_server + "/no-shadow",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )
        assert result.success, f"Crawl failed: {result.error_message}"
        html = result.html or ""

        assert "<ul" in html.lower(), "ul elements should be present"
        assert "<li>" in html.lower(), "li elements should be present"
        assert "<nav" in html.lower(), "nav elements should be present"

        li_count = len(re.findall(r'<li[>\s]', html))
        assert li_count >= 5, f"Should have at least 5 li elements, found {li_count}"


@pytest.mark.asyncio
async def test_regression_side_by_side_parity(local_server):
    """Side-by-side: flatten on vs off on svelte-like page should be nearly identical."""
    async with AsyncWebCrawler(
        config=BrowserConfig(headless=True, verbose=False)
    ) as crawler:
        r_off = await crawler.arun(
            url=local_server + "/no-shadow",
            config=CrawlerRunConfig(flatten_shadow_dom=False, verbose=False),
        )
        r_on = await crawler.arun(
            url=local_server + "/no-shadow",
            config=CrawlerRunConfig(flatten_shadow_dom=True, verbose=False),
        )

    html_off = r_off.html or ""
    html_on = r_on.html or ""

    # Check that all headings appear in both
    headings_off = set(re.findall(r'<h[1-4][^>]*>([^<]+)</h[1-4]>', html_off, re.I))
    headings_on = set(re.findall(r'<h[1-4][^>]*>([^<]+)</h[1-4]>', html_on, re.I))
    missing = headings_off - headings_on
    assert not missing, f"Headings missing from flatten output: {missing}"

    for text in ["Introduction", "Guide", "API Reference", "Examples", "FAQ"]:
        assert text in html_on, f"'{text}' should be in flatten=True output"
