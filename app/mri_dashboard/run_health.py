"""Operational health and coverage summaries for MRI runs.

Inspired by VA's health_log/global_census, but computed only from MRI's real
acquisition evidence. No synthetic totals, no sentinel values.
"""
from __future__ import annotations

from collections import Counter


def build_health(events: list[dict]) -> dict:
    rows = list(events or [])
    by_market = Counter(str(e.get("marketplace") or "N/A") for e in rows)
    errors = [e for e in rows if str(e.get("state") or "").upper()
              in ("SOURCE_BLOCKED", "EXTRACTOR_FAILURE", "PARTIAL")]
    durations = [float(e["duration_ms"]) for e in rows
                 if e.get("duration_ms") is not None]
    return {
        "events": len(rows),
        "by_marketplace": dict(by_market),
        "errors": len(errors),
        "error_rate_pct": round((len(errors) / len(rows) * 100), 2) if rows else 0.0,
        "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else None,
        "last_event": rows[-1].get("at") if rows else None,
        "status": ("DEGRADED" if errors else ("HEALTHY" if rows else "NO_DATA")),
    }


def build_source_health(events: list[dict]) -> dict:
    out = {}
    for event in events or []:
        mkt = str(event.get("marketplace") or "N/A")
        state = str(event.get("state") or "").upper()
        node = out.setdefault(mkt, {
            "marketplace": mkt, "last_event": None, "last_success": None,
            "last_failure": None, "consecutive_failures": 0,
            "status": "HEALTHY"})
        node["last_event"] = event.get("at")
        if state in ("FOUND", "EXHAUSTION", "COMPLETE"):
            node["last_success"] = event.get("at")
            node["consecutive_failures"] = 0
            node["status"] = "HEALTHY"
        else:
            node["last_failure"] = event.get("at")
            node["consecutive_failures"] += 1
            node["status"] = "DEGRADED"
    return out


def build_global_coverage(taxonomy: dict, acquisitions: list[dict],
                          results: list[dict], declared_totals: dict | None = None) -> dict:
    """Category census vs brand observations, with explicit known/unknown."""
    tax = taxonomy or {}
    cats = tax.get("categories") or []
    targets = [c for c in cats if (c or {}).get("acquisition", True) is not False]
    acqs = list(acquisitions or [])
    completed = [a for a in acqs
                 if str(a.get("acquisition_state") or "").upper()
                 in ("FOUND", "EXHAUSTION", "COMPLETE")]
    raw = sum(int(a.get("products_observed_raw")
                  or a.get("products_extracted") or 0) for a in acqs)
    unique_ids = {
        str((r or {}).get("observed_sku") or (r or {}).get("producto_id")
            or (r or {}).get("marketplace_product_id") or "")
        for r in (results or [])
    }
    unique_ids.discard("")
    declared = [int(v) for v in (declared_totals or {}).values()
                if isinstance(v, (int, float)) and int(v) > 0]
    declared_sum = sum(declared) if declared else None
    return {
        "categories_discovered": len(targets),
        "categories_discovered_total": len(cats),
        "categories_acquired": len(acqs),
        "categories_complete": len(completed),
        "observations_raw": raw,
        "unique_publications": len(unique_ids),
        "duplicate_observations": max(0, raw - len(unique_ids)),
        "declared_total_known": declared_sum,
        "coverage_vs_declared_pct": (round(len(unique_ids) / declared_sum * 100, 2)
                                     if declared_sum else None),
        "coverage_status": ("COMPLETE" if acqs and len(completed) == len(acqs)
                            and len(targets) and len(acqs) >= len(targets)
                            else "PARTIAL"),
    }
