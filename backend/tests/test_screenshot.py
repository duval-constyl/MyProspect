import asyncio
import base64
from contextlib import asynccontextmanager

from app.analysis.screenshot import DESKTOP, MOBILE, Screenshots, capture_site
from app.domain import Offer
from app.report import render_audit_html
from app.routers.prospects import prospect_detail

PNG = b"\x89PNG\r\n\x1a\nfake-image"


class FakePage:
    def __init__(self, browser, options):
        self.browser, self.options = browser, options

    async def goto(self, url, timeout=None, wait_until=None):
        self.browser.visited.append((url, self.options["viewport"]["width"], timeout))
        if self.browser.behaviour == "timeout":
            raise TimeoutError("trop long")
        if self.browser.behaviour == "hang":
            await asyncio.sleep(3600)

    async def wait_for_load_state(self, state="load", timeout=None):
        self.browser.calls.append(("settle", state, timeout))
        if self.browser.behaviour == "never_idle":
            raise TimeoutError("le réseau ne se calme jamais")

    async def screenshot(self, type="png"):
        self.browser.calls.append(("screenshot",))
        return PNG + str(self.options["viewport"]["width"]).encode()

    async def close(self):
        self.browser.closed_pages += 1


class FakeBrowser:
    def __init__(self, behaviour="ok"):
        self.behaviour = behaviour
        self.visited = []
        self.calls = []
        self.closed_pages = 0

    async def new_page(self, **options):
        return FakePage(self, options)


def factory_for(browser):
    @asynccontextmanager
    async def factory():
        yield browser

    return factory


async def test_returns_both_images_on_success():
    browser = FakeBrowser()

    shots = await capture_site("salon-eclat.fr", browser_factory=factory_for(browser))

    assert shots.desktop_png == PNG + b"1280"
    assert shots.mobile_png == PNG + b"390"
    assert [(url, width) for url, width, _ in browser.visited] == [
        ("https://salon-eclat.fr/", 1280),
        ("https://salon-eclat.fr/", 390),
    ]
    assert browser.visited[0][2] == 15_000  # milliseconds
    assert browser.closed_pages == 2
    assert DESKTOP["viewport"] == {"width": 1280, "height": 800}
    assert MOBILE["viewport"] == {"width": 390, "height": 844} and MOBILE["is_mobile"] is True


async def test_waits_for_the_page_to_settle_before_capture():
    # Real run (2026-11-25): pages shot right after « load » were black (fade-in, background video).
    browser = FakeBrowser()

    await capture_site("https://salon.fr/", browser_factory=factory_for(browser))

    assert browser.calls[:2] == [("settle", "networkidle", 3000), ("screenshot",)]


async def test_page_that_never_settles_is_still_captured():
    shots = await capture_site("https://salon.fr/", browser_factory=factory_for(FakeBrowser("never_idle")))

    assert shots.desktop_png is not None and shots.mobile_png is not None


async def test_returns_none_images_on_timeout():
    shots = await capture_site("https://lent.fr/", browser_factory=factory_for(FakeBrowser("timeout")))

    assert shots == Screenshots(desktop_png=None, mobile_png=None)


async def test_hanging_site_is_cut_by_the_overall_timeout():
    shots = await capture_site("https://bloque.fr/", timeout_s=0.05, browser_factory=factory_for(FakeBrowser("hang")))

    assert shots == Screenshots(None, None)


async def test_malformed_url_returns_none_images():
    browser = FakeBrowser()

    shots = await capture_site("http//bad url", browser_factory=factory_for(browser))

    assert shots == Screenshots(None, None)
    assert browser.visited == []  # the browser is not even used


async def test_browser_that_cannot_start_returns_none_images():
    @asynccontextmanager
    async def broken():
        raise RuntimeError("Executable doesn't exist: chromium")
        yield  # pragma: no cover

    assert await capture_site("https://salon.fr/", browser_factory=broken) == Screenshots(None, None)


def test_report_shows_placeholder_text_when_screenshot_missing(add, db_session):
    prospect = add("11111111100011", "SALON ECLAT", score=75)
    detail = prospect_detail(prospect.id, db_session)

    html = render_audit_html(detail, Offer.WEB, screenshots=Screenshots(None, None))
    without = render_audit_html(detail, Offer.WEB)

    assert "Capture sur ordinateur indisponible" in html
    assert "Capture sur téléphone indisponible" in html
    assert "data:image/png" not in html
    assert "Capture sur ordinateur" not in without  # no section at all without screenshots


def test_report_embeds_images_as_data_uri_when_present(add, db_session):
    prospect = add("11111111100011", "SALON ECLAT", score=75)
    detail = prospect_detail(prospect.id, db_session)

    html = render_audit_html(detail, Offer.WEB, screenshots=Screenshots(PNG, None))

    assert f"data:image/png;base64,{base64.b64encode(PNG).decode()}" in html
    assert "Capture sur téléphone indisponible" in html


def test_audit_route_captures_the_analysed_site_when_enabled(client, add, db_session, monkeypatch):
    from datetime import UTC, datetime

    from app.models import SiteAnalysisRow
    from app.routers import exports

    prospect = add("11111111100011", "SALON ECLAT", score=20, website="https://salon-eclat.fr")
    db_session.add(SiteAnalysisRow(
        prospect_id=prospect.id, url="https://salon-eclat.fr/", reachable=True, https=False,
        has_title=True, has_description=True, has_h1=True, has_viewport=True, response_ms=200,
        tech=[], mobile_perf=None, analyzed_at=datetime(2026, 11, 25, tzinfo=UTC),
    ))
    db_session.commit()
    captured = []

    async def fake_capture(url, timeout_s=15, browser_factory=None):
        captured.append(url)
        return Screenshots(PNG, PNG)

    seen = {}

    def fake_pdf(detail, offer, screenshots=None):
        seen["screenshots"] = screenshots
        return b"%PDF-1.7 fake"

    monkeypatch.setattr(exports, "capture_site", fake_capture)
    monkeypatch.setattr(exports, "render_audit_pdf", fake_pdf)

    response = client.get(f"/prospects/{prospect.id}/audit.pdf")

    assert response.status_code == 200
    assert captured == ["https://salon-eclat.fr/"]
    assert seen["screenshots"] == Screenshots(PNG, PNG)

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "screenshots_enabled", False)
    client.get(f"/prospects/{prospect.id}/audit.pdf")
    assert captured == ["https://salon-eclat.fr/"]  # no new capture
    assert seen["screenshots"] is None
