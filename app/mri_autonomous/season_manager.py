"""MRI Commercial Intelligence v1 — season registry, products, observations, alerts.

This module never touches the acquisition engines. It only reads mri_publications
and writes the season_* tables in the operational SQLite database.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_SEASON = "GRUPOS_2026 SS"
DEFAULT_YEAR = 2026


def _db_path(db_path: Optional[str] = None) -> str:
    if db_path:
        return str(db_path)
    root = Path(__file__).resolve().parents[3]
    return str(root / "data" / "sqlite" / "mri_operational" / "visibility.db")


SCHEMA = """
CREATE TABLE IF NOT EXISTS season_registry (
    season_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    year INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    UNIQUE(name, year)
);
CREATE TABLE IF NOT EXISTS season_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    sku_padre TEXT NOT NULL,
    sku_hijo TEXT,
    nombre TEXT,
    precio_venta REAL,
    mpm_ripley TEXT,
    mlc_meli TEXT,
    mkp_paris TEXT,
    falabella_id TEXT,
    group_id TEXT,
    ultima_actualizacion TEXT,
    FOREIGN KEY(season_id) REFERENCES season_registry(season_id),
    UNIQUE(season_id, sku_padre)
);
CREATE TABLE IF NOT EXISTS season_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_product_id INTEGER NOT NULL,
    marketplace TEXT NOT NULL,
    audit_run_id TEXT,
    estado TEXT NOT NULL,
    precio_observado REAL,
    precio_oferta REAL,
    stock_status TEXT,
    posicion_observada INTEGER,
    top_level TEXT,
    url_evidencia TEXT,
    fecha_observacion TEXT NOT NULL,
    FOREIGN KEY(season_product_id) REFERENCES season_products(id)
);
CREATE TABLE IF NOT EXISTS season_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_product_id INTEGER NOT NULL,
    marketplace TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(season_product_id) REFERENCES season_products(id)
);
CREATE INDEX IF NOT EXISTS idx_season_obs_product ON season_observations(season_product_id, marketplace, id);
CREATE INDEX IF NOT EXISTS idx_season_alert_product ON season_alerts(season_product_id, marketplace, id);
"""


def init_season_schema(db_path: Optional[str] = None) -> Dict[str, Any]:
    conn = sqlite3.connect(_db_path(db_path), timeout=30)
    try:
        conn.executescript(SCHEMA)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(season_products)")]
        if "group_id" not in cols:
            conn.execute("ALTER TABLE season_products ADD COLUMN group_id TEXT")
        conn.commit()
        tables = {}
        for table in ("season_registry", "season_products", "season_observations", "season_alerts"):
            tables[table] = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        return {"ok": True, "tables": tables}
    finally:
        conn.close()


def _norm(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")


COLUMN_ALIASES = {
    "sku_padre": ("sku_padre", "sku padre", "skupadre", "padre", "sku_mpm", "mpm_padre"),
    "sku_hijo": ("sku_hijo", "sku hijo", "skuhijo", "hijo", "sku"),
    "nombre": ("nombre", "name", "producto", "descripcion", "product_title", "nombre_producto"),
    "precio_venta": ("precio_venta", "precio venta", "precio", "price", "precio_multivende", "precio_venta_clp"),
    "mpm_ripley": ("mpm_ripley", "mpm ripley", "mpm", "ripley_id", "ripley"),
    "mlc_meli": ("mlc_meli", "mlc meli", "mlc", "meli_id", "mercadolibre_id", "mlc_id"),
    "mkp_paris": ("mkp_paris", "mkp paris", "mkp", "paris_id", "paris"),
    "falabella_id": ("falabella_id", "falabella id", "falabella", "falabella_sku", "falabella_link"),
}


def _map_columns(df) -> Dict[str, str]:
    found = {}
    normed = {_norm(c): c for c in df.columns}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = _norm(alias)
            if key in normed:
                found[field] = normed[key]
                break
    return found


def ensure_season(name: Optional[str] = None, year: Optional[int] = None,
                  db_path: Optional[str] = None) -> int:
    init_season_schema(db_path)
    name = name or DEFAULT_SEASON
    year = int(year or DEFAULT_YEAR)
    conn = sqlite3.connect(_db_path(db_path), timeout=30)
    try:
        conn.execute("INSERT OR IGNORE INTO season_registry(name, year, status) VALUES (?,?,?)",
                     (name, year, "ACTIVE"))
        row = conn.execute("SELECT season_id FROM season_registry WHERE name=? AND year=?",
                           (name, year)).fetchone()
        conn.commit()
        return int(row[0])
    finally:
        conn.close()


def _read_sheet_with_header(path, sheet=None):
    """Read one sheet, locating the real header row (CHECKLIST has title rows)."""
    import pandas as pd
    probe = pd.read_excel(path, sheet_name=sheet, header=None, nrows=12)
    header_row = None
    for i in range(min(12, len(probe))):
        vals = [_norm(v) for v in probe.iloc[i].tolist()]
        if "sku_padre" in vals:
            header_row = i
            break
    if header_row is None:
        return None
    return pd.read_excel(path, sheet_name=sheet, header=header_row)


def ingest_season_file(path: str, season_name: Optional[str] = None,
                       year: Optional[int] = None, db_path: Optional[str] = None,
                       season_id: Optional[str] = None) -> Dict[str, Any]:
    """Ingest CHECKLIST .xlsx with multiple sheets (GRUPO 1..6) or a CSV.

    For each sheet, the real header row is detected by finding SKU_PADRE.
    Rows are upserted by (season_id, sku_padre); group_id stores the sheet.
    """
    import pandas as pd
    p = Path(path)
    season_name = season_id or season_name or p.stem
    if p.suffix.lower() in (".csv", ".txt"):
        frames = [(p.stem, _read_sheet_with_header(p, None))]
    else:
        xls = pd.ExcelFile(p)
        frames = []
        for sheet in xls.sheet_names:
            df = _read_sheet_with_header(p, sheet)
            if df is not None:
                frames.append((sheet, df))
    season_id_int = ensure_season(season_name, year, db_path)
    conn = sqlite3.connect(_db_path(db_path), timeout=60)
    inserted = updated = ignored = 0
    groups: Dict[str, Dict[str, int]] = {}
    now = datetime.now().isoformat()
    try:
        for sheet, df in frames:
            mapping = _map_columns(df)
            stats = {"rows": int(len(df)), "inserted": 0, "updated": 0, "ignored": 0}
            if "sku_padre" not in mapping:
                stats["ignored"] = int(len(df))
                stats["error"] = "SKU_PADRE_NOT_FOUND"
                groups[sheet] = stats
                ignored += stats["ignored"]
                continue
            for _, row in df.iterrows():
                def val(field):
                    col = mapping.get(field)
                    if not col:
                        return None
                    v = row.get(col)
                    if pd.isna(v):
                        return None
                    return v
                sku_padre = str(val("sku_padre") or "").strip()
                if not sku_padre:
                    stats["ignored"] += 1
                    ignored += 1
                    continue
                fields = {
                    "sku_hijo": val("sku_hijo"), "nombre": val("nombre"),
                    "precio_venta": val("precio_venta"), "mpm_ripley": val("mpm_ripley"),
                    "mlc_meli": val("mlc_meli"), "mkp_paris": val("mkp_paris"),
                    "falabella_id": val("falabella_id"),
                }
                existing = conn.execute(
                    "SELECT id FROM season_products WHERE season_id=? AND sku_padre=?",
                    (season_id_int, sku_padre)).fetchone()
                if existing:
                    conn.execute("""UPDATE season_products SET sku_hijo=?, nombre=?,
                        precio_venta=?, mpm_ripley=?, mlc_meli=?, mkp_paris=?,
                        falabella_id=?, group_id=?, ultima_actualizacion=? WHERE id=?""",
                        (fields["sku_hijo"], fields["nombre"], fields["precio_venta"],
                         fields["mpm_ripley"], fields["mlc_meli"], fields["mkp_paris"],
                         fields["falabella_id"], sheet, now, existing[0]))
                    stats["updated"] += 1
                    updated += 1
                else:
                    conn.execute("""INSERT INTO season_products
                        (season_id, sku_padre, sku_hijo, nombre, precio_venta,
                         mpm_ripley, mlc_meli, mkp_paris, falabella_id, group_id,
                         ultima_actualizacion)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (season_id_int, sku_padre, fields["sku_hijo"], fields["nombre"],
                         fields["precio_venta"], fields["mpm_ripley"], fields["mlc_meli"],
                         fields["mkp_paris"], fields["falabella_id"], sheet, now))
                    stats["inserted"] += 1
                    inserted += 1
            groups[sheet] = stats
        conn.commit()
        return {"ok": True, "season_id": season_id_int, "season_name": season_name,
                "inserted": inserted, "updated": updated, "ignored": ignored,
                "groups": groups, "sheets": len(frames)}
    finally:
        conn.close()


