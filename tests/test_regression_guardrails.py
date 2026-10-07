import unittest
import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.scrapers.base_scraper import BaseScraper
from app.auditor.nicopoly_matcher import is_nicopoly
from app.loaders.multivende_loader import get_multivende_loader
import re
import json
import io


class DummyScraper(BaseScraper):
    def __init__(self):
        super().__init__(headless=True, marketplace="Test")

    async def navigate(self, url: str) -> bool:
        return True

    async def get_total_count(self, url: str) -> int:
        return 0

    async def scrape_category(self, url: str, target_count: int = 30) -> list[dict]:
        return []


class TestRegressionGuardrails(unittest.TestCase):
    def setUp(self):
        self.scraper = DummyScraper()

    # ── 1. GUARDRAIL PRECIOS (parse_price_text) ──────────────────────────────
    def test_parse_price_standard_clp(self):
        """Verifica parseo estándar de precios chilenos con punto."""
        self.assertEqual(self.scraper.parse_price_text("$19.990"), 19990.0)
        self.assertEqual(self.scraper.parse_price_text("$79.990"), 79990.0)
        self.assertEqual(self.scraper.parse_price_text("$1.399.912"), 1399912.0)

    def test_parse_price_five_digit_concatenation(self):
        """Verifica que números de 5 dígitos con cuotas ('99906') se recorten a $9.990 y NO a $99.906."""
        self.assertEqual(self.scraper.parse_price_text("99906"), 9990.0)
        self.assertEqual(self.scraper.parse_price_text("699906"), 69990.0)

    # ── 2. GUARDRAIL MATCHER NICOPOLY (is_nicopoly) ─────────────────────────
    def test_nicopoly_matcher_title_fallback(self):
        """Verifica que is_nicopoly funcione tanto con 'title' como con 'product_title'."""
        prod1 = {"title": "Abrigo Cuello Camisero Negro Nicopoly"}
        prod2 = {"product_title": "Abrigo Cuello Camisero Negro Nicopoly"}
        self.assertTrue(is_nicopoly(prod1))
        self.assertTrue(is_nicopoly(prod2))

    def test_nicopoly_matcher_word_boundary_blacklist(self):
        """Verifica que 'ad' como substring no bloquee palabras como 'bufanda' o 'rosada'."""
        prod = {"title": "Bufanda Rosada Abrigada Nicopoly"}
        self.assertTrue(is_nicopoly(prod))

    def test_nicopoly_matcher_competitor_blocking(self):
        """Verifica que marcas competidoras sin mención de Nicopoly se descarten."""
        prod_competitor = {"title": "Vestido Pliegues ZARA", "vendor": "ZARA"}
        self.assertFalse(is_nicopoly(prod_competitor))

    # ── 3. GUARDRAIL MULTIVENDE LOADER ──────────────────────────────────────
    def test_multivende_generic_word_isolation(self):
        """Verifica que palabras genéricas cortas como 'Tapado' no hagan match ambiguo con SKUs."""
        loader = get_multivende_loader()
        match_generic = loader.lookup_sku("Mercado Libre", "Tapado")
        self.assertIsNone(match_generic, "La palabra genérica 'Tapado' sin marca no debe retornar ningún SKU de Multivende.")

    # ── 4. GUARDRAIL DEDUPLICACIÓN LECTURA / ESCRITURA ──────────────────────
    def test_deduplication_read_write_alignment(self):
        """Verifica que títulos con y sin la palabra 'Nicopoly' colapsen exactamente a la misma clave única."""
        def _make_key(s_item):
            mkt_sku = str(s_item.get("marketplace_sku", "")).strip()
            if mkt_sku:
                return mkt_sku
            raw_title = str(s_item.get("product_title", s_item.get("title", ""))).strip().lower()
            clean = re.sub(r"\b(nicopoly|nicopolo|nico poly)\b", "", raw_title, flags=re.IGNORECASE).strip()
            clean = re.sub(r"\s+", " ", clean)
            return clean

        item1 = {"product_title": "Trench Ecocuero Café Nicopoly", "marketplace_sku": ""}
        item2 = {"product_title": "Trench Ecocuero Café", "marketplace_sku": ""}
        
        key1 = _make_key(item1)
        key2 = _make_key(item2)
        
        self.assertEqual(key1, key2, "Títulos con y sin 'Nicopoly' deben generar exactamente la misma clave deduplicada.")



    # 5. GUARDRAIL ANTI-REGRESION ML (14-Ago): evita que un tercero revierta los fixes
    def test_ml_fix_guardrails_source(self):
        """Verifica en el codigo fuente que los fixes ML-1/ML-2/ML-3 siguen presentes."""
        base = os.path.join(os.path.dirname(__file__), '..', 'app', 'scrapers', 'base_scraper.py')
        ml = os.path.join(os.path.dirname(__file__), '..', 'app', 'scrapers', 'mercadolibre_scraper.py')
        cb = os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'circuit_breaker.py')
        with io.open(base, encoding='utf-8', errors='replace') as f:
            base_src = f.read()
        with io.open(ml, encoding='utf-8', errors='replace') as f:
            ml_src = f.read()
        with io.open(cb, encoding='utf-8', errors='replace') as f:
            cb_src = f.read()

        # Fix ML-1: _sanitize_cookies NO debe tener filtro ACTIVO de cookies de autenticacion.
        # Se detecta el patron de bloqueo (lista de keys + continue), no la mencion en comentarios.
        idx = base_src.find('def _sanitize_cookies')
        if idx >= 0:
            tail = base_src[idx:idx + 4000]
            has_seller_keys_set = 'seller_keys' in tail or "'orguserid'" in tail or '"orguserid"' in tail
            has_continue_filter = 'continue' in tail
            if has_seller_keys_set and has_continue_filter:
                self.fail('_sanitize_cookies tiene filtro activo de cookies de autenticacion (Fix ML-1 revertido)')
        # Fix ML-2: headless=False forzado para ML debe existir
        self.assertIn('Forcing headless=False', base_src,
                      'Bloque Forcing headless=False eliminado (Fix ML-2 revertido)')
        # Fix ML-2: no debe existir guest mode que salte la carga de cookies
        self.assertNotIn('guest mode', ml_src.lower(),
                         'Guest mode reintroducido (Fix ML-2 revertido)')
        # Fix ML-3: recovery largo para ML en el breaker
        self.assertIn('CIRCUIT_BREAKER_RECOVERY_ML_S', cb_src,
                      'Recovery ML largo eliminado (Fix ML-3 revertido)')

    def test_ml_cookies_include_auth_keys(self):
        """Verifica que el session.json de ML conserve orguserid/orgnickp/ftid."""
        session = os.path.join(os.path.dirname(__file__), '..', 'data', 'mercadolibre_session.json')
        if not os.path.exists(session):
            self.skipTest('session.json no presente')
        with io.open(session, encoding='utf-8', errors='replace') as f:
            data = json.load(f)
        if isinstance(data, dict):
            cookies = data.get('cookies', [])
        elif isinstance(data, list):
            cookies = data
        else:
            self.skipTest('session.json con formato inesperado')
        names = [c.get('name') for c in cookies]
        for key in ('orguserid', 'orgnickp', 'ftid'):
            self.assertIn(key, names, 'Falta cookie de autenticacion %s en session.json' % key)

    def test_is_nicopoly_respects_brand(self):
        """Fix RIP-1: is_nicopoly debe rechazar productos con marca extrana
        (ej. Ripley 'RAINDOOR', 'GENÉRICO') aunque su titulo embeba un SKU Nicopoly."""
        matcher = os.path.join(os.path.dirname(__file__), '..', 'app', 'auditor', 'nicopoly_matcher.py')
        with io.open(matcher, encoding='utf-8', errors='replace') as f:
            src = f.read()
        idx = src.find('def is_nicopoly')
        self.assertGreaterEqual(idx, 0, 'is_nicopoly no encontrado')
        tail = src[idx:idx + 2000]
        # Debe existir el bloque que respeta el vendor/brand no-Nicopoly
        self.assertIn('if vendor and not any(re.search(p, vendor) for p in NICOPOLY_PATTERNS):',
                      tail, 'Falta bloque de respeto de marca (Fix RIP-1 revertido)')

        # Verificacion funcional directa
        self.assertFalse(is_nicopoly(
            {"vendor": "RAINDOOR", "title": "PANTALÓN MUJER RAINDOOR REGULAR FIT N07097EXL", "marketplace_sku": ""},
            marketplace="Ripley"), 'Producto RAINDOOR con SKU Nicopoly embebido debe ser rechazado')
        self.assertFalse(is_nicopoly(
            {"vendor": "GENÉRICO", "title": "CONJUNTO 2 PIEZAS MUJER N07007AS", "marketplace_sku": ""},
            marketplace="Ripley"), 'Producto GENÉRICO con SKU Nicopoly embebido debe ser rechazado')
        self.assertTrue(is_nicopoly(
            {"vendor": "NICOPOLY", "title": "JEANS RECTO NICOPOLY", "marketplace_sku": ""},
            marketplace="Ripley"), 'Producto NICOPOLY debe ser aceptado')

    def test_ripley_empty_state_not_substring(self):
        """Fix RIP-2: '0 resultados' NO debe matchear como substring dentro de
        '10/20/100 resultados'. Usar lookbehind negativo (?<!\\d)."""
        ripley = os.path.join(os.path.dirname(__file__), '..', 'app', 'scrapers', 'ripley_scraper.py')
        with io.open(ripley, encoding='utf-8', errors='replace') as f:
            src = f.read()
        self.assertIn(r'(?<!\d)0\s+resultados', src,
                      'Falta regex lookbehind para 0 resultados (Fix RIP-2 revertido)')
        # El substring crudo ya no debe estar en la lista de indicadores
        lines = src.splitlines()
        self.assertFalse(any(l.strip() == '"0 resultados"' for l in lines),
                         'Item "0 resultados" reintroducido en lista (Fix RIP-2 revertido)')

        # Verificacion funcional
        import re
        def is_empty(body):
            bl = body.lower()
            inds = [
                "no existen productos que cumplan con tus criterios de filtrado",
                "intenta ajustar los filtros aplicados",
                "no encontramos resultados",
            ]
            return any(i in bl for i in inds) or bool(re.search(r'(?<!\d)0\s+resultados', bl))
        self.assertFalse(is_empty('10 Resultados en Jeans mujer NICOPOLY'))
        self.assertFalse(is_empty('20 Resultados en Jeans'))
        self.assertFalse(is_empty('100 Resultados en Jeans'))
        self.assertTrue(is_empty('0 Resultados en Enteritos Mujer NICOPOLY'))

    def test_ml_pagination_path_based(self):
        """Fix ML-12: la paginacion ML debe usar _Desde_N como SEGMENTO DE PATH,
        no como query param (?_Desde_N). El query param es ignorado por ML y
        reciclaba la pagina 1, limitando la captura a 48 SKUs unicos."""
        ml = os.path.join(os.path.dirname(__file__), '..', 'app', 'scrapers', 'mercadolibre_scraper.py')
        with io.open(ml, encoding='utf-8', errors='replace') as f:
            ml_src = f.read()
        idx = ml_src.find('async def _go_to_next_page')
        self.assertGreaterEqual(idx, 0, '_go_to_next_page no encontrado')
        tail = ml_src[idx:idx + 2500]
        self.assertIn('path_part', tail, 'Paginacion no separa path/query (Fix ML-12 revertido)')
        self.assertIn('_Desde_{new_offset}', tail, 'Falta append path-based _Desde_N (Fix ML-12 revertido)')
        self.assertNotIn('sep = "&" if "?" in clean_url else "?"', tail,
                         'Paginacion por query param reintroducida (Fix ML-12 revertido)')

    def test_ml_selector_no_duplication(self):
        """Fix ML-13: el selector de items NO debe matchear .poly-card y
        .ui-search-layout__item en paralelo (duplicaba cada producto 2x)."""
        ml = os.path.join(os.path.dirname(__file__), '..', 'app', 'scrapers', 'mercadolibre_scraper.py')
        with io.open(ml, encoding='utf-8', errors='replace') as f:
            ml_src = f.read()
        idx = ml_src.find('async def _extract_products_from_html')
        self.assertGreaterEqual(idx, 0, '_extract_products_from_html no encontrado')
        tail = ml_src[idx:idx + 1500]
        self.assertIn('.ui-search-layout__item', tail, 'Selector li.ui-search-layout__item ausente')
        self.assertNotIn('.poly-card, .ui-search-layout__item', tail,
                         'Selector duplicado (.poly-card, .ui-search-layout__item) reintroducido (Fix ML-13 revertido)')


if __name__ == "__main__":
    unittest.main()
