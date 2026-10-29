"""ML declared total and snapshot/diff helpers."""
from app.mri_dashboard.meli_snapshot import parse_declared_total, snapshot, diff


def test_reads_declared_total():
    assert parse_declared_total("Vestuario y Calzado 658 resultados") == 658
    assert parse_declared_total("Mostrando 1 - 48 de 1.234") == 1234
    assert parse_declared_total("1 resultado") == 1
    assert parse_declared_total("sin coincidencias") is None


def test_snapshot_diff_is_deterministic():
    prev = snapshot([{"marketplace_sku": "MLC1", "price": 10, "status": "OK"}])
    curr = snapshot([{"marketplace_sku": "MLC1", "price": 20, "status": "OK"},
                     {"marketplace_sku": "MLC2", "price": 5, "status": "OK"}])
    changes = diff(prev, curr)
    assert any(c["change"] == "PRICE_CHANGE" and c["item_id"] == "MLC1" for c in changes)
    assert any(c["change"] == "NEW_LISTING" and c["item_id"] == "MLC2" for c in changes)
