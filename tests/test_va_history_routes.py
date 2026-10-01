import pytest
import sqlite3
import uuid
import os
from datetime import datetime

# Tests for VA-HISTORY-ROUTES-TAXONOMY-READINESS-001

def setup_test_db(db_path=":memory:"):
    conn = sqlite3.connect(db_path)
    from app.storage.mri_foundation import init_additive_schema
    init_additive_schema(conn)
    return conn

def test_red_publication_history_preserved():
    """
    If a publication is updated with a new URL or position, its history MUST be preserved.
    """
    conn = setup_test_db()
    
    # 1. First run
    run_1 = "run_history_001"
    pub_id = "pub_hist_001"
    conn.cursor().execute("INSERT INTO mri_runs (run_id, started_at, marketplace, brand, execution_mode, truth_model_version, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (run_1, "2026-10-01", "Ripley", "Nicopoly", "LIVE", "1.0", "VERIFIED", "2026-10-01"))
    
    from app.storage.mri_foundation import persist_identity
    persist_identity(
        conn,
        product_id="prod_01",
        publication_id=pub_id,
        brand="Nicopoly",
        marketplace="Ripley",
        marketplace_product_id="R_01",
        canonical_url="https://ripley.cl/product-old",
        status="OBSERVED",
        variants=[],
        observed_at="2026-10-01T10:00:00",
        run_id=run_1,
        position=10,
        surface="Category Browse"
    )
    
    # 2. Second run - URL changes
    run_2 = "run_history_002"
    conn.cursor().execute("INSERT INTO mri_runs (run_id, started_at, marketplace, brand, execution_mode, truth_model_version, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (run_2, "2026-10-02", "Ripley", "Nicopoly", "LIVE", "1.0", "VERIFIED", "2026-10-02"))
    
    persist_identity(
        conn,
        product_id="prod_01",
        publication_id=pub_id,
        brand="Nicopoly",
        marketplace="Ripley",
        marketplace_product_id="R_01",
        canonical_url="https://ripley.cl/product-new",
        status="OBSERVED",
        variants=[],
        observed_at="2026-10-02T10:00:00",
        run_id=run_2,
        position=5,
        surface="Brand Hub"
    )
    
    # The current state should show the new URL
    cur = conn.cursor()
    cur.execute("SELECT canonical_url FROM mri_publications WHERE publication_id=?", (pub_id,))
    assert cur.fetchone()[0] == "https://ripley.cl/product-new"
    
    # The history MUST show the old URL for run_1
    cur.execute("SELECT canonical_url, position, surface FROM mri_historical_publications WHERE publication_id=? AND run_id=?", (pub_id, run_1))
    history_row = cur.fetchone()
    
    assert history_row is not None, "History for run_1 was destroyed!"
    assert history_row[0] == "https://ripley.cl/product-old"
    assert history_row[1] == 10
    
def test_red_category_history_preserved():
    """
    If a category route changes, history MUST be preserved.
    """
    conn = setup_test_db()
    run_1 = "run_cat_001"
    cat_id = "cat_001"
    
    conn.cursor().execute("INSERT INTO mri_runs (run_id, started_at, marketplace, brand, execution_mode, truth_model_version, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (run_1, "2026-10-01", "Ripley", "Nicopoly", "LIVE", "1.0", "VERIFIED", "2026-10-01"))
    
    from app.storage.mri_foundation import assign_categories
    assign_categories(
        conn,
        publication_id="pub_hist_001",
        categories=[{
            "category_id": cat_id,
            "category_name": "Poleras",
            "marketplace": "Ripley",
            "canonical_url": "https://ripley.cl/poleras-old",
            "run_id": run_1
        }],
        observed_at="2026-10-01T10:00:00"
    )
    
    # Run 2: URL changes
    run_2 = "run_cat_002"
    conn.cursor().execute("INSERT INTO mri_runs (run_id, started_at, marketplace, brand, execution_mode, truth_model_version, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (run_2, "2026-10-02", "Ripley", "Nicopoly", "LIVE", "1.0", "VERIFIED", "2026-10-02"))
    
    assign_categories(
        conn,
        publication_id="pub_hist_001",
        categories=[{
            "category_id": cat_id,
            "category_name": "Poleras",
            "marketplace": "Ripley",
            "canonical_url": "https://ripley.cl/poleras-new",
            "run_id": run_2
        }],
        observed_at="2026-10-02T10:00:00"
    )
    
    cur = conn.cursor()
    cur.execute("SELECT canonical_url FROM mri_categories WHERE category_id=?", (cat_id,))
    assert cur.fetchone()[0] == "https://ripley.cl/poleras-new"
    
    cur.execute("SELECT canonical_url FROM mri_historical_categories WHERE category_id=? AND run_id=?", (cat_id, run_1))
    history_row = cur.fetchone()
    
    assert history_row is not None, "Category history for run_1 was destroyed!"
    assert history_row[0] == "https://ripley.cl/poleras-old"

def test_red_publication_category_history():
    """
    If a product moves to a new category, its previous category mapping for that run MUST be preserved.
    """
    conn = setup_test_db()
    # Need to check `mri_historical_publication_categories`
    pass
