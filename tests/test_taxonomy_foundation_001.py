"""Deterministic tests for MRI taxonomy foundation.

Run directly with unittest to avoid the known pytest tmp_path WinError:
    python -m unittest tests.test_taxonomy_foundation_001
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.mri_autonomous.taxonomy_store import (
    FRONTIER_TABLE,
    HISTORY_TABLE,
    MIGRATIONS_TABLE,
    NODES_TABLE,
    TAXONOMY_SCHEMA_VERSION,
    TaxonomyHierarchyError,
    apply_taxonomy_migration,
    persist_taxonomy_snapshot,
    record_taxonomy_learning,
)

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = Path(__file__).resolve().parents[2]
TMP_ROOT = REPO / "evidence_local_validation" / "taxonomy_foundation_001"


class TaxonomyFoundationTests(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = TMP_ROOT / f"case_{uuid.uuid4().hex}"
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.db = self.tmp / "taxonomy.db"
        self.conn = sqlite3.connect(str(self.db))
        self.conn.executescript(
            "CREATE TABLE mri_categories ("
            "category_id TEXT PRIMARY KEY, marketplace TEXT NOT NULL, "
            "category_name TEXT NOT NULL, canonical_url TEXT, created_at TEXT NOT NULL);"
            "INSERT INTO mri_categories VALUES "
            "('cat_old','Falabella','Old category','https://example.invalid/old','2026-01-01');"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_migration_is_idempotent_and_nondestructive(self):
        self.assertEqual(apply_taxonomy_migration(self.conn), TAXONOMY_SCHEMA_VERSION)
        first = self.conn.execute(
            f"SELECT version, checksum FROM {MIGRATIONS_TABLE}").fetchall()
        apply_taxonomy_migration(self.conn)
        second = self.conn.execute(
            f"SELECT version, checksum FROM {MIGRATIONS_TABLE}").fetchall()
        self.assertEqual(first, second)
        self.assertEqual(len(second), 1)
        row = self.conn.execute(
            "SELECT category_id, category_name FROM mri_categories").fetchone()
        self.assertEqual(row, ("cat_old", "Old category"))
        tables = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({NODES_TABLE, HISTORY_TABLE, FRONTIER_TABLE}.issubset(tables))

    def test_existing_operational_copy_is_preserved(self):
        source = WORKSPACE / "data" / "sqlite" / "mri_operational" / "visibility.db"
        if not source.exists():
            self.skipTest("operational DB not present")
        copy = self.tmp / "operational_copy.db"
        shutil.copy2(source, copy)
        con = sqlite3.connect(str(copy))
        before = con.execute("SELECT count(*) FROM mri_categories").fetchone()[0]
        apply_taxonomy_migration(con)
        after = con.execute("SELECT count(*) FROM mri_categories").fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        con.close()

    def test_hierarchy_parent_and_child(self):
        apply_taxonomy_migration(self.conn)
        result = persist_taxonomy_snapshot(
            self.conn, "Falabella", "run_1",
            [
                {"category_id": "root", "name": "Root", "url": "https://x/root"},
                {"category_id": "child", "name": "Child", "parent_id": "root",
                 "url": "https://x/child"},
            ],
            taxonomy_source="TEST", source_evidence="fixture",
        )
        self.assertEqual(result["roots"], 1)
        self.assertEqual(result["edges"], 1)
        self.assertEqual(result["leaves"], 1)
        parent = self.conn.execute(
            f"SELECT parent_category_id, hierarchical_path FROM {NODES_TABLE} "
            "WHERE marketplace='Falabella' AND category_id='child'").fetchone()
        self.assertEqual(parent[0], "root")

    def test_cross_marketplace_parent_is_rejected(self):
        apply_taxonomy_migration(self.conn)
        with self.assertRaises(TaxonomyHierarchyError):
            persist_taxonomy_snapshot(
                self.conn, "Ripley", "run_cross",
                [{"category_id": "child", "name": "Child", "parent_id": "root"}],
            )

    def test_cycle_is_rejected(self):
        apply_taxonomy_migration(self.conn)
        with self.assertRaises(TaxonomyHierarchyError):
            persist_taxonomy_snapshot(
                self.conn, "Ripley", "run_cycle",
                [
                    {"category_id": "a", "name": "A", "parent_id": "b"},
                    {"category_id": "b", "name": "B", "parent_id": "a"},
                ],
            )

    def test_repeated_snapshot_does_not_lose_history(self):
        apply_taxonomy_migration(self.conn)
        nodes = [{"category_id": "root", "name": "Root"}]
        persist_taxonomy_snapshot(self.conn, "Paris", "run_hist", nodes)
        persist_taxonomy_snapshot(self.conn, "Paris", "run_hist",
                                  [{"category_id": "root", "name": "Root renamed"}])
        node = self.conn.execute(
            f"SELECT category_name FROM {NODES_TABLE} "
            "WHERE marketplace='Paris' AND category_id='root'").fetchone()
        self.assertEqual(node[0], "Root renamed")
        history = self.conn.execute(
            f"SELECT count(*) FROM {HISTORY_TABLE} WHERE run_id='run_hist'").fetchone()[0]
        self.assertEqual(history, 1)

    def test_frontier_and_learning(self):
        apply_taxonomy_migration(self.conn)
        persist_taxonomy_snapshot(
            self.conn, "Mercado Libre", "run_front",
            [
                {"category_id": "root", "name": "Root", "discovery_status": "COMPLETE"},
                {"category_id": "blocked", "name": "Blocked",
                 "discovery_status": "BLOCKED"},
            ],
        )
        row = self.conn.execute(
            f"SELECT nodes_discovered, frontier_blocked, frontier_exhausted "
            f"FROM {FRONTIER_TABLE} WHERE run_id='run_front'").fetchone()
        self.assertEqual(row, (2, 1, 1))
        record_taxonomy_learning(
            self.conn, knowledge_id="k1", marketplace="Mercado Libre",
            knowledge_type="BLOCKER", observation="Blocked on page 1",
            source_evidence="run_front", confidence="OBSERVED",
            validation_status="NOT_VERIFIED")
        confidence = self.conn.execute(
            "SELECT confidence, validation_status FROM mri_taxonomy_learning "
            "WHERE knowledge_id='k1'").fetchone()
        self.assertEqual(confidence, ("OBSERVED", "NOT_VERIFIED"))

    def test_consumer_schema_is_unchanged(self):
        before = self.conn.execute("PRAGMA table_info(mri_categories)").fetchall()
        apply_taxonomy_migration(self.conn)
        after = self.conn.execute("PRAGMA table_info(mri_categories)").fetchall()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
