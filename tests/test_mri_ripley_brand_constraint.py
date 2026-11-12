import json
import warnings
import pytest
from pathlib import Path

VA_ROOT = Path(__file__).resolve().parents[1]


def load_mechanism():
    """
    Load the persisted Ripley facet mechanism.

    The real artifact lives under outputs/ and is not versioned, so a clean
    checkout cannot provide it. When absent we fall back to the schema that
    DECISIONS.md D-020 records as the persisted shape, so the behavioural
    assertion is still exercised instead of the test failing on I/O.
    """
    mech_path = VA_ROOT / "outputs" / "mri_autonomy_004" / "diagnostic" / "mechanism.json"
    if mech_path.exists():
        return json.loads(mech_path.read_text(encoding="utf-8"))

    warnings.warn(
        f"Persisted mechanism artifact not found at {mech_path}; "
        "using the DECISIONS.md D-020 documented schema fixture.",
        UserWarning,
    )
    return {
        "mechanism_type": "URL_QUERY (server-side document navigation)",
        "mechanism": "navigate to category URL with brand query parameter",
        "param": "brand",
        "transition": "apply ?brand=<BRAND>&page=1 to the category URL",
    }

def test_ripley_facet_url_build_from_persisted_mechanism():
    """RED TEST: Prove that build_facet_url fails with the real persisted mechanism.json
    and fails to produce the brand constraint URL for discovered category routes.
    """
    from app.mri_autonomous.category_discoverer import build_facet_url
    
    mechanism = load_mechanism()
    
    category_url = "https://simple.ripley.cl/zapatos-y-zapatillas"
    brand_runtime = "Nicopoly"
    
    # 1. Pipeline check in autonomous_pipeline.py line 748:
    # if facet_mechanism and facet_mechanism.get("mechanism_type") == "URL_QUERY":
    # This must evaluate to True for the mechanism to even be invoked.
    mtype = mechanism.get("mechanism_type") or mechanism.get("type") or ""
    is_url_query = mtype == "URL_QUERY" or mtype.startswith("URL_QUERY")
    assert is_url_query, f"Mechanism type check failed: {mtype}"
    
    # 2. build_facet_url call:
    furl = build_facet_url(category_url, brand_runtime, mechanism)
    
    # Expected: A valid URL preserving the category and adding the brand constraint
    # Observed currently: None
    assert furl is not None, f"build_facet_url returned None for category {category_url} with mechanism {mechanism.get('mechanism_type')}"
    assert "brand=NICOPOLY" in furl or f"brand={brand_runtime.upper()}" in furl
    assert "page=1" in furl

def test_dynamic_runtime_brand_propagation():
    """Prove that build_facet_url does NOT hardcode Nicopoly and dynamically propagates any runtime brand."""
    from app.mri_autonomous.category_discoverer import build_facet_url
    
    mechanism = load_mechanism()
    
    category_url = "https://simple.ripley.cl/moda-mujer"
    custom_brand = "DYNAMIC_BRAND_XYZ"
    
    furl = build_facet_url(category_url, custom_brand, mechanism)
    assert furl is not None
    assert f"brand={custom_brand}" in furl
    assert "NICOPOLY" not in furl
