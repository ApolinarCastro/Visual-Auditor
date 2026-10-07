# -*- coding: utf-8 -*-
"""Tests de transferencia MRI-AUTONOMY-001 (capacidades, no respuestas).
Capa 1: pagination helpers. Capa 2: brand normalization. Capa 3: experience brand param.
Ejecutar: venv python -m pytest tests/test_mri_autonomy_transfer.py -q
"""
import importlib
import sys
import tempfile
from pathlib import Path

import pytest

VA = Path(__file__).resolve().parents[1]
if str(VA) not in sys.path:
    sys.path.insert(0, str(VA))


# ---------------- Capa 1: pagination ----------------

class TestPagination:
    def test_parse_pager_text_basic(self):
        from app.mri_autonomous.pagination import parse_pager_text
        r = parse_pager_text("... Página 3 de 14 ...")
        assert r == {"current": 3, "total": 14}

    def test_parse_pager_text_accentless_and_single(self):
        from app.mri_autonomous.pagination import parse_pager_text
        assert parse_pager_text("Pagina 1 de 486") == {"current": 1, "total": 486}
        assert parse_pager_text("pagina 1 de 1") == {"current": 1, "total": 1}

    def test_parse_pager_text_absent(self):
        from app.mri_autonomous.pagination import parse_pager_text
        assert parse_pager_text("no pager here") is None

    def test_detect_sort_mode(self):
        from app.mri_autonomous.pagination import detect_sort_mode
        assert detect_sort_mode("Ordenar por\nRelevancia") == "Relevancia"
        assert detect_sort_mode("Ordenar por Recomendados") == "Recomendados"
        assert detect_sort_mode("sin control") is None

    def test_pagination_url_sets_param(self):
        from app.mri_autonomous.pagination import pagination_url
        u = pagination_url("https://simple.ripley.cl/search/nicopoly?sort=relevance_desc&page=1", "page", 5)
        assert "page=5" in u and "sort=relevance_desc" in u and "page=1" not in u

    def test_pagination_url_adds_param(self):
        from app.mri_autonomous.pagination import pagination_url
        u = pagination_url("https://simple.ripley.cl/search/nicopoly", "page", 2)
        assert u.endswith("?page=2") or u.endswith("&page=2")

    def test_build_plan_from_candidates(self):
        from app.mri_autonomous.pagination import build_pagination_plan
        plan = build_pagination_plan(
            "https://simple.ripley.cl/search/nicopoly",
            [f"https://simple.ripley.cl/search/nicopoly?page={n}" for n in range(2, 12)],
        )
        assert plan is not None
        assert plan["param"] == "page"
        assert plan["observed_pages"] == list(range(2, 12))
        assert plan["max_observed"] == 11

    def test_build_plan_rejects_foreign_paths(self):
        from app.mri_autonomous.pagination import build_pagination_plan
        plan = build_pagination_plan(
            "https://simple.ripley.cl/search/nicopoly",
            ["https://simple.ripley.cl/moda-mujer?page=2"],
        )
        assert plan is None

    def test_build_plan_none_when_no_candidates(self):
        from app.mri_autonomous.pagination import build_pagination_plan
        assert build_pagination_plan("https://simple.ripley.cl/search/nicopoly", []) is None


# ---------------- Capa 2: brand normalización ----------------

class TestBrandNorm:
    def test_slug_from_hub_url_ripley(self):
        from app.mri_autonomous.brand_norm import brand_slug_from_hub_url
        assert brand_slug_from_hub_url("https://simple.ripley.cl/search/nicopoly") == "nicopoly"

    def test_slug_from_hub_url_query(self):
        from app.mri_autonomous.brand_norm import brand_slug_from_hub_url
        assert brand_slug_from_hub_url("https://www.paris.cl/search?q=nicopoly") == "nicopoly"
        assert brand_slug_from_hub_url("https://www.falabella.com/falabella-cl/search?Ntt=Nicopoly") == "nicopoly"

    def test_normalize_brand(self):
        from app.mri_autonomous.brand_norm import normalize_brand
        assert normalize_brand("Nicopoly") == "nicopoly"
        assert normalize_brand(" NICOPOLY ") == "nicopoly"

    def test_brand_match_positive_vendor(self):
        from app.mri_autonomous.brand_norm import brand_match
        assert brand_match({"vendor": "NICOPOLY", "title": "CHAQUETA X"}, "Nicopoly")
        assert brand_match({"vendor": "", "title": "VESTIDO NICOPOLY ROJO"}, "Nicopoly")

    def test_brand_match_negative(self):
        from app.mri_autonomous.brand_norm import brand_match
        assert not brand_match({"vendor": "ZARA", "title": "BUFANDA"}, "Nicopoly")

    def test_brand_match_variable_brand(self):
        from app.mri_autonomous.brand_norm import brand_match
        # La capacidad debe funcionar para CUALQUIER marca, no solo Nicopoly
        assert brand_match({"vendor": "ACME", "title": "Producto ACME 1"}, "ACME")
        assert not brand_match({"vendor": "OTRA", "title": "Producto"}, "ACME")


