"""Unit tests for the generic surface classifier (no network, no DB).

TDD RED step for the systemic discovery-model fix: navigation/facet links
must never become taxonomy nodes without direct commercial evidence.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestSurfaceClassifierContract(unittest.TestCase):
    def test_pdp_urls_classify_as_pdp(self):
        from app.mri_autonomous.surface_classifier import classify_surface
        for url in [
            "https://simple.ripley.cl/p/12345678",
            "https://www.paris.cl/vestido-lindo-MK123.html",
            "https://www.falabella.com/falabella-cl/product/154330354/",
        ]:
            res = classify_surface(url, {})
            self.assertEqual(res["surface_type"], "PDP", url)

    def test_pagination_variants_detected(self):
        from app.mri_autonomous.surface_classifier import classify_surface
        res = classify_surface("https://listado.mercadolibre.cl/nicopoly_Desde_49", {})
        self.assertEqual(res["surface_type"], "PAGINATION")
        res = classify_surface("https://www.falabella.com/search?Ntt=x&page=2", {})
        self.assertEqual(res["surface_type"], "PAGINATION")

    def test_facet_filter_urls_are_facets_not_categories(self):
        from app.mri_autonomous.surface_classifier import classify_surface
        res = classify_surface("https://www.falabella.com/category/cat2005?f=Brand%3A%3ANicopoly", {})
        self.assertIn(res["surface_type"], ("ATTRIBUTE_FACET", "COMMERCIAL_CATEGORY"))
        res = classify_surface("https://listado.mercadolibre.cl/ropa/nicopoly_NoIndex_True", {})
        self.assertEqual(res["surface_type"], "ATTRIBUTE_FACET")

    def test_fulfillment_signals(self):
        from app.mri_autonomous.surface_classifier import classify_surface
        res = classify_surface("https://www.paris.cl/search?q=x&fulfillment=1", {})
        self.assertEqual(res["surface_type"], "FULFILLMENT_FACET")

    def test_brand_hub_is_brand_surface(self):
        from app.mri_autonomous.surface_classifier import classify_surface
        res = classify_surface("https://www.paris.cl/search?q=nicopoly", {"brand": "nicopoly"})
        self.assertEqual(res["surface_type"], "BRAND_SURFACE")

    def test_category_paths_are_candidates_not_certified(self):
        from app.mri_autonomous.surface_classifier import classify_surface, certify_node
        res = classify_surface("https://www.paris.cl/outlet/outlet-electro/?q=nicopoly", {})
        self.assertEqual(res["surface_type"], "COMMERCIAL_CATEGORY")
        # candidate only: certification requires direct commercial evidence
        self.assertFalse(certify_node(res, products_observed=5, nicopoly_present=0)["certified"])
        self.assertTrue(certify_node(res, products_observed=5, nicopoly_present=3)["certified"])
        self.assertFalse(certify_node(res, products_observed=0, nicopoly_present=0)["certified"])

    def test_corporate_nav_rejected(self):
        from app.mri_autonomous.surface_classifier import classify_surface
        res = classify_surface("https://www.paris.cl/sostenibilidad/estrategia/?q=nicopoly", {})
        self.assertEqual(res["surface_type"], "CORPORATE_NAVIGATION")

    def test_brand_surface_certifies_as_brand_surface_not_category(self):
        from app.mri_autonomous.surface_classifier import classify_surface, certify_node
        res = classify_surface("https://www.paris.cl/search?q=nicopoly", {"brand": "nicopoly"})
        cert = certify_node(res, products_observed=20, nicopoly_present=18)
        self.assertTrue(cert["certified"])
        self.assertEqual(cert["node_type"], "BRAND_SURFACE")

    def test_every_result_has_evidence(self):
        from app.mri_autonomous.surface_classifier import classify_surface
        for url in ["https://www.paris.cl/search?q=nicopoly", "https://x.cl/abc"]:
            res = classify_surface(url, {})
            self.assertTrue(res["evidence"], url)
            self.assertGreaterEqual(res["confidence"], 0.0)
            self.assertLessEqual(res["confidence"], 1.0)


if __name__ == "__main__":
    unittest.main()
