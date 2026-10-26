"""Ripley verified acquisition rules (no network)."""
import asyncio
import uuid

from app.mri_dashboard.ripley_autonomous import (
    SourceBlocked, extract_cards, merge_categories, reconcile_category,
    scan_category, is_blocked, extract_category_links)


def _html(cards, extra=""):
    body = "".join(
        f'<article data-testid="product-item"><a href="/producto-x-mpm{sku}/p" '
        f'title="{name}"><span data-price="{price}"></span></a></article>'
        for sku, name, price in cards)
    return (f'<html><body><section data-testid="product-list">{body}</section>'
            f'{extra}</body></html>')


def test_extract_only_product_list_not_carousels():
    extra = ('<div class="carousel"><a href="/producto-y-mpm99999999999/p" '
             'title="Recomendado">x</a></div>')
    cards = extract_cards(_html([("10003569411", "Blazer Blanco", 39990)], extra))
    assert [c.sku for c in cards] == ["MPM10003569411"]
    assert cards[0].name == "Blazer Blanco"
    assert cards[0].price == 39990


def test_cloudflare_block_page_is_never_catalogue():
    blocked = '<html><title>Blocked</title><script>cloudflarePage:"Blocked"</script>'
    assert is_blocked(blocked) is True
    try:
        extract_cards(blocked)
        raise AssertionError("debía lanzar SourceBlocked")
    except SourceBlocked:
        pass


def test_n_n_memberships_and_duplicates():
    a = extract_cards(_html([("10000000001", "Gilet", 1)]))
    b = extract_cards(_html([("10000000001", "Gilet", 1), ("10000000002", "Polera", 2)]))
    merged = merge_categories({"Blusas": a, "Chaquetas": b})
    assert merged["unique_products"] == 2
    assert merged["duplicates"]["MPM10000000001"] == ["Blusas", "Chaquetas"]


def test_reconcile_tolerance_and_mismatch():
    assert reconcile_category("Jeans", 78, 78)["status"] == "COMPLETE"
    assert reconcile_category("Jeans", 78, 77)["status"] == "COMPLETE"
    assert reconcile_category("Jeans", 78, 40)["status"] == "PARTIAL_OR_BLOCKED"
    assert reconcile_category("Jeans", None, 40)["status"] == "UNVERIFIED"


def test_transient_empty_page_retries_before_stop():
    calls = {"n": 0}
    async def fake_fetch(url):
        calls["n"] += 1
        if calls["n"] == 1:
            return "<html><body><section data-testid='product-list'></section></body></html>"
        return _html([("10000000003", "Vestido", 1)])

    async def no_sleep(_):
        return None

    res = asyncio.run(scan_category(fake_fetch, "https://x?page={page}", "Vestidos",
                                    empty_retries=1, sleep=no_sleep))
    assert res.cards and res.cards[0].sku == "MPM10000000003"
    assert res.empty_retries == 1


def test_category_links_discovery():
    html = ('<a href="/moda-mujer/tops-y-chaquetas/blusas-y-poleras">B</a>'
            '<a href="https://simple.ripley.cl/moda-mujer/jeans-y-pantalones">J</a>'
            '<a href="/carrito">no</a>')
    links = extract_category_links(html)
    assert any("blusas-y-poleras" in x for x in links)
    assert any("jeans-y-pantalones" in x for x in links)
    assert all("carrito" not in x for x in links)
