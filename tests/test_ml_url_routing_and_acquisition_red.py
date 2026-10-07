import pytest
import re
from bs4 import BeautifulSoup
from app.scrapers.mercadolibre_scraper import MercadoLibreScraper

def test_ml_navigate_does_not_unconditionally_rewrite_store_url():
    """
    RED test:
    Prior code unconditionally rewrote 'tienda/nicopoly' to 'https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly'
    in navigate().
    This test asserts that clean_url preserves the official store URL and does not inject hardcoded fallback URLs.
    """
    test_brand = "TEST_RUNTIME_BRAND"
    scraper = MercadoLibreScraper(headless=True)
    
    # Check 1: Dynamic brand store URL must NOT be rewritten to hardcoded fallback
    store_url = f"https://www.mercadolibre.cl/tienda/{test_brand.lower()}"
    
    # We inspect the clean_url logic that navigate executes
    # In current production, line 75 rewrites 'tienda/nicopoly' hardcoded, and does nothing for TEST_RUNTIME_BRAND,
    # or rewrites nicopoly store URLs to the blocked fallback URL.
    # We test with both a generic brand and nicopoly to ensure neither is rewritten to the blocked fallback.
    url_to_test = "https://www.mercadolibre.cl/tienda/nicopoly"
    
    # In current production, lines 74-77 rewrite this URL to https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly
    # This assertion demands that official store URLs are NOT rewritten to the blocked fallback URL
    clean_url = scraper._get_clean_navigation_url(url_to_test) if hasattr(scraper, "_get_clean_navigation_url") else None
    
    # If helper doesn't exist, simulate the current code in navigate:
    # We test whether scraper's clean_url logic preserves the store URL:
    assert clean_url is not None, "Scraper must have a method to resolve clean navigation URL without side effects"
    assert clean_url == url_to_test, f"Official store URL should be preserved, but got: {clean_url}"

def test_ml_official_store_showcase_extraction_not_discarded():
    """
    RED test:
    Official store HTML renders products in .ui-ms-polycard-carousel / .ui-ms-section-eshops.
    Current production line 491 filters out any item with 'carousel' or 'recommendation' in parent classes,
    causing 0 products to be extracted from the official store.
    """
    sample_html = """
    <div class="home home--seller home--seller-brand">
      <div class="ui-ms-section-eshops ui-ms-section-eshops--seller">
        <div class="mshops-recommendations-wrapper ui-ms-polycard-carousel">
          <div class="andes-carousel-snapped__container">
            <div class="poly-card">
              <span class="poly-component__title">Polera Básica Algodón TEST_RUNTIME_BRAND</span>
              <span class="andes-money-amount__fraction">15.990</span>
              <a href="https://www.mercadolibre.cl/polera-basica/up/MLCU123456?wid=MLC123456">Ver producto</a>
            </div>
            <div class="poly-card">
              <span class="poly-component__title">Jeans Rectos TEST_RUNTIME_BRAND</span>
              <span class="andes-money-amount__fraction">29.990</span>
              <a href="https://www.mercadolibre.cl/jeans-rectos/up/MLCU789012?wid=MLC789012">Ver producto</a>
            </div>
          </div>
        </div>
      </div>
    </div>
    """
    scraper = MercadoLibreScraper(headless=True)
    import asyncio
    # Current production _extract_products_from_html will return 0 products because line 491 discards them
    products = asyncio.run(scraper._extract_products_from_html(sample_html, 1, 0, None))
    
    assert len(products) == 2, f"Expected 2 products from official store showcase, but extracted {len(products)}"
    assert products[0]["title"] == "Polera Básica Algodón TEST_RUNTIME_BRAND"
    assert products[0]["price"] == 15990.0
    assert products[0]["marketplace_sku"] == "MLC123456"
