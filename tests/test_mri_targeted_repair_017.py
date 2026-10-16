"""
tests/test_mri_targeted_repair_017.py

Targeted Test Suite for MRI-TARGETED-REPAIR-017.
Verifies the exact three material defects identified in MRI_CODEX_CRITICAL_VALIDATION_016:

1. Defect F1: Primary HAR Provenance & Integrity
   - Verification of primary HAR file reference: path, SHA-256 recalculation, original declared capture date.
   - Separate capture timestamp (observed_at) from normalization/processing timestamp.
   - Declarative incomplete provenance when source data lacks verified evidence.

2. Defect F2: Run-Scoped Category Memberships Isolation
   - Category memberships in mri_publication_categories must not leak stale links into subsequent runs.
   - Run 1 and Run 2 on the same publication preserve their respective categories independently.
   - No leftover stale ACTIVE category links across runs.

3. Defect F3: Explicit Representation of UNKNOWN / null Counts
   - Empty or unverifiable upstream response returns null/UNKNOWN commercial totals.
   - Value 0 is reserved strictly for certified zero-result responses.
   - Both persistence, API (/api/rea/paris), and dashboard respect the distinction.
"""

import os
import json
import sqlite3
import hashlib
import pathlib
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.mri_autonomous.storage_guard import StorageConfig
from app.mri_autonomous.rea_paris_engine import REAParisEngine, NormalizedPublication
from app.mri_dashboard.mri_api import app, fetch_run_publications


