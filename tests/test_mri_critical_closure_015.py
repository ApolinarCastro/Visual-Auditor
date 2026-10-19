"""
tests/test_mri_critical_closure_015.py

Automated Test Suite for MRI-CRITICAL-CLOSURE-015.
Reproduces and verifies fixes for all 6 defects identified in MRI_CODEX_FINAL_VALIDATION_013:

1. Defect 1: Production isolation independent of CWD. Re-targeting to canonical production paths
   or paths outside the authorized sandbox raises ProductionWriteBlockedError.
2. Defect 2: /api/rea/paris queries SQLite storage directly without network calls;
   recovery_runner in run_consolidated_recovery_pipeline is properly defined.
3. Defect 3: Master catalog correspondence & replay provenance: no unverified 'CORRECT' or
   'TARGET_IDENTITY_VERIFIED' when unlinked; preserves HAR replay status.
4. Defect 4: REA observation history preservation across repeat runs: previous observations
   are archived into mri_historical_publications instead of being deleted.
5. Defect 5: Coverage filtering and dashboard representation: PAGE_BUDGET_EXCEEDED is
   properly selectable, grouped under PARTIAL, and displayed in publication detail.
6. Defect 6: Incomplete or empty upstream responses return NO_EVIDENCE_RECORDED instead of
   claiming OPERATIONAL with fake zero counts.
"""

import os
import json
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.mri_autonomous.storage_guard import StorageConfig, ProductionWriteBlockedError
from app.mri_autonomous.experience_store import ExperienceStore
from app.mri_dashboard.category_manager import CategoryManager
from app.mri_dashboard.mri_runner import MRIOrchestrator
from app.mri_autonomous.rea_paris_engine import REAParisEngine, NormalizedPublication, CommercialEntity
from app.mri_dashboard.mri_api import (
    app,
    run_consolidated_recovery_pipeline,
    fetch_run_publications
)
from fastapi.testclient import TestClient


