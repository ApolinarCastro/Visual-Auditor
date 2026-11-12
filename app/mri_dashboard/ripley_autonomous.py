"""Ripley autonomous acquisition helpers (verified 2026-10-26).

Rules learned from live evidence:
- HTTP/curl/sitemap -> Cloudflare 403; browser session is the only channel.
- Search surface: /search/nicopoly?brand=NICOPOLY&page=N (48 cards/page).
- Category membership comes from listing membership, NEVER from breadcrumb
  (breadcrumb is always "Moda Mujer > Marcas Casuales > Nicopoly").
- A page may render empty before hydration: retry 2 times (15-20 s) before
  declaring end-of-pagination.
- Counters are NOT additive: a SKU can belong to 2+ categories.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import re
from dataclasses import dataclass, field

PRODUCT_SECTION_RE = re.compile(
    r"<section[^>]*data-testid=[\"']product-list[\"'][^>]*>(.*?)</section>",
    re.I | re.S)
SKU_RE = re.compile(r"mpm(\d{11})", re.I)
HREF_RE = re.compile(r"href=[\"']([^\"']*?mpm\d{11}[^\"']*)[\"']", re.I)
NAME_RE = re.compile(r"(?:title|aria-label)=[\"']([^\"']{4,200})[\"']", re.I)
PRICE_RE = re.compile(r"(?:data-price|price)[\"']?\s*[:=]\s*[\"']?(\d{3,9})", re.I)
BLOCK_MARKERS = ('cloudflarePage:"Blocked"', "cloudflarePage:'Blocked'",
                 "<title>Blocked</title>", "cf-ray")


class SourceBlocked(RuntimeError):
    pass


def is_blocked(html: str, status: int | None = None) -> bool:
    if status == 403:
        return True
    text = html or ""
    if any(m in text for m in BLOCK_MARKERS):
        return True
    return "Blocked" in text[:2000] and "cloudflare" in text.lower()


@dataclass
class Card:
    sku: str
    url: str
    name: str = ""
    price: int | None = None


def extract_cards(html: str, base_url: str = "https://simple.ripley.cl") -> list[Card]:
    """Extract ONLY the product results grid (excludes carousels/sections)."""
    if is_blocked(html):
        raise SourceBlocked("Cloudflare challenge detectado; no es catálogo")
    m = PRODUCT_SECTION_RE.search(html or "")
    if not m:
        return []
    section = m.group(1)
    cards: list[Card] = []
    seen = set()
    # Each card/block is separated by data-testid or article; anchors are enough.
    blocks = re.split(r"(?=<(?:article|div)[^>]*data-testid=[\"'](?:product|pod)[^\"']*[\"'])",
                      section, flags=re.I)
    for block in blocks or [section]:
        href = HREF_RE.search(block)
        if not href:
            continue
        sku = "MPM" + SKU_RE.search(href.group(1)).group(1)
        if sku.upper() in seen:
            continue
        seen.add(sku.upper())
        name_m = NAME_RE.search(block)
        price_m = PRICE_RE.search(block)
        url = href.group(1)
        if url.startswith("/"):
            url = base_url + url
        cards.append(Card(sku=sku.upper(), url=url,
                          name=html_lib.unescape(name_m.group(1)) if name_m else "",
                          price=int(price_m.group(1)) if price_m else None))
    return cards


def extract_category_links(html: str, base_url: str = "https://simple.ripley.cl") -> list[str]:
    """Discover category URLs from the brand/search page (lvl1/lvl2 surfaces)."""
    found = []
    for href in re.findall(r"href=[\"']([^\"']+)[\"']", html or ""):
        low = href.lower()
        if "simple.ripley.cl" in low or low.startswith("/"):
            if any(k in low for k in ("/moda-mujer/", "/moda-infantil/",
                                      "/accesorios", "categories.lvl")):
                url = base_url + href if href.startswith("/") else href
                if url not in found:
                    found.append(url)
    return found


def merge_categories(cards_by_category: dict[str, list[Card]]) -> dict:
    """N:N product-category model; never sum category counters."""
    memberships: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    urls: dict[str, str] = {}
    for category, cards in cards_by_category.items():
        for card in cards:
            memberships.setdefault(card.sku, set()).add(category)
            names.setdefault(card.sku, card.name)
            urls.setdefault(card.sku, card.url)
    duplicates = {sku: sorted(cats) for sku, cats in memberships.items() if len(cats) > 1}
    return {"memberships": {k: sorted(v) for k, v in memberships.items()},
            "names": names, "urls": urls, "duplicates": duplicates,
            "unique_products": len(memberships)}


def reconcile_category(category: str, site_count: int | None, extracted: int) -> dict:
    if site_count is None:
        return {"category": category, "site_count": None, "extracted": extracted,
                "status": "UNVERIFIED", "difference": None}
    diff = site_count - extracted
    status = "COMPLETE" if abs(diff) <= 1 else "PARTIAL_OR_BLOCKED"
    return {"category": category, "site_count": site_count, "extracted": extracted,
            "difference": diff, "status": status,
            "reason": ("diferencia dentro de tolerancia (tarjeta duplicada)"
                       if status == "COMPLETE" else
                       "extraídos != contador: posible hidratación o bloqueo")}


@dataclass
class ScanResult:
    category: str
    cards: list[Card] = field(default_factory=list)
    pages: int = 0
    blocked: bool = False
    empty_retries: int = 0


async def scan_category(fetch_page, url_template: str, category: str, *,
                        page_size: int = 48, max_pages: int = 60,
                        empty_retries: int = 2, wait_seconds: int = 15,
                        sleep=asyncio.sleep) -> ScanResult:
    """Paginate a Ripley category; retries transient empty pages before stopping."""
    result = ScanResult(category=category)
    empty_streak = 0
    for page in range(1, max_pages + 1):
        url = url_template.format(page=page)
        try:
            html = await fetch_page(url)
        except Exception:
            result.blocked = True
            break
        if is_blocked(html):
            result.blocked = True
            break
        cards = extract_cards(html)
        result.pages = page
        if cards:
            result.cards.extend(cards)
            empty_streak = 0
            if len(cards) < page_size:
                break
            continue
        if empty_streak < empty_retries:
            empty_streak += 1
            result.empty_retries += 1
            await sleep(wait_seconds)
            continue
        break
    return result
