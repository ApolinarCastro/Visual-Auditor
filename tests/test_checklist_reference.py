"""Checklist is VALIDATION-ONLY and must not feed autonomous acquisition."""
from pathlib import Path

from app.mri_dashboard.checklist_reference import build_checklist_report


def _checklist():
    return {"authority": "VALIDATION_ONLY", "products": [
        {"group": "GRUPO 1", "sku_padre": "N03049A", "sku_hijo": "N03049AL",
         "name": "Blazer Manga 3/4 Ajustado con Solapas Blanco Nicopoly",
         "channels": {
             "falabella": {"product_id": "156819797",
                           "link": "https://www.falabella.com/falabella-cl/product/156819795/Blazer"},
             "mercado libre": {"product_id": "MLC3532948848",
                               "link": "https://articulo.mercadolibre.cl/MLC-3532948848-x"},
             "ripley": {"product_id": "MPM10000316121", "link": None},
             "paris": {"product_id": "MKO9LCTA36", "link": None}}},
        {"group": "GRUPO 1", "sku_padre": "N03049B-7", "sku_hijo": "N03049BL-7",
         "name": "Blazer Manga 3/4 Ajustado con Solapas Negro Nicopoly",
         "channels": {"falabella": {"product_id": "156818998",
                                    "link": "https://www.falabella.com/falabella-cl/product/156818996/Blazer"}}},
    ]}


def _obs(title, oid, url):
    return {"producto_id": oid, "producto_nombre": title,
            "canonical_url": url, "real_category": "Abrigos y Chaquetas"}


def test_checklist_matches_falabella_by_url_product_id():
    obs = [
        _obs("Blazer Manga 3/4 Ajustado con Solapas Blanco Nicopoly",
             "156819796", "https://www.falabella.com/falabella-cl/product/156819795/Blazer"),
        _obs("Blazer Manga 3/4 Ajustado con Solapas Negro Nicopoly",
             "156818998", "https://www.falabella.com/falabella-cl/product/156818996/Blazer"),
    ]
    r = build_checklist_report(_checklist(), "Falabella", obs)
    assert r["authority"] == "VALIDATION_ONLY"
    assert r["total_products"] == 2
    assert r["coverage"]["published_verified"] == 2
    assert r["coverage"]["missing"] == 0


def test_checklist_missing_when_not_observed():
    obs = [_obs("Blazer Blanco", "156819796",
                "https://www.falabella.com/falabella-cl/product/156819795/Blazer")]
    r = build_checklist_report(_checklist(), "Falabella", obs)
    assert r["coverage"]["missing"] == 1
    assert r["missing"][0]["parent"] == "N03049B-7"


def test_autonomous_engines_do_not_reference_checklist():
    for rel in ("app/mri_dashboard/falabella_autonomous.py",
                "app/mri_dashboard/taxonomy.py",
                "app/mri_autonomous/falabella_ssr_engine.py"):
        src = Path(rel).read_text(encoding="utf-8").lower()
        assert "checklist" not in src, f"checklist leaked into {rel}"
