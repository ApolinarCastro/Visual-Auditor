"""A marketplace run may only navigate its own host."""
from app.mri_dashboard.marketplace_scope import url_allowed, filter_scope


def test_ripley_rejects_mercadolibre_urls():
    assert url_allowed("Ripley", "https://simple.ripley.cl/moda-mujer")
    assert not url_allowed("Ripley", "https://www.mercadolibre.cl/tienda/nicopoly")
    assert not url_allowed("Mercado Libre", "https://simple.ripley.cl/moda")


def test_filter_scope_returns_evidence_of_dropped_categories():
    cats = {
        "a": {"name": "Blusas", "url": "https://simple.ripley.cl/moda/blusas"},
        "b": {"name": "Otros", "url": "https://www.mercadolibre.cl/tienda/nicopoly/otros/"},
    }
    kept, dropped = filter_scope("Ripley", cats)
    assert set(kept) == {"a"}
    assert dropped[0]["reason"] == "MARKETPLACE_HOST_MISMATCH"