def _safe_float(v):
    try:
        return float(str(v).replace("$", "").replace(".", "").replace(",", "."))
    except Exception:
        return None


def _top_level(position):
    if not position:
        return None
    p = int(position)
    for n in (30, 60, 90, 120, 240):
        if p <= n:
            return f"TOP{n}"
    return "OUTSIDE_TOP240"


def _pub_price(row):
    try:
        attrs = json.loads(row.get("commercial_attributes") or "{}")
        containers = [attrs, attrs.get("observed_attributes") or {},
                      attrs.get("commercial_attributes") or {}]
        for cont in containers:
            for key in ("price", "precio", "offer_price", "precio_oferta",
                        "price_displayed", "price_regular"):
                if cont.get(key) is not None:
                    return _safe_float(cont.get(key))
    except Exception:
        pass
    return None


def _pub_stock(row):
    try:
        attrs = json.loads(row.get("commercial_attributes") or "{}")
        observed = attrs.get("observed_attributes") or {}
        raw = str(attrs.get("stock_status") or observed.get("stock_status")
                  or attrs.get("stock") or observed.get("stock") or "").upper()
        if not raw:
            avail = attrs.get("availability") or observed.get("availability")
            if avail:
                raw = str(avail).upper()
        if raw in ("IN_STOCK", "OUT_OF_STOCK"):
            return raw
        for cont in (attrs, observed):
            if cont.get("in_stock") is True:
                return "IN_STOCK"
            if cont.get("in_stock") is False:
                return "OUT_OF_STOCK"
    except Exception:
        pass
    return "UNKNOWN"


