"""MRI-layer session supervision inspired by the VA's proven tactics.

The frozen marketplace scrapers stay untouched. MRI adds:
- storefront warmup before category work;
- challenge detection from the live page;
- controlled browser restart + cookie re-injection;
- explicit telemetry for every recovery.
No CAPTCHA solving and no silent retry loops.
"""
from __future__ import annotations

import random
from datetime import datetime

_HOME = {
    "Ripley": "https://simple.ripley.cl",
    "Mercado Libre": "https://www.mercadolibre.cl",
}
_CHALLENGE_MARKERS = (
    "verify you are human", "verifica que eres un ser humano",
    "cloudflare", "turnstile", "captcha", "suspicious traffic",
    "account-verification", "access denied", "blocked",
)


async def detect_challenge(page) -> str | None:
    if page is None:
        return None
    try:
        url = str(page.url or "").lower()
        if any(x in url for x in ("/login", "/jwz/", "account-verification")):
            return f"URL_CHALLENGE:{url[:120]}"
        body = (await page.inner_text("body", timeout=5000)).lower()
        for marker in _CHALLENGE_MARKERS:
            if marker in body:
                return marker
    except Exception:
        return None
    return None


async def warmup_page(page, marketplace: str) -> bool:
    """Short human-like homepage visit; best effort, never fatal."""
    home = _HOME.get(marketplace)
    if page is None or not home:
        return False
    try:
        await page.goto(home, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(1200, 2200))
        try:
            await page.mouse.move(random.randint(80, 500), random.randint(120, 500))
            await page.mouse.wheel(0, random.randint(200, 600))
        except Exception:
            pass
        await page.wait_for_timeout(random.randint(600, 1200))
        return True
    except Exception:
        return False


async def recover_session(scraper, marketplace: str, state: dict, inject_session) -> bool:
    """Stop/restart the managed browser, re-inject cookies and warm up once."""
    if scraper is None:
        return False
    started = False
    try:
        await scraper.stop()
    except Exception:
        pass
    try:
        await scraper.start()
        started = True
    except Exception as exc:
        state.setdefault("errors", []).append({
            "stage": "sesion", "error": f"SESSION_RESTART_FAILED: {exc}",
            "at": datetime.now().isoformat()})
        return False
    try:
        await inject_session(scraper, marketplace, state)
    except Exception:
        pass
    try:
        await warmup_page(getattr(scraper, "page", None), marketplace)
    except Exception:
        pass
    state.setdefault("session_recoveries", []).append({
        "marketplace": marketplace, "started": started,
        "at": datetime.now().isoformat()})
    return started
