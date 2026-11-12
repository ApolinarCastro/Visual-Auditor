"""Deterministic tests for root taxonomy adapters (MRI-ROOT-TAXONOMY-002)."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.mri_autonomous.taxonomy_roots import (
    classify_falabella_candidate,
    discover_falabella_roots,
    discover_meli_roots,
    discover_paris_roots_from_urls,
    discover_ripley_roots_from_urls,
    parse_falabella_hierarchy,
    persist_falabella_root_snapshot,
)
from app.mri_autonomous.taxonomy_store import (
    FRONTIER_TABLE,
    apply_taxonomy_migration,
    persist_taxonomy_snapshot,
)


class FakeMeliEngine:
    site_id = "MLC"

    def _request(self, endpoint, params=None):
        if endpoint.endswith("/categories"):
            return 200, [{"id": "ROOT1", "name": "Root"}], "200"
        return 200, {}, "200"

    def get_category_by_id(self, cid):
        data = {
            "ROOT1": {"name": "Root", "children": [{"id": "CHILD1"}]},
            "CHILD1": {"name": "Child", "children": []},
        }[cid]
        return SimpleNamespace(name=data["name"], children=data["children"]), "200"


class FakeFalabellaEngine:
    base_url = "https://www.falabella.com"

    def fetch_page_ssr_data(self, page):
        return {"fake": True}

    def extract_taxonomy_tree(self, payload):
        return [
            SimpleNamespace(category_id="F1", name="Root", parent_id=None,
                            hierarchical_path="Root", canonical_url="https://www.falabella.com/F1"),
            SimpleNamespace(category_id="F2", name="Child", parent_id="F1",
                            hierarchical_path="Root > Child", canonical_url="https://www.falabella.com/F2"),
        ]


class RootTaxonomyTests(unittest.TestCase):
    def test_meli_roots_come_from_api_and_keep_hierarchy(self):
        result = discover_meli_roots(FakeMeliEngine())
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.roots_discovered, 1)
        self.assertEqual(result.nodes_discovered, 2)
        child = next(c for c in result.categories if c["category_id"] == "CHILD1")
        self.assertEqual(child["parent_id"], "ROOT1")
        self.assertIn("Root", child["hierarchical_path"])

    def test_falabella_roots_keep_parent_and_path(self):
        result = discover_falabella_roots(FakeFalabellaEngine(), payload={})
        self.assertEqual(result.status, "PASS")
        child = next(c for c in result.categories if c["category_id"] == "F2")
        self.assertEqual(child["parent_id"], "F1")
        self.assertEqual(child["hierarchical_path"], "Root > Child")

    def test_falabella_root_links_are_real_ssr_roots(self):
        payload = {"page": {"containers": [{
            "url": "https://www.falabella.com/falabella-cl/category/cat20002/Moda-Mujer"
        }]}}
        result = discover_falabella_roots(
            FakeFalabellaEngine(), payload=payload)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.source, "SSR_ROOT_CATEGORY_LINKS")
        self.assertEqual(result.categories[0]["category_id"], "cat20002")
        self.assertIsNone(result.categories[0]["parent_id"])

    def test_ripley_root_urls_filter_foreign_hosts_and_dedupe(self):
        urls = [
            "https://simple.ripley.cl/moda-mujer/vestidos",
            "https://simple.ripley.cl/moda-mujer/vestidos",
            "https://evil.example/ripley-copy",
        ]
        result = discover_ripley_roots_from_urls(urls)
        self.assertEqual(len(result.categories), 1)
        self.assertEqual(result.categories[0]["parent_id"], None)
        self.assertEqual(result.categories[0]["discovery_status"], "NOT_VERIFIED")

    def test_paris_root_urls_are_mri_only_shape(self):
        result = discover_paris_roots_from_urls([
            "https://www.paris.cl/moda-mujer/vestidos",
            "https://www.paris.cl/moda-mujer/vestidos",
        ])
        self.assertEqual(len(result.categories), 1)
        self.assertEqual(result.source, "PARIS_MRI_ROOT_NAVIGATION")
        self.assertIsNone(result.categories[0]["parent_id"])

    def test_roots_persist_through_taxonomy_store(self):
        db = sqlite3.connect(":memory:")
        try:
            apply_taxonomy_migration(db)
            result = discover_falabella_roots(FakeFalabellaEngine(), payload={})
            counts = persist_taxonomy_snapshot(
                db, "Falabella", "run_root_test", result.categories,
                taxonomy_source=result.source, source_evidence="fixture")
            self.assertEqual(counts["roots"], 1)
            self.assertEqual(counts["edges"], 1)
            frontier = db.execute(
                f"SELECT nodes_discovered, edges_verified FROM {FRONTIER_TABLE} "
                "WHERE run_id='run_root_test'").fetchone()
            self.assertEqual(frontier, (2, 1))
        finally:
            db.close()

    def test_falabella_candidate_classification_uses_url_structure(self):
        self.assertEqual(classify_falabella_candidate(
            "https://www.falabella.com/falabella-cl/category/cat1/X"), "CATEGORY_CANDIDATE")
        self.assertEqual(classify_falabella_candidate(
            "https://www.falabella.com/falabella-cl/brand/NICOPOLY"), "BRAND")
        self.assertEqual(classify_falabella_candidate(
            "https://www.falabella.com/falabella-cl/search?Ntt=x"), "SEARCH")
        self.assertEqual(classify_falabella_candidate(
            "https://www.falabella.com/falabella-cl/page/foo"), "NAVIGATION")

    def test_falabella_breadcrumb_edges_are_evidenced(self):
        payload = {"props": {"pageProps": {"breadCrumbData": [
            {"id": "CATG36075", "label": "Vestidos de Fiesta",
             "link": "/category/CATG36075/Vestidos-de-Fiesta", "isRoot": True},
            {"id": "CATG36072", "label": "Ropa de Fiesta",
             "link": "/category/CATG36072/Ropa-de-Fiesta", "isRoot": False},
            {"id": "cat20002", "label": "Mujer - Moda Mujer",
             "link": "/category/cat20002/Moda-Mujer", "isRoot": False},
        ]}}}
        edges = parse_falabella_hierarchy(payload)
        self.assertEqual(len(edges), 2)
        self.assertEqual(edges[0]["child_id"], "CATG36075")
        self.assertEqual(edges[0]["parent_id"], "CATG36072")
        self.assertEqual(edges[1]["child_id"], "CATG36072")
        self.assertEqual(edges[1]["parent_id"], "cat20002")
        self.assertEqual(edges[0]["source_evidence"], "FALABELLA_SSR_BREADCRUMB")

    def test_falabella_special_route_executes_and_persists(self):
        db = sqlite3.connect(":memory:")
        try:
            result, counts = persist_falabella_root_snapshot(
                db, "run_special", FakeFalabellaEngine())
            self.assertEqual(result.status, "PASS")
            self.assertIsNotNone(counts)
            self.assertEqual(counts["nodes"], 2)
            persisted = db.execute(
                "SELECT count(*) FROM mri_taxonomy_nodes "
                "WHERE marketplace='Falabella'").fetchone()[0]
            self.assertEqual(persisted, 2)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
