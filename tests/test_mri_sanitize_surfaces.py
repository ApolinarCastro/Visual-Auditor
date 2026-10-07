"""Unit tests for surface sanitization (no network, no DB).

A facet whose URL is the seed hub URL itself (self-link) must be dropped:
scraping it would duplicate the seed surface rows and fabricate
multi-membership (the Paris 1052/526 case).
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _cat(name, url):
    return {"marketplace": "Paris", "category_name": name, "category_url": url}


class TestSanitizeSurfaces(unittest.TestCase):
    def test_self_link_dropped(self):
        from app.mri_autonomous.autonomous_pipeline import sanitize_surfaces
        hub = "https://www.paris.cl/search?q=nicopoly"
        cats = [_cat("Search", hub), _cat("Outlet Audio", "https://www.paris.cl/outlet/audio/?q=nicopoly")]
        sane, invalid, _ = sanitize_surfaces(cats, "Paris", hub)
        self.assertEqual([c["category_name"] for c in sane], ["Outlet Audio"])
        self.assertEqual(invalid, 1)

    def test_distinct_urls_kept(self):
        from app.mri_autonomous.autonomous_pipeline import sanitize_surfaces
        hub = "https://www.paris.cl/search?q=nicopoly"
        cats = [_cat("A", "https://www.paris.cl/a/?q=nicopoly"),
                _cat("B", "https://www.paris.cl/b/?q=nicopoly")]
        sane, invalid, _ = sanitize_surfaces(cats, "Paris", hub)
        self.assertEqual(len(sane), 2)
        self.assertEqual(invalid, 0)

    def test_ml_facet_variants_rejected(self):
        from app.mri_autonomous.autonomous_pipeline import sanitize_surfaces
        hub = "https://www.mercadolibre.cl/tienda/nicopoly"
        cats = [_cat("F", "https://listado.mercadolibre.cl/x/nicopoly_NoIndex_True")]
        sane, invalid, _ = sanitize_surfaces(cats, "Mercado Libre", hub)
        self.assertEqual(sane, [])
        self.assertEqual(invalid, 1)


if __name__ == "__main__":
    unittest.main()
