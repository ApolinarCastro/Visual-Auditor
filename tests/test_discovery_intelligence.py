"""Prior routes are used only when host-valid and are logged."""
from app.mri_dashboard.discovery_intelligence import recover_prior_categories


def test_prior_recovery_filters_cross_host(monkeypatch):
    import app.mri_dashboard.discovery_intelligence as DI
    class CM:
        def get_categories(self, mkt):
            return {"good": {"name": "Blusas", "url": "https://simple.ripley.cl/x"},
                    "bad": {"name": "Otros", "url": "https://www.mercadolibre.cl/x"}}
    monkeypatch.setattr("app.mri_dashboard.category_manager.category_manager", CM())
    state = {}
    cats = DI.recover_prior_categories("Ripley", state)
    assert len(cats) == 1
    assert cats[0]["url"].startswith("https://simple.ripley.cl")
    assert state["discovery_recovery"][0]["dropped_cross_host"] == 1