# ---------------- Capa 3: experience brand param (sin hardcode) ----------------

class TestExperienceBrandParam:
    def _store(self, tmp: Path):
        from app.mri_autonomous.experience_store import ExperienceStore
        return ExperienceStore(db_path=str(tmp / "mri_experience_test.db"))

    def test_get_strategies_respects_brand(self, tmp_path):
        s = self._store(tmp_path)
        s.record_strategy(marketplace="Ripley", brand="MarcaX", strategy_id="s1",
                          strategy_type="paginate", surface="u", hypothesis="h",
                          attempt=1, result="SUCCESS", evidence="e")
        got_x = s.get_strategies("Ripley", brand="MarcaX")
        got_nico = s.get_strategies("Ripley", brand="Nicopoly")
        assert len(got_x) == 1
        assert len(got_nico) == 0, "get_strategies no debe devolver estrategias de otra marca (hardcode Nicopoly)"

    def test_select_strategy_respects_brand(self, tmp_path):
        s = self._store(tmp_path)
        s.record_strategy(marketplace="Ripley", brand="MarcaX", strategy_id="p1",
                          strategy_type="paginate", surface="https://x", hypothesis="h",
                          attempt=1, result="SUCCESS", evidence="e", confidence=0.9)
        assert s.select_strategy("Ripley", "MarcaX", "paginate", "https://x") is not None
        assert s.select_strategy("Ripley", "Nicopoly", "paginate", "https://x") is None

    def test_record_strategy_outcome_uses_marketplace(self, tmp_path):
        s = self._store(tmp_path)
        s.record_strategy(marketplace="Ripley", brand="MarcaX", strategy_id="o1",
                          strategy_type="paginate", surface="u", hypothesis="h",
                          attempt=1, result="PENDING", evidence="e")
        s.record_strategy_outcome("Ripley", "MarcaX", "o1", "SUCCESS", 0.8, "ok")
        row = s.get_strategy("Ripley", "MarcaX", "o1")
        assert row is not None and row["result"] == "SUCCESS"
        # el registro de experiencia asociado debe quedar bajo marketplace real Ripley/MarcaX
        exp = s.get_experience_item("Ripley", "MarcaX", "STRATEGY", "o1")
        assert exp is not None, "outcome debe registrar experiencia con marketplace/brand reales (no 'Nicopoly')"


# ---------------- Capa 4: cobertura en resume (regla pura) ----------------

class TestResumeCoverage:
    def test_resume_full_frontier_not_not_discovered(self):
        from app.mri_autonomous.autonomous_pipeline import resume_coverage_status
        assert resume_coverage_status(hub_skipped=True, has_other_categories=False, controlled_stop=False) == "PARTIAL"

    def test_resume_with_pending_categories_defers(self):
        from app.mri_autonomous.autonomous_pipeline import resume_coverage_status
        assert resume_coverage_status(hub_skipped=True, has_other_categories=True, controlled_stop=False) is None

    def test_non_resumed_run_defers(self):
        from app.mri_autonomous.autonomous_pipeline import resume_coverage_status
        assert resume_coverage_status(hub_skipped=False, has_other_categories=False, controlled_stop=False) is None


# ---------------- Capa 5 (MRI-AUTONOMY-002): navegacion, facets, experiencia ----------------

