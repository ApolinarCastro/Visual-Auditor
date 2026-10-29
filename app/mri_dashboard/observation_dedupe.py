"""Run-wide observation dedupe (no production scraper changes)."""
from __future__ import annotations


def product_id(product: dict) -> str:
    return str(
        product.get("marketplace_sku")
        or product.get("sku")
        or product.get("product_id")
        or ""
    ).upper()


def filter_new_products(products: list[dict], seen: set[str]) -> tuple[list[dict], int]:
    """Keep first occurrence of each id; count repeated observations."""
    new_products = []
    for product in products or []:
        pid = product_id(product)
        if not pid or pid not in seen:
            if pid:
                seen.add(pid)
            new_products.append(product)
    return new_products, len(products or []) - len(new_products)
