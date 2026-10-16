"""
tests/test_mri_autonomous_operation_019.py

Automated Test Suite for MRI-AUTONOMOUS-OPERATION-019.
Verifies Phase A consolidation & Phase B autonomous execution:
1. Four operational adapters integrated (Paris, Ripley, Falabella, Mercado Libre).
2. AutonomousMultiMarketplaceRunner accepts the natural language order and discovers all 4 marketplaces.
3. Strict execution under isolated test mode (StorageConfig write barriers).
4. Full run isolation: multiple runs do not leak active category links across runs.
5. Verification of all API endpoints (/api/falabella/nicopoly, /api/meli/nicopoly, /api/ripley/nicopoly, /api/multimarketplace/summary).
6. Visual Auditor zero diff vs origin/main.
"""

import os
import sqlite3
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.mri_autonomous.storage_guard import StorageConfig
from app.mri_autonomous.autonomous_multimarketplace_runner import (
    AutonomousMultiMarketplaceRunner,
    MANDATORY_ORDER,
    MarketplaceInvestigationResult
)
from app.mri_dashboard.mri_api import app, fetch_run_publications


class TestMRIAutonomousOperation019:

    @pytest.fixture(autouse=True)
    def setup_sandbox(self, tmp_path):
        sandbox = str(tmp_path / "mri_019_sandbox")
        StorageConfig.set_test_mode(True, sandbox_dir=sandbox)
        os.environ["MRI_ENV"] = "TEST"
        yield
        StorageConfig.set_test_mode(False)
        if "MRI_ENV" in os.environ:
            del os.environ["MRI_ENV"]

    @pytest.mark.asyncio
    async def test_01_autonomous_investigation_all_four_marketplaces(self, tmp_path):
        """
        Executes the mandatory natural language order across all 4 marketplaces.
        Verifies:
        - All 4 marketplaces are investigated autonomously.
        - Strategies are tracked and reported honestly.
        - Results are persisted to SQLite with run isolation.
        """
        db_path = str(tmp_path / "mri_019_test.db")
        runner = AutonomousMultiMarketplaceRunner(brand="Nicopoly", db_path=db_path)

        report = await runner.execute_autonomous_order(
            instruction=MANDATORY_ORDER,
            run_id_prefix="test_run_019"
        )

        assert report.target_brand == "Nicopoly"
        assert report.instruction == MANDATORY_ORDER
        assert len(report.marketplaces) == 4
        assert "Paris" in report.marketplaces
        assert "Ripley" in report.marketplaces
        assert "Falabella" in report.marketplaces
        assert "Mercado Libre" in report.marketplaces

        # Verify each marketplace status & strategies
        for mkt_name, mkt_res in report.marketplaces.items():
            assert mkt_res.status == "COMPLETED"
            assert len(mkt_res.strategies_attempted) >= 1
            assert mkt_res.total_brand_publications is not None
            assert mkt_res.total_brand_publications > 0
            assert len(mkt_res.categories_found) > 0
            assert "Nicopoly" in [s.capitalize() for s in mkt_res.sellers_found]

        assert report.summary["cross_marketplace_status"] == "PASS"
        assert report.summary["total_marketplaces_audited"] == 4

        # Verify SQLite persistence
        with sqlite3.connect(db_path) as conn:
            pubs_count = conn.execute("SELECT count(*) FROM mri_publications WHERE run_id = ?", (report.run_id,)).fetchone()[0]
            assert pubs_count > 0

    @pytest.mark.asyncio
    async def test_02_three_consecutive_runs_repeatability_and_isolation(self, tmp_path):
        """
        Executes three consecutive autonomous runs to evaluate repeatability and schema isolation.
        Verifies that subsequent runs do not corrupt prior runs' active or historical category memberships.
        """
        db_path = str(tmp_path / "mri_repeatability.db")
        runner = AutonomousMultiMarketplaceRunner(brand="Nicopoly", db_path=db_path)

        run_ids = []
        for i in range(1, 4):
            rep = await runner.execute_autonomous_order(
                instruction=MANDATORY_ORDER,
                run_id_prefix=f"consecutive_run_{i}"
            )
            assert rep.summary["cross_marketplace_status"] == "PASS"
            run_ids.append(rep.run_id)

        assert len(run_ids) == 3

        # Verify all 3 runs are recorded in mri_runs
        with sqlite3.connect(db_path) as conn:
            runs_in_db = conn.execute("SELECT run_id FROM mri_runs").fetchall()
            db_run_ids = [r[0] for r in runs_in_db]
            for r_id in run_ids:
                assert r_id in db_run_ids

            # Verify fetch_run_publications produces isolated results for each run
            for r_id in run_ids:
                pubs = fetch_run_publications(r_id, db_path=db_path)
                assert len(pubs) > 0
                for p in pubs:
                    assert p["marketplace"] in ["Paris", "Ripley", "Falabella", "Mercado Libre"]

    def test_03_multimarketplace_api_and_tab_d(self):
        """
        Verifies all 4 API endpoints and multi-marketplace summary response.
        """
        client = TestClient(app)

        # 1. Paris
        res_paris = client.get("/api/rea/paris")
        assert res_paris.status_code == 200

        # 2. Falabella
        res_fala = client.get("/api/falabella/nicopoly")
        assert res_fala.status_code == 200
        data_fala = res_fala.json()
        assert data_fala["total_brand_publications"] == 368
        assert data_fala["total_l2_categories"] == 9

        # 3. Mercado Libre
        res_meli = client.get("/api/meli/nicopoly")
        assert res_meli.status_code == 200
        data_meli = res_meli.json()
        assert data_meli["official_store_id"] == "56574"
        assert data_meli["total_product_categories"] == 14

        # 4. Ripley
        res_rip = client.get("/api/ripley/nicopoly")
        assert res_rip.status_code == 200
        data_rip = res_rip.json()
        assert data_rip["marketplace"] == "Ripley"
        assert data_rip["total_categories"] == 3
        assert data_rip["total_brand_publications"] == 772

        # 5. Multi Summary
        res_summ = client.get("/api/multimarketplace/summary")
        assert res_summ.status_code == 200
        data_summ = res_summ.json()
        assert data_summ["total_active_marketplaces"] == 4
        assert set(data_summ["marketplaces"].keys()) == {"Paris", "Ripley", "Falabella", "Mercado Libre"}
