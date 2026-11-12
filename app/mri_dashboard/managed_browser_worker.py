"""Visible managed browser for MRI session administration.

Runs as a separate process so the HTTP server never owns the visible browser.
The worker uses the existing persistent-profile lock and writes Cookie-Editor
compatible state when the dashboard requests a save.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.mri_autonomous.browser_profile_manager import ProfileLock
from app.mri_dashboard import session_store


def _write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _fail(control: Path, message: str) -> None:
    _write(control / "status.json", {"state": "FAILED", "error": message,
                                     "at": datetime.now().isoformat()})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--marketplace", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--control", required=True)
    args = ap.parse_args()
    control = Path(args.control)
    control.mkdir(parents=True, exist_ok=True)
    profile = Path(args.profile)
    save_flag = control / "save.flag"
    stop_flag = control / "stop.flag"
    for flag in (save_flag, stop_flag):
        flag.unlink(missing_ok=True)
    lock = ProfileLock(profile, run_id="managed-browser")
    try:
        lock.acquire()
    except Exception as exc:
        _fail(control, f"PROFILE_LOCKED: {exc}")
        return 3
    browser = None
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            _write(control / "status.json", {
                "state": "STARTING", "pid": os.getpid(),
                "marketplace": args.marketplace,
                "at": datetime.now().isoformat()})
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(profile), headless=False,
                args=["--start-maximized"])
            page = browser.pages[0] if browser.pages else browser.new_page()
            try:
                page.goto(session_store.HOME_URLS.get(args.marketplace, ""),
                          wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            _write(control / "status.json", {
                "state": "OPEN", "pid": os.getpid(),
                "marketplace": args.marketplace,
                "profile": str(profile),
                "at": datetime.now().isoformat()})
            while not stop_flag.exists():
                if save_flag.exists():
                    try:
                        raw = browser.cookies()
                        cookies = []
                        now = time.time()
                        for c in raw:
                            exp = c.get("expires")
                            if exp not in (None, -1) and float(exp) <= now:
                                continue
                            cookies.append({
                                "name": c.get("name"),
                                "value": c.get("value"),
                                "domain": c.get("domain"),
                                "path": c.get("path") or "/",
                                "secure": bool(c.get("secure")),
                                "httpOnly": bool(c.get("httpOnly")),
                                "sameSite": c.get("sameSite"),
                                **({"expires": exp} if exp not in (None, -1) else {}),
                            })
                        path = session_store.session_path(args.marketplace)
                        payload = {"marketplace": args.marketplace,
                                   "updated_at": datetime.now().isoformat(),
                                   "cookies": cookies,
                                   "source": "MANAGED_BROWSER"}
                        _write(path, payload)
                        _write(control / "saved.json", {
                            "count": len(cookies),
                            "at": payload["updated_at"]})
                    except Exception as exc:
                        _write(control / "save_error.json", {
                            "error": f"{type(exc).__name__}: {exc}",
                            "at": datetime.now().isoformat()})
                    finally:
                        save_flag.unlink(missing_ok=True)
                time.sleep(0.35)
    except Exception as exc:
        _fail(control, f"BROWSER_LAUNCH_FAILED: {type(exc).__name__}: {exc}")
        return 4
    finally:
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        lock.release()
    _write(control / "status.json", {"state": "CLOSED",
                                     "at": datetime.now().isoformat()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
