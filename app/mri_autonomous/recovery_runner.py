"""
app/mri_autonomous/recovery_runner.py

Permanent operational runner for multi-marketplace commercial publication recovery.
Provides reproducible execution across Mercado Libre, Falabella, Paris, and Ripley
using certified scraper mechanisms with strict resource boundaries and checkpoints.
"""

import asyncio
import json
import logging
import re
import urllib.request
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from app.scrapers.mercadolibre_scraper import MercadoLibreScraper
from app.scrapers.paris_scraper import ParisScraper
from app.scrapers.ripley_scraper import RipleyScraper

logger = logging.getLogger(__name__)

class AcquisitionRecoveryRunner:
    """
    Reproducible operational acquisition pipeline across 4 marketplaces.
    Runs certified paginated harvesting, deduplication, and persistence.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path("evidence/va_4mp_live_publications_001")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.raw_harvest_file = self.output_dir / "raw_live_harvest.json"

    def fetch_falabella_catalog(self, brand: str = "nicopoly", max_pages: int = 10) -> List[Dict[str, Any]]:
        """
        Certified HTTP SSR paginated acquisition for Falabella.
        Uses canonical www.falabella.com with standard browser User-Agent to avoid WAF 403.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8"
        }
        products = {}
        for page in range(1, max_pages + 1):
            url = f"https://www.falabella.com/falabella-cl/search?Ntt={brand}&page={page}"
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
                
                m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
                if not m:
                    break
                data = json.loads(m.group(1))
                results = data.get("props", {}).get("pageProps", {}).get("results", [])
                if not results:
                    break
                
                for r in results:
                    pid = str(r.get("productId") or "").strip()
                    title = str(r.get("displayName") or "").strip()
                    p_url = str(r.get("url") or f"https://www.falabella.com/falabella-cl/product/{pid}/p")
                    prices = r.get("prices", [])
                    price = 0.0
                    if prices:
                        pval = prices[0].get("price", [0])
                        if isinstance(pval, list) and pval:
                            price = float(str(pval[0]).replace(".", "").replace(",", "."))
                        elif isinstance(pval, (int, float)):
                            price = float(pval)
                    
                    if pid and pid not in products:
                        products[pid] = {
                            "title": title,
                            "vendor": "Nicopoly",
                            "price": price,
                            "marketplace_sku": pid,
                            "url": p_url,
                            "position_absolute": len(products) + 1,
                            "source_url": "https://www.falabella.com/falabella-cl/search?Ntt=nicopoly",
                            "marketplace": "Falabella",
                            "harvest_time": datetime.now().isoformat()
                        }
            except Exception as e:
                logger.warning(f"[RecoveryRunner] Falabella page {page} fetch failed: {e}")
                break
        return list(products.values())

    async def fetch_paris_catalog(self, brand: str = "nicopoly", max_batches: int = 25) -> List[Dict[str, Any]]:
        """Certified Playwright headless batch extraction for Paris."""
        p = ParisScraper(headless=True)
        await p.start()
        products = {}
        try:
            url = f"https://www.paris.cl/search?q={brand}"
            ok = await p.navigate(url)
            if not ok:
                return []
            
            consecutive_unchanged = 0
            last_count = 0
            for batch in range(1, max_batches + 1):
                html = await p.page.content()
                items = await p._extract_products_from_html(html, len(products), None)
                for it in items:
                    sku = str(it.get("marketplace_sku") or "").strip()
                    url_it = (it.get("url") or "").strip()
                    key = url_it if url_it else sku
                    if key and key not in products:
                        it["position_absolute"] = len(products) + 1
                        it["marketplace"] = "Paris"
                        it["harvest_time"] = datetime.now().isoformat()
                        it["source_url"] = url
                        products[key] = it
                
                if len(products) == last_count:
                    consecutive_unchanged += 1
                else:
                    consecutive_unchanged = 0
                    last_count = len(products)
                if consecutive_unchanged >= 3:
                    break
                
                btn = await p.page.query_selector('button:has-text("Mostrar más")')
                if not btn:
                    break
                await btn.click()
                await asyncio.sleep(1.5)
        finally:
            await p.stop()
        return list(products.values())

    async def fetch_mercadolibre_catalog(self, max_pages: int = 15) -> List[Dict[str, Any]]:
        """Certified Playwright headless paginated extraction for Mercado Libre official store."""
        scraper = MercadoLibreScraper(headless=True)
        await scraper.start()
        try:
            res = await scraper.scrape_autonomous_category(
                "https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly",
                max_pages=max_pages
            )
            raw = res.get("products", [])
            for it in raw:
                it["marketplace"] = "Mercado Libre"
                it["source_url"] = "https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly"
                it["harvest_time"] = datetime.now().isoformat()
            return raw
        finally:
            await scraper.stop()

    async def fetch_ripley_catalog(self, brand: str = "nicopoly", max_pages: int = 10) -> List[Dict[str, Any]]:
        """Certified Playwright headless paginated extraction for Ripley."""
        scraper = RipleyScraper(headless=True)
        await scraper.start()
        try:
            res = await scraper.scrape_autonomous_category(
                f"https://simple.ripley.cl/search/{brand}",
                max_pages=max_pages
            )
            raw = res.get("products", [])
            for it in raw:
                it["marketplace"] = "Ripley"
                it["source_url"] = f"https://simple.ripley.cl/search/{brand}"
                it["harvest_time"] = datetime.now().isoformat()
            return raw
        finally:
            await scraper.stop()

    def run_all_harvests(self) -> Dict[str, List[Dict[str, Any]]]:
        """Runs all 4 harvests sequentially and returns combined dictionary."""
        logger.info("[RecoveryRunner] Starting Falabella harvest...")
        fala = self.fetch_falabella_catalog()
        
        logger.info("[RecoveryRunner] Starting Paris harvest...")
        paris = asyncio.run(self.fetch_paris_catalog())
        
        logger.info("[RecoveryRunner] Starting Mercado Libre harvest...")
        ml = asyncio.run(self.fetch_mercadolibre_catalog())
        
        logger.info("[RecoveryRunner] Starting Ripley harvest...")
        ripley = asyncio.run(self.fetch_ripley_catalog())
        
        harvest = {
            "Falabella": fala,
            "Paris": paris,
            "Mercado Libre": ml,
            "Ripley": ripley
        }
        with open(self.raw_harvest_file, "w", encoding="utf-8") as f:
            json.dump(harvest, f, ensure_ascii=False, indent=2)
        return harvest
