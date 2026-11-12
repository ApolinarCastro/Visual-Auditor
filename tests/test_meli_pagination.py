"""ML offset pagination recovery and Body alias."""
from app.mri_dashboard.meli_pagination import next_page_url, unique_new_products
from app.mri_dashboard.discovery_kernel import _canonical_category_name


def test_next_page_url_uses_path_segment():
    url = "https://listado.mercadolibre.cl/tienda/nicopoly/listado/vestuario-calzado/pantalones/"
    assert next_page_url(url, 49).endswith("/pantalones/_Desde_49")
    assert "?_Desde" not in next_page_url(url, 49)


def test_recovery_keeps_only_new_products():
    existing = [{"marketplace_sku": "MLC1"}]
    incoming = [{"marketplace_sku": "MLC1"}, {"marketplace_sku": "MLC2"}]
    new = unique_new_products(existing, incoming)
    assert [p["marketplace_sku"] for p in new] == ["MLC2"]


def test_ropa_interior_is_reported_as_body():
    assert _canonical_category_name("Ropa Interior y de Dormir") == "Body"
