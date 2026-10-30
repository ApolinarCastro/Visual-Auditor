"""Observations must match category names despite slug differences."""
from app.mri_dashboard.category_observations import observations_for


def test_abrigos_children_and_alias_names_match():
    cats = {
        "a": {"name": "Chaquetas, Parkas y Blazers"},
        "b": {"name": "Chalecos, Sweaters y Cardigans"},
        "c": {"name": "Accesorios de Moda"},
        "d": {"name": "Body"},
        "e": {"name": "Bermudas y Shorts"},
    }
    acqs = [
        {"requested_url": "https://x/abrigos/chaquetas-parkas-blazers/", "products_observed_raw": 199},
        {"requested_url": "https://x/abrigos/chalecos-sweaters-cardigans/", "products_observed_raw": 42},
        {"requested_url": "https://x/accesorios-moda/", "products_observed_raw": 24},
        {"requested_url": "https://x/ropa-interior-dormir/", "products_observed_raw": 4},
        {"requested_url": "https://x/bermudas-shorts/", "products_observed_raw": 18},
    ]
    out = observations_for(cats, acqs)
    assert out["a"] == 199 and out["b"] == 42
    assert out["c"] == 24 and out["d"] == 4 and out["e"] == 18
