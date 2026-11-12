"""Falabella SSR MRI-layer pagination + checkpoint tests (fixtures)."""
from pathlib import Path

import app.mri_dashboard.falabella_ssr_coverage as FB


class FakeEngine:
    """FIXTURE engine: 48 pods/page, `pages` real pages, then empty page."""

    def __init__(self, pages=5, per_page=48, fail_on=None, reported=None,
                 no_count=False):
        self.pages, self.per_page = pages, per_page
        self.fail_on = fail_on
        self.reported = reported if not no_count else -1
        self.calls = []

    def get_category_catalog(self, category_id=None, slug=None, page=1):
        self.calls.append(page)
        if self.fail_on and page == self.fail_on:
            raise RuntimeError("SSR network error")
        count = None if self.reported == -1 else (
            self.reported if self.reported is not None else self.pages * self.per_page)
        if page > self.pages:
            return {"products": [], "reported_count": count,
                    "url": f"https://f/{slug}?page={page}"}
        items = [{"productId": f"{category_id}-p{page}-{i}", "title": f"Polera {page}-{i}",
                  "url": f"https://www.falabella.com/p/{category_id}-{page}-{i}",
                  "seller": "Falabella", "brand": "Nicopoly",
                  "category_id": category_id, "page": page}
                 for i in range(self.per_page)]
        return {"products": items,
                "reported_count": count,
                "url": f"https://f/{slug}?page={page}",
                "sha256": f"sha-{page}"}


CAT = {"category_id": "cat1", "name": "Moda Mujer", "url": "https://f/cat1"}


def test_pagination_goes_beyond_two_pages_and_ends_on_exhaustion():
    eng = FakeEngine(pages=5, per_page=48, no_count=True)
    res = FB.traverse_category(eng, CAT)
    assert res["pages_traversed"] == 6          # 5 real pages + empty terminal page
    assert eng.calls == [1, 2, 3, 4, 5, 6]      # frozen scraper's 2-page cap bypassed
    assert res["publications"] == 5 * 48
    assert res["unique_publications"] == 5 * 48
    assert res["terminal"] == FB.EXHAUSTED
    assert res["complete"] is True
    # evidence preserved per page (url + response hash when available)
    assert res["pages"][0]["url"] and res["pages"][0]["response_sha256"] == "sha-1"


def test_reported_count_reaches_terminal_without_extra_pages():
    eng = FakeEngine(pages=5, per_page=48, reported=96)
    res = FB.traverse_category(eng, CAT)
    assert res["terminal"] == FB.REPORTED_REACHED
    assert res["unique_publications"] == 96
    assert eng.calls == [1, 2]


def test_empty_first_page_is_extractor_failure_not_end_of_catalog():
    eng = FakeEngine(pages=0)
    res = FB.traverse_category(eng, CAT)
    assert res["terminal"] == FB.EXTRACTOR_FAILURE
    assert res["complete"] is False
    assert eng.calls == [1]


def test_safety_page_bound_leaves_category_pending_never_pass():
    eng = FakeEngine(pages=1000, per_page=48, reported=None)
    res = FB.traverse_category(eng, CAT, max_pages=3)
    assert res["terminal"] == FB.PENDING
    assert res["complete"] is False
    assert len(eng.calls) == 3


def test_source_error_marks_blocked_and_keeps_acquired_pages():
    eng = FakeEngine(pages=5, fail_on=3)
    res = FB.traverse_category(eng, CAT)
    assert res["terminal"] == FB.BLOCKED
    assert res["complete"] is False
    assert res["unique_publications"] == 2 * 48      # pages 1-2 kept
    assert len(res["pages"]) == 2


def test_duplicate_ids_across_pages_are_not_counted_twice():
    class DupEngine(FakeEngine):
        def get_category_catalog(self, category_id=None, slug=None, page=1):
            payload = super().get_category_catalog(category_id, slug, page)
            if payload.get("products"):
                payload["products"] = payload["products"][:10] + payload["products"][:10]
            return payload
    res = FB.traverse_category(DupEngine(pages=2, per_page=20, reported=40), CAT)
    assert res["unique_publications"] <= res["publications"]
    ids = [o["product_id"] for o in res["observations"]]
    assert len(ids) == len(set(ids))


