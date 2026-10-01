"""
Category Alignment Engine — VA-PRODUCT-TAXONOMY-CAPABILITY-001

Minimal, deterministic capability to resolve:
  PRODUCT_TITLE → CANONICAL_PRODUCT_TYPE → EXPECTED_MARKETPLACE_CATEGORIES
  + OBSERVED_CATEGORIES → CATEGORY_ALIGNMENT

Principles (from VA-EXECUTIVE-DASHBOARD-SEMANTIC-AUDIT-001 / D-029):
  PUBLICADO ≠ CORRECTAMENTE CATEGORIZADO ≠ VISIBLE

Rules enforced:
  - Brand Hub is NOT a commercial category.
  - Legacy configured category is NOT automatically the expected category.
  - Absence of observation does NOT prove MISALIGNED without coverage evidence.
  - Many-to-many publication ↔ category is legal (MULTI_CATEGORY).
  - Unknown product type → UNRESOLVED.
  - No brand/publication hardcode in alignment logic.

This module is PURE / NO-I/O at the alignment layer.
DB integration is provided by run_alignment_on_db() for operational use.
"""

from __future__ import annotations

import re
import sqlite3
import os
from enum import Enum
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Alignment status enum
# ──────────────────────────────────────────────────────────────────────────────

class AlignmentStatus(str, Enum):
    ALIGNED = "ALIGNED"
    MISALIGNED = "MISALIGNED"
    MULTI_CATEGORY = "MULTI_CATEGORY"
    UNRESOLVED = "UNRESOLVED"


# ──────────────────────────────────────────────────────────────────────────────
# Non-commercial surfaces — observing a product here does NOT confirm
# presence in a commercial category corridor.
# ──────────────────────────────────────────────────────────────────────────────

NON_COMMERCIAL_SURFACES: frozenset[str] = frozenset({
    "Brand Hub",
    "Brand Store",
    "Brand Navigation",
    "Search Grid",
    "General Navigation",
    "Department Facet",
    "Brand Surface",
    "Mujer",
    "Hombre",
    "Niños",
    "New In",
    "Gillette",           # Ripley non-fashion surface
})


# ──────────────────────────────────────────────────────────────────────────────
# Sub-category equivalence: observed sub-category counts as presence in parent.
# Derived from real mri_categories data — NOT hardcoded marketplace logic.
# A product observed in "Poleras" is within the "Poleras y Blusas" corridor.
# A product observed in "Sweaters" is within "Sweaters, Chalecos y Tejidos".
# ──────────────────────────────────────────────────────────────────────────────

# Maps: parent_category_name → frozenset of sub-category names that qualify as
# evidence of presence in that parent commercial corridor.
_SUBCATEGORY_EQUIVALENCES: dict[str, frozenset[str]] = {
    # Paris
    "Poleras y Blusas": frozenset({"Poleras", "Blusas", "Poleras y Blusas", "Calzas", "Polerones"}),
    "Blazers, Chaquetas y Abrigos": frozenset({
        "Blazers", "Chaquetas", "Abrigos", "Parkas",
        "Blazers, Chaquetas y Abrigos", "Chaquetas y Abrigos",
    }),
    "Sweaters, Chalecos y Tejidos": frozenset({
        "Sweaters", "Chalecos", "Sweaters, Chalecos y Tejidos",
        "Sweaters y chalecos",
    }),
    "Vestidos y Faldas": frozenset({
        "Vestidos", "Faldas", "Vestidos y Faldas",
        "Vestidos De Fiesta", "Enteritos",
    }),
    "Jeans y Pantalones": frozenset({
        "Jeans", "Pantalones", "Jeans y Pantalones",
    }),
    # Falabella
    "Abrigos y Chaquetas": frozenset({
        "Abrigos", "Chaquetas", "Parkas", "Abrigos y Chaquetas",
        "Parkas Mujer",
    }),
    "Blusas": frozenset({"Blusas", "Blusas Mujer", "Camisas"}),
    "Cardigans": frozenset({"Cardigans", "Sweaters y chalecos", "Sweaters"}),
    "Chaquetas Parkas Blazers": frozenset({
        "Chaquetas", "Parkas", "Blazers", "Abrigos",
        "Chaquetas Parkas Blazers",
    }),
    # Mercado Libre
    "Chaquetas Parkas Blazers": frozenset({
        "Chaquetas Parkas Blazers", "Abrigos",
    }),
}


