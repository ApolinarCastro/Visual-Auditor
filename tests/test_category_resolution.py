"""Single category resolver escalation order."""
import asyncio
from app.mri_dashboard.category_resolution import resolve_categories


class _Tax:
    def __init__(self, status, cats=None):
        self.status = status
        self.cats = cats or []
    async def discover_taxonomy_async(self, mkt, **kw):
        return {"marketplace": mkt, "status": self.status,
                "categories": self.cats, "source": "TEST"}


def test_resolver_returns_live_categories(monkeypatch):
    import app.mri_dashboard.taxonomy as T
    class Eng:
        async def discover_taxonomy_async(self, mkt, **kw):
            return {"marketplace": mkt, "status": "TAXONOMY_DISCOVERED",
                    "categories": [{"category_id": "1", "name": "A",
                                    "url": "https://simple.ripley.cl/a"}],
                    "source": "TEST"}
    monkeypatch.setattr(T, "discover_taxonomy_async", Eng().discover_taxonomy_async)
    res = asyncio.run(resolve_categories("Ripley", None, "https://simple.ripley.cl/x",
                                         "Nicopoly", {}, lambda *a, **k: None))
    assert res["status"] == "TAXONOMY_DISCOVERED"
    assert res["source"] == "TEST"
