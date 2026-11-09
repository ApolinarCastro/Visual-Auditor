"""AUDIT_VERIFIED_ROUTES â€” audit persisted verified commercial routes directly.

This mode reuses the existing MRI stack; it is NOT a new engine:
  * routes come from ExperienceStore (CATEGORY rows already verified)
  * strategy choice uses the existing CapabilityRegistry/StrategySelector
  * acquisition uses the existing engines/scrapers
  * publications/evidence use AcquisitionRecoveryRunner.persist_to_sqlite,
    mri_foundation.append_evidence and the existing SQLite schema
  * checkpoints use the dashboard auxiliary directory (JSON, atomic replace)

It never performs global taxonomy discovery. Incidental findings are recorded
as pending candidates for DISCOVERY, never explored here.

Public API:
    preview_verified_routes(...)
    load_verified_routes(...)
    execute_verified_routes_audit(...)
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import re
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROUTE_SCOPES = ("ALL_VERIFIED", "TOP_N", "SELECTED_ROUTES")
ROUTE_STATES = (
    "FOUND", "EMPTY_VERIFIED", "SOURCE_BLOCKED", "AUTH_REQUIRED",
    "EXTRACTOR_FAILURE", "EXTRACTOR_FAILURE_RETRYABLE", "INTERNAL_CONTRACT_ERROR",
    "NO_VIABLE_CAPABILITY", "ROUTE_SKIPPED", "TIMEOUT", "POSITION_NOT_OBSERVABLE",
)
# Accounting terminal states (a route attempt reached a final result).
TERMINAL_STATES = ("FOUND", "EMPTY_VERIFIED", "SOURCE_BLOCKED", "AUTH_REQUIRED",
                   "EXTRACTOR_FAILURE", "EXTRACTOR_FAILURE_RETRYABLE",
                   "INTERNAL_CONTRACT_ERROR", "NO_VIABLE_CAPABILITY",
                   "ROUTE_SKIPPED", "TIMEOUT")
# Resume skips only commercially-attributed terminal results; internal contract
# errors and non-viable strategies are retried after a fix, never counted as
# a completed audit.
RESUME_SKIP_STATES = ("FOUND", "EMPTY_VERIFIED", "SOURCE_BLOCKED", "AUTH_REQUIRED",
                      "ROUTE_SKIPPED")
FAILURE_CLASSES = ("SOURCE_FAILURE", "AUTH_FAILURE", "EXTRACTION_FAILURE",
                   "INTERNAL_CONTRACT_ERROR", "RESOURCE_FAILURE", "USER_CANCELLED",
                   "NO_STRATEGY")
VERIFIED_STATUSES = ("LAST_GOOD", "VALIDATED")
_INTERNAL_EXC = (TypeError, AttributeError, NameError, ImportError, SyntaxError)
_REDACT_RE = re.compile(
    r"(?i)((?:cookie|authorization|bearer|token|secret|password|api[_-]?key)\s*[:=]\s*)[^\s,;]+")


def _redact(text: str, limit: int = 8000) -> str:
    """Strip credential-bearing tokens from technical diagnostics."""
    return _REDACT_RE.sub(r"\1[REDACTED]", str(text or ""))[:limit]


def _classify_failure(state: str, reason: str = "", exc: Optional[BaseException] = None) -> Optional[str]:
    """Attribute a failure to its real origin (commercial vs internal)."""
    if state in ("FOUND", "EMPTY_VERIFIED"):
        return None
    if state == "NO_VIABLE_CAPABILITY":
        return "NO_STRATEGY"
    if exc is not None and isinstance(exc, _INTERNAL_EXC):
        return "INTERNAL_CONTRACT_ERROR"
    text = str(reason or "")
    if re.search(r"\b(TypeError|AttributeError|NameError|ImportError|SyntaxError)\b", text):
        return "INTERNAL_CONTRACT_ERROR"
    if state == "AUTH_REQUIRED":
        return "AUTH_FAILURE"
    if state == "SOURCE_BLOCKED":
        return "SOURCE_FAILURE"
    if state == "TIMEOUT":
        return "RESOURCE_FAILURE"
    if exc is not None and isinstance(exc, (PermissionError, OSError)):
        return "RESOURCE_FAILURE"
    return "EXTRACTION_FAILURE"


def _write_diagnostic(run_id: str, route: Dict[str, Any], operation: str,
                      exc: BaseException, failure_class: str) -> Dict[str, Any]:
    """Persist a redacted technical diagnostic and return its trace_id."""
    trace_id = uuid.uuid4().hex
    payload = {
        "trace_id": trace_id, "run_id": run_id,
        "route_id": route.get("route_id"), "marketplace": route.get("marketplace"),
        "operation": operation, "component": "verified_routes_audit",
        "failure_class": failure_class,
        "exception_type": type(exc).__name__,
        "exception_message": _redact(str(exc), 1200),
        "traceback": _redact("".join(traceback.format_exception(type(exc), exc, exc.__traceback__))),
        "timestamp": datetime.now().isoformat(),
    }
    try:
        path = _checkpoint_dir() / "mri_route_diagnostics.jsonl"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return {"trace_id": trace_id, "exception_type": payload["exception_type"],
            "exception_message": payload["exception_message"],
            "failure_class": failure_class,
            "diagnostic_path": str(_checkpoint_dir() / "mri_route_diagnostics.jsonl")}


def selection_snapshot_path(run_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(run_id))
    return _checkpoint_dir() / f"mri_verified_routes_selection_{safe}.json"


def selection_fingerprint(routes: Iterable[Dict[str, Any]]) -> str:
    material = "\n".join(f"{r.get('route_id')}|{r.get('url')}" for r in routes)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def save_selection_snapshot(run_id: str, selection: Dict[str, Any],
                            experience_source: Optional[str] = None) -> Dict[str, Any]:
    """Persist an immutable snapshot of the selected scope (id+url+filters)."""
    path = selection_snapshot_path(run_id)
    fingerprint = selection_fingerprint(selection.get("routes") or [])
    snapshot = {
        "run_id": run_id,
        "marketplace_scope": selection.get("marketplace"),
        "selection_mode": selection.get("scope"),
        "routes_selected": int(selection.get("routes_selected") or len(selection.get("routes") or [])),
        "selection_fingerprint": fingerprint,
        "selection_timestamp": datetime.now().isoformat(),
        "experience_source": experience_source or selection.get("experience_source"),
        "routes": [dict(r) for r in selection.get("routes") or []],
    }
    if not path.exists():
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    return {"path": str(path), "fingerprint": fingerprint,
            "routes_selected": snapshot["routes_selected"],
            "selection_timestamp": snapshot["selection_timestamp"]}


def load_selection_snapshot(run_id: str) -> Optional[Dict[str, Any]]:
    path = selection_snapshot_path(run_id)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not data.get("routes"):
            return None
        return data
    except Exception:
        return None
MAX_CONSECUTIVE_FAILURES = 3
MIN_SUCCESS_EVIDENCE = 1
MARKETPLACES = ("Mercado Libre", "Paris", "Ripley", "Falabella")

CAPABILITY_TYPE_BY_MARKET = {
    "Paris": "CATALOG_DISCOVERY",
    "Ripley": "PRODUCT_EXTRACTION",
    "Falabella": "PRODUCT_EXTRACTION",
    "Mercado Libre": "OFFICIAL_STORE_ISOLATION",
}


# ---------------------------------------------------------------------------
# Route recovery / deterministic selection
# ---------------------------------------------------------------------------

def _valid_url(url: str) -> bool:
    try:
        p = urlsplit(str(url))
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def canonical_route_key(url: str) -> str:
    """Dedupe key that PRESERVES commercial filter parameters.

    Only scheme/host casing, fragment and query ordering are normalized.
    Filter parameters (``f.*``, ``tipoProductoAll``, ``q``) are never removed.
    """
    p = urlsplit(str(url))
    pairs = sorted(parse_qsl(p.query, keep_blank_values=True))
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/",
                       urlencode(pairs), ""))


def classify_route_type(url: str, exp: Dict[str, Any]) -> str:
    low = str(url).lower()
    params = {k.lower(): v for k, v in parse_qsl(urlsplit(str(url)).query)}
    if "/category/" in low or "/categoria/" in low or "category_id" in params:
        return "COMMERCIAL_CATEGORY"
    if any(k.startswith("f.") for k in params) or "tipoProductoAll".lower() in params:
        return "COMMERCIAL_FACET"
    if "/tienda/" in low or "/brand/" in low or "/marca/" in low:
        return "STORE_OR_BRAND"
    if "search" in low or "q" in params or "ntt" in params:
        return "SEARCH_RESULTS"
    return str(exp.get("page_type") or "CATEGORY")


def _page_type_is_promotion(exp: Dict[str, Any]) -> bool:
    return str(exp.get("page_type") or "").upper() in ("PROMOTION", "PROMO")


def load_verified_routes(
    marketplace: str = "ALL",
    scope: str = "ALL_VERIFIED",
    limit: Optional[int] = None,
    selected_routes: Optional[Iterable[str]] = None,
    brand: str = "Nicopoly",
    experience_store: Any = None,
    markets: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Recover/dedupe/select verified routes with explicit, traceable reasons."""
    if scope not in ROUTE_SCOPES:
        raise ValueError(f"INVALID_SCOPE: {scope}")
    markets_to_run = list(markets or ([marketplace] if marketplace != "ALL" else MARKETPLACES))
    if experience_store is None:
        from app.mri_autonomous.experience_store import ExperienceStore
        experience_store = ExperienceStore()

    selected_set: Optional[set] = None
    if scope == "SELECTED_ROUTES":
        selected_set = {canonical_route_key(u) for u in (selected_routes or []) if _valid_url(u)}
        if not selected_set:
            raise ValueError("SELECTED_ROUTES requires at least one valid URL")
    if scope == "TOP_N":
        if limit is None:
            raise ValueError("TOP_N requires an explicit positive limit")
        try:
            limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("TOP_N limit must be an integer") from exc
        if limit <= 0:
            raise ValueError("TOP_N limit must be > 0")

    out_markets: Dict[str, Any] = {}
    all_selected: List[Dict[str, Any]] = []
    all_skipped: List[Dict[str, str]] = []
    total_available = 0
    total_eligible = 0

    rows_by_market: Dict[str, List[Dict[str, Any]]] = {}
    for mkt in markets_to_run:
        raw = experience_store.get_all_experiences(marketplace=mkt, brand=brand) or []
        rows_by_market[mkt] = [r for r in raw if r.get("knowledge_type") == "CATEGORY"]

    # CP0: the dashboard write/learning DB (operational) can legitimately carry
    # no CATEGORY rows yet while the authorized experience DB holds the verified
    # routes. Read the authorized source read-only instead of migrating/merging.
    experience_source = "ExperienceStore"
    if sum(len(v) for v in rows_by_market.values()) == 0:
        try:
            import sqlite3 as _sqlite
            from app.mri_autonomous.storage_guard import StorageConfig as _SC
            _repo_root = Path(__file__).resolve().parents[3]
            candidates = [os.getenv("MRI_EXPERIENCE_DB"),
                          str(_repo_root / "data" / "mri_experience.db"),
                          str(getattr(_SC, "PRODUCTION_EXPERIENCE", ""))]
            for authorized in [c for c in candidates if c and os.path.exists(str(c))]:
                conn = _sqlite.connect("file:" + str(authorized).replace("\\", "/") + "?mode=ro",
                                       uri=True)
                conn.row_factory = _sqlite.Row
                fetched_any = False
                try:
                    for mkt in markets_to_run:
                        fetched = [dict(r) for r in conn.execute(
                            "SELECT * FROM experience WHERE marketplace=? AND brand=? "
                            "AND knowledge_type='CATEGORY'", (mkt, brand))]
                        if fetched:
                            fetched_any = True
                        rows_by_market[mkt] = fetched
                finally:
                    conn.close()
                if fetched_any and any(rows_by_market.values()):
                    experience_source = f"authorized_experience_read_only:{authorized}"
                    break
        except Exception:
            pass

    for mkt in markets_to_run:
        rows = rows_by_market.get(mkt) or []
        total_available += len(rows)
        seen: Dict[str, Dict[str, Any]] = {}
        skipped: List[Dict[str, str]] = []
        for row in rows:
            url = str(row.get("source_url") or "").strip()
            if not _valid_url(url):
                skipped.append({"url": url or "", "reason": "INVALID_URL"})
                continue
            if row.get("status") not in VERIFIED_STATUSES:
                skipped.append({"url": url, "reason": f"STATUS_{row.get('status') or 'UNKNOWN'}"})
                continue
            if int(row.get("consecutive_failures") or 0) >= MAX_CONSECUTIVE_FAILURES:
                skipped.append({"url": url, "reason": "CONSECUTIVE_FAILURES"})
                continue
            if int(row.get("success_count") or 0) < MIN_SUCCESS_EVIDENCE:
                skipped.append({"url": url, "reason": "NO_VERIFICATION_EVIDENCE"})
                continue
            if _page_type_is_promotion(row):
                skipped.append({"url": url, "reason": "PROMOTION_NOT_COMMERCIAL_ROUTE"})
                continue
            if canonical_route_key(url) in seen:
                skipped.append({"url": url, "reason": "DUPLICATE_ROUTE"})
                continue
            seen[canonical_route_key(url)] = {
                "route_id": f"exp_{row.get('id')}",
                "marketplace": mkt,
                "url": url,
                "route_type": classify_route_type(url, row),
                "route_source": "experience_store",
                "experience_id": row.get("id"),
                "status": row.get("status"),
                "success_count": int(row.get("success_count") or 0),
                "consecutive_failures": int(row.get("consecutive_failures") or 0),
                "last_seen_at": row.get("last_seen_at"),
                "page_type": row.get("page_type"),
            }
        eligible = list(seen.values())
        eligible.sort(key=lambda r: (-r["success_count"],
                                     str(r.get("last_seen_at") or ""),
                                     r["url"]), )
        # deterministic secondary order for equal timestamps
        eligible.sort(key=lambda r: (-r["success_count"], r["url"]))
        total_eligible += len(eligible)

        if scope == "ALL_VERIFIED":
            selected = eligible
        elif scope == "TOP_N":
            selected = eligible[:int(limit)]  # type: ignore[arg-type]
        else:
            selected = [r for r in eligible if canonical_route_key(r["url"]) in (selected_set or set())]
        for r in selected:
            r["scope"] = scope
            r["total_scope_claim"] = (scope == "ALL_VERIFIED")
        all_selected.extend(selected)
        all_skipped.extend([dict(s, marketplace=mkt) for s in skipped])
        out_markets[mkt] = {
            "routes_available": len(rows),
            "routes_eligible": len(eligible),
            "routes_selected": len(selected),
            "routes_skipped": len(skipped),
            "routes": selected,
            "skipped": skipped,
        }

    total_selected = len(all_selected)
    by_market = {m: len(v["routes"]) for m, v in out_markets.items()}
    selection_reason = (
        f"scope={scope}; deterministic order=success_count DESC,url ASC; "
        f"eligible={total_eligible}; selected={total_selected}"
    )
    return {
        "mode": "AUDIT_VERIFIED_ROUTES",
        "marketplace": marketplace,
        "scope": scope,
        "brand": brand,
        "experience_source": experience_source,
        "routes_available": total_available,
        "routes_eligible": total_eligible,
        "routes_selected": total_selected,
        "routes_skipped": len(all_skipped),
        "selection_reason": selection_reason,
        "total_scope_claim": (scope == "ALL_VERIFIED"),
        "routes_by_marketplace": by_market,
        "marketplaces": out_markets,
        "routes": all_selected,
        "skipped": all_skipped,
    }