def test_checkpoint_per_page_and_resume_without_refetching_confirmed_pages():
    aux = Path("evidence_local_validation/acquisition_truth/_fb_cp")
    aux.mkdir(parents=True, exist_ok=True)
    import uuid
    RUN = f"run_fb_resume_{uuid.uuid4().hex[:8]}"
    eng = FakeEngine(pages=5, per_page=48, fail_on=4)
    first = FB.traverse_categories(eng, [CAT], run_id=RUN, aux_dir=aux)
    cp_path = aux / f"mri_coverage_checkpoint_{RUN}_falabella_ssr.json"
    assert cp_path.exists(), "per-page checkpoint must exist"
    assert not list(aux.glob("*.tmp")), "atomic write must not leave temp files"
    assert first["categories"][0]["terminal"] == FB.BLOCKED
    assert first["categories"][0]["pages_traversed"] == 3

    eng2 = FakeEngine(pages=5, per_page=48)     # recovery: source works again
    second = FB.traverse_categories(eng2, [CAT], run_id=RUN, aux_dir=aux)
    assert eng2.calls and eng2.calls[0] == 4, f"must resume at page 4, calls={eng2.calls}"
    assert second["categories"][0]["terminal"] in (FB.EXHAUSTED, FB.REPORTED_REACHED)
    assert second["checkpoint_resumed"] is True
    ids = [o["product_id"] for o in second["observations"]]
    assert len(ids) == len(set(ids))            # no duplicated identifiers


def test_brand_scope_filters_out_non_nicopoly_products():
    class MixedEngine(FakeEngine):
        def get_category_catalog(self, category_id=None, slug=None, page=1):
            if page > 1:
                return {"products": [], "pagination": {"count": 2}}
            return {"props": {"pageProps": {"pagination": {"count": 4}, "results": [
                {"productId": "N1", "title": "Polera Nicopoly", "brand": "Nicopoly"},
                {"productId": "X1", "title": "Sosten Flores", "brand": "Flores"},
                {"productId": "X2", "title": "Blazer Basement", "brand": "Basement"},
                {"productId": "N2", "title": "Pantalón Nicopoly", "brand": "Nicopoly"}]}}}

        def harvest_sample_publications(self, brand="NICOPOLY", max_items=48,
                                        page_payload=None):
            from types import SimpleNamespace
            pp = (page_payload or {}).get("props", {}).get("pageProps", {})
            pubs = [SimpleNamespace(publication_id=i["productId"], sku=i["productId"],
                                    title=i["title"], canonical_url="https://f/"+i["productId"],
                                    sellers=[i["brand"]], brand=i["brand"], condition="NEW",
                                    source_file_path="f", source_file_sha256="s",
                                    evidence_type="SSR") for i in pp.get("results", [])]
            return pubs, []

    res = FB.traverse_category(MixedEngine(pages=1), {"category_id": "C1", "name": "Mujer",
                                                      "url": "https://f/c1"})
    ids = {o["product_id"] for o in res["observations"]}
    assert ids == {"N1", "N2"}
    assert res["skipped_non_brand"] == 2
    assert res["complete"] is True


def test_repeated_identical_page_is_stall_not_pass():
    class RepeatEngine(FakeEngine):
        def get_category_catalog(self, category_id=None, slug=None, page=1):
            return {"props": {"pageProps": {"pagination": {"count": 500}, "results": [
                {"productId": "SAME-1", "title": "Polera Nicopoly", "brand": "Nicopoly"},
                {"productId": "SAME-2", "title": "Top Nicopoly", "brand": "Nicopoly"}]}}}

        def harvest_sample_publications(self, brand="NICOPOLY", max_items=48,
                                        page_payload=None):
            from types import SimpleNamespace
            pp = (page_payload or {}).get("props", {}).get("pageProps", {})
            pubs = [SimpleNamespace(publication_id=i["productId"], sku=i["productId"],
                                    title=i["title"], canonical_url="https://f/"+i["productId"],
                                    sellers=["Nicopoly"], brand=i["brand"], condition="NEW",
                                    source_file_path="f", source_file_sha256="s",
                                    evidence_type="SSR") for i in pp.get("results", [])]
            return pubs, []

    res = FB.traverse_category(RepeatEngine(pages=1),
                               {"category_id": "C1", "name": "Mujer", "url": "https://f/c1"})
    assert res["terminal"] == FB.NO_PROGRESS
    assert res["complete"] is False
    assert res["pages_traversed"] <= 4          # no runaway to 200
