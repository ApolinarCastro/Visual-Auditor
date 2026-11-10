"""HTTP-only Ripley engine (MRI-020).

Uses the public category HTML and its embedded __NEXT_DATA__ catalog.
No Playwright, no Chromium.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Any, Dict, List

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


class RipleyHTTPEngine:
    def fetch_html(self, url: str, timeout: int = 30) -> str:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept-Language": "es-CL,es;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "ignore")

    @staticmethod
    def _next_data(html: str) -> Dict[str, Any]:
        m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if not m:
            return {}
        try:
            return json.loads(m.group(1))
        except Exception:
            return {}

    def scrape_category(self, url: str, timeout: int = 30) -> Dict[str, Any]:
        try:
            html = self.fetch_html(url, timeout=timeout)
        except Exception as exc:
            return {"products": [], "stop_reason": "SOURCE_BLOCKED",
                    "failure_type": f"HTTP_{type(exc).__name__}", "pages_traversed": 0}
        data = self._next_data(html)
        props = ((data.get("props") or {}).get("pageProps") or {})
        findability = props.get("findabilityProps") or {}
        catalog = findability.get("data") or {}
        raw = catalog.get("products") or props.get("products") or []
        total = catalog.get("total")
        products: List[Dict[str, Any]] = []
        for idx, item in enumerate(raw, 1):
            if not isinstance(item, dict):
                continue
            sku = str(item.get("sku") or item.get("partNumber") or item.get("uniqueID") or "")
            if not sku:
                continue
            name = str(item.get("name") or "")
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            parent = str(item.get("parentProductID") or sku)
            product_url = (item.get("url") or
                           f"https://simple.ripley.cl/{slug}-mpm{parent}" if slug else
                           f"https://simple.ripley.cl/producto/{sku}")
            price = item.get("priceNumber") or item.get("masterPriceNumber") or 0
            products.append({
                "marketplace_sku": sku,
                "title": name,
                "product_title": name,
                "url": product_url,
                "brand": str(item.get("brand") or "Nicopoly"),
                "vendor": "Nicopoly",
                "price": float(price or 0),
                "position_absolute": idx,
                "category": (findability.get("catalog") or {}).get("name") or "Ripley",
            })
        return {
            "products": products,
            "stop_reason": "EXHAUSTION" if products else "SOURCE_BLOCKED",
            "failure_type": None if products else "NO_PRODUCTS_IN_HTTP_RESPONSE",
            "pages_traversed": 1,
            "total_declared": total,
        }
