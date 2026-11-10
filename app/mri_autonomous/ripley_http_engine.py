"""HTTP-only Ripley engine with bounded pagination (MRI-022)."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any, Dict, List

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
MAX_PAGES = int(os.getenv("MRI_HTTP_MAX_PAGES", "10"))


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

    def _products(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        props = ((data.get("props") or {}).get("pageProps") or {})
        findability = props.get("findabilityProps") or {}
        catalog = findability.get("data") or {}
        raw = catalog.get("products") or props.get("products") or []
        out = []
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
                           (f"https://simple.ripley.cl/{slug}-mpm{parent}" if slug else
                            f"https://simple.ripley.cl/producto/{sku}"))
            out.append({
                "marketplace_sku": sku,
                "title": name,
                "product_title": name,
                "url": product_url,
                "brand": str(item.get("brand") or "Nicopoly"),
                "vendor": "Nicopoly",
                "price": float(item.get("priceNumber") or item.get("masterPriceNumber") or 0),
                "position_absolute": idx,
            })
        return out

    def scrape_category(self, url: str, timeout: int = 30,
                        max_pages: int | None = None) -> Dict[str, Any]:
        limit = int(max_pages or MAX_PAGES)
        seen, products = set(), []
        pages = 0
        for page in range(1, limit + 1):
            page_url = url if page == 1 else (url + ("&" if "?" in url else "?") + f"page={page}")
            try:
                html = self.fetch_html(page_url, timeout=timeout)
            except Exception as exc:
                return {"products": products, "stop_reason": "SOURCE_BLOCKED",
                        "failure_type": f"HTTP_{type(exc).__name__}", "pages_traversed": pages}
            data = self._next_data(html)
            batch = self._products(data)
            pages += 1
            new = 0
            for p in batch:
                if p["marketplace_sku"] in seen:
                    continue
                seen.add(p["marketplace_sku"])
                p["position_absolute"] = len(products) + 1
                products.append(p)
                new += 1
            if not batch or new == 0:
                break
        return {"products": products, "stop_reason": "EXHAUSTION" if products else "EMPTY_VERIFIED",
                "failure_type": None, "pages_traversed": pages}
