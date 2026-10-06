"""VA-FINAL-RESOLUTION-LOOP-001 - Stop semantics contract (RAW vs RELEVANT frontier).

Mission contract (cases):
  A) raw=0 & relevant=0                      -> execution complete (may be CONFIRMED).
  B) raw>0, every remaining node verifiably pruned -> RELEVANT=0: controlled completion
     of the relevant scope; a pruned raw frontier alone never forces an incomplete verdict.
  C) relevant>0                              -> never certifies complete coverage.
  D) WAF/timeout blocks relevance resolution -> BLOCKED / incomplete per existing contract;
     never CONFIRMED; never NOT_FOUND (SOURCE_BLOCKED != NOT_FOUND).
  E) infinite/repetitive frontier            -> bounded stop: every unvisited node reaches
     a terminal classification; nothing remains QUEUED/NOT_VISITED forever.

All tests are PURE (no network, no DB, no scraper instantiation) and only call PRODUCTION code.
"""
import pytest

from app.mri_autonomous.category_discoverer import frontier_relevance_accounting
from app.mri_autonomous.autonomous_pipeline import (
    classify_unvisited_terminal,
    decide_coverage_status,
)


def _hub(stop="EXHAUSTION"):
    return {"category_name": "Brand Hub", "is_seed_surface": True, "stop_reason": stop,
            "pages_traversed": 3, "coverage_status": "CONFIRMED", "products_found": 50}


def _certified(name="Vestidos"):
    return {"category_name": name, "stop_reason": "EXHAUSTION", "coverage_status": "CONFIRMED",
            "surface_classification": "COMMERCIAL_CATEGORY", "node_status": "CERTIFIED",
            "products_found": 5, "is_seed_surface": False}


def _pruned(name="Automotriz", cls="NON_COMMERCIAL", evidence=("non-commercial path",)):
    return {"category_name": name, "stop_reason": "NOT_VISITED", "category_type": cls,
            "classification_evidence": list(evidence), "is_seed_surface": False}


def _unresolved_raw(name="Zapatos"):
    return {"category_name": name, "stop_reason": "NOT_VISITED",
            "surface_classification": "COMMERCIAL_CATEGORY",
            "classification_evidence": ["deep-path:1-segment"], "is_seed_surface": False}


def _decide(cats, **kw):
    defaults = dict(resume_override=None, controlled_stop=False,
                    any_discovered_categories=bool(cats), base_notes_text="")
    defaults.update(kw)
    return decide_coverage_status(cats, **defaults)


# ---------- CASE A: raw=0 & relevant=0 -> complete ----------
def test_case_a_raw_0_relevant_0_execution_complete():
    cats = [_hub(), _certified()]
    acc = frontier_relevance_accounting(cats)
    assert acc["raw_frontier_remaining"] == 0
    assert acc["relevant_frontier_remaining"] == 0
    assert acc["relevant_pending_work"] is False
    status, notes, _ = _decide(cats)
    assert status == "CONFIRMED"
    assert not any("COVERAGE_PARTIAL" in n for n in notes)


# ---------- CASE B: raw>0 fully pruned -> not incomplete ----------
def test_case_b_raw_pruned_relevant_0_is_sufficient_for_relevant_scope():
    cats = [_hub(), _certified(), _pruned()]
    acc = frontier_relevance_accounting(cats)
    assert acc["raw_frontier_remaining"] == 1
    assert acc["relevant_frontier_remaining"] == 0
    assert acc["relevant_pending_work"] is False
    status, notes, _ = _decide(cats)
    assert status == "CONFIRMED"  # verified pruning alone must not force "incomplete census"
    assert not any("COVERAGE_PARTIAL" in n for n in notes)
    assert any("FRONTIER_RAW_PRUNED" in n for n in notes)


def test_case_b_without_evidence_is_irrelevant_by_default():
    cats = [_hub(), _certified(), _pruned(evidence=())]
    acc = frontier_relevance_accounting(cats)
    assert acc["raw_frontier_remaining"] == 1
    assert acc["relevant_frontier_remaining"] == 0  # DENY BY DEFAULT: without target_brand_present, it is irrelevant
    assert acc["relevant_pending_work"] is False


