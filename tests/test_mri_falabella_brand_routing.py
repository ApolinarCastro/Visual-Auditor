import asyncio
import json
import pytest
from pathlib import Path

FIXTURE_HTML = """
<!DOCTYPE html>
<html>
  <head><title>falabella.com</title></head>
  <body>
    <div id="testId-ProductLandingContainer"></div>
    <script id="__NEXT_DATA__" type="application/json">
    {
      "props": {
        "pageProps": {
          "facets": [
            {
              "name": "Tipo",
              "id": "Tipo",
              "values": [
                {
                  "name": "Pantalones",
                  "count": 208,
                  "url": "f.product.attribute.Tipo=Pantalones"
                },
                {
                  "name": "Blazers",
                  "count": 155,
                  "url": "f.product.attribute.Tipo=Blazers"
                }
              ]
            },
            {
              "name": "Categoría",
              "id": "L0_category_paths",
              "values": [
                {
                  "name": "Mujer",
                  "count": 1106,
                  "url": "f.product.L0_category_paths=cat7330051%7C%7CMujer"
                }
              ]
            }
          ]
        }
      }
    }
    </script>
  </body>
</html>
"""

def test_fal_br_03_runtime_brand_control():
    """FAL-BR-03: Runtime brand controls search and validation without hardcoded literals."""
    from app.mri_autonomous.brand_hubs import brand_hub_for
    hub = brand_hub_for("Falabella", "AnyBrandXYZ")
    assert "anybrandxyz" in hub.canonical_reference.lower()
    assert "nicopoly" not in hub.canonical_reference.lower()

def test_fal_br_04_no_premature_brand_not_present():
    """FAL-BR-04: Route without brand evidence must not automatically declare BRAND_NOT_PRESENT."""
    from app.mri_autonomous.surface_classifier import certify_node
    # Unverified category node with 0 brand products observed
    cls = {"surface_type": "COMMERCIAL_CATEGORY", "confidence": 0.7, "evidence": ["category-facet-query-param"]}
    cert = certify_node(cls, products_observed=10, nicopoly_present=0)
    # Must not certify as verified brand node, but preserve honest unresolved/candidate state
    assert cert["certified"] is False

@pytest.mark.asyncio
async def test_fal_br_01_and_02_extract_commercial_category_from_ssr():
    """FAL-BR-01 & FAL-BR-02: Extract commercial category routes from Falabella SSR __NEXT_DATA__."""
    from playwright.async_api import async_playwright
    from app.mri_autonomous.category_discoverer import discover_categories_from_page, category_name_from_url

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.set_content(FIXTURE_HTML, wait_until="domcontentloaded")

    try:
        hub_url = "https://www.falabella.com/falabella-cl/search?Ntt=nicopoly"
        categories = await discover_categories_from_page(page, "Falabella", hub_url, brand="Nicopoly")
        
        # FAL-BR-01: Must extract at least one commercial category route
        assert len(categories) > 0, "No commercial categories extracted from Falabella SSR __NEXT_DATA__"
        
        # FAL-BR-02: Route must preserve provenance, category type, and category name
        pantalones_routes = [u for u in categories if "Pantalones" in u]
        assert len(pantalones_routes) > 0, f"Expected Pantalones category route in {categories}"
        
        cat_name = category_name_from_url(pantalones_routes[0], brand="Nicopoly")
        assert cat_name == "Pantalones", f"Expected category name 'Pantalones', got '{cat_name}'"
    finally:
        await browser.close()
        await pw.stop()

def test_fal_br_05_surface_classifier_commercial_category():
    """FAL-BR-05: Classify surface must recognize Falabella category facet query parameters as COMMERCIAL_CATEGORY."""
    from app.mri_autonomous.surface_classifier import classify_surface
    url = "https://www.falabella.com/falabella-cl/search?Ntt=nicopoly&f.product.attribute.Tipo=Pantalones"
    cls = classify_surface(url, {"brand": "Nicopoly"})
    assert cls["surface_type"] == "COMMERCIAL_CATEGORY", f"Expected COMMERCIAL_CATEGORY, got {cls['surface_type']}"
