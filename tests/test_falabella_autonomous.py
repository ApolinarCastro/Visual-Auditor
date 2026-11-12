
"""Autonomous Falabella SSR audit tests (fixtures mirroring the verified report)."""
from pathlib import Path
import app.mri_dashboard.falabella_autonomous as FBA


def _card(pid, sku=None, title="Prenda Nicopoly", price="19.990"):
    return {"productId": str(pid), "skuId": str(sku or int(pid) + 1),
            "displayName": title, "brand": "NICOPOLY",
            "sellerId": "SC75ABC", "sellerName": "Nicopoly",
            "GSCCategoryId": "G08020501",
            "url": f"https://www.falabella.com/falabella-cl/product/{pid}/x",
            "prices": [{"type": "internetPrice", "price": [price]}]}


class EvidenceEngine:
    """Fixtures: brand 415 cards / 377 unique, search and L2 add new ids."""

    def __init__(self):
        ids = [str(100000 + i) for i in range(377)]
        cards = [_card(i) for i in ids]
        cards += [_card(ids[i], sku=int(ids[i]) + 1) for i in range(38)]  # 415 cards, 38 dups
        self.brand_pages = {p: cards[(p - 1) * 48: p * 48] for p in range(1, 10)}
        self.calls = []

    def _payload(self, cards, count=415, facets=None, build="1955d0b3"):
        pp = {"results": cards, "pagination": {"count": count}} if cards else {}
        if facets:
            pp["facets"] = facets
        return {"buildId": build, "props": {"pageProps": pp}}

    def get_category_catalog(self, category_id=None, slug=None, page=1, extra_params=None):
        params = dict(extra_params or {})
        params["page"] = page
        return self.fetch_page_ssr_data(f"/category/{category_id}/x", params)

    def get_brand_catalog(self, brand_name="NICOPOLY", page=1):
        self.calls.append(("brand", page))
        if page > 9:
            return {"buildId": "1955d0b3", "props": {"pageProps": {}}}  # no pagination: end
        facets = [{"name": "Categoría", "facetType": "f.product.L0_category_paths",
                   "values": [{"count": 1511, "id": "cat7330051", "title": "Mujer",
                               "facetType": "f.product.L0_category_paths",
                               "url": "f.product.L0_category_paths=cat7330051%7C%7CMujer"}]}] if page == 1 else None
        return self._payload(self.brand_pages[page], facets=facets)

    def fetch_page_ssr_data(self, path, params=None):
        page = int((params or {}).get("page", 1))
        self.calls.append((path, page))
        if path.startswith("/category/cat7330051"):
            return {"buildId": "b", "props": {"pageProps": {
                "pagination": {"count": 440}, "results": [],
                "facets": [{"name": "Categoría", "facetType": "f.product.L1_category_paths",
                            "values": [{"id": "cat20002", "title": "Moda Mujer",
                                        "facetType": "f.product.L1_category_paths",
                                        "url": "f.product.L1_category_paths=cat7330051%7C%7CMujer%2Fcat20002%7C%7CModa+Mujer"}]}]}}}
        if path.startswith("/category/cat20002"):
            return {"buildId": "b", "props": {"pageProps": {
                "pagination": {"count": 440}, "results": [],
                "facets": [{"name": "Categoría", "facetType": "f.product.L2_category_paths",
                            "values": [
                                {"id": "cat850036", "title": "Abrigos y Chaquetas",
                                 "facetType": "f.product.L2_category_paths",
                                 "url": "f.product.L2_category_paths=cat7330051%7C%7CMujer%2Fcat20002%7C%7CModa+Mujer%2Fcat850036%7C%7CAbrigos"},
                                {"id": "cat850040", "title": "Pantalones",
                                 "facetType": "f.product.L2_category_paths",
                                 "url": "f.product.L2_category_paths=cat7330051%7C%7CMujer%2Fcat20002%7C%7CModa+Mujer%2Fcat850040%7C%7CPantalones"}]}]}}}
        if path.startswith("/category/cat850036"):
            if page == 1:
                return self._payload([_card("DL0000001", sku=1), _card("100000", sku=100001)],
                                     count=2)
            return {"buildId": "b", "props": {"pageProps": {}}}
        if path.startswith("/category/cat850040"):
            if page == 1:
                return self._payload([_card("DL0000002", sku=2)], count=1)
            return {"buildId": "b", "props": {"pageProps": {}}}
        if path == "/search":
            if page == 1:
                return self._payload([_card("DL0000003", sku=3), _card("100001", sku=100002)],
                                     count=2)
            return {"buildId": "b", "props": {"pageProps": {}}}
        return {"buildId": "b", "props": {"pageProps": {}}}


