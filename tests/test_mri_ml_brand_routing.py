"""
TDD Tests for MRI-ML-BRAND-ROUTING-001:
Mercado Libre autonomous brand routing and category discovery.

FASE 1 — TEST ROJO:
Must reproduce demonstrated failures before production changes.
"""

import sys
import os
import unittest
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestMercadoLibreBrandRoutingRed(unittest.IsolatedAsyncioTestCase):

    def test_ml_01_reject_non_commercial_address_navigation(self):
        """TEST ML-01: addresses/v3/navigation/hub?go=... NO puede clasificarse como categoría comercial.
        Debe ser rechazada como navegación no comercial / GENERAL_NAVIGATION / CORPORATE_NAVIGATION.
        """
        from app.mri_autonomous.surface_classifier import classify_surface

        address_url = (
            "https://www.mercadolibre.cl/addresses/v3/navigation/hub"
            "?go=https%3A%2F%2Flistado.mercadolibre.cl%2Ftienda%2Fnicopoly%2Fnicopoly"
        )
        cls = classify_surface(address_url, {"brand": "nicopoly"})

        # Initial expectation: FAIL because current classifier marks len(segs) >= 2 as COMMERCIAL_CATEGORY
        self.assertNotEqual(
            cls["surface_type"],
            "COMMERCIAL_CATEGORY",
            f"Address hub must not be classified as COMMERCIAL_CATEGORY: {cls}",
        )
        self.assertIn(
            cls["surface_type"],
            ("GENERAL_NAVIGATION", "CORPORATE_NAVIGATION", "UNKNOWN"),
            f"Address hub should be classified as non-commercial navigation: {cls}",
        )

    def test_ml_02_discover_commercial_category_from_official_store(self):
        """TEST ML-02: Dada una representación realista de la Tienda Oficial con categorías/facetas comerciales:
        MRI debe producir al menos una categoría comercial válida con nombre real y no 'Nicopoly Tienda Nicopoly'.
        """
        from app.mri_autonomous.category_discoverer import category_name_from_url

        url_ropa = "https://listado.mercadolibre.cl/ropa-accesorios/nicopoly_Tienda_nicopoly"
        url_vestidos = "https://listado.mercadolibre.cl/vestidos/nicopoly_Tienda_nicopoly"

        name_ropa = category_name_from_url(url_ropa)
        name_vestidos = category_name_from_url(url_vestidos)

        # Initial expectation: FAIL because category_name_from_url currently returns 'Nicopoly Tienda Nicopoly'
        self.assertNotIn("Nicopoly Tienda Nicopoly", name_ropa, "Category name must not be store name")
        self.assertNotIn("Nicopoly Tienda Nicopoly", name_vestidos, "Category name must not be store name")
        self.assertEqual(name_ropa.lower(), "ropa accesorios")
        self.assertEqual(name_vestidos.lower(), "vestidos")

    def test_ml_03_preserve_provenance_and_dynamic_brand(self):
        """TEST ML-03: La categoría descubierta debe conservar provenance y NO depender del literal 'Nicopoly'.
        FACET_SELECTORS y la extracción deben funcionar dinámicamente para marcas como 'kross' o 'acme'.
        """
        from app.mri_autonomous.category_discoverer import FACET_SELECTORS, category_name_from_url

        # Check FACET_SELECTORS does not hardcode 'nicopoly'
        ml_selectors = FACET_SELECTORS.get("Mercado Libre", [])
        for sel in ml_selectors:
            self.assertNotIn(
                "nicopoly",
                sel.lower(),
                f"FACET_SELECTORS for Mercado Libre contains hardcoded 'nicopoly': {sel}",
            )

        # Dynamic brand category derivation
        acme_cat_url = "https://listado.mercadolibre.cl/herramientas/acme_Tienda_acme"
        acme_name = category_name_from_url(acme_cat_url)
        self.assertEqual(acme_name.lower(), "herramientas")

    def test_ml_04_brand_discovery_event_emits_brand_evidence_count(self):
        """TEST ML-04: BRAND_DISCOVERY no puede depender exclusivamente de una clave de evento que el pipeline no emite.
        category_done debe emitir 'brand_evidence_count_text' con el conteo de productos de la marca observados.
        """
        from app.mri_autonomous.autonomous_pipeline import make_category_done_payload

        payload = make_category_done_payload(
            marketplace="Mercado Libre",
            batch_number=1,
            batch_started_at="2026-09-29T12:00:00",
            category_name="Ropa y Accesorios",
            category_url="https://listado.mercadolibre.cl/ropa-accesorios/nicopoly_Tienda_nicopoly",
            pages_traversed=1,
            stop_reason="EXHAUSTION",
            failure_type=None,
            raw_count=48,
            new_unique_count=48,
            cumulative_unique_count=48,
            products=[{"title": "Vestido Nicopoly Fiesta", "vendor": "Nicopoly"}],
            brand_evidence_count=48,
        )

        self.assertIn(
            "brand_evidence_count_text",
            payload,
            "category_done event MUST contain 'brand_evidence_count_text' to prevent false BRAND_DISCOVERY FAIL",
        )
        self.assertEqual(payload["brand_evidence_count_text"], 48)
        self.assertEqual(payload["brand_present"], 48)

    async def test_ml_05_mock_page_discovery_official_store(self):
        """TEST ML-05: Validar que discover_categories_from_page extraiga categorías comerciales
        y descarte URLs no comerciales (/addresses/v3/navigation/hub).
        """
        from unittest.mock import AsyncMock
        from app.mri_autonomous.category_discoverer import discover_categories_from_page

        mock_page = AsyncMock()
        mock_anchors = [
            # Non-commercial address hub link
            {
                "href": "https://www.mercadolibre.cl/addresses/v3/navigation/hub?go=https%3A%2F%2Flistado.mercadolibre.cl%2Ftienda%2Fnicopoly%2Fnicopoly",
                "text": "Enviar a",
                "cls": "nav-menu-cp",
            },
            # Store root (hub) itself - should not be extracted as subcategory
            {
                "href": "https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly",
                "text": "Nicopoly",
                "cls": "ui-search-breadcrumb__title",
            },
            # Real commercial subcategories
            {
                "href": "https://listado.mercadolibre.cl/ropa-accesorios/nicopoly_Tienda_nicopoly",
                "text": "Ropa y Accesorios (540)",
                "cls": "ui-search-link",
            },
            {
                "href": "https://listado.mercadolibre.cl/vestidos/nicopoly_Tienda_nicopoly",
                "text": "Vestidos (120)",
                "cls": "ui-search-link",
            },
        ]
        mock_page.evaluate.return_value = mock_anchors

        cats = await discover_categories_from_page(
            mock_page,
            marketplace="Mercado Libre",
            hub_url="https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly",
            brand="Nicopoly",
        )

        self.assertNotIn(
            "https://www.mercadolibre.cl/addresses/v3/navigation/hub?go=https%3A%2F%2Flistado.mercadolibre.cl%2Ftienda%2Fnicopoly%2Fnicopoly",
            cats,
            "Address navigation hub MUST be rejected",
        )
        self.assertIn("https://listado.mercadolibre.cl/ropa-accesorios/nicopoly_Tienda_nicopoly", cats)
        self.assertIn("https://listado.mercadolibre.cl/vestidos/nicopoly_Tienda_nicopoly", cats)

    async def test_ml_06_generalization_non_nicopoly_brand(self):
        """TEST ML-06 (FASE 6): Demostrar que el mecanismo usa runtime brand dinámico y no depende de 'Nicopoly'."""
        from unittest.mock import AsyncMock
        from app.mri_autonomous.category_discoverer import discover_categories_from_page, category_name_from_url

        mock_page = AsyncMock()
        mock_anchors = [
            {
                "href": "https://listado.mercadolibre.cl/cervezas/kross_Tienda_kross",
                "text": "Cervezas (30)",
                "cls": "ui-search-link",
            },
            {
                "href": "https://listado.mercadolibre.cl/vasos/kross_Tienda_kross",
                "text": "Vasos y Copas (10)",
                "cls": "ui-search-link",
            },
        ]
        mock_page.evaluate.return_value = mock_anchors

        cats = await discover_categories_from_page(
            mock_page,
            marketplace="Mercado Libre",
            hub_url="https://listado.mercadolibre.cl/kross_Tienda_kross",
            brand="Kross",
        )

        self.assertEqual(len(cats), 2)
        self.assertEqual(category_name_from_url(cats[0]).lower(), "cervezas")
        self.assertEqual(category_name_from_url(cats[1]).lower(), "vasos")


if __name__ == "__main__":
    unittest.main()
