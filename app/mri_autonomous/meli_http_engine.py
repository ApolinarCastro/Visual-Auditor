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
        cookies: Dict[str, str] = {}
        # MRI-029: reuse the cookies already persisted by the dashboard's
        # session store (35 ML cookies) before trying Chrome/CDP.
        if str(_os.environ.get("USE_SAVED_COOKIES", "1")).lower() not in ("0", "false", "no"):
            try:
                from app.mri_dashboard.session_store import load_cookies
                for c in load_cookies("Mercado Libre") or []:
                    name = c.get("name")
                    value = c.get("value")
                    if name and value is not None:
                        cookies[str(name)] = str(value)
            except Exception:
                pass
        if cookies:
            return cookies
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
            card = anchor.find_parent(
                class_=re.compile(r"poly-card|ui-search-layout__item", re.I))
            price = None
            if card is not None:
                price_node = card.select_one(
                    ".andes-money-amount__fraction, .poly-price__current, "
                    "[data-testid='price-part']")
                if price_node is not None:
                    digits = re.sub(r"[^0-9]", "", price_node.get_text(" ", strip=True))
                    if digits:
                        price = float(digits)
            products.append({
                "marketplace_sku": pid,
                "title": title[:200],
                "product_title": title[:200],
                "url": href,
                "brand": "Nicopoly",
                "vendor": "Nicopoly",
                "price": price or 0.0,
                "price_observed": price,
                "stock_status": "UNKNOWN",
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
