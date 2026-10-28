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
    "Mercado Libre": ("mercadolibre.cl",),
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
    if isinstance(raw, dict):
        raw = raw.get("cookies", [])
    if not isinstance(raw, list):
        raise ValueError("Se esperaba un array JSON de cookies")
    out, seen = [], set()
    now = datetime.now().timestamp()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = item.get("value")
        domain = str(item.get("domain") or "").strip()
        if not name or value is None or not _domain_ok(domain, marketplace):
            continue
        expires = item.get("expirationDate", item.get("expires"))
        try:
            expires = float(expires) if expires not in (None, "", -1) else None
        except (TypeError, ValueError):
            expires = None
        if expires is not None and expires <= now:
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
        raise ValueError(f"No hay cookies válidas para {marketplace} (dominio/expiración)")
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
