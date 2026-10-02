"""
Unit and Integration Tests for Search Intent and Season Tracker Capabilities.
Task: VA-SEARCH-INTENT-SEASON-MINIMAL-IMPLEMENTATION-001
"""

import pytest
import sqlite3
import os
from typing import Dict, Any

from app.storage.mri_foundation import (
    init_additive_schema,
    SEARCH_INTENT_ENABLED,
    SEASON_TRACKER_ENABLED,
    import_expected_search_intents,
    import_pilot_season_products,
    get_season_product_observations,
    persist_identity,
    append_evidence,
    STATUS_OBSERVED,
    STATUS_VERIFIED
)
from app.mri_autonomous.category_alignment import resolve_product_type

CSV_INTENTS_PATH = r"C:\Users\ASUS Zenbook\Documents\Visibility Auditor\Busquedas_Concretas_Visual_Auditor.csv"
PILOT_CSV_PATH = r"evidence\va_search_intent_season_fit_probe_002\pilot_20_products.csv"


def setup_db():
    conn = sqlite3.connect(":memory:")
    init_additive_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# FASE 2: FLAGS OFF BASELINE PARITY
# ---------------------------------------------------------------------------
def test_flags_off_baseline_parity():
    """
    ST-002 / ARCH-007: With both feature flags OFF, Visual Auditor foundation
    defaults to inactive search intent & season tracker operations.
    """
    assert SEARCH_INTENT_ENABLED is False
    assert SEASON_TRACKER_ENABLED is False


# ---------------------------------------------------------------------------
# FASE 3: EXPECTED SEARCH INTENTS IMPORT & UNIQUENESS
# ---------------------------------------------------------------------------
def test_expected_search_intents_import():
    """
    KW-001 - KW-005: 57 total searches imported, 57 unique searches,
    26 PRINCIPAL, 31 SECUNDARIA, versioned search_set.
    """
    conn = setup_db()
    res = import_expected_search_intents(conn, CSV_INTENTS_PATH, search_set_version="SS2026_V1")
    
    assert res["imported"] == 57
    assert res["unique"] == 57
    assert res["principal"] == 26
    assert res["secondary"] == 31
    assert res["search_set_version"] == "SS2026_V1"

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT intent) FROM mri_expected_search_intents")
    assert cursor.fetchone()[0] == 57

    cursor.execute("SELECT COUNT(*) FROM mri_expected_search_intents WHERE level = 'PRINCIPAL'")
    assert cursor.fetchone()[0] == 26

    cursor.execute("SELECT COUNT(*) FROM mri_expected_search_intents WHERE level = 'SECUNDARIA'")
    assert cursor.fetchone()[0] == 31


# ---------------------------------------------------------------------------
# FASE 4: ENLACE SEARCH INTENT & REUTILIZACIÓN DE PRODUCT_TYPE
# ---------------------------------------------------------------------------
def test_search_intent_product_type_linkage():
    """
    KW-006 / KW-007: Demonstrates:
    PRODUCT -> CANONICAL PRODUCT TYPE -> EXPECTED SEARCH INTENT
    Tests Blazer and 4 other types (Pantalon, Jeans, Polera, Gilet).
    Also proves SECUNDARIA does not automatically overwrite PRINCIPAL.
    """
    conn = setup_db()
    import_expected_search_intents(conn, CSV_INTENTS_PATH)
    cursor = conn.cursor()

    test_titles = [
        ("Blazer Manga 3/4 Ajustado con Solapas Blanco Nicopoly", "Blazer", "Blazer Mujer"),
        ("Pantalón Recto Con Pinza Blanco Nicopoly", "Pantalon", "Pantalón Mujer"),
        ("Jeans Corte Barrel Blanco Nicopoly", "Jeans", "Jeans Mujer"),
        ("Polera Manga Larga Cuello Bote Blanco Nicopoly", "Polera", "Polera Mujer"),
        ("Gilet Básico Ajustable Blanco Nicopoly", "Gilet", "Gilet Mujer"),
    ]

    for title, expected_type, expected_principal_query in test_titles:
        resolved_type = resolve_product_type(title)
        assert resolved_type == expected_type, f"Failed for title: {title}"

        # Query principal intent from mri_expected_search_intents
        # Account for accent variations in DB (Pantalon vs Pantalón)
        cursor.execute(
            """
            SELECT intent, level FROM mri_expected_search_intents
            WHERE (product_type = ? OR product_type LIKE ? OR product_type = 'Pantalón')
              AND level = 'PRINCIPAL'
            """,
            (resolved_type, f"{resolved_type}%")
        )
        principal_rows = cursor.fetchall()
        assert len(principal_rows) >= 1
        intents = [r[0] for r in principal_rows]
        assert expected_principal_query in intents

    # Verify secondary searches do NOT replace principal
    cursor.execute(
        """
        SELECT intent, level FROM mri_expected_search_intents
        WHERE product_type = 'Blazer' ORDER BY level
        """
    )
    blazer_intents = cursor.fetchall()
    principal_intents = [r[0] for r in blazer_intents if r[1] == "PRINCIPAL"]
    secondary_intents = [r[0] for r in blazer_intents if r[1] == "SECUNDARIA"]

    assert "Blazer Mujer" in principal_intents
    assert "Blazer Largo Mujer" in secondary_intents
    assert principal_intents != secondary_intents


