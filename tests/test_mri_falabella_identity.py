# -*- coding: utf-8 -*-
"""VA-MRI-4MP-E2E-FAILURE-RESOLUTION-001 — Falabella identity (fixture de estructura REAL).

Observado en el golden run 20261006_124152: productos Falabella con
vendor='NICOPOLY' (brandName del SSR), sin master SKU y con títulos SIN la marca
("Blazer Manga 3/4 ... Mujer") fueron rechazados como INSUFFICIENT_EVIDENCE.

Contrato:
- un producto con evidencia vendor/brand = NICOPOLY sobrevive RAW -> NORMALIZED -> IDENTITY
  como Nicopoly (publicación aceptada);
- un producto de otra marca NO debe convertirse en Nicopoly.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.mri_autonomous.autonomous_pipeline import materialize_discovered_products


def _falabella_like(sku="156820392", vendor="NICOPOLY", pos=1,
                    title="Blazer Manga 3/4 Ajustado con Solapas Amarillo Mantequilla Mujer"):
    return {
        "title": title,
        "vendor": vendor,
        "marketplace_sku": sku,
        "price": 37790.0,
        "position_absolute": pos,
        "_discovered_categories": ["Brand Hub"],
    }


def _discovery(products):
    return {"marketplace": "Falabella", "products": products,
            "discovered_categories": [], "category_node_types": {}}


def test_nicopoly_vendor_survives_raw_to_publication():
    res = materialize_discovered_products(_discovery([
        _falabella_like(sku="156820392", pos=1),
        _falabella_like(sku="156908472", pos=2,
                        title="Blazer Rayas Diplomaticas Cafe Mujer"),
    ]), "va_test_falabella_identity")
    assert res["terminal_states"]["NICOPOLY_CONFIRMED"] == 2
    assert len(res["accepted"]) == 2
    for acc in res["accepted"]:
        assert acc["membership"]["classification"] == "NICOPOLY_CONFIRMED"
        assert acc["evidence"]["membership_classification"] == "NICOPOLY_CONFIRMED"


def test_other_brand_is_not_converted_to_nicopoly():
    res = materialize_discovered_products(_discovery([
        _falabella_like(sku="999000111", vendor="BUFFALO CHILE",
                        title="Parka Invierno Mujer"),
        _falabella_like(sku="999000112", vendor="", title="Polera Basica Negra"),
    ]), "va_test_falabella_identity")
    assert res["terminal_states"]["NICOPOLY_CONFIRMED"] == 0
    assert len(res["accepted"]) == 0


def test_direct_classifier_accepts_explicit_brand_field():
    from mri_commercial_materialization_golden_slice.v001.materializer_engine import (
        GenericCommercialMaterializer,
    )
    mat = GenericCommercialMaterializer("va_test_falabella_identity")
    now = datetime.now().strftime("%Y-%m-%d")
    norm = mat.normalize_observation({
        "id": 1, "marketplace": "Falabella", "marketplace_sku": "156820392",
        "sku_master": "", "product_title": "Blazer Manga 3/4 Ajustado con Solapas Amarillo Mujer",
        "brand": "NICOPOLY", "price": 37790.0, "position_absolute": 1,
        "created_at": now + "T12:00:00", "audit_date": now,
        "category": "Brand Hub", "is_nicopoly": 1,
    })
    membership = mat.validate_nicopoly_membership(
        norm, {"status": "RESOLVED", "publication_id": "pub_x", "marketplace_product_id": "156820392"})
    assert membership["classification"] == "NICOPOLY_CONFIRMED"
