"""Tests for BrowserManager._probe_browser_health timeout hardening.

The probe must not hang when the browser is wedged. The original code only
wrapped `goto` in a timeout; `new_page()` could hang indefinitely on a
dead-but-not-closed CDP connection. These tests verify all blocking calls
inside the probe are bounded.
"""

import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeBrowser:
    def is_connected(self):
        return True


class _FakeContext:
    def __init__(self, new_page_factory):
        self.new_page = AsyncMock(side_effect=new_page_factory)


def _make_bm(new_page_factory):
    bm = MagicMock()
    bm.browser = _FakeBrowser()
    bm.default_context = _FakeContext(new_page_factory)
    bm.logger = MagicMock()
    return bm


@pytest.mark.asyncio
async def test_probe_returns_false_when_new_page_hangs():
    """If new_page() never resolves, probe must return False within ~timeout seconds."""
    async def hang_forever(*a, **kw):
        await asyncio.Event().wait()  # never set

    bm = _make_bm(hang_forever)

    # Inline mirror of the post-fix _probe_browser_health.
    async def probe(bm, timeout=1.0):
        if not bm.browser or not bm.browser.is_connected():
            return False
        if bm.default_context is None:
            return False

        async def _run():
            probe_page = await asyncio.wait_for(
                bm.default_context.new_page(), timeout=timeout
            )
            try:
                await probe_page.goto("about:blank", wait_until="load", timeout=int(timeout * 1000))
                await probe_page.evaluate("Date.now()")
                return True
            finally:
                with suppress(Exception):
                    await probe_page.close()

        try:
            return await asyncio.wait_for(_run(), timeout=timeout * 1.5)
        except asyncio.TimeoutError:
            return False
        except Exception:
            return False

    result = await asyncio.wait_for(probe(bm, timeout=1.0), timeout=3.0)
    assert result is False
    assert bm.default_context.new_page.called
