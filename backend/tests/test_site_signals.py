import httpx
import respx

from app.analysis.site import analyze_site, detect_booking_signals

HTML = {"Content-Type": "text/html; charset=utf-8"}


def page(body: str, head: str = "") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


def test_detects_planity_link_as_booking():
    html = page('<a href="https://www.planity.com/salon-eclat-69001-lyon">Prendre RDV</a>')

    assert detect_booking_signals(html) == (True, False)


def test_detects_booking_iframe_from_known_provider():
    html = page('<iframe src="https://widget.zenchef.com/frame?rid=123"></iframe>')

    assert detect_booking_signals(html) == (True, False)


def test_detects_order_link_text():
    html = page('<a href="/carte">Commander en ligne</a>')

    assert detect_booking_signals(html) == (False, True)


def test_detects_delivery_platform_as_order():
    html = page('<a href="https://deliveroo.fr/fr/menu/lyon/bouchon">Livraison</a>')

    assert detect_booking_signals(html) == (False, True)


def test_detects_booking_keyword_in_link_url_and_text():
    by_url = page('<a href="/prendre-rendez-vous">Nos horaires</a>')
    by_text = page('<a href="/contact">Réserver une table</a>')

    assert detect_booking_signals(by_url) == (True, False)
    assert detect_booking_signals(by_text) == (True, False)


def test_paragraph_mentioning_reservation_is_not_booking():
    html = page(
        "<p>Réservation conseillée le week-end. Vous pouvez réserver par téléphone"
        " ou commander sur place.</p>"
        '<a href="/mentions-legales">Mentions légales et conditions de réservation</a>'
    )

    assert detect_booking_signals(html) == (False, False)


def test_empty_or_broken_html_has_no_signal():
    assert detect_booking_signals("") == (False, False)
    assert detect_booking_signals("<a href=") == (False, False)


@respx.mock
async def test_reads_wordpress_version_from_generator_meta():
    respx.get("https://garage.fr/").mock(
        return_value=httpx.Response(
            200, headers=HTML, text=page("<h1>Garage</h1>", '<meta name="generator" content="WordPress 5.8">')
        )
    )

    analysis = await analyze_site("https://garage.fr/")

    assert analysis.tech == ["wordpress@5.8"]


@respx.mock
async def test_reads_jquery_version_from_script_src():
    respx.get("https://salon.fr/").mock(
        return_value=httpx.Response(
            200,
            headers=HTML,
            text=page("", '<script src="/assets/js/jquery-1.12.4.min.js"></script>'),
        )
    )
    respx.get("https://wp.fr/").mock(
        return_value=httpx.Response(
            200,
            headers=HTML,
            text=page("", '<script src="/wp-includes/js/jquery/jquery.min.js?ver=3.7.1"></script>'),
        )
    )

    assert (await analyze_site("https://salon.fr/")).tech == ["jquery@1.12.4"]
    assert (await analyze_site("https://wp.fr/")).tech == ["wordpress", "jquery@3.7.1"]


@respx.mock
async def test_existing_v1_fields_unchanged():
    respx.get("https://salon-eclat.fr/").mock(
        return_value=httpx.Response(
            200,
            headers=HTML,
            text=page(
                '<h1>Salon Éclat</h1><a href="https://www.planity.com/salon-eclat">Réserver</a>',
                '<title>Salon Éclat</title><meta name="description" content="Coiffeur">'
                '<meta name="viewport" content="width=device-width">',
            ),
        )
    )

    analysis = await analyze_site("https://salon-eclat.fr/")

    assert (analysis.reachable, analysis.https, analysis.has_title, analysis.has_description) == (
        True, True, True, True,
    )
    assert (analysis.has_h1, analysis.has_viewport, analysis.mobile_perf) == (True, True, None)
    assert (analysis.has_booking, analysis.has_online_order) == (True, False)


@respx.mock
async def test_unreachable_site_has_no_signal():
    respx.get("https://lent.fr/").mock(side_effect=httpx.ReadTimeout("trop long"))

    analysis = await analyze_site("https://lent.fr/")

    assert (analysis.has_booking, analysis.has_online_order) == (False, False)
