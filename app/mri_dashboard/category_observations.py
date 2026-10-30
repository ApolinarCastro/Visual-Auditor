"""Match persisted category rows to acquisition URLs for raw result counts."""
from __future__ import annotations

import re

_STOP = {"y", "de", "del", "la", "el", "los", "las", "para", "en", "con", "por"}
_ALIASES = {
    # Display/category name -> URL hint when the marketplace slug differs.
    "body": ("ropa", "interior"),
}


def _tokens(value: str) -> set[str]:
    raw = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split()
    return {t for t in raw if t and t not in _STOP}


def _score(category_name: str, url: str) -> int:
    name_tokens = _tokens(category_name)
    url_tokens = _tokens(url)
    if not name_tokens or not url_tokens:
        return 0
    hints = _ALIASES.get(str(category_name or "").strip().lower())
    if hints and all(h in url_tokens for h in hints):
        return 100
    return len(name_tokens & url_tokens)


def observations_for(categories: dict, acquisitions: list[dict]) -> dict[str, int]:
    """Return {category_id: raw observed count} using URL/name evidence."""
    matched: dict[str, int] = {}
    for acq in acquisitions or []:
        url = str(acq.get("requested_url") or acq.get("observed_url") or "")
        raw = int(acq.get("products_observed_raw")
                  or acq.get("products_extracted") or 0)
        if not raw or not url:
            continue
        best_id, best_score = None, 0
        for cid, cat in (categories or {}).items():
            score = _score((cat or {}).get("name"), url)
            if score > best_score:
                best_id, best_score = cid, score
        if best_id and best_score:
            matched[best_id] = max(int(matched.get(best_id, 0)), raw)
    return matched
