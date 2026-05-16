# browser_adapter.py
"""
Browser adapter for Crawl4AI to support both Playwright and undetected browsers
with minimal changes to existing codebase.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
import time
import json

# Import both, but use conditionally
try:
    from playwright.async_api import Page
except ImportError:
    Page = Any

try:
    from patchright.async_api import Page as UndetectedPage
except ImportError:
    UndetectedPage = Any


class BrowserAdapter(ABC):
    """Abstract adapter for browser-specific operations"""
    
    @abstractmethod
    async def evaluate(self, page: Page, expression: str, arg: Any = None) -> Any:
        """Execute JavaScript in the page"""
        pass
    
    @abstractmethod
    async def setup_console_capture(self, page: Page, captured_console: List[Dict]) -> Optional[Callable]:
        """Setup console message capturing, returns handler function if needed"""
        pass
    
    @abstractmethod
    async def setup_error_capture(self, page: Page, captured_console: List[Dict]) -> Optional[Callable]:
        """Setup error capturing, returns handler function if needed"""
        pass
    
    @abstractmethod
    async def retrieve_console_messages(self, page: Page) -> List[Dict]:
        """Retrieve captured console messages (for undetected browsers)"""
        pass
    
    @abstractmethod
    async def cleanup_console_capture(self, page: Page, handle_console: Optional[Callable], handle_error: Optional[Callable]):
        """Clean up console event listeners"""
        pass
    
    @abstractmethod
    def get_imports(self) -> tuple:
        """Get the appropriate imports for this adapter"""
        pass


class PlaywrightAdapter(BrowserAdapter):
    """Adapter for standard Playwright"""
    
    async def evaluate(self, page: Page, expression: str, arg: Any = None) -> Any:
        """Standard Playwright evaluate"""
        if arg is not None:
            return await page.evaluate(expression, arg)
        return await page.evaluate(expression)
    
    async def setup_console_capture(self, page: Page, captured_console: List[Dict]) -> Optional[Callable]:
        """Setup console capture using Playwright's event system"""
        def handle_console_capture(msg):
            try:
                message_type = "unknown"
                try:
                    message_type = msg.type
                except:
                    pass
                    
                message_text = "unknown"
                try:
                    message_text = msg.text
                except:
                    pass
                    
                entry = {
                    "type": message_type,
                    "text": message_text,
                    "timestamp": time.time()
                }
                
                captured_console.append(entry)
                
            except Exception as e:
                captured_console.append({
                    "type": "console_capture_error", 
                    "error": str(e), 
                    "timestamp": time.time()
                })
        
        page.on("console", handle_console_capture)
        return handle_console_capture
    
    async def setup_error_capture(self, page: Page, captured_console: List[Dict]) -> Optional[Callable]:
        """Setup error capture using Playwright's event system"""
        def handle_pageerror_capture(err):
            try:
                error_message = "Unknown error"
                try:
                    error_message = err.message
                except:
                    pass
                    
                error_stack = ""
                try:
                    error_stack = err.stack
                except:
                    pass
                    
                captured_console.append({
                    "type": "error",
                    "text": error_message,
                    "stack": error_stack,
                    "timestamp": time.time()
                })
            except Exception as e:
                captured_console.append({
                    "type": "pageerror_capture_error", 
                    "error": str(e), 
                    "timestamp": time.time()
                })
        
        page.on("pageerror", handle_pageerror_capture)
        return handle_pageerror_capture
    
    async def retrieve_console_messages(self, page: Page) -> List[Dict]:
        """Not needed for Playwright - messages are captured via events"""
        return []
    
    async def cleanup_console_capture(self, page: Page, handle_console: Optional[Callable], handle_error: Optional[Callable]):
        """Remove event listeners"""
        if handle_console:
            page.remove_listener("console", handle_console)
        if handle_error:
            page.remove_listener("pageerror", handle_error)
    
    def get_imports(self) -> tuple:
        """Return Playwright imports"""
        from playwright.async_api import Page, Error
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        return Page, Error, PlaywrightTimeoutError