# ---------- CASE C: relevant>0 -> never complete ----------
def test_case_c_relevant_pending_never_certifies_complete():
    unresolved_relevant = _unresolved_raw()
    unresolved_relevant["target_brand_present"] = 1
    cats = [_hub(), _certified(), unresolved_relevant]
    acc = frontier_relevance_accounting(cats)
    assert acc["relevant_frontier_remaining"] == 1
    assert acc["relevant_pending_work"] is True
    status, notes, _ = _decide(cats)
    assert status == "PARTIAL"
    assert status != "CONFIRMED"
    assert any("relevant frontier remaining" in n for n in notes)


# ---------- CASE D: blocked/timeout -> incomplete; never NOT_FOUND ----------
def test_case_d_blocked_relevance_undetermined_is_not_found_never_substituted():
    status, notes, acc = _decide([], any_discovered_categories=False,
                                 base_notes_text="WAF BLOCKED during hub acquisition")
    assert status == "BLOCKED"
    assert status != "NOT_FOUND"
    assert status != "CONFIRMED"


def test_case_d_blocked_hub_is_incomplete_not_not_found():
    status, _, _ = _decide([{"category_name": "Brand Hub", "is_seed_surface": True,
                             "stop_reason": "BLOCKED", "pages_traversed": 0,
                             "products_found": 0}])
    assert status in ("PARTIAL", "BLOCKED")
    assert status != "NOT_FOUND"


def test_case_d_timeout_isolated_category_prevents_complete_claim():
    cats = [_hub(), _certified(),
            {"category_name": "Sets", "stop_reason": "CATEGORY_BUDGET_EXCEEDED",
             "coverage_status": "BLOCKED", "products_found": 0, "is_seed_surface": False}]
    status, notes, _ = _decide(cats)
    assert status in ("PARTIAL", "BLOCKED")
    assert status != "NOT_FOUND"
    assert any("unresolved blocked" in n for n in notes)


# ---------- CASE E: bounded stop ----------
def test_case_e_bounded_stop_classifies_every_unvisited_node_terminal():
    pile = [
        _pruned("Automotriz"),
        _pruned("Chanel", cls="BRAND_NAVIGATION", evidence=("competitor brand showcase",)),
        _unresolved_raw("Zapatos"),
        _unresolved_raw("Sets"),
    ]
    for cat in pile:
        classify_unvisited_terminal(cat)
    leftovers = [c for c in pile if c.get("stop_reason") in (None, "QUEUED", "NOT_VISITED")]
    assert leftovers == []  # bounded: no pending remains
    assert pile[0]["stop_reason"] == "NON_COMMERCIAL" and pile[0]["coverage_status"] == "TERMINAL"
    assert pile[1]["stop_reason"] == "BRAND_NAVIGATION" and pile[1]["coverage_status"] == "TERMINAL"
    assert pile[2]["stop_reason"] == "OPERATIONAL_BATCH_LIMIT_REACHED" and pile[2]["coverage_status"] == "EXHAUSTED"
    # idempotent: re-application cannot loop or mutate further
    snapshot = [dict(c) for c in pile]
    for cat in pile:
        classify_unvisited_terminal(cat)
    assert pile == snapshot


def test_case_e_controlled_stop_partial_and_accounted():
    cats = [_hub(), _certified(), _pruned()]
    for cat in cats:
        if (cat.get("stop_reason") or "QUEUED") in (None, "QUEUED", "NOT_VISITED"):
            classify_unvisited_terminal(cat)
    status, notes, acc = _decide(cats, controlled_stop=True)
    assert status == "PARTIAL"
    assert acc["raw_frontier_remaining"] == 0  # terminals are accounted, not pending
    assert any("CONTROLLED_STOP" in n for n in notes)


# ---------- Cross-cutting: seed surface is never pending frontier ----------
def test_accounting_excludes_seed_surface_from_raw():
    unresolved_relevant = _unresolved_raw()
    unresolved_relevant["target_brand_present"] = 1
    cats = [_hub(stop="PAGINATION_PARAM_NOT_FOUND"), unresolved_relevant]
    acc = frontier_relevance_accounting(cats)
    assert acc["raw_frontier_remaining"] == 1
    assert acc["relevant_frontier_names"] == ["Zapatos"]
