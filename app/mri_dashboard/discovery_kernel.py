"""Generic marketplace discovery kernel for MRI.

Runtime contract:
- Input: marketplace + brand (+ optional known store URL).
- Discover surfaces and category routes from the marketplace itself.
- Never start from a fixed category list or a copied route.
- Persist what was learned; validation is a continuously updated snapshot.

Marketplace-specific details live in adapters, not in the orchestrator.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from app.mri_dashboard.discovery_graph import (
    learned_categories, mark_hit, merge_discovered)

_CATEGORY_ALIASES = {
    # Operator-confirmed mapping (2026-10-29): ML's Ropa Interior y de Dormir
    # contains the store's Body products and must be reported as Body.
    "ropa interior y de dormir": "Body",
}

_STORE_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36")
_MEMORY = Path(__file__).resolve().parents[2] / "knowledge" / "discovery_memory.json"


@dataclass
class DiscoveryTarget:
    marketplace: str
    brand: str
    store_url: str | None = None


@dataclass
class DiscoveryResult:
    target: DiscoveryTarget
    store_url: str | None
    categories: list[dict] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)
    validation: dict = field(default_factory=dict)
    state: str = "DISCOVERED"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def _canonical_category_name(value: str) -> str:
    name = str(value or "").strip()
    return _CATEGORY_ALIASES.get(name.lower(), name)


def _memory() -> dict:
    try:
        data = json.loads(_MEMORY.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_memory(data: dict) -> None:
    try:
        _MEMORY.parent.mkdir(parents=True, exist_ok=True)
        _MEMORY.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    except Exception:
        pass


class MeliAdapter:
    """Mercado Libre adapter; no brand/category constants."""

    SITE_RE = re.compile(r"mercadolibre\.(cl|com\.ar|com\.mx|com\.br|com\.co|com\.uy|com\.pe|com\.ec)")
    LISTING_RE = re.compile(r"/tienda/([^/]+)/listado/([^\"'?#<> ]+)")

    def __init__(self):
        self.root_category = "MLC1430"  # public API: Vestuario y Calzado

    def resolve_store(self, target: DiscoveryTarget) -> str | None:
        if target.store_url:
            return target.store_url.rstrip("/")
        slug = _slug(target.brand)
        if not slug:
            return None
        return f"https://www.mercadolibre.cl/tienda/{slug}"

    def fetch(self, url: str, timeout: int = 15) -> tuple[str, str]:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": _STORE_UA, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read().decode("utf-8", errors="replace"), str(res.status)
        except Exception as exc:
            return "", f"FETCH_FAILED:{type(exc).__name__}"

    def api_category(self, category_id: str, timeout: int = 8) -> dict:
        req = urllib.request.Request(
            f"https://api.mercadolibre.com/categories/{category_id}",
            headers={"User-Agent": "MRI/2.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8", errors="replace"))

    def parse_categories(self, html: str, store_url: str) -> list[dict]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "lxml")
        found: dict[str, dict] = {}

        def _path_key(url: str) -> str:
            return urlparse(url).path.rstrip("/").lower()
        for a in soup.select("a[href]"):
            href = str(a.get("href") or "")
            m = self.LISTING_RE.search(href)
            if not m:
                continue
            path = m.group(2).split("#")[0].strip("/")
            label = a.get_text(" ", strip=True)
            url = href.split("#")[0].split("?")[0]
            key = _path_key(url)
            found[key] = {
                "name": label or path.split("/")[-1].replace("-", " ").title(),
                "url": url,
                "path": path,
                "source": "STOREFRONT_LINK",
                "category_id": None,
                "parent_url": None,
            }
        # Embedded mshops menu: recover names/IDs from the JSON payload.
        raw = (html or "").replace('\\"', '"').replace("\\u002F", "/")
        menu = re.findall(
            r'\{"id":"[^"]+","name":"([^"]+)","url":"([^"]*?/listado/[^"]+)",'
            r'"type":"[^"]+","selected":(?:true|false),"in_header":(?:true|false),'
            r'"picture":null,"category_id":"?(MLC[0-9]+)"?', raw, re.I)
        for name, url, cid in menu:
            url = url.split("?")[0].split("#")[0]
            found[_path_key(url)] = {
                "name": _canonical_category_name(name), "url": url,
                "path": self.LISTING_RE.search(url).group(2) if self.LISTING_RE.search(url) else "",
                "source": "STOREFRONT_MENU", "category_id": cid, "parent_url": None,
            }
        return list(found.values())

    def discover_from_api(self, store_url: str, known: list[dict],
                          missing_names: set[str] | None = None) -> list[dict]:
        """Expand only missing categories, and only with store-brand evidence."""
        missing = {str(n).lower() for n in (missing_names or set())}
        if not missing:
            return []
        try:
            root = self.api_category(self.root_category)
        except Exception:
            return []
        store_slug = urlparse(store_url).path.rstrip("/").split("/")[-1].lower()
        base = store_url.rstrip("/") + "/listado/"
        out = []
        for child in root.get("children_categories") or []:
            name = child.get("name")
            if not name or not child.get("id") or name.lower() not in missing:
                continue
            slug = _slug(name)
            candidate = base + "vestuario-calzado/" + slug + "/"
            body, status = self.fetch(candidate, timeout=8)
            low = body.lower()
            store_evidence = (store_slug and store_slug in low) or "tienda oficial" in low
            listing_evidence = any(x in low for x in ("resultados", "poly-card", "ui-search-layout"))
            if status == "200" and store_evidence and listing_evidence:
                out.append({
                    "name": _canonical_category_name(name), "url": candidate,
                    "path": "vestuario-calzado/" + slug,
                    "source": "PUBLIC_CATEGORY_API_PROBED",
                    "category_id": child.get("id"), "parent_url": None,
                })
        return out

    @staticmethod
    def hierarchy(categories: list[dict]) -> list[dict]:
        """Mark parent routes as reference when children exist; avoid double acquisition."""
        urls = [urlparse(c.get("url", "")).path.rstrip("/").lower()
                for c in categories if c.get("url")]
        for c in categories:
            u = urlparse(c.get("url", "")).path.rstrip("/").lower()
            c["parent_url"] = None
            for other in urls:
                if other != u and other.startswith(u + "/"):
                    c["parent_url"] = other
                    break
            c["acquisition"] = c["parent_url"] is None
        return categories

    def discover(self, target: DiscoveryTarget) -> DiscoveryResult:
        store_url = self.resolve_store(target)
        if not store_url:
            return DiscoveryResult(target, None, [], ["STORE_UNRESOLVED"], state="STORE_BLOCKED")
        cached = learned_categories("Mercado Libre", target.brand)
        if cached:
            cached = self.hierarchy(cached)
            mark_hit("Mercado Libre", target.brand)
            return DiscoveryResult(target, store_url, cached, ["GRAPH_CACHE"],
                                   state="DISCOVERED_FROM_GRAPH")
        html, status = self.fetch(store_url)
        if status != "200":
            return DiscoveryResult(target, store_url, [], [f"STOREFRONT_{status}"], state="STORE_BLOCKED")
        strategies = ["STOREFRONT_LINK", "STOREFRONT_MENU"]
        cats = self.parse_categories(html, store_url)
        key = f"{target.marketplace}|{target.store_url or target.brand}"
        previous = set((_memory().get(key) or {}).get("categories") or [])
        current = {c.get("name") for c in cats if c.get("name")}
        missing_names = {n for n in previous if n not in current}
        api_cats = self.discover_from_api(store_url, cats, missing_names)
        if api_cats:
            strategies.append("PUBLIC_CATEGORY_API_PROBED")
        seen: dict[str, dict] = {}
        for c in cats + api_cats:
            key = urlparse(c.get("url", "")).path.rstrip("/").lower()
            if not key:
                continue
            # Prefer the observed storefront route over an API-derived candidate.
            if key not in seen or c.get("source") == "STOREFRONT_MENU":
                seen[key] = c
        # Also dedupe identical names across spelling variants.
        by_name: dict[str, dict] = {}
        for c in seen.values():
            name = _norm(c.get("name"))
            if name and name not in by_name:
                by_name[name] = c
        cats = self.hierarchy(list(by_name.values()))
        merge_discovered("Mercado Libre", target.brand, None, cats, "DISCOVERY_KERNEL")
        return DiscoveryResult(target, store_url, cats, strategies)

    def validation_snapshot(self, target: DiscoveryTarget, cats: list[dict]) -> dict:
        key = f"{target.marketplace}|{target.store_url or target.brand}"
        mem = _memory()
        previous = (mem.get(key) or {})
        prev_names = set(previous.get("categories") or [])
        now_names = {c.get("name") for c in cats if c.get("name")}
        new = sorted(now_names - prev_names)
        removed = sorted(prev_names - now_names)
        snapshot = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "categories": sorted(now_names),
            "new": new,
            "removed": removed,
            "count": len(now_names),
        }
        mem[key] = snapshot
        _save_memory(mem)
        return snapshot


class DiscoveryKernel:
    def __init__(self):
        self.adapters = {"Mercado Libre": MeliAdapter()}

    def adapter_for(self, marketplace: str):
        key = next((k for k in self.adapters if _norm(k) == _norm(marketplace)), None)
        return self.adapters.get(key) if key else None

    def discover(self, target: DiscoveryTarget) -> DiscoveryResult:
        adapter = self.adapter_for(target.marketplace)
        if adapter is None:
            return DiscoveryResult(target, None, [], ["NO_ADAPTER"], state="UNSUPPORTED_MARKETPLACE")
        result = adapter.discover(target)
        if result.store_url and result.categories:
            result.validation = adapter.validation_snapshot(target, result.categories)
        return result
