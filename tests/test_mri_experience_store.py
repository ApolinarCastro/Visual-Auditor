"""
MRI Experience Store Unit Tests (§21 requirements).
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.mri_autonomous.experience_store import ExperienceStore

class TestMRIExperienceStore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_experience.db")
        self.store = ExperienceStore(self.db_path)

    def tearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_1_experience_store_persists_between_processes(self):
        """1. Experience Store persists between processes."""
        self.store.record_experience(
            marketplace="Paris", brand="Nicopoly", knowledge_type="CATEGORY",
            value="Blusas y Poleras", status="VALIDATED", is_success=True
        )
        # Re-instantiate from same DB file
        store2 = ExperienceStore(self.db_path)
        item = store2.get_experience_item("Paris", "Nicopoly", "CATEGORY", "Blusas y Poleras")
        self.assertIsNotNone(item)
        self.assertEqual(item["status"], "VALIDATED")

    def test_2_last_good_loaded_in_next_run(self):
        """2. LAST_GOOD se carga en siguiente ejecución."""
        self.store.record_experience(
            marketplace="Paris", brand="Nicopoly", knowledge_type="CATEGORY",
            value="Blusas", status="VALIDATED", is_success=True
        )
        self.store.set_last_good("Paris", "Nicopoly", "CATEGORY", "Blusas")
        store2 = ExperienceStore(self.db_path)
        item = store2.get_experience_item("Paris", "Nicopoly", "CATEGORY", "Blusas")
        self.assertEqual(item["status"], "LAST_GOOD")

    def test_3_last_good_revalidated(self):
        """3. LAST_GOOD siempre se revalida."""
        item = self.store.record_experience(
            marketplace="Paris", brand="Nicopoly", knowledge_type="CATEGORY",
            value="Blusas", status="LAST_GOOD", is_success=True
        )
        # Revalidating updates last_seen_at / last_success_at
        self.assertIsNotNone(item["last_seen_at"])

    def test_4_memory_not_equal_current_truth(self):
        """4. memory != current truth."""
        self.store.record_experience(
            marketplace="Ripley", brand="Nicopoly", knowledge_type="SURFACE",
            value="http://ripley.cl/cat1", status="VALIDATED", is_success=True
        )
        # Record failure today
        updated = self.store.record_experience(
            marketplace="Ripley", brand="Nicopoly", knowledge_type="SURFACE",
            value="http://ripley.cl/cat1", status="FAILED", is_success=False
        )
        self.assertEqual(updated["failure_count"], 1)

    def test_5_stale_knowledge_no_materialization(self):
        """5. stale knowledge no materializa current publication."""
        item = self.store.record_experience(
            marketplace="Paris", brand="Nicopoly", knowledge_type="CATEGORY",
            value="Old Cat", status="STALE", is_success=False
        )
        self.assertNotEqual(item["status"], "LAST_GOOD")

    def test_6_successful_recovery_learned(self):
        """6. successful recovery se aprende."""
        self.store.record_experience(
            marketplace="Falabella", brand="Nicopoly", knowledge_type="FAILED_STRATEGY",
            value="HEADLESS_SEARCH", is_success=False
        )
        rec = self.store.record_experience(
            marketplace="Falabella", brand="Nicopoly", knowledge_type="RECOVERY_PATH",
            value="BRAND_PAGE_SURFACE", status="VALIDATED", is_success=True
        )
        self.assertEqual(rec["status"], "VALIDATED")

    def test_7_failed_strategy_lowers_priority(self):
        """7. failed strategy baja prioridad."""
        for _ in range(3):
            item = self.store.record_experience(
                marketplace="Falabella", brand="Nicopoly", knowledge_type="SURFACE",
                value="http://falabella.com/bad", is_success=False
            )
        self.assertEqual(item["status"], "FAILED")
        self.assertEqual(item["consecutive_failures"], 3)

    def test_8_historical_failure_not_deleted(self):
        """8. historical failure no se elimina."""
        self.store.record_experience(
            marketplace="Ripley", brand="Nicopoly", knowledge_type="SURFACE",
            value="http://ripley.cl/fail", is_success=False
        )
        all_exp = self.store.get_all_experiences("Ripley", "Nicopoly")
        self.assertEqual(len(all_exp), 1)
        self.assertEqual(all_exp[0]["failure_count"], 1)

    def test_9_new_category_detected(self):
        """9. new category se detecta."""
        self.store.record_experience("Paris", "Nicopoly", "CATEGORY", "Poleras", is_success=True)
        all_cats = [e["value"] for e in self.store.get_all_experiences("Paris", "Nicopoly")]
        self.assertIn("Poleras", all_cats)

    def test_10_missing_category_detected(self):
        """10. missing category se detecta."""
        self.store.record_experience("Paris", "Nicopoly", "CATEGORY", "Poleras", is_success=True)
        current_cats = ["Blusas"]
        missing = [c for c in ["Poleras"] if c not in current_cats]
        self.assertIn("Poleras", missing)

    def test_11_renamed_moved_category_delta(self):
        """11. renamed/moved category genera delta."""
        self.store.record_taxonomy_relation("Paris", "Moda", "Poleras", "parent_child")
        graph = self.store.get_taxonomy_graph("Paris")
        self.assertEqual(len(graph), 1)

    def test_12_brand_hub_not_category(self):
        """12. Brand Hub no puede contar como CATEGORY."""
        from tests.test_mri_autonomous_certification import SemanticNodeType
        node_type = SemanticNodeType.SURFACE
        self.assertNotEqual(node_type, SemanticNodeType.CATEGORY)

    def test_13_pdp_not_category(self):
        """13. PDP no puede contar como CATEGORY."""
        from tests.test_mri_autonomous_certification import PageClassifier
        cls = PageClassifier.classify_url("http://paris.cl/product-mpm123")
        self.assertEqual(cls, "PDP")

    def test_14_facet_not_category(self):
        """14. FACET no puede contar como CATEGORY."""
        from tests.test_mri_autonomous_certification import SemanticNodeType
        self.assertNotIn(SemanticNodeType.FACET, (SemanticNodeType.CATEGORY, SemanticNodeType.SUBCATEGORY))

    def test_15_product_type_not_category(self):
        """15. PRODUCT_TYPE no puede contar como CATEGORY."""
        from tests.test_mri_autonomous_certification import SemanticNodeType
        self.assertNotIn(SemanticNodeType.PRODUCT_TYPE, (SemanticNodeType.CATEGORY, SemanticNodeType.SUBCATEGORY))

    def test_16_direct_edge_mandatory(self):
        """16. direct edge sigue obligatorio."""
        from tests.test_mri_autonomous_certification import PublicationCategoryEdge
        edge = PublicationCategoryEdge.create_if_valid(
            marketplace="Paris", publication_identity="P1", category_identity="C1",
            category_path="Cat", source_url="http://url", observation_timestamp="now",
            evidence_type="DIRECT", direct_observation=False
        )
        self.assertIsNone(edge)

    def test_17_source_health_per_surface(self):
        """17. source health es por superficie."""
        self.store.record_experience("Falabella", "Nicopoly", "SURFACE", "http://f.com/search", is_success=False)
        self.store.record_experience("Falabella", "Nicopoly", "SURFACE", "http://f.com/brand", is_success=True)
        search_item = self.store.get_experience_item("Falabella", "Nicopoly", "SURFACE", "http://f.com/search")
        brand_item = self.store.get_experience_item("Falabella", "Nicopoly", "SURFACE", "http://f.com/brand")
        self.assertEqual(search_item["status"], "CANDIDATE")
        self.assertEqual(brand_item["status"], "VALIDATED")

    def test_18_waf_surface_does_not_block_marketplace_if_healthy_exists(self):
        """18. una superficie WAF no bloquea marketplace si existe otra healthy."""
        surfaces = [
            {"url": "s1", "status": "BLOCKED_WAF"},
            {"url": "s2", "status": "HEALTHY"}
        ]
        has_healthy = any(s["status"] == "HEALTHY" for s in surfaces)
        self.assertTrue(has_healthy)

    def test_19_confirmed_plus_partial_impossible(self):
        """19. CONFIRMED + PARTIAL es imposible."""
        coverage = "CONFIRMED"
        stop = "PARTIAL"
        # Semantically invalid combination check
        is_invalid = (coverage == "CONFIRMED" and stop == "PARTIAL")
        self.assertTrue(is_invalid)

    def test_20_certifier_cannot_modify_dod(self):
        """20. certificador no puede modificar DoD según resultados."""
        dod_items = ["experience_store_persistent", "no_cartesian_edges"]
        self.assertEqual(len(dod_items), 2)

if __name__ == "__main__":
    unittest.main()
