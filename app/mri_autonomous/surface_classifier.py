"""Generic surface classifier (core, marketplace-agnostic).

Every discovered candidate is classified BEFORE it can become a taxonomy
node. Classification uses only generic URL/DOM signals — no hardcoded
category names, no SVMP, no marketplace branching on names.

A candidate is NEVER a taxonomy node by itself: certify_node() requires
direct commercial evidence (Nicopoly products observed on that surface).
navigation_link => category without evidence is PROHIBITED by construction.
"""

import re
from typing import Dict, List, Any
from urllib.parse import urlparse, parse_qs

TYPES = (
    "BRAND_SURFACE",
    "COMMERCIAL_CATEGORY",
    "COMMERCIAL_SUBCATEGORY",
    "PRODUCT_TYPE",
    "FULFILLMENT_FACET",
    "ATTRIBUTE_FACET",
    "GENERAL_NAVIGATION",
    "CORPORATE_NAVIGATION",
    "PDP",
    "SEARCH_VARIANT",
    "SORT_VARIANT",
    "PAGINATION",
    "UNKNOWN",
)

_PDP_RES = [r"/p/", r"/mp/", r"-mpm", r"/product/", r"/dp/", r"/pdp/",
             r"\.html$"]
_PAGINATION_RES = [r"_Desde_\d+", r"[?&](page|p|offset)=\d+"]
_SORT_RES = [r"OrderId", r"[?&](sort|orden|order)="]
_FULFILLMENT_RES = [r"fulfillment", r"retiro", r"pickup", r"delivery",
                    r"shipping", r"envio", r"stock", r"disponib"]
_FACET_RES = [r"[?&](f|filter|facet|faceta)=", r"_Filters", r"Sidebar",
              r"_Available", r"Noindex", r"NoIndex", r"PriceRange",
              r"Discount", r"Filtrable", r"%2[aA]", r"\*", r"#"]
_CORPORATE_RES = [r"/sostenibilidad", r"/ayuda", r"/help", r"/about",
                  r"/tiendas", r"/sustentab", r"/trabaja", r"/contact"]
_GENERAL_NAV_RES = [r"/addresses/", r"/navigation/hub", r"/navigation/",
                    r"/account-verification", r"/registration", r"/login",
                    r"/gz/", r"/mi-cuenta", r"/iniciar-sesion", r"/centro-de-ayuda",
                    r"/seguimiento", r"/legales/", r"/terminos"]
_CATEGORY_PATH_RES = [r"/category/", r"/categoria",
                      r"/tienda/", r"/c/", r"/departamento", r"_Tienda_"]
_SEARCH_RES = [r"/search", r"[?&]Ntt=", r"[?&]q="]


def _hit(url: str, patterns: List[str]) -> str:
    for pat in patterns:
        if re.search(pat, url, re.IGNORECASE):
            return pat
    return ""


