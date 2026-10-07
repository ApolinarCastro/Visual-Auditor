import asyncio
import json
import pytest
from pathlib import Path

VA_ROOT = Path(__file__).resolve().parent.parent


def test_fal_02_challenge_page_classification():
    """FAL-02: Fixture of CHALLENGE_PAGE must be classified correctly."""
    challenge_html = """
    <html>
      <head><title>Cloudflare</title></head>
      <body>
        <h1>Lo siento, su acceso ha sido bloqueado</h1>
        <p>Ray ID: 1234567890abcdef</p>
      </body>
    </html>
    """
    from app.scrapers.falabella_scraper import detect_challenge_in_text
    is_chal, markers = detect_challenge_in_text(challenge_html, status=403)
    assert is_chal is True
    assert "access_blocked" in markers or "status_403" in markers

def test_fal_03_commercial_response_not_challenge():
    """FAL-03: Legitimate commercial response must NOT be classified as challenge."""
    commercial_html = """
    <html>
      <head><title>falabella.com</title></head>
      <body>
        <div class="pod-group">
          <div class="pod">
            <h3>Blazer Formal</h3>
            <span class="price">$29.990</span>
          </div>
        </div>
        <script id="__NEXT_DATA__">{"props": {"pageProps": {"results": [{"displayName": "Blazer"}]}}}</script>
      </body>
    </html>
    """
    from app.scrapers.falabella_scraper import detect_challenge_in_text, detect_commercial_content
    is_chal, ch_markers = detect_challenge_in_text(commercial_html, status=200)
    assert is_chal is False

    is_comm, comm_markers = detect_commercial_content(commercial_html)
    assert is_comm is True


def test_fal_05_anti_hardcode_brand_independence():
    """FAL-05: Solution must support dynamic runtime brand without literal hardcoding."""
    from app.mri_autonomous.brand_hubs import brand_hub_for
    hub_generic = brand_hub_for("Falabella", "GenericBrand123")
    assert "GenericBrand123".lower() in hub_generic.canonical_reference.lower()
    assert "nicopoly" not in hub_generic.canonical_reference.lower()

@pytest.mark.asyncio
async def test_fal_01_and_04_pipeline_selects_working_strategy():
    """FAL-01 & FAL-04: FalabellaScraper must handle challenge by activating existing HTTP acquisition fallback."""
    from app.scrapers.falabella_scraper import FalabellaScraper

    scraper = FalabellaScraper(headless=True)
    await scraper.start()
    try:
        test_url = "https://www.falabella.com/falabella-cl/search?Ntt=nicopoly"
        ok = await scraper.navigate(test_url)
        assert ok is True, "FalabellaScraper.navigate failed"
        
        # Verify page content is commercial, not Cloudflare
        title = await scraper.page.title()
        assert "cloudflare" not in title.lower(), f"Page still on challenge: {title}"
        assert "falabella" in title.lower() or "search" in title.lower()
        
        # Verify DOM is usable and has product elements or structured data
        pods = await scraper.page.query_selector_all(".pod, .pod-4_GRID, div[id*='testId-pod'], [class*='pod-group']")
        next_data = await scraper.page.query_selector("#__NEXT_DATA__")
        assert len(pods) > 0 or next_data is not None, "DOM has no commercial products or __NEXT_DATA__"
    finally:
        await scraper.stop()
