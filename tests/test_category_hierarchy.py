"""Abrigos rollup: children are commercial subcategories."""
from app.mri_dashboard.category_hierarchy import parent_for, rollup


def test_abrigos_children_roll_up_to_parent():
    cats = {
        "a": {"name": "Chaquetas, Parkas y Blazers", "publications": 168},
        "b": {"name": "Chalecos, Sweaters y Cardigans", "publications": 42},
        "c": {"name": "Poleras", "publications": 115},
    }
    out = rollup(cats)
    names = {v["name"]: v for v in out.values()}
    assert "Abrigos" in names
    assert names["Abrigos"]["publications"] == 210
    assert "Chaquetas, Parkas y Blazers" not in names
    assert "Poleras" in names


def test_hierarchy_is_case_insensitive():
    assert parent_for("CHALECOS, SWEATERS Y CARDIGANS") == "Abrigos"
