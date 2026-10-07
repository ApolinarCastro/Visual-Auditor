import json
import pytest
from pathlib import Path

VA_ROOT = Path(__file__).resolve().parents[1]

def test_ripley_facet_url_build_from_persisted_mechanism():
    """RED TEST: Prove that build_facet_url fails with the real persisted mechanism.json
    and fails to produce the brand constraint URL for discovered category routes.
    """
    from app.mri_autonomous.category_discoverer import build_facet_url
    
    mech_path = VA_ROOT / "outputs" / "mri_autonomy_004" / "diagnostic" / "mechanism.json"
    assert mech_path.exists(), "outputs/mri_autonomy_004/diagnostic/mechanism.json must exist"
    mechanism = json.loads(mech_path.read_text(encoding="utf-8"))
    
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
    
    mech_path = VA_ROOT / "outputs" / "mri_autonomy_004" / "diagnostic" / "mechanism.json"
    mechanism = json.loads(mech_path.read_text(encoding="utf-8"))
    
    category_url = "https://simple.ripley.cl/moda-mujer"
    custom_brand = "DYNAMIC_BRAND_XYZ"
    
    furl = build_facet_url(category_url, custom_brand, mechanism)
    assert furl is not None
    assert f"brand={custom_brand}" in furl
    assert "NICOPOLY" not in furl
