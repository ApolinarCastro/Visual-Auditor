"""Persistent discovery graph: reuse learned marketplace routes.

Nodes are marketplace/brand surfaces and category routes; the graph stores the
evidence and timestamps needed to skip rediscovery while keeping routes
revalidatable. No category list is fixed here.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_GRAPH = Path(__file__).resolve().parents[2] / "knowledge" / "discovery_graph.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(marketplace: str, brand: str, store_url: str | None = None) -> str:
    # One graph node per brand/marketplace; the store URL is stored inside the
    # node and can be revalidated without changing the lookup key.
    return f"{marketplace}|{brand}"


def _load() -> dict:
    try:
        data = json.loads(_GRAPH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    try:
        _GRAPH.parent.mkdir(parents=True, exist_ok=True)
        _GRAPH.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    except Exception:
        pass


def load_node(marketplace: str, brand: str, store_url: str | None = None) -> dict:
    return dict(_load().get(_key(marketplace, brand, store_url)) or {})


def learned_categories(marketplace: str, brand: str,
                       store_url: str | None = None,
                       max_age_seconds: int = 86400) -> list[dict]:
    node = load_node(marketplace, brand, store_url)
    try:
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(node.get("updated_at"))).total_seconds()
    except Exception:
        return []
    if not node.get("categories") or age > max_age_seconds:
        return []
    out = []
    for name, c in (node.get("categories") or {}).items():
        if not c.get("url") or c.get("status") in ("INVALID", "BLOCKED"):
            continue
        item = dict(c)
        item["name"] = name
        item["source"] = "GRAPH_CACHE"
        out.append(item)
    return out


def merge_discovered(marketplace: str, brand: str, store_url: str | None,
                     categories: list[dict], source: str) -> dict:
    data = _load()
    key = _key(marketplace, brand, store_url)
    node = data.setdefault(key, {"categories": {}, "created_at": _now()})
    node["store_url"] = store_url
    node["marketplace"] = marketplace
    node["brand"] = brand
    node["updated_at"] = _now()
    for c in categories or []:
        name = c.get("name")
        url = c.get("url")
        if not name or not url:
            continue
        old = node["categories"].get(name) or {}
        node["categories"][name] = {
            "url": url,
            "source": c.get("source") or source,
            "parent_url": c.get("parent_url"),
            "acquisition": c.get("acquisition", True),
            "category_id": c.get("category_id"),
            "fallback_urls": c.get("fallback_urls") or old.get("fallback_urls") or [],
            "first_seen": old.get("first_seen") or _now(),
            "last_seen": _now(),
            "status": "ACTIVE",
            "hits": int(old.get("hits") or 0),
        }
    _save(data)
    return node


def mark_hit(marketplace: str, brand: str, store_url: str | None = None) -> None:
    data = _load()
    key = _key(marketplace, brand, store_url)
    node = data.get(key)
    if not node:
        return
    node["last_used"] = _now()
    for c in (node.get("categories") or {}).values():
        c["hits"] = int(c.get("hits") or 0) + 1
    _save(data)


def mark_verified(marketplace: str, brand: str, store_url: str | None,
                  category_name: str, state: str) -> None:
    data = _load()
    key = _key(marketplace, brand, store_url)
    node = data.get(key)
    if not node:
        return
    c = (node.get("categories") or {}).get(category_name)
    if not c:
        return
    c["last_verified"] = _now()
    c["status"] = "ACTIVE" if state in ("FOUND", "EXHAUSTION") else state
    _save(data)
