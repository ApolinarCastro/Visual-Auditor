"""Discovery intelligence: escalate after a live-discovery failure.

The Creao research already established route knowledge. MRI reuses it as a
prior, validates every URL against the marketplace host, and records the
recovery strategy. Priors are not authoritative: acquisition still validates
each route live.
"""
from __future__ import annotations

from datetime import datetime

from app.mri_dashboard.marketplace_scope import filter_scope


def recover_prior_categories(marketplace: str, state: dict) -> list[dict]:
    """Return host-valid learned category routes as recovery candidates."""
    try:
        from app.mri_dashboard.category_manager import category_manager
        raw = category_manager.get_categories(marketplace) or {}
    except Exception:
        raw = {}
    kept, dropped = filter_scope(marketplace, raw)
    cats = []
    for cid, cat in kept.items():
        if not (cat or {}).get("url"):
            continue
        cats.append({
            "category_id": cid,
            "name": (cat or {}).get("name") or cid,
            "url": cat["url"],
            "parent_id": (cat or {}).get("parent_id"),
            "source": "LEARNED_PRIOR_ROUTES",
            "acquisition": (cat or {}).get("acquisition", True),
        })
    state.setdefault("discovery_recovery", []).append({
        "marketplace": marketplace,
        "strategy": "LEARNED_PRIOR_ROUTES",
        "candidates": len(cats),
        "dropped_cross_host": len(dropped),
        "at": datetime.now().isoformat(),
    })
    return cats
