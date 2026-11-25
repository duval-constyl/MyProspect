"""Website analysis: reachability, HTTPS, basic SEO tags, viewport, technology
(with its version when readable), booking and online-order links.

`analyze_site` never raises: anything that prevents reading an HTML page
(malformed URL, timeout, too many redirects, error status, non-HTML content)
gives `reachable=False`.
"""

import asyncio
import re
import time
import unicodedata
from datetime import UTC, datetime

import httpx
from selectolax.lexbor import LexborHTMLParser

from app.domain import SiteAnalysis
from app.http import new_http_client

TIMEOUT_S = 10.0
MAX_REDIRECTS = 5
MAX_HTML_BYTES = 2_000_000
USER_AGENT = "Mozilla/5.0 (compatible; MyProspect/0.1; analyse de site)"
HTML_TYPES = ("text/html", "application/xhtml+xml")
TECH_ORDER = ("wordpress", "wix", "shopify", "jquery")
TECH_IN_GENERATOR = {"wordpress": "wordpress", "wix": "wix", "shopify": "shopify"}
TECH_IN_ASSETS = {
    "wordpress": ("/wp-content/", "/wp-includes/"),
    "wix": ("wixstatic.com", "parastorage.com", "wix.com"),
    "shopify": ("cdn.shopify.com", "shopify"),
    "jquery": ("jquery",),
}
WORDPRESS_VERSION = re.compile(r"wordpress\s+(\d+(?:\.\d+)*)")
JQUERY_VERSIONS = (
    re.compile(r"jquery[-.]?(\d+\.\d+(?:\.\d+)?)(?:\.slim)?(?:\.min)?\.js"),  # jquery-1.12.4.min.js
    re.compile(r"jquery/(\d+\.\d+(?:\.\d+)?)/"),  # cdnjs: /jquery/3.6.0/jquery.min.js
    re.compile(r"jquery[^/?]*\.js\?ver=(\d+\.\d+(?:\.\d+)?)"),  # WordPress: jquery.min.js?ver=3.7.1
)

# Booking and ordering providers seen in links or iframes (V2 plan, Task 1).
BOOKING_PROVIDERS = ("planity", "calendly", "zenchef", "thefork", "lafourchette", "doctolib", "resalib")
ORDER_PROVIDERS = ("ubereats", "deliveroo", "foodles")
# Words searched in a link's text or URL only; ordinary paragraphs never count.
BOOKING_WORDS = re.compile(r"\b(reserver|prendre (un )?rendez vous)\b")
ORDER_WORDS = re.compile(r"\bcommander\b")


def new_site_client() -> httpx.AsyncClient:
    """HTTP client with the redirect limit and timeout expected by analyze_site."""
    return new_http_client(
        timeout=TIMEOUT_S,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        headers={"User-Agent": USER_AGENT},
    )


async def analyze_site(url: str, client: httpx.AsyncClient | None = None) -> SiteAnalysis:
    analyzed_at = datetime.now(UTC)
    candidates = _candidate_urls(url)
    if not candidates:
        return _unreachable(url.strip(), analyzed_at)

    own_client = client is None
    http = client or new_site_client()
    try:
        for index, candidate in enumerate(candidates):
            is_last = index == len(candidates) - 1
            try:
                async with asyncio.timeout(TIMEOUT_S):
                    return await _analyze(http, candidate, analyzed_at)
            except (httpx.TransportError, TimeoutError):
                # No scheme given and HTTPS failed: the site may only speak HTTP.
                if is_last:
                    return _unreachable(candidate, analyzed_at)
            except Exception:  # noqa: BLE001 - an analysis must never break a collection
                return _unreachable(candidate, analyzed_at)
        return _unreachable(candidates[-1], analyzed_at)
    finally:
        if own_client:
            await http.aclose()


def _candidate_urls(raw: str) -> list[str]:
    """Normalized URLs to try, in order; [] if the URL is malformed."""
    value = (raw or "").strip()
    if not value or re.search(r"\s", value):
        return []
    has_scheme = "://" in value
    candidates = [value] if has_scheme else [f"https://{value}", f"http://{value}"]
    valid = []
    for candidate in candidates:
        try:
            parsed = httpx.URL(candidate)
        except (httpx.InvalidURL, ValueError, TypeError):
            continue
        if parsed.scheme in ("http", "https") and "." in parsed.host:
            valid.append(str(parsed.copy_with(path=parsed.path or "/")))
    return valid


