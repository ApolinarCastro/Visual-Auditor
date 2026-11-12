"""Deterministic observation-vs-publication reconciliation (CP3)."""
from __future__ import annotations

from collections import Counter


def result_identity(row: dict) -> str:
    row = row or {}
    product = row.get("product") or {}
    value = (row.get("observed_sku") or row.get("producto_id")
             or row.get("marketplace_product_id") or product.get("sku"))
    return str(value or "").strip()


def summarize_results(results) -> dict:
    rows = list(results or [])
    identities = [result_identity(r) for r in rows]
    unique = {i for i in identities if i}
    dup_counts = Counter(i for i in identities if i)
    duplicates = sum(n - 1 for n in dup_counts.values() if n > 1)
    by_market = Counter(str((r or {}).get("marketplace") or "N/A") for r in rows)
    return {
        "observations": len(rows),
        "unique_publications": len(unique),
        "duplicate_observations": duplicates,
        "empty_identities": identities.count(""),
        "duplicate_identities": {k: v for k, v in dup_counts.items() if v > 1},
        "by_marketplace": dict(by_market),
        "definition": "observations = posiciones/categorías observadas; "
                      "unique_publications = identidad de publicación única",
    }


def reconcile_declared(declared, extracted_raw: int, extracted_unique: int,
                       max_ratio: float = 0.02) -> dict:
    """Compare the source count against observed positions, not unique IDs.

    A declared page total counts positions. Duplicate IDs inside the same
    category are positions observed more than once and are collapsed later by
    persistence; they are not missing publications. Unique IDs remain a
    separate diagnostic.
    """
    if declared in (None, "", 0) or not extracted_raw:
        return {"status": "UNVERIFIED", "difference_ratio": None,
                "reported_count": declared, "extracted_raw": extracted_raw,
                "extracted_unique": extracted_unique}
    try:
        ratio = abs(int(declared) - int(extracted_raw)) / int(declared)
    except Exception:
        return {"status": "UNVERIFIED", "difference_ratio": None,
                "reported_count": declared, "extracted_raw": extracted_raw,
                "extracted_unique": extracted_unique}
    return {
        "status": "PARTIAL" if ratio > max_ratio else "OK",
        "difference_ratio": round(ratio, 4),
        "reported_count": int(declared),
        "extracted_raw": int(extracted_raw),
        "extracted_unique": int(extracted_unique),
    }
