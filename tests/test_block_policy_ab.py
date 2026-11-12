"""Fase A/B — sentinel rotativo, política de canal y G4."""
from app.mri_dashboard.block_policy import (
    assert_channel, classify_response, classify_scraper_failure, classify_sku,
    policy_for, reported_product_count, valid_sku)


def _page(title, marker):
    filler = "x" * (125 * 1024)
    return f"<html><head><title>{title}</title></head><body>{marker}{filler}</body></html>"


def test_iua_variant_is_blocked_with_rotating_signature():
    body = _page("Error en Ripley.com | IUA", 'cloudflarePage:"Im Under Attack"')
    d = classify_response(http_status=403, body=body,
                          headers={"server": "cloudflare"})
    assert d.classification == "BLOCKED"
    assert len(d.signals) >= 2


def test_captcha_box_variant_is_blocked():
    body = _page("Error en Ripley.com | Captcha Box",
                 'cloudflarePage:"Captcha Box"')
    d = classify_response(http_status=403, body=body,
                          headers={"server": "cloudflare"})
    assert d.classification == "BLOCKED"
    assert len(d.signals) >= 2


def test_real_small_page_is_not_blocked():
    d = classify_response(http_status=200, body="<html><title>Pantalones</title>"
                                               "<section data-testid='product-list'></section></html>",
                          headers={"server": "nginx"})
    assert d.classification == "REAL"


def test_closed_browser_and_blocked_scraper_failures():
    assert classify_scraper_failure({
        "failure_type": "TargetClosedError: Browser.new_context: Target page, "
                        "context or browser has been closed"}) == "BROWSER_CLOSED"
    assert classify_scraper_failure({
        "failure_type": "cloudflarePage: Captcha Box"}) == "BLOCKED"
    assert classify_scraper_failure({"stop_reason": "BLOCKED"}) == "BLOCKED"


def test_channel_policy_is_enforced():
    assert policy_for("Ripley")["allowed_channels"] == ("browser",)
    try:
        assert_channel("Ripley", "http")
        raise AssertionError("HTTP en Ripley debía rechazarse")
    except ValueError as exc:
        assert "CHANNEL_NOT_ALLOWED" in str(exc)
    assert_channel("Ripley", "browser")
    # Paris baseline no se toca: su política no prohíbe canales.
    assert policy_for("Paris")["forbidden"] == ()


def test_valid_sku_regex():
    assert valid_sku("MPM10003569411")
    assert not valid_sku("MPM123")
    assert not valid_sku("mpm10003569411".upper() + "X")


def test_g4_accepts_numeric_ripley_ids_and_rejects_bad_mpm():
    assert classify_sku("156819795") == "VALID"
    assert classify_sku("MPM10003569411") == "VALID"
    assert classify_sku("MPM123") == "INVALID_MPM"
    assert classify_sku("") == "EMPTY"


def test_g3_never_uses_pagination_total_declared_as_products():
    # Ripley pager total_declared = PAGES, not products.
    assert reported_product_count({"total_declared": 6}) is None
    assert reported_product_count({"total_products": 265}) == 265
    assert reported_product_count({"reported_products": "212"}) == 212
    assert reported_product_count(None) is None
