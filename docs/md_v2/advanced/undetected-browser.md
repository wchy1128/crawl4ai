# Undetected Browser Mode

## Overview

Crawl4AI offers two powerful anti-bot features to help you access websites with bot detection:

1. **Stealth Mode** - Uses playwright-stealth to modify browser fingerprints and behaviors
2. **Undetected Browser Mode** - Advanced browser adapter with deep-level patches for sophisticated bot detection

This guide covers both features and helps you choose the right approach for your needs.

## Anti-Bot Features Comparison

| Feature | Regular Browser | Stealth Mode | Undetected Browser |
|---------|----------------|--------------|-------------------|
| WebDriver Detection | ❌ | ✅ | ✅ |
| Navigator Properties | ❌ | ✅ | ✅ |
| Plugin Emulation | ❌ | ✅ | ✅ |
| CDP Detection | ❌ | Partial | ✅ |
| Deep Browser Patches | ❌ | ❌ | ✅ |
| Performance Impact | None | Minimal | Moderate |
| Setup Complexity | None | None | Minimal |

## When to Use Each Approach

### Use Regular Browser + Stealth Mode When:
- Sites have basic bot detection (checking navigator.webdriver, plugins, etc.)
- You need good performance with basic protection
- Sites check for common automation indicators

### Use Undetected Browser When:
- Sites employ sophisticated bot detection services (Cloudflare, DataDome, etc.)
- Stealth mode alone isn't sufficient
- You're willing to trade some performance for better evasion

### Best Practice: Progressive Enhancement
1. **Start with**: Playwright + Stealth mode (`enable_stealth=True` + behavioral config)
2. **If blocked**: Switch to Undetected browser (Patchright) for binary-level evasion
3. **If still blocked**: Add proxy rotation / session management via `CrawlerRunConfig`

## Stealth Mode

Stealth mode is the simpler anti-bot solution that works with both regular and undetected browsers:

```python
from crawl4ai import AsyncWebCrawler, BrowserConfig

# Enable stealth mode with regular browser
browser_config = BrowserConfig(
    enable_stealth=True,  # Simple flag to enable
    headless=False       # Better for avoiding detection
)

async with AsyncWebCrawler(config=browser_config) as crawler:
    result = await crawler.arun("https://example.com")
```

### What Stealth Mode Does:
- Removes `navigator.webdriver` flag
- Modifies browser fingerprints
- Emulates realistic plugin behavior
- Adjusts navigator properties
- Fixes common automation leaks

## Undetected Browser Mode

For sites with sophisticated bot detection that stealth mode can't bypass, use the undetected browser adapter:

### Key Features

- **Drop-in Replacement**: Uses the same API as regular browser mode
- **Enhanced Stealth**: Built-in patches to evade common detection methods
- **Browser Adapter Pattern**: Seamlessly switch between regular and undetected modes
- **Automatic Installation**: `crawl4ai-setup` installs all necessary browser dependencies

### Quick Start

```python
import asyncio
from crawl4ai import (
    AsyncWebCrawler, 
    BrowserConfig, 
    CrawlerRunConfig,
    UndetectedAdapter
)
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy

async def main():
    # Create the undetected adapter
    undetected_adapter = UndetectedAdapter()
    
    # Create browser config
    browser_config = BrowserConfig(
        headless=False,  # Headless mode can be detected easier
        verbose=True,
    )
    
    # Create the crawler strategy with undetected adapter
    crawler_strategy = AsyncPlaywrightCrawlerStrategy(
        browser_config=browser_config,
        browser_adapter=undetected_adapter
    )
    
    # Create the crawler with our custom strategy
    async with AsyncWebCrawler(
        crawler_strategy=crawler_strategy,
        config=browser_config
    ) as crawler:
        # Your crawling code here
        result = await crawler.arun(
            url="https://example.com",
            config=CrawlerRunConfig()
        )
        print(result.markdown[:500])

asyncio.run(main())
```

## Combining Both Features

**`enable_stealth` and `UndetectedAdapter` are mutually exclusive** and cannot be
combined.  `playwright_stealth` injects evasion scripts via `add_init_script()`,
which triggers a Patchright driver-layer bug that breaks DNS (see below).
BrowserManager automatically skips StealthAdapter when `use_undetected=True`.

For a JS-level stealth + behavioral evasion combo that works with pure Playwright
(no Patchright dependency), use:

```python
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

browser_config = BrowserConfig(
    enable_stealth=True,   # playwright_stealth: JS-layer navigator/WebGL/plugin evasions
    headless=True,
)

crawl_config = CrawlerRunConfig(
    simulate_user=True,         # mouse movements, human-like behavior
    flatten_shadow_dom=True,    # open closed shadow roots
    magic=True,                 # auto-dismiss overlays / consent popups
    override_navigator=True,    # additional navigator property overrides
)

async with AsyncWebCrawler(config=browser_config) as crawler:
    result = await crawler.arun("https://example.com", config=crawl_config)
```

