# -*- coding: utf-8 -*-
"""VA-MRI-4MP-E2E-FAILURE-RESOLUTION-001 — Ripley termination bounds (RIP-A..F).

Golden failure 20261006_124152: 32 categorías del menú global (zapatos/belleza/
tecno) a ~35s c/u, 648s sin progreso, kill exterior a 1200s. Sin cota de
no-progreso y sin excepción para rutas con evidencia real de membership.

RIP-A: storefront de marca competidora -> PRUNED
RIP-B: categoría DOM global sin evidencia de relevancia -> PRUNED
RIP-C: ruta comercial relevante (menú estructurado / con brand slug) -> preservada
RIP-D: raw frontier grande pero RELEVANT_PENDING_WORK=0 tras bounded stop -> parada acotada
RIP-E: frontera repetida/sin progreso -> bounded stop
RIP-F: ruta comercial válida SIN brand slug pero con evidencia real de membership
       -> NO debe ser podada únicamente por ausencia del brand slug
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.mri_autonomous.category_discoverer import build_navigation_candidates
from app.mri_autonomous.autonomous_pipeline import (
    classify_unvisited_terminal,
    decide_coverage_status,
)

HUB = "https://simple.ripley.cl/search/nicopoly"
BRAND = "Nicopoly"


def _node(href, label="X", container="dom", **extra):
    n = {"href": href, "label": label, "container": container}
    n.update(extra)
    return n


def test_rip_a_competitor_brand_storefront_pruned():
    cands = build_navigation_candidates(
        [_node("/marcas-destacadas/chanel", "Chanel")], HUB, BRAND)
    assert cands == []


def test_rip_b_global_dom_category_without_relevance_pruned():
    cands = build_navigation_candidates(
        [_node("/tecno/celulares", "Celulares")], HUB, BRAND)
    assert cands == []


def test_rip_c_relevant_commercial_routes_preserved():
    menu = build_navigation_candidates(
        [_node("/moda-mujer/vestidos-y-enteritos", "Vestidos", container="menu_dialog")],
        HUB, BRAND)
    assert len(menu) == 1 and menu[0]["url"].endswith("/moda-mujer/vestidos-y-enteritos")
    branded = build_navigation_candidates(
        [_node("/tienda/nicopoly-oficial", "Tienda Nicopoly")], HUB, BRAND)
    assert len(branded) == 1


def test_rip_f_route_with_membership_evidence_not_pruned_for_missing_slug():
    cands = build_navigation_candidates(
        [_node("/moda-mujer/vestidos-y-enteritos", "Vestidos",
               membership_evidence={"brand": "Nicopoly", "source": "experience_store",
                                    "evidence_id": "ev_x"})],
        HUB, BRAND)
    assert len(cands) == 1
    assert cands[0]["url"].endswith("/moda-mujer/vestidos-y-enteritos")


def test_rip_e_no_progress_streak_and_bounded_stop():
    from app.mri_autonomous.autonomous_pipeline import (
        next_no_progress_streak,
        no_progress_should_stop,
    )
    s = 0
    for _ in range(4):
        s = next_no_progress_streak(s, 0)
    assert s == 4
    assert no_progress_should_stop(s, 5) is False
    s = next_no_progress_streak(s, 0)
    assert no_progress_should_stop(s, 5) is True
    # un hallazgo nuevo resetea la racha
    s = next_no_progress_streak(s, 3)
    assert s == 0
    assert no_progress_should_stop(s, 5) is False
    # límite deshabilitado (0/None) nunca frena
    assert no_progress_should_stop(999, 0) is False


def test_rip_d_large_raw_frontier_relevant_zero_bounded_stop():
    """Tras el bounded stop, la cola restante queda terminal y el cierre es acotado."""
    pruned = [{"category_name": "Automotriz", "stop_reason": "NOT_VISITED",
               "category_type": "NON_COMMERCIAL", "classification_evidence": ["non-commercial"],
               "is_seed_surface": False} for _ in range(50)]
    remaining = [{"category_name": "Zapatos-%d" % i, "stop_reason": "QUEUED",
                  "surface_classification": "COMMERCIAL_CATEGORY", "is_seed_surface": False}
                 for i in range(30)]
    for cat in remaining:
        classify_unvisited_terminal(cat)  # bounded stop terminaliza el resto
    cats = [{"category_name": "Brand Hub", "is_seed_surface": True, "stop_reason": "EXHAUSTION",
             "products_found": 50},
            {"category_name": "Vestidos", "stop_reason": "EXHAUSTION",
             "surface_classification": "COMMERCIAL_CATEGORY", "node_status": "CERTIFIED",
             "products_found": 5, "is_seed_surface": False}] + pruned + remaining
    status, notes, acc = decide_coverage_status(
        cats, resume_override=None, controlled_stop=True,
        any_discovered_categories=True, base_notes_text="")
    assert status == "PARTIAL"  # nunca CONFIRMED con controlled stop
    assert acc["raw_frontier_remaining"] == 50  # solo los podados quedan RAW
    assert acc["relevant_pending_work"] is False
    assert any("CONTROLLED_STOP" in n for n in notes)
    leftovers = [c for c in cats if c.get("stop_reason") in (None, "QUEUED", "NOT_VISITED")
                 and not c.get("is_seed_surface") and not c.get("classification_evidence")]
    assert leftovers == []  # nada quedó sin clasificar de forma no verificable
