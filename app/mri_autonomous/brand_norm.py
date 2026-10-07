"""Brand normalization utilities (generic).

Transferred lesson (MRI-AUTOCLAW-001 / MRI-AUTONOMY-001 generalization):
productive logic must treat the brand as a *variable*. This module derives the
brand slug from any brand-hub URL and matches products against it, so no
'micopoly'-style literal is needed in acceptance, filtering or certification.
"""
from __future__ import annotations

import re
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

_RESERVED_LAST_SEGMENTS = {"search", "buscar", "tienda", "store", "listado"}


def normalize_brand(brand: Any) -> str:
    return re.sub(r"\s+", " ", str(brand or "").strip().lower())


def brand_slug_from_hub_url(hub_url: str) -> str:
    """Extract the brand slug from a brand hub URL (path or q/ntt param)."""
    if not hub_url:
        return ""
    p = urlparse(hub_url)
    path = p.path.strip("/")
    if path:
        last = path.split("/")[-1]
        if last and last.lower() not in _RESERVED_LAST_SEGMENTS:
            return last.lower()
    qs = parse_qs(p.query)
    for key, vals in qs.items():
        if key.lower() in ("q", "ntt") and vals:
            return normalize_brand(vals[0])
    return ""


def brand_match(product: Dict[str, Any], brand: str) -> bool:
    """True when the product's vendor or title carries the requested brand."""
    slug = normalize_brand(brand)
    if not slug:
        return False
    vendor = normalize_brand(product.get("vendor") or product.get("brand") or "")
    if vendor == slug:
        return True
    title = normalize_brand(product.get("title") or "")
    return bool(title and slug in title)
