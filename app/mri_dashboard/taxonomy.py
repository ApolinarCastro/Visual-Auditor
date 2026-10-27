"""
Marketplace taxonomy discovery for MRI full audits (MRI-CATEGORY-COVERAGE-002).

Layer: MRI only. It reuses the EXISTING engines (no new scraper, no browser of
its own, frozen VA scrapers untouched):
  * Ripley   -> app.mri_autonomous.category_discoverer.discover_categories_from_page
                (uses the already-open Playwright page of the Ripley scraper)
  * Falabella -> app.mri_autonomous.falabella_ssr_engine
                (SSR payload + extract_taxonomy_tree)
  * Mercado Libre -> app.mri_autonomous.meli_taxonomy_engine (official API helpers)

Contract: a marketplace is only TAXONOMY_DISCOVERED with at least one real
category carrying id/name/url. Anything else is UNAVAILABLE/BLOCKED with a
cause; the caller must keep such a marketplace as pending (AUDIT_FAIL), never
AUDIT_PASS. A brand search remains complementary, never a substitute.
"""
from __future__ import annotations

from app.mri_dashboard.acquisition_contract import classify_commercial_identity

DISCOVERED = "TAXONOMY_DISCOVERED"
UNAVAILABLE = "TAXONOMY_UNAVAILABLE"
BLOCKED = "TAXONOMY_BLOCKED"
NOT_REQUIRED = "TAXONOMY_NOT_REQUIRED"
def _cat(cid, name, url, parent=None, level=1, source=None, count=None):
    return {
        "category_id": str(cid) if cid is not None else None,
        "name": name,
        "url": url,
        "parent_id": str(parent) if parent is not None else None,
        "level": level,
        "source": source,
        "reported_count": count,
        "commercial_relevance": "BRAND_CORRIDOR" if name and any(
            t in str(name).lower() for t in ("nicopoly", "tienda", "marca")) else "DEPARTMENT",
    }


def _result(marketplace, status, categories, source, notes=None, *,
            complete=False, coverage_scope=None, pending_scope=None):
    return {
        "marketplace": marketplace,
        "status": status,
        "source": source,
        "categories": categories,
        "notes": notes or [],
        "brand_search_is_complementary": True,
        # DISCOVERED != COMPLETE. Only explicit exhaustive evidence may set True.
        "taxonomy_complete": bool(complete),
        "coverage_scope": coverage_scope or (
            "EXHAUSTIVE" if complete else "DISCOVERED_NOT_EXHAUSTIVELY_VERIFIED"),
        "pending_scope": pending_scope or [],
    }


def ripely_taxonomy(scraper, hub_url, brand="Nicopoly"):
    """Sync convenience wrapper (tests / no-running-loop callers)."""
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(ripely_taxonomy_async(scraper, hub_url, brand))
    return _result("Ripley", UNAVAILABLE, [], "PLAYWRIGHT_PAGE",
                   ["use discover_taxonomy_async inside a running event loop"])


