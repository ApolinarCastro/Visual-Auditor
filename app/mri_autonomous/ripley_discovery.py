"""Live Ripley category discovery (MRI layer, no hardcoded result list).

The expected daily-review categories are validation targets, not production
input. This module reads the live page/menu/facet anchors and derives category
URLs structurally; it never returns a fixed answer list.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlparse, parse_qs, urlencode

BASE = "https://simple.ripley.cl"
PRODUCT_MARKERS = ("-mpm", "/p/", "/mp/", "/producto", "/product/")
NON_CATEGORY_MARKERS = ("/search", "/tienda/", "/marcas/", "/marca/", "/cuenta",
                        "/login", "/carrito", "/ayuda", "/seguimiento")
CATEGORY_PREFIXES = ("/moda-mujer", "/moda-infantil", "/moda-hombre",
                     "/accesorios", "/calzado")


def _clean_url(href: str) -> str | None:
    if not href:
        return None
    full = urljoin(BASE + "/", href)
    parsed = urlparse(full)
    if parsed.netloc and "ripley" not in parsed.netloc.lower():
        return None
    path = parsed.path.rstrip("/") or "/"
    low = path.lower()
    if any(m in low for m in PRODUCT_MARKERS):
        return None
    if any(m in low for m in NON_CATEGORY_MARKERS):
        return None
    if not any(low.startswith(p) for p in CATEGORY_PREFIXES):
        # category facet links may be query-only; accept categories.lvl*
        if not any(k.startswith("categories.lvl") for k in parse_qs(parsed.query)):
            return None
    # Give every category URL the brand filter and page placeholder.
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["brand"] = ["NICOPOLY"]
    qs["page"] = ["{page}"]
    query = urlencode(qs, doseq=True).replace("%7Bpage%7D", "{page}")
    return parsed._replace(query=query).geturl()


def _raw_urls(anchors: list[dict]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for item in anchors or []:
        href = item.get("href") if isinstance(item, dict) else None
        cleaned = _clean_url(href)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        urls.append(cleaned)
    return urls


def _leaf_urls(urls: list[str]) -> list[str]:
    # Keep leaves, not their parent containers: a category URL that is a path
    # prefix of another discovered category is not a leaf target.
    paths = {u: urlparse(u).path.rstrip("/") for u in urls}
    leaves = [u for u, p in paths.items()
              if not any(o != u and op.startswith(p + "/") for o, op in paths.items())]
    return leaves or urls


def category_urls_from_anchors(anchors: list[dict], base: str = BASE) -> list[str]:
    return _leaf_urls(_raw_urls(anchors))


def _anchor_script() -> str:
    return """() => {
      const out = [];
      for (const a of document.querySelectorAll('a[href], [data-href], [data-url], button[onclick]')) {
        let href = a.href || a.getAttribute('href') || a.getAttribute('data-href') || a.getAttribute('data-url') || '';
        if (!href) {
          const oc = a.getAttribute('onclick') || '';
          const m = oc.match(/https?:[/]{2}[^'\"]+/);
          if (m) href = m[0];
        }
        const text = (a.innerText || a.textContent || '').trim();
        if (href) out.push({href, text});
      }
      return out.slice(0, 1500);
    }"""


async def _read_anchors(page) -> list[dict]:
    try:
        value = await page.evaluate(_anchor_script())
        return value if isinstance(value, list) else []
    except Exception:
        return []


async def _navigate_via_va(scraper, page, url: str) -> bool:
    """Use VA's Ripley navigator (challenge detection + session harvest)."""
    if scraper is not None:
        nav = getattr(scraper, "_navigate_ripley", None)
        if nav is not None:
            try:
                return bool(await nav(url))
            except Exception:
                return False
    try:
        await page.goto(url, wait_until="commit", timeout=60000)
        return True
    except Exception:
        return False


async def _restart_va(scraper) -> bool:
    """Restart the VA browser after a challenge closes the context."""
    if scraper is None:
        return False
    stop = getattr(scraper, "stop", None)
    start = getattr(scraper, "start", None)
    if stop is None or start is None:
        return False
    try:
        await stop()
    except Exception:
        pass
    try:
        import asyncio
        await asyncio.sleep(2)
        await start()
        return True
    except Exception:
        return False


async def _open_menu(page) -> None:
    """Expand the categories menu if it is collapsed (best effort)."""
    if not hasattr(page, "locator"):
        return
    selectors = (
        'button:has-text("Categorías")',
        'a:has-text("Categorías")',
        'button:has-text("Menú")',
        '[data-testid*="menu"] button',
    )
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count():
                await loc.click(timeout=3000)
                await page.wait_for_timeout(1200)
                return
        except Exception:
            continue


async def discover_live_categories(page, hub_url: str, brand: str = "NICOPOLY",
                                   navigate: bool = True, scraper=None,
                                   diagnostics: list | None = None,
                                   prior_urls: list[str] | None = None) -> list[str]:
    """Discover ALL visible Ripley category URLs, aggregating hubs/menus.

    The daily-review list is a validation sample, never a fixed answer. Every
    page that may expose a different slice of the menu/facets is visited and
    the union is pruned to leaf categories.
    """
    first_anchors = await _read_anchors(page)
    raw = _raw_urls(first_anchors)
    if diagnostics is not None:
        diagnostics.append({"url": hub_url, "current_page": True,
                            "anchors": len(first_anchors)})
    if not navigate:
        return _leaf_urls(raw)

    # Verified query experience goes first. This is learned runtime knowledge,
    # not a fixed category list; it only changes probe order.
    learned = []
    for _u in (prior_urls or []):
        if not _u:
            continue
        _u = str(_u).replace("&page={page}", "").replace("?page={page}", "")
        if _u.startswith("http") and _u not in learned:
            learned.append(_u)
    if diagnostics is not None and learned:
        diagnostics.append({"prior_urls": len(learned)})
    # Only the brand hub and the marketplace root are navigation seeds.
    # Categories must be derived from links/menu/facets on those live pages;
    # no hardcoded category URLs are acquisition inputs.
    candidates = learned + [hub_url, f"{BASE}/"]
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ok = await _navigate_via_va(scraper, page, candidate)
        if not ok:
            # VA strategy: a Cloudflare challenge may close the context. Restart
            # once and retry the hub before declaring discovery unavailable.
            restarted = await _restart_va(scraper)
            if diagnostics is not None:
                diagnostics.append({"url": candidate, "nav_ok": False,
                                    "restarted": restarted})
            if restarted:
                page = getattr(scraper, "page", page)
                ok = await _navigate_via_va(scraper, page, candidate)
        if not ok:
            if diagnostics is not None:
                diagnostics.append({"url": candidate, "nav_ok": False,
                                    "after_restart": False})
            continue
        await _open_menu(page)
        anchors = await _read_anchors(page)
        raw.extend(_raw_urls(anchors))
        if diagnostics is not None:
            diagnostics.append({"url": candidate, "nav_ok": True,
                                "anchors": len(anchors)})
    # dedupe preserving order, then keep the broadest leaf set
    dedup, seen_u = [], set()
    for u in raw:
        if u not in seen_u:
            seen_u.add(u)
            dedup.append(u)
    return _leaf_urls(dedup)
