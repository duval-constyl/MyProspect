"""Screenshots of a prospect's home page for the audit report (V3 plan, Task 4).

`capture_site` never raises: any failure (malformed URL, timeout, site down,
browser missing) gives `None` for the image concerned.
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.analysis.site import _candidate_urls

SETTLE_MS = 3000
DESKTOP = {"viewport": {"width": 1280, "height": 800}}
MOBILE = {
    "viewport": {"width": 390, "height": 844},
    "is_mobile": True,
    "has_touch": True,
    "device_scale_factor": 2,
    "user_agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    ),
}


@dataclass(frozen=True)
class Screenshots:
    desktop_png: bytes | None
    mobile_png: bytes | None


@asynccontextmanager
async def _chromium():
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            yield browser
        finally:
            await browser.close()


async def capture_site(url: str, timeout_s: float = 15, browser_factory=None) -> Screenshots:
    candidates = _candidate_urls(url)
    if not candidates:
        return Screenshots(None, None)
    target = candidates[0]
    try:
        # Per-page timeouts, plus an overall guard in case a page ignores them.
        async with asyncio.timeout(timeout_s * 3):
            async with (browser_factory or _chromium)() as browser:
                desktop = await _shot(browser, target, timeout_s, DESKTOP)
                mobile = await _shot(browser, target, timeout_s, MOBILE)
                return Screenshots(desktop, mobile)
    except Exception:  # noqa: BLE001 - a missing screenshot must never break the report
        return Screenshots(None, None)


async def _shot(browser, url: str, timeout_s: float, options: dict) -> bytes | None:
    page = None
    try:
        page = await browser.new_page(**options)
        await page.goto(url, timeout=timeout_s * 1000, wait_until="load")
        try:
            # Let fade-ins and background images finish; a page that never goes quiet is shot anyway.
            await page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
        except Exception:  # noqa: BLE001
            pass
        return await page.screenshot(type="png")
    except Exception:  # noqa: BLE001
        return None
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:  # noqa: BLE001
                pass