class StealthAdapter(BrowserAdapter):
    """Adapter for Playwright with stealth features using playwright_stealth.

    Uses the Stealth class (the only public API).  The old code tried to
    import stealth_async / stealth_sync — those names never existed in any
    release of playwright_stealth, so enable_stealth was silently broken.

    Must NOT be combined with UndetectedAdapter / Patchright:
    playwright_stealth injects via context.add_init_script(), which triggers
    Patchright's driver-layer DNS bug.  BrowserManager enforces this mutual
    exclusion — _stealth_adapter is only created when use_undetected=False.
    """

    def __init__(self):
        self._console_script_injected = {}
        self._stealth = None
        self._stealth_available = self._check_stealth_availability()

    def _check_stealth_availability(self) -> bool:
        """Check if playwright_stealth is importable and instantiate the Stealth helper."""
        try:
            from playwright_stealth import Stealth
            self._stealth = Stealth()
            return True
        except ImportError:
            self._stealth = None
            return False

    async def apply_stealth(self, page: Page):
        """Inject playwright_stealth evasion scripts via add_init_script().

        Safe under pure Playwright.  Under Patchright add_init_script()
        breaks DNS; BrowserManager.__init__ already prevents this path
        (self._stealth_adapter is None when use_undetected=True).
        """
        if self._stealth_available and self._stealth:
            try:
                await self._stealth.apply_stealth_async(page)
            except Exception:
                pass

    async def evaluate(self, page: Page, expression: str, arg: Any = None) -> Any:
        """Standard Playwright evaluate with stealth applied"""
        if arg is not None:
            return await page.evaluate(expression, arg)
        return await page.evaluate(expression)

    async def setup_console_capture(self, page: Page, captured_console: List[Dict]) -> Optional[Callable]:
        """Setup console capture using Playwright's event system with stealth"""
        # Apply stealth to the page first
        await self.apply_stealth(page)

        def handle_console_capture(msg):
            try:
                message_type = "unknown"
                try:
                    message_type = msg.type
                except:
                    pass

                message_text = "unknown"
                try:
                    message_text = msg.text
                except:
                    pass

                entry = {
                    "type": message_type,
                    "text": message_text,
                    "timestamp": time.time()
                }

                captured_console.append(entry)

            except Exception as e:
                captured_console.append({
                    "type": "console_capture_error",
                    "error": str(e),
                    "timestamp": time.time()
                })

        page.on("console", handle_console_capture)
        return handle_console_capture

    async def setup_error_capture(self, page: Page, captured_console: List[Dict]) -> Optional[Callable]:
        """Setup error capture using Playwright's event system"""
        def handle_pageerror_capture(err):
            try:
                error_message = "Unknown error"
                try:
                    error_message = err.message
                except:
                    pass

                error_stack = ""
                try:
                    error_stack = err.stack
                except:
                    pass

                captured_console.append({
                    "type": "error",
                    "text": error_message,
                    "stack": error_stack,
                    "timestamp": time.time()
                })
            except Exception as e:
                captured_console.append({
                    "type": "pageerror_capture_error",
                    "error": str(e),
                    "timestamp": time.time()
                })

        page.on("pageerror", handle_pageerror_capture)
        return handle_pageerror_capture

    async def retrieve_console_messages(self, page: Page) -> List[Dict]:
        """Not needed for Playwright - messages are captured via events"""
        return []

    async def cleanup_console_capture(self, page: Page, handle_console: Optional[Callable], handle_error: Optional[Callable]):
        """Remove event listeners"""
        if handle_console:
            page.remove_listener("console", handle_console)
        if handle_error:
            page.remove_listener("pageerror", handle_error)

    def get_imports(self) -> tuple:
        """Return Playwright imports"""
        from playwright.async_api import Page, Error
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        return Page, Error, PlaywrightTimeoutError


class UndetectedAdapter(BrowserAdapter):
    """Adapter for Patchright (undetected Chromium / Firefox).

    CRITICAL: Patchright's driver layer has a bug where ANY add_init_script()
    call (context or page level) breaks DNS resolution, causing
    ERR_NAME_NOT_RESOLVED on subsequent page.goto().  Both Chromium and
    Firefox engine are affected.

    Therefore this adapter MUST NOT call add_init_script() anywhere.
    Console / error capture uses the standard Playwright event system
    (page.on("console") / page.on("pageerror")) instead of JS injection.
    """

    def __init__(self):
        pass

    async def evaluate(self, page: UndetectedPage, expression: str, arg: Any = None) -> Any:
        """Evaluate JS in the page.  Always uses isolated_context=True for
        stealth; the old non-isolated path existed only to reach
        window.__capturedConsole which is no longer used."""
        if arg is not None:
            return await page.evaluate(expression, arg, isolated_context=True)
        return await page.evaluate(expression, isolated_context=True)

    async def setup_console_capture(self, page: UndetectedPage, captured_console: List[Dict]) -> Optional[Callable]:
        """Setup console capture via event listener (NOT add_init_script).

        Patchright's driver-layer DNS bug makes add_init_script() unsafe,
        so we use the same Page.on("console") event mechanism as PlaywrightAdapter.
        """

        def handle_console_capture(msg):
            try:
                message_type = "unknown"
                try:
                    message_type = msg.type
                except Exception:
                    pass

                message_text = "unknown"
                try:
                    message_text = msg.text
                except Exception:
                    pass

                entry = {
                    "type": message_type,
                    "text": message_text,
                    "timestamp": time.time(),
                }
                captured_console.append(entry)
            except Exception as e:
                captured_console.append({
                    "type": "console_capture_error",
                    "error": str(e),
                    "timestamp": time.time(),
                })

        page.on("console", handle_console_capture)
        return handle_console_capture

    async def setup_error_capture(self, page: UndetectedPage, captured_console: List[Dict]) -> Optional[Callable]:
        """Setup error capture via event listener (NOT add_init_script).

        Same reason as setup_console_capture — avoids Patchright's DNS bug.
        """

        def handle_pageerror_capture(err):
            try:
                error_message = "Unknown error"
                try:
                    error_message = err.message
                except Exception:
                    pass

                error_stack = ""
                try:
                    error_stack = err.stack
                except Exception:
                    pass

                captured_console.append({
                    "type": "error",
                    "text": error_message,
                    "stack": error_stack,
                    "timestamp": time.time(),
                })
            except Exception as e:
                captured_console.append({
                    "type": "pageerror_capture_error",
                    "error": str(e),
                    "timestamp": time.time(),
                })

        page.on("pageerror", handle_pageerror_capture)
        return handle_pageerror_capture

    async def retrieve_console_messages(self, page: UndetectedPage) -> List[Dict]:
        """Messages are captured into captured_console list via events — no
        JS-side extraction needed."""
        return []

    async def cleanup_console_capture(self, page: UndetectedPage, handle_console: Optional[Callable], handle_error: Optional[Callable]):
        """Remove event listeners registered during setup."""
        if handle_console:
            page.remove_listener("console", handle_console)
        if handle_error:
            page.remove_listener("pageerror", handle_error)

    def get_imports(self) -> tuple:
        """Return Patchright imports"""
        from patchright.async_api import Page, Error
        from patchright.async_api import TimeoutError as PlaywrightTimeoutError
        return Page, Error, PlaywrightTimeoutError