## Patchright DNS Limitation — Important

Patchright's driver layer has a bug: **any** call to `add_init_script()`
(context-level or page-level) breaks DNS resolution, causing
`ERR_NAME_NOT_RESOLVED` (Chromium) or `NS_ERROR_UNKNOWN_HOST` (Firefox) on
subsequent `page.goto()` calls.  This affects both Chromium and Firefox
engines equally.  Pure Playwright does NOT have this issue.

### Affected Config Parameters

When using `UndetectedAdapter` (Patchright), the following `CrawlerRunConfig`
params would normally trigger `add_init_script()` — they are automatically
adapted to work without it:

| Parameter | Default behavior | Patchright behavior |
|-----------|-----------------|-------------------|
| `override_navigator=True` | `context.add_init_script("navigator_overrider")` | Skipped — Patchright binary patches already handle navigator evasion |
| `simulate_user=True` | triggers navigator_overrider injection | Skipped (same reason) |
| `magic=True` | triggers navigator_overrider injection | Skipped (same reason) |
| `flatten_shadow_dom=True` | `context.add_init_script(attachShadow override)` | attachShadow patched via `page.evaluate()` after `goto()` completes (best-effort) |
| `BrowserConfig.init_scripts` | user-provided init scripts injected | Skipped with warning log |
| `capture_console_messages=True` | `page.add_init_script()` for console hook | Uses `page.on("console")` / `page.on("pageerror")` event listeners instead |

### Technical Details

The bug is in Patchright's driver layer implementation of CDP
`Page.addScriptToEvaluateOnNewDocument`.  When the script-hook is registered
before the network stack fully initializes, the DNS resolution module fails to
start, making every subsequent navigation fail with a host-not-found error.

Our fix:
1. **Skip `add_init_script()` entirely** under Patchright for navigator
   overrides, shadow DOM patches, and user init_scripts.
2. **Use `page.evaluate()`** to patch `attachShadow` after page load
   (best-effort — shadow roots created before this point remain closed).
3. **Use event listeners** (`page.on("console")`, `page.on("pageerror")`)
   instead of JS injection for console message capture.
4. **Log a warning** when user-provided `init_scripts` are skipped.

### Recommended Configurations

**For sites with advanced anti-bot (Cloudflare, DataDome):**
```python
browser_config = BrowserConfig(headless=True)
adapter = UndetectedAdapter()
# enable_stealth should NOT be set — Patchright handles binary-level evasion

crawl_config = CrawlerRunConfig(
    magic=True,                  # auto-dismiss popups
    simulate_user=True,          # human-like behavior
    flatten_shadow_dom=True,     # shadow DOM expansion (post-goto evaluate)
    # override_navigator is NOT needed — Patchright handles it at binary level
)
```

**For sites with basic anti-bot (most sites):**
```python
browser_config = BrowserConfig(
    enable_stealth=True,   # playwright_stealth JS evasions
    headless=True,
)
# No UndetectedAdapter needed — pure Playwright works fine

crawl_config = CrawlerRunConfig(
    magic=True,
    simulate_user=True,
    flatten_shadow_dom=True,
    override_navigator=True,  # Safe under Playwright (add_init_script works)
)
```

## Examples

### Example 1: Basic Stealth Mode

```python
import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

async def test_stealth_mode():
    # Simple stealth mode configuration
    browser_config = BrowserConfig(
        enable_stealth=True,
        headless=False
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url="https://bot.sannysoft.com",
            config=CrawlerRunConfig(screenshot=True)
        )
        
        if result.success:
            print("✓ Successfully accessed bot detection test site")
            # Save screenshot to verify detection results
            if result.screenshot:
                import base64
                with open("stealth_test.png", "wb") as f:
                    f.write(base64.b64decode(result.screenshot))
                print("✓ Screenshot saved - check for green (passed) tests")

asyncio.run(test_stealth_mode())
```

### Example 2: Undetected Browser Mode

```python
import asyncio
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    UndetectedAdapter
)
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy


async def main():
    # Create browser config
    browser_config = BrowserConfig(
        headless=False,
        verbose=True,
    )
    
    # Create the undetected adapter
    undetected_adapter = UndetectedAdapter()
    
    # Create the crawler strategy with the undetected adapter
    crawler_strategy = AsyncPlaywrightCrawlerStrategy(
        browser_config=browser_config,
        browser_adapter=undetected_adapter
    )
    
    # Create the crawler with our custom strategy
    async with AsyncWebCrawler(
        crawler_strategy=crawler_strategy,
        config=browser_config
    ) as crawler:
        # Configure the crawl
        crawler_config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter()
            ),
            capture_console_messages=True,  # Test adapter console capture
        )
        
        # Test on a site that typically detects bots
        print("Testing undetected adapter...")
        result: CrawlResult = await crawler.arun(
            url="https://www.helloworld.org", 
            config=crawler_config
        )
        
        print(f"Status: {result.status_code}")
        print(f"Success: {result.success}")
        print(f"Console messages captured: {len(result.console_messages or [])}")
        print(f"Markdown content (first 500 chars):\n{result.markdown.raw_markdown[:500]}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Browser Adapter Pattern

The undetected browser support is implemented using an adapter pattern, allowing seamless switching between different browser implementations:

```python
# Regular browser adapter (default)
from crawl4ai import PlaywrightAdapter
regular_adapter = PlaywrightAdapter()