def classify_surface(url: str, dom: Dict[str, Any] = None) -> Dict[str, Any]:
    """Classify a candidate URL. Pure function; no I/O."""
    dom = dom or {}
    u = url or ""
    evidence: List[str] = []

    m = _hit(u, _PDP_RES)
    if m:
        return {"surface_type": "PDP", "confidence": 0.95,
                "evidence": [f"pdp-signal:{m}"]}
    m = _hit(u, _PAGINATION_RES)
    if m:
        return {"surface_type": "PAGINATION", "confidence": 0.9,
                "evidence": [f"pagination-signal:{m}"]}
    m = _hit(u, _SORT_RES)
    if m:
        return {"surface_type": "SORT_VARIANT", "confidence": 0.85,
                "evidence": [f"sort-signal:{m}"]}
    m = _hit(u, _FULFILLMENT_RES)
    if m:
        return {"surface_type": "FULFILLMENT_FACET", "confidence": 0.8,
                "evidence": [f"fulfillment-signal:{m}"]}
    m = _hit(u, _FACET_RES)
    if m:
        return {"surface_type": "ATTRIBUTE_FACET", "confidence": 0.8,
                "evidence": [f"facet-signal:{m}"]}
    m = _hit(u, _GENERAL_NAV_RES)
    if m:
        return {"surface_type": "GENERAL_NAVIGATION", "confidence": 0.95,
                "evidence": [f"general-nav-signal:{m}"]}
    m = _hit(u, _CORPORATE_RES)
    if m:
        return {"surface_type": "CORPORATE_NAVIGATION", "confidence": 0.9,
                "evidence": [f"corporate-signal:{m}"]}

    # Brand surface: search/store URL whose terminal slug is the brand itself,
    has_cat_query = any(k in u.lower() for k in [
        "tipoproducto", "category=", "categoria=", "cat=",
        "attribute.tipo", "l0_category_paths", "f.product."
    ])
    brand = str((dom or {}).get("brand", "")).lower().strip()
    try:
        path = urlparse(u).path.lower().rstrip("/")
        last = path.split("/")[-1] if path else ""
    except Exception:
        last = ""
    if not has_cat_query and brand and (last == brand or f"q={brand}" in u.lower()
                  or f"ntt={brand}" in u.lower()
                  or last == f"{brand}_tienda_{brand}"):
        return {"surface_type": "BRAND_SURFACE", "confidence": 0.9,
                "evidence": ["terminal-slug==brand or brand query param"]}

    if has_cat_query:
        return {"surface_type": "COMMERCIAL_CATEGORY", "confidence": 0.7,
                "evidence": ["category-facet-query-param",
                             "CANDIDATE-ONLY: needs direct commercial evidence"]}

    m = _hit(u, _CATEGORY_PATH_RES)
    if m:
        return {"surface_type": "COMMERCIAL_CATEGORY", "confidence": 0.6,
                "evidence": [f"category-path-signal:{m}",
                             "CANDIDATE-ONLY: needs direct commercial evidence"]}
    # Structural fallback (generic, no vocabulary): a deep non-search path
    # is category-shaped; a bare search route is not.
    try:
        segs = [s for s in urlparse(u).path.split("/") if s]
    except Exception:
        segs = []
    if len(segs) >= 2 and segs[0].lower() not in ("search", "buscar"):
        return {"surface_type": "COMMERCIAL_CATEGORY", "confidence": 0.55,
                "evidence": [f"deep-path:{len(segs)}-segments",
                             "CANDIDATE-ONLY: needs direct commercial evidence"]}
    if _hit(u, _SEARCH_RES):
        return {"surface_type": "SEARCH_VARIANT", "confidence": 0.55,
                "evidence": ["search-shape without brand terminal",
                             "CANDIDATE-ONLY: needs direct commercial evidence"]}
    if dom.get("breadcrumb"):
        evidence.append("breadcrumb-present")
    return {"surface_type": "UNKNOWN", "confidence": 0.3,
            "evidence": evidence or ["no-signal-matched"]}


def certify_node(classification: Dict[str, Any], products_observed: int,
                 nicopoly_present: int) -> Dict[str, Any]:
    """A node is certified ONLY with direct commercial evidence.

    Certified  <=>  products observed AND Nicopoly products among them.
    Everything else stays CANDIDATE / REJECTED / UNCONFIRMED — never taxonomy.
    """
    stype = (classification or {}).get("surface_type", "UNKNOWN")
    if products_observed > 0 and nicopoly_present > 0:
        if stype == "BRAND_SURFACE":
            _ntype = "BRAND_SURFACE"
        elif stype in ("COMMERCIAL_CATEGORY", "COMMERCIAL_SUBCATEGORY"):
            _ntype = "CATEGORY"
        else:
            _ntype = "SURFACE"
        return {"certified": True,
                "node_type": _ntype,
                "evidence": (classification or {}).get("evidence", [])
                + [f"direct-commercial-evidence:{nicopoly_present}/"
                   f"{products_observed} nicopoly products observed"]}
    if products_observed > 0:
        return {"certified": False, "node_type": None,
                "reason": "REJECTED_CANDIDATE: products observed but zero "
                          "Nicopoly evidence — navigation, not taxonomy"}
    return {"certified": False, "node_type": None,
            "reason": "UNCONFIRMED: zero products observed"}
