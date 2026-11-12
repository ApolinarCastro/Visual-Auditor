"""Run-wide dedupe prevents recommendation-carousel contamination."""
from app.mri_dashboard.observation_dedupe import filter_new_products


def test_duplicate_ids_are_dropped_and_counted():
    seen = set()
    products = [{"marketplace_sku": "MLC1"}, {"marketplace_sku": "MLC1"},
                {"marketplace_sku": "MLC2"}, {"product_id": "MLC2"}]
    new, dup = filter_new_products(products, seen)
    assert [p.get("marketplace_sku") or p.get("product_id") for p in new] == ["MLC1", "MLC2"]
    assert dup == 2
    assert seen == {"MLC1", "MLC2"}
