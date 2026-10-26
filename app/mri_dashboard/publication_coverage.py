"""Publication coverage: master catalog vs observed marketplace listings.

Marketplace-agnostic core with explicit per-channel inputs (stock + channel
price from the master). Never claims coverage when the acquisition run is not
complete: expected-but-unmatched products are UNVERIFIED, not "missing".
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

STOP = {
    "nicopoly", "mujer", "hombre", "unisex", "negro", "blanco", "cafe", "café",
    "gris", "azul", "rojo", "verde", "beige", "oliva", "burdeo", "rosado",
    "celeste", "mocca", "khaki", "marino", "talla", "color", "de", "la", "las",
    "los", "con", "sin", "para", "por", "the", "and",
}


def _norm(text) -> str:
    s = unicodedata.normalize("NFKD", str(text or "")).encode(
        "ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _tokens(text) -> set:
    return {t for t in _norm(text).split() if len(t) >= 3 and t not in STOP}


def _master_expected(master_items, marketplace):
    """Expected universe for one channel: stock > 0 and channel price > 0."""
    key = marketplace.lower()
    expected, zero, unknown, no_price = [], [], [], []
    for item in master_items or []:
        stock = item.get("stock", -1)
        price = float((item.get("prices") or {}).get(key) or 0)
        if stock == 0:
            zero.append(item)
        elif stock < 0:
            unknown.append(item)
        elif price <= 0:
            no_price.append(item)
        else:
            expected.append(item)
    return expected, zero, unknown, no_price


def _resolve(obs, expected, sku_index):
    """Deterministic match: exact internal SKU, then unique normalized title."""
    text = " ".join(str(obs.get(k) or "") for k in
                    ("producto_id", "sku", "producto_nombre", "canonical_url"))
    for sku, item in sku_index.items():
        if len(sku) >= 4 and re.search(r"(?<![A-Za-z0-9])" + re.escape(sku)
                                      + r"(?![A-Za-z0-9])", text, re.I):
            return item, "SKU_EXACT"
    ot = _tokens(obs.get("producto_nombre"))
    if len(ot) < 2:
        return None, None
    scores = []
    for item in expected:
        mt = _tokens(item.get("product_name"))
        if len(mt) < 2:
            continue
        union = ot | mt
        score = len(ot & mt) / len(union) if union else 0.0
        scores.append((score, item))
    scores.sort(key=lambda x: x[0], reverse=True)
    if not scores or scores[0][0] < 0.85:
        return None, None
    if len(scores) > 1 and scores[1][0] >= scores[0][0] - 0.05:
        return None, None                       # ambiguous: never invent a match
    return scores[0][1], "TITLE_UNIQUE"


def build_report(marketplace, observations, master_items, *, run_id=None,
                 run_complete=True, catalog_available=True):
    expected, zero, unknown, no_price = _master_expected(master_items, marketplace)
    sku_index = {str(i.get("sku_master")).lower(): i for i in expected
                 if i.get("sku_master")}
    matched, missing, extra = [], [], []
    matched_skus = set()
    for obs in observations or []:
        item, method = _resolve(obs, expected, sku_index)
        if item is None:
            extra.append({
                "observed_id": obs.get("producto_id") or obs.get("sku"),
                "title": obs.get("producto_nombre"),
                "url": obs.get("canonical_url") or obs.get("url"),
                "category": obs.get("real_category"),
                "reason": "SIN_MATCH_UNICO_EN_MAESTRO",
            })
            continue
        sku = str(item.get("sku_master"))
        if sku in matched_skus:
            continue
        matched_skus.add(sku)
        matched.append({
            "sku_master": sku,
            "name": item.get("product_name"),
            "method": method,
            "observed_id": obs.get("producto_id") or obs.get("sku"),
            "url": obs.get("canonical_url") or obs.get("url"),
            "category": obs.get("real_category"),
        })
    for item in expected:
        sku = str(item.get("sku_master"))
        if sku in matched_skus:
            continue
        missing.append({
            "sku_master": sku,
            "name": item.get("product_name"),
            "stock": item.get("stock"),
            "price_channel": (item.get("prices") or {}).get(marketplace.lower()),
        })
    coverage = {
        "published_verified": len(matched) if run_complete else 0,
        "missing": len(missing) if run_complete else 0,
        "unverified": 0 if run_complete else len(expected),
        "extra_not_in_master": len(extra),
        "ambiguous": sum(1 for e in extra if "match" in e["reason"].lower()),
    }
    return {
        "marketplace": marketplace,
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(),
        "catalog_available": catalog_available,
        "run_complete": run_complete,
        "master": {
            "total": len(master_items or []),
            "expected": len(expected),
            "discarded_no_stock": len(zero),
            "unverified_stock": len(unknown),
            "not_expected_channel": len(no_price),
        },
        "coverage": coverage,
        "published": matched,
        "missing": missing,
        "extra": extra[:500],
        "discarded_no_stock": [
            {"sku_master": i.get("sku_master"),
             "name": i.get("product_name")} for i in zero[:500]],
    }
