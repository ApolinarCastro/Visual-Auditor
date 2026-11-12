"""Mercado Libre snapshot/diff helpers (MRI layer).

Lightweight, dependency-free adaptation of the useful MIT-licensed ideas:
- declared result count from a rendered listing page;
- stable item snapshots;
- deterministic change events.
No scraping, no browser, no credentials.
"""
from __future__ import annotations

import re
from typing import Any


def parse_declared_total(text: str) -> int | None:
    """Read '658 resultados' / 'Mostrando 1 - 48 de 658' from page text."""
    if not text:
        return None
    normalized = str(text).replace("\xa0", " ")
    patterns = (
        r"([\d.]{1,12})\s*resultados?",
        r"mostrando\s+[\d.]+\s*-\s*[\d.]+\s+de\s+([\d.]{1,12})",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized, re.I):
            try:
                value = int(match.group(1).replace(".", ""))
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
    return None


def _item_id(item: dict) -> str:
    return str(item.get("marketplace_sku") or item.get("item_id")
               or item.get("id") or "").strip().upper()


def snapshot(items: list[dict]) -> dict[str, dict]:
    out = {}
    for item in items or []:
        item_id = _item_id(item)
        if not item_id:
            continue
        out[item_id] = {
            "title": item.get("title"),
            "price": item.get("price"),
            "status": item.get("status") or item.get("acquisition_state"),
            "url": item.get("url"),
        }
    return out


def diff(previous: dict | None, current: dict) -> list[dict]:
    """Compare two snapshots; only reports observable changes."""
    if previous is None:
        return [{"change": "BASELINE", "item_id": k} for k in current]
    changes = []
    for item_id, now in current.items():
        before = previous.get(item_id)
        if before is None:
            changes.append({"change": "NEW_LISTING", "item_id": item_id,
                            "new": now})
            continue
        for field in ("price", "status"):
            if before.get(field) != now.get(field):
                changes.append({"change": field.upper() + "_CHANGE",
                                "item_id": item_id,
                                "old": before.get(field),
                                "new": now.get(field)})
    for item_id, before in previous.items():
        if item_id not in current:
            changes.append({"change": "REMOVED_LISTING", "item_id": item_id,
                            "old": before})
    return changes
