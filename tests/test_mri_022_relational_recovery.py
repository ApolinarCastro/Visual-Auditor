"""
Test suite validating the resolution of defects reproduced in MRI-CODEX-FINAL-INTEGRITY-GATE-027:
1. Relational model preservation: mri_runs.run_id PRIMARY KEY retained, foreign keys from child tables (mri_evidence_ledger, mri_shadow_snapshots) remain valid.
2. Non-destructive, idempotent initialization: No DROP TABLE or destructive ALTER TABLE on mri_runs.
3. Multi-marketplace independence: 4 marketplaces maintain independent states in mri_run_marketplace_states under a shared run_id. Updating one marketplace doesn't alter others.
4. Ripley API Truth & Scoping: Runs without acquisitions show 0 publications and appropriate terminal state (SOURCE_BLOCKED / NO_EVIDENCE_RECORDED), never inheriting previous run's active publications.
5. Preservation of runs with zero publications: History and history detail endpoints preserve and return empty/blocked runs.
6. A/B/C isolation (MRI-026 certification) preserved without cross-run category leakage.
"""

import asyncio
import hashlib
import json
import os
import pathlib
import sqlite3
import pytest
from app.mri_autonomous.storage_guard import StorageConfig
from app.mri_autonomous.autonomous_multimarketplace_runner import AutonomousMultiMarketplaceRunner
from app.mri_autonomous.rea_paris_engine import REAParisEngine, CommercialEntity, NormalizedPublication
from app.mri_autonomous.falabella_ssr_engine import FalabellaSSREngine
from app.mri_autonomous.meli_taxonomy_engine import MeliTaxonomyEngine
from app.mri_autonomous.ripley_commercial_engine import RipleyCommercialEngine, RIPLEY_REFERENCE_CATEGORIES
from app.storage.mri_foundation import ADDITIVE_SCHEMA_SQL


@pytest.fixture
def sandbox_db(tmp_path):
    """Sets up an isolated test SQLite DB with StorageConfig set to test mode."""
    test_db = tmp_path / "sandbox_test.db"
    StorageConfig.set_test_mode(True, str(tmp_path))
    return str(test_db)


def test_relational_model_and_foreign_keys(sandbox_db):
    """
    Test 1: Demonstrates that mri_runs.run_id remains a single primary key,
    foreign keys from child tables (mri_evidence_ledger, mri_run_marketplace_states)
    remain 100% valid, and PRAGMA foreign_key_check passes with zero violations.
    """
    conn = sqlite3.connect(sandbox_db)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(ADDITIVE_SCHEMA_SQL)

    # Insert a parent run
    conn.execute("""
        INSERT INTO mri_runs (run_id, started_at, finished_at, marketplace, brand, execution_mode, truth_model_version, terminal_state, source_method, status, created_at)
        VALUES ('RUN_LEGACY_001', '2026-10-20T00:00:00', NULL, 'Paris', 'Nicopoly', 'TEST_MODE', '2.0', 'COMPLETED', 'API', 'SUCCESS', '2026-10-20T00:00:00')
    """)

    # Insert child record in mri_evidence_ledger referencing run_id
    conn.execute("""
        INSERT INTO mri_evidence_ledger (evidence_id, run_id, marketplace, brand, claim_type, claim_value, source_surface, method, observed_at, confidence, status, raw_reference, content_hash, truth_model_version)
        VALUES ('EV_001', 'RUN_LEGACY_001', 'Paris', 'Nicopoly', 'AUDIT', '10', 'SURFACE_1', 'METHOD_1', '2026-10-20T00:00:00', 1.0, 'RECORDED', 'REF_1', 'HASH_001', '2.0')
    """)

    # Insert child records in mri_run_marketplace_states referencing run_id
    conn.execute("""
        INSERT INTO mri_run_marketplace_states (run_id, marketplace, terminal_state, source_method, execution_mode, started_at, finished_at, status, created_at)
        VALUES ('RUN_LEGACY_001', 'Paris', 'COMPLETED', 'API', 'TEST_MODE', '2026-10-20T00:00:00', '2026-10-20T00:01:00', 'SUCCESS', '2026-10-20T00:00:00')
    """)

    # Verify foreign_key_check returns zero errors
    fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
    assert fk_violations == [], f"Expected 0 foreign key violations, found: {fk_violations}"

    # Verify runner _init_sqlite_tables is idempotent and does not break existing FKs or drop tables
    runner = AutonomousMultiMarketplaceRunner(db_path=sandbox_db)
    runner._init_sqlite_tables(conn)

    fk_violations_after = conn.execute("PRAGMA foreign_key_check;").fetchall()
    assert fk_violations_after == [], f"Foreign key check failed after runner initialization: {fk_violations_after}"

    # Verify table schema has mri_runs with run_id PRIMARY KEY
    mri_runs_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='mri_runs';").fetchone()[0]
    assert "run_id TEXT PRIMARY KEY" in mri_runs_ddl or "PRIMARY KEY (run_id)" in mri_runs_ddl

    # Verify row still exists
    row = conn.execute("SELECT run_id, marketplace FROM mri_runs WHERE run_id = 'RUN_LEGACY_001';").fetchone()
    assert row == ('RUN_LEGACY_001', 'Paris')

    conn.close()