def _insert_alert(conn, product_id, marketplace, alert_type, severity, details):
    conn.execute("""INSERT INTO season_alerts
        (season_product_id, marketplace, alert_type, severity, details, created_at, is_read)
        VALUES (?,?,?,?,?,?,0)""",
        (product_id, marketplace, alert_type, severity,
         json.dumps(details, ensure_ascii=False), datetime.now().isoformat()))


def _id_candidates(target: str) -> list[str]:
    """Marketplace IDs appear with/without MPM/FALA_/MLC-/MKP prefixes."""
    raw = str(target or "").strip()
    vals = {raw}
    for prefix in ("MPM", "FALA_", "FALA", "MLC-", "MLC", "MKP", "PARIS-"):
        if raw.upper().startswith(prefix):
            vals.add(raw[len(prefix):].lstrip("-_"))
    digits = re.sub(r"[^0-9]", "", raw)
    if digits:
        vals.add(digits)
    clean = re.sub(r"[^A-Za-z0-9]", "", raw)
    if clean:
        vals.add(clean)
    return [v for v in vals if v]


def _ids_match(expected: str, observed: str) -> bool:
    """Compare marketplace IDs tolerantly: FALA_/MLC-/MPM prefix variants are the same ID."""
    def norm(v):
        return re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()
    a, b = norm(expected), norm(observed)
    for prefix in ("MPM", "FALA", "MLC", "MKP"):
        if a.startswith(prefix):
            a = a[len(prefix):]
        if b.startswith(prefix):
            b = b[len(prefix):]
    if a == b:
        return True
    # Falabella numeric IDs may arrive as FALA_<id>.
    if a.isdigit() and b.endswith(a):
        return True
    if b.isdigit() and a.endswith(b):
        return True
    # ML/Paris IDs may differ only by separators/known prefixes.
    if a.lstrip("FALA") == b.lstrip("FALA"):
        return True
    # Paris publications may embed the marketplace ID in a URL slug.
    if len(a) >= 5 and (a in b or b in a):
        return True
    return False


