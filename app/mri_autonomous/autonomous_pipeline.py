"""
Autonomous discovery -> MRI pipeline.
MARKETPLACE + NICOPOLY -> discover categories -> observe publications -> materialize MRI
Uses only brand hub as seed. No SVMP, no category list, no preconfigured URLs.
"""

import asyncio
import hashlib
import json
import logging
import sqlite3
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from app.mri_autonomous.brand_hubs import brand_hub_for
from app.mri_autonomous.category_discoverer import discover_categories_from_page, category_name_from_url
from app.mri_autonomous.pagination import build_pagination_plan
def _explicit_target_identity(product, brand):
    """Relevance requires an explicit product field, never search/context hints."""
    target = str(brand or "").strip().casefold()
    observed = str(product.get("vendor") or product.get("brand") or "").strip().casefold()
    return bool(target and observed == target)


VA_ROOT = Path(__file__).resolve().parents[2]
from app.mri_autonomous.category_discoverer import (
    build_navigation_candidates, choose_navigation_strategy,
    choose_facet_strategy_decision, facet_signals_verified,
    build_facet_url, brand_effect_verified, prioritize_children)
from mri_commercial_materialization_golden_slice.v001.materializer_engine import GenericCommercialMaterializer
from mri_post_audit_pipeline.v001.post_audit_materializer import PostAuditMaterializer
from app.config.settings import DB_PATH

logger = logging.getLogger(__name__)

# Surfaces discovered per marketplace will be recorded with evidence
# ML FACET blocklist: URLs that are attribute/filter variants, not taxonomy categories.
# Observed offenders in Run 4: "Filtersavailablesidebar" (sidebar filter),
# "blazer-nicopoly#D[R:nicopoly,P:1,Q:5]" (hash-encoded search state).
ML_FACET_PATTERNS = [
    r'_(?:Desde|PriceRange|OrderId|Discount|Offset)_[^/]+',
    r'Filtrable',   # explicit ML facet filter suffix
    r'Noindex',     # ML no-index facet
    r'%2[aA]',      # encoded asterisk * used in ML facet URLs
    r'\*',          # raw asterisk facet separator
    r'#',           # hash fragments encode search/filter state, NOT categories
    r'_Filters',    # sidebar filter variants (Filtersavailablesidebar, etc.)
    r'Sidebar',     # sidebar navigation facets
    r'_Available',  # stock-filter facets
]


HUB_RETRY_SKIP_THRESHOLD = 2


def should_retry_hub(consecutive_empty_runs: int) -> bool:
    """Experience policy: retry a hub scrape only while the hub has not
    gone empty too many times in a row. Each double-empty already costs
    two bounded attempts plus challenge evidence, so after
    HUB_RETRY_SKIP_THRESHOLD consecutive double-empties the retry is
    skipped (single attempt). Success resets the streak via the normal
    experience update path."""
    return int(consecutive_empty_runs or 0) < HUB_RETRY_SKIP_THRESHOLD


def resume_coverage_status(hub_skipped: bool, has_other_categories: bool,
                           controlled_stop: bool):
    """Pure rule (MRI-AUTONOMY-001): a resumed run whose frontier was fully
    completed by the parent must not report NOT_DISCOVERED. Returns a coverage
    override or None (None = keep the normal classification)."""
    if hub_skipped and not has_other_categories and not controlled_stop:
        return "PARTIAL"
    return None


def next_no_progress_streak(streak: int, new_unique_count: int) -> int:
    """VA-MRI-4MP-E2E-FAILURE-RESOLUTION-001: consecutive no-new-observations streak."""
    if (new_unique_count or 0) > 0:
        return 0
    return int(streak or 0) + 1


def no_progress_should_stop(streak: int, limit) -> bool:
    """Bounded stop: True when `streak` consecutive categories produced no new
    unique observations and a positive limit is configured (0/None disables)."""
    try:
        lim = int(limit)
    except Exception:
        return False
    return lim > 0 and int(streak or 0) >= lim

_FRONTIER_TERMINAL_CLASSES = (
    "NON_COMMERCIAL", "BRAND_NAVIGATION", "GENERAL_NAVIGATION", "CORPORATE_NAVIGATION",
)


def classify_unvisited_terminal(cat: dict) -> dict:
    """MRI-RIPLEY-FRONTIER-VALIDATION-001 / VA-FINAL-RESOLUTION-LOOP-001: under a
    controlled stop or run completion every unvisited node must reach a terminal
    classification (bounded stop; nothing is left QUEUED/NOT_VISITED forever)."""
    st = cat.get("category_type") or cat.get("surface_classification")
    if st in _FRONTIER_TERMINAL_CLASSES:
        cat["stop_reason"] = st
        cat["coverage_status"] = "TERMINAL"
    else:
        cat["stop_reason"] = "OPERATIONAL_BATCH_LIMIT_REACHED"
        cat["coverage_status"] = "EXHAUSTED"
    return cat


def decide_coverage_status(final_categories, *, resume_override, controlled_stop,
                           any_discovered_categories, base_notes_text="") -> tuple:
    """VA-FINAL-RESOLUTION-LOOP-001: closure decision keyed on RELEVANT pending work.

    Cases (mission contract):
      A) raw=0 & relevant=0 -> full execution; may be CONFIRMED.
      B) raw>0 but every remaining node is verifiably pruned (relevant=0) -> the
         pruned raw frontier alone never forces an incomplete verdict.
      C) relevant>0 -> never certifies complete coverage.
      D) blocked/timeout relevance undetermined -> BLOCKED/PARTIAL; never NOT_FOUND.
      E) bounded stop lives in the crawl loop (controlled stop -> terminal states);
         this function only consumes terminal accounts.
    Returns (coverage_status, notes, accounting)."""
    from app.mri_autonomous.category_discoverer import frontier_relevance_accounting
    notes = []
    acc = frontier_relevance_accounting(final_categories)
    if acc["relevant_pending_work"]:
        notes.append(
            "COVERAGE_PARTIAL: relevant frontier remaining "
            "%d of raw %d (irrelevance requires verified evidence)"
            % (acc["relevant_frontier_remaining"], acc["raw_frontier_remaining"]))
        return "PARTIAL", notes, acc
    if acc["raw_frontier_remaining"] > 0:
        notes.append(
            "FRONTIER_RAW_PRUNED: %d raw node(s) verifiably pruned as irrelevant "
            "(deterministic classification + evidence); relevant pending = 0"
            % acc["raw_frontier_remaining"])
    _hub_rec = next((c for c in (final_categories or [])
                     if c.get("category_name") == "Brand Hub"), None)
    if resume_override:
        notes.append(
            "RESUME_COMPLETE: frontier processed by parent run (checkpoint); "
            "nothing re-scraped (duplicate_completed_work=0)")
        return resume_override, notes, acc
    if _hub_rec is not None and (_hub_rec.get("stop_reason") or "") not in ("EXHAUSTION",):
        notes.append(
            "COVERAGE_PARTIAL: Brand Hub stop=%s pages=%s"
            % (_hub_rec.get("stop_reason"), _hub_rec.get("pages_traversed")))
        return "PARTIAL", notes, acc
    if controlled_stop:
        notes.append("CONTROLLED_STOP active: remaining facets NOT_VISITED by operator flag")
        return "PARTIAL", notes, acc
    if final_categories and any(c.get("products_found", 0) > 0 for c in final_categories):
        _non_seed = [c for c in final_categories if not c.get("is_seed_surface")]
        _unresolved_blocked = [
            c for c in _non_seed
            if c.get("coverage_status") == "BLOCKED"
            or c.get("stop_reason") in ("BLOCKED", "CATEGORY_BUDGET_EXCEEDED", "EXTRACTOR_FAILURE")
        ]
        if _unresolved_blocked:
            notes.append(
                "COVERAGE_PARTIAL: %d unresolved blocked node(s) prevent relevance resolution"
                % len(_unresolved_blocked))
            return "PARTIAL", notes, acc
        _non_seed_certified = [c for c in _non_seed if c.get("node_status") == "CERTIFIED"]
        if _non_seed and not _non_seed_certified:
            notes.append("COVERAGE_PARTIAL: discovered non-seed branches terminal but none CERTIFIED")
            return "PARTIAL", notes, acc
        return "CONFIRMED", notes, acc
    if any_discovered_categories:
        return "PARTIAL", notes, acc
    return ("BLOCKED" if "BLOCKED" in str(base_notes_text) else "NOT_DISCOVERED"), notes, acc


def make_category_done_payload(
    marketplace: str,
    batch_number: int,
    batch_started_at: str,
    category_name: str,
    category_url: str,
    pages_traversed: int,
    stop_reason: str,
    failure_type: str | None,
    raw_count: int,
    new_unique_count: int,
    cumulative_unique_count: int,
    products: list,
    brand_evidence_count: int,
    **kwargs
) -> dict:
    """Build canonical category_done event payload guaranteeing brand evidence emission."""
    payload = {
        "kind": "category_done",
        "marketplace": marketplace,
        "batch_number": batch_number,
        "batch_started_at": batch_started_at,
        "category_name": category_name,
        "category_url": category_url,
        "pages_traversed": pages_traversed,
        "stop_reason": stop_reason,
        "failure_type": failure_type,
        "raw_count": raw_count,
        "brand_evidence_count_text": brand_evidence_count,
        "brand_present": brand_evidence_count,
        "new_unique_count": new_unique_count,
        "cumulative_unique_count": cumulative_unique_count,
        "products": products,
        "timed_out": False,
    }
    payload.update(kwargs)
    return payload