def test_autonomous_audit_matches_verified_evidence():
    audit = FBA.run_full_audit(EvidenceEngine(), brand="NICOPOLY", delay=0)
    brand = audit["surfaces"][0]
    assert brand["surface"] == "brand:NICOPOLY"
    assert brand["expected_cards"] == 415
    assert brand["cards"] == 415
    assert brand["unique_product_ids"] == 377
    assert brand["terminal"] == FBA.EXHAUSTION
    assert audit["build_id"] == "1955d0b3"
    assert audit["categories_discovered"] == 2
    assert audit["complete"] is True
    # union of surfaces: 377 brand + 2 L2-only + 1 search-only = 380
    assert audit["unique_product_ids"] == 380
    assert audit["cards_total"] == 415 + 3 + 2
    assert audit["duplicated_cards"] == audit["cards_total"] - 380
    obs = {o["product_id"]: o for o in audit["observations"]}
    assert len(obs) == 380
    assert obs["DL0000001"]["surfaces"] == ["category:cat850036"]
    assert obs["100000"]["surfaces"][0] == "brand:NICOPOLY"
    assert obs["100000"]["seller_name"] == "Nicopoly"
    assert obs["100000"]["price"] == 19990.0


def test_soft_404_is_not_found_never_success():
    class Soft:
        def get_brand_catalog(self, brand_name="NICOPOLY", page=1):
            return {"props": {"pageProps": {}}}      # 200 without pagination

        def fetch_page_ssr_data(self, path, params=None):
            return {"props": {"pageProps": {}}}

    audit = FBA.run_full_audit(Soft(), brand="NICOPOLY", delay=0, include_search=False)
    brand = audit["surfaces"][0]
    assert brand["terminal"] == FBA.SOFT_404
    assert brand["complete"] is False
    assert audit["complete"] is False


def test_repeated_page_is_no_progress_not_pass():
    class Stall:
        def get_brand_catalog(self, brand_name="NICOPOLY", page=1):
            return {"props": {"pageProps": {
                "results": [_card("1"), _card("2")], "pagination": {"count": 415}}}}

        def fetch_page_ssr_data(self, path, params=None):
            return {"props": {"pageProps": {}}}

    audit = FBA.run_full_audit(Stall(), brand="NICOPOLY", delay=0, include_search=False)
    brand = audit["surfaces"][0]
    assert brand["terminal"] == FBA.NO_PROGRESS
    assert brand["complete"] is False
    assert audit["complete"] is False


def test_missing_l2_discovery_blocks_pass():
    class NoL2(EvidenceEngine):
        def get_brand_catalog(self, brand_name="NICOPOLY", page=1):
            return {"buildId": "x", "props": {"pageProps": {
                "results": [_card("1")], "pagination": {"count": 1},
                "facets": [{"name": "Categoría", "facetType": "f.product.L0_category_paths",
                            "values": [{"id": "cat7330051", "title": "Mujer",
                                        "facetType": "f.product.L0_category_paths",
                                        "url": "f.product.L0_category_paths=cat7330051"}]}]}}}

        def fetch_page_ssr_data(self, path, params=None):
            return {"buildId": "x", "props": {"pageProps": {
                "results": [], "pagination": {"count": 0}}}}

    audit = FBA.run_full_audit(NoL2(), brand="NICOPOLY", delay=0)
    assert audit["categories_discovered"] == 0
    assert audit["complete"] is False
    assert any("L2_NOT_DISCOVERED" in p for p in audit["pending_surfaces"])


def test_403_retry_recovers_one_surface():
    class Flaky(EvidenceEngine):
        def __init__(self):
            super().__init__()
            self.failed = set()

        def get_brand_catalog(self, brand_name="NICOPOLY", page=1):
            if page == 2 and "p2" not in self.failed:
                self.failed.add("p2")
                raise RuntimeError("HTTP Error 403: Forbidden")
            return super().get_brand_catalog(brand_name, page)

    audit = FBA.run_full_audit(Flaky(), brand="NICOPOLY", delay=0, include_search=False)
    brand = audit["surfaces"][0]
    assert brand["terminal"] == FBA.EXHAUSTION
    assert brand["cards"] == 415


