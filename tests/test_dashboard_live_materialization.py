import pytest
import sqlite3
from datetime import datetime
from app.dashboard.mri_read_model import MRIReadModel

def test_categories_read_model_uses_materialized_db_records():
    """
    RED TEST:
    Verifies that MRIReadModel.get_categories() reads active commercial records
    from SQLite (mri_categories, mri_publication_categories, mri_publications)
    instead of returning a frozen research census stub with
    RESEARCH_SUMMARY_NOT_MATERIALIZED and TopN = N/A.
    """
    rm = MRIReadModel()
    
    # Dynamically find the latest observation timestamp and position in DB
    conn = rm.get_read_only_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT max(p.observed_at) as latest_obs,
               count(p.position) as total_positions
        FROM mri_publications p
        WHERE p.run_id != 'run_golden_shadow_001' AND p.run_id NOT LIKE '%test%'
    """)
    db_stats = dict(cur.fetchone())
    conn.close()
    
    assert db_stats["total_positions"] > 0, "Prerequisite: database must contain publications with positions"
    latest_db_obs_date = db_stats["latest_obs"][:10]  # e.g. '2026-09-30'
    
    cat_result = rm.get_categories()
    items = cat_result.get("items", [])
    assert len(items) > 0, "Categories view must return items"
    
    # In RED state, this fails: all items have 'RESEARCH_SUMMARY_NOT_MATERIALIZED'
    # and last_verified starting with '2026-09-21' instead of latest_db_obs_date
    evidence_states = [c.get("evidence_state") for c in items]
    assert "RESEARCH_SUMMARY_NOT_MATERIALIZED" not in evidence_states, (
        f"Found stale RESEARCH_SUMMARY_NOT_MATERIALIZED in categories view: {evidence_states[:3]}"
    )
    
    # TopN must be calculated from observed positions, not 'N/A (NOT MATERIALIZED)'
    top30_vals = [c.get("top30_count") for c in items]
    assert any(val != "N/A (NOT MATERIALIZED)" for val in top30_vals), (
        f"All categories have top30_count as 'N/A (NOT MATERIALIZED)' despite valid positions in DB"
    )
    
    # Timestamps must match the latest evidence in DB, not 2026-09-21
    timestamps = [c.get("last_verified") for c in items if c.get("last_verified")]
    assert any(ts.startswith(latest_db_obs_date) for ts in timestamps), (
        f"Expected category timestamps to reflect latest DB observation date {latest_db_obs_date}, but got {timestamps[:3]}"
    )

def test_legacy_comparison_uses_dynamic_mri_evidence():
    """
    RED TEST:
    Verifies that MRIReadModel.get_legacy_comparison() reflects active commercial
    records from mri_publications rather than frozen 2026-09-21 research aggregates.
    """
    rm = MRIReadModel()
    
    conn = rm.get_read_only_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT max(p.observed_at) as latest_obs
        FROM mri_publications p
        WHERE p.run_id != 'run_golden_shadow_001' AND p.run_id NOT LIKE '%test%'
    """)
    latest_obs = cur.fetchone()["latest_obs"]
    conn.close()
    
    latest_date = latest_obs[:10]
    comp_result = rm.get_legacy_comparison()
    comparisons = comp_result.get("comparisons", [])
    assert len(comparisons) > 0, "Legacy comparison must return entries"
    
    # Timestamps should reflect current evidence date, not stale 2026-09-21
    dates = [c.get("last_observed", "")[:10] for c in comparisons]
    assert any(d == latest_date for d in dates), (
        f"Expected legacy comparison to reflect latest observation date {latest_date}, but got {dates}"
    )