def _observed_matches_expected(observed_category: str, expected_category: str) -> bool:
    """
    Return True if observed_category is the expected_category itself OR
    is a known sub-category of the expected commercial corridor.
    """
    if observed_category == expected_category:
        return True
    equiv = _SUBCATEGORY_EQUIVALENCES.get(expected_category, frozenset())
    return observed_category in equiv


# ──────────────────────────────────────────────────────────────────────────────
# Canonical product type → keyword patterns
# Ordered from most-specific to least-specific.
# Resolution uses first match (greedy specificity).
# ──────────────────────────────────────────────────────────────────────────────

_PRODUCT_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    # Outerwear — must be before generic "Chaqueta"
    ("Abrigo",       [r"\babrigo\b"]),
    ("Parka",        [r"\bparka\b"]),
    ("Trench",       [r"\btrench\b"]),
    ("Bomber",       [r"\bbomber\b"]),
    # Blazers / suit jackets — before Chaqueta
    ("Blazer",       [r"\bblazers?\b"]),
    # Jackets
    ("Chaqueta",     [r"\bchaqueta\b"]),
    # Cardigans / sweaters / gilets
    ("Cardigan",     [r"\bc[aá]rdigan\b"]),
    ("Sweater",      [r"\bsweater\b"]),
    ("Gilet",        [r"\bgilet\b"]),
    # Bottoms
    ("Jeans",        [r"\bjeans\b"]),
    ("Pantalon",     [r"\bpantal[oó]n\b"]),
    ("Shorts",       [r"\bshorts?\b", r"\bbermudas?\b"]),
    ("Falda",        [r"\bfalda\b"]),
    # Tops
    ("Polera",       [r"\bpolera\b"]),
    ("Blusa",        [r"\bblusa\b"]),
    ("Camisa",       [r"\bcamisa\b"]),
    ("Kimono",       [r"\bkimono\b"]),
    ("Top",          [r"\btop\b"]),
    ("Body",         [r"\bbody\b", r"\bbodies\b"]),
    ("Calza",        [r"\bcalzas?\b", r"\bleggings?\b"]),
    # Dresses / skirts combined
    ("Vestido",      [r"\bvestido\b"]),
    # Sets / conjuntos
    ("Conjunto",     [r"\bconjunto\b", r"\bset\b"]),
    ("Vest",         [r"\bvest\b"]),
]


def resolve_product_type(title: str) -> Optional[str]:
    """
    Deterministically map a product title to a canonical product type.

    Strategy: ordered regex match on normalised title.
    Returns None when no type can be determined.

    Parameters
    ----------
    title : str
        Raw variant title from mri_variants.variant_title.

    Returns
    -------
    str or None
        Canonical product type string, or None if unresolvable.
    """
    if not title:
        return None
    normalised = title.lower()
    for product_type, patterns in _PRODUCT_TYPE_PATTERNS:
        for pat in patterns:
            if re.search(pat, normalised, re.IGNORECASE):
                return product_type
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Marketplace-specific expected category mapping
# Derived from real mri_categories rows observed in the DB.
# Key: (marketplace_normalised, canonical_product_type)
# Value: list of expected category names (primary first)
# ──────────────────────────────────────────────────────────────────────────────

# Normalisation helper
def _norm_mp(marketplace: str) -> str:
    return marketplace.lower().replace(" ", "_").replace("é", "e").replace("á", "a")


