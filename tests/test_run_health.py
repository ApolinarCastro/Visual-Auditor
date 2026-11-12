"""Operational health/census are derived from real acquisition evidence."""
from app.mri_dashboard.run_health import build_global_coverage, build_health, build_source_health


def test_health_exposes_errors_and_source_state():
    events = [
        {"marketplace": "Mercado Libre", "state": "FOUND", "duration_ms": 100},
        {"marketplace": "Mercado Libre", "state": "PARTIAL", "duration_ms": 200},
    ]
    h = build_health(events)
    assert h["events"] == 2 and h["errors"] == 1
    assert h["status"] == "DEGRADED"
    src = build_source_health(events)
    assert src["Mercado Libre"]["status"] == "DEGRADED"
    assert src["Mercado Libre"]["consecutive_failures"] == 1


def test_global_coverage_uses_real_counts():
    cov = build_global_coverage(
        {"categories": [{"name": "A"}, {"name": "B"}]},
        [{"acquisition_state": "FOUND", "products_observed_raw": 10},
         {"acquisition_state": "FOUND", "products_observed_raw": 5}],
        [{"observed_sku": "1"}, {"observed_sku": "2"}, {"observed_sku": "2"}],
        {"A": 10, "B": 5})
    assert cov["categories_discovered"] == 2
    assert cov["categories_complete"] == 2
    assert cov["observations_raw"] == 15
    assert cov["unique_publications"] == 2
    assert cov["coverage_vs_declared_pct"] == 13.33
    assert cov["coverage_status"] == "COMPLETE"