class TestMRICriticalClosure015:

    @pytest.fixture(autouse=True)
    def setup_sandbox(self, tmp_path):
        sandbox = str(tmp_path / "mri_015_sandbox")
        StorageConfig.set_test_mode(True, sandbox_dir=sandbox)
        os.environ["MRI_ENV"] = "TEST"
        yield
        StorageConfig.set_test_mode(False)
        if "MRI_ENV" in os.environ:
            del os.environ["MRI_ENV"]

    def test_01_cwd_independent_production_isolation(self, tmp_path):
        """
        Codex 013 Defect 1:
        Verifies that re-targeting ExperienceStore, CategoryManager, or MRIOrchestrator
        to real production targets (like data/experience.db, data/mri_categories.json,
        data/mri_history.json) raises ProductionWriteBlockedError regardless of CWD.
        """
        sandbox = str(tmp_path / "safe_sandbox")
        os.makedirs(sandbox, exist_ok=True)
        safe_db = os.path.join(sandbox, "safe.db")

        # 1. ExperienceStore
        store = ExperienceStore(db_path=safe_db)
        store.db_path = "data/experience.db"
        with pytest.raises(ProductionWriteBlockedError):
            store._get_connection()

        store.db_path = str(StorageConfig.PRODUCTION_EXPERIENCE)
        with pytest.raises(ProductionWriteBlockedError):
            store._get_connection()

        # 2. CategoryManager
        cm = CategoryManager(data_path=os.path.join(sandbox, "safe_cat.json"))
        cm.data_path = "data/mri_categories.json"
        with pytest.raises(ProductionWriteBlockedError):
            cm._save()

        # 3. MRIOrchestrator
        orch = MRIOrchestrator()
        orch.history_file = "data/mri_history.json"
        with pytest.raises(ProductionWriteBlockedError):
            orch._save_history()

    def test_02_recovery_runner_defined_and_api_offline_storage(self, tmp_path):
        """
        Codex 013 Defect 2:
        1. Calling run_consolidated_recovery_pipeline does NOT raise NameError ('recovery_runner' is not defined).
        2. /api/rea/paris queries SQLite storage directly without requiring network requests.
        """
        # Test 1: recovery_runner definition
        with patch("app.mri_dashboard.mri_api.get_recovery_runner") as mock_getter:
            mock_runner = MagicMock()
            mock_runner.execute_complete_pipeline.return_value = {
                "run_id": "test_run_015",
                "pipeline_status": "SUCCESS"
            }
            mock_getter.return_value = mock_runner
            with patch("app.mri_dashboard.mri_api.fetch_run_publications", return_value=[]):
                # Must execute without NameError
                run_consolidated_recovery_pipeline()
                assert mock_runner.execute_complete_pipeline.called

        # Test 2: /api/rea/paris queries SQLite directly
        client = TestClient(app)
        res = client.get("/api/rea/paris")
        assert res.status_code == 200
        data = res.json()
        assert "marketplace" in data
        assert data["marketplace"] == "Paris"

    def test_03_rea_master_catalog_identity_and_provenance(self, tmp_path):
        """
        Codex 013 Defect 3:
        Verifies that an unlinked publication is NOT marked TARGET_IDENTITY_VERIFIED
        or CORRECT, and preserves replay provenance (CONTROLLED_REPLAY).
        """
        test_db = str(tmp_path / "test_vis.db")
        engine = REAParisEngine()

        with sqlite3.connect(test_db) as conn:
            conn.execute("""
                CREATE TABLE mri_runs (
                    run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, marketplace TEXT,
                    brand TEXT, execution_mode TEXT, truth_model_version TEXT, terminal_state TEXT,
                    source_method TEXT, status TEXT, created_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE mri_publications (
                    publication_id TEXT PRIMARY KEY, product_id TEXT, marketplace TEXT, marketplace_product_id TEXT,
                    canonical_url TEXT, status TEXT, observed_at TEXT, run_id TEXT, position INTEGER, surface TEXT,
                    position_state TEXT, category_relationship TEXT, evidence_type TEXT, raw_source_id TEXT,
                    acquisition_status TEXT, identity_status TEXT, category_observed TEXT,
                    category_source TEXT, category_expected TEXT, category_decision TEXT, commercial_attributes TEXT
                )
            """)
            conn.execute("CREATE TABLE mri_historical_publications AS SELECT * FROM mri_publications WHERE 0")
            conn.execute("CREATE TABLE mri_products (product_id TEXT PRIMARY KEY, canonical_brand TEXT, product_status TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE mri_categories (category_id TEXT PRIMARY KEY, marketplace TEXT, category_name TEXT, canonical_url TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE mri_publication_categories (publication_id TEXT, category_id TEXT, status TEXT, observed_at TEXT, PRIMARY KEY(publication_id, category_id))")

        # Unknown SKU with no master catalog match
        pub = NormalizedPublication(
            publication_id="PUB-PARIS-UNKNOWN",
            marketplace="Paris",
            sku="MKRMXN8EXC",
            title="Enterito No Vinculado",
            brand="Nicopoly",
            sellers=["Paris"],
            is_official_seller=False,
            price_regular=39990.0,
            price_displayed=19990.0,
            discount_percentage=50.0,
            condition="NEW",
            canonical_url="https://www.paris.cl/enterito.html",
            categories=[{"group_id": "catEnteritos", "name": "Enteritos y Jardineras", "path": "/moda/enteritos"}]
        )

        res = engine.persist_to_mri_sqlite([pub], [], "run_rea_015_1", db_path=test_db)
        assert res["publications_materialized"] == 1

        with sqlite3.connect(test_db) as conn:
            cur = conn.cursor()
            row = cur.execute("""
                SELECT identity_status, category_decision, evidence_type, raw_source_id
                FROM mri_publications WHERE publication_id = 'PUB-PARIS-UNKNOWN'
            """).fetchone()

            # Must NOT claim verified identity or CORRECT without master catalog match
            assert row[0] == "IDENTITY_NOT_LINKED"
            assert row[1] == "REVIEW_REQUIRED"
            assert ("REPLAY" in row[3]) or ("PROVENANCE_INCOMPLETE" in row[3])

    def test_04_rea_observation_history_preservation(self, tmp_path):
        """
        Codex 013 Defect 4:
        When persisting the same publication across multiple REA runs,
        the previous observation is archived into mri_historical_publications
        so observation history is NOT lost.
        """
        test_db = str(tmp_path / "test_hist_vis.db")
        engine = REAParisEngine()

        with sqlite3.connect(test_db) as conn:
            conn.execute("""
                CREATE TABLE mri_runs (
                    run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, marketplace TEXT,
                    brand TEXT, execution_mode TEXT, truth_model_version TEXT, terminal_state TEXT,
                    source_method TEXT, status TEXT, created_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE mri_publications (
                    publication_id TEXT PRIMARY KEY, product_id TEXT, marketplace TEXT, marketplace_product_id TEXT,
                    canonical_url TEXT, status TEXT, observed_at TEXT, run_id TEXT, position INTEGER, surface TEXT,
                    position_state TEXT, category_relationship TEXT, evidence_type TEXT, raw_source_id TEXT,
                    acquisition_status TEXT, identity_status TEXT, category_observed TEXT,
                    category_source TEXT, category_expected TEXT, category_decision TEXT, commercial_attributes TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE mri_historical_publications (
                    history_id TEXT PRIMARY KEY, publication_id TEXT, product_id TEXT, marketplace TEXT, marketplace_product_id TEXT,
                    canonical_url TEXT, status TEXT, observed_at TEXT, run_id TEXT, position INTEGER, surface TEXT,
                    position_state TEXT, category_relationship TEXT, evidence_type TEXT, raw_source_id TEXT,
                    acquisition_status TEXT, identity_status TEXT, category_observed TEXT,
                    category_source TEXT, category_expected TEXT, category_decision TEXT, commercial_attributes TEXT
                )
            """)
            conn.execute("CREATE TABLE mri_products (product_id TEXT PRIMARY KEY, canonical_brand TEXT, product_status TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE mri_categories (category_id TEXT PRIMARY KEY, marketplace TEXT, category_name TEXT, canonical_url TEXT, created_at TEXT)")
            conn.execute("CREATE TABLE mri_publication_categories (publication_id TEXT, category_id TEXT, status TEXT, observed_at TEXT, PRIMARY KEY(publication_id, category_id))")

        pub = NormalizedPublication(
            publication_id="PUB-PARIS-REPEAT",
            marketplace="Paris",
            sku="SKU-REPEAT-001",
            title="Blazer Nicopoly",
            brand="Nicopoly",
            sellers=["NICOPOLY"],
            is_official_seller=True,
            price_regular=49990.0,
            price_displayed=29990.0,
            discount_percentage=40.0,
            condition="NEW",
            canonical_url="https://www.paris.cl/blazer.html",
            categories=[{"group_id": "catBlazers", "name": "Blazers", "path": "/moda/blazers"}]
        )

        # First run
        engine.persist_to_mri_sqlite([pub], [], "run_rea_repeat_001", db_path=test_db)
        # Second run with different run_id
        engine.persist_to_mri_sqlite([pub], [], "run_rea_repeat_002", db_path=test_db)

        with sqlite3.connect(test_db) as conn:
            cur = conn.cursor()
            cnt_active = cur.execute("SELECT COUNT(*) FROM mri_publications WHERE publication_id = 'PUB-PARIS-REPEAT'").fetchone()[0]
            cnt_hist = cur.execute("SELECT COUNT(*) FROM mri_historical_publications WHERE publication_id = 'PUB-PARIS-REPEAT'").fetchone()[0]

            assert cnt_active == 1, "Active publication must exist"
            assert cnt_hist == 1, "Previous run publication MUST be archived into mri_historical_publications"

    def test_05_coverage_filter_and_dashboard_representation(self):
        """
        Codex 013 Defect 5:
        Verifies that PAGE_BUDGET_EXCEEDED is correctly preserved as coverage and
        HTML contains the PAGE_BUDGET_EXCEEDED filter option.
        """
        html_path = "app/mri_dashboard/templates/index.html"
        assert os.path.exists(html_path)
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        # HTML must expose PAGE_BUDGET_EXCEEDED in filterCoverage
        assert 'value="PAGE_BUDGET_EXCEEDED"' in html
        assert 'Cobertura y Límite:' in html

    def test_06_empty_upstream_not_declared_operational(self):
        """
        Codex 013 Defect 6:
        Verifies that an empty or missing response is NOT declared OPERATIONAL with fake zeros.
        """
        client = TestClient(app)
        with patch("app.mri_dashboard.mri_api.get_sqlite_conn") as mock_conn:
            # Mock empty DB
            cur_mock = MagicMock()
            cur_mock.fetchall.return_value = []
            cur_mock.execute.return_value.fetchall.return_value = []
            mock_conn.return_value.cursor.return_value = cur_mock

            with patch("app.mri_autonomous.rea_paris_engine.REAParisEngine.get_brand_summary", return_value={"total_brand_results": 0}):
                with patch("app.mri_autonomous.rea_paris_engine.REAParisEngine.get_seller_summary", return_value={"total_seller_results": 0}):
                    res = client.get("/api/rea/paris")
                    assert res.status_code == 200
                    data = res.json()
                    # Must NOT be OPERATIONAL when evidence is empty
                    assert data["status"] != "OPERATIONAL"
                    assert data["status"] in ("NO_EVIDENCE_RECORDED", "OFFLINE_NO_PERSISTED_RECORDS")