def preview_verified_routes(marketplace: str = "ALL", scope: str = "ALL_VERIFIED",
                            limit: Optional[int] = None,
                            selected_routes: Optional[Iterable[str]] = None,
                            experience_store: Any = None) -> Dict[str, Any]:
    selection = load_verified_routes(
        marketplace=marketplace, scope=scope, limit=limit,
        selected_routes=selected_routes, experience_store=experience_store)
    return {
        "mode": "AUDIT_VERIFIED_ROUTES",
        "marketplace": marketplace,
        "scope": scope,
        "routes_available": selection["routes_available"],
        "routes_eligible": selection["routes_eligible"],
        "routes_selected": selection["routes_selected"],
        "routes_skipped": selection["routes_skipped"],
        "routes_by_marketplace": selection["routes_by_marketplace"],
        "total_scope_claim": selection["total_scope_claim"],
        "experience_source": selection.get("experience_source"),
        "sample": [{"marketplace": r["marketplace"], "url": r["url"],
                    "route_type": r["route_type"]} for r in selection["routes"][:5]],
    }


# ---------------------------------------------------------------------------
# Acquisition (existing engines/scrapers only)
# ---------------------------------------------------------------------------

def _mk_publication(route: Dict[str, Any], marketplace: str, *, sku: str, title: str,
                    url: str, position: Optional[int] = None,
                    identity: str = "TARGET_IDENTITY_VERIFIED") -> Dict[str, Any]:
    return {
        "sku": sku or hashlib.sha1(f"{url}|{title}".encode("utf-8")).hexdigest()[:12],
        "title": title or "UNKNOWN",
        "url": url,
        "position_absolute": position,
        "identity_status": identity,
    }


