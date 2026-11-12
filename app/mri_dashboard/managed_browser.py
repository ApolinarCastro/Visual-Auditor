"""Lifecycle helpers for the visible managed browser (no secrets in API output)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from app.mri_autonomous.browser_profile_manager import profile_status
from app.mri_dashboard import session_store

ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).resolve().parent / "managed_browser_worker.py"


def _control_dir(marketplace: str) -> Path:
    slug = session_store.MARKET_SLUG.get(
        session_store.canonical_marketplace(marketplace), "marketplace")
    path = ROOT / "data" / "sessions" / "managed" / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pid_alive(pid) -> bool:
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def status(marketplace: str) -> dict:
    name = session_store.canonical_marketplace(marketplace)
    control = _control_dir(name)
    st = _read(control / "status.json", {}) or {}
    pid = st.get("pid") or _read(control / "pid.json", {}).get("pid")
    alive = bool(pid and _pid_alive(pid))
    prof = session_store.browser_profile_path(name)
    return {
        "marketplace": name,
        "state": st.get("state") or ("CLOSED" if not alive else "UNKNOWN"),
        "alive": alive,
        "pid": pid if alive else None,
        "profile": str(prof),
        "profile_lock": profile_status(prof),
        "session": session_store.session_status(name),
        "control_dir": str(control),
        "updated_at": st.get("at"),
    }


def open_browser(marketplace: str) -> dict:
    name = session_store.canonical_marketplace(marketplace)
    if name not in session_store.MARKET_DOMAINS:
        return {"ok": False, "error": "MARKETPLACE_NOT_SUPPORTED"}
    current = status(name)
    if current.get("alive"):
        return {"ok": True, "already_open": True, **current}
    profile = session_store.browser_profile_path(name)
    locked = profile_status(profile)
    if locked.get("locked"):
        return {"ok": False, "error": "PROFILE_LOCKED",
                "message": f"Perfil en uso por PID {locked.get('pid')}"}
    control = _control_dir(name)
    for f in ("status.json", "saved.json", "save_error.json", "stop.flag", "save.flag"):
        (control / f).unlink(missing_ok=True)
    log = (control / "worker.log").open("a", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        proc = subprocess.Popen(
            [sys.executable, str(WORKER), "--marketplace", name,
             "--profile", str(profile), "--control", str(control)],
            cwd=str(ROOT), stdout=log, stderr=log, creationflags=creationflags)
    except Exception as exc:
        log.close()
        return {"ok": False, "error": "BROWSER_LAUNCH_FAILED",
                "message": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            log.close()
        except Exception:
            pass
    (control / "pid.json").write_text(
        json.dumps({"pid": proc.pid, "started_at": datetime.now().isoformat()}),
        encoding="utf-8")
    # Give Playwright time to report a clear WinError/launch failure.
    for _ in range(30):
        time.sleep(0.5)
        st = _read(control / "status.json", {}) or {}
        if st.get("state") in ("OPEN", "FAILED"):
            break
        if proc.poll() is not None:
            break
    return {"ok": (status(name).get("state") != "FAILED"), "pid": proc.pid,
            **status(name)}


def save_session(marketplace: str) -> dict:
    name = session_store.canonical_marketplace(marketplace)
    control = _control_dir(name)
    if not status(name).get("alive"):
        return {"ok": False, "error": "BROWSER_NOT_OPEN"}
    (control / "saved.json").unlink(missing_ok=True)
    (control / "save_error.json").unlink(missing_ok=True)
    (control / "save.flag").write_text("save", encoding="utf-8")
    for _ in range(40):
        time.sleep(0.5)
        saved = _read(control / "saved.json")
        if saved:
            return {"ok": True, **saved,
                    "session": session_store.session_status(name)}
        err = _read(control / "save_error.json")
        if err:
            return {"ok": False, "error": "SESSION_SAVE_FAILED", **err}
    return {"ok": False, "error": "SESSION_SAVE_TIMEOUT"}


def close_browser(marketplace: str) -> dict:
    name = session_store.canonical_marketplace(marketplace)
    control = _control_dir(name)
    st = status(name)
    if not st.get("alive"):
        return {"ok": True, "already_closed": True, **st}
    (control / "stop.flag").write_text("stop", encoding="utf-8")
    for _ in range(30):
        time.sleep(0.5)
        if not status(name).get("alive"):
            return {"ok": True, "closed": True, **status(name)}
    # Last-resort cleanup of the worker process only (never other processes).
    pid = st.get("pid")
    if pid:
        try:
            proc = subprocess.Popen(["taskkill", "/PID", str(pid), "/T"],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            proc.wait(timeout=10)
        except Exception:
            pass
    return {"ok": not status(name).get("alive"), "forced": True, **status(name)}


def verify_session(marketplace: str) -> dict:
    name = session_store.canonical_marketplace(marketplace)
    cookies = session_store.list_cookies(name, reveal=False)
    return {
        "marketplace": name,
        "cookie_count": len(cookies),
        "expired": sum(1 for c in cookies if c.get("expired")),
        "has_auth_candidates": any(
            str(c.get("name", "")).lower() in
            ("cf_clearance", "ssid", "sessionid", "csrf_token", "sid")
            for c in cookies),
        # Presence of cookies is not proof of an authenticated session.
        "authenticated": None,
        "auth_status": "NOT_VERIFIED",
        "note": "La validez de autenticación requiere comprobación en navegador.",
    }