class TestNavigationCandidates:
    def _nodes(self):
        return [
            {"label": "Moda Mujer", "href": "/moda-mujer", "container": "menu_dialog"},
            {"label": "Moda Hombre", "href": "/moda-hombre", "container": "menu_dialog"},
            {"label": "Ayuda", "href": "/ayuda", "container": "menu_dialog"},
            {"label": "Cuenta", "href": "https://www.bancoripley.cl/", "container": "footer"},
            {"label": "Black Friday", "href": "/minisitios/black-friday", "container": "footer"},
            {"label": "Producto X", "href": "/casaca-mujer-io-2000411528740", "container": "grid"},
            {"label": "Pagina 2", "href": "/search/nicopoly?page=2", "container": "pager"},
            {"label": "Moda Mujer dup", "href": "/moda-mujer?track=1", "container": "menu_dialog"},
        ]

    def test_extracts_only_commercial_hypotheses(self):
        from app.mri_autonomous.category_discoverer import build_navigation_candidates
        cands = build_navigation_candidates(self._nodes(), "https://simple.ripley.cl/search/nicopoly", "Nicopoly")
        urls = sorted(c["url"] for c in cands)
        assert urls == ["https://simple.ripley.cl/moda-hombre", "https://simple.ripley.cl/moda-mujer"]

    def test_candidate_shape(self):
        from app.mri_autonomous.category_discoverer import build_navigation_candidates
        cands = build_navigation_candidates(self._nodes(), "https://simple.ripley.cl/search/nicopoly", "Nicopoly")
        c = cands[0]
        for k in ("candidate_id", "url", "label", "parent", "depth", "discovery_method", "evidence_locator", "classification"):
            assert k in c
        assert c["depth"] == 1 and c["parent"] is None

    def test_no_known_category_lists(self):
        import inspect
        from app.mri_autonomous import category_discoverer as cd
        src = inspect.getsource(cd)
        assert "known_ripley_categories" not in src
        assert "moda-mujer" not in src.split("def build_navigation_candidates")[1][:2000]


class TestStrategyChoice:
    def test_choose_menu_after_raw_dom_failure(self):
        from app.mri_autonomous.category_discoverer import choose_navigation_strategy
        failed = [{"strategy_id": "nav::raw_dom_only", "result": "FAILED", "failure_signature": "no_navigation_candidates_from_raw_dom"}]
        strategy, decision = choose_navigation_strategy(failed, [])
        assert strategy == "menu_open_anchors"
        assert decision and decision["decision"] == "SELECTED_ALTERNATIVE"
        assert "raw_dom_only" in decision["because"]

    def test_default_raw_dom_without_evidence(self):
        from app.mri_autonomous.category_discoverer import choose_navigation_strategy
        strategy, decision = choose_navigation_strategy([], [])
        assert strategy == "raw_dom_anchors"
        assert decision is None


class TestFacetSignals:
    def test_two_signals_required(self):
        from app.mri_autonomous.category_discoverer import facet_signals_verified
        before = {"url": "u1", "count": 100, "titles": ["a", "b", "c"]}
        after_url = {"url": "u2", "count": 100, "titles": ["a", "b", "c"]}
        after_count = {"url": "u1", "count": 55, "titles": ["a", "b", "c"]}
        after_two = {"url": "u2", "count": 55, "titles": ["a", "b", "c"]}
        assert facet_signals_verified(before, after_url) is False
        assert facet_signals_verified(before, after_count) is False
        assert facet_signals_verified(before, after_two) is True

    def test_product_set_change_counts_as_signal(self):
        from app.mri_autonomous.category_discoverer import facet_signals_verified
        before = {"url": "u1", "count": None, "titles": ["a", "b", "c"]}
        after = {"url": "u2", "count": None, "titles": ["z", "b", "c"]}
        assert facet_signals_verified(before, after) is True