async def ripely_taxonomy_async(scraper, hub_url, brand="Nicopoly"):
    """Discover Ripley categories from the page the scraper already opened.

    `discover_categories_from_page` is a coroutine: it MUST be awaited. Calling
    it synchronously returned a coroutine, which was then iterated -> no
    categories and a misleading TAXONOMY_UNAVAILABLE (root cause 2026-10-26).
    """
    import inspect
    from app.mri_autonomous.category_discoverer import discover_categories_from_page
    page = getattr(scraper, "page", None)
    if page is None:
        return _result("Ripley", BLOCKED, [], "PLAYWRIGHT_PAGE",
                       ["el scraper no expone una página abierta"])
    try:
        urls = discover_categories_from_page(page, "Ripley", hub_url, brand)
        if inspect.isawaitable(urls):
            urls = await urls
    except Exception as exc:
        return _result("Ripley", UNAVAILABLE, [], "PLAYWRIGHT_PAGE",
                       [f"{type(exc).__name__}: {exc}"])
    # The frozen discoverer only recognizes brand-bearing facet anchors; the
    # live Ripley menu/search page exposes category links without the brand in
    # the href. Probe them before accepting the static partial fallback.
    if not urls:
        try:
            from app.mri_autonomous.ripley_discovery import discover_live_categories
            _diag = []
            _prior = []
            try:
                from app.mri_dashboard.ripley_query_experience import read_query_experience
                from app.mri_autonomous.storage_guard import StorageConfig
                _rows = read_query_experience(StorageConfig.get_aux_dir())
                _prior = [r.get("url") for r in _rows if r.get("products")]
            except Exception:
                _prior = []
            urls = await discover_live_categories(
                page, hub_url, brand, scraper=scraper, diagnostics=_diag,
                prior_urls=_prior)
            if not urls:
                # Keep the diagnostic in the taxonomy result, never invent 7.
                _discovery_diag = _diag
        except Exception:
            urls = []
    cats, seen = [], set()
    for u in urls or []:
        if not isinstance(u, str) or not u.startswith("http") or u in seen:
            continue
        seen.add(u)
        slug = u.rstrip("/").split("/")[-1].split("?")[0]
        cats.append(_cat(slug, slug.replace("-", " ").title(), u, source="NAVIGATION"))
    if not cats:
        # NEVER substitute a static 7-category list. If the live site does not
        # expose categories, this is a discovery gap, not a partial taxonomy.
        _note = "la página no expuso categorías comerciales navegables"
        try:
            _note += f" | diagnostico={_discovery_diag[:6]}"
        except Exception:
            pass
        return _result("Ripley", UNAVAILABLE, [], "LIVE_DISCOVERY",
                       [_note],
                       complete=False, coverage_scope="NO_CATEGORIES_DISCOVERED",
                       pending_scope=["COMMERCIAL_TAXONOMY_UNRESOLVED"])
    return _result("Ripley", DISCOVERED, cats, "NAVIGATION")


async def discover_taxonomy_async(marketplace, *, scraper=None, hub_url=None,
                                  brand="Nicopoly"):
    """Async-safe taxonomy discovery for the MRI runner.

    - Ripley: awaits the Playwright-based discovery on the MAIN event loop
      (Playwright objects are loop-bound; they cannot be moved to a thread).
    - Falabella/Mercado Libre: blocking HTTP/API calls are moved OFF the event
      loop so the dashboard and /api/state keep responding during discovery.
    - Paris: untouched baseline.
    """
    import asyncio
    try:
        if marketplace == "Paris":
            return _result("Paris", NOT_REQUIRED, [], "PARIS_VALIDATED_BASELINE")
        if marketplace == "Ripley":
            return await ripely_taxonomy_async(
                scraper, hub_url or f"https://simple.ripley.cl/search/{brand.lower()}",
                brand)
        return await asyncio.to_thread(
            discover_taxonomy, marketplace, scraper=scraper, hub_url=hub_url,
            brand=brand)
    except Exception as exc:
        return _result(marketplace, UNAVAILABLE, [], "UNKNOWN",
                       [f"{type(exc).__name__}: {exc}"])


def falabella_taxonomy(brand="Nicopoly"):
    """Discover Falabella taxonomy from the SSR payload already fetchable."""
    from app.mri_autonomous.falabella_ssr_engine import FalabellaSSREngine
    try:
        engine = FalabellaSSREngine()
        payload = engine.get_brand_catalog(brand_name=brand, page=1)
        nodes = engine.extract_taxonomy_tree(payload) or []
    except Exception as exc:
        return _result("Falabella", BLOCKED, [], "SSR_NEXT_DATA",
                       [f"{type(exc).__name__}: {exc}"])
    cats, seen = [], set()
    for n in nodes:
        cid = getattr(n, "category_id", None)
        if cid is None or str(cid) in seen:
            continue
        seen.add(str(cid))
        cats.append(_cat(cid, getattr(n, "name", None),
                         getattr(n, "canonical_url", None),
                         parent=getattr(n, "parent_id", None),
                         level=getattr(n, "level", 1),
                         source="SSR_NEXT_DATA",
                         count=getattr(n, "reported_count", None)))
    if not cats:
        return _result("Falabella", UNAVAILABLE, [], "SSR_NEXT_DATA",
                       ["el payload SSR no expuso taxonomía"])
    return _result("Falabella", DISCOVERED, cats, "SSR_NEXT_DATA")


