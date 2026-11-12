"""Snapshot + diff contract (MRI-adapted, comparable-only)."""
import json
import uuid
from pathlib import Path

import app.mri_dashboard.falabella_snapshots as S


def _dir():
    p = Path("evidence_local_validation/acquisition_truth/_snap_" + uuid.uuid4().hex[:8])
    p.mkdir(parents=True, exist_ok=True)
    return p


def _obs(pid, skus):
    """skus: {sku: price}"""
    return {"product_id": pid,
            "skus": {s: {"price": p} for s, p in skus.items()},
            "categories": ["Poleras Mujer"],
            "surfaces": ["brand:NICOPOLY"],
            "url": f"https://www.falabella.com/falabella-cl/product/{pid}/x",
            "seller_name": "Nicopoly"}


def _audit(aux, surfaces=None):
    return {"_aux_dir": str(aux), "complete": True, "build_id": "b1",
            "surfaces": surfaces or [{"surface": "brand:NICOPOLY",
                                      "terminal": "EXHAUSTION",
                                      "expected_cards": 2, "cards": 2,
                                      "unique_product_ids": 2,
                                      "unique_keys": 3,
                                      "pages_traversed": 1}]}


def test_snapshot_is_immutable_and_counts_keys():
    aux = _dir()
    a = _audit(aux)
    p1, s1 = S.capture(a, [_obs("P1", {"S1": 1000, "S2": 1200}),
                           _obs("P2", {"S3": 500})])
    p2, s2 = S.capture(a, [_obs("P1", {"S1": 1000, "S2": 1200}),
                           _obs("P2", {"S3": 500})])
    assert p1.exists() and p2.exists() and p1 != p2       # never overwrites
    assert s1["unique_products"] == 2
    assert s1["unique_keys"] == 3
    assert s1["coverage_fingerprint"] == s2["coverage_fingerprint"]
    assert s1["build_id"] == "b1"


def test_diff_detects_add_remove_and_price_change():
    aux = _dir()
    a = _audit(aux)
    _, s1 = S.capture(a, [_obs("P1", {"S1": 1000, "S2": 1200}),
                          _obs("P2", {"S3": 500})])
    p2, s2 = S.capture(a, [_obs("P1", {"S1": 1100, "S2": 1200}),
                           _obs("P3", {"S4": 600})])
    d = S.compare_and_write(aux, p2, s2)
    assert d["comparable"] is True
    assert d["products"]["added"] == ["P3"]
    assert d["products"]["removed"] == ["P2"]
    assert len(d["products"]["price_changes"]) == 1
    assert d["products"]["price_changes"][0]["delta_clp"] == 100
    assert d["skus"]["added"] == 1 and d["skus"]["removed"] == 1
    assert d["skus"]["price_changes"] == 1
    assert d["coverage_changed"] is False


def test_same_data_is_idempotent():
    aux = _dir()
    a = _audit(aux)
    obs = [_obs("P1", {"S1": 1000}), _obs("P2", {"S2": 2000})]
    _, s1 = S.capture(a, obs)
    p2, s2 = S.capture(a, obs)
    d = S.compare_and_write(aux, p2, s2)
    assert d["products"]["added"] == [] and d["products"]["removed"] == []
    assert d["products"]["price_changes"] == []
    assert d["skus"]["added"] == 0 and d["skus"]["removed"] == 0


def test_different_coverage_is_not_compared():
    aux = _dir()
    a1 = _audit(aux)
    _, s1 = S.capture(a1, [_obs("P1", {"S1": 1000})])
    a2 = _audit(aux, [{"surface": "brand:NICOPOLY", "terminal": "EXHAUSTION",
                       "expected_cards": 2, "cards": 2, "unique_product_ids": 2,
                       "unique_keys": 2, "pages_traversed": 1},
                      {"surface": "category:cat850040", "terminal": "EXHAUSTION",
                       "expected_cards": 1, "cards": 1, "unique_product_ids": 1,
                       "unique_keys": 1, "pages_traversed": 1}])
    p2, s2 = S.capture(a2, [_obs("P1", {"S1": 1000})])
    d = S.compare_and_write(aux, p2, s2)
    assert d["comparable"] is False
    assert d["reason"] == "SIN_BASELINE_COMPARABLE"