def test_four_marketplaces_independent_states(sandbox_db):
    """
    Test 2: Verifies that 4 marketplaces persist independent states under a single shared run_id
    and updating one marketplace does not corrupt or overwrite other marketplaces.
    """
    runner = AutonomousMultiMarketplaceRunner(db_path=sandbox_db)
    with sqlite3.connect(sandbox_db) as conn:
        runner._init_sqlite_tables(conn)

    run_id = "RUN_SHARED_4MP_001"
    paris_eng = REAParisEngine()
    falabella_eng = FalabellaSSREngine()
    meli_eng = MeliTaxonomyEngine()
    ripley_eng = RipleyCommercialEngine()

    # Persist initial 4 states
    paris_eng.persist_to_mri_sqlite([], [], run_id, db_path=sandbox_db, terminal_state="COMPLETED")
    falabella_eng.persist_to_mri_sqlite([], [], run_id, db_path=sandbox_db, terminal_state="PARTIAL")
    meli_eng.persist_to_mri_sqlite([], [], run_id, db_path=sandbox_db, terminal_state="SOURCE_BLOCKED")
    ripley_eng.persist_to_mri_sqlite([], [], run_id, db_path=sandbox_db, terminal_state="FAILED")

    conn = sqlite3.connect(sandbox_db)
    states_before = conn.execute("""
        SELECT marketplace, terminal_state, status
        FROM mri_run_marketplace_states
        WHERE run_id = ?
        ORDER BY marketplace
    """, (run_id,)).fetchall()

    expected_before = [
        ("Falabella", "PARTIAL", "SUCCESS"),
        ("Mercado Libre", "SOURCE_BLOCKED", "SUCCESS"),
        ("Paris", "COMPLETED", "SUCCESS"),
        ("Ripley", "FAILED", "SUCCESS"),
    ]
    assert states_before == expected_before

    # Now update only Ripley to SOURCE_BLOCKED
    ripley_eng.persist_to_mri_sqlite([], [], run_id, db_path=sandbox_db, terminal_state="SOURCE_BLOCKED")

    states_after = conn.execute("""
        SELECT marketplace, terminal_state, status
        FROM mri_run_marketplace_states
        WHERE run_id = ?
        ORDER BY marketplace
    """, (run_id,)).fetchall()

    expected_after = [
        ("Falabella", "PARTIAL", "SUCCESS"),
        ("Mercado Libre", "SOURCE_BLOCKED", "SUCCESS"),
        ("Paris", "COMPLETED", "SUCCESS"),
        ("Ripley", "SOURCE_BLOCKED", "SUCCESS"),
    ]
    assert states_after == expected_after
    conn.close()


