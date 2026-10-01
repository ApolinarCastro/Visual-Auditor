"""
RED TESTS for VA-PRODUCT-TAXONOMY-CAPABILITY-001
Demonstrates the gap that category_alignment module must fill.

These tests MUST FAIL before implementation and PASS after.
"""

import pytest


# ---------------------------------------------------------------------------
# Attempt to import the (not-yet-existing) module — must fail as ImportError
# ---------------------------------------------------------------------------
def _import_module():
    from app.mri_autonomous.category_alignment import (
        resolve_product_type,
        get_expected_categories,
        compute_alignment,
        AlignmentStatus,
    )
    return resolve_product_type, get_expected_categories, compute_alignment, AlignmentStatus


# ---------------------------------------------------------------------------
# RED-1: Brand Hub does not imply correct categorization
# ---------------------------------------------------------------------------
def test_red_brand_hub_not_implies_correct_category():
    """
    BRAND HUB != CORRECT COMMERCIAL CATEGORY.
    A product only observed in Brand Hub must yield UNRESOLVED,
    NOT ALIGNED, when we cannot confirm its expected category was audited.
    """
    resolve_product_type, get_expected_categories, compute_alignment, AlignmentStatus = _import_module()

    result = compute_alignment(
        publication_id="pub_test_001",
        marketplace="Ripley",
        title="Chaqueta Biker Negro Mujer Nicopoly",
        observed_categories=["Brand Hub"],
        observed_surfaces=["Brand Hub"],
        expected_category_coverage=False,  # expected cat was NOT audited with coverage
    )
    assert result["alignment_status"] == AlignmentStatus.UNRESOLVED, (
        f"Brand Hub-only + no coverage => UNRESOLVED but got {result['alignment_status']}"
    )


# ---------------------------------------------------------------------------
# RED-2: Legacy configured category is NOT automatically the expected category
# ---------------------------------------------------------------------------
def test_red_legacy_category_not_auto_truth():
    """
    LEGACY_CONFIGURED_CATEGORY != EXPECTED_CATEGORY by definition.
    The alignment engine must not treat a legacy label as a confirmed
    expected category without a valid mapping rule.
    """
    _, get_expected_categories, _, _ = _import_module()

    # An unknown/unmapped marketplace should return empty expected categories
    result = get_expected_categories(
        marketplace="UNKNOWN_MARKETPLACE",
        canonical_product_type="Blazer",
    )
    assert result == [], (
        f"Unknown marketplace should return empty expected cats but got {result}"
    )


# ---------------------------------------------------------------------------
# RED-3: Expected category + observed expected category => ALIGNED
# ---------------------------------------------------------------------------
def test_red_observed_in_expected_category_is_aligned():
    """
    If EXPECTED_CATEGORY is deterministically resolved AND the publication
    appears in that category => ALIGNED.
    """
    resolve_product_type, get_expected_categories, compute_alignment, AlignmentStatus = _import_module()

    result = compute_alignment(
        publication_id="pub_test_003",
        marketplace="Mercado Libre",
        title="Vestido Largo Halter Encaje Burdeo Nicopoly",
        observed_categories=["Vestidos"],
        observed_surfaces=["Category Browse"],
        expected_category_coverage=True,
    )
    assert result["alignment_status"] == AlignmentStatus.ALIGNED, (
        f"Vestido in Vestidos should be ALIGNED but got {result['alignment_status']}"
    )


# ---------------------------------------------------------------------------
# RED-4: Multi-category with expected category preserves ALIGNED
# ---------------------------------------------------------------------------
def test_red_multi_category_includes_expected_is_aligned():
    """
    If observed_categories includes the expected category, alignment is
    ALIGNED even when additional categories are also observed.
    The multi-category nature is preserved as an additional attribute,
    but the primary status remains ALIGNED.
    """
    resolve_product_type, get_expected_categories, compute_alignment, AlignmentStatus = _import_module()

    result = compute_alignment(
        publication_id="pub_test_004",
        marketplace="Paris",
        title="Pantalon Recto Con Pinza Mocca Nicopoly",
        observed_categories=["Jeans y Pantalones", "Pantalones", "Brand Hub"],
        observed_surfaces=["Brand Hub", "Category Browse"],
        expected_category_coverage=True,
    )
    # Must be ALIGNED because expected "Jeans y Pantalones" is in observed
    assert result["alignment_status"] == AlignmentStatus.ALIGNED, (
        f"Multi-cat including expected => ALIGNED but got {result['alignment_status']}"
    )
    # Must also note multi-category
    assert result.get("is_multi_category") is True, (
        "Must flag is_multi_category=True when observed > 1 commercial categories"
    )


