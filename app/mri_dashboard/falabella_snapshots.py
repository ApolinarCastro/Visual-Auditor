"""Comparable, append-only Falabella snapshots + diffs for MRI.

Reuses the useful idea of the external pipeline (dated snapshot + product/SKU
diff + price changes) but keeps MRI's rules: dynamic surfaces, explicit
terminals, StorageGuard-authorized aux dir, atomic writes, coverage fingerprint,
and no silent 403/soft-404 handling.

Snapshots live in <aux_dir>/falabella_snapshots/ and are never overwritten.
Only snapshots with the SAME coverage fingerprint and both complete are
compared; otherwise the delta is declared COVERAGE_CHANGED/UNCOMPARABLE.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

_DIR = "falabella_snapshots"
_DIFFS = "diffs"
_TERMINAL_OK = ("EXHAUSTION", "EMPTY")


def _fingerprint(surfaces):
    labels = sorted(str(s.get("surface")) for s in surfaces or [])
    return hashlib.sha1("|".join(labels).encode("utf-8")).hexdigest()[:16]


def _atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _price_min(obs):
    prices = [p.get("price") for p in (obs.get("skus") or {}).values()
              if p.get("price") is not None]
    return min(prices) if prices else obs.get("price")


def capture(audit, observations, run_id=None):
    """Write an immutable snapshot and return (path, snapshot dict)."""
    aux = Path(audit["_aux_dir"])
    surfaces = [{k: s.get(k) for k in
                 ("surface", "terminal", "expected_cards", "cards",
                  "unique_product_ids", "unique_keys", "pages_traversed")}
                for s in (audit.get("surfaces") or [])]
    products = []
    keys = set()
    for obs in observations or []:
        pid = str(obs.get("product_id"))
        skus = {}
        for sku, meta in (obs.get("skus") or {}).items():
            skus[str(sku)] = meta
            keys.add((pid, str(sku)))
        products.append({
            "productId": pid,
            "groupUrl": obs.get("group_url") or obs.get("url"),
            "variants": obs.get("variants") or ([obs.get("variant_id")]
                                                  if obs.get("variant_id") else []),
            "skuIds": sorted(skus),
            "skus": skus,
            "price_min": _price_min(obs),
            "categories": obs.get("categories") or [],
            "surfaces": obs.get("surfaces") or [],
            "url": obs.get("url"),
            "seller": obs.get("seller_name"),
        })
    captured = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    snap = {
        "captured_at_utc": captured,
        "run_id": run_id,
        "build_id": audit.get("build_id"),
        "coverage_fingerprint": _fingerprint(surfaces),
        "complete": bool(audit.get("complete")),
        "surfaces": surfaces,
        "unique_products": len(products),
        "unique_keys": len(keys),
        "products": products,
    }
    stamp = captured.replace(":", "").replace("-", "")
    path = aux / _DIR / f"falabella_{stamp}_{str(run_id or 'run')[:28]}.json"
    _atomic_write(path, json.dumps(snap, ensure_ascii=False, indent=1))
    return path, snap


def load_previous(aux, fingerprint, current_path):
    folder = Path(aux) / _DIR
    if not folder.exists():
        return None
    for f in sorted(folder.glob("falabella_*.json"), reverse=True):
        if str(f) == str(current_path):
            continue
        try:
            snap = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if snap.get("coverage_fingerprint") == fingerprint and snap.get("complete"):
            return f, snap
    return None


def _product_map(snap):
    out = {}
    for p in snap.get("products") or []:
        out[str(p.get("productId"))] = p
    return out


def _sku_map(snap):
    out = {}
    for p in snap.get("products") or []:
        for sku, meta in (p.get("skus") or {}).items():
            out[(str(p.get("productId")), str(sku))] = meta.get("price")
    return out


def diff(prev, cur):
    pa, ca = _product_map(prev), _product_map(cur)
    common = set(pa) & set(ca)
    price_changes = []
    for pid in common:
        pp, cp = pa[pid].get("price_min"), ca[pid].get("price_min")
        if pp is not None and cp is not None and pp != cp:
            price_changes.append((pid, pp, cp, cp - pp,
                                  round(100 * (cp - pp) / pp, 2) if pp else None))
    pka, cka = _sku_map(prev), _sku_map(cur)
    sku_add = [k for k in cka if k not in pka]
    sku_del = [k for k in pka if k not in cka]
    sku_changes = [(k, pka[k], cka[k]) for k in (set(pka) & set(cka))
                   if pka[k] is not None and cka[k] is not None and pka[k] != cka[k]]
    union_products = set(pa) | set(ca)
    union_keys = set(pka) | set(cka)
    return {
        "comparable": True,
        "prev_captured_at": prev.get("captured_at_utc"),
        "cur_captured_at": cur.get("captured_at_utc"),
        "products": {
            "previous": len(pa), "current": len(ca), "common": len(common),
            "added": sorted(set(ca) - set(pa)), "removed": sorted(set(pa) - set(ca)),
            "price_changes": [{"productId": pid, "before": b, "after": a,
                               "delta_clp": d, "delta_pct": p}
                              for pid, b, a, d, p in sorted(price_changes)],
            "jaccard": round(len(common) / len(union_products), 4) if union_products else None,
        },
        "skus": {
            "previous": len(pka), "current": len(cka),
            "added": len(sku_add), "removed": len(sku_del),
            "price_changes": len(sku_changes),
            "jaccard": round((len(pka) & len(cka)) / len(union_keys), 4) if union_keys else None,
        },
        "coverage_changed": False,
    }


def compare_and_write(aux, current_path, snap):
    """Return a compact freshness dict; write diff JSON/CSV when comparable."""
    prev = load_previous(aux, snap["coverage_fingerprint"], current_path)
    if not prev:
        return {"comparable": False, "reason": "SIN_BASELINE_COMPARABLE",
                "coverage_fingerprint": snap["coverage_fingerprint"]}
    prev_path, prev_snap = prev
    coverage_changed = (
        sorted(str((s.get("expected_cards"), s.get("terminal"))) for s in prev_snap.get("surfaces") or [])
        != sorted(str((s.get("expected_cards"), s.get("terminal"))) for s in snap.get("surfaces") or []))
    d = diff(prev_snap, snap)
    d["coverage_changed"] = coverage_changed
    d["baseline_snapshot"] = prev_path.name
    stamp = snap["captured_at_utc"].replace(":", "").replace("-", "")
    diffdir = Path(aux) / _DIR / _DIFFS
    _atomic_write(diffdir / f"falabella_diff_{stamp}.json",
                  json.dumps(d, ensure_ascii=False, indent=1))
    rows = []
    for pid in d["products"]["added"]:
        rows.append({"nivel": "PRODUCTO", "tipo": "ALTA", "productId": pid})
    for pid in d["products"]["removed"]:
        rows.append({"nivel": "PRODUCTO", "tipo": "BAJA", "productId": pid})
    for ch in d["products"]["price_changes"]:
        rows.append({"nivel": "PRODUCTO", "tipo": "CAMBIO_PRECIO",
                     "productId": ch["productId"], "precio_anterior": ch["before"],
                     "precio_nuevo": ch["after"], "delta_clp": ch["delta_clp"],
                     "delta_pct": ch["delta_pct"]})
    with open(diffdir / f"falabella_diff_{stamp}.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["nivel", "tipo", "productId",
                                           "precio_anterior", "precio_nuevo",
                                           "delta_clp", "delta_pct"])
        w.writeheader()
        w.writerows(rows)
    return d