def test_ripley_run_scoped_truth_and_zero_static(sandbox_db):
    """
    Test 3: Reproduces the Ripley scoping contraexample from Codex 027:
    - AUDIT_OLD_RIPLEY persists 1 publication and OLD_CATEGORY.
    - AUDIT_NEW_EMPTY_RIPLEY persists 0 publications with SOURCE_BLOCKED.
    - Querying Ripley summary for AUDIT_NEW_EMPTY_RIPLEY reports 0 publications,
      0 acquired categories, status SOURCE_BLOCKED, and NEVER reports the old run's publications.
    - Querying AUDIT_OLD_RIPLEY still retrieves 1 publication and OLD_CATEGORY.
    """
    ripley_eng = RipleyCommercialEngine()

    # 1. Old run with 1 publication
    old_raw = [{
        "marketplace_sku": "RIPLEY_SKU_OLD",
        "title": "Chaqueta Invierno Nicopoly",
        "url": "https://simple.ripley.cl/chaqueta-old",
        "vendor": "Nicopoly",
        "price": 29990.0,
        "category": "Chaquetas",
        "category_id": "cat_chaquetas"
    }]
    old_pubs, old_ents = ripley_eng.normalize_items_to_publications(old_raw)
    ripley_eng.persist_to_mri_sqlite(old_pubs, old_ents, "AUDIT_OLD_RIPLEY", db_path=sandbox_db, terminal_state="COMPLETED")

    # 2. New run with 0 publications and SOURCE_BLOCKED
    new_pubs, new_ents = ripley_eng.normalize_items_to_publications([])
    assert new_pubs == []
    assert new_ents == []
    ripley_eng.persist_to_mri_sqlite(new_pubs, new_ents, "AUDIT_NEW_EMPTY_RIPLEY", db_path=sandbox_db, terminal_state="SOURCE_BLOCKED")

    # Summary for latest run (AUDIT_NEW_EMPTY_RIPLEY)
    summary_new = ripley_eng.get_commercial_summary(db_path=sandbox_db)
    assert summary_new["total_brand_publications"] == 0
    assert summary_new["total_official_seller_publications"] == 0
    assert summary_new["categories"] == []
    assert summary_new["status"] == "SOURCE_BLOCKED"
    assert summary_new["run_id"] == "AUDIT_NEW_EMPTY_RIPLEY"

    # Explicit summary for old run
    summary_old = ripley_eng.get_commercial_summary(db_path=sandbox_db, run_id="AUDIT_OLD_RIPLEY")
    assert summary_old["total_brand_publications"] == 1
    assert summary_old["total_official_seller_publications"] == 1
    assert summary_old["status"] == "OPERATIONAL"


def test_empty_runs_preserved_in_history_and_detail(sandbox_db):
    """
    Test 4: Verifies that a run with 4 marketplace states but 0 publications
    is preserved and visible in get_history() and get_history_run_publications().
    """
    from app.mri_dashboard.mri_api import get_history, get_history_run_publications, orchestrator
    import app.mri_dashboard.mri_api as api_mod

    # Redirect api DB_PATH to sandbox_db
    api_mod.DB_PATH = pathlib.Path(sandbox_db)
    StorageConfig.set_test_mode(True, str(pathlib.Path(sandbox_db).parent))
    StorageConfig.get_sqlite_path = classmethod(lambda cls: pathlib.Path(sandbox_db))

    runner = AutonomousMultiMarketplaceRunner(db_path=sandbox_db)
    with sqlite3.connect(sandbox_db) as conn:
        runner._init_sqlite_tables(conn)

    empty_run = "AUDIT_EMPTY_FOUR"
    for eng, state in [
        (REAParisEngine(), "COMPLETED"),
        (FalabellaSSREngine(), "PARTIAL"),
        (MeliTaxonomyEngine(), "SOURCE_BLOCKED"),
        (RipleyCommercialEngine(), "FAILED")
    ]:
        eng.persist_to_mri_sqlite([], [], empty_run, db_path=sandbox_db, terminal_state=state)

    # Call get_history
    history_res = asyncio.run(get_history())
    history_data = json.loads(history_res.body)
    run_entries = [h for h in history_data["history"] if h["run_id"] == empty_run]
    assert len(run_entries) == 1, f"Expected empty run in history, got: {history_data}"
    entry = run_entries[0]
    assert entry["total"] == 0
    assert entry["confirmed"] == 0

    # Call get_history_run_publications (should return 200 with 0 publications, not 404)
    detail_res = asyncio.run(get_history_run_publications(empty_run))
    assert detail_res.status_code == 200
    detail_data = json.loads(detail_res.body)
    assert detail_data["run_id"] == empty_run
    assert detail_data["publications"] == []
    assert detail_data["count"] == 0
    assert detail_data["source"] == "SQLITE_EMPTY_RUN"


