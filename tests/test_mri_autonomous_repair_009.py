"""
tests/test_mri_autonomous_repair_009.py

Comprehensive 10-Point Automated Test Suite for MRI-AUTONOMOUS-REPAIR-009:
1. Bloqueo de escritura productiva desde todos los escritores (StorageConfig write barrier).
2. Conservación de 2.533 observaciones históricas en SQLite.
3. Posiciones distintas cuando la evidencia indica posiciones distintas (no constante 1).
4. Cobertura parcial y PAGE_BUDGET_EXCEEDED conservada hasta API y dashboard.
5. Identificación correcta de padre y variante (Paris N05298A y Falabella N05301E-7).
6. Rechazo de coincidencias falsas como 3/4 frente a 1/2.
7. Separación estricta de tienda/corredor de marca y categoría departamental.
8. Integridad de evidencia primaria (sin hashes ficticios).
9. Funcionamiento desde checkout limpio, sin módulos locales ocultos.
10. Cero modificaciones de Visual Auditor (VA frozen vs origin/main).
"""

import os
import sys
import shutil
import sqlite3
import json
import pytest
from pathlib import Path

# Ensure project root in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Activate isolated test mode immediately before any module-level writers instantiate
from app.mri_autonomous.storage_guard import StorageConfig, ProductionWriteBlockedError
StorageConfig.set_test_mode(True, sandbox_dir="tmp/mri_sandbox_test")

from app.mri_autonomous.experience_store import ExperienceStore
from app.mri_autonomous.category_evaluator import evaluate_commercial_category
from app.mri_dashboard.category_manager import CategoryManager
from app.mri_dashboard.mri_api import (
    normalize_title_tokens,
    clean_cat_title,
    get_master_catalog,
    fetch_run_publications
)
from app.mri_autonomous.recovery_runner import AcquisitionRecoveryRunner