def sanitize_surfaces(categories, marketplace: str, hub_url: str):
    """Pure surface sanitizer (no I/O): dedupes by base URL, rejects ML
    facet variants, and drops any facet that IS the seed hub URL
    (self-link would duplicate the seed surface rows and fabricate
    multi-membership). Returns (sanitized, invalid_edges, notes)."""
    sanitized = []
    seen_base_urls = {hub_url}
    invalid_edges = 0
    notes = []
    for cat in categories:
        url = cat["category_url"]
        base_url = url
        if marketplace.lower() == "mercado libre":
            base_url = url.split('#')[0]
            base_url = re.sub(r'_(?:Desde|PriceRange|OrderId|Discount|Offset)_[^/]+', '', base_url)
            is_facet = any(
                re.search(pat, base_url, re.IGNORECASE)
                for pat in ML_FACET_PATTERNS if pat != r'#'
            )
            if is_facet:
                invalid_edges += 1
                cat["stop_reason"] = "EXTRACTOR_FAILURE"
                cat["coverage_status"] = "BLOCKED"
                cat["evidence"] = cat.get("evidence", "") + " | FACET_URL_REJECTED: not a CATEGORY node"
                continue
        if base_url in seen_base_urls:
            invalid_edges += 1
            if base_url == hub_url:
                notes.append(f"SELF_LINK_DROPPED: facet is the seed hub URL itself: {url}")
            continue
        seen_base_urls.add(base_url)
        cat["sanitized_url"] = base_url
        sanitized.append(cat)
    return sanitized, invalid_edges, notes


def pending_node_record(category, marketplace, brand_first_gap):
    """Describe known node evidence; never synthesize missing identity fields."""
    from app.mri_autonomous.category_discoverer import _verifiably_irrelevant
    try:
        direct_count = int(category.get("target_brand_present") or 0)
    except (TypeError, ValueError):
        direct_count = 0
    witnesses = category.get("target_membership_product_ids") or []
    evidence_type = None
    state = "UNRESOLVED"
    if witnesses or direct_count > 0 or category.get("brand_evidence_found") is True:
        state = "REQUIRED"
        evidence_type = "target_product_membership" if witnesses else "direct_target_brand_evidence"
    elif _verifiably_irrelevant(category):
        state = "REJECTED_AS_UNPROVEN"
        evidence_type = "non_commercial_classification"
    return {
        "marketplace": marketplace,
        "node_id": category.get("surface_id") or category.get("category_id") or category.get("candidate_id"),
        "surface_url": category.get("category_url") or category.get("surface_url"),
        "surface_name": category.get("category_name") or category.get("surface_name"),
        "discovery_method": category.get("discovery_method") or category.get("provenance"),
        "relevance_state": state,
        "relevance_evidence_type": evidence_type,
        "relevance_evidence": {
            "target_membership_product_ids": witnesses,
            "target_brand_present": category.get("target_brand_present"),
            "brand_evidence_found": category.get("brand_evidence_found"),
            "classification_evidence": category.get("classification_evidence"),
        },
        "stop_reason": category.get("stop_reason"),
        "block_reason": category.get("failure_type"),
        "brand_first_gap": brand_first_gap,
    }


def merge_observed_memberships(existing, incoming, surface_name, surface_url):
    """Union observed edges without replacing commercial membership with a seed.

    A name without a URL is retained as unresolved metadata, never used to
    invent a route. Names and URLs remain aligned; exact edges are unique.
    """
    edges = []
    for record in (existing, incoming):
        names = record.get("_discovered_categories") or []
        urls = record.get("_discovered_category_urls") or []
        if not isinstance(names, list) or not isinstance(urls, list):
            continue
        for index, name in enumerate(names):
            if not isinstance(name, str) or not name.strip():
                continue
            url = urls[index] if index < len(urls) else None
            url = url if isinstance(url, str) and url else None
            edge = (name, url)
            if edge not in edges:
                edges.append(edge)
    if (surface_name, surface_url) not in edges:
        edges.append((surface_name, surface_url))
    existing["_discovered_categories"] = [name for name, _ in edges]
    existing["_discovered_category_urls"] = [url for _, url in edges]


