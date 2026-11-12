"""MRI-REPOSITORY-RECONCILIATION-001 contracts."""
import asyncio
import inspect

from app.mri_autonomous.category_evaluator import evaluate_commercial_category
from app.mri_dashboard import taxonomy as T


class _FakePage:
    pass


class _FakeScraper:
    page = _FakePage()


def test_ripely_taxonomy_has_one_sync_and_one_async_definition():
    src = inspect.getsource(T)
    assert src.count("def ripely_taxonomy(scraper") == 1
    assert src.count("async def ripely_taxonomy_async") == 1


def test_ripley_missing_live_categories_is_unavailable_not_static_fallback(monkeypatch):
    async def _empty(*a, **k):
        return []

    monkeypatch.setattr(
        "app.mri_autonomous.category_discoverer.discover_categories_from_page", _empty)
    monkeypatch.setattr(
        "app.mri_autonomous.ripley_discovery.discover_live_categories", _empty)
    res = asyncio.run(T.ripely_taxonomy_async(_FakeScraper(), "https://hub"))
    assert res["status"] == T.UNAVAILABLE
    assert res["categories"] == []
    assert res["taxonomy_complete"] is False
    assert res["coverage_scope"] == "NO_CATEGORIES_DISCOVERED"
    assert res["pending_scope"]


def test_ripley_live_taxonomy_is_discovered_not_automatically_complete(monkeypatch):
    async def _urls(*a, **k):
        return ["https://simple.ripley.cl/moda-mujer/tops-y-chaquetas"]

    monkeypatch.setattr(
        "app.mri_autonomous.category_discoverer.discover_categories_from_page", _urls)
    res = asyncio.run(T.ripely_taxonomy_async(_FakeScraper(), "https://hub"))
    assert res["status"] == T.DISCOVERED
    assert res["taxonomy_complete"] is False
    assert T.summarize({"Ripley": res})["complete_scope"] is False


def test_missing_live_categories_is_never_complete_scope(monkeypatch):
    async def _empty(*a, **k):
        return []

    monkeypatch.setattr(
        "app.mri_autonomous.category_discoverer.discover_categories_from_page", _empty)
    monkeypatch.setattr(
        "app.mri_autonomous.ripley_discovery.discover_live_categories", _empty)
    res = asyncio.run(T.ripely_taxonomy_async(_FakeScraper(), "https://hub"))
    summary = T.summarize({"Ripley": res})
    assert summary["unavailable"]
    assert summary["complete_scope"] is False


def test_expected_category_missing_is_no_verificado():
    out = evaluate_commercial_category(
        product_title="Blazer Negro Nicopoly",
        expected_category="NO_VERIFICADO",
        observed_category="Blusas y Poleras",
        identity_status="TARGET_IDENTITY_VERIFIED",
    )
    assert out["decision"] == "NO_VERIFICADO"
    assert out["expected_category_status"] == "SIN_REFERENCIA"


def test_expected_category_independent_allows_evaluation():
    out = evaluate_commercial_category(
        product_title="Blazer Negro Nicopoly",
        expected_category="Chaquetas y Blazers",
        observed_category="Blazer",
        identity_status="TARGET_IDENTITY_VERIFIED",
    )
    assert out["decision"] != "NO_VERIFICADO"