async def _analyze(http: httpx.AsyncClient, url: str, analyzed_at: datetime) -> SiteAnalysis:
    started = time.perf_counter()
    async with http.stream("GET", url) as response:
        response_ms = int((time.perf_counter() - started) * 1000)
        final_url = str(response.url)
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if response.status_code >= 400 or content_type not in HTML_TYPES:
            return _unreachable(final_url, analyzed_at)
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) >= MAX_HTML_BYTES:
                break
        html = body.decode(response.encoding or "utf-8", errors="replace")

    tree = LexborHTMLParser(html)
    meta = _meta_by_name(tree)
    booking, order = _booking_signals(tree)
    return SiteAnalysis(
        url=final_url,
        reachable=True,
        https=response.url.scheme == "https",
        has_title=_has_text(tree, "title"),
        has_description=bool(meta.get("description")),
        has_h1=_has_text(tree, "h1"),
        has_viewport=bool(meta.get("viewport")),
        response_ms=response_ms,
        tech=_detect_tech(tree, meta.get("generator", "")),
        mobile_perf=None,
        analyzed_at=analyzed_at,
        has_booking=booking,
        has_online_order=order,
    )


def _unreachable(url: str, analyzed_at: datetime) -> SiteAnalysis:
    return SiteAnalysis(
        url=url,
        reachable=False,
        https=False,
        has_title=False,
        has_description=False,
        has_h1=False,
        has_viewport=False,
        response_ms=None,
        tech=[],
        mobile_perf=None,
        analyzed_at=analyzed_at,
    )


def _meta_by_name(tree: LexborHTMLParser) -> dict[str, str]:
    meta = {}
    for node in tree.css("meta"):
        name = (node.attributes.get("name") or "").strip().lower()
        content = (node.attributes.get("content") or "").strip()
        if name and name not in meta:
            meta[name] = content
    return meta


def _has_text(tree: LexborHTMLParser, tag: str) -> bool:
    return any(node.text(strip=True) for node in tree.css(tag))


def _detect_tech(tree: LexborHTMLParser, generator: str) -> list[str]:
    """Technologies as "name@version" when the version is readable, else "name"."""
    generator = generator.lower()
    found = {tech for tech, marker in TECH_IN_GENERATOR.items() if marker in generator}
    assets = [
        (node.attributes.get("src") or node.attributes.get("href") or "").lower()
        for node in tree.css("script, link")
    ]
    for tech, markers in TECH_IN_ASSETS.items():
        if any(marker in asset for asset in assets for marker in markers):
            found.add(tech)

    versions: dict[str, str] = {}
    if match := WORDPRESS_VERSION.search(generator):
        versions["wordpress"] = match.group(1)
    for asset in assets:
        for pattern in JQUERY_VERSIONS:
            if "jquery" not in versions and (match := pattern.search(asset)):
                versions["jquery"] = match.group(1)
    return [f"{tech}@{versions[tech]}" if tech in versions else tech for tech in TECH_ORDER if tech in found]


def detect_booking_signals(html: str) -> tuple[bool, bool]:
    """(online booking, online ordering) links found in the page."""
    if not html:
        return False, False
    try:
        return _booking_signals(LexborHTMLParser(html))
    except Exception:  # noqa: BLE001 - a broken page simply has no signal
        return False, False


def _booking_signals(tree: LexborHTMLParser) -> tuple[bool, bool]:
    booking = order = False
    for node in tree.css("a, iframe"):
        url = (node.attributes.get("href") or node.attributes.get("src") or "").lower()
        text = node.text(strip=True) if node.tag == "a" else ""
        words = f"{_plain(text)} {_plain(url)}"
        booking = booking or any(p in url for p in BOOKING_PROVIDERS) or bool(BOOKING_WORDS.search(words))
        order = order or any(p in url for p in ORDER_PROVIDERS) or bool(ORDER_WORDS.search(words))
    return booking, order


def _plain(text: str) -> str:
    """Lowercase, no accents, separators (- _ / . ? = &) turned into spaces."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text).split())
