import httpx
import respx

from app.analysis.site import analyze_site
from app.sources.pagespeed import PAGESPEED_URL, mobile_perf

GOOD_PAGE = """<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Garage Martin, réparation toutes marques à Lyon.">
  <meta name="generator" content="WordPress 6.6">
  <title>Garage Martin - Lyon</title>
  <script src="/wp-includes/js/jquery/jquery.min.js"></script>
</head>
<body><h1>Garage Martin</h1></body>
</html>"""

BARE_PAGE = "<html><head></head><body><p>Bienvenue</p></body></html>"

HTML = {"Content-Type": "text/html; charset=utf-8"}


@respx.mock
async def test_good_site_all_flags_true():
    respx.get("https://garage-martin.fr/").mock(
        return_value=httpx.Response(200, headers=HTML, text=GOOD_PAGE)
    )

    analysis = await analyze_site("garage-martin.fr")

    assert analysis.reachable is True
    assert analysis.https is True
    assert analysis.has_title is True
    assert analysis.has_description is True
    assert analysis.has_h1 is True
    assert analysis.has_viewport is True
    assert analysis.tech == ["wordpress@6.6", "jquery"]  # V2: version when readable
    assert analysis.response_ms is not None and analysis.response_ms >= 0
    assert analysis.mobile_perf is None
    assert analysis.url == "https://garage-martin.fr/"


@respx.mock
async def test_missing_title_description_h1_viewport_flags():
    respx.get("https://salon-eclat.fr/").mock(
        return_value=httpx.Response(200, headers=HTML, text=BARE_PAGE)
    )

    analysis = await analyze_site("https://salon-eclat.fr/")

    assert analysis.reachable is True
    assert analysis.has_title is False
    assert analysis.has_description is False
    assert analysis.has_h1 is False
    assert analysis.has_viewport is False
    assert analysis.tech == []


@respx.mock
async def test_empty_title_and_description_count_as_missing():
    respx.get("https://vide.fr/").mock(
        return_value=httpx.Response(
            200,
            headers=HTML,
            text='<html><head><title> </title><meta name="description" content=""></head>'
            "<body><h1></h1></body></html>",
        )
    )

    analysis = await analyze_site("https://vide.fr/")

    assert (analysis.has_title, analysis.has_description, analysis.has_h1) == (False, False, False)


@respx.mock
async def test_http_only_site_has_https_false():
    respx.get("http://plomberie-durand.fr/").mock(
        return_value=httpx.Response(200, headers=HTML, text=GOOD_PAGE)
    )

    analysis = await analyze_site("http://plomberie-durand.fr/")

    assert analysis.reachable is True
    assert analysis.https is False


@respx.mock
async def test_redirect_http_to_https_counts_as_https():
    respx.get("http://plomberie-durand.fr/").mock(
        return_value=httpx.Response(301, headers={"Location": "https://www.plomberie-durand.fr/"})
    )
    respx.get("https://www.plomberie-durand.fr/").mock(
        return_value=httpx.Response(200, headers=HTML, text=GOOD_PAGE)
    )

    analysis = await analyze_site("http://plomberie-durand.fr/")

    assert analysis.reachable is True
    assert analysis.https is True
    assert analysis.url == "https://www.plomberie-durand.fr/"


@respx.mock
async def test_no_scheme_falls_back_to_http_when_https_fails():
    respx.get("https://vieux-site.fr/").mock(side_effect=httpx.ConnectError("pas de TLS"))
    respx.get("http://vieux-site.fr/").mock(
        return_value=httpx.Response(200, headers=HTML, text=GOOD_PAGE)
    )

    analysis = await analyze_site("vieux-site.fr")

    assert analysis.reachable is True
    assert analysis.https is False


@respx.mock
async def test_too_many_redirects_returns_unreachable():
    respx.get("https://boucle.fr/").mock(
        return_value=httpx.Response(302, headers={"Location": "https://boucle.fr/"})
    )

    analysis = await analyze_site("https://boucle.fr/")

    assert analysis.reachable is False


async def test_malformed_url_returns_unreachable_not_exception():
    analysis = await analyze_site("http//bad url")

    assert analysis.reachable is False
    assert analysis.https is False
    assert analysis.tech == []


@respx.mock
async def test_timeout_returns_unreachable():
    respx.get("https://lent.fr/").mock(side_effect=httpx.ReadTimeout("trop long"))

    analysis = await analyze_site("https://lent.fr/")

    assert analysis.reachable is False
    assert analysis.response_ms is None


@respx.mock
async def test_pdf_response_is_unreachable():
    respx.get("https://catalogue.fr/").mock(
        return_value=httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=b"%PDF-1.7"
        )
    )

    analysis = await analyze_site("https://catalogue.fr/")

    assert analysis.reachable is False


@respx.mock
async def test_error_status_is_unreachable():
    respx.get("https://en-panne.fr/").mock(return_value=httpx.Response(500, headers=HTML, text=""))

    analysis = await analyze_site("https://en-panne.fr/")

    assert analysis.reachable is False


@respx.mock
async def test_detects_wix_and_shopify_from_scripts():
    respx.get("https://boutique.fr/").mock(
        return_value=httpx.Response(
            200,
            headers=HTML,
            text='<html><head><script src="https://static.parastorage.com/x.js"></script>'
            '<script src="https://cdn.shopify.com/s/files/app.js"></script></head></html>',
        )
    )

    analysis = await analyze_site("https://boutique.fr/")

    assert analysis.tech == ["wix", "shopify"]


async def test_mobile_perf_none_without_key():
    assert await mobile_perf("https://garage-martin.fr/", None) is None
    assert await mobile_perf("https://garage-martin.fr/", "") is None


@respx.mock
async def test_mobile_perf_reads_performance_score():
    route = respx.get(PAGESPEED_URL).mock(
        return_value=httpx.Response(
            200, json={"lighthouseResult": {"categories": {"performance": {"score": 0.42}}}}
        )
    )

    assert await mobile_perf("https://garage-martin.fr/", "cle-test") == 42
    params = route.calls[0].request.url.params
    assert params["url"] == "https://garage-martin.fr/"
    assert params["strategy"] == "mobile"
    assert params["category"] == "performance"
    assert params["key"] == "cle-test"


@respx.mock
async def test_mobile_perf_error_returns_none():
    respx.get(PAGESPEED_URL).mock(return_value=httpx.Response(429))

    assert await mobile_perf("https://garage-martin.fr/", "cle-test") is None