# Undetected browser adapter
from crawl4ai import UndetectedAdapter
undetected_adapter = UndetectedAdapter()
```

The adapter handles:
- JavaScript execution
- Console message capture
- Error handling
- Browser-specific optimizations

## Best Practices

1. **Avoid Headless Mode**: Detection is easier in headless mode
   ```python
   browser_config = BrowserConfig(headless=False)
   ```

2. **Use Reasonable Delays**: Don't rush through pages
   ```python
   crawler_config = CrawlerRunConfig(
       wait_time=3.0,  # Wait 3 seconds after page load
       delay_before_return_html=2.0  # Additional delay
   )
   ```

3. **Rotate User Agents**: You can customize user agents
   ```python
   browser_config = BrowserConfig(
       headers={"User-Agent": "your-user-agent"}
   )
   ```

4. **Handle Failures Gracefully**: Some sites may still detect and block
   ```python
   if not result.success:
       print(f"Crawl failed: {result.error_message}")
   ```

## Advanced Usage Tips

### Progressive Detection Handling

```python
async def crawl_with_progressive_evasion(url):
    # Step 1: Try regular browser with stealth
    browser_config = BrowserConfig(
        enable_stealth=True,
        headless=False
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url)
        if result.success and "Access Denied" not in result.html:
            return result
    
    # Step 2: If blocked, try undetected browser
    print("Regular + stealth blocked, trying undetected browser...")
    
    adapter = UndetectedAdapter()
    strategy = AsyncPlaywrightCrawlerStrategy(
        browser_config=browser_config,
        browser_adapter=adapter
    )
    
    async with AsyncWebCrawler(
        crawler_strategy=strategy,
        config=browser_config
    ) as crawler:
        result = await crawler.arun(url)
        return result
```

## Installation

The undetected browser dependencies are automatically installed when you run:

```bash
crawl4ai-setup
```

This command installs all necessary browser dependencies for both regular and undetected modes.

## Limitations

- **Patchright + add_init_script**: Cannot use `add_init_script()`
  under Patchright due to driver-layer DNS bug.  Affected params
  (`flatten_shadow_dom`, `override_navigator`, `init_scripts`) are
  automatically adapted.  See "Patchright DNS Limitation" above.
- **StealthAdapter previously broken**: Before the 2026-05 fix,
  `enable_stealth=True` was silently non-functional — `StealthAdapter`
  imported non-existent function names.  Now fixed to use the correct
  `playwright_stealth.Stealth` class API.
- **Performance**: Slightly slower than regular mode due to additional patches
- **Headless Detection**: Some sites can still detect headless mode
- **Resource Usage**: May use more resources than regular mode
- **Not 100% Guaranteed**: Advanced anti-bot services are constantly evolving

## Troubleshooting

### Browser Not Found

Run the setup command:
```bash
crawl4ai-setup
```

### Detection Still Occurring

Try combining with other features:
```python
crawler_config = CrawlerRunConfig(
    simulate_user=True,  # Add user simulation
    magic=True,  # Enable magic mode
    wait_time=5.0,  # Longer waits
)
```

### Performance Issues

If experiencing slow performance:
```python
# Use selective undetected mode only for protected sites
if is_protected_site(url):
    adapter = UndetectedAdapter()
else:
    adapter = PlaywrightAdapter()  # Default adapter
```

## Future Plans

**Note**: In future versions of Crawl4AI, we may enable stealth mode and undetected browser by default to provide better out-of-the-box success rates. For now, users should explicitly enable these features when needed.

## Conclusion

Crawl4AI provides flexible anti-bot solutions:

1. **Start Simple**: Use regular browser + stealth mode for most sites
2. **Escalate if Needed**: Switch to undetected browser for sophisticated protection
3. **Combine for Maximum Effect**: Use both features together when facing the toughest challenges

Remember:
- Always respect robots.txt and website terms of service
- Use appropriate delays to avoid overwhelming servers
- Consider the performance trade-offs of each approach
- Test progressively to find the minimum necessary evasion level

## See Also

- [Advanced Features](advanced-features.md) - Overview of all advanced features
- [Proxy & Security](proxy-security.md) - Using proxies with anti-bot features
- [Session Management](session-management.md) - Maintaining sessions across requests
- [Identity Based Crawling](identity-based-crawling.md) - Additional anti-detection strategies
- [Anti-Bot Detection & Fallback](anti-bot-and-fallback.md) - Automatic retry and proxy escalation when blocking is detected