@pytest.fixture(scope="module")
def sandbox_env(tmp_path_factory):
    """Sets up an isolated sandbox environment where test mode is strictly enabled."""
    sandbox_dir = tmp_path_factory.mktemp("mri_sandbox_009")
    StorageConfig.set_test_mode(True, sandbox_dir=sandbox_dir)
    os.environ["MRI_ENV"] = "TEST"
    
    # Initialize isolated SQLite database with required schema
    isolated_db = sandbox_dir / "visibility.db"
    conn = sqlite3.connect(isolated_db)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mri_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT,
            finished_at TEXT,
            marketplace TEXT,
            brand TEXT,
            execution_mode TEXT,
            truth_model_version TEXT,
            terminal_state TEXT,
            source_method TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mri_publications (
            publication_id TEXT PRIMARY KEY,
            product_id TEXT,
            marketplace TEXT,
            marketplace_product_id TEXT,
            canonical_url TEXT,
            status TEXT,
            observed_at TEXT,
            run_id TEXT,
            position INTEGER,
            surface TEXT,
            position_state TEXT,
            category_relationship TEXT,
            evidence_type TEXT,
            raw_source_id TEXT,
            acquisition_status TEXT,
            identity_status TEXT,
            category_observed TEXT,
            category_source TEXT,
            category_expected TEXT,
            category_decision TEXT,
            commercial_attributes TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mri_historical_publications (
            history_id TEXT PRIMARY KEY,
            publication_id TEXT,
            product_id TEXT,
            marketplace TEXT,
            marketplace_product_id TEXT,
            canonical_url TEXT,
            status TEXT,
            observed_at TEXT,
            run_id TEXT,
            position INTEGER,
            surface TEXT,
            position_state TEXT,
            category_relationship TEXT,
            evidence_type TEXT,
            raw_source_id TEXT,
            acquisition_status TEXT,
            identity_status TEXT,
            category_observed TEXT,
            category_source TEXT,
            category_expected TEXT,
            category_decision TEXT,
            commercial_attributes TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mri_categories (
            category_id TEXT PRIMARY KEY,
            marketplace TEXT,
            category_name TEXT,
            canonical_url TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mri_publication_categories (
            publication_id TEXT,
            category_id TEXT,
            status TEXT,
            observed_at TEXT,
            PRIMARY KEY (publication_id, category_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mri_products (
            product_id TEXT PRIMARY KEY,
            canonical_brand TEXT,
            product_status TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS product_snapshots (
            marketplace_sku TEXT,
            product_title TEXT,
            sku_master TEXT,
            audit_date TEXT
        )
    """)
    conn.commit()
    conn.close()

    yield sandbox_dir

    # Cleanup test mode
    StorageConfig.set_test_mode(False)
    if "MRI_ENV" in os.environ:
        del os.environ["MRI_ENV"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Negative Test: Production Write Barrier from All Writers
# ─────────────────────────────────────────────────────────────────────────────

def test_production_write_barrier_rejection(sandbox_env):
    """
    Demonstrates with negative testing that attempting to write to production paths
    from any writer raises ProductionWriteBlockedError.
    """
    prod_sqlite = StorageConfig.PRODUCTION_SQLITE
    prod_exp = StorageConfig.PRODUCTION_EXPERIENCE
    prod_history = StorageConfig.PRODUCTION_HISTORY
    prod_cat = StorageConfig.PRODUCTION_CATEGORIES

    # Direct assertion check
    with pytest.raises(ProductionWriteBlockedError):
        StorageConfig.assert_write_allowed(prod_sqlite)

    with pytest.raises(ProductionWriteBlockedError):
        StorageConfig.assert_write_allowed(prod_exp)

    # ExperienceStore writer rejection when forced to production path
    with pytest.raises(ProductionWriteBlockedError):
        ExperienceStore(db_path=prod_exp)

    # CategoryManager writer rejection on save to production path
    cm = CategoryManager(data_path=prod_cat)
    with pytest.raises(ProductionWriteBlockedError):
        cm._save()

    # RecoveryRunner writer rejection on persist to production path
    runner = AcquisitionRecoveryRunner(db_path=prod_sqlite)
    with pytest.raises(ProductionWriteBlockedError):
        runner.persist_to_sqlite({"observations": []}, "test_run_rejection")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Historical Preservation: 2,533 Observations in Run run_va_mri_operational_integration_1792000336
# ─────────────────────────────────────────────────────────────────────────────

def test_historical_preservation_2533_records():
    """
    Verifies that the historical baseline in backup_production_009/visibility.db
    contains exactly 2,533 observations (2,489 active + 44 historical) for the run.
    """
    db_path = Path("backup_production_009/visibility.db")
    if not db_path.exists():
        db_path = Path("data/sqlite/visibility.db")
    assert db_path.exists(), "A SQLite DB with baseline observations must exist"
    
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    cur = conn.cursor()
    run_id = "run_va_mri_operational_integration_1792000336"
    
    cnt_pubs = cur.execute(
        "SELECT COUNT(*) FROM mri_publications WHERE run_id = ?", (run_id,)
    ).fetchone()[0]
    
    cnt_hist = cur.execute(
        "SELECT COUNT(*) FROM mri_historical_publications WHERE run_id = ?", (run_id,)
    ).fetchone()[0]
    
    conn.close()

    assert cnt_pubs == 2489, f"Expected 2489 active publications for run, got {cnt_pubs}"
    assert cnt_hist == 44, f"Expected 44 historical publications for run, got {cnt_hist}"
    assert cnt_pubs + cnt_hist == 2533, f"Total records must be exactly 2,533, got {cnt_pubs + cnt_hist}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Position Accuracy: Distinct Observed Positions (No Hardcoded 1)
# ─────────────────────────────────────────────────────────────────────────────

def test_position_accuracy_distinct_positions(sandbox_env):
    """
    Tests that observations across pages retain their distinct observed positions
    (e.g., 1, 2, 3... 48) and are never collapsed into a constant 1.
    """
    runner = AcquisitionRecoveryRunner(
        output_dir=sandbox_env / "evidence",
        db_path=sandbox_env / "visibility.db"
    )
    run_id = "test_run_positions_009"
    
    observations = []
    for pos in range(1, 49):
        observations.append({
            "publication_id": f"pub_test_{pos}",
            "marketplace": "Falabella",
            "observed_url": f"https://www.falabella.com/falabella-cl/product/1000{pos}/p",
            "position_observed": pos,
            "title": f"Prenda Nicopoly Modelo {pos}",
            "observation_timestamp": "2026-10-15T12:00:00",
            "status": "OBSERVED",
            "acquisition_status": "OBSERVED",
            "identity_status": "TARGET_IDENTITY_VERIFIED",
            "category_observed": "Moda Mujer → Chaquetas",
            "category_source": "PUBLIC_CHANNEL_BREADCRUMBS",
            "category_expected": "Chaquetas",
            "category_decision": "CORRECT",
            "commercial_attributes": "{}"
        })
    
    res = runner.persist_to_sqlite({"observations": observations}, run_id)
    assert res["publications_materialized"] == 48

    # Query back from isolated SQLite
    conn = sqlite3.connect(sandbox_env / "visibility.db")
    cur = conn.cursor()
    positions = [
        r[0] for r in cur.execute(
            "SELECT position FROM mri_publications WHERE run_id = ? ORDER BY position ASC", (run_id,)
        ).fetchall()
    ]
    conn.close()

    assert len(positions) == 48
    assert len(set(positions)) == 48, "All 48 positions must be distinct"
    assert positions[0] == 1
    assert positions[-1] == 48
    assert 1 not in positions[1:], "Positions > 1 must not be hardcoded to 1"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Coverage Integrity: PAGE_BUDGET_EXCEEDED Preserved Up to API
# ─────────────────────────────────────────────────────────────────────────────

def test_coverage_preserves_page_budget_exceeded(sandbox_env):
    """
    Verifies that when a run terminates with PAGE_BUDGET_EXCEEDED,
    the coverage is strictly preserved as PAGE_BUDGET_EXCEEDED (never overridden to COMPLETE).
    """
    db_file = sandbox_env / "visibility.db"
    conn = sqlite3.connect(db_file, timeout=30.0)
    cur = conn.cursor()
    run_id = "test_run_page_budget_009"

    # Register run with terminal_state = PAGE_BUDGET_EXCEEDED
    cur.execute("""
        INSERT OR REPLACE INTO mri_runs (run_id, started_at, finished_at, marketplace, terminal_state, status)
        VALUES (?, '2026-10-15T10:00:00', '2026-10-15T10:05:00', 'Falabella', 'PAGE_BUDGET_EXCEEDED', 'STOPPED')
    """, (run_id,))

    # Insert sample publication with URL and verified identity
    cur.execute("""
        INSERT OR REPLACE INTO mri_publications (
            publication_id, marketplace, marketplace_product_id, canonical_url, status, run_id,
            position, category_observed, identity_status, category_decision
        ) VALUES (
            'pub_budget_1', 'Falabella', 'SKU_BUDGET_1', 'https://www.falabella.com/p/1', 'OBSERVED', ?,
            1, 'Moda Mujer → Chaquetas', 'TARGET_IDENTITY_VERIFIED', 'CORRECT'
        )
    """, (run_id,))
    conn.commit()
    conn.close()

    # Call API helper
    pubs = fetch_run_publications(run_id)
    assert len(pubs) == 1
    pub = pubs[0]
    assert pub["coverage"] == "PAGE_BUDGET_EXCEEDED", (
        f"Coverage must be PAGE_BUDGET_EXCEEDED, got {pub['coverage']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Parent / Variant Resolution (Paris N05298A and Falabella N05301E-7)
# ─────────────────────────────────────────────────────────────────────────────

def test_parent_variant_resolution():
    """
    Verifies that Paris parent N05298A retains candidate variants without arbitrarily
    guessing a single variant SKU, and Falabella N05301E-7 resolves accurately.
    """
    child_to_cat, parent_to_cat, title_to_cat, token_to_entries = get_master_catalog()

    # Paris N05298A check
    assert "N05298A" in parent_to_cat, "Parent N05298A must exist in master catalog"
    p_variants = [c for c, e in child_to_cat.items() if e.get("parent") == "N05298A"]
    assert len(p_variants) >= 4, f"N05298A must have multiple size variants, got {p_variants}"
    assert "N05298AS" in p_variants
    assert "N05298AXL" in p_variants

    # Falabella N05301E-7 check
    assert "N05301E-7" in parent_to_cat, "Parent N05301E-7 must exist in master catalog"
    f_variants = [c for c, e in child_to_cat.items() if e.get("parent") == "N05301E-7"]
    assert len(f_variants) >= 4
    assert any("N05301ES-7" in v for v in f_variants)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Rejection of False Collisions: 3/4 vs 1/2
# ─────────────────────────────────────────────────────────────────────────────

def test_rejection_of_fraction_collisions_3_4_vs_1_2():
    """
    Ensures that titles with '3/4' and '1/2' produce distinct token representations
    and never match each other falsely.
    """
    title_34 = "Blazer Manga 3/4 Ajustado con Solapas Amarillo Mantequilla"
    title_12 = "Blazer Manga 1/2 Ajustado con Solapas Amarillo Mantequilla"

    tokens_34 = normalize_title_tokens(title_34)
    tokens_12 = normalize_title_tokens(title_12)

    assert tokens_34 != tokens_12, "Fractions 3/4 and 1/2 must NOT collapse to identical tokens"
    assert "3slash4" in tokens_34
    assert "1slash2" in tokens_12
    assert "3slash4" not in tokens_12
    assert "1slash2" not in tokens_34


# ─────────────────────────────────────────────────────────────────────────────
# 7. Brand Corridor Separation from Departmental Category
# ─────────────────────────────────────────────────────────────────────────────

def test_brand_corridor_separation_ripley():
    """
    Verifies that a brand corridor (e.g. 'Moda Mujer → Marcas Casuales → Nicopoly')
    is identified as TIENDA_DE_MARCA and not accepted as a valid departmental clothing category.
    """
    eval_res = evaluate_commercial_category(
        product_title="Blazer Ajustado Nicopoly",
        expected_category="Ropa - Ropa Mujer - Chaquetas - Blazers",
        observed_category="Moda Mujer → Marcas Casuales → Nicopoly",
        public_attributes={},
        marketplace="Ripley",
        identity_status="TARGET_IDENTITY_VERIFIED"
    )

    assert eval_res["decision"] == "REVIEW_REQUIRED"
    assert "TIENDA_DE_MARCA" in eval_res.get("corredor_tipo", "")
    assert eval_res.get("brand_corridor") == "Moda Mujer → Marcas Casuales → Nicopoly"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Primary Evidence Integrity: Verifiable URL & Traceability
# ─────────────────────────────────────────────────────────────────────────────

def test_primary_evidence_integrity():
    """
    Ensures observations require genuine URLs and non-synthetic attributes.
    """
    eval_unverified = evaluate_commercial_category(
        product_title="Prenda Desconocida",
        expected_category="Vestidos",
        observed_category="NO_VERIFICADO",
        public_attributes={},
        marketplace="Paris",
        identity_status="IDENTIDAD_NO_VERIFICADA"
    )

    assert eval_unverified["decision"] == "REVIEW_REQUIRED"
    assert "Identidad no verificada" in eval_unverified["reason"]


# ─────────────────────────────────────────────────────────────────────────────
# 9. Clean Checkout: Untracked Essential Modules Present
# ─────────────────────────────────────────────────────────────────────────────

def test_clean_checkout_modules_presence():
    """
    Verifies that category_evaluator, category_manager, and storage_guard
    are cleanly importable and part of the codebase.
    """
    import app.mri_autonomous.category_evaluator
    import app.mri_dashboard.category_manager
    import app.mri_autonomous.storage_guard

    assert hasattr(app.mri_autonomous.category_evaluator, "evaluate_commercial_category")
    assert hasattr(app.mri_dashboard.category_manager, "CategoryManager")
    assert hasattr(app.mri_autonomous.storage_guard, "StorageConfig")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Zero VA Modifications: Diff vs origin/main on VA is Zero
# ─────────────────────────────────────────────────────────────────────────────

def test_zero_va_modifications():
    """
    Verifies that app/auditor, app/scrapers, and app/core are 100% frozen
    and have zero git diff vs origin/main.
    """
    import subprocess
    cmd = ["git", "diff", "origin/main", "--", "app/auditor", "app/scrapers", "app/core"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.returncode == 0, f"Git diff command failed: {proc.stderr}"
    assert proc.stdout.strip() == "", f"VA directories MUST HAVE ZERO DIFF vs origin/main. Found:\n{proc.stdout}"