def test_persistent_403_is_source_blocked_not_pass():
    class Blocked(EvidenceEngine):
        def get_brand_catalog(self, brand_name="NICOPOLY", page=1):
            raise RuntimeError("HTTP Error 403: Forbidden")

    audit = FBA.run_full_audit(Blocked(), brand="NICOPOLY", delay=0, include_search=False)
    brand = audit["surfaces"][0]
    assert brand["terminal"] == FBA.SOURCE_BLOCKED
    assert audit["complete"] is False


def test_brand_filtered_empty_category_is_complete_not_failure():
    def empty_fetch(page):
        return {"props": {"pageProps": {"results": [], "pagination": {"count": 0}}}}

    res = FBA._paginate(empty_fetch, surface="category:EMPTY", allow_empty=True)
    assert res["terminal"] == FBA.EMPTY
    assert res["complete"] is True
    res2 = FBA._paginate(empty_fetch, surface="brand:NICOPOLY", allow_empty=False)
    assert res2["terminal"] == FBA.NOT_FOUND
    assert res2["complete"] is False


def test_gsc_group_is_grounded_or_explicitly_ambiguous():
    obs = [
        {"product_id": "1", "category_name": "Poleras Mujer", "category_gsc": "G08020501"},
        {"product_id": "2", "category_name": "Blusas Mujer", "category_gsc": "G08020501"},
        {"product_id": "3", "category_gsc": "G08020501"},
        {"product_id": "4", "category_name": "Vestidos y enteritos", "category_gsc": "G08020602"},
        {"product_id": "5", "category_gsc": "G08020602"},
    ]
    stats = FBA._assign_gsc_groups(obs)
    assert stats["ambiguous"] >= 1
    assert obs[2].get("category_name") is None
    assert "Blusas Mujer" in obs[2]["category_group_label"]
    assert "Poleras Mujer" in obs[2]["category_group_label"]
    assert obs[4]["category_name"] == "Vestidos y enteritos"


def test_pdp_breadcrumb_enrichment_and_failure_cache():
    import uuid
    tmp_path = Path("evidence_local_validation/acquisition_truth/_pdp_" + uuid.uuid4().hex[:8])
    tmp_path.mkdir(parents=True, exist_ok=True)
    obs = [{"product_id": "X", "url": "https://www.falabella.com/falabella-cl/product/1/p",
            "category_gsc": "G08020501"}]
    good = '<script type="application/ld+json">{"@type":"BreadcrumbList","itemListElement":[{"position":1,"name":"Mujer - Moda Mujer"},{"position":2,"name":"Poleras Mujer"}]}</script>'
    stats = FBA.enrich_missing_categories(obs, aux_dir=tmp_path, delay=0,
                                          fetcher=lambda url: good)
    assert stats["enriched"] == 1
    assert obs[0]["category_name"] == "Poleras Mujer"
    assert obs[0]["category_source"] == "PDP_BREADCRUMB"

    obs2 = [{"product_id": "Y", "url": "https://www.falabella.com/falabella-cl/product/2/p",
             "category_gsc": "G08020502"}]
    def blocked(url):
        raise RuntimeError("HTTP Error 403: Forbidden")
    stats2 = FBA.enrich_missing_categories(obs2, aux_dir=tmp_path, delay=0,
                                           fetcher=blocked)
    assert stats2["blocked"] == 1
    assert obs2[0].get("category_name") is None


def test_runner_result_never_copies_observed_as_expected():
    rows = FBA.to_runner_results([{
        "product_id": "1", "sku_id": "2", "title": "Polera", "brand": "NICOPOLY",
        "seller_name": "Nicopoly", "category_name": "Poleras Mujer",
        "category_source": "SSR_L2", "category_gsc": "G08020501",
        "url": "https://www.falabella.com/falabella-cl/product/1/p",
        "price": 1000.0, "surface": "category:cat850036", "page": 1,
        "build_id": "b", "position": 1, "observed_at": "2026-10-26T12:00:00"}])
    assert rows[0]["expected_category"] == "SIN_REFERENCIA"
    assert rows[0]["real_category"] == "Poleras Mujer"
    assert rows[0]["commercial_attributes"]["expected_category_status"] == "SIN_REFERENCIA"

    gsc = FBA.to_runner_results([{
        "product_id": "3", "sku_id": "4", "title": "Top", "brand": "NICOPOLY",
        "seller_name": "Nicopoly", "category_gsc": "G08020501",
        "category_group_label": "G08020501 (L2: Blusas Mujer / Poleras Mujer)",
        "category_source": "GSC_ONLY",
        "url": "https://www.falabella.com/falabella-cl/product/3/p",
        "surface": "brand:NICOPOLY", "page": 1, "build_id": "b",
        "position": 2, "observed_at": "2026-10-26T12:00:00"}])
    assert "L2: Blusas Mujer / Poleras Mujer" in gsc[0]["real_category"]
    assert gsc[0]["category_source"] == "GSC_ONLY"


