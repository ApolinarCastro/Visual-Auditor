"""Master category mapping and leaf-equivalence regression."""
from app.mri_autonomous.category_evaluator import evaluate_commercial_category
import app.mri_dashboard.mri_api as api


def test_master_category_is_category_not_brand():
    api._master_catalog_cache = None
    child, parent, title, tokens = api.get_master_catalog()
    entry = parent.get("N05299I") or child.get("N05299IM")
    assert entry is not None
    assert entry["category"] != "Nicopoly"
    assert entry["category"].startswith("Ropa - Ropa Mujer - Chaquetas")
    assert "Blazers" in entry["category"]


def test_blazer_leaf_equivalence_is_correct():
    out = evaluate_commercial_category(
        product_title="BLAZER CUELLO CRUZADO GRIS MUJER NICOPOLY",
        expected_category="Ropa - Ropa Mujer - Chaquetas - Blazers",
        observed_category="Moda Mujer → Tops y chaquetas → Chaquetas y blazers",
        identity_status="PARENT_IDENTITY_VERIFIED",
        marketplace="Ripley",
    )
    assert out["decision"] == "CORRECT"


def test_blusa_leaf_equivalence_is_correct():
    out = evaluate_commercial_category(
        product_title="BLUSA VUELOS MANGA LARGA CAFE MUJER NICOPOLY",
        expected_category="Ropa - Ropa Mujer - Blusas - Blusas",
        observed_category="Moda Mujer → Tops y chaquetas → Blusas y poleras",
        identity_status="PARENT_IDENTITY_VERIFIED",
        marketplace="Ripley",
    )
    assert out["decision"] == "CORRECT"


def test_blusa_subtype_master_matches_ripley_category_level():
    out = evaluate_commercial_category(
        product_title="BLUSA VUELOS MANGA LARGA CAFE MUJER NICOPOLY",
        expected_category="Ropa - Ropa Mujer - Blusas - Blusas Manga Larga",
        observed_category="Moda Mujer → Tops y chaquetas → Blusas y poleras",
        identity_status="PARENT_IDENTITY_VERIFIED",
        marketplace="Ripley",
    )
    assert out["decision"] == "CORRECT"


def test_pantalones_parent_jeans_does_not_contradict_leaf():
    out = evaluate_commercial_category(
        product_title="PANTALON BASICO CELESTE MUJER NICOPOLY",
        expected_category="Ropa - Ropa Mujer - Pantalones - Pantalones Casuales",
        observed_category="Moda Mujer → Jeans y Pantalones → Pantalones",
        identity_status="PARENT_IDENTITY_VERIFIED",
        marketplace="Ripley",
    )
    assert out["decision"] == "CORRECT"
