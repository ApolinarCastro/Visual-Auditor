"""Fail-closed execution preflight for MRI (skills, browsers, profiles, auth)."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / "skills"
MANIFEST = SKILLS_DIR / "MRI_MANDATORY_SKILLS.json"
ML_PROFILE = ROOT / "data" / "mercado_libre_profile"
RIPLEY_PROFILE = ROOT / "data" / "ripley_profile"


def _check_skills():
    details = {}
    blockers = []
    if not MANIFEST.exists():
        return {"ok": False, "details": {"manifest": False},
                "blockers": ["skills/MRI_MANDATORY_SKILLS.json ausente"]}
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "details": {}, "blockers": [f"manifiesto inválido: {exc}"]}
    required = manifest.get("required") or []
    details["manifest"] = True
    details["fail_closed"] = bool(manifest.get("fail_closed"))
    for name in required:
        present = (SKILLS_DIR / name).exists()
        details[name] = present
        if not present:
            blockers.append(f"skill obligatoria ausente: {name}")
    if not required or not manifest.get("fail_closed"):
        blockers.append("manifiesto sin required o sin fail_closed")
    return {"ok": not blockers, "details": details, "blockers": blockers}


def _check_auth():
    user = os.environ.get("DASHBOARD_USER")
    password = os.environ.get("DASHBOARD_PASS")
    blockers = [] if (user and password) else ["DASHBOARD_USER/DASHBOARD_PASS ausentes"]
    return {"ok": not blockers, "details": {"user": bool(user), "password": bool(password)},
            "blockers": blockers}


def _check_browsers():
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    chromium = sorted(base.glob("chromium-*")) if base.exists() else []
    details = {"playwright_dir": base.exists(),
               "chromium_versions": [p.name for p in chromium]}
    blockers = []
    if not base.exists() or not chromium:
        blockers.append("Playwright/Chromium no instalado")
    if len(chromium) > 2:
        details["warning"] = f"{len(chromium)} builds de Chromium; pinear una versión"
    return {"ok": not blockers, "details": details, "blockers": blockers}


def _check_profiles():
    from app.mri_autonomous.browser_profile_manager import profile_status
    details = {}
    blockers = []
    for name, path in (("mercado_libre", ML_PROFILE), ("ripley", RIPLEY_PROFILE)):
        st = profile_status(path)
        details[name] = st
        if not st.get("exists"):
            details.setdefault("warnings", []).append(f"perfil se creará al primer uso: {path}")
        if st.get("locked"):
            blockers.append(f"perfil bloqueado: {path} (PID {st.get('pid')})")
    return {"ok": not blockers, "details": details, "blockers": blockers}


def run_preflight(*, check_auth=True):
    checks = {"skills": _check_skills()}
    if check_auth:
        checks["auth"] = _check_auth()
    checks["browsers"] = _check_browsers()
    checks["profiles"] = _check_profiles()
    blockers = []
    for name, res in checks.items():
        for b in res.get("blockers") or []:
            blockers.append(f"{name}: {b}")
    return {"ok": not blockers, "generated_at": __import__("datetime").datetime.now().isoformat(),
            "checks": checks, "blockers": blockers}