def cross_audit(run_id: str, season_id: Optional[int] = None,
                db_path: Optional[str] = None) -> Dict[str, Any]:
    init_season_schema(db_path)
    conn = sqlite3.connect(_db_path(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        if season_id is None:
            row = conn.execute("SELECT season_id FROM season_registry WHERE status='ACTIVE' ORDER BY season_id DESC LIMIT 1").fetchone()
            if not row:
                return {"ok": False, "error": "NO_ACTIVE_SEASON"}
            season_id = row[0]
        elif isinstance(season_id, str) and not season_id.isdigit():
            row = conn.execute("SELECT season_id FROM season_registry WHERE name=? ORDER BY season_id DESC LIMIT 1", (season_id,)).fetchone()
            if not row:
                return {"ok": False, "error": "SEASON_NOT_FOUND", "season": season_id}
            season_id = row[0]
        else:
            season_id = int(season_id)
        products = [dict(r) for r in conn.execute(
            "SELECT * FROM season_products WHERE season_id=?", (season_id,))]
        obs_count = alert_count = 0
        fields = [("mpm_ripley", "Ripley"), ("mlc_meli", "Mercado Libre"),
                  ("mkp_paris", "Paris"), ("falabella_id", "Falabella")]
        now = datetime.now().isoformat()
        for product in products:
            for id_field, marketplace in fields:
                target = str(product.get(id_field) or "").strip()
                if not target:
                    continue
                cands = _id_candidates(target)
                ph = ",".join("?" * len(cands))
                pub = conn.execute(f"""SELECT * FROM mri_publications
                    WHERE run_id LIKE ? AND marketplace=?
                    AND (marketplace_product_id IN ({ph}) OR publication_id LIKE ?)
                    ORDER BY position ASC, rowid DESC LIMIT 1""",
                    [run_id + "%", marketplace] + cands + ["%" + target + "%"]).fetchone()
                estado = "FOUND" if pub else "NOT_FOUND"
                if pub and not _ids_match(target, str(pub["marketplace_product_id"] or "")):
                    _insert_alert(conn, product["id"], marketplace, "IDENTITY_MISMATCH",
                                  "CRITICAL", {"expected": target,
                                               "observed": str(pub["marketplace_product_id"] or ""),
                                               "url": pub["canonical_url"]})
                    alert_count += 1
                price = _pub_price(dict(pub)) if pub else None
                stock = _pub_stock(dict(pub)) if pub else "UNKNOWN"
                if stock == "UNKNOWN" and price is not None:
                    stock = "IN_STOCK"  # v1 inference: priced live publication
                position = int(pub["position"] or 0) if pub and pub["position"] else None
                top = _top_level(position) if position else None
                url = pub["canonical_url"] if pub else None
                prev = conn.execute("""SELECT * FROM season_observations
                    WHERE season_product_id=? AND marketplace=?
                    ORDER BY id DESC LIMIT 1""", (product["id"], marketplace)).fetchone()
                conn.execute("""INSERT INTO season_observations
                    (season_product_id, marketplace, audit_run_id, estado,
                     precio_observado, precio_oferta, stock_status, posicion_observada,
                     top_level, url_evidencia, fecha_observacion)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (product["id"], marketplace, run_id, estado, price, None,
                     stock, position, top, url, now))
                obs_count += 1
                if prev:
                    prev = dict(prev)
                    if price is not None and prev.get("precio_observado") is not None:
                        old = float(prev["precio_observado"])
                        if price < old:
                            _insert_alert(conn, product["id"], marketplace, "PRICE_DROP", "WARN",
                                          {"old": old, "new": price})
                            alert_count += 1
                        elif price > old:
                            _insert_alert(conn, product["id"], marketplace, "PRICE_INCREASE", "INFO",
                                          {"old": old, "new": price})
                            alert_count += 1
                    if prev.get("stock_status") == "IN_STOCK" and stock == "OUT_OF_STOCK":
                        _insert_alert(conn, product["id"], marketplace, "STOCK_OUTAGE", "CRITICAL",
                                      {"old": "IN_STOCK", "new": stock})
                        alert_count += 1
                    elif prev.get("stock_status") == "OUT_OF_STOCK" and stock == "IN_STOCK":
                        _insert_alert(conn, product["id"], marketplace, "BACK_IN_STOCK", "INFO",
                                      {"old": "OUT_OF_STOCK", "new": stock})
                        alert_count += 1
                    old_top = prev.get("top_level")
                    if old_top and top and old_top != top:
                        order = {"TOP30": 30, "TOP60": 60, "TOP90": 90, "TOP120": 120, "TOP240": 240}
                        if order.get(top, 999) > order.get(old_top, 0):
                            _insert_alert(conn, product["id"], marketplace, "TOP_CHANGE", "WARN",
                                          {"old": old_top, "new": top})
                            alert_count += 1
        conn.commit()
        return {"ok": True, "season_id": season_id, "products": len(products),
                "observations": obs_count, "alerts": alert_count}
    finally:
        conn.close()


def season_status(db_path: Optional[str] = None) -> Dict[str, Any]:
    init_season_schema(db_path)
    conn = sqlite3.connect(_db_path(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        return {
            "seasons": [dict(r) for r in conn.execute("SELECT * FROM season_registry")],
            "products": conn.execute("SELECT COUNT(*) FROM season_products").fetchone()[0],
            "observations": conn.execute("SELECT COUNT(*) FROM season_observations").fetchone()[0],
            "alerts": conn.execute("SELECT COUNT(*) FROM season_alerts").fetchone()[0],
        }
    finally:
        conn.close()
