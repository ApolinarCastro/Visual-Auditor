"""Listing membership beats a brand-only PDP breadcrumb."""
from app.mri_dashboard.listing_category import (
    acquisition_url, category_from_listing_url, category_from_product_url)

URL = ("https://simple.ripley.cl/top-cuello-bote-espalda-drapeada-blanco-mujer-"
       "nicopoly-mpm10003579880?color_80=Blanco&s=mdco&pos=27&catPos=219&p=5"
       "&ps=48&cat=blusas_y_poleras&orig=PLP&prodNavFullCategory="
       "Moda%20Mujer%20%3E%20Tops%20y%20chaquetas%20%3E%20Blusas%20y%20poleras")


def test_listing_url_wins_over_brand_breadcrumb():
    out = category_from_product_url(URL)
    assert out["category"] == "Moda Mujer → Tops y chaquetas → Blusas y poleras"
    assert out["subcategory"] == "Blusas y poleras"
    assert out["source"] == "LISTING_MEMBERSHIP_URL"
    assert out["evidence"] == "prodNavFullCategory"


def test_cat_parameter_fallback():
    out = category_from_product_url("https://x/p?cat=jeans_y_pantalones")
    assert out["source"] == "LISTING_CAT_PARAM"
    assert "Jeans" in out["category"]


def test_missing_url_returns_none():
    assert category_from_product_url(None) is None
    assert category_from_product_url("https://x/p?foo=1") is None


def test_category_from_acquisition_surface():
    out = category_from_listing_url(
        "https://simple.ripley.cl/moda-mujer/tops-y-chaquetas/blusas-y-poleras?brand=NICOPOLY")
    assert "Blusas Y Poleras" in out["category"]
    assert out["source"] == "ACQUISITION_SURFACE"


def test_acquisition_url_removes_page_placeholder():
    raw = "https://simple.ripley.cl/moda-mujer/tops-y-chaquetas/abrigos?brand=NICOPOLY&page={page}"
    assert acquisition_url(raw) == "https://simple.ripley.cl/moda-mujer/tops-y-chaquetas/abrigos?brand=NICOPOLY"
    assert "{page}" not in acquisition_url(raw)
