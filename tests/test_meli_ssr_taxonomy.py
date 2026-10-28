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