def _paris_route_publications(route: Dict[str, Any]) -> Dict[str, Any]:
    from app.mri_autonomous.rea_paris_engine import REAParisEngine
    engine = REAParisEngine()
    url = route["url"]
    qs = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
    if qs.get("tipoProductoAll"):
        payload = engine.browse("tipoProductoAll", qs["tipoProductoAll"], page=1,
                                num_results=40, filters={"brand": "Nicopoly"})
    else:
        payload = engine.search(qs.get("q", "nicopoly"), page=1, num_results=40)
    response = payload.get("response", {}) if isinstance(payload, dict) else {}
    total = int(response.get("total_num_results") or 0)
    pubs = []
    for idx, item in enumerate(response.get("results") or [], 1):
        value = item.get("value") if isinstance(item, dict) and isinstance(item.get("value"), dict) else item
        if not isinstance(value, dict):
            continue
        pubs.append(_mk_publication(
            route, "Paris",
            sku=str(value.get("id") or value.get("sku") or ""),
            title=str(value.get("name") or value.get("title") or ""),
            url=str(value.get("url") or value.get("canonical_url") or ""),
            position=None))
    state = "FOUND" if (pubs or total > 0) else "EMPTY_VERIFIED"
    return {"state": state, "publications": pubs, "source_total": total,
            "positions_observable": False,
            "reason": f"CONSTRUCTOR_BROWSE_TOTAL={total}"}


def _falabella_route_publications(route: Dict[str, Any]) -> Dict[str, Any]:
    from app.mri_autonomous.falabella_ssr_engine import FalabellaSSREngine
    engine = FalabellaSSREngine()
    url = route["url"]
    p = urlsplit(url)
    rel = p.path + (("?" + p.query) if p.query else "")
    payload = engine.fetch_page_ssr_data(rel)
    props = (payload or {}).get("props", {}).get("pageProps", {})
    total = int((props.get("pagination") or {}).get("count") or 0)
    pubs = []
    try:
        normalized, _entities = engine.harvest_sample_publications(
            brand="NICOPOLY", max_items=48, page_payload=payload)
        for idx, pub in enumerate(normalized, 1):
            pubs.append(_mk_publication(
                route, "Falabella",
                sku=str(getattr(pub, "sku", "") or ""),
                title=str(getattr(pub, "title", "") or ""),
                url=str(getattr(pub, "canonical_url", "") or ""),
                position=None))
    except Exception:
        pubs = []
    state = "FOUND" if (pubs or total > 0) else "EMPTY_VERIFIED"
    return {"state": state, "publications": pubs, "source_total": total,
            "positions_observable": False,
            "reason": f"SSR_PAGE_TOTAL={total}"}