class TestMRITargetedRepair017:

    @pytest.fixture(autouse=True)
    def setup_sandbox(self, tmp_path):
        sandbox = str(tmp_path / "mri_017_sandbox")
        StorageConfig.set_test_mode(True, sandbox_dir=sandbox)
        os.environ["MRI_ENV"] = "TEST"
        yield
        StorageConfig.set_test_mode(False)
        if "MRI_ENV" in os.environ:
            del os.environ["MRI_ENV"]

    def _init_sqlite_schema(self, db_path: str):
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mri_runs (
                    run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, marketplace TEXT,
                    brand TEXT, execution_mode TEXT, truth_model_version TEXT, terminal_state TEXT,
                    source_method TEXT, status TEXT, created_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mri_publications (
                    publication_id TEXT PRIMARY KEY, product_id TEXT, marketplace TEXT, marketplace_product_id TEXT,
                    canonical_url TEXT, status TEXT, observed_at TEXT, run_id TEXT, position INTEGER, surface TEXT,
                    position_state TEXT, category_relationship TEXT, evidence_type TEXT, raw_source_id TEXT,
                    acquisition_status TEXT, identity_status TEXT, category_observed TEXT,
                    category_source TEXT, category_expected TEXT, category_decision TEXT, commercial_attributes TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mri_historical_publications (
                    history_id TEXT PRIMARY KEY, publication_id TEXT, product_id TEXT, marketplace TEXT, marketplace_product_id TEXT,
                    canonical_url TEXT, status TEXT, observed_at TEXT, run_id TEXT, position INTEGER, surface TEXT,
                    position_state TEXT, category_relationship TEXT, evidence_type TEXT, raw_source_id TEXT,
                    acquisition_status TEXT, identity_status TEXT, category_observed TEXT,
                    category_source TEXT, category_expected TEXT, category_decision TEXT, commercial_attributes TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mri_categories (
                    category_id TEXT PRIMARY KEY, marketplace TEXT, category_name TEXT, canonical_url TEXT, created_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mri_publication_categories (
                    publication_id TEXT, category_id TEXT, status TEXT, observed_at TEXT, PRIMARY KEY(publication_id, category_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mri_historical_publication_categories (
                    history_id TEXT PRIMARY KEY, publication_id TEXT, category_id TEXT, run_id TEXT, observed_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mri_products (
                    product_id TEXT PRIMARY KEY, canonical_brand TEXT, product_status TEXT, created_at TEXT
                )
            """)

    def test_01_har_provenance_integrity_and_capture_date(self, tmp_path):
        """
        Codex 016 Defect F1:
        1. Verifies SHA-256 recalculation against primary evidence.
        2. Recovers declared capture date ('startedDateTime') separate from normalization date.
        3. Persists verifiable reference to file path and SHA-256.
        """
        db = str(tmp_path / "test_f1.db")
        self._init_sqlite_schema(db)
        engine = REAParisEngine()

        har_path = pathlib.Path("evidence/mri_rea_discovery_010/paris_search_capture.har").resolve()
        assert har_path.exists(), "Committed HAR evidence must exist"
        expected_sha = hashlib.sha256(har_path.read_bytes()).hexdigest()
        assert expected_sha == "1ed56cc6a9453d6b67a64f6c7566b2496a2294db661ff3f7fc3e9e5077483ed9"

        har_data = json.loads(har_path.read_text(encoding="utf-8"))
        entry = har_data["log"]["entries"][0]
        feed = json.loads(entry["response"]["content"]["text"])
        declared_capture = entry["startedDateTime"]

        with patch.object(engine, "browse", return_value=feed):
            pubs, ents = engine.harvest_sample_publications(max_items=5)

        pub = pubs[0]
        assert pub.evidence_type == "CONTROLLED_REPLAY"
        assert pub.source_file_sha256 == expected_sha
        assert pub.source_captured_at == declared_capture
        assert expected_sha[:16] in pub.raw_source_id

        # Persist and check database columns & attributes
        engine.persist_to_mri_sqlite(pubs, ents, "run_f1_test", db_path=db)

        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM mri_publications WHERE publication_id = ?", (pub.publication_id,)).fetchone()
            assert row is not None
            assert row["evidence_type"] == "CONTROLLED_REPLAY"
            assert expected_sha[:16] in row["raw_source_id"]
            # Observed at matches declared capture date, not execution date
            assert row["observed_at"] == declared_capture

            attrs = json.loads(row["commercial_attributes"])
            assert attrs.get("source_file_sha256") == expected_sha
            assert attrs.get("source_captured_at") == declared_capture

    def test_02_run_scoped_memberships_isolation(self, tmp_path):
        """
        Codex 016 Defect F2:
        1. Run 1 on publication has categories [CatA, CatB].
        2. Run 2 on same publication has only category [CatC].
        3. mri_publication_categories must NOT retain stale links [CatA, CatB] as ACTIVE for Run 2.
        4. Category memberships are strictly isolated and preserved by run.
        """
        db = str(tmp_path / "test_f2.db")
        self._init_sqlite_schema(db)
        engine = REAParisEngine()

        pub_id = "PARIS-MKRMXN8EXC"

        # Run 1: two categories
        pub1 = NormalizedPublication(
            publication_id=pub_id,
            marketplace="Paris",
            sku="MKRMXN8EXC",
            title="Enterito Pabilo Burdeos Nicopoly",
            brand="Nicopoly",
            sellers=["NICOPOLY"],
            is_official_seller=True,
            price_regular=None,
            price_displayed=19990.0,
            discount_percentage=50.0,
            condition="new",
            canonical_url="https://www.paris.cl/enterito-pabilo-burdeos-nicopoly-MKRMXN8EXC.html",
            categories=[
                {"group_id": "mujModEnteritosJardineras", "name": "Enteritos y Jardineras", "path": "/moda/enteritos"},
                {"group_id": "mujMrcNicopoly", "name": "Nicopoly", "path": "/moda/marcas"}
            ],
            promotions=["promo1"]
        )

        engine.persist_to_mri_sqlite([pub1], [], "audit017_rea_1", db_path=db)

        with sqlite3.connect(db) as conn:
            links1 = conn.execute("SELECT category_id, status FROM mri_publication_categories WHERE publication_id = ?", (pub_id,)).fetchall()
            assert len(links1) == 2
            assert all(status == "ACTIVE" for _, status in links1)
            cat_ids_1 = {cat_id for cat_id, _ in links1}
            assert "PARIS_mujModEnteritosJardineras" in cat_ids_1
            assert "PARIS_mujMrcNicopoly" in cat_ids_1

        # Run 2: exactly one single different category
        pub2 = NormalizedPublication(
            publication_id=pub_id,
            marketplace="Paris",
            sku="MKRMXN8EXC",
            title="Enterito Pabilo Burdeos Nicopoly",
            brand="Nicopoly",
            sellers=["Vopero"],
            is_official_seller=False,
            price_regular=None,
            price_displayed=19990.0,
            discount_percentage=50.0,
            condition="new",
            canonical_url="https://www.paris.cl/enterito-pabilo-burdeos-nicopoly-MKRMXN8EXC.html",
            categories=[
                {"group_id": "AUDIT016_SECOND_CATEGORY", "name": "Categoría control segunda corrida", "path": "/audit-fixture"}
            ],
            promotions=["AUDIT016_SECOND_PROMOTION"]
        )

        engine.persist_to_mri_sqlite([pub2], [], "audit017_rea_2", db_path=db)

        with sqlite3.connect(db) as conn:
            # Active links must ONLY contain the new run's categories
            active_links = conn.execute("SELECT category_id FROM mri_publication_categories WHERE publication_id = ? AND status = 'ACTIVE'", (pub_id,)).fetchall()
            assert len(active_links) == 1, f"Expected exactly 1 active category, found: {active_links}"
            assert active_links[0][0] == "PARIS_AUDIT016_SECOND_CATEGORY"

            # Historical links table must retain previous run memberships
            hist_links = conn.execute("SELECT category_id, run_id FROM mri_historical_publication_categories WHERE publication_id = ?", (pub_id,)).fetchall()
            assert len(hist_links) == 2
            assert all(run == "audit017_rea_1" for _, run in hist_links)

    def test_03_empty_source_returns_unknown_null_counts(self):
        """
        Codex 016 Defect F3:
        1. When upstream source returns empty {} and SQLite has no rows,
           endpoint /api/rea/paris returns status 'NO_EVIDENCE_RECORDED'.
        2. Commercial totals (total_brand, total_official_seller, other_sellers_total)
           MUST be explicitly null/None, not converted to 0.
        """
        client = TestClient(app)

        with patch("app.mri_dashboard.mri_api.get_sqlite_conn") as mock_conn:
            cur_mock = MagicMock()
            cur_mock.fetchall.return_value = []
            cur_mock.execute.return_value.fetchall.return_value = []
            mock_conn.return_value.cursor.return_value = cur_mock

            # Upstream JSON fixture is {} (empty responses)
            with patch("app.mri_autonomous.rea_paris_engine.REAParisEngine._get_json", return_value={}):
                res = client.get("/api/rea/paris")
                assert res.status_code == 200
                data = res.json()

                assert data["status"] == "NO_EVIDENCE_RECORDED"
                assert data["total_brand"] is None, f"Expected null, got {data['total_brand']}"
                assert data["total_official_seller"] is None, f"Expected null, got {data['total_official_seller']}"
                assert data["other_sellers_total"] is None, f"Expected null, got {data['other_sellers_total']}"
