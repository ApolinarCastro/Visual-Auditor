"""Master catalog upload policy: stock 0 = immediate discard candidate."""
from app.loaders.multivende_loader import MultivendeLoader


def _item(sku, stock, price, name="Prenda"):
    return {"sku_master": sku, "sku_hijo": sku, "sku_padre": "",
            "product_name": name, "brand": "Nicopoly",
            "prices": {"falabella": price, "ripley": 0,
                       "mercado libre": 0, "paris": 0},
            "stock": stock}


def test_channel_stock_policy():
    loader = MultivendeLoader("nonexistent.xlsx")
    loader._loaded = True
    loader._master_items = [
        _item("N1", 0, 1000),    # sin stock -> descartado
        _item("N2", 5, 1000),    # esperado
        _item("N3", 3, 0),       # sin precio de canal -> no esperado
        _item("N4", -1, 1000),   # stock desconocido
    ]
    r = loader.expected_for_channel("falabella")
    assert r["expected"] == 1
    assert r["discarded_no_stock"] == 1
    assert r["unverified_stock"] == 1
    assert r["not_expected"] == 1
    assert r["discarded_items"][0]["sku_master"] == "N1"
