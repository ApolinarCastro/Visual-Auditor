"""G3: declared count counts positions, not unique publication ids."""
from app.mri_dashboard.observation_reconciliation import reconcile_declared


def test_duplicate_positions_do_not_fail_g3():
    # 199 declared positions, 199 extracted, 194 unique ids (5 repeats).
    result = reconcile_declared(199, 199, 194)
    assert result["status"] == "OK"
    assert result["extracted_raw"] == 199
    assert result["extracted_unique"] == 194


def test_real_missing_positions_still_fail():
    result = reconcile_declared(199, 194, 194)
    assert result["status"] == "PARTIAL"
    assert result["difference_ratio"] > 0.02


def test_missing_declared_is_unverified():
    assert reconcile_declared(None, 10, 10)["status"] == "UNVERIFIED"
