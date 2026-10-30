"""MRI-layer MercadoLibre storefront SSR acquisition.

VA verified that the only stable public product source is the SSR storefront:
`www.mercadolibre.cl/tienda/nicopoly` (200) with `pageProps`/`polycards`.
This adapter never touches the frozen ML scraper and never invents counts.
"""
from __future__ import annotations

import asyncio
import html as _html
import json
import re
from typing import Any

from app.mri_autonomous.meli_taxonomy_engine import (
    MLC_STOREFRONT_URL, MeliTaxonomyEngine)


def _brace_slice(text: str, start: int) -> str | None:
    """Return a balanced JSON object/array starting at/after start."""
    i = start
    while i < len(text) and text[i] not in "[{":
        i += 1
    if i >= len(text):
        return None
    open_ch = text[i]
    close_ch = "]" if open_ch == "[" else "}"
    depth = 0
    in_str = False
    esc = False
    for j in range(i, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    return None


def extract_polycards(html: str) -> list[dict]:
    """Decode the SSR payload and return polycards without trusting DOM."""
    if not html:
        return []
    text = html.replace("\\u002F", "/").replace("\\/", "/")
    # Unescape the JSON string wrapper used by _n.ctx.s.q("{...}").
    text = text.replace('\\"', '"').replace("\\u0022", '"')
    for key in ('"polycards"', 'polycards'):
        at = text.find(key)
        if at < 0:
            continue
        raw = _brace_slice(text, at + len(key))
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        if isinstance(payload, dict):
            payload = payload.get("polycards") or payload.get("results") or []
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
    return []


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or value.get("value") or "").strip()
    return str(value or "").strip()


def normalize_polycard(card: dict) -> dict | None:
    meta = card.get("metadata") or card.get("item") or {}
    item_id = str(meta.get("id") or meta.get("item_id") or card.get("id") or "").strip().upper()
    user_product_id = str(meta.get("user_product_id") or meta.get("userProductId") or "").strip().upper()
    title = _text(card.get("title"))
    url = str(meta.get("url") or card.get("url") or "").strip()
    if not item_id and url:
        m = re.search(r"(MLC-?\d+)", url, re.I)
        if m:
            item_id = m.group(1).replace("-", "").upper()
    if not item_id or not title:
        return None
    price = 0.0
    try:
        price = float((card.get("price") or {}).get("current_price", {}).get("value") or 0)
    except Exception:
        pass
    return {
        "title": title,
        "vendor": str(meta.get("seller_name") or "Nicopoly"),
        "brand_surface_url": MLC_STOREFRONT_URL,
        "price": price,
        "marketplace_sku": item_id,
        "user_product_id": user_product_id,
        "url": url,
        "page": 1,
        "position_local": 0,
        "position_absolute": 0,
    }


def parse_storefront_dom_products(html: str) -> list[dict]:
    """Parse rendered SSR storefront cards (current ML layout, no JSON payload)."""
    if not html:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []
    products, seen = [], set()
    for a in soup.select('a.poly-component__title[href], a[href*="/up/MLCU"]'):
        href = a.get("href") or ""
        title = a.get_text(" ", strip=True)
        if not href or not title:
            continue
        import urllib.parse
        m_item = re.search(r"item_id(?:%3A|:)(MLC\d+)", href, re.I)
        if not m_item:
            m_item = re.search(r"[?&#]wid=(MLC\d+)", href, re.I)
        m_up = re.search(r"/up/(MLCU\d+)", href, re.I)
        item_id = (m_item.group(1) if m_item else "").upper()
        user_product_id = (m_up.group(1) if m_up else "").upper()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        card = a.find_parent(class_=re.compile(r"poly-card|ui-search-layout__item"))
        price = 0.0
        if card is not None:
            price_el = card.select_one(".poly-price__current .andes-money-amount__fraction")
            if price_el:
                try:
                    price = float(re.sub(r"[^0-9]", "", price_el.get_text()) or 0)
                except Exception:
                    price = 0.0
        products.append({
            "title": title,
            "vendor": "Nicopoly",
            "brand_surface_url": MLC_STOREFRONT_URL,
            "price": price,
            "marketplace_sku": item_id,
            "user_product_id": user_product_id,
            "url": href,
            "page": 1,
            "position_local": len(products) + 1,
            "position_absolute": len(products) + 1,
        })
    return products


def parse_storefront_products(html: str) -> list[dict]:
    products, seen = [], set()
    cards = extract_polycards(html)
    if not cards:
        return parse_storefront_dom_products(html)
    for card in cards:
        item = normalize_polycard(card)
        if not item or item["marketplace_sku"] in seen:
            continue
        seen.add(item["marketplace_sku"])
        item["position_local"] = len(products) + 1
        item["position_absolute"] = len(products) + 1
        products.append(item)
    return products


async def scrape_storefront_category(url: str) -> dict:
    if "listado.mercadolibre.cl" in str(url) or "/listado/" in str(url):
        return {"products": [], "stop_reason": "SOURCE_BLOCKED",
                "pages_traversed": 0,
                "failure_type": "STOREFRONT_ONLY_SURFACE: listado requires human verification"}
    html, status = await asyncio.to_thread(MeliTaxonomyEngine().fetch_storefront_html)
    if status != "FOUND" or not html:
        return {"products": [], "stop_reason": "SOURCE_BLOCKED",
                "pages_traversed": 0,
                "failure_type": f"STOREFRONT_{status}"}
    products = parse_storefront_products(html)
    if not products:
        return {"products": [], "stop_reason": "EXTRACTOR_FAILURE",
                "pages_traversed": 1,
                "failure_type": "SSR_POLYCARDS_NOT_FOUND"}
    return {
        "products": products,
        "stop_reason": "EXHAUSTION",
        "pages_traversed": 1,
        "failure_type": None,
        # The storefront does not expose a product total; never turn the
        # visible 37 cards into an invented total.
        "pagination": {"total_declared": None},
    }
