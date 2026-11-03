"""Match persisted category rows to acquisition URLs for raw result counts.

Matching must be URL-first. Category display names can share the whole family
prefix (e.g. "Moda Mujer → Vestidos y Enteritos → Faldas" vs "... → Vestidos"),
so token scoring over the full name creates ties and attributes an acquisition
to the wrong category.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

_STOP = {"y", "de", "del", "la", "el", "los", "las", "para", "en", "con", "por"}
_ALIASES = {
    "body": ("ropa", "interior"),
}


def _tokens(value: str) -> set[str]:
    raw = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split()
    return {t for t in raw if t and t not in _STOP}


def _base_url(value: str) -> str:
    try:
        return urlparse(str(value or "")).path.rstrip("/").lower()
    except Exception:
        return ""


def _leaf_name(value: str) -> str:
    parts = [p.strip() for p in str(value or "").replace(">", "→").split("→") if p.strip()]
    return parts[-1] if parts else str(value or "")


def _score(category_name: str, url: str) -> int:
    """Score only the leaf category name against the URL leaf, not the prefix."""
    leaf_tokens = _tokens(_leaf_name(category_name))
    url_tokens = _tokens(urlparse(str(url or "")).path.replace("-", " ").replace("/", " "))
    if not leaf_tokens or not url_tokens:
        return 0
    hints = _ALIASES.get(str(_leaf_name(category_name)).strip().lower())
    if hints and all(h in url_tokens for h in hints):
        return 100
    return len(leaf_tokens & url_tokens)


def observations_for(categories: dict, acquisitions: list[dict]) -> dict[str, int]:
    """Return {category_id: raw observed count} using URL-first evidence."""
    matched: dict[str, int] = {}
    # Exact canonical-path index avoids every prefix/name tie.
    by_base: dict[str, str] = {}
    for cid, cat in (categories or {}).items():
        base = _base_url((cat or {}).get("url"))
        if base:
            by_base[base] = cid
    def _url_leaf(value: str) -> str:
        try:
            parts = [p for p in urlparse(str(value or "")).path.split("/") if p]
            return parts[-1] if parts else ""
        except Exception:
            return ""

    for acq in acquisitions or []:
        url = str(acq.get("requested_url") or acq.get("observed_url") or "")
        raw = int(acq.get("products_observed_raw")
                  or acq.get("products_extracted") or 0)
        if not raw or not url:
            continue
        base = _base_url(url)
        cid = by_base.get(base)
        if not cid:
            # Exact leaf is the strongest evidence and avoids prefix ties
            # (Faldas vs Vestidos vs Enteritos share the same family).
            _leaf = _tokens(_url_leaf(url))
            exact = [candidate for candidate, cat in (categories or {}).items()
                     if _tokens(_leaf_name((cat or {}).get("name"))) == _leaf
                     and _leaf]
            if len(exact) == 1:
                cid = exact[0]
        if not cid:
            best_id, best_score = None, 0
            for candidate, cat in (categories or {}).items():
                score = _score((cat or {}).get("name"), url)
                if score > best_score:
                    best_id, best_score = candidate, score
            cid = best_id
        if cid:
            matched[cid] = max(int(matched.get(cid, 0)), raw)
    return matched
