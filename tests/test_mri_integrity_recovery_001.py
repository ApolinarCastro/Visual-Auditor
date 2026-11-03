"""CP3 persistence/repeatability for MRI integrity recovery 001.

These tests prove the RecoveryRunner archives category membership before the
active junction is replaced, so a second run cannot silently destroy the first
run's category evidence.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.mri_autonomous.recovery_runner import AcquisitionRecoveryRunner
from app.mri_autonomous.storage_guard import StorageConfig
from app.storage.mri_foundation import ADDITIVE_SCHEMA_SQL


def _obs(run_id: str, category: str) -> dict:
    return {
        "publication_id": "PUB-INTEGRITY-001",
        "marketplace": "Falabella",
        "observed_url": "https://www.falabella.com/falabella-cl/product/1/test",
        "position_observed": 1,
        "title": "Producto Integridad",
        "observation_timestamp": "2026-11-02T10:00:00",
        "acquisition_status": "OBSERVED",
        "identity_status": "OFFICIAL_VERIFIED",
        "category_observed": category,
        "category_source": "TEST",
        "category_expected": "SIN_REFERENCIA",
        "category_decision": "NO_VERIFICADO",
        "commercial_attributes": "{}",
        "raw_source_id": "TEST-RAW",
        "evidence_type": "TEST",
        "status": "OBSERVED",
        "run_id": run_id,
    }


def test_recovery_runner_preserves_previous_run_category_membership():
    base = Path("evidence_local_validation/mri_integrity_recovery_001")
    base.mkdir(parents=True, exist_ok=True)
    db = base / "persistence_repeatability.db"
    db.unlink(missing_ok=True)
    StorageConfig.set_test_mode(True, str(base))
    conn = sqlite3.connect(db)
    conn.executescript(ADDITIVE_SCHEMA_SQL)
    # Production schema has these columns; ADDITIVE_SCHEMA_SQL is the minimal
    # foundation. Add the same columns for an isolated contract test.
    pub_cols = ["position_state", "category_relationship", "evidence_type",
                "raw_source_id", "acquisition_status", "identity_status",
                "category_observed", "category_source", "category_expected",
                "category_decision", "commercial_attributes"]
    for col in pub_cols:
        try:
            conn.execute(f"ALTER TABLE mri_publications ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    hist_cols = ["product_id", "marketplace", "marketplace_product_id", "status",
                 "position_state", "category_relationship", "evidence_type",
                 "raw_source_id", "acquisition_status", "identity_status",
                 "category_observed", "category_source", "category_expected",
                 "category_decision", "commercial_attributes"]
    for col in hist_cols:
        try:
            conn.execute(f"ALTER TABLE mri_historical_publications ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

    runner = AcquisitionRecoveryRunner(db_path=db)
    first = {"observations": [_obs("RUN-A", "Categoria A")],
             "terminal_state": "COMPLETED"}
    second = {"observations": [_obs("RUN-B", "Categoria B")],
              "terminal_state": "COMPLETED"}
    runner.persist_to_sqlite(first, "RUN-A",
                             run_meta={"marketplace": "Falabella"})
    runner.persist_to_sqlite(second, "RUN-B",
                             run_meta={"marketplace": "Falabella"})

    conn = sqlite3.connect(db)
    active = conn.execute(
        "SELECT category_id FROM mri_publication_categories "
        "WHERE publication_id = 'PUB-INTEGRITY-001'").fetchall()
    historical = conn.execute(
        "SELECT category_id FROM mri_historical_publication_categories "
        "WHERE publication_id = 'PUB-INTEGRITY-001' AND run_id = 'RUN-A'"
    ).fetchall()
    conn.close()

    assert active, "la corrida activa debe tener una categoría"
    assert historical, "la corrida anterior debe conservar su categoría histórica"
    assert active != historical, "las categorías activa e histórica no deben ser idénticas"


def test_persist_rolls_back_before_commit_on_write_failure():
    base = Path("evidence_local_validation/mri_integrity_recovery_001")
    base.mkdir(parents=True, exist_ok=True)
    db = base / "persistence_rollback.db"
    db.unlink(missing_ok=True)
    StorageConfig.set_test_mode(True, str(base))
    conn = sqlite3.connect(db)
    conn.executescript(ADDITIVE_SCHEMA_SQL)
    conn.execute("""
        CREATE TRIGGER fail_pub_insert BEFORE INSERT ON mri_publications
        BEGIN SELECT RAISE(ABORT, 'forced persistence failure'); END;
    """)
    conn.commit(); conn.close()
    runner = AcquisitionRecoveryRunner(db_path=db)
    try:
        runner.persist_to_sqlite(
            {"observations": [_obs("RUN-FAIL", "Categoria A")],
             "terminal_state": "COMPLETED"},
            "RUN-FAIL", run_meta={"marketplace": "Falabella"})
        raised = False
    except Exception:
        raised = True
    assert raised, "la escritura debe fallar explícitamente"
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM mri_publications").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM mri_runs WHERE run_id='RUN-FAIL'").fetchone()[0] == 0
    conn.close()