def test_abc_category_isolation_preserved(sandbox_db):
    """
    Test 5: Preserves certified MRI-026 A/B/C isolation test.
    Successive runs with shared publications must not cross-contaminate categories.
    """
    runner = AutonomousMultiMarketplaceRunner(db_path=sandbox_db)
    with sqlite3.connect(sandbox_db) as conn:
        runner._init_sqlite_tables(conn)

    meli_eng = MeliTaxonomyEngine()

    for suffix in ["A", "B", "C"]:
        cat = f"CAT_{suffix}"
        pub = NormalizedPublication(
            publication_id="PUB_SHARED_MELI",
            marketplace="Mercado Libre",
            sku="SKU_SHARED",
            title="Producto Test Shared",
            brand="Nicopoly",
            sellers=["Nicopoly"],
            is_official_seller=True,
            price_regular=None,
            price_displayed=None,
            discount_percentage=None,
            condition="NEW",
            canonical_url=f"https://mercadolibre.cl/p/{suffix}",
            categories=[{"group_id": cat, "name": cat, "path": cat}]
        )
        ent = CommercialEntity(
            marketplace="Mercado Libre",
            group_id=cat,
            display_name=cat,
            entity_type="category",
            parent_id=None,
            hierarchical_path=cat,
            official_url=f"https://mercadolibre.cl/cat/{suffix}",
            reported_total=1
        )
        meli_eng.persist_to_mri_sqlite([pub], [ent], f"AUDIT_{suffix}", db_path=sandbox_db, terminal_state="COMPLETED")

    # Verify that query for each run only retrieves its own category
    conn = sqlite3.connect(sandbox_db)
    for suffix in ["A", "B", "C"]:
        run_id = f"AUDIT_{suffix}"
        # Check active or historical publication category
        cat_rows = conn.execute("""
            SELECT category_id FROM mri_publication_categories WHERE publication_id = 'PUB_SHARED_MELI'
        """).fetchall()
        hist_cat_rows = conn.execute("""
            SELECT category_id FROM mri_historical_publication_categories WHERE run_id = ?
        """, (run_id,)).fetchall()

        if run_id == "AUDIT_C":
            # Active run
            assert cat_rows == [(f"MELI_CAT_CAT_C",)]
        else:
            assert hist_cat_rows == [(f"MELI_CAT_CAT_{suffix}",)]
    conn.close()