async def _browser_route_publications(route: Dict[str, Any], marketplace: str,
                                      timeout_s: int = 120) -> Dict[str, Any]:
    from app.mri_dashboard.mri_runner import get_scraper
    scraper = get_scraper(marketplace or route["marketplace"])
    if scraper is None:
        return {"state": "EXTRACTOR_FAILURE", "publications": [] if False else [],
                "reason": "NO_EXISTING_SCRAPER_FOR_MARKETPLACE",
                "failure_class": "EXTRACTION_FAILURE", "scraper_started": False}
    started = False
    try:
        await asyncio.wait_for(scraper.start(), timeout=timeout_s)
        started = True
        try:
            await asyncio.wait_for(scraper.navigate(route["url"]), timeout=timeout_s)
        except Exception as exc:
            text = str(exc).lower()
            state = ("SOURCE_BLOCKED" if ("403" in text or "429" in text or "blocked" in text)
                     else "TIMEOUT" if "timeout" in text else "EXTRACTOR_FAILURE")
            failure_class = _classify_failure(state, str(exc), exc)
            if failure_class == "INTERNAL_CONTRACT_ERROR":
                state = "INTERNAL_CONTRACT_ERROR"
            return {"state": state, "publications": [],
                    "reason": _redact(f"NAVIGATE_{type(exc).__name__}: {exc}", 500),
                    "failure_class": failure_class, "scraper_started": started}
        # Engine-specific contract: only pass max_pages when the method accepts it.
        params = inspect.signature(scraper.scrape_autonomous_category).parameters
        kwargs = {"max_pages": 1} if "max_pages" in params else {}
        result = await asyncio.wait_for(
            scraper.scrape_autonomous_category(route["url"], **kwargs), timeout=timeout_s)
        products = result.get("products") or []
        stop = str(result.get("stop_reason") or "")
        pubs = []
        for idx, product in enumerate(products, 1):
            pos = product.get("position_absolute") or product.get("position") or product.get("position_observed")
            pubs.append(_mk_publication(
                route, marketplace,
                sku=str(product.get("marketplace_sku") or product.get("sku") or ""),
                title=str(product.get("title") or ""),
                url=str(product.get("url") or product.get("link") or ""),
                position=int(pos) if pos is not None else None))
        if pubs:
            state = "FOUND"
        elif stop in ("SOURCE_BLOCKED", "RATE_LIMIT"):
            state = "SOURCE_BLOCKED"
        elif stop in ("EXTRACTOR_FAILURE", "PAGINATION_BLOCKED"):
            state = "EXTRACTOR_FAILURE_RETRYABLE"
        elif stop == "EMPTY_VERIFIED":
            state = "EMPTY_VERIFIED"
        else:
            state = "EMPTY_VERIFIED" if stop in ("EXHAUSTION", "NO_PROGRESS") else "EXTRACTOR_FAILURE_RETRYABLE"
        return {"state": state, "publications": pubs,
                "positions_observable": any(p.get("position_absolute") is not None for p in pubs),
                "reason": f"STOP={stop}", "scraper_started": started,
                "failure_class": _classify_failure(state, f"STOP={stop}")}
    except asyncio.TimeoutError:
        return {"state": "TIMEOUT", "publications": [], "reason": "BROWSER_TIMEOUT",
                "failure_class": "RESOURCE_FAILURE", "scraper_started": started}
    except Exception as exc:
        failure_class = _classify_failure("EXTRACTOR_FAILURE", str(exc), exc)
        state = "INTERNAL_CONTRACT_ERROR" if failure_class == "INTERNAL_CONTRACT_ERROR" else "EXTRACTOR_FAILURE"
        diag = _write_diagnostic("", route, f"{marketplace}.scrape_autonomous_category",
                                 exc, failure_class) if failure_class == "INTERNAL_CONTRACT_ERROR" else {}
        return {"state": state, "publications": [],
                "reason": _redact(f"{type(exc).__name__}: {exc}", 800),
                "failure_class": failure_class, "scraper_started": started, **diag}
    finally:
        try:
            await scraper.stop()
        except Exception:
            pass