# ---------------------------------------------------------------------------
# RED-5: Expected category not audited with coverage => UNRESOLVED, not MISALIGNED
# ---------------------------------------------------------------------------
def test_red_expected_not_audited_is_unresolved_not_misaligned():
    """
    NOT_OBSERVED_IN_EXPECTED_CATEGORY != PROVEN_MISALIGNED.
    Without coverage evidence that we scanned the expected category,
    we CANNOT declare MISALIGNED.
    """
    resolve_product_type, get_expected_categories, compute_alignment, AlignmentStatus = _import_module()

    result = compute_alignment(
        publication_id="pub_test_005",
        marketplace="Ripley",
        title="Blazer Basico Sastrero Negro Mujer",
        observed_categories=["Brand Hub"],
        observed_surfaces=["Brand Hub"],
        expected_category_coverage=False,  # We did NOT scan the expected cat
    )
    assert result["alignment_status"] != AlignmentStatus.MISALIGNED, (
        "Without coverage of expected category, result must not be MISALIGNED"
    )
    assert result["alignment_status"] == AlignmentStatus.UNRESOLVED, (
        f"Should be UNRESOLVED when coverage missing, got {result['alignment_status']}"
    )


# ---------------------------------------------------------------------------
# RED-6: Expected known + coverage + absent + present in other => MISALIGNED
# ---------------------------------------------------------------------------
def test_red_coverage_plus_absent_in_expected_is_misaligned():
    """
    MISALIGNED requires:
      A. Expected category determined
      B. Expected category was audited with sufficient coverage
      C. Publication confirmed existing
      D. Product NOT found in expected category
      E. Product found in ANOTHER category or surface
    """
    resolve_product_type, get_expected_categories, compute_alignment, AlignmentStatus = _import_module()

    result = compute_alignment(
        publication_id="pub_ripley_72df33d13e81",
        marketplace="Ripley",
        title="Blusa Saten Cruzado Rojo Nicopoly",
        observed_categories=["Vestidos"],         # observed in WRONG category
        observed_surfaces=["Category Browse"],
        expected_category_coverage=True,           # expected cat WAS audited
    )
    # Blusa expected in Blusas/tops but found in Vestidos => MISALIGNED
    assert result["alignment_status"] == AlignmentStatus.MISALIGNED, (
        f"Blusa in Vestidos with coverage => MISALIGNED but got {result['alignment_status']}"
    )


# ---------------------------------------------------------------------------
# RED-7: Unknown product type => UNRESOLVED
# ---------------------------------------------------------------------------
def test_red_unknown_product_type_is_unresolved():
    """
    A product whose type cannot be determined deterministically must yield
    UNRESOLVED, never ALIGNED or MISALIGNED.
    """
    resolve_product_type, get_expected_categories, compute_alignment, AlignmentStatus = _import_module()

    ptype = resolve_product_type("ZXQY-RANDOM-ITEM-NO-MATCH-9999 Nicopoly")
    assert ptype is None or ptype == "UNKNOWN", (
        f"Unrecognized title should yield None/UNKNOWN but got {ptype!r}"
    )

    result = compute_alignment(
        publication_id="pub_test_007",
        marketplace="Mercado Libre",
        title="ZXQY-RANDOM-ITEM-NO-MATCH-9999 Nicopoly",
        observed_categories=["Some Category"],
        observed_surfaces=["Category Browse"],
        expected_category_coverage=True,
    )
    assert result["alignment_status"] == AlignmentStatus.UNRESOLVED, (
        f"Unknown product type => UNRESOLVED but got {result['alignment_status']}"
    )


# ---------------------------------------------------------------------------
# RED-8: No Nicopoly/Ripley hardcode in core alignment logic
# ---------------------------------------------------------------------------
def test_red_no_hardcode_brand_or_marketplace():
    """
    The alignment engine must NOT contain hardcoded brand/marketplace
    conditionals as special cases in the alignment decision logic.
    """
    import inspect
    from app.mri_autonomous import category_alignment as mod

    source = inspect.getsource(mod)

    # Forbidden: brand-specific or publication-specific branching in alignment
    forbidden_patterns = [
        'if marketplace == "Ripley"',
        "if marketplace == 'Ripley'",
        'if brand == "Nicopoly"',
        "if brand == 'Nicopoly'",
        'pub_ripley_72df33d13e81',
        'N00001RP',
    ]
    for pat in forbidden_patterns:
        assert pat not in source, (
            f"Hardcoded pattern found in category_alignment.py: {pat!r}"
        )