class TestG16Grader:
    def _call(self, membership):
        import sys as _sys
        from pathlib import Path as _P
        VA = _P(__file__).resolve().parents[1]
        gs = VA / "mri_commercial_materialization_golden_slice" / "v001"
        if str(gs) not in _sys.path:
            _sys.path.insert(0, str(gs))
        import materializer_engine as me
        m = me.GenericCommercialMaterializer(run_id="run_mri_autonomy_002_20260928_170000")
        norm = {"captured_at": "2026-09-28T10:00:00", "raw_sku": "1001", "raw_title": "CHAQUETA X",
                "marketplace": "Ripley", "source_record_id": "s1"}
        identity = {"status": "RESOLVED", "marketplace_product_id": "1001"}
        ev_info = {"evidence_id": "e1", "source_record_id": "s1"}
        return m.evaluate_grader(norm, identity, {"effective_price": 1000, "regular_price": None, "sale_price": None},
                                 {"relationship": "LEGACY_CONFIGURED_CATEGORY"},
                                 {"position_state": "OBSERVED_POSITION"}, ev_info, membership=membership)

    def test_g16_true_for_confirmed_membership(self):
        g = self._call({"classification": "NICOPOLY_CONFIRMED"})
        assert g["rules"]["G16"] is True

    def test_g16_false_without_membership(self):
        g = self._call(None)
        assert g["rules"]["G16"] is False

    def test_g16_false_for_other_classification(self):
        g = self._call({"classification": "NON_NICOPOLY_CONFIRMED"})
        assert g["rules"]["G16"] is False


class TestNoHardcodedCategoryNames:
    def test_surface_classifier_has_no_category_name_literal(self):
        from pathlib import Path as _P
        VA = _P(__file__).resolve().parents[1]
        src = (VA / "app" / "mri_autonomous" / "surface_classifier.py").read_text(encoding="utf-8")
        assert "moda-mujer" not in src.lower()


# ---------------- Capa 6 (cert2d fix): predicado de menu + namespaces ----------------

class TestNavigationPredicateV2:
    def test_priority_click_targets_categories(self):
        from app.scrapers.ripley_scraper import RipleyScraper
        assert "categor" in RipleyScraper.NAV_BUTTON_JS_PRIORITY
        assert "men" in RipleyScraper.NAV_BUTTON_JS_FALLBACK

    def test_utility_namespaces_excluded(self):
        from app.mri_autonomous import category_discoverer as cd
        for ns in ("seguimiento", "landings"):
            assert ns in cd._MARKETING_NAMESPACES


class TestFacetProbeScoping:
    def test_probe_scopes_and_guards(self):
        from pathlib import Path as _P
        VA = _P(__file__).resolve().parents[1]
        scraper_src = (VA / 'app' / 'scrapers' / 'ripley_scraper.py').read_text(encoding='utf-8')
        pipe_src = (VA / 'app' / 'mri_autonomous' / 'autonomous_pipeline.py').read_text(encoding='utf-8')
        assert 'unscoped' in scraper_src
        assert 'not _fprobe.get("unscoped")' in pipe_src


class TestNavDiscoveryEnsuresHubSurface:
    def test_pipeline_navigates_hub_before_discovery(self):
        from pathlib import Path as _P
        VA = _P(__file__).resolve().parents[1]
        src = (VA / 'app' / 'mri_autonomous' / 'autonomous_pipeline.py').read_text(encoding='utf-8')
        i_nav = src.index('await scraper._navigate_ripley(hub_url)')
        i_disc = src.index('discover_navigation(raw_only')
        assert i_nav < i_disc, 'la superficie del hub debe asegurarse ANTES de discover_navigation'


class TestRobustFailureFilter:
    def test_pipeline_filters_failed_in_code(self):
        from pathlib import Path as _P
        VA = _P(__file__).resolve().parents[1]
        src = (VA / 'app' / 'mri_autonomous' / 'autonomous_pipeline.py').read_text(encoding='utf-8')
        assert "get('result') == 'FAILED'" in src or '"result") == \'FAILED\'' in src


class TestNavHarvestV4:
    def test_scraper_uses_best_container(self):
        from pathlib import Path as _P
        VA = _P(__file__).resolve().parents[1]
        src = (VA / 'app' / 'scrapers' / 'ripley_scraper.py').read_text(encoding='utf-8')
        assert "bestCount" in src
        assert "fallback_second_click" in src or "second_click" in src