def meli_taxonomy(query="nicopoly"):
    """Discover Mercado Libre taxonomy through its official API helpers.

    The official domain_discovery payload uses keys like `domain_id`,
    `domain_name`, `category_id`, `category_name`; the previous parser only
    accepted `category_id`/`name`, so a FOUND response was reported as
    TAXONOMY_UNAVAILABLE with cause "FOUND" (misleading, zero pages).
    """
    from app.mri_autonomous.meli_taxonomy_engine import MeliTaxonomyEngine
    try:
        engine = MeliTaxonomyEngine()
        nodes, err = engine.discover_category_by_domain(query)
    except Exception as exc:
        return _result("Mercado Libre", BLOCKED, [], "OFFICIAL_API",
                       [f"{type(exc).__name__}: {exc}"])
    cats, seen, raw_keys = [], set(), set()
    for n in nodes or []:
        if not isinstance(n, dict):
            n = {"category_id": getattr(n, "category_id", None),
                 "name": getattr(n, "name", None)}
        raw_keys.update(str(k) for k in n.keys())
        cid = (n.get("category_id") or n.get("domain_id")
               or n.get("categoryId") or n.get("id"))
        if cid is None or str(cid) in seen:
            continue
        seen.add(str(cid))
        name = (n.get("category_name") or n.get("domain_name")
                or n.get("name") or n.get("domain"))
        path = n.get("path_from_root") or n.get("category_path")
        if isinstance(path, (list, tuple)) and path:
            last = path[-1]
            last_name = last.get("name") if isinstance(last, dict) else str(last)
            url = ("https://listado.mercadolibre.cl/"
                   + str(last_name).replace(" ", "-").lower())
        else:
            slug = str(name or cid).replace(" ", "-").lower()
            url = f"https://listado.mercadolibre.cl/{slug}"
        cats.append(_cat(cid, name, url, source="OFFICIAL_API"))
    if not cats:
        # Never call this WAF: it is an official-API contract/parse issue.
        cause = (f"{err}: no parseable categories (keys={sorted(raw_keys)[:10]})"
                 if err == "FOUND" else (err or "sin respuesta util"))
        return _result("Mercado Libre", UNAVAILABLE, [], "OFFICIAL_API", [cause])
    return _result("Mercado Libre", DISCOVERED, cats, "OFFICIAL_API")


def discover_taxonomy(marketplace, *, scraper=None, hub_url=None, brand="Nicopoly"):
    """Marketplace-specific plan; returns a contract dict (never raises)."""
    try:
        if marketplace == "Paris":
            # Paris keeps its validated route untouched.
            return _result("Paris", NOT_REQUIRED, [], "PARIS_VALIDATED_BASELINE")
        if marketplace == "Ripley":
            return ripely_taxonomy(scraper, hub_url or f"https://simple.ripley.cl/search/{brand.lower()}", brand)
        if marketplace == "Falabella":
            return falabella_taxonomy(brand)
        if marketplace == "Mercado Libre":
            return meli_taxonomy(brand.lower())
    except Exception as exc:                     # never abort the audit
        return _result(marketplace, UNAVAILABLE, [], "UNKNOWN",
                       [f"{type(exc).__name__}: {exc}"])
    return _result(marketplace, NOT_REQUIRED, [], "UNKNOWN")


def summarize(taxonomy_map: dict) -> dict:
    """Coverage-facing summary of taxonomy discovery."""
    out = {"marketplaces": taxonomy_map,
           "discovered": [], "unavailable": [], "pending": [],
           "not_required": []}
    for mkt, res in (taxonomy_map or {}).items():
        status = (res or {}).get("status")
        if status == DISCOVERED:
            out["discovered"].append({"marketplace": mkt,
                                      "categories": len(res.get("categories") or []),
                                      "taxonomy_complete": bool(res.get("taxonomy_complete"))})
        elif status == NOT_REQUIRED:
            out["not_required"].append(mkt)
        elif status == BLOCKED:
            out["pending"].append(mkt)
        else:
            out["unavailable"].append(mkt)
    # A run whose requested scope has no taxonomy requirement (e.g. Paris
    # baseline) is complete; any pending/unavailable marketplace is not.
    out["complete_scope"] = (not out["unavailable"] and not out["pending"]
                             and bool(out["discovered"])
                             and all(d.get("taxonomy_complete") for d in out["discovered"]))
    return out


__all__ = ["discover_taxonomy", "summarize", "DISCOVERED",
           "UNAVAILABLE", "BLOCKED", "NOT_REQUIRED", "classify_commercial_identity"]