# Mapping uses canonical category names as they appear in mri_categories.category_name
_EXPECTED_CATEGORY_MAP: dict[tuple[str, str], list[str]] = {
    # ── MERCADO LIBRE ────────────────────────────────────────────────────────
    ("mercado_libre", "Vestido"):   ["Vestidos"],
    ("mercado_libre", "Calza"):     ["Calzas"],
    ("mercado_libre", "Blusa"):     ["Blusas"],
    ("mercado_libre", "Polera"):    ["Poleras"],
    ("mercado_libre", "Falda"):     ["Faldas"],
    ("mercado_libre", "Abrigo"):    ["Abrigos", "Chaquetas Parkas Blazers"],
    ("mercado_libre", "Parka"):     ["Abrigos", "Chaquetas Parkas Blazers"],
    ("mercado_libre", "Trench"):    ["Abrigos", "Chaquetas Parkas Blazers"],
    ("mercado_libre", "Bomber"):    ["Abrigos", "Chaquetas Parkas Blazers"],
    ("mercado_libre", "Chaqueta"):  ["Abrigos", "Chaquetas Parkas Blazers"],
    ("mercado_libre", "Blazer"):    ["Abrigos", "Chaquetas Parkas Blazers"],
    ("mercado_libre", "Shorts"):    ["Bermudas y Shorts"],
    ("mercado_libre", "Pantalon"):  ["Pantalones"],
    ("mercado_libre", "Jeans"):     ["Pantalones"],
    ("mercado_libre", "Camisa"):    ["Camisas"],
    ("mercado_libre", "Kimono"):    ["Kimonos"],
    ("mercado_libre", "Body"):      ["Body"],
    ("mercado_libre", "Top"):       ["Blusas", "Poleras"],
    ("mercado_libre", "Cardigan"):  ["Abrigos"],
    ("mercado_libre", "Sweater"):   ["Abrigos"],
    ("mercado_libre", "Gilet"):     ["Abrigos"],
    ("mercado_libre", "Conjunto"):  ["Blusas"],
    # ── PARIS ───────────────────────────────────────────────────────────────
    ("paris", "Sweater"):   ["Sweaters, Chalecos y Tejidos"],
    ("paris", "Cardigan"):  ["Sweaters, Chalecos y Tejidos"],
    ("paris", "Gilet"):     ["Sweaters, Chalecos y Tejidos"],
    ("paris", "Jeans"):     ["Jeans y Pantalones"],
    ("paris", "Pantalon"):  ["Jeans y Pantalones"],
    ("paris", "Blazer"):    ["Blazers, Chaquetas y Abrigos"],
    ("paris", "Chaqueta"):  ["Blazers, Chaquetas y Abrigos"],
    ("paris", "Abrigo"):    ["Blazers, Chaquetas y Abrigos"],
    ("paris", "Parka"):     ["Blazers, Chaquetas y Abrigos"],
    ("paris", "Trench"):    ["Blazers, Chaquetas y Abrigos"],
    ("paris", "Bomber"):    ["Blazers, Chaquetas y Abrigos"],
    ("paris", "Polera"):    ["Poleras y Blusas"],
    ("paris", "Blusa"):     ["Poleras y Blusas"],
    ("paris", "Top"):       ["Poleras y Blusas"],
    ("paris", "Camisa"):    ["Poleras y Blusas"],
    ("paris", "Body"):      ["Poleras y Blusas"],
    ("paris", "Vestido"):   ["Vestidos y Faldas"],
    ("paris", "Falda"):     ["Vestidos y Faldas"],
    ("paris", "Shorts"):    ["Shorts"],
    ("paris", "Calza"):     ["Poleras y Blusas"],
    ("paris", "Conjunto"):  ["Poleras y Blusas"],
    # ── FALABELLA ───────────────────────────────────────────────────────────
    # Derived from real mri_categories for Falabella (22 categories)
    ("falabella", "Abrigo"):   ["Abrigos y Chaquetas"],
    ("falabella", "Parka"):    ["Abrigos y Chaquetas"],
    ("falabella", "Trench"):   ["Abrigos y Chaquetas"],
    ("falabella", "Bomber"):   ["Abrigos y Chaquetas"],
    ("falabella", "Chaqueta"): ["Abrigos y Chaquetas"],
    ("falabella", "Blazer"):   ["Blazers"],
    ("falabella", "Sweater"):  ["Cardigans"],
    ("falabella", "Cardigan"): ["Cardigans"],
    ("falabella", "Gilet"):    ["Chaquetas Parkas Blazers"],
    ("falabella", "Pantalon"): ["Pantalones"],
    ("falabella", "Jeans"):    ["Jeans"],
    ("falabella", "Shorts"):   ["Shorts"],
    ("falabella", "Polera"):   ["Poleras"],
    ("falabella", "Blusa"):    ["Blusas"],
    ("falabella", "Top"):      ["Blusas", "Poleras"],
    ("falabella", "Camisa"):   ["Blusas"],
    ("falabella", "Body"):     ["Blusas"],
    ("falabella", "Calza"):    ["Poleras"],
    ("falabella", "Vestido"):  ["Vestido Casual"],
    ("falabella", "Falda"):    ["Vestido Casual"],
    ("falabella", "Conjunto"): ["Blusas"],
    ("falabella", "Vest"):     ["Vest"],
    # ── RIPLEY ──────────────────────────────────────────────────────────────
    # Ripley has only 3 categories in mri_categories (limited MRI coverage)
    # Vestidos, Blusas y poleras, Brand Hub
    ("ripley", "Vestido"):  ["Vestidos"],
    ("ripley", "Blusa"):    ["Blusas y poleras"],
    ("ripley", "Polera"):   ["Blusas y poleras"],
    ("ripley", "Top"):      ["Blusas y poleras"],
    ("ripley", "Camisa"):   ["Blusas y poleras"],
    ("ripley", "Body"):     ["Blusas y poleras"],
    ("ripley", "Calza"):    ["Blusas y poleras"],
    # All other Ripley types have no audited expected category → UNRESOLVED
}