async def autonomous_discover_marketplace(marketplace: str, brand: str = "Nicopoly", max_categories: int = 12, headless: bool = True, category_budget_seconds: int = 300, progress_sink=None, max_batches: int = None, resume_state: Dict[str, Any] = None, no_progress_limit: int = 12) -> Dict[str, Any]:
    """
    Real autonomous discovery for a single marketplace.
    Returns discovered_categories with evidence and products.

    category_budget_seconds: operational time budget per category scrape. A hung
        extractor yields CATEGORY_BUDGET_EXCEEDED (PARTIAL) instead of killing
        the run. This is a traversal budget, not an expected result count.
    progress_sink: optional async callable receiving per-category progress
        payloads (batch evidence) as they occur. Used for live event/row/
        checkpoint persistence. None preserves legacy in-memory behavior.
    """
    hub = brand_hub_for(marketplace, brand)
    hub_url = hub.canonical_reference
    discovered_categories: List[Dict[str, Any]] = []
    products_by_category: Dict[str, List[Dict]] = {}
    all_products: List[Dict] = []
    coverage_status = "UNVERIFIED"
    evidence_notes = []
    # Initialize at function scope — prevents UnboundLocalError when scraper
    # fails before reaching the sanitization section inside the try block.
    sanitized_categories: List[Dict[str, Any]] = []
    invalid_edges: int = 0
    _facet_remainder_accounting: Dict[str, int] = {"raw": 0, "relevant": 0, "pruned": 0}
    _remainder_nodes = []
    brand_first_gap = None


    # Lazy imports to avoid hard dependency at import time
    try:
        from app.scrapers.paris_scraper import ParisScraper
        from app.scrapers.falabella_scraper import FalabellaScraper
        from app.scrapers.mercadolibre_scraper import MercadoLibreScraper
        from app.scrapers.ripley_scraper import RipleyScraper
    except Exception as e:
        return {
            "marketplace": marketplace,
            "target_brand": brand,
            "hub_url": hub_url,
            "discovered_categories": [],
            "products": [],
            "coverage_status": "BLOCKED",
            "evidence": f"Scraper import failed: {e}",
            "discovery_method": hub.discovery_method
        }

    scraper = None
    mkt_low = marketplace.lower()
    if mkt_low == "paris":
        scraper = ParisScraper(headless=headless)
    elif mkt_low == "falabella":
        scraper = FalabellaScraper(headless=headless)
    elif "mercado" in mkt_low:
        scraper = MercadoLibreScraper(headless=headless)
    elif mkt_low == "ripley":
        scraper = RipleyScraper(headless=headless)
    else:
        return {"marketplace": marketplace, "target_brand": brand, "hub_url": hub_url, "discovered_categories": [], "products": [], "coverage_status": "BLOCKED", "evidence": f"Unknown marketplace {marketplace}", "discovery_method": hub.discovery_method}

    # Experience Store integration
    from app.mri_autonomous.experience_store import ExperienceStore
    exp_store = ExperienceStore()
    prior_experiences = exp_store.get_all_experiences(marketplace=marketplace, brand=brand)
    logger.info(f"[{marketplace}] EXPERIENCE_LOADED: {len(prior_experiences)} prior records")

    try:
        await scraper.start()
        # 1) Navigate to hub and extract facets
        try:
            nav_hub_url = f"{hub_url.rstrip('/')}/listado/" if "mercado" in marketplace.lower() and "/listado" not in hub_url else hub_url
            ok = await scraper.navigate(nav_hub_url)
            if not ok:
                raise Exception("navigate returned False")
        except Exception as e:
            # Try to continue - page may still have content
            logger.warning(f"[{marketplace}] hub navigate warning: {e}")
        # Ensure page exists and wait a bit
        await asyncio.sleep(3)
        try:
            await scraper.page.wait_for_selector("a, [class*='product'], [class*='Product']", timeout=8000)
        except Exception:
            pass
        # Extract category URLs
        facet_urls = await discover_categories_from_page(scraper.page, marketplace, hub_url, brand=brand)

        # Merge with prior LAST_GOOD / VALIDATED categories from Experience Store
        for exp in prior_experiences:
            if exp["knowledge_type"] == "CATEGORY" and exp["status"] in ("LAST_GOOD", "VALIDATED"):
                u = exp["source_url"] or exp["value"]
                if u and u.startswith("http") and u not in facet_urls:
                    facet_urls.insert(0, u)
                    logger.info(f"[{marketplace}] LAST_GOOD_SELECTED & REVALIDATION_STARTED: {u}")
        # Also try to infer categories from visible filter chips text if no URLs
        if not facet_urls:
            try:
                chips = await scraper.page.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll("[class*='facet'] *, [class*='filter'] *, [class*='chip'] *, a"));
                    return els.map(e=>e.innerText).filter(t=>t && t.length<40).slice(0,30);
                }""")
                evidence_notes.append(f"Fallback chips: {chips[:10]}")
            except Exception as ce:
                evidence_notes.append(f"chips fallback failed: {ce}")
        
        # Systemic surface classification (core model, not URL lists):
        # every candidate is classified; PDP / PAGINATION / SORT / FACET /
        # CORPORATE surfaces can never become taxonomy nodes. Only
        # BRAND_SURFACE / COMMERCIAL_CATEGORY / SEARCH_VARIANT stay
        # CANDIDATE pending direct commercial evidence at certify time.
        from app.mri_autonomous.surface_classifier import classify_surface
        sc_excluded = {"PDP", "PAGINATION", "SORT_VARIANT",
                       "FULFILLMENT_FACET", "ATTRIBUTE_FACET",
                       "CORPORATE_NAVIGATION", "GENERAL_NAVIGATION"}

        # Experience-driven skip: surfaces with >=3 consecutive recorded
        # failures are not re-attempted (failed strategies persist to avoid
        # repeating known errors). Each skip is a logged decision.
        experience_decisions = [{
            "timestamp": datetime.now().isoformat(),
            "event": "EXPERIENCE_LOADED",
            "marketplace": marketplace,
            "prior_records": len(prior_experiences),
        }]
        strategy_attempts = []
        fail_map = {}
        for exp in prior_experiences:
            if exp["knowledge_type"] == "CATEGORY" and (exp["consecutive_failures"] or 0) >= 3:
                fail_map[exp["source_url"] or exp["value"]] = exp["consecutive_failures"]
        skipped_known_failures = []

        # Pagination evidence collection (MRI-AUTONOMY-001): observed page links
        # for the SAME path as the hub are traversal evidence (never taxonomy
        # nodes). They drive real page-to-page traversal in the hub scrape.
        pagination_candidates = []

        # Build discovered category records
        for url in facet_urls[:max_categories]:
            if url in fail_map:
                skipped_known_failures.append(url)
                experience_decisions.append({
                    "timestamp": datetime.now().isoformat(),
                    "event": "STRATEGY_S_SELECTED_BECAUSE_EXPERIENCE",
                    "strategy": "skip-known-failures",
                    "reason": f"consecutive_failures={fail_map[url]} recorded; skipping re-attempt",
                    "surface_url": url,
                })
                try:
                    exp_store.record_strategy(
                        marketplace=marketplace, brand=brand,
                        strategy_id=f"skip:{url}",
                        strategy_type="skip-known-failures",
                        surface=url,
                        hypothesis="re-attempt would repeat a known failure",
                        attempt=int(fail_map[url]) + 1,
                        result="SKIPPED",
                        evidence=f"consecutive_failures={fail_map[url]}",
                    )
                except Exception as _rse:
                    logger.warning(f"[{marketplace}] strategy record failed (non-fatal): {_rse}")
                logger.info(f"[{marketplace}] SKIP_KNOWN_FAILURE (experience): {url}")
                continue
            name = category_name_from_url(url, brand=brand) or "Unknown"
            # Deduplicate by name
            if any(c["category_name"].lower() == name.lower() for c in discovered_categories):
                continue
            cls = classify_surface(url, {"brand": brand})
            if cls["surface_type"] == "PAGINATION":
                from urllib.parse import urlparse as _urlparse
                if _urlparse(url).path == _urlparse(hub_url).path:
                    pagination_candidates.append(url)
            if cls["surface_type"] in sc_excluded:
                evidence_notes.append(
                    f"SURFACE_REJECTED: {url} classified {cls['surface_type']} "
                    f"({(cls['evidence'] or [''])[0]}); never a taxonomy node")
                continue
            discovered_categories.append({
                "marketplace": marketplace,
                "category_name": name,
                "category_url": url,
                "category_id": f"cat_{hashlib.md5((marketplace+name).encode()).hexdigest()[:8]}",
                "discovery_method": hub.discovery_method,
                "source": hub_url,
                "timestamp": datetime.now().isoformat(),
                "products_found": 0,
                "evidence": f"Discovered via facet extraction from {hub_url}",
                "coverage_status": "UNVERIFIED",
                "surface_type": "CATEGORY_BROWSE",
                "semantic_type": "CATEGORY",
                "surface_classification": cls["surface_type"],
                "classification_confidence": cls["confidence"],
                "classification_evidence": cls["evidence"],
                "node_certified": False,
                "node_type": None,
            })
        
        # Sanitize URLs to prevent Cartesian edge explosion (e.g., ML sorting/facet variants)
        _hub_pagination_plan = build_pagination_plan(hub_url, pagination_candidates)
        if _hub_pagination_plan:
            evidence_notes.append(
                f"PAGINATION_DISCOVERED: param={_hub_pagination_plan['param']} "
                f"pages={_hub_pagination_plan['observed_pages']} "
                f"(hub traversal will follow observed transitions)")
            try:
                exp_store.record_experience(
                    marketplace=marketplace, brand=brand,
                    knowledge_type="PAGINATION_MECHANISM",
                    value=f"{_hub_pagination_plan['param']}:{hub_url}",
                    source_url=hub_url, page_type="PAGINATION",
                    status="VALIDATED", is_success=True,
                    evidence_reference=f"observed page links: {_hub_pagination_plan['observed_pages'][:6]}",
                )
            except Exception as _pe:
                evidence_notes.append(f"pagination experience record failed (non-fatal): {_pe}")

        sanitized_categories, invalid_edges, _san_notes = sanitize_surfaces(
            discovered_categories, marketplace, hub_url)
        evidence_notes.extend(_san_notes)

        global_product_map = {} # marketplace_sku -> product dict

        def _cross_check_memberships(product):
            """Only observed target-product edges may expand required work."""
            if not _explicit_target_identity(product, brand):
                return
            from urllib.parse import urlparse
            for name, url in zip(product.get("_discovered_categories", []),
                                 product.get("_discovered_category_urls", [])):
                if not url or url == hub_url:
                    continue
                parsed = urlparse(url)
                if parsed.scheme not in ("http", "https") or parsed.netloc != urlparse(hub_url).netloc:
                    continue
                cls = classify_surface(url, {"brand": brand})
                if cls["surface_type"] != "COMMERCIAL_CATEGORY":
                    continue
                category = next((c for c in sanitized_categories
                                 if c["category_url"] == url), None)
                if category is None:
                    category = {
                        "marketplace": marketplace, "category_name": name,
                        "category_url": url, "is_seed_surface": False,
                        "surface_classification": "COMMERCIAL_CATEGORY",
                        "discovery_method": "TARGET_PRODUCT_MEMBERSHIP",
                        "classification_evidence": cls.get("evidence", []),
                        "stop_reason": "QUEUED", "coverage_status": "UNVERIFIED",
                        "products_found": 0,
                    }
                    sanitized_categories.append(category)
                witnesses = category.setdefault("target_membership_product_ids", [])
                identity = product.get("marketplace_sku") or product.get("url")
                if identity and identity not in witnesses:
                    witnesses.append(identity)
                category["brand_evidence_found"] = bool(witnesses)

        async def _emit_progress(payload: dict):
            if progress_sink is None:
                return
            try:
                await progress_sink(payload)
            except Exception as sink_e:
                logger.warning(f"[{marketplace}] progress_sink failed (non-fatal): {sink_e}")

        if len(facet_urls) > max_categories:
            _remainder_urls = facet_urls[max_categories:]
            _rem_relevant = 0
            _rem_pruned = 0
            for _ru in _remainder_urls:
                try:
                    _rc = classify_surface(_ru, {"brand": brand})
                except Exception:
                    _rc = {}
                _rcls = (_rc or {}).get("surface_type")
                _remainder_nodes.append({
                    "category_url": _ru,
                    "discovery_method": hub.discovery_method,
                    "surface_classification": _rcls,
                    "classification_evidence": (_rc or {}).get("evidence"),
                    "stop_reason": "CATEGORY_BUDGET_EXHAUSTED",
                })
                if (_rcls in ("NON_COMMERCIAL", "BRAND_NAVIGATION",
                              "GENERAL_NAVIGATION", "CORPORATE_NAVIGATION")
                        and (_rc or {}).get("evidence")):
                    _rem_pruned += 1
                else:
                    _rem_relevant += 1
            _facet_remainder_accounting = {
                "raw": len(_remainder_urls), "relevant": _rem_relevant, "pruned": _rem_pruned,
            }
            evidence_notes.append(
                f"CATEGORY_BUDGET_EXHAUSTED: {len(_remainder_urls)} of {len(facet_urls)} discovered "
                f"facets not visited within operational budget; deterministic accounting: "
                f"raw={len(_remainder_urls)}, relevant={_rem_relevant}, "
                f"pruned_with_evidence={_rem_pruned} (relevance never assumed)"
            )

        # SEED SURFACE FIRST (iteration-2 fix): the hub itself is a discovered
        # surface with direct evidence. Facet links may be unfiltered site nav
        # (e.g. Paris `?q=nicopoly` electro links), so the hub is always
        # scraped as batch 0 — never gated on facet presence. No hardcoded
        # categories; no SVMP.
        hub_batch_started_at = datetime.now().isoformat()
        hub_before_unique = len(global_product_map)
        _completed_urls = set((resume_state or {}).get("completed_urls", []))
        _batches_emitted = 0
        _controlled_stop = False
        _hub_skipped = False
        _consecutive_no_progress = 0
        nav_candidates = []
        nav_strategy = None
        nav_opened = None
        nav_anchors_total = None
        _nav_decisions = []
        _facet_decisions = []
        facet_probe_count = 0
        try:
            _mech_path = Path(VA_ROOT) / "outputs" / "mri_autonomy_004" / "diagnostic" / "mechanism.json"
            facet_mechanism = json.loads(_mech_path.read_text(encoding="utf-8")) if _mech_path.exists() else None
        except Exception:
            facet_mechanism = None
        facet_applied_count = 0
        try:
            async def _do_hub_scrape0():
                if hasattr(scraper, "scrape_autonomous_category"):
                    if getattr(scraper, "supports_pagination", False):
                        try:
                            return await scraper.scrape_autonomous_category(
                                hub_url, pagination=_hub_pagination_plan, brand=brand)
                        except TypeError:
                            pass
                    return await scraper.scrape_autonomous_category(hub_url)
                return {"products": await scraper.scrape_top_240(hub_url)}

            _hub_skipped = hub_url in _completed_urls
            if _hub_skipped:
                evidence_notes.append(
                    "RESUME_SKIP: Brand Hub already completed in parent run; not re-scraped")
                logger.info(f"[{marketplace}] RESUME_SKIP Brand Hub")
                hub_prods0 = []
            else:
                # Permitted recovery: a single bounded retry when the first
                # pass returns zero products (e.g. challenge page served).
                # Both attempts are recorded; a double-empty means the block
                # is external, not transient. Experience policy: after
                # HUB_RETRY_SKIP_THRESHOLD consecutive double-empties the
                # retry itself is skipped (logged decision).
                _hub_row = exp_store.get_experience_item(
                    marketplace, brand, "SURFACE", "Brand Hub")
                _hub_streak = int((_hub_row or {}).get("consecutive_failures") or 0)
                _allow_retry = should_retry_hub(_hub_streak)
                if not _allow_retry:
                    experience_decisions.append({
                        "timestamp": datetime.now().isoformat(),
                        "event": "STRATEGY_S_SELECTED_BECAUSE_EXPERIENCE",
                        "strategy": "hub-no-retry-on-streak",
                        "reason": f"Brand Hub double-empty streak={_hub_streak}; skipping retry",
                        "surface_url": hub_url,
                    })
                    try:
                        exp_store.record_strategy(
                            marketplace=marketplace, brand=brand,
                            strategy_id="hub-no-retry-on-streak",
                            strategy_type="hub-no-retry-on-streak",
                            surface=hub_url,
                            hypothesis="retry after double-empty wastes budget on persistent block",
                            attempt=int(_hub_streak) + 1,
                            result="SKIPPED",
                            evidence=f"streak={_hub_streak} double-empties",
                        )
                    except Exception as _rse2:
                        logger.warning(f"[{marketplace}] hub strategy record failed (non-fatal): {_rse2}")
                    logger.info(f"[{marketplace}] HUB_NO_RETRY (experience streak={_hub_streak})")
                hub_prods0 = []
                hub_pages_meta = None
                hub_stop_meta = None
                hub_pagination_meta = None
                hub_sort_meta = None
                for _hi in (0, 1):
                    if _hi == 1 and not _allow_retry:
                        break
                    _h_start = datetime.now().isoformat()
                    hub_result0 = await asyncio.wait_for(
                        _do_hub_scrape0(), timeout=category_budget_seconds)
                    hub_prods0 = hub_result0.get("products", [])
                    hub_pages_meta = hub_result0.get("pages_traversed", 1)
                    hub_stop_meta = hub_result0.get("stop_reason", "EXHAUSTION")
                    hub_pagination_meta = hub_result0.get("pagination")
                    hub_sort_meta = hub_result0.get("sort_mode")
                    strategy_attempts.append({
                        "attempt_id": f"{marketplace}:Brand Hub:hub:{_hi}",
                        "strategy": "hub-scrape" if _hi == 0 else "hub-retry-once",
                        "reason": "first attempt" if _hi == 0 else "first pass empty; single permitted retry",
                        "started_at": _h_start,
                        "finished_at": datetime.now().isoformat(),
                        "result": "SUCCESS" if hub_prods0 else "EMPTY",
                        "evidence": f"{len(hub_prods0)} products",
                        "next_decision": "USE_RESULT" if hub_prods0 or _hi == 1 else "RETRY_ONCE",
                    })
                    if hub_prods0 or _hi == 1:
                        break
                    await asyncio.sleep(5)
                if not hub_prods0 and not _hub_skipped:
                    # Double-empty feeds the streak so future runs can skip
                    # the retry; failed strategies persist, never deleted.
                    exp_store.record_experience(
                        marketplace=marketplace, brand=brand,
                        knowledge_type="SURFACE", value="Brand Hub",
                        source_url=hub_url, page_type="BRAND_SEARCH",
                        status="FAILED", is_success=False,
                        evidence_reference="hub double-empty: challenge/block, not transient",
                    )
            for p in hub_prods0:
                sku = p.get("marketplace_sku") or p.get("title", "")
                if sku not in global_product_map:
                    global_product_map[sku] = dict(p, _discovery_method=hub.discovery_method)
                    all_products.append(global_product_map[sku])
                merge_observed_memberships(global_product_map[sku], p, "Brand Hub", hub_url)
                _cross_check_memberships(global_product_map[sku])
            if hub_prods0:
                from app.mri_autonomous.surface_classifier import certify_node as _hcert
                _hnico = sum(
                    1 for p in hub_prods0
                    if _explicit_target_identity(p, brand))
                _hcert_res = _hcert({"surface_type": "BRAND_SURFACE",
                                     "evidence": ["seed-surface:hub_url==brand terminal"]},
                                    len(hub_prods0), _hnico)
                sanitized_categories.insert(0, {
                    "marketplace": marketplace,
                    "is_seed_surface": True,
                    "category_name": "Brand Hub",
                    "category_url": hub_url,
                    "category_id": f"cat_{hashlib.md5((marketplace+'Brand Hub').encode()).hexdigest()[:8]}",
                    "discovery_method": hub.discovery_method,
                    "source": hub_url,
                    "timestamp": datetime.now().isoformat(),
                    "products_found": len(hub_prods0),
                    "evidence": "Seed surface scraped as batch 0 with direct evidence",
                    "coverage_status": "CONFIRMED" if _hcert_res["certified"] else "PARTIAL",
                    "stop_reason": hub_stop_meta or "EXHAUSTION",
                    "pages_traversed": hub_pages_meta or 1,
                    "pagination": hub_pagination_meta,
                    "sort_mode": hub_sort_meta,
                    "surface_type": "BRAND_SEARCH",
                    "semantic_type": "SURFACE",
                    "surface_classification": "BRAND_SURFACE",
                    "node_certified": _hcert_res["certified"],
                    "node_type": _hcert_res.get("node_type"),
                    "target_brand_present": _hnico,
                })
                exp_store.record_experience(
                    marketplace=marketplace, brand=brand, knowledge_type="SURFACE",
                    value="Brand Hub", source_url=hub_url, page_type="BRAND_SEARCH",
                    status="LAST_GOOD" if _hcert_res["certified"] else "VALIDATED",
                    is_success=True,
                    evidence_reference=f"batch0: {len(hub_prods0)} products, {_hnico} target brand",
                )
                products_by_category["Brand Hub"] = hub_prods0
                await _emit_progress(make_category_done_payload(
                    marketplace=marketplace,
                    batch_number=0,
                    batch_started_at=hub_batch_started_at,
                    category_name="Brand Hub",
                    category_url=hub_url,
                    pages_traversed=hub_pages_meta or 1,
                    stop_reason=hub_stop_meta or "EXHAUSTION",
                    failure_type=None,
                    raw_count=len(hub_prods0),
                    new_unique_count=len(global_product_map) - hub_before_unique,
                    cumulative_unique_count=len(global_product_map),
                    products=hub_prods0,
                    brand_evidence_count=_hnico,
                    pagination=hub_pagination_meta,
                ))
                _batches_emitted += 1
        except asyncio.TimeoutError:
            evidence_notes.append(
                f"hub scrape CATEGORY_BUDGET_EXCEEDED after {category_budget_seconds}s"
            )
            await _emit_progress({
                "kind": "category_timeout",
                "marketplace": marketplace,
                "batch_number": 0,
                "batch_started_at": hub_batch_started_at,
                "category_name": "Brand Hub",
                "category_url": hub_url,
                "pages_traversed": 0,
                "stop_reason": "CATEGORY_BUDGET_EXCEEDED",
                "failure_type": "TIMEOUT",
                "raw_count": 0,
                "new_unique_count": 0,
                "cumulative_unique_count": len(global_product_map),
                "products": [],
                "timed_out": True,
            })
        except Exception as he:
            evidence_notes.append(f"hub scrape failed: {he}")

        if max_batches is not None and _batches_emitted >= max_batches:
            _controlled_stop = True
            evidence_notes.append(
                f"CONTROLLED_STOP: batch budget max_batches={max_batches} reached; "
                f"run stops here by operator flag (resume demo), not by exhaustion")

        batch_number = 0
        
        # Check for BRAND_FIRST_GAP
        brand_first_gap = None
        if not hub_prods0 and not _hub_skipped:
            brand_first_gap = "BRAND_ENTRY_BLOCKED" if hub_stop_meta == "BLOCKED" else "BRAND_ENTRY_EMPTY"
        elif hub_prods0:
            unresolved = sum(1 for p in global_product_map.values()
                             if _explicit_target_identity(p, brand) and not any(
                                 (p.get("marketplace_sku") or p.get("url")) in c.get("target_membership_product_ids", [])
                                 for c in sanitized_categories if not c.get("is_seed_surface")))
            if unresolved > 0:
                brand_first_gap = "UNRESOLVED_PRODUCT_MEMBERSHIP"
                
        # Check experience for gap resolution
        exp_store.record_experience(marketplace, brand, knowledge_type="EVENT", value="EXPERIENCE_LOOKUP", source_url="global_discovery", page_type="nav", status="INFO", is_success=True)
        _cert_urls = [exp["source_url"] for exp in prior_experiences if exp.get("knowledge_type") == "CATEGORY" and exp.get("status") in ("LAST_GOOD", "VALIDATED") and exp.get("source_url")]
        if _cert_urls and not brand_first_gap:
            exp_store.record_experience(marketplace, brand, knowledge_type="EVENT", value="EXPERIENCE_HIT", source_url="global_discovery", page_type="nav", status="INFO", is_success=True)
            exp_store.record_experience(marketplace, brand, knowledge_type="EVENT", value="EXPERIENCE_USED", source_url="global_discovery", page_type="nav", status="INFO", is_success=True)

        # ---- MRI-AUTONOMY-003: NAVIGATION SOURCE (network JSON) + fallback (menu anchors) ----
        try:
            if not brand_first_gap:
                evidence_notes.append("GLOBAL_DISCOVERY_ALLOWED = FALSE (No BRAND_FIRST_GAP observed)")
                logger.info(f"[{marketplace}] No BRAND_FIRST_GAP. Skipping global discovery.")
                nav_candidates = []
                _nav_source = None
            else:
                evidence_notes.append(f"BRAND_FIRST_GAP identified: {brand_first_gap}. Enabling GLOBAL_DISCOVERY fallback.")
                logger.info(f"[{marketplace}] BRAND_FIRST_GAP: {brand_first_gap}")
                _nav_source = None
            if brand_first_gap is not None and hasattr(scraper, "discover_navigation_source"):
                try:
                    await _emit_progress({"kind": "navigation_source_attempt", "marketplace": marketplace,
                                          "target_url": hub_url})
                    _nav_source = await scraper.discover_navigation_source(hub_url)
                except Exception as _nse:
                    evidence_notes.append(f"navigation source capture failed (non-fatal): {_nse}")
            if _nav_source and _nav_source.get("found") and isinstance(_nav_source.get("json"), (list, dict)):
                nav_strategy = "network_source"
                from app.mri_autonomous.category_discoverer import parse_navigation_source as _pns
                nav_candidates = _pns(_nav_source.get("json"), hub_url, brand, _nav_source.get("sha16") or "")
                _cert_urls = [exp["source_url"] for exp in prior_experiences if exp.get("knowledge_type") == "CATEGORY" and exp.get("status") in ("LAST_GOOD", "VALIDATED") and exp.get("source_url")]
                if _cert_urls:
                    nav_candidates = prioritize_children(nav_candidates, _cert_urls)
                try:
                    exp_store.record_strategy(marketplace, brand, strategy_id="nav::network_source",
                                              strategy_type="discover_navigation",
                                              surface=_nav_source.get("url") or hub_url,
                                              hypothesis="navigation tree served as network JSON on load",
                                              attempt=1, result="SUCCESS" if nav_candidates else "FAILED",
                                              evidence=f"source={_nav_source.get('url')} sha16={_nav_source.get('sha16')} candidates={len(nav_candidates)}",
                                              confidence=0.85)
                    exp_store.record_strategy_outcome(marketplace, brand, "nav::network_source",
                                                      "SUCCESS" if nav_candidates else "FAILED", 0.85,
                                                      f"candidates={len(nav_candidates)}")
                except Exception as _se:
                    evidence_notes.append(f"nav source persist failed (non-fatal): {_se}")
                _src_dec = {"decision": "SELECTED_ALTERNATIVE", "capability": "discover_navigation",
                            "selected": "network_source",
                            "because": "menu anchors path recorded FAILED previously; validated network source available",
                            "evidence": f"source_url={_nav_source.get('url')} sha16={_nav_source.get('sha16')}"}
                _nav_decisions.append(_src_dec)
                await _emit_progress({"kind": "EXPERIENCE_DECISION", "marketplace": marketplace, **_src_dec})
                await _emit_progress({"kind": "navigation_source_found", "marketplace": marketplace,
                                      "source_url": _nav_source.get("url"), "sha16": _nav_source.get("sha16"),
                                      "candidates": len(nav_candidates)})
                nav_opened = None
                nav_anchors_total = None
            if brand_first_gap is not None and not nav_candidates:
                _prior_failed = []
                try:
                    _all_nav = exp_store.get_strategies(marketplace, brand) or []
                    _prior_failed = [s for s in _all_nav if s.get('result') == 'FAILED']
                except Exception:
                    _prior_failed = []
                _prior_ok = []
                try:
                    _prior_ok = exp_store.get_strategies(marketplace, brand) or []
                except Exception:
                    _prior_ok = []
                nav_strategy, _nav_decision = choose_navigation_strategy(_prior_failed, _prior_ok)
                if _nav_decision:
                    _nav_decisions.append(_nav_decision)
                    await _emit_progress({"kind": "EXPERIENCE_DECISION", "marketplace": marketplace, **_nav_decision})
                if hasattr(scraper, "discover_navigation"):
                    try:
                        if hasattr(scraper, "_navigate_ripley"):
                            await scraper._navigate_ripley(hub_url)
                    except Exception as _nve:
                        evidence_notes.append(f"hub surface ensure failed (non-fatal): {_nve}")
                    _nav_res = await scraper.discover_navigation(raw_only=(nav_strategy == "raw_dom_anchors"))
                else:
                    _nav_res = {"opened": False, "nodes": [], "anchors_total": 0, "evidence_locator": "no_navigation_support"}
                nav_opened = _nav_res.get("opened")
                nav_anchors_total = _nav_res.get("anchors_total")
                nav_candidates = build_navigation_candidates(_nav_res.get("nodes", []), hub_url, brand)
                _cert_urls = [exp["source_url"] for exp in prior_experiences if exp.get("knowledge_type") == "CATEGORY" and exp.get("status") in ("LAST_GOOD", "VALIDATED") and exp.get("source_url")]
                if _cert_urls:
                    nav_candidates = prioritize_children(nav_candidates, _cert_urls)
                _nav_label = "SUCCESS" if nav_candidates else "FAILED"
                try:
                    exp_store.record_strategy(marketplace, brand, strategy_id=f"nav::{nav_strategy}",
                                              strategy_type="discover_navigation", surface=hub_url,
                                              hypothesis="navigation exposes commercial category links",
                                              attempt=1, result=_nav_label,
                                              evidence=f"candidates={len(nav_candidates)} anchors={nav_anchors_total} opened={nav_opened}",
                                              confidence=0.7)
                    exp_store.record_strategy_outcome(marketplace, brand, f"nav::{nav_strategy}", _nav_label,
                                                      0.7, f"candidates={len(nav_candidates)}")
                except Exception as _se:
                    evidence_notes.append(f"nav strategy persist failed (non-fatal): {_se}")
                await _emit_progress({"kind": "navigation_discovered", "marketplace": marketplace,
                                      "strategy": nav_strategy, "menu_opened": nav_opened,
                                      "anchors_total": nav_anchors_total,
                                      "candidates": len(nav_candidates),
                                      "evidence_locator": _nav_res.get("evidence_locator")})
            if nav_candidates:
                _nav_records = []
                for c in nav_candidates[:1600]:
                    await _emit_progress({"kind": "NEW_CATEGORY_HYPOTHESIS", "marketplace": marketplace,
                                          "category_name": c["label"], "category_url": c["url"],
                                          "candidate_id": c["candidate_id"],
                                          "parent": c.get("parent"), "depth": c.get("depth"),
                                          "discovery_method": c["discovery_method"],
                                          "evidence_locator": c["evidence_locator"]})
                    _nav_records.append({"category_name": c["label"], "category_url": c["url"],
                                         "category_type": c["classification"].get("surface_type"),
                                         "is_seed_surface": False,
                                         "discovery_method": c["discovery_method"],
                                         "evidence_locator": c["evidence_locator"],
                                         "classification_evidence": c["classification"].get("evidence", []),
                                         "nav_parent": c.get("parent"), "nav_depth": c.get("depth"),
                                         "stop_reason": "QUEUED",
                                         "coverage_status": "QUEUED"})
                _seed_items = [c for c in sanitized_categories if c.get("is_seed_surface")]
                _san, _iv2, _n2 = sanitize_surfaces([c for c in sanitized_categories if not c.get("is_seed_surface")] + _nav_records, marketplace, hub_url)
                sanitized_categories = _seed_items + _san
                for _n in _n2:
                    evidence_notes.append(_n)
            await _emit_progress({"kind": "frontier_state", "marketplace": marketplace,
                                  "queued": [c["label"] for c in nav_candidates],
                                  "hub_processed": bool(locals().get("hub_prods0"))})
        except Exception as _ne:
            evidence_notes.append(f"navigation discovery failed (non-fatal): {_ne}")
        for cat in sanitized_categories:
            if cat.get("is_seed_surface"):
                # Already scraped as batch 0 above; re-scraping here would
                # duplicate the seed surface rows within the same run.
                continue
            if _controlled_stop:
                classify_unvisited_terminal(cat)
                continue
            url = cat["category_url"]
            if url in _completed_urls:
                evidence_notes.append(f"RESUME_SKIP: already completed in parent run: {url}")
                logger.info(f"[{marketplace}] RESUME_SKIP {cat['category_name']}")
                cat["stop_reason"] = "RESUME_SKIPPED"
                continue
            batch_number += 1
            batch_started_at = datetime.now().isoformat()
            before_unique = len(global_product_map)
            timed_out = False
            await _emit_progress({
                "kind": "category_attempt",
                "marketplace": marketplace,
                "batch_number": batch_number,
                "batch_started_at": batch_started_at,
                "category_name": cat["category_name"],
                "category_url": url,
            })
            try:
                # ---- MRI-AUTONOMY-002: FACET discovery/application (brand runtime var) ----
                _facet_state = {"applied": False, "max_pages": 1, "brand_option": False}
                _furl = None
                if getattr(scraper, "supports_navigation", False) and hasattr(scraper, "discover_facets"):
                    try:
                        _fprobe = await scraper.discover_facets()
                        facet_probe_count += 1
                        _bl = brand.strip().lower()
                        _brand_opt = any(_bl in (o or "").lower()
                                         for s in _fprobe.get("sections", [])
                                         for o in s.get("options", []))
                        cat["brand_facet_option_present"] = bool(_brand_opt)
                        if _brand_opt:
                            _facet_state["brand_option"] = True
                            _facet_state["max_pages"] = 3
                        await _emit_progress({"kind": "facet_discovered", "marketplace": marketplace,
                                              "batch_number": batch_number,
                                              "category_name": cat["category_name"],
                                              "category_url": url,
                                              "panel_opened": _fprobe.get("panel_opened"),
                                              "brand_option_present": bool(_brand_opt),
                                              "checkbox_count": _fprobe.get("checkbox_count"),
                                              "evidence_locator": _fprobe.get("evidence_locator")})
                        _mtype = (facet_mechanism.get("mechanism_type") or facet_mechanism.get("type") or "") if facet_mechanism else ""
                        if facet_mechanism and (_mtype == "URL_QUERY" or _mtype.startswith("URL_QUERY")):
                            _furl = build_facet_url(url, brand, facet_mechanism)
                            if _furl:
                                _sig_before = await scraper.page_signature()
                                await scraper._navigate_ripley(_furl)
                                await asyncio.sleep(4)
                                _sig_after = await scraper.page_signature()
                                _page_txt = await scraper.page.evaluate("() => (document.body.innerText || '').toLowerCase()")
                                _brand_count = _page_txt.count(brand.strip().lower())
                                _verified = brand_effect_verified(_sig_before, _sig_after, brand) and _brand_count > 0
                                _facet_state["applied"] = bool(_verified)
                                if _verified:
                                    facet_applied_count += 1
                                    cat["facet_applied_url"] = scraper.page.url
                                    cat["brand_context_hint"] = True
                                await _emit_progress({"kind": "facet_application", "marketplace": marketplace,
                                                      "batch_number": batch_number,
                                                      "category_name": cat["category_name"],
                                                      "category_url": url,
                                                      "mechanism": "URL_QUERY",
                                                      "facet_url": _furl,
                                                      "verified": bool(_verified),
                                                      "signals": str({"before": _sig_before, "after": _sig_after})[:400]})
                        if _brand_opt and _fprobe.get("panel_opened") and not _fprobe.get("unscoped"):
                            _f_dec = choose_facet_strategy_decision(exp_store, marketplace, brand, url)
                            _facet_decisions.append(_f_dec)
                            await _emit_progress({"kind": "EXPERIENCE_DECISION", "marketplace": marketplace,
                                                  "batch_number": batch_number, **_f_dec})
                            _sig_before = await scraper.page_signature()
                            _fres = await scraper.apply_brand_facet(brand) or {}
                            _sig_after = _fres.get("after") or {}
                            _verified = facet_signals_verified(_sig_before, _sig_after)
                            _facet_state["applied"] = bool(_verified)
                            if _verified:
                                facet_applied_count += 1
                                cat["facet_applied_url"] = scraper.page.url
                            await _emit_progress({"kind": "facet_application", "marketplace": marketplace,
                                                  "batch_number": batch_number,
                                                  "category_name": cat["category_name"],
                                                  "category_url": url,
                                                  "verified": bool(_verified),
                                                  "signals": str({"before": _sig_before, "after": _sig_after})[:400]})
                            _res_label = "SUCCESS" if _verified else "FAILED"
                            try:
                                exp_store.record_strategy(marketplace, brand,
                                                          strategy_id=f"facet::ui::{url}",
                                                          strategy_type="facet_apply", surface=url,
                                                          hypothesis="brand facet narrows the surface",
                                                          attempt=1, result=_res_label,
                                                          evidence=str(_sig_after)[:250], confidence=0.7)
                                exp_store.record_strategy_outcome(marketplace, brand,
                                                                  f"facet::ui::{url}", _res_label, 0.7,
                                                                  str(_sig_after)[:180])
                            except Exception:
                                pass
                    except Exception as _fe:
                        evidence_notes.append(f"facet step failed (non-fatal) {cat.get('category_name')}: {_fe}")
                # Recovery chain: primary extractor first; on TIMEOUT a single
                # alternative-extractor attempt (bounded); on other errors a
                # single same-method retry. Every attempt is recorded with
                # attempt_id/strategy/reason/timestamps/result/evidence.
                _methods = []
                if hasattr(scraper, "scrape_autonomous_category"):
                    _methods.append("scrape_autonomous_category")
                _methods.append("scrape_top_240")

                async def _do_one(_m):
                    if _m == "scrape_autonomous_category":
                        if getattr(scraper, "supports_pagination", False):
                            _target = (scraper.page.url if _facet_state.get("applied") else (_furl or url))
                            _mp = 3 if _facet_state.get("applied") else _facet_state.get("max_pages", 1)
                            return await scraper.scrape_autonomous_category(_target, brand=brand, max_pages=_mp)
                        return await scraper.scrape_autonomous_category(url)
                    prods = await scraper.scrape_top_240(url)
                    return {
                        "products": prods,
                        "pages_traversed": 1,
                        "stop_reason": "EXHAUSTION" if len(prods) > 0 else "NO_PROGRESS",
                        "failure_type": None,
                    }

                result = None
                _last_timeout = None
                for _mi, _mname in enumerate(_methods):
                    _a_start = datetime.now().isoformat()
                    _budget = category_budget_seconds if _mi == 0 else 120
                    if _mi > 0:
                        await _emit_progress({
                            "kind": "recovery_attempt",
                            "marketplace": marketplace,
                            "batch_number": batch_number,
                            "category_name": cat["category_name"],
                            "category_url": url,
                            "strategy": "alternative-extractor",
                            "reason": "primary timed out",
                        })
                    try:
                        result = await asyncio.wait_for(_do_one(_mname), timeout=_budget)
                        if _mi > 0:
                            await _emit_progress({
                                "kind": "recovery_result",
                                "marketplace": marketplace,
                                "batch_number": batch_number,
                                "category_name": cat["category_name"],
                                "category_url": url,
                                "result": "RECOVERY_SUCCEEDED",
                                "evidence": f"{len(result.get('products', []))} products via {_mname}",
                            })
                        strategy_attempts.append({
                            "attempt_id": f"{marketplace}:{cat['category_name']}:{_mname}:{_mi}",
                            "strategy": "primary-extractor" if _mi == 0 else "alternative-extractor",
                            "reason": "first attempt" if _mi == 0 else "primary timed out; alternative extractor",
                            "started_at": _a_start,
                            "finished_at": datetime.now().isoformat(),
                            "result": "SUCCESS",
                            "evidence": f"{len(result.get('products', []))} products via {_mname}",
                            "next_decision": "USE_RESULT",
                        })
                        break
                    except asyncio.TimeoutError as _te:
                        _last_timeout = _te
                        if _mi > 0:
                            await _emit_progress({
                                "kind": "recovery_result",
                                "marketplace": marketplace,
                                "batch_number": batch_number,
                                "category_name": cat["category_name"],
                                "category_url": url,
                                "result": "RECOVERY_FAILED",
                                "evidence": f"alternative {_mname} also timed out",
                            })
                        _more = _mi + 1 < len(_methods)
                        strategy_attempts.append({
                            "attempt_id": f"{marketplace}:{cat['category_name']}:{_mname}:{_mi}",
                            "strategy": "primary-extractor" if _mi == 0 else "alternative-extractor",
                            "reason": f"budget exceeded after {_budget}s",
                            "started_at": _a_start,
                            "finished_at": datetime.now().isoformat(),
                            "result": "TIMEOUT",
                            "evidence": f"{_mname} exceeded {_budget}s",
                            "next_decision": "TRY_ALTERNATIVE" if _more else "RECORD_FAILED",
                        })
                        continue
                if result is None:
                    raise _last_timeout

                prods = result.get("products", [])
                pages = result.get("pages_traversed", 0)
                # Default to EXTRACTOR_FAILURE (not UNKNOWN which is invalid per semantic model)
                stop_reason = result.get("stop_reason", "EXTRACTOR_FAILURE")
                failure_type = result.get("failure_type", None)
                
                cat["pages_traversed"] = pages
                cat["stop_reason"] = stop_reason
                cat["failure_type"] = failure_type
                
                # Tag each product with its discovered category
                for p in prods:
                    sku = p.get("marketplace_sku") or p.get("title", "")
                    if sku not in global_product_map:
                        global_product_map[sku] = dict(p, _discovery_method=hub.discovery_method)
                        all_products.append(global_product_map[sku])
                    # Union incoming and directly observed edges for this identity.
                    merge_observed_memberships(global_product_map[sku], p, cat["category_name"], url)
                    _cross_check_memberships(global_product_map[sku])
                        
                products_by_category[cat["category_name"]] = prods
                cat["products_found"] = len(prods)

                # Node certification (systemic model fix): a surface becomes a
                # taxonomy node ONLY with direct commercial evidence, i.e.
                # Nicopoly products observed on it. EXHAUSTION of a noise
                # surface is not CONFIRMED.
                from app.mri_autonomous.surface_classifier import certify_node as _certify
                _nico_here = sum(
                    1 for p in prods
                    if _explicit_target_identity(p, brand))
                _cert = _certify(
                    {"surface_type": cat.get("surface_classification", "COMMERCIAL_CATEGORY"),
                     "evidence": cat.get("classification_evidence", [])},
                    len(prods), _nico_here)
                cat["node_certified"] = _cert["certified"]
                cat["node_type"] = _cert.get("node_type")
                cat["cert_reason"] = _cert.get("evidence", _cert.get("reason"))
                cat["target_brand_present"] = _nico_here
                cat["brand_present"] = _nico_here
                cat["surface_id"] = url
                cat["provenance"] = cat.get("discovery_method") or "facet_urls"
                from app.mri_autonomous.category_discoverer import classify_node_status as _cns
                cat["node_status"] = _cns(_cert["certified"], stop_reason, len(prods), _nico_here)

                if stop_reason == "EXHAUSTION" and _cert["certified"]:
                    cat["coverage_status"] = "CONFIRMED"
                    exp_store.record_experience(
                        marketplace=marketplace, brand=brand, knowledge_type="CATEGORY",
                        value=cat["category_name"], source_url=url, page_type="CATEGORY_GRID",
                        status="LAST_GOOD", is_success=True, evidence_reference=f"Found {len(prods)} products, {_nico_here} target brand"
                    )
                    logger.info(f"[{marketplace}] REVALIDATION_PASS & LAST_GOOD persisted for category: {cat['category_name']}")
                elif stop_reason == "BLOCKED":
                    cat["coverage_status"] = "BLOCKED"
                    exp_store.record_experience(
                        marketplace=marketplace, brand=brand, knowledge_type="CATEGORY",
                        value=cat["category_name"], source_url=url, page_type="WAF",
                        status="FAILED", is_success=False, evidence_reference=f"Scrape blocked"
                    )
                else:
                    cat["coverage_status"] = "PARTIAL"
                    exp_store.record_experience(
                        marketplace=marketplace, brand=brand, knowledge_type="CATEGORY",
                        value=cat["category_name"], source_url=url, page_type="CATEGORY_GRID",
                        status="VALIDATED", is_success=True, evidence_reference=f"Partial stop: {stop_reason}"
                    )
                    
                logger.info(f"[{marketplace}] {cat['category_name']}: {len(prods)} products (stop: {stop_reason})")
                await _emit_progress(make_category_done_payload(
                    marketplace=marketplace,
                    batch_number=batch_number,
                    batch_started_at=batch_started_at,
                    category_name=cat["category_name"],
                    category_url=url,
                    pages_traversed=pages,
                    stop_reason=stop_reason,
                    failure_type=failure_type,
                    raw_count=len(prods),
                    new_unique_count=len(global_product_map) - before_unique,
                    cumulative_unique_count=len(global_product_map),
                    products=prods,
                    brand_evidence_count=_nico_here,
                    node_status=cat.get("node_status"),
                    facet_applied=bool(_facet_state.get("applied")) if _facet_state else False,
                    surface_classification=cat.get("surface_classification"),
                    provenance=cat.get("provenance"),
                ))
                _batches_emitted += 1
                if max_batches is not None and _batches_emitted >= max_batches:
                    _controlled_stop = True
                    evidence_notes.append(
                        f"CONTROLLED_STOP: batch budget max_batches={max_batches} reached")
                await asyncio.sleep(1.2)
            except asyncio.TimeoutError:
                cat["pages_traversed"] = cat.get("pages_traversed", 0)
                cat["stop_reason"] = "CATEGORY_BUDGET_EXCEEDED"
                cat["coverage_status"] = "BLOCKED"
                cat["evidence"] = cat.get("evidence", "") + (
                    f" | CATEGORY_BUDGET_EXCEEDED after {category_budget_seconds}s; "
                    f"hung extractor isolated, run continues"
                )
                exp_store.record_experience(
                    marketplace=marketplace, brand=brand, knowledge_type="CATEGORY",
                    value=cat["category_name"], source_url=url, page_type="UNKNOWN",
                    status="FAILED", is_success=False,
                    evidence_reference=f"CATEGORY_BUDGET_EXCEEDED after {category_budget_seconds}s"
                )
                logger.warning(f"[{marketplace}] category budget exceeded for {url}")
                await _emit_progress({
                    "kind": "category_timeout",
                    "marketplace": marketplace,
                    "batch_number": batch_number,
                    "batch_started_at": batch_started_at,
                    "category_name": cat["category_name"],
                    "category_url": url,
                    "pages_traversed": cat.get("pages_traversed", 0),
                    "stop_reason": "CATEGORY_BUDGET_EXCEEDED",
                    "failure_type": "TIMEOUT",
                    "raw_count": 0,
                    "new_unique_count": 0,
                    "cumulative_unique_count": len(global_product_map),
                    "products": [],
                    "timed_out": True,
                })
                _batches_emitted += 1
                if max_batches is not None and _batches_emitted >= max_batches:
                    _controlled_stop = True
                    evidence_notes.append(
                        f"CONTROLLED_STOP: batch budget max_batches={max_batches} reached")
            except Exception as e:
                cat["coverage_status"] = "BLOCKED"
                cat["evidence"] += f" | scrape failed: {e}"
                cat["stop_reason"] = "EXTRACTOR_FAILURE"
                exp_store.record_experience(
                    marketplace=marketplace, brand=brand, knowledge_type="CATEGORY",
                    value=cat["category_name"], source_url=url, page_type="UNKNOWN",
                    status="FAILED", is_success=False, evidence_reference=str(e)
                )
                logger.warning(f"[{marketplace}] scrape failed for {url}: {e}")
                await _emit_progress({
                    "kind": "category_error",
                    "marketplace": marketplace,
                    "batch_number": batch_number,
                    "batch_started_at": batch_started_at,
                    "category_name": cat["category_name"],
                    "category_url": url,
                    "pages_traversed": cat.get("pages_traversed", 0),
                    "stop_reason": "EXTRACTOR_FAILURE",
                    "failure_type": type(e).__name__,
                    "raw_count": 0,
                    "new_unique_count": 0,
                    "cumulative_unique_count": len(global_product_map),
                    "products": [],
                    "timed_out": False,
                    "error": str(e),
                })
                _batches_emitted += 1
                if max_batches is not None and _batches_emitted >= max_batches:
                    _controlled_stop = True
                    evidence_notes.append(
                        f"CONTROLLED_STOP: batch budget max_batches={max_batches} reached")

            _no_new_here = len(global_product_map) - before_unique
            _consecutive_no_progress = next_no_progress_streak(_consecutive_no_progress, _no_new_here)
            if no_progress_should_stop(_consecutive_no_progress, no_progress_limit):
                _controlled_stop = True
                evidence_notes.append(
                    f"NO_PROGRESS_BOUNDED_STOP: {_consecutive_no_progress} consecutive categories "
                    f"produced no new unique observations (limit={no_progress_limit}); "
                    f"remaining frontier terminal-classified")

        _final_cats = sanitized_categories if sanitized_categories else discovered_categories
        _resume_cov = resume_coverage_status(
            hub_skipped=bool(_hub_skipped),
            has_other_categories=bool([c for c in (sanitized_categories or [])
                                       if c.get("category_name") != "Brand Hub"]),
            controlled_stop=bool(_controlled_stop))
        coverage_status, _cov_notes, _fa = decide_coverage_status(
            _final_cats,
            resume_override=_resume_cov,
            controlled_stop=bool(_controlled_stop),
            any_discovered_categories=bool(discovered_categories),
            base_notes_text=str(evidence_notes),
        )
        evidence_notes.extend(_cov_notes)
        if _facet_remainder_accounting.get("relevant", 0) > 0:
            evidence_notes.append(
                f"COVERAGE_PARTIAL_REASON: budget-truncated frontier with "
                f"{_facet_remainder_accounting['relevant']} relevant facet(s) pending "
                f"(RELEVANT_PENDING_WORK=true)")
            if coverage_status == "CONFIRMED":
                coverage_status = "PARTIAL"
        
    except Exception as e:
        logger.error(f"[{marketplace}] autonomous discovery failed: {e}", exc_info=True)
        coverage_status = "BLOCKED"
        evidence_notes.append(str(e))
    finally:
        try:
            await scraper.stop()
        except Exception:
            pass
    
    # Strategy persistence (CREAO REUSE): the run's own strategic outcomes
    # are stored as STRATEGY records so a LATER process can load and select
    # them. Failed strategies persist to avoid repeating known errors.
    try:
        _hub_ok = any(c.get("category_name") == "Brand Hub" and c.get("products_found", 0) > 0
                      for c in discovered_categories)
        exp_store.record_experience(
            marketplace=marketplace, brand=brand, knowledge_type="STRATEGY",
            value="hub-first-batch0", source_url=hub_url, page_type="BRAND_SEARCH",
            status="VALIDATED" if _hub_ok else "FAILED", is_success=bool(_hub_ok),
            evidence_reference=f"Brand Hub scraped as batch 0: {'ok' if _hub_ok else 'no products'}",
        )
        _skipped = [d.get("surface_url") for d in experience_decisions
                    if d.get("event") == "STRATEGY_S_SELECTED_BECAUSE_EXPERIENCE"]
        exp_store.record_experience(
            marketplace=marketplace, brand=brand, knowledge_type="STRATEGY",
            value="skip-known-failures", source_url=None, page_type=None,
            status="VALIDATED", is_success=True,
            evidence_reference=f"skipped {len(_skipped)} known-failure surfaces this run",
        )
        experience_decisions.append({
            "timestamp": datetime.now().isoformat(),
            "event": "STRATEGIES_PERSISTED",
            "marketplace": marketplace,
            "strategies": ["hub-first-batch0", "skip-known-failures"],
        })
    except Exception as _se:
        evidence_notes.append(f"strategy persistence failed (non-fatal): {_se}")

    brand_confirmed = [p for p in all_products if _explicit_target_identity(p, brand)]
    
    try:
        _fc = _final_cats
    except NameError:
        _fc = []
    from app.mri_autonomous.category_discoverer import global_coverage_cap as _gcap
    coverage_status = _gcap("PASS" if nav_candidates else "BLOCKED", coverage_status)
    _frontier_view = {
        "queued": [c.get("category_name") for c in _fc],
        "processed": [c.get("category_name") for c in _fc
                      if c.get("stop_reason") not in (None, "QUEUED", "NOT_VISITED")],
        "exhausted": [c.get("category_name") for c in _fc if c.get("stop_reason") in ("EXHAUSTION", "OPERATIONAL_BATCH_LIMIT_REACHED")],
        "not_visited": [c.get("category_name") for c in _fc
                        if c.get("stop_reason") in (None, "QUEUED", "NOT_VISITED")
                        and not c.get("is_seed_surface")],
    }
    try:
        _fa_view = _fa
    except NameError:
        _fa_view = {"raw_frontier_remaining": 0, "relevant_frontier_remaining": 0}
    _fa_raw_total = int(_fa_view.get("raw_frontier_remaining", 0)) + int(_facet_remainder_accounting.get("raw", 0))
    _fa_rel_total = int(_fa_view.get("relevant_frontier_remaining", 0)) + int(_facet_remainder_accounting.get("relevant", 0))
    _frontier_view.update({
        "raw_frontier_remaining": _fa_raw_total,
        "relevant_frontier_remaining": _fa_rel_total,
        "relevant_pending_work": bool(_fa_rel_total > 0),
        "budget_remainder": dict(_facet_remainder_accounting),
    })
    _multi_count = 0
    try:
        _multi_count = sum(1 for _p in global_product_map.values()
                           if len(_p.get("_discovered_categories", [])) > 1)
    except Exception:
        _multi_count = 0
    _nav_summary = {"strategy": nav_strategy, "menu_opened": nav_opened,
                    "anchors_total": nav_anchors_total, "candidates": len(nav_candidates),
                    "navigation_discovery_status": ("PASS" if nav_candidates else "BLOCKED")}
    _facets_summary = {"surfaces_probed": facet_probe_count, "applied_verified": facet_applied_count}
    _exp_count = len(_nav_decisions) + len(_facet_decisions)
    diagnostic = {
        "invalid_edges": invalid_edges if 'invalid_edges' in locals() else 0,
        "edges": sum(len(p.get("_discovered_categories", [])) for p in brand_confirmed),
        "edges_with_direct_observation_evidence": sum(len(p.get("_discovered_categories", [])) for p in brand_confirmed),
    }

    node_types = {}
    for _c in (sanitized_categories if sanitized_categories else discovered_categories):
        node_types[_c["category_name"]] = _c.get("node_type") or (
            "SURFACE" if _c["category_name"] == "Brand Hub" else "UNCERTIFIED")

    # The budget remainder used to survive only as counters. Retain actual
    # identities plus unfinished traversal states for deterministic offline replay.
    pending_nodes = []
    current_by_url = {c.get("category_url"): c for c in _fc if c.get("category_url")}
    pending_states = {None, "QUEUED", "NOT_VISITED", "BLOCKED", "SOURCE_BLOCKED",
                      "CATEGORY_BUDGET_EXCEEDED", "CATEGORY_BUDGET_EXHAUSTED",
                      "EXTRACTOR_FAILURE", "OPERATIONAL_BATCH_LIMIT_REACHED"}
    pending_urls = set()
    for candidate in _remainder_nodes + list(_fc):
        url = candidate.get("category_url")
        category = current_by_url.get(url, candidate)
        if category.get("stop_reason") not in pending_states and category.get("coverage_status") != "BLOCKED":
            continue
        if url and url in pending_urls:
            continue
        if url:
            pending_urls.add(url)
        pending_nodes.append(pending_node_record(category, marketplace, brand_first_gap))

    return {
        "marketplace": marketplace,
        "target_brand": brand,
        "hub_url": hub_url,
        "discovered_categories": sanitized_categories if sanitized_categories else discovered_categories,
        "products_by_category": products_by_category,
        "products": all_products,
        "coverage_status": coverage_status,
        "evidence_notes": evidence_notes,
        "discovery_method": hub.discovery_method,
        "discovered_at": datetime.now().isoformat(),
        "diagnostic": diagnostic,
        "frontier": _frontier_view,
        "pending_nodes": pending_nodes,
        "brand_first_gap": brand_first_gap,
        "navigation": _nav_summary,
        "facets": _facets_summary,
        "multi_membership_products": _multi_count,
        "experience_decisions_count": _exp_count,
        "experience_decisions": experience_decisions if 'experience_decisions' in locals() else [],
        "strategy_attempts": strategy_attempts if 'strategy_attempts' in locals() else [],
        "skipped_known_failures": [
            d.get("surface_url") for d in (experience_decisions if 'experience_decisions' in locals() else [])
            if d.get("event") == "STRATEGY_S_SELECTED_BECAUSE_EXPERIENCE"],
        "category_node_types": node_types,
    }

def materialize_discovered_products(discovery_result: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    """
    Materialize discovered products through GenericCommercialMaterializer -> mri_publications.
    Ensures publication_category edges not duplicated publications.
    Returns stats per classification.
    """
    products = discovery_result.get("products", [])
    marketplace = discovery_result.get("marketplace", "")
    # Build synthetic snapshots from discovered products for materializer
    # Need fields expected by materializer: marketplace, marketplace_sku, sku_master, product_title, brand, price, position_absolute, created_at, is_nicopoly, category
    snapshots = []
    now = datetime.now().isoformat()
    for idx, p in enumerate(products):
        title = p.get("title", p.get("product_title", "")) or ""
        brand = p.get("vendor", p.get("brand", "")) or ""
        sku = p.get("marketplace_sku", "") or ""
        snapshots.append({
            "id": 9000000 + idx,  # synthetic id for evidence ledger
            "marketplace": marketplace,
            "marketplace_sku": sku,
            "sku_master": p.get("sku_master", ""),
            "product_title": title,
            "brand": brand,
            "price": float(p.get("price", 0) or 0),
            "position_absolute": int(p.get("position_absolute", idx+1) or idx+1),
            "created_at": now,
            "audit_date": now,
            "category": p.get("_discovered_categories", ["Brand Hub"])[0],
            "_categories_list": p.get("_discovered_categories", ["Brand Hub"]),
            "is_nicopoly": p.get("is_nicopoly", 0)
        })
    # Use materializer directly to classify
    mat = GenericCommercialMaterializer(run_id, target_brand=discovery_result.get("target_brand"))
    accepted = []
    rejected = []
    edges = []  # publication_category edges: (pub_id, category, snap_id, membership_type)
    seen_pub = {}
    _pub_cats = {}  # pub_id -> set of category names (multi-membership proof)
    
    terminal_states = {
        "TARGET_IDENTITY_VERIFIED": 0,
        "NON_TARGET_BRAND_CONFIRMED": 0,
        "NICOPOLY_CONFIRMED": 0,
        "NON_NICOPOLY_CONFIRMED": 0,
        "INSUFFICIENT_EVIDENCE": 0,
        "IDENTITY_UNRESOLVED": 0
    }
    
    for snap in snapshots:
        res = mat.process_record(snap)
        
        status = res.get("status")
        if status in ("IDENTITY_UNRESOLVED", "IDENTITY_REJECTED_SYNTHETIC"):
            terminal_states["IDENTITY_UNRESOLVED"] += 1
        else:
            membership = res.get("membership", {})
            classification = membership.get("classification", "UNKNOWN")
            key = classification if classification in terminal_states else "INSUFFICIENT_EVIDENCE"
            terminal_states[key] += 1

        if res["status"] == "ACCEPTED":
            pub_id = res["identity"]["publication_id"]
            categories = snap["_categories_list"]
            node_types = discovery_result.get("category_node_types", {})
            # Deduplicate publication, accumulate typed edges: CATEGORY only
            # for certified commercial nodes, SURFACE otherwise. Fulfillment /
            # attribute / facet memberships are never fabricated here.
            if pub_id not in seen_pub:
                seen_pub[pub_id] = res
                accepted.append(res)
            # Always record edge for this category, even if pub already seen
            for cat in categories:
                mtype = "CATEGORY" if node_types.get(cat) == "CATEGORY" else "SURFACE"
                edges.append((pub_id, cat, snap["id"], mtype))
                _pub_cats.setdefault(pub_id, set()).add(cat)
        else:
            rejected.append(res)
            
    return {
        "snapshots": snapshots,
        "accepted": accepted,
        "rejected": rejected,
        "edges": edges,
        "unique_publications": len(seen_pub),
        "multi_category_pubs": sum(
            1 for _cats in _pub_cats.values() if len(_cats) > 1),
        "terminal_states": terminal_states
    }
