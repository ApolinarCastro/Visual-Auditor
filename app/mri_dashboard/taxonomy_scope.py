"""Taxonomy scope guard for full audits (CP2)."""
from __future__ import annotations


def categories_from_taxonomy(taxonomy: dict | None) -> dict:
    """Return acquisition categories belonging to THIS taxonomy result only.

    The persistent category_manager can contain categories discovered in older
    runs (including generic, non-store listado URLs). Full-audit scope must not
    inherit them.
    """
    categories = {}
    for item in (taxonomy or {}).get("categories") or []:
        key = str(item.get("category_id") or item.get("url") or "")
        if not key:
            continue
        categories[key] = {
            "name": item.get("name"),
            "url": item.get("url"),
            "parent_id": item.get("parent_id"),
            "acquisition": item.get("acquisition", True),
        }
    return categories
