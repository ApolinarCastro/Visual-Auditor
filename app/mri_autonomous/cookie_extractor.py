"""Automatic Chrome cookie extraction for MRI (no Playwright)."""
from __future__ import annotations

import glob
import os
import shutil
import tempfile
from typing import Dict, List, Tuple


def _temp_dir() -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "data", "runtime_tmp", "cookie_extract")
    os.makedirs(base, exist_ok=True)
    # pywin32 gencache needs a writable TEMP; the system temp may be restricted.
    os.environ["TEMP"] = base
    os.environ["TMP"] = base
    return base


def _chrome_cookie_files() -> List[str]:
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "Google", "Chrome", "User Data")
    files = glob.glob(os.path.join(base, "*", "Network", "Cookies"))
    files += glob.glob(os.path.join(base, "*", "Cookies"))
    return sorted(set(os.path.abspath(f) for f in files if os.path.exists(f)))


def get_meli_cookies(domain: str = ".mercadolibre.cl") -> Dict[str, str]:
    """Read ML cookies from Coffee/Chrome profiles via browser_cookie3.

    Handles a locked Chrome database by copying it to a workspace temp file.
    Returns {} (with no fabricated values) when Chrome is open and unreadable.
    """
    _temp_dir()
    try:
        import browser_cookie3
    except Exception:
        return {}
    candidates: List[Tuple[str, str]] = []
    files = _chrome_cookie_files()
    for src in files:
        dst = os.path.join(_temp_dir(), "Cookies_" + str(abs(hash(src))))
        try:
            shutil.copy2(src, dst)
            candidates.append((src, dst))
        except Exception:
            # Chrome may hold an exclusive lock; try the original path (works
            # when Chrome is closed, or browser_cookie3 can use its own copy).
            candidates.append((src, src))
    # Also try browser_cookie3's default profile discovery.
    candidates.insert(0, ("default", ""))
    for label, path in candidates:
        try:
            if path:
                jar = browser_cookie3.chrome(cookie_file=path, domain_name=domain)
            else:
                jar = browser_cookie3.chrome(domain_name=domain)
            out = {c.name: c.value for c in jar}
            if out:
                return out
        except Exception:
            continue
    return {}


def get_meli_cookie_status() -> Dict[str, object]:
    cookies = get_meli_cookies()
    return {
        "marketplace": "mercadolibre",
        "status": "IMPORTED" if cookies else "NO_COOKIES",
        "count": len(cookies),
        "cookies": sorted(cookies.keys()),
        "source": "chrome_profile",
    }
