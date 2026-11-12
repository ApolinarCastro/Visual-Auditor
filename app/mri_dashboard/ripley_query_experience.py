"""Query experience log for autonomous Ripley discovery.

Records what MRI actually tried (surface URL, category, result, stop reason)
so future runs can reuse successful query shapes and avoid repeating failed
ones. It contains no master category list and no hardcoded answer set.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

LOG_NAME = "ripley_query_experience.jsonl"


def _log_path(aux_dir) -> Path:
    base = Path(aux_dir) if aux_dir else Path("data/sqlite/mri_operational")
    base.mkdir(parents=True, exist_ok=True)
    return base / LOG_NAME


def record_query(aux_dir, *, run_id: str, marketplace: str, url: str,
                 category: str, products: int, state: str,
                 stop_reason: str | None = None,
                 failure: str | None = None) -> dict:
    entry = {
        "run_id": run_id,
        "marketplace": marketplace,
        "url": url,
        "category": category,
        "products": int(products or 0),
        "state": state,
        "stop_reason": stop_reason,
        "failure": failure,
        "observed_at": datetime.now().isoformat(),
    }
    path = _log_path(aux_dir)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_query_experience(aux_dir, run_id: str | None = None) -> list[dict]:
    path = _log_path(aux_dir)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if run_id is None or item.get("run_id") == run_id:
            out.append(item)
    return out


def successful_query_shapes(aux_dir, marketplace: str = "Ripley") -> dict:
    """Learn URL/category shapes that produced products, without hardcoding."""
    out = {}
    for item in read_query_experience(aux_dir):
        if item.get("marketplace") != marketplace or not item.get("products"):
            continue
        key = item.get("category") or item.get("url")
        if key:
            out[key] = {"url": item["url"],
                        "products": item["products"],
                        "stop_reason": item.get("stop_reason")}
    return out
