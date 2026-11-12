"""P0 coverage semantics: count, EMPTY categories and brand routes."""
from app.mri_dashboard import coverage as C
from app.mri_autonomous.ripley_discovery import _clean_url


def test_categories_discovered_counts_actual_categories():
    cov = C.new_coverage("run", "Ripley", {})
    for cid in ("a", "b"):
        cov["categories"][cid] = {"name": cid, "url": cid, "status": "PENDING",
                                  "pages_observed": 0, "termination": None,
                                  "publications": 0, "last_id": None,
                                  "stop_reason": None}
        C.record_category(cov, cid, pages=1, stop_state="EMPTY", publications=0)
    C.finalize(cov)
    assert cov["categories_discovered"] == 2
    assert cov["categories_traversed_completely"] == 2
    assert cov["acceptance"] == C.AUDIT_PASS


def test_brand_page_is_not_a_category():
    assert _clean_url("https://simple.ripley.cl/moda-mujer/marcas-destacadas/cacharel?brand=NICOPOLY") is None


def test_observations_match_category_by_url_leaf_not_family_prefix():
    from app.mri_dashboard.category_observations import observations_for
    cats = {
        "faldas": {"name": "Moda Mujer → Vestidos y Enteritos → Faldas",
                   "url": "https://simple.ripley.cl/moda-mujer/vestidos-y-enteritos/faldas"},
        "vestidos": {"name": "Moda Mujer → Vestidos y Enteritos → Vestidos",
                     "url": "https://simple.ripley.cl/moda-mujer/vestidos-y-enteritos/vestidos"},
        "enteritos": {"name": "Moda Mujer → Vestidos y Enteritos → Enteritos",
                      "url": "https://simple.ripley.cl/moda-mujer/vestidos-y-enteritos/enteritos"},
    }
    acqs = [
        {"requested_url": "https://simple.ripley.cl/moda-mujer/vestidos-y-enteritos/faldas?brand=NICOPOLY&page={page}", "products_observed_raw": 24},
        {"requested_url": "https://simple.ripley.cl/moda-mujer/vestidos-y-enteritos/vestidos?brand=NICOPOLY&page={page}", "products_observed_raw": 68},
        {"requested_url": "https://simple.ripley.cl/moda-mujer/vestidos-y-enteritos/enteritos?brand=NICOPOLY&page={page}", "products_observed_raw": 7},
    ]
    got = observations_for(cats, acqs)
    assert got == {"faldas": 24, "vestidos": 68, "enteritos": 7}


def test_duplicate_only_category_is_complete_not_failed():
    from app.mri_dashboard import coverage as C
    cov = C.new_coverage("run", "Ripley", {})
    C.record_category(cov, "flare", pages=1, stop_state="EMPTY_DUPLICATE_ONLY", publications=0)
    C.finalize(cov)
    assert cov["categories"]["flare"]["status"] == "COMPLETE"
    assert cov["acceptance"] == C.AUDIT_PASS


def test_taxonomy_summary_reports_discovered_incomplete_not_absent():
    from app.mri_dashboard.taxonomy import summarize
    summary = summarize({"Ripley": {"status": "TAXONOMY_DISCOVERED",
                                    "categories": [{"category_id": "x"}],
                                    "taxonomy_complete": False}})
    assert summary["discovered"]
    assert summary["incomplete"] == ["Ripley"]
    assert summary["complete_scope"] is False
