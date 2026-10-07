"""
Brand hubs: deterministic seed surfaces derived ONLY from MARKETPLACE + BRAND.
No category list, no SVMP, no manual URL list.
"""

from dataclasses import dataclass
from typing import Dict

@dataclass
class BrandHub:
    marketplace: str
    brand: str
    canonical_reference: str
    surface_type: str
    discovery_method: str

def brand_hub_for(marketplace: str, brand: str = "Nicopoly") -> BrandHub:
    """
    Deterministically generates brand hub URL from marketplace + brand.
    This is the ONLY input-derived seed. All categories are discovered from the hub DOM.
    """
    m = marketplace.strip().lower()
    b = brand.strip().lower()
    # Brand hubs are search / brand-store URLs, NOT category URLs.
    if m == "paris":
        # Paris brand search - returns all Nicopoly products with category facets
        return BrandHub(marketplace="Paris", brand=brand,
                        canonical_reference=f"https://www.paris.cl/search?q={b}",
                        surface_type="BRAND_SEARCH",
                        discovery_method="BRAND_SEARCH_PARIS")
    elif m == "falabella":
        return BrandHub(marketplace="Falabella", brand=brand,
                        canonical_reference=f"https://www.falabella.com/falabella-cl/search?Ntt={b}",
                        surface_type="BRAND_SEARCH",
                        discovery_method="BRAND_SEARCH_FALABELLA")
    elif m in ("mercado libre", "mercadolibre", "meli"):
        # ML has two hubs: official store + general search grid. Primary is store.
        return BrandHub(marketplace="Mercado Libre", brand=brand,
                        canonical_reference=f"https://www.mercadolibre.cl/tienda/{b.lower()}",
                        surface_type="BRAND_STORE",
                        discovery_method="BRAND_STORE_ML")
    elif m == "ripley":
        return BrandHub(marketplace="Ripley", brand=brand,
                        canonical_reference=f"https://simple.ripley.cl/search/{b.lower()}",
                        surface_type="BRAND_SEARCH",
                        discovery_method="BRAND_SEARCH_RIPLEY")
    else:
        raise ValueError(f"Unsupported marketplace: {marketplace}")

BRAND_HUB_MAP: Dict[str, BrandHub] = {}
