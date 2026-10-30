"""Coverage contract: master expected vs observed, stock rule, no false claims."""
from app.mri_dashboard.publication_coverage import build_report


def _master(sku, name, stock, falabella_price, ripley_price=0):
    return {"sku_master": sku, "sku_hijo": sku, "sku_padre": "",
            "product_name": name, "brand": "Nicopoly",
            "prices": {"falabella": falabella_price, "ripley": ripley_price,
                       "mercado libre": 0, "paris": 0},
            "stock": stock}


def _obs(title, oid="X1"):
    return {"producto_id": oid, "producto_nombre": title,
            "canonical_url": "https://www.falabella.com/falabella-cl/product/1/x",
            "real_category": "Poleras Mujer"}


def test_published_and_missing():
    master = [
        _master("N05155BL", "Polera Básica Cuello Redondo Negro", 10, 19990),
        _master("N06207BM", "Blazer Dos Botones Burdeo", 5, 39990),
        _master("N09999XX", "Parka Acolchada Negra", 0, 49990),      # stock 0
        _master("N08888YY", "Short Básico Negro", 5, 0),            # no Falabella price
        _master("N07777ZZ", "Falda Midi Satinada", -1, 29990),      # stock unknown
    ]
    obs = [
        _obs("Polera Básica Cuello Redondo Negro Nicopoly", "1001"),
        _obs("Blazer Dos Botones Burdeo Nicopoly", "1002"),
    ]
    r = build_report("Falabella", obs, master)
    assert r["master"]["expected_child_skus"] == 2
    assert r["master"]["discarded_no_stock"] == 1
    assert r["master"]["unverified_stock"] == 1
    assert r["master"]["not_expected_channel"] == 1
    assert r["coverage"]["published_verified"] == 2
    assert r["coverage"]["missing"] == 0


def test_missing_is_reported_only_when_run_complete():
    master = [
        _master("N05155BL", "Polera Básica Cuello Redondo Negro", 10, 19990),
        _master("N06207BM", "Blazer Dos Botones Burdeo", 5, 39990),
    ]
    obs = [_obs("Polera Básica Cuello Redondo Negro Nicopoly", "1001")]
    complete = build_report("Falabella", obs, master)
    assert complete["coverage"]["missing"] == 1
    assert complete["missing"][0]["sku_parent"] == "N06207BM"
    partial = build_report("Falabella", obs, master, run_complete=False)
    assert partial["coverage"]["missing"] == 0
    assert partial["coverage"]["unverified"] == 2


def test_stock_zero_never_counts_as_missing():
    master = [_master("N09999XX", "Parka Acolchada Negra", 0, 49990)]
    r = build_report("Falabella", [], master)
    assert r["master"]["expected_child_skus"] == 0
    assert r["coverage"]["missing"] == 0
    assert r["master"]["discarded_no_stock"] == 1


def test_coverage_uses_checklist_channel_id():
    master = [{"sku_master": "156819797", "sku_padre": "N03049A",
               "sku_hijo": "N03049AL",
               "product_name": "Blazer Manga 3/4 Ajustado con Solapas Blanco Nicopoly",
               "stock": 10,
               "prices": {"falabella": 53990, "ripley": 0,
                          "mercado libre": 0, "paris": 0}}]
    checklist = {"products": [{
        "sku_padre": "N03049A", "sku_hijo": "N03049AL",
        "name": "Blazer Manga 3/4 Ajustado con Solapas Blanco Nicopoly",
        "channels": {"falabella": {
            "product_id": "156819797",
            "link": "https://www.falabella.com/falabella-cl/product/156819795/Blazer"}}}]}
    obs = [{"producto_id": "156819795",
            "producto_nombre": "Titulo distinto sin coincidencia",
            "canonical_url": "https://www.falabella.com/falabella-cl/product/156819795/Blazer"}]
    r = build_report("Falabella", obs, master, checklist=checklist)
    assert r["coverage"]["published_verified"] == 1
    assert r["coverage"]["missing"] == 0
    assert r["published"][0]["method"] == "CHECKLIST_ID"
