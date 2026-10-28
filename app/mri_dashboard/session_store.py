"""Local session-cookie store for MRI (Ripley / Mercado Libre).

The operator pastes a Cookie-Editor JSON array in the dashboard. MRI stores the
normalized cookies under data/sessions (outside git), never logs values, and
re-injects them into its own persistent browser context. This is session reuse,
not CAPTCHA solving.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

MARKET_DOMAINS = {
    "Ripley": ("ripley.cl",),
    # Cookie-Editor can export auth cookies for .mercadolibre.com while the
    # Chilean storefront is .cl; accept both and let the browser apply scope.
    "Mercado Libre": ("mercadolibre.cl", "mercadolibre.com"),
}
MARKET_SLUG = {"Ripley": "ripley", "Mercado Libre": "mercado_libre"}


def _session_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_path(marketplace: str) -> Path:
    slug = MARKET_SLUG.get(marketplace, re.sub(r"[^a-z0-9]+", "_", marketplace.lower()))
    return _session_dir() / f"{slug}_cookies.json"


def _domain_ok(domain: str, marketplace: str) -> bool:
    domain = str(domain or "").lower().lstrip(".")
    return any(domain == d or domain.endswith("." + d) for d in MARKET_DOMAINS.get(marketplace, ()))


def _same_site(value):
    if value is None:
        return None
    v = str(value).strip().lower()
    return {"no_restriction": "None", "none": "None", "lax": "Lax",
            "strict": "Strict", "unspecified": None}.get(v)


def normalize_cookies(raw, marketplace: str) -> list[dict]:
    """Convert Cookie-Editor/EditThisCookie JSON into Playwright cookies."""
    # Accept a JSON string, {"cookies":[...]}, or a single cookie object.
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception as exc:
            raise ValueError(f"JSON inválido: {type(exc).__name__}") from exc
    if isinstance(raw, dict):
        if "cookies" in raw:
            raw = raw.get("cookies")
        elif "name" in raw and "value" in raw:
            raw = [raw]
        else:
            raise ValueError("El objeto JSON no contiene 'cookies' ni una cookie única")
    if not isinstance(raw, list):
        raise ValueError(f"Se esperaba un array JSON de cookies; recibido {type(raw).__name__}")
    out, seen = [], set()
    now = datetime.now().timestamp()
    stats = {"total": len(raw), "domain": 0, "expired": 0, "shape": 0}
    for item in raw:
        if not isinstance(item, dict):
            stats["shape"] += 1
            continue
        name = str(item.get("name") or "").strip()
        value = item.get("value")
        domain = str(item.get("domain") or "").strip()
        if not name or value is None:
            stats["shape"] += 1
            continue
        if not _domain_ok(domain, marketplace):
            stats["domain"] += 1
            continue
        expires = item.get("expirationDate", item.get("expires"))
        try:
            expires = float(expires) if expires not in (None, "", -1) else None
        except (TypeError, ValueError):
            expires = None
        if expires is not None and expires <= now:
            stats["expired"] += 1
            continue  # never import an expired credential
        cookie = {
            "name": name,
            "value": str(value),
            "domain": domain,
            "path": str(item.get("path") or "/"),
            "secure": bool(item.get("secure", False)),
            "httpOnly": bool(item.get("httpOnly", False)),
        }
        if expires is not None:
            cookie["expires"] = expires
        same_site = _same_site(item.get("sameSite"))
        if same_site:
            cookie["sameSite"] = same_site
        key = (cookie["domain"], cookie["name"], cookie["path"])
        if key in seen:
            continue
        seen.add(key)
        out.append(cookie)
        if len(out) >= 500:
            break
    if not out:
        raise ValueError(
            f"No hay cookies válidas para {marketplace}: "
            f"total={stats['total']}, dominio={stats['domain']}, "
            f"expiradas={stats['expired']}, inválidas={stats['shape']}")
    return out


def save_session(marketplace: str, raw) -> dict:
    cookies = normalize_cookies(raw, marketplace)
    path = session_path(marketplace)
    payload = {
        "marketplace": marketplace,
        "updated_at": datetime.now().isoformat(),
        "cookies": cookies,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return {"marketplace": marketplace, "count": len(cookies),
            "updated_at": payload["updated_at"]}


def load_cookies(marketplace: str) -> list[dict]:
    path = session_path(marketplace)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cookies = data.get("cookies") if isinstance(data, dict) else data
        return cookies if isinstance(cookies, list) else []
    except Exception:
        return []


def session_status(marketplace: str) -> dict:
    path = session_path(marketplace)
    cookies = load_cookies(marketplace)
    updated = None
    if path.exists():
        updated = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    return {"marketplace": marketplace, "exists": path.exists(),
            "cookie_count": len(cookies), "updated_at": updated,
            "status": "ACTIVO" if cookies else "SIN_SESION"}