class TestNavJsonPairs:
    def test_extracts_name_url_pairs(self):
        from app.mri_autonomous.category_discoverer import extract_nav_pairs_from_json
        payload = {"menu": [{"name": "Moda Mujer", "url": "/moda-mujer", "children": [
            {"name": "Vestidos", "url": "/moda-mujer/vestidos"}]},
            {"label": "Tecno", "link": "/tecno"}]}
        pairs = extract_nav_pairs_from_json(payload)
        assert ("Moda Mujer", "/moda-mujer") in pairs
        assert ("Vestidos", "/moda-mujer/vestidos") in pairs
        assert ("Tecno", "/tecno") in pairs

    def test_ignores_non_path_urls(self):
        from app.mri_autonomous.category_discoverer import extract_nav_pairs_from_json
        payload = {"items": [{"name": "X", "url": "https://otro.cl/x"},
                               {"name": "Y", "url": "#"}, {"name": "Z", "url": "/ok"}]}
        pairs = extract_nav_pairs_from_json(payload)
        assert ("Z", "/ok") in pairs
        assert all(p[1].startswith("/") for p in pairs)

    def test_scraper_collects_menu_responses(self):
        from pathlib import Path as _P
        VA = _P(__file__).resolve().parents[1]
        src = (VA / "app" / "scrapers" / "ripley_scraper.py").read_text(encoding="utf-8")
        assert "response" in src and "extract_nav_pairs_from_json" in src


# ---------------- Capa 8 (MRI-AUTONOMY-003): cobertura global vs nav discovery ----------------

class TestGlobalCoverageCap:
    def test_blocked_navigation_caps_confirmed(self):
        from app.mri_autonomous.category_discoverer import global_coverage_cap
        assert global_coverage_cap("BLOCKED", "CONFIRMED") == "PARTIAL"
        assert global_coverage_cap("PARTIAL", "CONFIRMED") == "PARTIAL"

    def test_pass_navigation_keeps_status(self):
        from app.mri_autonomous.category_discoverer import global_coverage_cap
        assert global_coverage_cap("PASS", "CONFIRMED") == "CONFIRMED"
        assert global_coverage_cap("BLOCKED", "PARTIAL") == "PARTIAL"


# ---------------- Capa 9 (MRI-AUTONOMY-003): fuente de navegacion (menu API) ----------------

class TestNavigationSourceParse:
    def _raw(self):
        from pathlib import Path as _P
        VA = _P(__file__).resolve().parents[1]
        import json as _json
        return _json.loads((VA / 'tests' / 'fixtures' / 'nav_menu_source_sample.json').read_text(encoding='utf-8'))

    def test_parses_all_nodes_with_chain_urls(self):
        from app.mri_autonomous.category_discoverer import parse_navigation_source
        cands = parse_navigation_source(self._raw(), 'https://simple.ripley.cl/search/nicopoly', 'Nicopoly', 'shaTEST')
        assert len(cands) == 1437
        urls = {c['url'] for c in cands}
        assert 'https://simple.ripley.cl/belleza' in urls
        assert 'https://simple.ripley.cl/belleza/cuidado-de-la-piel/contorno-de-ojos' in urls
        assert all(u.startswith('https://simple.ripley.cl/') for u in urls)
        assert all('-mpm' not in u for u in urls)

    def test_shape_parent_depth_provenance(self):
        from app.mri_autonomous.category_discoverer import parse_navigation_source
        cands = parse_navigation_source(self._raw(), 'https://simple.ripley.cl/search/nicopoly', 'Nicopoly', 'shaTEST')
        by_url = {c['url']: c for c in cands}
        deep = by_url['https://simple.ripley.cl/belleza/cuidado-de-la-piel/contorno-de-ojos']
        assert deep['parent'] == 'cuidado-de-la-piel'
        assert deep['depth'] >= 3
        assert deep['discovery_method'] == 'menu_api_source'
        assert 'shaTEST' in deep['evidence_locator']
        top = by_url['https://simple.ripley.cl/belleza']
        assert top['parent'] is None and top['depth'] == 1

    def test_bfs_order_top_levels_first(self):
        from app.mri_autonomous.category_discoverer import parse_navigation_source
        cands = parse_navigation_source(self._raw(), 'https://simple.ripley.cl/search/nicopoly', 'Nicopoly', 'shaTEST')
        depths = [c['depth'] for c in cands]
        assert depths == sorted(depths), 'orden BFS: niveles ascendentes'


# ---------------- Capa 10 (MRI-AUTONOMY-004): semantica de estado de nodo ----------------