async def acquire_route(route: Dict[str, Any], timeout_s: int = 120) -> Dict[str, Any]:
    """Execute one verified route with the existing acquisition component."""
    mkt = route["marketplace"]
    try:
        if mkt == "Paris":
            return await asyncio.wait_for(asyncio.to_thread(_paris_route_publications, route),
                                          timeout=timeout_s)
        if mkt == "Falabella":
            return await asyncio.wait_for(asyncio.to_thread(_falabella_route_publications, route),
                                          timeout=timeout_s)
        return await _browser_route_publications(route, mkt, timeout_s)
    except asyncio.TimeoutError:
        return {"state": "TIMEOUT", "publications": [], "reason": f"ROUTE_TIMEOUT_{timeout_s}s"}
    except Exception as exc:
        text = str(exc).lower()
        return {"state": "SOURCE_BLOCKED" if ("403" in text or "429" in text or "forbidden" in text)
                else "EXTRACTOR_FAILURE",
                "publications": [], "reason": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Strategy reuse (existing selector)
# ---------------------------------------------------------------------------

def select_route_strategy(route: Dict[str, Any], store: Any = None) -> Dict[str, Any]:
    """Select with the CORRECTED selector: persisted experience is an input."""
    marketplace = route["marketplace"]
    try:
        from app.mri_autonomous.capability_registry import CapabilityRegistry, CapabilityType
        from app.mri_autonomous.strategy_selector import StrategySelector
        registry = CapabilityRegistry(auto_probe=True, experience_store=store,
                                      persistence_enabled=store is not None)
        selector = StrategySelector(registry, experience_store=store)
        cap_type = getattr(CapabilityType, CAPABILITY_TYPE_BY_MARKET.get(marketplace, "PRODUCT_EXTRACTION"))
        selected = selector.select_strategy(marketplace, cap_type)
        if selected is None:
            return {"strategy_selected": None, "reason": "NO_VIABLE_CAPABILITY",
                    "_registry": registry}
        decision = {
            "strategy_selected": selected.strategy_id,
            "capability_id": selected.capability.capability_id,
            "adapter_mode": selected.capability.adapter_mode.value,
            "selection_reason": selected.selection_reason,
            "fallback_chain": list(selected.fallback_strategy_ids),
            "experience_evidence": (selected.evidence or {}).get("capability_evidence", {}),
            "experience_consulted": bool((selected.evidence or {}).get("experience_consulted")),
            "_registry": registry,
        }
        if store is not None:
            try:
                store.record_strategy_decision(
                    marketplace=marketplace, brand="Nicopoly",
                    strategy_id=selected.strategy_id, selected=True,
                    reason=selected.selection_reason,
                    alternative_strategy_id=(selected.fallback_strategy_ids or [None])[0],
                    expected_outcome="ROUTE_AUDIT")
            except Exception:
                pass
        return decision
    except Exception as exc:
        return {"strategy_selected": None, "reason": f"SELECTOR_UNAVAILABLE: {type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Observations, evidence, checkpoints
# ---------------------------------------------------------------------------

def build_observations(run_id: str, route: Dict[str, Any], publications: List[Dict[str, Any]],
                       acquisition_state: str) -> List[Dict[str, Any]]:
    observations = []
    now = datetime.now().isoformat()
    for page_number, pub in enumerate(publications, 1):
        position = pub.get("position_absolute")
        position_state = "EXACT" if position is not None else "POSITION_NOT_OBSERVABLE"
        attributes = {
            "run_id": run_id,
            "route_id": route["route_id"],
            "route_type": route["route_type"],
            "route_url": route["url"],
            "page_number": 1,
            "position_scope": "COMMERCIAL_RESULTS" if position is not None else "NOT_OBSERVABLE",
            "organic_or_sponsored": None,
            "evidence_reference": f"verified_route:{route['experience_id']}",
        }
        observations.append({
            "publication_id": pub.get("sku") or f"pub_{hashlib.md5(pub.get('url', '').encode()).hexdigest()[:10]}",
            "marketplace": route["marketplace"],
            "observed_url": pub.get("url") or route["url"],
            "title": pub.get("title") or "UNKNOWN",
            "observation_timestamp": now,
            "position_observed": position,
            "position_state": position_state,
            "status": "OBSERVED",
            "acquisition_status": "OBSERVED",
            "identity_status": pub.get("identity_status") or "TARGET_IDENTITY_VERIFIED",
            "category_observed": route.get("route_type") or "COMMERCIAL_CATEGORY",
            "category_source": "VERIFIED_ROUTE",
            "category_expected": route.get("route_type") or "COMMERCIAL_CATEGORY",
            "category_decision": "OBSERVED",
            "commercial_attributes": json.dumps(attributes, ensure_ascii=False),
            "route_id": route["route_id"],
            "route_type": route["route_type"],
            "acquisition_state": acquisition_state,
        })
    return observations


def persist_route_result(run_id: str, route: Dict[str, Any], acquisition: Dict[str, Any],
                         observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Persist the ROUTE RESULT (even with zero publications) + evidence, idempotently."""
    persisted = {"publications_materialized": 0, "evidence_id": None, "idempotent": False}
    failure_class = acquisition.get("failure_class") or _classify_failure(
        acquisition.get("state", ""), str(acquisition.get("reason") or ""))
    raw = json.dumps({
        "run_id": run_id, "route_id": route.get("route_id"),
        "route_type": route.get("route_type"), "route_url": route.get("url"),
        "strategy_selected": acquisition.get("strategy_selected"),
        "strategy_executed": acquisition.get("strategy_executed"),
        "acquisition_state": acquisition.get("state"),
        "failure_class": failure_class,
        "failure_reason": _redact(str(acquisition.get("reason") or ""), 800),
        "publications": len(observations),
        "trace_id": acquisition.get("trace_id"),
    }, ensure_ascii=False, separators=(",", ":"))[:2000]
    try:
        import sqlite3
        from app.mri_autonomous.storage_guard import StorageConfig
        from app.storage.mri_foundation import append_evidence
        conn = sqlite3.connect(str(StorageConfig.get_sqlite_path()))
        try:
            existing = conn.execute(
                "SELECT evidence_id FROM mri_evidence_ledger WHERE run_id=? "
                "AND claim_type='VERIFIED_ROUTE_AUDIT' AND raw_reference LIKE ?",
                (run_id, f'%"route_id":"{route.get("route_id")}"%')).fetchone()
            if existing:
                persisted.update({"evidence_id": existing[0], "idempotent": True})
                return persisted
            if observations:
                try:
                    from app.mri_autonomous.recovery_runner import AcquisitionRecoveryRunner
                    rec = AcquisitionRecoveryRunner()
                    result = rec.persist_to_sqlite(
                        {"observations": observations, "terminal_state": acquisition["state"]},
                        run_id,
                        run_meta={
                            "marketplace": route["marketplace"],
                            "execution_mode": f"AUDIT_VERIFIED_ROUTES::{route['marketplace']}",
                            "source_method": "VERIFIED_ROUTE_AUDIT",
                            "terminal_state": acquisition["state"],
                        })
                    persisted.update(result)
                except Exception as exc:
                    persisted["persist_error"] = _redact(f"{type(exc).__name__}: {exc}", 400)
            # Guarantee the attempted route has a run row, even with zero publications.
            if not conn.execute("SELECT 1 FROM mri_runs WHERE run_id=?", (run_id,)).fetchone():
                conn.execute(
                    "INSERT OR IGNORE INTO mri_runs (run_id, started_at, finished_at, marketplace, brand, "
                    "execution_mode, truth_model_version, terminal_state, source_method, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_id, datetime.now().isoformat(), datetime.now().isoformat(),
                     route["marketplace"], "Nicopoly",
                     f"AUDIT_VERIFIED_ROUTES::{route['marketplace']}", "1", acquisition["state"],
                     "VERIFIED_ROUTE_AUDIT", acquisition["state"], datetime.now().isoformat()))
            evidence_id = append_evidence(
                conn, run_id, route["marketplace"], "Nicopoly",
                "VERIFIED_ROUTE_AUDIT", acquisition["state"],
                route["url"], "VERIFIED_ROUTE_ACQUISITION", 0.9,
                "VALIDATED" if acquisition["state"] in ("FOUND", "EMPTY_VERIFIED") else "FAILED",
                raw_reference=raw)
            persisted["evidence_id"] = evidence_id
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        persisted["evidence_error"] = _redact(f"{type(exc).__name__}: {exc}", 400)
    return persisted


def _checkpoint_dir() -> Path:
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        return Path(StorageConfig.get_aux_dir())
    except Exception:
        return Path("data/sqlite/mri_operational")


def checkpoint_path(run_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(run_id))
    return _checkpoint_dir() / f"mri_verified_routes_checkpoint_{safe}.json"


def save_checkpoint(run_id: str, payload: Dict[str, Any]) -> str:
    path = checkpoint_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return str(path)


def load_checkpoint(run_id: str) -> Optional[Dict[str, Any]]:
    path = checkpoint_path(run_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_scope_acceptance(summary: Dict[str, Any]) -> Dict[str, Any]:
    selected = int(summary.get("routes_selected") or 0)
    routes = summary.get("routes") or []
    by_id: Dict[str, str] = {}
    for idx, r in enumerate(routes):
        key = r.get("route_id") or f"__idx_{idx}"
        by_id[str(key)] = str(r.get("state") or "")
    states = list(by_id.values())
    processed = len(states)
    completed = sum(1 for s in states if s in ("FOUND", "EMPTY_VERIFIED"))
    blocked = sum(1 for s in states if s in ("SOURCE_BLOCKED", "AUTH_REQUIRED"))
    failed = sum(1 for s in states if s in ("EXTRACTOR_FAILURE", "EXTRACTOR_FAILURE_RETRYABLE",
                                            "INTERNAL_CONTRACT_ERROR", "TIMEOUT"))
    no_viable = sum(1 for s in states if s == "NO_VIABLE_CAPABILITY")
    remaining = max(selected - processed, 0)
    if summary.get("run_status") != "RUN_COMPLETED":
        selected_status = "SELECTED_ROUTES_PARTIAL"
    elif selected and completed == selected:
        selected_status = "SELECTED_ROUTES_COMPLETE"
    elif completed:
        selected_status = "SELECTED_ROUTES_PARTIAL"
    else:
        selected_status = "SOURCE_BLOCKED" if blocked else "SELECTED_ROUTES_PARTIAL"
    return {
        "run_status": summary.get("run_status"),
        "selected_routes_status": selected_status,
        "routes_selected": selected,
        "routes_processed": processed,
        "routes_completed": completed,
        "routes_failed": failed,
        "routes_blocked": blocked,
        "routes_no_viable_strategy": no_viable,
        "routes_not_started": remaining,
        "routes_remaining": remaining,
        "routes_source_blocked": blocked,
        "routes_extractor_failures": failed,
        "taxonomy_global": "TAXONOMY_GLOBAL_UNVERIFIED",
        "scope_acceptance": ("PASS" if selected_status == "SELECTED_ROUTES_COMPLETE"
                             else "PARTIAL"),
        "note": ("Scope acceptance evaluates only the declared selected routes; "
                 "it does not certify global taxonomy (DISCOVERY remains separate)."),
    }


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _route_counters(results: List[Dict[str, Any]], selected: int) -> Dict[str, int]:
    by_id: Dict[str, str] = {}
    for idx, r in enumerate(results):
        key = r.get("route_id") or f"__idx_{idx}"
        by_id[str(key)] = str(r.get("state") or "")
    states = list(by_id.values())
    processed = len(states)
    completed = sum(1 for s in states if s in ("FOUND", "EMPTY_VERIFIED"))
    blocked = sum(1 for s in states if s in ("SOURCE_BLOCKED", "AUTH_REQUIRED"))
    failed = sum(1 for s in states if s in ("EXTRACTOR_FAILURE", "EXTRACTOR_FAILURE_RETRYABLE",
                                            "INTERNAL_CONTRACT_ERROR", "TIMEOUT"))
    no_viable = sum(1 for s in states if s == "NO_VIABLE_CAPABILITY")
    return {"routes_processed": processed, "routes_completed": completed,
            "routes_failed": failed, "routes_blocked": blocked,
            "routes_no_viable_strategy": no_viable,
            "routes_not_started": max(selected - processed, 0),
            "routes_remaining": max(selected - processed, 0)}


def _route_history(experience_store: Any, route: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Read the persisted per-route state (ROUTE_STATE), not the capability health."""
    if experience_store is None:
        return None
    try:
        return experience_store.get_experience_item(
            route.get("marketplace"), "Nicopoly", "ROUTE_STATE", route.get("route_id"))
    except Exception:
        return None


def _route_is_exhausted(row: Optional[Dict[str, Any]]) -> bool:
    """A route with >=3 terminal failures is skipped; capability health is untouched."""
    if not row:
        return False
    terminal_route_states = ("SOURCE_BLOCKED", "AUTH_REQUIRED", "EMPTY_VERIFIED")
    try:
        failures = int(row.get("failure_count") or 0)
    except Exception:
        failures = 0
    return failures >= 3 and str(row.get("page_type") or "") in terminal_route_states


async def execute_verified_routes_audit(
    *,
    run_id: str,
    marketplace: str = "ALL",
    scope: str = "ALL_VERIFIED",
    limit: Optional[int] = None,
    selected_routes: Optional[Iterable[str]] = None,
    resume_run_id: Optional[str] = None,
    brand: str = "Nicopoly",
    experience_store: Any = None,
    acquisition_fn: Optional[Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]] = None,
    persist_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    stop_requested: Optional[Callable[[], bool]] = None,
    timeout_s: int = 120,
) -> Dict[str, Any]:
    started = datetime.now().isoformat()
    t0 = time.time()
    if experience_store is None:
        from app.mri_autonomous.experience_store import ExperienceStore
        experience_store = ExperienceStore()
    selection = load_verified_routes(
        marketplace=marketplace, scope=scope, limit=limit,
        selected_routes=selected_routes, brand=brand,
        experience_store=experience_store)
    selected_total = int(selection.get("routes_selected") or len(selection.get("routes") or []))
    selection["marketplace"] = marketplace
    selection["scope"] = scope

    # CP5: freeze the selected scope. Resume MUST use the frozen snapshot.
    resume_checkpoint = None
    if resume_run_id:
        frozen = load_selection_snapshot(resume_run_id)
        resume_checkpoint = load_checkpoint(resume_run_id)
        if frozen and frozen.get("routes"):
            selection["routes"] = [dict(r) for r in frozen["routes"]]
            selected_total = int(frozen.get("routes_selected") or len(frozen["routes"]))
            selection["selection_fingerprint"] = frozen.get("selection_fingerprint")
            selection["frozen_selection"] = True
            selection["selection_snapshot_path"] = str(selection_snapshot_path(resume_run_id))
        else:
            selection["frozen_selection"] = False
            selection["resume_scope_warning"] = (
                "LEGACY_CHECKPOINT_WITHOUT_SELECTION_SNAPSHOT: exact resume scope not guaranteed")
        selection["resumed_from"] = resume_run_id
        if resume_checkpoint:
            done = {r["route_id"]: r for r in resume_checkpoint.get("routes") or []
                    if r.get("state") in RESUME_SKIP_STATES}
            selection["routes"] = [r for r in selection["routes"] if r["route_id"] not in done]
            selection["already_completed"] = len(done)
    else:
        snapshot = save_selection_snapshot(run_id, selection,
                                           experience_source=selection.get("experience_source"))
        selection["selection_snapshot"] = snapshot
        selection["selection_fingerprint"] = snapshot["fingerprint"]
        selection["selection_snapshot_path"] = snapshot["path"]
        selection["frozen_selection"] = True

    total = len(selection["routes"])
    results: List[Dict[str, Any]] = []
    run_status = "RUN_COMPLETED"
    acquire = acquisition_fn or acquire_route

    def _checkpoint(run_status_value: str) -> None:
        counters = _route_counters(results, selected_total)
        save_checkpoint(run_id, {
            "run_id": run_id, "mode": "AUDIT_VERIFIED_ROUTES",
            "marketplace": marketplace, "scope": scope,
            "started_at": started, "updated_at": datetime.now().isoformat(),
            "run_status": run_status_value,
            "routes_selected": selected_total,
            "routes": results,
            "selection_fingerprint": selection.get("selection_fingerprint"),
            "selection_snapshot_path": selection.get("selection_snapshot_path"),
            "frozen_selection": selection.get("frozen_selection"),
            "resume_scope_warning": selection.get("resume_scope_warning"),
            "counters": counters,
        })

    for index, route in enumerate(selection["routes"], 1):
        if stop_requested is not None and stop_requested():
            run_status = "STOPPED_BY_USER"
            break
        strategy = select_route_strategy(route, store=experience_store)
        strategy_id = strategy.get("strategy_selected")
        state: Dict[str, Any] = {
            "route_id": route["route_id"], "marketplace": route["marketplace"],
            "url": route["url"], "route_type": route["route_type"],
            "strategy": strategy, "publications": 0, "positions_observable": 0,
            "state": "EXTRACTOR_FAILURE", "reason": None, "failure_class": None,
            "scraper_started": False, "trace_id": None,
        }
        acquisition: Dict[str, Any]
        _history = _route_history(experience_store, route)
        if _route_is_exhausted(_history):
            # MRI-005: a route individually exhausted is skipped; capability stays intact.
            acquisition = {"state": "ROUTE_SKIPPED", "publications": [],
                           "reason": f"ROUTE_HISTORY_FAILURES={_history.get('failure_count')}",
                           "failure_class": "ROUTE_SKIPPED", "scraper_started": False}
            strategy_id = None
        elif not strategy_id:
            # CP2: no viable strategy => NEVER start a scraper.
            acquisition = {"state": "NO_VIABLE_CAPABILITY", "publications": [],
                           "reason": "NO_VIABLE_CAPABILITY", "failure_class": "NO_STRATEGY",
                           "scraper_started": False}
        else:
            try:
                acquisition = await asyncio.wait_for(acquire(route), timeout=timeout_s + 15)
            except asyncio.TimeoutError:
                acquisition = {"state": "TIMEOUT", "publications": [], "reason": "HARD_TIMEOUT",
                               "failure_class": "RESOURCE_FAILURE"}
            except Exception as exc:
                failure_class = _classify_failure("EXTRACTOR_FAILURE", str(exc), exc)
                acquisition = {"state": ("INTERNAL_CONTRACT_ERROR" if failure_class == "INTERNAL_CONTRACT_ERROR"
                                         else "EXTRACTOR_FAILURE"),
                               "publications": [], "reason": _redact(f"{type(exc).__name__}: {exc}", 800),
                               "failure_class": failure_class}
                if failure_class == "INTERNAL_CONTRACT_ERROR":
                    diag = _write_diagnostic(run_id, route, "acquire_route", exc, failure_class)
                    acquisition.update(diag)
        if not isinstance(acquisition, dict):
            acquisition = {"state": "EXTRACTOR_FAILURE", "publications": [],
                           "reason": "INVALID_ACQUISITION_RESULT"}
        if acquisition.get("state") in ("FOUND", "EMPTY_VERIFIED"):
            failure_class = None
        else:
            failure_class = acquisition.get("failure_class") or _classify_failure(
                acquisition.get("state", ""), str(acquisition.get("reason") or ""))
        acquisition.setdefault("failure_class", failure_class)
        acquisition.setdefault("scraper_started", bool(strategy_id))
        acquisition.setdefault("strategy_selected", strategy_id)
        acquisition.setdefault("strategy_executed", strategy_id)
        acquisition.setdefault("fallback_reason", None)
        observations = build_observations(run_id, route, acquisition.get("publications") or [],
                                          acquisition["state"])
        persisted = (persist_fn or persist_route_result)(run_id, route, acquisition, observations)
        state.update({
            "state": acquisition["state"],
            "reason": acquisition.get("reason"),
            "failure_class": failure_class,
            "publications": len(observations),
            "positions_observable": sum(1 for o in observations
                                        if o.get("position_state") == "EXACT"),
            "persisted": persisted,
            "scraper_started": bool(acquisition.get("scraper_started")),
            "trace_id": acquisition.get("trace_id"),
            "exception_type": acquisition.get("exception_type"),
            "exception_message": acquisition.get("exception_message"),
            "strategy_selected": strategy_id,
            "strategy_executed": strategy_id,
            "fallback_reason": None,
        })
        _registry = strategy.pop("_registry", None)
        _capability_id = strategy.get("capability_id")
        _success = acquisition["state"] in ("FOUND", "EMPTY_VERIFIED")
        # MRI-005: per-route failures are recorded as ROUTE_STATE; only errors that
        # prove the capability itself cannot run (scraper did not start) and successes
        # update capability health. Internal contract errors never degrade it (CP6).
        if _registry is not None and _capability_id:
            try:
                _route_evidence = json.dumps({
                    "run_id": run_id, "route_id": route["route_id"],
                    "state": acquisition["state"], "failure_class": failure_class,
                    "reason": _redact(str(acquisition.get("reason") or ""), 300),
                }, ensure_ascii=False)[:900]
                if failure_class in ("INTERNAL_CONTRACT_ERROR", "NO_STRATEGY", "USER_CANCELLED",
                                     "ROUTE_SKIPPED"):
                    pass  # never attribute these to commercial capability health
                elif _success:
                    _registry.report_outcome(_capability_id, True, scope="capability")
                    _registry.report_outcome(
                        _capability_id, True, scope="route", route_id=route["route_id"],
                        marketplace=route["marketplace"], state=acquisition["state"],
                        evidence=_route_evidence)
                elif not acquisition.get("scraper_started"):
                    # Capability-level: the scraper never started (config/resource).
                    _registry.report_outcome(
                        _capability_id, False, scope="capability",
                        error_message=_redact(str(acquisition.get("reason") or ""), 300))
                    _registry.report_outcome(
                        _capability_id, False, scope="route", route_id=route["route_id"],
                        marketplace=route["marketplace"], state=acquisition["state"],
                        evidence=_route_evidence)
                else:
                    # Route-level commercial/extraction failure: do NOT block the capability.
                    _registry.report_outcome(
                        _capability_id, False, scope="route", route_id=route["route_id"],
                        marketplace=route["marketplace"], state=acquisition["state"],
                        evidence=_route_evidence)
            except Exception as _ro_exc:
                state["registry_outcome_error"] = f"{type(_ro_exc).__name__}: {_ro_exc}"
        if experience_store is not None:
            try:
                _trace = {
                    "run_id": run_id, "marketplace": route["marketplace"],
                    "route_id": route["route_id"], "route_url": route["url"],
                    "capability_id": _capability_id,
                    "strategy_selected": strategy_id,
                    "strategy_executed": strategy_id,
                    "fallback_reason": None,
                    "failure_class": failure_class,
                    "acquisition_outcome": acquisition["state"],
                    "exception_type": acquisition.get("exception_type"),
                    "exception_message": acquisition.get("exception_message"),
                    "trace_id": acquisition.get("trace_id"),
                    "scraper_started": bool(acquisition.get("scraper_started")),
                    "publications_observed": len(observations),
                    "evidence_reference": f"verified_route:{route.get('experience_id')}",
                }
                experience_store.record_experience(
                    marketplace=route["marketplace"], brand="Nicopoly",
                    knowledge_type="DECISION_TRACE",
                    value=f"{run_id}:{route['marketplace']}:{route['route_id']}",
                    source_url=route["url"], page_type="ROUTE_AUDIT",
                    status="VALIDATED" if _success else "FAILED",
                    is_success=_success,
                    evidence_reference=json.dumps(_trace, ensure_ascii=False)[:3500])
                if strategy_id:
                    experience_store.record_strategy(
                        marketplace=route["marketplace"], brand="Nicopoly",
                        strategy_id=strategy_id, strategy_type="ROUTE_AUDIT",
                        surface=route["url"],
                        hypothesis="verified route reuses selected capability",
                        attempt=1,
                        result="SUCCESS" if _success else "FAILED",
                        evidence=json.dumps(_trace, ensure_ascii=False)[:400],
                        confidence=0.9)
            except Exception as _tr_exc:
                state["trace_error"] = f"{type(_tr_exc).__name__}: {_tr_exc}"
        results.append(state)
        if progress_cb:
            try:
                progress_cb({"stage": "route", "route_index": index, "routes_total": total,
                             "route": route, "result": state})
            except Exception:
                pass
        _checkpoint("RUNNING" if index < total else run_status)

    counters = _route_counters(results, selected_total)
    by_market: Dict[str, Dict[str, int]] = {}
    for r in results:
        bucket = by_market.setdefault(r["marketplace"], {
            "routes_processed": 0, "found": 0, "empty_verified": 0,
            "source_blocked": 0, "failed": 0, "no_viable": 0, "publications": 0})
        bucket["routes_processed"] += 1
        bucket["publications"] += r["publications"]
        key = {"FOUND": "found", "EMPTY_VERIFIED": "empty_verified",
               "SOURCE_BLOCKED": "source_blocked", "AUTH_REQUIRED": "source_blocked",
               "NO_VIABLE_CAPABILITY": "no_viable"}.get(r["state"], "failed")
        bucket[key] += 1
    summary: Dict[str, Any] = {
        "mode": "AUDIT_VERIFIED_ROUTES", "run_id": run_id,
        "marketplace": marketplace, "scope": scope, "brand": brand,
        "started_at": started, "finished_at": datetime.now().isoformat(),
        "elapsed_seconds": round(time.time() - t0, 2), "run_status": run_status,
        "routes_available": selection["routes_available"],
        "routes_eligible": selection["routes_eligible"],
        "routes_selected": selected_total,
        "routes_skipped": selection["routes_skipped"],
        "selection_reason": selection["selection_reason"],
        "total_scope_claim": selection["total_scope_claim"],
        "experience_source": selection.get("experience_source"),
        "resumed_from": selection.get("resumed_from"),
        "already_completed": selection.get("already_completed"),
        "frozen_selection": selection.get("frozen_selection"),
        "selection_fingerprint": selection.get("selection_fingerprint"),
        "selection_snapshot_path": selection.get("selection_snapshot_path"),
        "resume_scope_warning": selection.get("resume_scope_warning"),
        "routes_processed": counters["routes_processed"],
        "routes_completed": counters["routes_completed"],
        "routes_failed": counters["routes_failed"],
        "routes_blocked": counters["routes_blocked"],
        "routes_no_viable_strategy": counters["routes_no_viable_strategy"],
        "routes_not_started": counters["routes_not_started"],
        "routes_remaining": counters["routes_remaining"],
        "routes": results,
        "by_marketplace": by_market,
        "publications_observed": sum(r["publications"] for r in results),
        "positions_observed": sum(r["positions_observable"] for r in results),
        "position_evidence_rate": round(
            (sum(r["positions_observable"] for r in results) /
             max(1, sum(r["publications"] for r in results))), 4),
        "checkpoint_path": str(checkpoint_path(run_id)),
    }
    summary["acceptance"] = build_scope_acceptance(summary)
    save_checkpoint(run_id, {
        "run_id": run_id, "mode": "AUDIT_VERIFIED_ROUTES",
        "marketplace": marketplace, "scope": scope,
        "started_at": started, "updated_at": summary["finished_at"],
        "run_status": run_status, "routes_selected": selected_total,
        "routes": results, "acceptance": summary["acceptance"],
        "selection_fingerprint": selection.get("selection_fingerprint"),
        "selection_snapshot_path": selection.get("selection_snapshot_path"),
        "frozen_selection": selection.get("frozen_selection"),
        "resume_scope_warning": selection.get("resume_scope_warning"),
        "counters": counters,
    })
    return summary
