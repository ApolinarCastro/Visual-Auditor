"""Proposal 1: formal Mercado Libre negative-path knowledge object."""
import json
from pathlib import Path


def test_ml_experience_object_is_formal_and_safe():
    path = Path("knowledge/MRI-EXP-ML-ACQUISITION-001.json")
    obj = json.loads(path.read_text(encoding="utf-8"))
    assert obj["marketplace"] == "Mercado Libre"
    assert obj["production_code_changes"] == 0
    assert obj["new_dependencies"] == 0
    assert obj["contains_credentials"] is False
    paths = {p["path"] for p in obj["known_negative_paths"]}
    assert any("sites/MLC/search" in p for p in paths)
    assert any("_Tienda_" in p for p in paths)
    assert any("_Desde_" in p and "query" in p.lower() for p in paths)
    text = path.read_text(encoding="utf-8").lower()
    assert "ssid" not in text
    assert '"value":' not in text