class TestNodeStatusSemantics:
    def test_no_brand_first_page_is_unresolved_not_rejected(self):
        from app.mri_autonomous.category_discoverer import classify_node_status
        # marca no visible en primera pagina != marca ausente en la categoria
        assert classify_node_status(False, "PAGINATION_PARAM_NOT_FOUND", 58, 0) == "UNRESOLVED"
        assert classify_node_status(False, "EXHAUSTION", 58, 0) == "UNRESOLVED"

    def test_terminal_and_certified_states(self):
        from app.mri_autonomous.category_discoverer import classify_node_status
        assert classify_node_status(True, "EXHAUSTION", 58, 3) == "CERTIFIED"
        assert classify_node_status(False, "BLOCKED", 0, 0) == "BLOCKED"
        assert classify_node_status(False, "EXTRACTOR_FAILURE", 0, 0) == "FAILED"


# ---------------- Capa 11 (MRI-AUTONOMY-005): mecanismo URL_QUERY ----------------

class TestFacetUrlMechanism:
    def test_build_transition_from_mechanism(self):
        from app.mri_autonomous.category_discoverer import build_facet_url
        mech = {"type": "URL_QUERY", "param": "brand", "value_case": "upper"}
        url = build_facet_url("https://simple.ripley.cl/moda-mujer", "Nicopoly", mech)
        assert url == "https://simple.ripley.cl/moda-mujer?brand=NICOPOLY&page=1"

    def test_param_comes_from_mechanism_not_hardcode(self):
        from app.mri_autonomous.category_discoverer import build_facet_url
        mech = {"type": "URL_QUERY", "param": "marca", "value_case": "upper"}
        url = build_facet_url("https://simple.ripley.cl/x", "Nicopoly", mech)
        assert "marca=NICOPOLY" in url and "brand=" not in url

    def test_no_mechanism_no_fabrication(self):
        from app.mri_autonomous.category_discoverer import build_facet_url
        assert build_facet_url("https://simple.ripley.cl/moda-mujer", "Nicopoly", None) is None
        assert build_facet_url("https://simple.ripley.cl/moda-mujer", "Nicopoly", {"type": "XHR"}) is None


class TestBrandEffectSignals:
    def test_effect_requires_multiple_signals(self):
        from app.mri_autonomous.category_discoverer import brand_effect_verified
        before = {"url": "https://simple.ripley.cl/moda-mujer", "total": 23829, "title": "Ropa Mujer | Ripley.com"}
        ok_all = {"url": "https://simple.ripley.cl/moda-mujer?brand=NICOPOLY&page=1", "total": 630,
                  "title": "Ropa Mujer NICOPOLY | Ripley.com"}
        only_url = {"url": ok_all["url"], "total": 23829, "title": before["title"]}
        only_count = {"url": before["url"], "total": 630, "title": before["title"]}
        assert brand_effect_verified(before, ok_all, "Nicopoly") is True
        assert brand_effect_verified(before, only_url, "Nicopoly") is False
        assert brand_effect_verified(before, only_count, "Nicopoly") is False


class TestChildrenPrioritization:
    def test_children_of_certified_first(self):
        from app.mri_autonomous.category_discoverer import prioritize_children
        cands = [
            {"url": "https://x/belleza", "label": "Belleza", "parent": None},
            {"url": "https://x/moda-mujer/vestidos", "label": "Vestidos", "parent": "moda-mujer"},
            {"url": "https://x/tecno", "label": "Tecno", "parent": None},
            {"url": "https://x/moda-mujer", "label": "Moda Mujer", "parent": None},
        ]
        out = prioritize_children(cands, {"https://x/moda-mujer"})
        urls = [c["url"] for c in out]
        assert urls[0] == "https://x/moda-mujer/vestidos"
        assert urls.index("https://x/moda-mujer") < urls.index("https://x/tecno")


class TestPageSignatureJs:
    def test_signature_js_is_raw_and_valid(self):
        from pathlib import Path as _P
        VA = _P(__file__).resolve().parents[1]
        src = (VA / 'app' / 'scrapers' / 'ripley_scraper.py').read_text(encoding='utf-8')
        i = src.index('async def page_signature')
        body = src[i:i+1400]
        assert 'r"""' in body or chr(39)+chr(39)+chr(39) in body, 'page_signature debe usar raw string para el JS'
        assert chr(92)+'d' not in body.split('evaluate(')[1][:200].replace(chr(92)+chr(92),''), 'no debe haber escapes rotos'


# TestEphemeralFallbackTrigger retirado (09-29): workaround ambiental de -005 no necesario en -006
# (entorno desbloqueado); el fallback TargetClosed en base_scraper queda pendiente documentado.
