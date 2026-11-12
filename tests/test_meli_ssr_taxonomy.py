"""Mercado Libre storefront SSR parser: menu categories, no Clips, no guess."""
from app.mri_autonomous.meli_taxonomy_engine import (
    MeliTaxonomyEngine, NICOPOLY_VERIFIED_CATEGORIES_MLC)


def _html_with_categories():
    base = "https://listado.mercadolibre.cl/tienda/nicopoly/listado/vestuario-calzado/"
    links = [f'<a href="{base}{c["slug"]}/#component=category_gallery">x</a>'
             for c in NICOPOLY_VERIFIED_CATEGORIES_MLC]
    links.append('<a href="https://www.mercadolibre.cl/tienda/nicopoly/clips?page=0">Clips</a>')
    return "<html><body>" + "".join(links) + "</body></html>"


def test_parses_menu_and_excludes_clips():
    cats = MeliTaxonomyEngine.parse_storefront_categories(_html_with_categories())
    ids = {c["category_id"] for c in cats}
    assert len(cats) == 14
    assert "MLC158342" in ids and "MLC455550" in ids
    assert all("clips" not in c["url"].lower() for c in cats)


def test_does_not_invent_categories_from_empty_html():
    assert MeliTaxonomyEngine.parse_storefront_categories("") == []


def test_parses_rendered_polycard_dom():
    from app.mri_autonomous.meli_ssr_storefront import parse_storefront_dom_products
    html = (
      '<div class="poly-card"><div class="poly-card__content">'
      '<a class="poly-component__title" href="https://www.mercadolibre.cl/blusa/up/MLCU1?'
      'pdp_filters=item_id%3AMLC111#x">Blusa Nicopoly</a>'
      '<div class="poly-price__current"><span class="andes-money-amount__fraction">25990</span></div>'
      '</div></div>'
    )
    rows = parse_storefront_dom_products(html)
    assert len(rows) == 1
    assert rows[0]["marketplace_sku"] == "MLC111"
    assert rows[0]["user_product_id"] == "MLCU1"
    assert rows[0]["price"] == 25990.0