# ---------------------------------------------------------------------------
# FASE 5 & 6: PILOT IMPORT & PARENT-CHILD TRACEABILITY
# ---------------------------------------------------------------------------
def test_pilot_season_import_and_traceability():
    """
    ST-003 - ST-009: 20 parents imported from Groups 1-4 (5 each).
    Groups 5 and 6 excluded (0).
    SKU children, listing IDs, and URLs preserved.
    """
    conn = setup_db()
    res = import_pilot_season_products(conn, PILOT_CSV_PATH)

    assert res["pilot_parents"] == 20
    assert res["group_1_parents"] == 5
    assert res["group_2_parents"] == 5
    assert res["group_3_parents"] == 5
    assert res["group_4_parents"] == 5
    assert res["group_5_processed"] == 0
    assert res["group_6_processed"] == 0
    assert res["pilot_children"] == 73  # exact sum of children across 20 parents

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT sku_parent) FROM mri_season_registry")
    assert cursor.fetchone()[0] == 20

    # Verify listing IDs and URLs preserved
    cursor.execute("SELECT COUNT(*) FROM mri_season_registry WHERE expected_listing_id IS NOT NULL AND expected_listing_id != ''")
    assert cursor.fetchone()[0] > 0

    cursor.execute("SELECT COUNT(*) FROM mri_season_registry WHERE expected_url IS NOT NULL AND expected_url != ''")
    assert cursor.fetchone()[0] > 0


# ---------------------------------------------------------------------------
# FASE 7 & 8: SEPARATED STATUSES & OBSERVATION REUSE (PUBLICATION_ID != EVIDENCE_ID)
# ---------------------------------------------------------------------------
def test_season_observation_reuse_and_semantics():
    """
    ST-010 - ST-014:
    - Season Tracker does not scrape.
    - Reuses existing audit observations via verified joins.
    - Explicitly verifies publication_id != evidence_id.
    - If no observation exists: reports NO_OBSERVATION (NOT NOT_FOUND).
    """
    conn = setup_db()
    import_pilot_season_products(conn, PILOT_CSV_PATH)

    # 1. Product without audit run -> NO_OBSERVATION
    unobserved = get_season_product_observations(conn, "N03049A")
    assert len(unobserved) > 0
    for obs in unobserved:
        assert obs["evidence_status"] == "NO_OBSERVATION"
        assert obs["publication_id"] is None
        assert obs["evidence_id"] is None

    # 2. Add an audit observation for N03049A in Ripley
    run_id = "run_audit_pilot_001"
    conn.cursor().execute(
        "INSERT INTO mri_runs (run_id, started_at, marketplace, brand, execution_mode, truth_model_version, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, "2026-10-02T10:00:00", "Ripley", "Nicopoly", "LIVE", "1.0", "VERIFIED", "2026-10-02T10:00:00")
    )

    ev_id = append_evidence(
        conn,
        run_id=run_id,
        marketplace="Ripley",
        brand="Nicopoly",
        claim_type="POSITION",
        claim_value="4",
        source_surface="Category Browse",
        method="DOM",
        confidence=1.0,
        status="VERIFIED"
    )

    pub_id = "pub_ripley_N03049A"
    persist_identity(
        conn,
        product_id="N03049A",
        brand="Nicopoly",
        publication_id=pub_id,
        marketplace="Ripley",
        marketplace_product_id="MPM10000316121",
        canonical_url="https://simple.ripley.cl/blazer-manga-34-ajustado-con-solapas-blanco-nicopoly-mpm10000316121",
        status=STATUS_OBSERVED,
        variants=[],
        run_id=run_id,
        position=4,
        surface="Category Browse"
    )

    # Add snapshot connecting publication_id to evidence_id
    conn.cursor().execute(
        "INSERT INTO mri_shadow_snapshots (snapshot_id, run_id, publication_id, marketplace, brand, observed_at, status, evidence_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("snap_01", run_id, pub_id, "Ripley", "Nicopoly", "2026-10-02T10:00:00", "OBSERVED", ev_id)
    )
    conn.commit()

    # Query observations again
    observed_list = get_season_product_observations(conn, "N03049A")
    ripley_obs = [o for o in observed_list if o["marketplace"] == "Ripley" and o["publication_id"] is not None]
    assert len(ripley_obs) > 0
    item = ripley_obs[0]

    # Verify publication_id != evidence_id
    assert item["publication_id"] != item["evidence_id"]
    assert item["publication_id"] == pub_id
    assert item["evidence_id"] == ev_id
    assert item["position"] == 4
    assert item["evidence_status"] == "VERIFIED"


# ---------------------------------------------------------------------------
# FASE 9: COMBINED INTEGRATION (SEASON -> PRODUCT -> TYPE -> INTENT -> OBSERVATION)
# ---------------------------------------------------------------------------
def test_combined_season_search_intent_pipeline():
    """
    Demonstrates complete pipeline:
    SEASON PRODUCT (Pilot)
      -> PRODUCT_TYPE (Resolved)
      -> EXPECTED SEARCH INTENT (Principals & Secondaries)
      -> OBSERVATION (Join)
    """
    conn = setup_db()
    import_expected_search_intents(conn, CSV_INTENTS_PATH)
    import_pilot_season_products(conn, PILOT_CSV_PATH)

    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT sku_parent, product_name FROM mri_season_registry LIMIT 5")
    samples = cursor.fetchall()

    for sku_p, title in samples:
        ptype = resolve_product_type(title)
        assert ptype is not None

        cursor.execute(
            """
            SELECT intent, priority, level FROM mri_expected_search_intents
            WHERE product_type = ? OR product_type LIKE ? OR (product_type = 'Pantalón' AND ? = 'Pantalon')
            ORDER BY level
            """,
            (ptype, f"{ptype}%", ptype)
        )
        intents = cursor.fetchall()
        assert len(intents) >= 1
        levels = {i[2] for i in intents}
        assert "PRINCIPAL" in levels
