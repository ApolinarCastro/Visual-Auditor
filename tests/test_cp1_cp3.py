"""CP1 Falabella expected category + CP3 observation reconciliation."""
from app.mri_dashboard.mri_runner import resolve_master_category_by_title
from app.mri_autonomous.category_evaluator import evaluate_commercial_category
from app.mri_dashboard.observation_reconciliation import summarize_results


def test_falabella_expected_category_is_independent_and_classified():
    expected = resolve_master_category_by_title(
        "Polera Entallada Escote Cuadrado Negro Nicopoly")
    assert expected == "Ropa - Ropa Mujer - Poleras - Poleras Sin Manga"
    out = evaluate_commercial_category(
        product_title="Polera Entallada Escote Cuadrado Negro Nicopoly",
        expected_category=expected,
        observed_category="Poleras Mujer",
        marketplace="Falabella",
        identity_status="OFFICIAL_VERIFIED")
    assert out["decision"] == "CORRECT"


def test_unknown_master_title_stays_unverified():
    assert resolve_master_category_by_title("Producto inexistente XYZ") is None


def test_observations_vs_unique_publications_are_explicit():
    rows = [
        {"observed_sku": "MLC1", "marketplace": "Mercado Libre"},
        {"observed_sku": "MLC1", "marketplace": "Mercado Libre"},
        {"observed_sku": "MLC2", "marketplace": "Mercado Libre"},
    ]
    summary = summarize_results(rows)
    assert summary["observations"] == 3
    assert summary["unique_publications"] == 2
    assert summary["duplicate_observations"] == 1


def test_taxonomy_scope_does_not_inherit_persistent_categories():
    from app.mri_dashboard.taxonomy_scope import categories_from_taxonomy
    tax = {"categories": [
        {"category_id": "STORE", "name": "Tienda", "url": "https://www.mercadolibre.cl/tienda/nicopoly", "acquisition": True},
        {"category_id": "REF", "name": "Blusas", "url": "https://listado.mercadolibre.cl/tienda/nicopoly/listado/vestuario-calzado/blusas/", "acquisition": True},
        {"category_id": "OLD", "name": "Generic", "url": "https://listado.mercadolibre.cl/vestuario-calzado/blusas/", "acquisition": False},
    ]}
    cats = categories_from_taxonomy(tax)
    assert set(cats) == {"STORE", "REF", "OLD"}
    assert cats["OLD"]["acquisition"] is False
