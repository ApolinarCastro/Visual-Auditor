"""MRI anti-block policy + rotating Cloudflare sentinel (MRI layer only).

Does not modify frozen VA scrapers. It classifies evidence after acquisition
and enforces which channel each marketplace may use.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SKU_RE = re.compile(r"^MPM\d{11}$")
GENERIC_SKU_RE = re.compile(r"^[A-Za-z0-9_-]{4,}$")
PRODUCT_COUNT_KEYS = ("total_products", "product_count", "reported_products",
                      "products_total", "results_total")

# Safe, legal channel policy: the managed browser is a normal user session;
# HTTP is only used where it is the certified marketplace route (Falabella SSR).
CHANNEL_POLICY = {
    "Ripley": {
        "allowed_channels": ("browser",),
        "forbidden": ("http",),
        "headless": False,
        "reason": "HTTP directo 403 en 8/8 rutas; navegador persistente es el único canal.",
    },
    "Mercado Libre": {
        "allowed_channels": ("browser",),
        "forbidden": ("http",),
        "headless": False,
        "reason": "Akamai/WAF; requiere perfil persistente no-headless.",
    },
    "Falabella": {
        "allowed_channels": ("ssr_http",),
        "forbidden": ("browser",),
        "reason": "Navegador bloqueado; SSR __NEXT_DATA__ es el canal certificado.",
    },
    "Paris": {
        "allowed_channels": ("browser",),
        "forbidden": (),
        "reason": "Baseline validado; no modificar.",
    },
}

TITLE_PATTERNS = ("IUA", "Captcha Box", "Blocked", "Just a moment",
                  "Error en Ripley", "Attention Required")
BODY_PATTERNS = (
    r'cloudflarePage\s*:\s*"[^"]+"',
    r"Im Under Attack",
    r"Captcha Box",
    r"cf-error-details",
    r"Just a moment\.\.\.",
    r"comprobando tu navegador",
)
BLOCK_SIZE_KB = (110, 180)
SERVER_MARKERS = ("cloudflare",)
CLOSED_MARKERS = (
    "target page, context or browser has been closed",
    "targetclosed", "browser has been closed", "context or browser has been closed",
)


@dataclass
class BlockDecision:
    classification: str
    signals: list[str] = field(default_factory=list)
    cause: str = ""

    @property
    def blocked(self) -> bool:
        return self.classification == "BLOCKED"


def _title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "",
                  re.I | re.S)
    return m.group(1).strip() if m else ""


def classify_response(*, http_status: int, body: str,
                      headers: dict | None = None,
                      error: str | None = None) -> BlockDecision:
    """Classify REAL / BLOCKED / ERROR with rotating Cloudflare signatures."""
    headers = headers or {}
    if error:
        low = str(error).lower()
        if any(m in low for m in CLOSED_MARKERS):
            return BlockDecision("BROWSER_CLOSED", ["browser_closed"], str(error)[:200])
        return BlockDecision("ERROR", [], str(error)[:200])

    signals: list[str] = []
    title = _title(body or "")
    if any(p.lower() in title.lower() for p in TITLE_PATTERNS):
        signals.append("title_pattern")
    if any(re.search(p, body or "", re.I) for p in BODY_PATTERNS):
        signals.append("body_pattern")
    size_kb = len((body or "").encode("utf-8")) / 1024
    if BLOCK_SIZE_KB[0] <= size_kb <= BLOCK_SIZE_KB[1]:
        signals.append("size_range_kb")
    server = str(headers.get("server") or headers.get("Server") or "").lower()
    if any(m in server for m in SERVER_MARKERS):
        signals.append("server_header")

    if len(signals) >= 2:
        return BlockDecision("BLOCKED", signals, "firma Cloudflare (2+ señales)")
    if http_status >= 400:
        return BlockDecision("ERROR", signals, f"HTTP {http_status} sin firma")
    return BlockDecision("REAL", signals, "contenido real")


def classify_scraper_failure(result: dict) -> str | None:
    """Map a scraper result to BLOCKED / BROWSER_CLOSED without parsing it."""
    failure = str((result or {}).get("failure_type") or "").lower()
    stop = str((result or {}).get("stop_reason") or "").upper()
    text = f"{failure} {stop}".lower()
    if any(m in text for m in CLOSED_MARKERS):
        return "BROWSER_CLOSED"
    if any(m in text for m in ("blocked", "challenge", "captcha", "cloudflare",
                               "turnstile", "iua", "im under attack")):
        return "BLOCKED"
    if stop in ("BLOCKED", "SOURCE_BLOCKED"):
        return "BLOCKED"
    return None


def valid_sku(value) -> bool:
    r"""True only for the MPM namespace (^MPM\d{11}$)."""
    return bool(value and SKU_RE.match(str(value).upper().strip()))


def classify_sku(value) -> str:
    """Classify observed ID without rejecting valid numeric Ripley IDs.

    Ripley cards expose MPM part numbers and numeric product/variant IDs.
    G4 must reject malformed MPM values, but a numeric ID is a valid identity.
    """
    text = str(value or "").strip().upper()
    if not text:
        return "EMPTY"
    if text.startswith("MPM"):
        return "VALID" if SKU_RE.match(text) else "INVALID_MPM"
    return "VALID" if GENERIC_SKU_RE.match(text) else "INVALID"


def reported_product_count(pagination: dict | None) -> int | None:
    """Product counter only from explicit product-count keys.

    `total_declared` in the Ripley pager is the number of PAGES, not products.
    Never use it as a product count (this caused the 6-vs-265 false gate).
    """
    if not isinstance(pagination, dict):
        return None
    for key in PRODUCT_COUNT_KEYS:
        value = pagination.get(key)
        if value not in (None, "", 0):
            try:
                n = int(value)
                if n > 0:
                    return n
            except (TypeError, ValueError):
                continue
    return None


def policy_for(marketplace: str) -> dict:
    return CHANNEL_POLICY.get(marketplace, {"allowed_channels": (), "forbidden": (),
                                             "reason": "sin política declarada"})


def assert_channel(marketplace: str, channel: str) -> None:
    pol = policy_for(marketplace)
    allowed = pol.get("allowed_channels") or ()
    if allowed and channel not in allowed:
        raise ValueError(
            f"CHANNEL_NOT_ALLOWED[{marketplace}]: {channel}; permitidos={allowed}. "
            f"{pol.get('reason', '')}")
