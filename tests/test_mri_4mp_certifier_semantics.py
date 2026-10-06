# -*- coding: utf-8 -*-
"""VA-MRI-4MP-E2E-FAILURE-RESOLUTION-001 — Certifier semantics contract (CERT-A..F).

El certificador NO puede derivar PASS del exit code: debe combinar
PROCESS_RESULT + COVERAGE_STATUS + RELEVANT_PENDING_WORK + STOP_REASON +
SOURCE_BLOCKED + EVIDENCE (artifact-based).

CERT-A: exit=0 + CONFIRMED + relevant=0            -> PASS
CERT-B: exit=0 + PARTIAL + relevant>0              -> NO PASS
CERT-C: exit=0 + PARTIAL + relevant=0              -> resolver por contrato (relevante completo)
CERT-D: TIMEOUT                                    -> FAIL/BLOCKED (nunca PASS)
CERT-E: SOURCE_BLOCKED                             -> no convertirse en NOT_FOUND
CERT-F: artefactos insuficientes                   -> UNKNOWN/PARTIAL (nunca PASS por defecto)
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import _mri_4mp_certification_helper as helper


def _m(**kw):
    base = {
        "coverage_status": None,
        "stop_reason_hint": None,
        "relevant_pending_work": None,
        "raw_frontier_remaining": None,
        "relevant_frontier_remaining": None,
        "source_blocked_count": 0,
        "not_found_count": 0,
        "evidence_sufficient": True,
        "recount": None,
    }
    base.update(kw)
    return base


def test_cert_a_confirmed_plus_zero_relevant_is_pass():
    r = helper.classify_marketplace_semantics(
        _m(coverage_status="CONFIRMED", relevant_pending_work=False),
        process_exit_code=0, timed_out=False)
    assert r["STATUS"] == "PASS"


def test_cert_b_partial_with_relevant_pending_is_not_pass():
    r = helper.classify_marketplace_semantics(
        _m(coverage_status="PARTIAL", relevant_pending_work=True),
        process_exit_code=0, timed_out=False)
    assert r["STATUS"] != "PASS"
    assert r["STATUS"] == "PARTIAL"


def test_cert_c_partial_without_relevant_pending_resolves_by_contract():
    r = helper.classify_marketplace_semantics(
        _m(coverage_status="PARTIAL", relevant_pending_work=False),
        process_exit_code=0, timed_out=False)
    # Contrato de terminación certificado: PARTIAL con RELEVANT_PENDING_WORK=0
    # es terminación controlada suficiente del alcance relevante (no decide la palabra PARTIAL).
    assert r["STATUS"] == "PASS"
    assert r.get("qualifier") == "RELEVANT_SCOPE_COMPLETE"


def test_cert_d_timeout_never_pass():
    r = helper.classify_marketplace_semantics(
        _m(coverage_status="BLOCKED"), process_exit_code=1, timed_out=True)
    assert r["STATUS"] in ("FAIL", "BLOCKED")
    assert r["STATUS"] != "PASS"


def test_cert_e_source_blocked_never_converted_to_not_found():
    r = helper.classify_marketplace_semantics(
        _m(coverage_status="BLOCKED", source_blocked_count=7),
        process_exit_code=0, timed_out=False)
    assert r["STATUS"] == "BLOCKED"
    assert r["STATUS"] != "NOT_FOUND"


def test_cert_e_status_never_not_found_for_any_input():
    cases = [
        _m(coverage_status="CONFIRMED", relevant_pending_work=False),
        _m(coverage_status="PARTIAL", relevant_pending_work=True),
        _m(coverage_status="BLOCKED", source_blocked_count=1),
        _m(evidence_sufficient=False),
    ]
    for c in cases:
        r = helper.classify_marketplace_semantics(c, process_exit_code=0, timed_out=False)
        assert r["STATUS"] != "NOT_FOUND"


def test_cert_f_insufficient_artifacts_never_default_pass():
    r = helper.classify_marketplace_semantics(
        _m(evidence_sufficient=False, coverage_status=None, relevant_pending_work=None),
        process_exit_code=0, timed_out=False)
    assert r["STATUS"] in ("UNKNOWN", "PARTIAL")
    assert r["STATUS"] != "PASS"


def test_extraction_reads_nested_run_dir_and_accounts_budget_remainder(tmp_path):
    """Fixture con la estructura REAL observada del golden run (dir anidado + artefactos)."""
    mkt_dir = tmp_path / "falabella"
    run_dir = mkt_dir / "20261006_124152_falabella"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text(json.dumps({
        "run_id": "20261006_124152_falabella", "marketplace": "Falabella",
        "categories": 13,
        "recount": {"RAW_OBSERVATIONS": 323, "DISTINCT_MARKETPLACE_PRODUCT_IDS": 296,
                    "NORMALIZED_OBSERVATIONS": 296, "NICOPOLY_CONFIRMED": 0,
                    "PUBLICATIONS": 0, "MEMBERSHIPS": 0, "BATCHES": 16, "EVENTS": 63},
    }), encoding="utf-8")
    (run_dir / "final_report.md").write_text(
        "# MRI_E2E_FALABELLA\n\nSTOP: PARTIAL (categories: 13, timeouts: 0)\n", encoding="utf-8")
    (run_dir / "taxonomy.json").write_text(json.dumps([
        {"category_name": "Brand Hub", "is_seed_surface": True, "stop_reason": "EXHAUSTION"},
        {"category_name": "Pantalones", "stop_reason": "EXHAUSTION",
         "surface_classification": "COMMERCIAL_CATEGORY", "products_found": 55},
        {"category_name": "Automotriz", "stop_reason": "NOT_VISITED", "category_type": "NON_COMMERCIAL",
         "classification_evidence": ["non-commercial path"], "is_seed_surface": False},
    ]), encoding="utf-8")
    (run_dir / "failures.json").write_text(json.dumps({
        "evidence_notes": [
            "CATEGORY_BUDGET_EXHAUSTED: 0 of 22 discovered facets not visited within operational budget; "
            "deterministic accounting: raw=0, relevant=0, pruned_with_evidence=0 (relevance never assumed)"
        ]
    }), encoding="utf-8")
    (run_dir / "events.jsonl").write_text(
        json.dumps({"action": "RUN_START", "timestamp": "2026-10-06T12:49:05"}) + "\n", encoding="utf-8")

    m = helper.extract_marketplace_metrics(str(mkt_dir))
    assert m["coverage_status"] == "PARTIAL"
    assert m["evidence_sufficient"] is True
    assert m["raw_frontier_remaining"] == 1        # Automotriz (NOT_VISITED) cuenta como RAW
    assert m["relevant_frontier_remaining"] == 0  # pero está podada con evidencia verificable
    assert m["relevant_pending_work"] is False
    r = helper.classify_marketplace_semantics(m, process_exit_code=0, timed_out=False)
    assert r["STATUS"] == "PASS"  # CERT-C: PARTIAL + relevant=0


def test_extraction_missing_artifacts_marks_insufficient(tmp_path):
    mkt_dir = tmp_path / "ripley"
    mkt_dir.mkdir()
    m = helper.extract_marketplace_metrics(str(mkt_dir))
    assert m["evidence_sufficient"] is False
    r = helper.classify_marketplace_semantics(m, process_exit_code=0, timed_out=False)
    assert r["STATUS"] in ("UNKNOWN", "PARTIAL")
