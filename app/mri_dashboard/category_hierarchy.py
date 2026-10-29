"""Commercial category hierarchy used for dashboard rollups.

The marketplace exposes leaf categories; the operator-facing universe groups
them under their commercial parent. This is metadata, not a scraper route.
"""
from __future__ import annotations

import re

CHILD_TO_PARENT = {
    "chaquetas parkas y blazers": "Abrigos",
    "chalecos sweaters y cardigans": "Abrigos",
}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def parent_for(name: str) -> str | None:
    return CHILD_TO_PARENT.get(_norm(name))


def rollup(categories: dict[str, dict]) -> dict[str, dict]:
    """Aggregate child categories into their commercial parent.

    Input/output are the {category_id: category} shape used by the dashboard
    API. Counts are summed for display; this never changes persisted rows.
    """
    out: dict[str, dict] = {}
    parent_sums: dict[str, int] = {}
    parent_obs: dict[str, int] = {}
    parent_entries: dict[str, dict] = {}
    for cid, cat in (categories or {}).items():
        name = str((cat or {}).get("name") or "")
        parent = parent_for(name)
        if parent:
            parent_sums[parent] = parent_sums.get(parent, 0) + int(
                (cat or {}).get("publications") or 0)
            parent_obs[parent] = parent_obs.get(parent, 0) + int(
                (cat or {}).get("observations") or (cat or {}).get("publications") or 0)
            parent_entries.setdefault(parent, {
                "name": parent, "url": (cat or {}).get("url") or "",
                "source": "COMMERCIAL_ROLLUP", "status": "VERIFIED",
            })
            continue
        out[cid] = cat
    for parent, n in parent_sums.items():
        existing = next((k for k, v in out.items()
                         if _norm((v or {}).get("name")) == _norm(parent)), None)
        if existing:
            out[existing]["publications"] = int(out[existing].get("publications") or 0) + n
            out[existing]["observations"] = int(out[existing].get("observations") or 0) + parent_obs.get(parent, 0)
            out[existing]["source"] = "COMMERCIAL_ROLLUP"
        else:
            out[f"rollup_{_norm(parent).replace(' ', '_')}"] = {
                **parent_entries.get(parent, {"name": parent, "url": ""}),
                "publications": n,
                "observations": parent_obs.get(parent, n),
            }
    return out
