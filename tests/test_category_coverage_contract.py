"""Coverage contract tests (MRI-CATEGORY-COVERAGE-001). FIXTURES only."""
from pathlib import Path

from app.mri_dashboard import coverage as C


def _cats(n=3):
    return {f"c{i}": {"name": f"Cat {i}", "url": f"https://mkt/cat/{i}"} for i in range(n)}


def test_no_historical_cap_is_a_coverage_target():
    # 48/96/240 were technical limits, never totals.
    assert C.PAGE_SENTINEL > 240
    cov = C.new_coverage("run_x", "Ripley", _cats(2))
    assert cov["acceptance"] == C.AUDIT_FAIL  # in progress is never PASS


def test_all_categories_exhausted_is_the_only_path_to_audit_pass():
    cov = C.new_coverage("run_x", "Ripley", _cats(3))
    for i in range(3):
        C.record_category(cov, f"c{i}", pages=12, stop_state="EXHAUSTION", publications=48)
    C.finalize(cov, unique_publications=150)
    assert cov["pages_observed"] == 36
    assert cov["categories_traversed_completely"] == 3
    assert cov["pages_pending"] == 0
    assert cov["termination_condition"] == "ALL_CATEGORIES_EXHAUSTED"
    assert cov["acceptance"] == C.AUDIT_PASS
    assert cov["acceptance_reasons"] == []


def test_blocked_category_forces_audit_fail_even_with_other_categories_complete():
    cov = C.new_coverage("run_x", "Mercado Libre", _cats(2))
    C.record_category(cov, "c0", pages=10, stop_state="EXHAUSTION", publications=40)
    C.record_category(cov, "c1", pages=0, stop_state="SOURCE_BLOCKED", publications=0)
    C.finalize(cov, unique_publications=40)
    assert cov["acceptance"] == C.AUDIT_FAIL
    assert any("bloqueadas" in r for r in cov["acceptance_reasons"])


def test_pending_category_forces_audit_fail():
    cov = C.new_coverage("run_x", "Falabella", _cats(2))
    C.record_category(cov, "c0", pages=2, stop_state="EXHAUSTION", publications=48)
    C.finalize(cov)
    assert cov["acceptance"] == C.AUDIT_FAIL
    assert cov["pages_pending"] is None
    assert any("sin recorrer" in r for r in cov["acceptance_reasons"])


def test_checkpoint_roundtrip_allows_resume():
    root = Path("evidence_local_validation/acquisition_truth/_cov_checkpoint_test")
    root.mkdir(parents=True, exist_ok=True)
    cov = C.new_coverage("run_resume", "Ripley", _cats(1))
    C.record_category(cov, "c0", pages=5, stop_state="EXHAUSTION", publications=240)
    path = C.save_checkpoint(root, cov)
    assert path and Path(path).exists()
    loaded = C.load_checkpoint(root, "run_resume")
    assert loaded is not None
    assert loaded["categories"]["c0"]["status"] == "COMPLETE"
    assert loaded["categories"]["c0"]["pages_observed"] == 5
    assert loaded["pages_observed"] == 5
