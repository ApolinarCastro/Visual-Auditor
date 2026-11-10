"""HTTP-only Mercado Libre engine (MRI-020).

Fetches the public SSR storefront with a bounded urllib timeout and extracts
MLC publication links. No Playwright, no Chromium.
"""
from __future__ import annotations

import asyncio
import re
import urllib.request
from typing import Any, Dict, List
from urllib.parse import urljoin

STOREFRONT_URL = "https://www.mercadolibre.cl/tienda/nicopoly"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


class MeliHTTPEngine:
    def _cookies(self) -> Dict[str, str]:
        import os as _os
        if str(_os.environ.get("USE_CHROME_COOKIES", "")).lower() not in ("1", "true", "yes"):
            return {}
        try:
            from app.mri_autonomous.cookie_extractor import get_meli_cookies
            return get_meli_cookies()
        except Exception:
            return {}

    def fetch_html(self, url: str = STOREFRONT_URL, timeout: int = 20) -> str:
        headers = {
            "User-Agent": UA,
            "Accept-Language": "es-CL,es;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        }
        cookies = self._cookies()
        if cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "ignore")

    @staticmethod
    def parse_html(html: str) -> List[Dict[str, Any]]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        products, seen = [], set()
        for anchor in soup.find_all("a", href=True):
            href = urljoin("https://www.mercadolibre.cl/", anchor["href"])
            if "/c/" in href or "#c_id" in href:
                continue
            match = re.search(r"(MLC-?\d+)", href, re.I)
            if not match:
                continue
            raw = match.group(1).upper()
            pid = raw if "-" in raw else raw.replace("MLC", "MLC-", 1)
            if pid in seen:
                continue
            seen.add(pid)
            title = (anchor.get("title") or anchor.get_text(" ", strip=True)
                     or (anchor.find("img").get("alt") if anchor.find("img") else "")
                     or pid)
            products.append({
                "marketplace_sku": pid,
                "title": title[:200],
                "product_title": title[:200],
                "url": href,
                "brand": "Nicopoly",
                "vendor": "Nicopoly",
                "price": 0.0,
                "position_absolute": len(products) + 1,
            })
        return products

    async def scrape_storefront(self, url: str = STOREFRONT_URL) -> Dict[str, Any]:
        try:
            html = await asyncio.to_thread(self.fetch_html, url)
        except Exception as exc:
            return {"products": [], "stop_reason": "SOURCE_BLOCKED",
                    "failure_type": f"HTTP_{type(exc).__name__}", "pages_traversed": 0}
        products = self.parse_html(html)
        if not products:
            return {"products": [], "stop_reason": "EXTRACTOR_FAILURE",
                    "failure_type": "MLC_LINKS_NOT_FOUND", "pages_traversed": 1}
        return {"products": products, "stop_reason": "EXHAUSTION",
                "failure_type": None, "pages_traversed": 1}