def test_initialization_atomicity_and_caller_transaction(sandbox_db):
    """
    Test 6: Tests SQLite initialization atomicity, constraint parity, and caller transaction preservation:
    - If caller owns an open transaction, _init_sqlite_tables must not commit it.
    - If a DDL error occurs during initialization (e.g. denied table creation), all partial tables are rolled back.
    - Fresh schema must preserve NOT NULL constraints matching legacy schema.
    """
    runner = AutonomousMultiMarketplaceRunner(db_path=sandbox_db)

    # 1. Caller transaction preservation
    conn = sqlite3.connect(sandbox_db)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("""
        CREATE TABLE mri_runs (
            run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, marketplace TEXT NOT NULL,
            brand TEXT NOT NULL, execution_mode TEXT NOT NULL, truth_model_version TEXT NOT NULL,
            terminal_state TEXT, source_method TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL
        )
    """)
    conn.execute("INSERT INTO mri_runs VALUES ('COMMITTED', '2026', NULL, 'Paris', 'TEST', 'AUDIT', '2', 'COMPLETED', 'AUDIT', 'SUCCESS', '2026')")
    conn.commit()

    # Caller starts transaction
    conn.execute("INSERT INTO mri_runs VALUES ('UNCOMMITTED', '2026', NULL, 'Paris', 'TEST', 'AUDIT', '2', 'COMPLETED', 'AUDIT', 'SUCCESS', '2026')")
    assert conn.in_transaction is True

    # Call _init_sqlite_tables
    runner._init_sqlite_tables(conn)

    # Caller decides to roll back
    conn.rollback()
    assert conn.in_transaction is False

    # The uncommitted row must have been rolled back
    remaining = conn.execute("SELECT run_id FROM mri_runs WHERE run_id = 'UNCOMMITTED'").fetchall()
    assert remaining == [], f"Expected uncommitted row to be rolled back, found: {remaining}"
    conn.close()

    # 2. Fresh schema constraint parity
    fresh_db = sandbox_db + "_fresh.db"
    conn_fresh = sqlite3.connect(fresh_db)
    conn_fresh.execute("PRAGMA foreign_keys = ON;")
    runner_fresh = AutonomousMultiMarketplaceRunner(db_path=fresh_db)
    runner_fresh._init_sqlite_tables(conn_fresh)

    with pytest.raises(sqlite3.IntegrityError):
        conn_fresh.execute("INSERT INTO mri_runs (run_id) VALUES ('INCOMPLETE_ROW')")
    conn_fresh.close()

    # 3. Initialization atomicity under injected fault
    fault_db = sandbox_db + "_fault.db"
    conn_fault = sqlite3.connect(fault_db)
    def deny_mstates(action, a, b, db, trigger):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TABLE and a == 'mri_run_marketplace_states' else sqlite3.SQLITE_OK
    conn_fault.set_authorizer(deny_mstates)

    with pytest.raises(sqlite3.DatabaseError):
        runner_fault = AutonomousMultiMarketplaceRunner(db_path=fault_db)
        runner_fault._init_sqlite_tables(conn_fault)

    conn_fault.set_authorizer(None)
    tables = conn_fault.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    assert tables == [], f"Expected 0 durable tables after initialization failure, found: {tables}"
    conn_fault.close()


def test_persistor_atomicity_and_connection_lifecycle(sandbox_db):
    """
    Test 7: Tests persistor atomicity and proper connection closure under injected failures:
    - Trigger error during persist_to_mri_sqlite must roll back the entire transaction.
    - No partial parents must remain durable.
    - Connection must be closed properly without leaving dangling open transactions.
    """
    runner = AutonomousMultiMarketplaceRunner(db_path=sandbox_db)
    conn = sqlite3.connect(sandbox_db)
    runner._init_sqlite_tables(conn)
    conn.execute("CREATE TRIGGER test_fault_trigger BEFORE INSERT ON mri_run_marketplace_states BEGIN SELECT RAISE(ABORT, 'TEST_INJECTED_ABORT'); END;")
    conn.commit()
    conn.close()

    engines = [REAParisEngine(), FalabellaSSREngine(), MeliTaxonomyEngine(), RipleyCommercialEngine()]

    for engine in engines:
        held = []
        orig_connect = sqlite3.connect
        def capture(*args, **kwargs):
            c = orig_connect(*args, **kwargs)
            held.append(c)
            return c
        sqlite3.connect = capture

        with pytest.raises(sqlite3.IntegrityError):
            engine.persist_to_mri_sqlite([], [], "FAULT_RUN_ID", db_path=sandbox_db)
        sqlite3.connect = orig_connect

        # Verify held connection is closed
        for c in held:
            with pytest.raises(sqlite3.ProgrammingError, match="Cannot operate on a closed database"):
                c.execute("SELECT 1")

        # Verify no durable parent remained in database
        check_conn = sqlite3.connect(sandbox_db)
        parent_count = check_conn.execute("SELECT count(*) FROM mri_runs WHERE run_id = 'FAULT_RUN_ID'").fetchone()[0]
        check_conn.close()
        assert parent_count == 0, f"Expected 0 durable parents for {type(engine).__name__}, got {parent_count}"