def get_expected_categories(marketplace: str, canonical_product_type: Optional[str]) -> list[str]:
    """
    Return the expected commercial category names for a given marketplace
    and canonical product type.

    Returns empty list when no deterministic mapping exists.
    Legacy configured category is NEVER used as a source here.

    Parameters
    ----------
    marketplace : str
        Marketplace name as stored in the DB.
    canonical_product_type : str or None
        Result from resolve_product_type().

    Returns
    -------
    list[str]
        Expected category names (may be empty → UNRESOLVED).
    """
    if not canonical_product_type or canonical_product_type == "UNKNOWN":
        return []
    key = (_norm_mp(marketplace), canonical_product_type)
    return list(_EXPECTED_CATEGORY_MAP.get(key, []))


# ──────────────────────────────────────────────────────────────────────────────
# Core alignment function — pure, no I/O
# ──────────────────────────────────────────────────────────────────────────────

def compute_alignment(
    publication_id: str,
    marketplace: str,
    title: str,
    observed_categories: list[str],
    observed_surfaces: list[str],
    expected_category_coverage: bool,
    canonical_product_type: Optional[str] = None,
    expected_categories: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    Compute CATEGORY_ALIGNMENT for a single publication.

    Decision tree (strict precedence):
    1. If canonical_product_type is unresolvable → UNRESOLVED (UNKNOWN_PRODUCT_TYPE)
    2. If expected_categories is empty (no mapping) → UNRESOLVED (NO_EXPECTED_MAPPING)
    3. Filter observed_categories to commercial only (exclude NON_COMMERCIAL_SURFACES)
    4. If commercial_observed intersects expected_categories:
       a. If commercial_observed has >1 distinct commercial categories → ALIGNED + is_multi_category=True
       b. Else → ALIGNED
    5. If commercial_observed is non-empty but does NOT intersect expected:
       a. If expected_category_coverage=True → MISALIGNED
       b. Else → UNRESOLVED (EXPECTED_CATEGORY_NOT_AUDITED)
    6. If commercial_observed is empty (only Brand Hub / non-commercial):
       a. If expected_category_coverage=True and non-commercial surface confirms presence:
          → UNRESOLVED (ABSENT_FROM_COMMERCIAL_CATEGORY_UNRESOLVED)
       b. Else → UNRESOLVED (EXPECTED_CATEGORY_NOT_AUDITED)

    NOTE: MULTI_CATEGORY as a primary status is only set when product is found
    in multiple distinct commercial categories AND none matches expected, which
    cannot happen per this logic (step 4 already resolves as ALIGNED).
    The is_multi_category flag carries the multi-category information.

    Parameters
    ----------
    publication_id : str
    marketplace : str
    title : str
    observed_categories : list[str]
        All category names where MRI observed this publication
        (including Brand Hub, non-commercial surfaces).
    observed_surfaces : list[str]
        All surface type labels from mri_publications.surface.
    expected_category_coverage : bool
        True = MRI has audited the expected commercial category with
        sufficient coverage to assert MISALIGNED if absent.
        False = expected cat was not audited, so absence → UNRESOLVED.
    canonical_product_type : str, optional
        If pre-resolved, skip title resolution.
    expected_categories : list[str], optional
        If pre-resolved, skip mapping lookup.

    Returns
    -------
    dict with keys:
        publication_id, marketplace, title,
        canonical_product_type, expected_categories,
        observed_categories, observed_surfaces,
        commercial_observed_categories,
        alignment_status (AlignmentStatus),
        is_multi_category (bool),
        alignment_reason (str),
        expected_category_coverage (bool)
    """
    # Step 0: resolve product type if not provided
    if canonical_product_type is None:
        canonical_product_type = resolve_product_type(title)

    # Step 1: unknown product type
    if not canonical_product_type or canonical_product_type == "UNKNOWN":
        return _result(
            publication_id, marketplace, title,
            canonical_product_type or "UNKNOWN",
            expected_categories or [],
            observed_categories, observed_surfaces,
            commercial_observed=[],
            status=AlignmentStatus.UNRESOLVED,
            is_multi=False,
            reason="UNKNOWN_PRODUCT_TYPE: title does not map to any canonical type",
            coverage=expected_category_coverage,
        )

    # Step 2: resolve expected categories if not provided
    if expected_categories is None:
        expected_categories = get_expected_categories(marketplace, canonical_product_type)

    if not expected_categories:
        return _result(
            publication_id, marketplace, title,
            canonical_product_type, [],
            observed_categories, observed_surfaces,
            commercial_observed=[],
            status=AlignmentStatus.UNRESOLVED,
            is_multi=False,
            reason="NO_EXPECTED_CATEGORY_MAPPING: product type has no known expected category for this marketplace",
            coverage=expected_category_coverage,
        )

    # Step 3: filter to commercial-only observed categories
    commercial_observed = [
        c for c in observed_categories
        if c not in NON_COMMERCIAL_SURFACES
    ]

    # Step 4: intersection with expected categories (using sub-category equivalence)
    matching = [
        c for c in commercial_observed
        if any(_observed_matches_expected(c, ec) for ec in expected_categories)
    ]
    if matching:
        is_multi = len(set(commercial_observed)) > 1
        return _result(
            publication_id, marketplace, title,
            canonical_product_type, expected_categories,
            observed_categories, observed_surfaces,
            commercial_observed=commercial_observed,
            status=AlignmentStatus.ALIGNED,
            is_multi=is_multi,
            reason=f"ALIGNED: observed in expected category {matching[0]!r}",
            coverage=expected_category_coverage,
        )

    # Step 5: commercial categories observed but none match expected
    if commercial_observed:
        if expected_category_coverage:
            return _result(
                publication_id, marketplace, title,
                canonical_product_type, expected_categories,
                observed_categories, observed_surfaces,
                commercial_observed=commercial_observed,
                status=AlignmentStatus.MISALIGNED,
                is_multi=len(set(commercial_observed)) > 1,
                reason=(
                    f"MISALIGNED: observed in {commercial_observed} "
                    f"but expected category {expected_categories} was audited "
                    "and product was absent from it"
                ),
                coverage=expected_category_coverage,
            )
        else:
            return _result(
                publication_id, marketplace, title,
                canonical_product_type, expected_categories,
                observed_categories, observed_surfaces,
                commercial_observed=commercial_observed,
                status=AlignmentStatus.UNRESOLVED,
                is_multi=False,
                reason="EXPECTED_CATEGORY_NOT_AUDITED: found in other commercial categories but expected category coverage not confirmed",
                coverage=expected_category_coverage,
            )

    # Step 6: only non-commercial surfaces observed
    return _result(
        publication_id, marketplace, title,
        canonical_product_type, expected_categories,
        observed_categories, observed_surfaces,
        commercial_observed=[],
        status=AlignmentStatus.UNRESOLVED,
        is_multi=False,
        reason="EXPECTED_CATEGORY_NOT_AUDITED: product only observed on non-commercial surfaces (e.g. Brand Hub)",
        coverage=expected_category_coverage,
    )


def _result(
    publication_id: str,
    marketplace: str,
    title: str,
    canonical_product_type: str,
    expected_categories: list[str],
    observed_categories: list[str],
    observed_surfaces: list[str],
    commercial_observed: list[str],
    status: AlignmentStatus,
    is_multi: bool,
    reason: str,
    coverage: bool,
) -> Dict[str, Any]:
    return {
        "publication_id": publication_id,
        "marketplace": marketplace,
        "title": title,
        "canonical_product_type": canonical_product_type,
        "expected_categories": expected_categories,
        "observed_categories": observed_categories,
        "observed_surfaces": observed_surfaces,
        "commercial_observed_categories": commercial_observed,
        "alignment_status": status,
        "is_multi_category": is_multi,
        "alignment_reason": reason,
        "expected_category_coverage": coverage,
    }


# ──────────────────────────────────────────────────────────────────────────────
# DB integration — operational layer (read-only)
# ──────────────────────────────────────────────────────────────────────────────

# Commercial categories from mri_categories that have confirmed MRI coverage
# (i.e., they were actively observed in at least one audit run).
# Used to determine expected_category_coverage for each publication.
_COVERAGE_MARKER = "OBSERVED"


def _get_audited_categories(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    """
    Returns set of (marketplace, category_name) tuples for categories that
    have confirmed observations in mri_publication_categories.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT c.marketplace, c.category_name
        FROM mri_publication_categories pc
        JOIN mri_categories c ON pc.category_id = c.category_id
        WHERE pc.status = 'OBSERVED'
          AND c.category_name NOT IN ('Brand Hub', 'Brand Store', 'Brand Navigation')
    """)
    return {(r[0], r[1]) for r in cur.fetchall()}


def run_alignment_on_db(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute category alignment over all MRI-materialized publications.

    Read-only. Does not write to any table.
    Uses mri_publications + mri_variants + mri_publication_categories + mri_categories.

    Returns
    -------
    dict with:
        total_publications, results (list of alignment dicts),
        summary (by marketplace and by status)
    """
    if db_path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.path.join(base_dir, "data", "sqlite", "visibility.db")

    try:
        uri = f"file:{os.path.abspath(db_path)}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    except Exception:
        conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    audited_categories = _get_audited_categories(conn)

    cur = conn.cursor()
    cur.execute("""
        SELECT p.publication_id, p.marketplace, p.surface,
               v.variant_title,
               GROUP_CONCAT(DISTINCT c.category_name) as observed_categories_raw
        FROM mri_publications p
        LEFT JOIN mri_variants v ON p.publication_id = v.publication_id
        LEFT JOIN mri_publication_categories pc ON p.publication_id = pc.publication_id
        LEFT JOIN mri_categories c ON pc.category_id = c.category_id
        GROUP BY p.publication_id
        ORDER BY p.marketplace, p.publication_id
    """)
    rows = cur.fetchall()
    conn.close()

    results = []
    for row in rows:
        pub_id = row["publication_id"]
        marketplace = row["marketplace"]
        surface = row["surface"] or ""
        title = row["variant_title"] or ""
        obs_cats_raw = row["observed_categories_raw"] or ""

        observed_categories = [c.strip() for c in obs_cats_raw.split(",") if c.strip()]
        # Surface from mri_publications is the primary surface
        observed_surfaces = [surface] if surface else []

        canonical_type = resolve_product_type(title)
        expected_cats = get_expected_categories(marketplace, canonical_type)

        # Determine coverage: is any expected category actually audited in this MP?
        coverage = False
        for ec in expected_cats:
            if (marketplace, ec) in audited_categories:
                coverage = True
                break

        alignment = compute_alignment(
            publication_id=pub_id,
            marketplace=marketplace,
            title=title,
            observed_categories=observed_categories,
            observed_surfaces=observed_surfaces,
            expected_category_coverage=coverage,
            canonical_product_type=canonical_type,
            expected_categories=expected_cats,
        )
        results.append(alignment)

    # Build summary
    by_mp: dict[str, dict[str, int]] = {}
    for r in results:
        mp = r["marketplace"]
        st = r["alignment_status"].value if isinstance(r["alignment_status"], AlignmentStatus) else str(r["alignment_status"])
        if mp not in by_mp:
            by_mp[mp] = {"total": 0, "ALIGNED": 0, "MISALIGNED": 0, "MULTI_CATEGORY": 0, "UNRESOLVED": 0}
        by_mp[mp]["total"] += 1
        by_mp[mp][st] = by_mp[mp].get(st, 0) + 1

    total_by_status: dict[str, int] = {"ALIGNED": 0, "MISALIGNED": 0, "MULTI_CATEGORY": 0, "UNRESOLVED": 0}
    for mp_data in by_mp.values():
        for st in total_by_status:
            total_by_status[st] += mp_data.get(st, 0)

    return {
        "total_publications": len(results),
        "by_marketplace": by_mp,
        "totals": total_by_status,
        "results": results,
    }
