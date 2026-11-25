"""Mobile performance score from PageSpeed Insights (optional, needs an API key).

Endpoint checked on 2026-11-25: GET /pagespeedonline/v5/runPagespeed with url,
strategy=mobile, category=performance, key; the score is
lighthouseResult.categories.performance.score (0 to 1).
"""

import httpx

from app.http import new_http_client

PAGESPEED_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
TIMEOUT_S = 60.0  # Lighthouse runs take tens of seconds


async def mobile_perf(
    url: str, api_key: str | None, client: httpx.AsyncClient | None = None
) -> int | None:
    """Mobile performance 0-100, or None without key or on any error."""
    if not api_key:
        return None
    own_client = client is None
    http = client or new_http_client(timeout=TIMEOUT_S)
    try:
        response = await http.get(
            PAGESPEED_URL,
            params={"url": url, "strategy": "mobile", "category": "performance", "key": api_key},
        )
        if response.status_code != 200:
            return None
        score = response.json()["lighthouseResult"]["categories"]["performance"]["score"]
        if score is None:
            return None
        return max(0, min(100, round(float(score) * 100)))
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None
    finally:
        if own_client:
            await http.aclose()
