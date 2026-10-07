# -*- coding: utf-8 -*-
"""
Red test suite for MRI-PARIS-BRAND-ROUTING-001
Tests PARIS-01 to PARIS-05 demonstrating gaps before minimal implementation.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

from app.mri_autonomous.surface_classifier import classify_surface
from app.mri_autonomous.category_discoverer import (
    discover_categories_from_page,
    category_name_from_url,
)

# Realistic RSC fixture snippet from live Paris search
PARIS_RSC_FIXTURE_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Nicopoly | Paris.cl</title>
<script>
self.__next_f.push([1,"25c:[\\"$\\",\\"$L25d\\",null,{\\"initialState\\":{\\"productData\\":{\\"statusCode\\":200,\\"total\\":540,\\"products\\":[{\\"name\\":\\"Polera Nicopoly\\",\\"brand\\":\\"Nicopoly\\"}],\\"facets\\":{\\"generalFacets\\":{\\"tipoProductoAll\\":{\\"key\\":\\"tipoProductoAll\\",\\"name\\":\\"Tipo de Producto\\",\\"options\\":[{\\"value\\":\\"Blusas\\",\\"count\\":61,\\"displayName\\":\\"Blusas\\"},{\\"value\\":\\"Chaquetas\\",\\"count\\":134,\\"displayName\\":\\"Chaquetas\\"},{\\"value\\":\\"Vestidos\\",\\"count\\":15,\\"displayName\\":\\"Vestidos\\"}]}}}}}}]);
</script>
</head>
<body>
<main>
  <a href="/search?q=nicopoly&page=2">Mostrar más</a>
  <a href="https://www.paris.cl/mi-cuenta/compras">Mis Compras</a>
  <a href="https://www.paris.cl/iniciar-sesion">Iniciar Sesión</a>
  <a href="https://www.paris.cl/centro-de-ayuda/">Centro de Ayuda</a>
  <a href="https://www.paris.cl/seguimiento-compras">Seguimiento</a>
</main>
</body>
</html>
"""


class TestParisBrandRoutingRed:
    def test_paris_01_reject_noncommercial_navigation(self):
        """PARIS-01: Non-commercial navigation (account, login, help, tracking) must be classified as GENERAL_NAVIGATION."""
        bad_urls = [
            "https://www.paris.cl/mi-cuenta/compras",
            "https://www.paris.cl/iniciar-sesion",
            "https://www.paris.cl/centro-de-ayuda/",
            "https://www.paris.cl/seguimiento-compras",
            "https://www.paris.cl/legales/terminos-y-condiciones",
        ]
        for url in bad_urls:
            cls = classify_surface(url, {"brand": "Nicopoly"})
            assert cls["surface_type"] in ("GENERAL_NAVIGATION", "CORPORATE_NAVIGATION"), (
                f"URL {url} wrongly classified as {cls['surface_type']}"
            )

    @pytest.mark.asyncio
    async def test_paris_02_extract_commercial_facets_from_rsc_fixture(self):
        """PARIS-02: Must extract at least one valid commercial facet category from Next.js App Router RSC stream."""
        mock_page = AsyncMock()
        mock_page.content.return_value = PARIS_RSC_FIXTURE_HTML
        mock_page.evaluate = AsyncMock()

        # Simulate evaluate for document.querySelectorAll('a[href]') and scripts
        async def mock_eval(script_str):
            if "__NEXT_DATA__" in script_str:
                return None  # Next.js App router has no __NEXT_DATA__
            if "querySelectorAll" in script_str:
                return [
                    {"href": "/search?q=nicopoly&page=2", "text": "Mostrar más", "cls": ""},
                    {"href": "https://www.paris.cl/mi-cuenta/compras", "text": "Mis Compras", "cls": ""},
                    {"href": "https://www.paris.cl/iniciar-sesion", "text": "Iniciar Sesión", "cls": ""},
                ]
            return []

        mock_page.evaluate.side_effect = mock_eval

        discovered = await discover_categories_from_page(
            mock_page, "Paris", "https://www.paris.cl/search?q=nicopoly", brand="Nicopoly"
        )
        assert len(discovered) > 0, "No commercial categories extracted from Paris RSC fixture"
        # Must include at least one tipoProductoAll facet route
        assert any("tipoProductoAll=" in u for u in discovered), (
            f"Expected tipoProductoAll in discovered categories: {discovered}"
        )

    def test_paris_03_preserve_provenance_and_category_name(self):
        """PARIS-03: Route must derive proper category name from tipoProductoAll and retain source URL."""
        url = "https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Blusas"
        name = category_name_from_url(url, brand="Nicopoly")
        assert name == "Blusas", f"Expected 'Blusas', got '{name}'"

        url2 = "https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Vestidos"
        name2 = category_name_from_url(url2, brand="Nicopoly")
        assert name2 == "Vestidos", f"Expected 'Vestidos', got '{name2}'"

    def test_paris_04_dynamic_brand_runtime_generalization(self):
        """PARIS-04: Must use dynamic brand argument, not hardcoded 'Nicopoly'."""
        brand = "Opposite"
        url = f"https://www.paris.cl/search?q={brand.lower()}&tipoProductoAll=Chaquetas"
        name = category_name_from_url(url, brand=brand)
        assert name == "Chaquetas", f"Expected 'Chaquetas', got '{name}'"

        cls = classify_surface(url, {"brand": brand})
        assert cls["surface_type"] == "COMMERCIAL_CATEGORY", (
            f"Expected COMMERCIAL_CATEGORY for dynamic brand facet, got {cls['surface_type']}"
        )

    def test_paris_05_brand_status_semantics_not_present_first_page(self):
        """PARIS-05: An unvisited or first-empty category must not declare permanent global NOT_FOUND."""
        from app.mri_autonomous.surface_classifier import certify_node
        # Candidate with 0 products on initial page
        res = certify_node({"surface_type": "COMMERCIAL_CATEGORY", "evidence": []}, 0, 0)
        assert not res["certified"], "Category with 0 products should not be certified"
        assert res.get("status") in ("UNVERIFIED", "UNRESOLVED", "PARTIAL", "EMPTY_PAGE", None), (
            f"Invalid status {res.get('status')}"
        )