def test_gsc_group_resolved_by_product_title():
    obs = [
        {"product_id": "1", "category_name": "Poleras Mujer", "category_gsc": "G08020501"},
        {"product_id": "2", "category_name": "Blusas Mujer", "category_gsc": "G08020501"},
        {"product_id": "3", "category_gsc": "G08020501",
         "title": "Polera Manga Caída Detalle Calado Oliva",
         "url": "https://www.falabella.com/falabella-cl/product/158189679/polera-manga-caida-detalle-calado-oliva-mujer-nicopoly"},
        {"product_id": "4", "category_gsc": "G08020501",
         "title": "Blusa Bordado Lazos Blanco",
         "url": "https://www.falabella.com/falabella-cl/product/158854709/blusa-bordado-lazos-blanco-mujer-nicopoly"},
    ]
    FBA._assign_gsc_groups(obs)
    assert obs[2]["category_name"] == "Poleras Mujer"
    assert obs[3]["category_name"] == "Blusas Mujer"


def test_specific_category_prefers_smallest_surface():
    sizes = {"Abrigos y Chaquetas": 123, "Sweaters y chalecos": 54,
             "Parkas Mujer": 3}
    assert FBA._specific_category(["Abrigos y Chaquetas", "Sweaters y chalecos"],
                                  sizes) == "Sweaters y chalecos"
    assert FBA._specific_category(["Abrigos y Chaquetas", "Parkas Mujer"],
                                  sizes) == "Parkas Mujer"


def test_top_title_resolved_by_category_token_profile():
    obs = [
        {"product_id": "1", "category_name": "Poleras Mujer", "category_gsc": "G08020501", "title": "Top Básico Mezcla Lino Blanco"},
        {"product_id": "2", "category_name": "Poleras Mujer", "category_gsc": "G08020501", "title": "Polera Manga Corta Básica Negro"},
        {"product_id": "3", "category_name": "Blusas Mujer", "category_gsc": "G08020501", "title": "Blusa Bordado Lazos Blanco"},
        {"product_id": "4", "category_gsc": "G08020501",
         "title": "Top Sin Mangas Acanalado Negro Mujer",
         "url": "https://www.falabella.com/falabella-cl/product/158119375/top-sin-mangas-acanalado-negro-mujer-nicopoly"},
    ]
    FBA._assign_gsc_groups(obs)
    assert obs[3]["category_name"] == "Poleras Mujer"


def test_group_id_prefers_canonical_product_url():
    assert FBA._group_id(
        "https://www.falabella.com/falabella-cl/product/158119375/top-sin-mangas/158119379",
        "158119379") == "158119375"
    assert FBA._group_id("", "158119379") == "158119379"


def test_runner_result_has_variant_and_evidence_contract():
    rows = FBA.to_runner_results([{
        "product_id": "158119375", "variant_id": "158119379",
        "variants": ["158119379"], "group_url": "https://www.falabella.com/falabella-cl/product/158119375/top",
        "sku_id": "158119379", "skus": {"158119379": {"price": 9990.0}},
        "title": "Top Sin Mangas Acanalado Negro Mujer", "brand": "NICOPOLY",
        "seller_name": "Nicopoly", "category_name": "Poleras Mujer",
        "category_source": "SURFACE_SPECIFIC", "category_gsc": "G08020501",
        "url": "https://www.falabella.com/falabella-cl/product/158119375/top",
        "price": 9990.0, "surface": "category:CATG35031", "page": 1,
        "build_id": "88393902", "position": 1,
        "observed_at": "2026-10-26T12:00:00",
    }])
    row = rows[0]
    assert row["producto_id"] == "158119375"
    assert row["variant_ids"] == ["158119379"]
    assert row["sku_ids"] == ["158119379"]
    assert row["commercial_attributes"]["evidence"]["surface"] == "category:CATG35031"
    assert row["commercial_attributes"]["evidence"]["build_id"] == "88393902"
    assert row["commercial_attributes"]["evidence"]["query"] is None
