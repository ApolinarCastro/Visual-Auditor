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
    # Numeric values from SQLite/pandas must not be treated as Chilean
    # thousands-separated text ("24.990" -> 24990, but 24990.0 -> 24990).
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).replace("$", "").strip()
        if s.count(".") == 1 and len(s.rsplit(".", 1)[1]) == 3 and s.rsplit(".", 1)[0].isdigit():
            s = s.replace(".", "")
        return float(s.replace(".", "").replace(",", "."))
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
    # MRI-044: prefer the canonical persisted columns.
    try:
        for key in ("price_observed", "price_offer"):
            if row.get(key) is not None:
                return _safe_float(row.get(key))
    except Exception:
        pass
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
    # MRI-044: prefer the canonical persisted column.
    try:
        canonical = str(row.get("stock_status") or "").upper()
        if canonical in ("IN_STOCK", "OUT_OF_STOCK"):
            return canonical
    except Exception:
        pass
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



def list_alerts(alert_type: Optional[str] = None, marketplace: Optional[str] = None,
                severity: Optional[str] = None, limit: int = 100,
                db_path: Optional[str] = None) -> Dict[str, Any]:
    init_season_schema(db_path)
    conn = sqlite3.connect(_db_path(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    where, params = [], []
    if alert_type:
        where.append("a.alert_type = ?")
        params.append(alert_type)
    if marketplace:
        where.append("a.marketplace = ?")
        params.append(marketplace)
    if severity:
        where.append("a.severity = ?")
        params.append(severity)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(f"""
        SELECT a.*, p.sku_padre, p.nombre, p.group_id
        FROM season_alerts a JOIN season_products p ON p.id = a.season_product_id
        {clause}
        ORDER BY a.id DESC LIMIT ?
    """, params + [int(limit or 100)]).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            detail = json.loads(d.get("details") or "{}")
        except Exception:
            detail = {}
        d["details_json"] = detail
        out.append(d)
    return {"ok": True, "alerts": out, "count": len(out)}


def alerts_summary(db_path: Optional[str] = None) -> Dict[str, Any]:
    init_season_schema(db_path)
    conn = sqlite3.connect(_db_path(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        by_type = [dict(r) for r in conn.execute(
            "SELECT alert_type, COUNT(*) n FROM season_alerts GROUP BY alert_type")]
        by_sev = [dict(r) for r in conn.execute(
            "SELECT severity, COUNT(*) n FROM season_alerts GROUP BY severity")]
        by_mkt = [dict(r) for r in conn.execute(
            "SELECT marketplace, COUNT(*) n FROM season_alerts GROUP BY marketplace")]
        products = conn.execute("SELECT COUNT(*) FROM season_products").fetchone()[0]
        return {"ok": True, "total_alerts": conn.execute(
            "SELECT COUNT(*) FROM season_alerts").fetchone()[0],
            "products": products, "by_type": by_type,
            "by_severity": by_sev, "by_marketplace": by_mkt}
    finally:
        conn.close()


def certification(marketplace: Optional[str] = None,
                  limit: int = 500, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Compare a reported VA top (when supplied) with MRI's latest observation."""
    init_season_schema(db_path)
    conn = sqlite3.connect(_db_path(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT p.id, p.sku_padre, p.nombre, p.group_id, p.falabella_id,
                   p.mkp_paris, p.mpm_ripley, p.mlc_meli,
                   o.marketplace, o.top_level, o.posicion_observada, o.estado,
                   o.fecha_observacion
            FROM season_products p
            LEFT JOIN season_observations o ON o.id = (
                SELECT id FROM season_observations x
                WHERE x.season_product_id = p.id
                  AND (? IS NULL OR x.marketplace = ?)
                ORDER BY x.id DESC LIMIT 1)
            WHERE p.season_id = (SELECT season_id FROM season_registry WHERE name='SS_2026')
            ORDER BY p.id LIMIT ?
        """, (marketplace, marketplace, int(limit or 500))).fetchall()
        out = []
        matches = mismatches = missing = 0
        for r in rows:
            d = dict(r)
            va = d.get("top_va")  # not persisted by MRI; explicit absence
            mri = d.get("top_level")
            if not mri:
                missing += 1
                coincide = None
            elif va is None:
                coincide = None
            else:
                coincide = str(va) == str(mri)
                matches += 1 if coincide else 0
                mismatches += 0 if coincide else 1
            d["top_va"] = va
            d["coincide"] = coincide
            d["difference"] = (f"VA: {va}, MRI: {mri}" if va and mri and not coincide else None)
            out.append(d)
        return {"ok": True, "rows": out, "products": len(out),
                "matches": matches, "mismatches": mismatches,
                "missing": missing, "va_data": "MISSING",
                "note": "VA reported TOP is not persisted by MRI; upload/VA JSON is required."}
    finally:
        conn.close()



def visibility(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """VA-style visibility matrix: marketplace x category with TOP buckets."""
    init_season_schema(db_path)
    conn = sqlite3.connect(_db_path(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT marketplace,
                   COALESCE(NULLIF(category_observed,''), NULLIF(category_expected,''),
                            'SIN_CATEGORIA') AS category,
                   COUNT(*) AS total_nicopoly,
                   SUM(CASE WHEN position BETWEEN 1 AND 30 THEN 1 ELSE 0 END) AS top_30,
                   SUM(CASE WHEN position BETWEEN 1 AND 60 THEN 1 ELSE 0 END) AS top_60,
                   SUM(CASE WHEN position BETWEEN 1 AND 90 THEN 1 ELSE 0 END) AS top_90,
                   SUM(CASE WHEN position BETWEEN 1 AND 120 THEN 1 ELSE 0 END) AS top_120,
                   SUM(CASE WHEN position BETWEEN 1 AND 240 THEN 1 ELSE 0 END) AS top_240
            FROM mri_publications
            WHERE position IS NOT NULL
              AND category_observed NOT IN ('CATEGORY_UNKNOWN','COMMERCIAL_FACET')
            GROUP BY marketplace, category
            ORDER BY marketplace, total_nicopoly DESC
        """).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            total = int(d["total_nicopoly"] or 0)
            def pct(n):
                return round((int(d.get(n) or 0) / total * 100.0), 2) if total else 0.0
            p30, p60, p90, p120, p240 = (pct("top_30"), pct("top_60"),
                                          pct("top_90"), pct("top_120"), pct("top_240"))
            if p30 >= 5:
                presence, risk = "EXCELENTE", "BAJO"
            elif p30 >= 2:
                presence, risk = "BUENA", "MEDIO"
            elif p30 >= 0.5:
                presence, risk = "MEDIA", "ALTO"
            else:
                presence, risk = "CRITICA", "CRITICO"
            d.update({"total_marketplace": total, "pct_30": p30, "pct_60": p60,
                      "pct_90": p90, "pct_120": p120, "pct_240": p240,
                      "presence_level": presence, "risk_level": risk})
            out.append(d)
        return out
    finally:
        conn.close()


def season_matrix(season_id: Optional[str] = None,
                  db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Latest season observation per product/marketplace, ordered by SKU."""
    init_season_schema(db_path)
    conn = sqlite3.connect(_db_path(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        sid = None
        if season_id:
            if str(season_id).isdigit():
                sid = int(season_id)
            else:
                row = conn.execute("SELECT season_id FROM season_registry WHERE name=? ORDER BY season_id DESC LIMIT 1",
                                   (season_id,)).fetchone()
                sid = row[0] if row else None
        if sid is None:
            row = conn.execute("SELECT season_id FROM season_registry WHERE status='ACTIVE' ORDER BY season_id DESC LIMIT 1").fetchone()
            sid = row[0] if row else None
        if sid is None:
            return []
        rows = conn.execute("""
            SELECT p.id AS season_product_id, p.sku_padre, p.sku_hijo, p.nombre,
                   p.group_id, p.season_id,
                   o.marketplace, o.estado, o.posicion_observada, o.top_level,
                   o.url_evidencia, o.precio_observado, o.stock_status,
                   o.audit_run_id, o.fecha_observacion
            FROM season_products p
            JOIN season_observations o ON o.season_product_id = p.id
                AND o.id = (
                    SELECT MAX(x.id) FROM season_observations x
                    WHERE x.season_product_id = p.id AND x.marketplace = o.marketplace)
            WHERE p.season_id=?
            ORDER BY p.sku_padre, o.marketplace
        """, (sid,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()



def season_health(season_id: Optional[str] = None,
                  db_path: Optional[str] = None) -> Dict[str, Any]:
    """Group the season matrix by SKU into a gerencial health panel."""
    rows = season_matrix(season_id, db_path)
    alerts = list_alerts(limit=5000, db_path=db_path).get("alerts", [])
    alert_by = {}
    for a in alerts:
        alert_by.setdefault((a["season_product_id"], a["marketplace"]), []).append(a)

    conn = sqlite3.connect(_db_path(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        if season_id and not str(season_id).isdigit():
            row = conn.execute("SELECT season_id FROM season_registry WHERE name=? ORDER BY season_id DESC LIMIT 1",
                               (season_id,)).fetchone()
            sid = row[0] if row else None
        elif season_id:
            sid = int(season_id)
        else:
            row = conn.execute("SELECT season_id FROM season_registry WHERE status='ACTIVE' ORDER BY season_id DESC LIMIT 1").fetchone()
            sid = row[0] if row else None
        products = [dict(r) for r in conn.execute(
            "SELECT id, sku_padre, sku_hijo, nombre, mpm_ripley, mlc_meli, mkp_paris, falabella_id, group_id "
            "FROM season_products WHERE season_id=? ORDER BY sku_padre", (sid,))] if sid else []
    finally:
        conn.close()

    by_sku = {}
    for r in rows:
        by_sku.setdefault(r["sku_padre"], []).append(r)

    def fallback_url(marketplace, p):
        if marketplace == "Ripley" and p.get("mpm_ripley"):
            return f"https://simple.ripley.cl/search/{p['mpm_ripley']}"
        if marketplace == "Paris" and p.get("mkp_paris"):
            return f"https://www.paris.cl/search/?q={p['mkp_paris']}"
        if marketplace == "Falabella" and p.get("falabella_id"):
            return f"https://www.falabella.com/falabella-cl/search?Ntt={p['falabella_id']}"
        if marketplace == "Mercado Libre" and p.get("mlc_meli"):
            return f"https://www.mercadolibre.cl/{p['mlc_meli']}"
        return None

    labels = {"Ripley": "Ripley", "Paris": "Paris", "Falabella": "Falabella", "Mercado Libre": "ML"}
    out = []
    counts = {"SALUDABLE": 0, "ADVERTENCIA": 0, "CRITICO": 0, "SIN_DATOS": 0}
    for p in products:
        obs = by_sku.get(p["sku_padre"], [])
        obs_by_mkt = {r["marketplace"]: r for r in obs}
        found = [r for r in obs if r.get("estado") == "FOUND"]
        markets = {}
        links = []
        for marketplace, label in labels.items():
            r = obs_by_mkt.get(marketplace)
            if not r:
                markets[label] = {"symbol": "➖", "estado": "SIN_DATO", "url": fallback_url(marketplace, p),
                                  "stock": "UNKNOWN", "price": None}
                continue
            al = alert_by.get((p["id"], marketplace), [])
            url = r.get("url_evidencia") or fallback_url(marketplace, p)
            if r.get("estado") == "FOUND":
                sym = "⚠️" if al else "✅"
                st = "CON_ALERTA" if al else "PUBLICADO"
                if url and url not in links:
                    links.append(url)
            else:
                sym, st = "❌", "NO_ENCONTRADO"
            markets[label] = {"symbol": sym, "estado": st, "url": url,
                              "stock": r.get("stock_status") or "UNKNOWN",
                              "price": r.get("precio_observado")}
        price = next((r.get("precio_observado") for r in found if r.get("precio_observado") is not None), None)
        stocks = [r.get("stock_status") for r in found]
        if "OUT_OF_STOCK" in stocks:
            stock = "OUT_OF_STOCK"
        elif "IN_STOCK" in stocks:
            stock = "IN_STOCK"
        else:
            stock = "UNKNOWN"
        price_alerts = [a for a in alerts if a["season_product_id"] == p["id"]
                        and a["alert_type"] in ("PRICE_DROP", "PRICE_INCREASE", "STOCK_OUTAGE", "BACK_IN_STOCK")]
        found_obs = bool(found)
        if not obs:
            health = "SIN_DATOS"
        elif not found_obs:
            health = "CRITICO"
        elif price_alerts or stock == "OUT_OF_STOCK" or (found_obs and stock == "UNKNOWN"):
            health = "ADVERTENCIA"
        else:
            health = "SALUDABLE"
        counts[health] += 1
        out.append({"sku_padre": p["sku_padre"], "sku_hijo": p.get("sku_hijo"),
                    "nombre": p["nombre"], "group_id": p.get("group_id"),
                    "health": health, "markets": markets, "price": price,
                    "stock": stock, "links": links,
                    "alerts": [{"type": a["alert_type"], "severity": a["severity"],
                                "details": a.get("details_json") or {}} for a in price_alerts]})
    return {"products": out, "counts": counts, "total": len(out)}
