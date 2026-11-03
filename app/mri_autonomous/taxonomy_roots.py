"""Root taxonomy adapters for MRI.

These adapters start from marketplace roots, not from brand-search result sets.
They only normalize evidence produced by existing engines; they do not add a
new crawler or bypass access controls.

Network calls are injectable for deterministic tests. When no root source is
available the result is explicit (FAIL/PARTIAL), never a fabricated tree.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import urlparse


@dataclass
class RootTaxonomyResult:
    marketplace: str
    status: str
    source: str
    categories: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    roots_discovered: int = 0
    nodes_discovered: int = 0
    frontier_pending: int = 0

    def as_taxonomy_result(self) -> dict[str, Any]:
        return {
            "marketplace": self.marketplace,
            "status": "TAXONOMY_DISCOVERED" if self.categories else "TAXONOMY_UNAVAILABLE",
            "source": self.source,
            "categories": self.categories,
            "notes": self.notes,
            "taxonomy_complete": False,
            "coverage_scope": "ROOT_DISCOVERED_NOT_EXHAUSTIVELY_VERIFIED",
            "pending_scope": ["ROOT_HIERARCHY_DEPTH_PENDING"] if self.categories else [],
        }


def _node(marketplace: str, cid: Any, name: Any, *, parent: Any = None,
          path: Optional[str] = None, url: Optional[str] = None,
          source: str = "ROOT_DISCOVERY", evidence: str = "",
          status: str = "NOT_VERIFIED") -> dict[str, Any]:
    cid_s = str(cid) if cid is not None else ""
    name_s = str(name or cid_s)
    return {
        "category_id": cid_s,
        "name": name_s,
        "url": url,
        "parent_id": str(parent) if parent not in (None, "") else None,
        "hierarchical_path": path or name_s,
        "source": source,
        "evidence": evidence,
        "discovery_status": status,
        "taxonomy_source": source,
    }


def _host_allowed(marketplace: str, url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if marketplace == "Ripley":
        return host == "simple.ripley.cl" or host.endswith(".ripley.cl")
    if marketplace == "Paris":
        return host == "www.paris.cl" or host == "paris.cl" or host.endswith(".paris.cl")
    if marketplace == "Falabella":
        return host.endswith("falabella.com") or host.endswith("falabella.cl")
    return True


def _url_nodes(marketplace: str, urls: Iterable[str], source: str) -> list[dict[str, Any]]:
    out, seen = [], set()
    for u in urls or []:
        if not isinstance(u, str) or not u.startswith("http") or u in seen:
            continue
        if not _host_allowed(marketplace, u):
            continue
        seen.add(u)
        cid = urlparse(u).path.rstrip("/").split("/")[-1] or u
        out.append(_node(marketplace, cid, cid.replace("-", " ").title(),
                         url=u, source=source, evidence=u, status="NOT_VERIFIED"))
    return out


def discover_meli_roots(engine: Any = None, *, max_nodes: int = 500) -> RootTaxonomyResult:
    """Discover ML hierarchy from the official site-categories API.

    The root list comes from /sites/{site}/categories; every child is expanded
    through the existing API helper. No category list is hardcoded here.
    """
    if engine is None:
        from app.mri_autonomous.meli_taxonomy_engine import MeliTaxonomyEngine
        engine = MeliTaxonomyEngine()
    site = getattr(engine, "site_id", "MLC")
    try:
        code, data, status = engine._request(f"/sites/{site}/categories")
    except Exception as exc:
        return RootTaxonomyResult("Mercado Libre", "FAIL", "OFFICIAL_CATEGORY_API",
                                  notes=[f"{type(exc).__name__}: {exc}"])
    if code != 200 or not isinstance(data, list):
        return RootTaxonomyResult("Mercado Libre", "FAIL", "OFFICIAL_CATEGORY_API",
                                  notes=[f"root API status={status}"])
    nodes: dict[str, dict[str, Any]] = {}
    roots = 0

    def walk(cid: str, parent: Optional[str], path: str) -> None:
        nonlocal roots
        if len(nodes) >= max_nodes or not cid or cid in nodes:
            return
        try:
            cat, _ = engine.get_category_by_id(cid)
        except Exception:
            cat = None
        if cat is None:
            return
        name = getattr(cat, "name", None) or cid
        full = f"{path} > {name}" if path else name
        nodes[cid] = _node("Mercado Libre", cid, name, parent=parent,
                           path=full, url=None, source="OFFICIAL_CATEGORY_API",
                           evidence=f"/sites/{site}/categories/{cid}")
        if parent is None:
            roots += 1
        for child in (getattr(cat, "children", None) or []):
            ccid = child.get("id") if isinstance(child, dict) else None
            if ccid:
                walk(str(ccid), cid, full)

    for root in data:
        if isinstance(root, dict) and root.get("id"):
            walk(str(root["id"]), None, "")
    cats = list(nodes.values())
    return RootTaxonomyResult(
        "Mercado Libre", "PASS" if cats else "FAIL", "OFFICIAL_CATEGORY_API",
        cats, roots_discovered=roots, nodes_discovered=len(cats),
        frontier_pending=max(0, len(cats) - len({c["parent_id"] for c in cats if c.get("parent_id")})))


def discover_falabella_roots(engine: Any = None, *, payload: Any = None,
                             page_url: str = "/falabella-cl/") -> RootTaxonomyResult:
    """Discover Falabella roots from real commercial links in the SSR payload.

    `extract_taxonomy_tree` only understands facet data and can return an empty
    list even when the homepage SSR contains commercial category links. Those
    links are an independent root source; they are used first and their parents
    remain NULL because the homepage link does not prove a hierarchy.
    """
    if engine is None:
        from app.mri_autonomous.falabella_ssr_engine import FalabellaSSREngine
        engine = FalabellaSSREngine()
    try:
        if payload is None:
            payload = engine.fetch_page_ssr_data(page_url)
        linked = _falabella_links_from_payload(payload)
        raw = engine.extract_taxonomy_tree(payload) or [] if not linked else []
    except Exception as exc:
        return RootTaxonomyResult("Falabella", "FAIL", "SSR_ROOT_PAGE",
                                  notes=[f"{type(exc).__name__}: {exc}"])
    if linked:
        cats = [_node("Falabella", c["category_id"], c["name"],
                      parent=None, path=c["name"], url=c["url"],
                      source="SSR_ROOT_CATEGORY_LINKS",
                      evidence=c["url"], status="NOT_VERIFIED")
                for c in linked]
        return RootTaxonomyResult(
            "Falabella", "PASS", "SSR_ROOT_CATEGORY_LINKS", cats,
            roots_discovered=len(cats), nodes_discovered=len(cats),
            frontier_pending=len(cats))
    cats = []
    for n in raw:
        cid = getattr(n, "category_id", None)
        if cid is None:
            continue
        cats.append(_node(
            "Falabella", cid, getattr(n, "name", None),
            parent=getattr(n, "parent_id", None),
            path=getattr(n, "hierarchical_path", None) or getattr(n, "name", None),
            url=getattr(n, "canonical_url", None),
            source="SSR_ROOT_PAGE",
            evidence=f"{getattr(engine, 'base_url', '')}{page_url}",
        ))
    return RootTaxonomyResult(
        "Falabella", "PASS" if cats else "PARTIAL", "SSR_ROOT_PAGE", cats,
        notes=[] if cats else ["SSR root page exposed no taxonomy"],
        roots_discovered=sum(1 for c in cats if not c["parent_id"]),
        nodes_discovered=len(cats))


def _falabella_links_from_payload(payload: Any) -> list[dict[str, str]]:
    """Extract real /category/<id>/<slug> links from the SSR payload."""
    import json
    import re
    from urllib.parse import unquote
    try:
        blob = json.dumps(payload, ensure_ascii=False)
    except Exception:
        blob = str(payload)
    pat = re.compile(r"/falabella-cl/category/([A-Za-z0-9]+)/([^\"'?#\\\\]+)")
    found: dict[str, dict[str, str]] = {}
    for cid, slug in pat.findall(blob):
        name = unquote(slug).replace("-", " ").strip()
        key = str(cid)
        if key not in found:
            found[key] = {
                "category_id": key,
                "name": name,
                "url": f"https://www.falabella.com/falabella-cl/category/{cid}/{slug}",
            }
    return list(found.values())


def discover_ripley_roots_from_urls(urls: Iterable[str]) -> RootTaxonomyResult:
    cats = _url_nodes("Ripley", urls, "RIPLEY_ROOT_NAVIGATION")
    return RootTaxonomyResult("Ripley", "PASS" if cats else "FAIL",
                              "RIPLEY_ROOT_NAVIGATION", cats,
                              roots_discovered=len(cats), nodes_discovered=len(cats),
                              frontier_pending=len(cats))


def discover_paris_roots_from_urls(urls: Iterable[str]) -> RootTaxonomyResult:
    cats = _url_nodes("Paris", urls, "PARIS_MRI_ROOT_NAVIGATION")
    return RootTaxonomyResult("Paris", "PASS" if cats else "FAIL",
                              "PARIS_MRI_ROOT_NAVIGATION", cats,
                              roots_discovered=len(cats), nodes_discovered=len(cats),
                              frontier_pending=len(cats))


def persist_falabella_root_snapshot(conn: Any, run_id: str,
                                    engine: Any = None) -> tuple[RootTaxonomyResult, dict[str, int] | None]:
    """Execute the Falabella root route and persist it for integration tests.

    Production uses the same root result + taxonomy_store path through the
    runner; this helper keeps the test deterministic without a server.
    """
    result = discover_falabella_roots(engine)
    counts = None
    if result.categories:
        from app.mri_autonomous.taxonomy_store import persist_taxonomy_snapshot
        counts = persist_taxonomy_snapshot(
            conn, "Falabella", run_id, result.categories,
            taxonomy_source=result.source, source_evidence="root discovery")
    return result, counts


async def discover_ripley_roots_async(scraper: Any, hub_url: str) -> RootTaxonomyResult:
    page = getattr(scraper, "page", None)
    if page is None:
        return RootTaxonomyResult("Ripley", "FAIL", "RIPLEY_ROOT_NAVIGATION",
                                  notes=["scraper has no open page"])
    from app.mri_autonomous.category_discoverer import discover_categories_from_page
    try:
        urls = discover_categories_from_page(page, "Ripley", hub_url, "")
        if inspect.isawaitable(urls):
            urls = await urls
    except Exception as exc:
        return RootTaxonomyResult("Ripley", "FAIL", "RIPLEY_ROOT_NAVIGATION",
                                  notes=[f"{type(exc).__name__}: {exc}"])
    return discover_ripley_roots_from_urls(urls or [])


async def discover_paris_roots_async(scraper: Any, hub_url: str = "https://www.paris.cl/") -> RootTaxonomyResult:
    """Paris taxonomy discovery in MRI only; Legacy scraper is untouched."""
    page = getattr(scraper, "page", None)
    if page is None:
        return RootTaxonomyResult("Paris", "FAIL", "PARIS_MRI_ROOT_NAVIGATION",
                                  notes=["scraper has no open page"])
    from app.mri_autonomous.category_discoverer import discover_categories_from_page
    try:
        urls = discover_categories_from_page(page, "Paris", hub_url, "")
        if inspect.isawaitable(urls):
            urls = await urls
    except Exception as exc:
        return RootTaxonomyResult("Paris", "FAIL", "PARIS_MRI_ROOT_NAVIGATION",
                                  notes=[f"{type(exc).__name__}: {exc}"])
    return discover_paris_roots_from_urls(urls or [])


__all__ = [
    "RootTaxonomyResult", "discover_meli_roots", "discover_falabella_roots",
    "discover_ripley_roots_from_urls", "discover_paris_roots_from_urls",
    "discover_ripley_roots_async", "discover_paris_roots_async",
    "persist_falabella_root_snapshot",
]
