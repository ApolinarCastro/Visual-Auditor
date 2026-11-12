"""Mercado Libre pagination recovery helpers (MRI layer)."""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit


def next_page_url(url: str, offset: int = 49) -> str:
    """Return the _Desde_N path-segment URL used by ML listados."""
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    path = re.sub(r"_Desde_\d+", "", path).rstrip("/")
    path = f"{path}/_Desde_{int(offset)}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def unique_new_products(existing: list[dict], incoming: list[dict]) -> list[dict]:
    seen = {
        str(p.get("marketplace_sku") or p.get("sku") or p.get("product_id") or "").upper()
        for p in existing
    }
    seen.discard("")
    out = []
    for product in incoming or []:
        pid = str(product.get("marketplace_sku") or product.get("sku")
                  or product.get("product_id") or "").upper()
        if pid and pid in seen:
            continue
        if pid:
            seen.add(pid)
        out.append(product)
    return out
