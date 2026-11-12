"""Marketplace URL scope guard.

A category URL must belong to the marketplace being audited. This prevents
persistent/fallback category caches from injecting another marketplace's URLs
into a run (observed: Ripley scraper navigating Mercado Libre URLs).
"""
from __future__ import annotations

from urllib.parse import urlparse

MARKETPLACE_HOSTS = {
    "Ripley": ("ripley.cl",),
    "Mercado Libre": ("mercadolibre.cl", "mercadolibre.com"),
    "Paris": ("paris.cl",),
    "Falabella": ("falabella.com", "falabella.cl"),
}


def _host_allowed(host: str, marketplace: str) -> bool:
    host = str(host or "").lower().rstrip(".")
    return any(host == d or host.endswith("." + d)
               for d in MARKETPLACE_HOSTS.get(marketplace, ()))


def url_allowed(marketplace: str, url: str) -> bool:
    try:
        host = urlparse(str(url or "")).hostname or ""
    except Exception:
        return False
    return _host_allowed(host, marketplace)


def filter_scope(marketplace: str, categories: dict) -> tuple[dict, list[dict]]:
    kept, dropped = {}, []
    for cid, cat in (categories or {}).items():
        url = (cat or {}).get("url") or ""
        if url_allowed(marketplace, url):
            kept[cid] = cat
        else:
            dropped.append({"category_id": cid, "name": (cat or {}).get("name"),
                            "url": url, "reason": "MARKETPLACE_HOST_MISMATCH"})
    return kept, dropped
