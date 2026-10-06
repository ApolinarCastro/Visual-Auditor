"""
Category discoverer: extracts real category facets from brand hub DOM.
No SVMP, no hardcoded category names. All categories discovered from marketplace.
"""

import re
import logging
from typing import List, Tuple
from urllib.parse import urljoin, urlparse, parse_qs, unquote, quote

from app.mri_autonomous.brand_norm import brand_slug_from_hub_url
from app.mri_autonomous.surface_classifier import classify_surface

logger = logging.getLogger(__name__)

# Selectors per marketplace for facet extraction
FACET_SELECTORS = {
    "Paris": [
        "a[href*='/c/']", "a[href*='categoria']", "a[href*='category']",
        "[data-testid*='facet'] a", "[class*='facet'] a", "[class*='filter'] a"
    ],
    "Falabella": [
        "a[href*='cat2']", "a[href*='category/cat']",
        "[class*='facet'] a", "[id*='facet'] a", "a[href*='f=Brand']", "a[href*='f.product.']"
    ],
    "Mercado Libre": [
        "a[href*='_Tienda_']", "a.ui-search-filter-dl dt", "[class*='filter'] a",
        ".ui-search-filter-name a", "a.ui-search-link"
    ],
    "Ripley": [
        "a[href*='search']", "[class*='facet'] a",
        "[class*='filter'] a", "a[href*='Nicopoly']"
    ]
}

async def discover_categories_from_page(page, marketplace: str, hub_url: str, brand: str = "") -> List[str]:
    """
    Extract category URLs from brand hub page.
    Returns list of canonical category URLs discovered on the hub.
    """
    category_urls = []
    brand_slug = (brand.lower().strip() if brand else "") or brand_slug_from_hub_url(hub_url) or ""
    try:
        # Use page evaluation to extract all facet/category links
        links = await page.evaluate("""() => {
            const anchors = Array.from(document.querySelectorAll('a[href]'));
            return anchors.map(a => ({href: a.href, text: a.innerText, cls: a.className})).slice(0, 500);
        }""")
        for item in links:
            href = item.get("href", "")
            text = item.get("text", "")
            if not href:
                continue
            # Heuristics to identify category / facet links (not product links)
            is_category = False
            low_href = href.lower()
            low_text = text.lower() if text else ""
            if marketplace.lower() == "falabella":
                if "category/cat" in low_href and ("brand" in low_href or (brand_slug and brand_slug in low_href)):
                    is_category = True
            elif marketplace.lower() == "paris":
                # COMMERCIAL_CONTEXT_REQUIRED: Reject corporate pages and irrelevant global nav departments
                if any(bad in low_href for bad in ["/sostenibilidad/", "/institucional/", "/empresa/", "/proyectos/", "/estrategia/", "/outlet/", "/electro/", "/hogar/", "/belleza/", "/deportes/", "/juguetes/", "/infantil/", "/ninos/"]):
                    continue
                # Paris category URLs can be direct category URLs (/mujer/moda/...) or facet filter URLs
                if any(cls_name in item.get("cls", "") for cls_name in ["childcategory-link", "subcategory-link"]) or "/mujer/moda/" in low_href:
                    if "-mpm" not in low_href:
                        is_category = True
                        # Append brand query parameter if not present to ensure brand filtering
                        if brand_slug and brand_slug not in low_href:
                            href = href + (("&q=" if "?" in href else "?q=") + brand_slug)
                elif (brand_slug and brand_slug in low_href) or (brand_slug and ("brand=" + brand_slug) in low_href):
                    if any(k in low_href for k in ["/c/", "categoria", "category", "facet", "cat="]) and "-mpm" not in low_href:
                        is_category = True
            elif "mercado" in marketplace.lower():
                # Non-commercial navigation filter: explicitly reject address, auth, and account URLs
                clean_href = href.split("#")[0]
                low_href = clean_href.lower()
                if any(bad in low_href for bad in ["/addresses/", "/navigation/hub", "/navigation/", "/registration", "/login", "/account-verification", "/gz/"]):
                    continue
                ML_FACET_BLOCKLIST = [
                    "filtrable", "noindex", "_pricerange", "_orderid",
                    "_discount", "_offset", "_desde",
                    "_filters", "sidebar", "_available",
                ]
                is_ml_facet = any(tok in low_href for tok in ML_FACET_BLOCKLIST)
                if "%2a" in low_href or "*" in clean_href:
                    is_ml_facet = True
                if (
                    (brand_slug and brand_slug in low_href)
                    and ("_tienda" in low_href or "categoria" in low_href or "listado" in low_href or "_container_" in low_href)
                    and not is_ml_facet
                ):
                    # Do not classify the store root itself as a subcategory
                    parsed_u = urlparse(clean_href)
                    u_path = parsed_u.path.strip("/")
                    u_segs = [s for s in u_path.split("/") if s]
                    if "_container_" in low_href or ("tienda" in low_href and len(u_segs) >= 3) or (len(u_segs) >= 2 and "_tienda_" in low_href):
                        is_category = True
                        href = clean_href
            elif marketplace.lower() == "ripley":
                if brand_slug and brand_slug in low_href and ("search" in low_href or "facet" in low_href or "cat=" in low_href or "categoria" in low_href):
                    if "-mpm" not in low_href and "/p/" not in low_href and "/mp/" not in low_href:
                        is_category = True

            if is_category:
                # Normalize
                if href not in category_urls:
                    category_urls.append(href)
        logger.info(f"[{marketplace}] discover_categories_from_page: found {len(category_urls)} raw facet links")
    except Exception as e:
        logger.warning(f"[{marketplace}] facet extraction failed: {e}")
    # For Paris: extract streaming RSC state (self.__next_f.push)
    if "paris" in marketplace.lower():
        try:
            rsc_text = ""
            if hasattr(page, "content"):
                try:
                    rsc_text = await page.content()
                except Exception:
                    rsc_text = ""
            if not rsc_text:
                rsc_text = await page.evaluate("""() => {
                    const scripts = Array.from(document.querySelectorAll('script'));
                    return scripts.map(s => s.textContent || '').join('\\n');
                }""")
            if rsc_text:
                rsc_categories = []
                # Look for tipoProductoAll with optional escaped quotes
                m_facet = re.search(r'\\?"tipoProductoAll\\?"\s*:\s*\{[^}]*\\?"options\\?"\s*:\s*(\[[^\]]+\])', rsc_text)
                if m_facet:
                    try:
                        raw_opts = m_facet.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
                        vals = re.findall(r'\\?"value\\?"\s*:\s*\\?"([^"\\]+)\\?"', raw_opts)
                        clean_hub = hub_url.split("?")[0]
                        for v in vals:
                            cat_url = f"{clean_hub}?q={brand_slug}&tipoProductoAll={quote(v)}"
                            if cat_url not in rsc_categories:
                                rsc_categories.append(cat_url)
                    except Exception as e:
                        logger.warning(f"[Paris] RSC facet extraction error: {e}")
                # Brand store route if present
                brand_store_matches = re.findall(rf'/(?:mujer/)?marcas/{re.escape(brand_slug)}/?', rsc_text, re.IGNORECASE)
                for b_route in set(brand_store_matches):
                    full_store_url = f"https://www.paris.cl{b_route if b_route.startswith('/') else '/' + b_route}"
                    if full_store_url not in rsc_categories:
                        rsc_categories.append(full_store_url)
                if rsc_categories:
                    category_urls = rsc_categories + category_urls
        except Exception as pe:
            logger.warning(f"[Paris] RSC discovery error: {pe}")
    elif marketplace.lower() == "falabella":
        try:
            fal_facets = await page.evaluate("""() => {
                const el = document.getElementById('__NEXT_DATA__');
                if (!el) return [];
                try {
                    const nd = JSON.parse(el.textContent);
                    const facets = nd?.props?.pageProps?.facets || [];
                    const routes = [];
                    for (const f of facets) {
                        const fName = (f.name || '').toLowerCase();
                        if (fName.includes('tipo') || fName.includes('categor') || f.id === 'Tipo') {
                            for (const v of (f.values || [])) {
                                if (v.url) {
                                    routes.push(v.url);
                                }
                            }
                        }
                    }
                    return routes;
                } catch(e) {
                    return [];
                }
            }""")
            for param in fal_facets:
                sep = "&" if "?" in hub_url else "?"
                full_u = f"{hub_url}{sep}{param}"
                if full_u not in category_urls:
                    category_urls.append(full_u)
        except Exception as fe:
            logger.warning(f"[Falabella] __NEXT_DATA__ discovery error: {fe}")
    # Fallback: extract from __NEXT_DATA__ or page JSON
    try:
        next_data = await page.evaluate("""() => {
            const el = document.getElementById('__NEXT_DATA__');
            return el ? el.textContent.slice(0, 8000) : null;
        }""")
        if next_data:
            # Look for category-like URLs inside JSON
            urls = re.findall(rf'https?://[^"\']+{re.escape(brand_slug)}[^"\']*', next_data, re.IGNORECASE) if brand_slug else []
            for u in urls:
                if "ripley" in marketplace.lower() and ("-mpm" in u.lower() or "/p/" in u.lower() or "/mp/" in u.lower()):
                    continue
                if u not in category_urls:
                    category_urls.append(u)
    except Exception:
        pass
    # Dedup and cap
    dedup = []
    seen = set()
    for u in category_urls:
        if u not in seen:
            seen.add(u)
            dedup.append(u)
    return dedup[:30]

def category_name_from_url(url: str, brand: str = "") -> str:
    """Derive human category name from URL without SVMP lookup."""
    try:
        parsed = urlparse(url)
        path = parsed.path.lower()
        # Falabella: /category/cat2005/vestidos?f=... or /search?Ntt={brand}&f.product.attribute.Tipo=Pantalones
        if "falabella" in url.lower():
            qs = parse_qs(parsed.query)
            for k, vals in qs.items():
                k_low = k.lower()
                if "attribute.tipo" in k_low or "category_paths" in k_low or "categoria" in k_low or "category" in k_low:
                    val = unquote(vals[0])
                    if "||" in val:
                        val = val.split("||")[-1]
                    return val.replace("-", " ").replace("+", " ").strip().title()
            parts = path.split("/")
            for p in parts:
                if p and p not in ("category","falabella-cl","search"):
                    # take last meaningful segment before query
                    name = p.replace("-", " ").strip()
                    if name and not name.startswith("cat"):
                        return name.title()
        # Mercado Libre: /ropa-accesorios/brand_Tienda_brand or /tienda/brand/category or /tienda/brand/listado/...
        if "_tienda_" in path or "/tienda/" in path:
            segs = [s for s in parsed.path.rstrip("/").split("/") if s]
            brand_lower = brand.lower() if brand else ""
            for i, seg in enumerate(segs):
                low_seg = seg.lower()
                if "_tienda_" in low_seg:
                    if i > 0:
                        cat_seg = segs[i - 1]
                        return cat_seg.replace("-", " ").replace("_", " ").title()
                elif low_seg == "tienda":
                    rem = segs[i + 2:]
                    if rem:
                        if rem[0].lower() == "listado":
                            rem = rem[1:]
                        if rem:
                            target_seg = rem[-1]
                            m = re.search(r'[A-Fa-f0-9]{16,}-(.+)', target_seg)
                            if m:
                                target_seg = m.group(1)
                            if target_seg.lower() != brand_lower:
                                return target_seg.replace("-", " ").replace("_", " ").title()
        # Paris: /search?q=nicopoly&tipoProductoAll=... or /search?q=nicopoly&facet...
        # Use query params if present
        qs = parse_qs(parsed.query)
        for k, vals in qs.items():
            if "tipoproducto" in k.lower() or "category" in k.lower() or "facet" in k.lower():
                return unquote(vals[0]).replace("-", " ").title()
        if "/marcas/" in path:
            return "Brand Store"
        # Fallback: last path segment
        seg = path.rstrip("/").split("/")[-1]
        seg = seg.split("?")[0].replace("-", " ").replace("_", " ")
        if seg and len(seg) < 60:
            return seg.title()
        return "Unknown"
    except Exception:
        return "Unknown"


# ---------------- MRI-AUTONOMY-002: navigation candidates & strategy policy ----------------
# Generic helpers. No known-category lists; candidates are HYPOTHESES that must be
# certified with direct commercial evidence before becoming taxonomy nodes.

_MARKETING_NAMESPACES = ("minisitios", "estatico", "legales", "bases-legales",
                         "promociones", "campanas", "campañas", "marketing",
                         "blogs", "blog", "sucursales", "tiendas",
                         "seguimiento", "landings", "compromiso")
_NON_TAXONOMY_TYPES = {"PDP", "PAGINATION", "SORT_VARIANT", "FULFILLMENT_FACET",
                       "ATTRIBUTE_FACET", "SEARCH_VARIANT", "BRAND_SURFACE",
                       "CORPORATE_NAVIGATION", "GENERAL_NAVIGATION"}


def _canonical_surface_path(url: str) -> str:
    from urllib.parse import urlparse
    try:
        p = urlparse(url)
        return f"{p.netloc.lower()}{p.path.rstrip('/')}"
    except Exception:
        return url


def build_navigation_candidates(nodes, hub_url: str, brand: str):
    """Turn raw navigation anchors into generic commercial-category HYPOTHESES.

    Each candidate carries provenance (discovery_method + evidence_locator) and
    the classifier output. PAGINATION / PDP / corporate / marketing are dropped;
    menu-container single-segment shapes are kept as hypotheses (certification
    still requires direct commercial evidence).
    """
    import hashlib
    from urllib.parse import urljoin, urlparse

    hub_host = urlparse(hub_url).netloc.lower()
    hub_path = urlparse(hub_url).path.rstrip("/")
    out, seen = [], set()
    for n in nodes or []:
        href = (n.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(hub_url, href)
        p = urlparse(url)
        if p.netloc.lower() != hub_host:
            continue
        path = p.path.rstrip("/")
        if not path or path == hub_path:
            continue
        segs = [s for s in path.split("/") if s]
        if any(s.lower() in _MARKETING_NAMESPACES for s in segs):
            continue
        if url in seen or path in seen:
            continue
        container = n.get("container") or "dom"
        cls = classify_surface(url, {"brand": brand, "nav_container": container == "menu_dialog"})
        st = cls["surface_type"]
        if st in _NON_TAXONOMY_TYPES:
            continue
            
        low_path = path.lower()
        brand_slug = brand.lower().replace(" ", "-") if brand else ""
        
        # RED-1: Prune competitor brand hubs. If it looks like a brand route but doesn't match our brand.
        is_brand_route = any(kw in low_path for kw in ["/marcas-destacadas/", "/marcas/", "/tienda/", "/_tienda_"])
        if is_brand_route and brand_slug and brand_slug not in low_path:
            continue
            
        # RED-2 / RED-4: Bounded Fallback. If discovered from raw generic DOM (not the structured menu api/dialog),
        # it must contain the brand explicitly, otherwise we're just harvesting the global site header.
        _has_membership_evidence = bool(n.get("membership_evidence") or n.get("brand_evidence"))
        if (container != "menu_dialog" and brand_slug and brand_slug not in low_path
                and not _has_membership_evidence):
            # Only exception: search pages, but those are pruned by _NON_TAXONOMY_TYPES usually.
            # We strictly drop generic DOM links that don't have the brand slug,
            # UNLESS the node carries real membership evidence (RIP-F guard).
            continue
            
        if st == "UNKNOWN":
            # only navigation-container, single-segment, non-search shapes
            if container != "menu_dialog" or len(segs) != 1:
                continue
        cid = "nav-" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]
        out.append({
            "candidate_id": cid,
            "url": url,
            "label": (n.get("label") or path)[:80],
            "parent": None,
            "depth": 1,
            "discovery_method": f"navigation_{container}_anchors",
            "evidence_locator": f"anchor:{href[:90]}",
            "classification": cls,
            "hypothesis": True,
        })
        seen.add(url)
        seen.add(path)
    return out


def choose_navigation_strategy(prior_failed, prior_success):
    """Experience-driven policy: do not blindly repeat a failed strategy.

    Returns (strategy_id, decision_event_or_None)."""
    for f in prior_failed or []:
        sid = str(f.get("strategy_id") or "")
        if sid.startswith("nav::raw_dom") and f.get("result") == "FAILED":
            return "menu_open_anchors", {
                "decision": "SELECTED_ALTERNATIVE",
                "capability": "discover_navigation",
                "selected": "menu_open_anchors",
                "because": "nav::raw_dom_only failed previously (no_navigation_candidates_from_raw_dom)",
                "evidence": f"prior failure record: {sid} (result=FAILED)",
            }
    return "raw_dom_anchors", None


def choose_facet_strategy_decision(exp_store, marketplace: str, brand: str, surface: str):
    """Decision event for facet application (reuse-with-revalidation policy)."""
    rows = []
    try:
        rows = exp_store.get_strategies(marketplace, brand) or []
    except Exception:
        rows = []
    prior_ok = [r for r in rows
                if r.get("strategy_type") == "facet_apply" and r.get("result") == "SUCCESS"]
    if prior_ok:
        return {
            "decision": "REUSE_REVALIDATED",
            "capability": "facet_apply",
            "selected": "ui_keyboard",
            "because": (f"facet strategy has {len(prior_ok)} prior SUCCESS record(s); "
                        f"explicit revalidation on this surface"),
            "evidence": f"prior strategy_id={prior_ok[0].get('strategy_id')} updated={prior_ok[0].get('updated_at')}",
        }
    return {
        "decision": "TRIAL_FIRST_TIME",
        "capability": "facet_apply",
        "selected": "ui_keyboard",
        "because": "no prior facet strategy records for this marketplace+brand",
        "evidence": f"fresh attempt on {surface}",
    }


def facet_signals_verified(before: dict, after: dict) -> bool:
    """Require >= 2 independent signals that the facet application changed state."""
    if not before or not after:
        return False
    signals = 0
    if (before.get("url") or "") != (after.get("url") or ""):
        signals += 1
    bc, ac = before.get("count"), after.get("count")
    if bc is not None and ac is not None and bc != ac:
        signals += 1
    bt, at = before.get("titles") or [], after.get("titles") or []
    if bt and at and bt != at:
        signals += 1
    return signals >= 2


def extract_nav_pairs_from_json(obj, _depth=0):
    """Recursively collect (label, href) pairs from network JSON navigation state.
    Only internal paths ('/...') are kept. Generic across marketplaces."""
    pairs = []
    if _depth > 12:
        return pairs
    if isinstance(obj, dict):
        label_keys = ("name", "title", "label", "text", "description")
        url_keys = ("url", "href", "link", "path", "target", "slug")
        lbl = next((obj.get(k) for k in label_keys if isinstance(obj.get(k), str) and obj.get(k).strip()), None)
        url = next((obj.get(k) for k in url_keys if isinstance(obj.get(k), str) and obj.get(k).strip()), None)
        if url and url.startswith("/") and not url.startswith("//"):
            if lbl:
                pairs.append((lbl.strip()[:80], url.strip()))
        for v in obj.values():
            pairs.extend(extract_nav_pairs_from_json(v, _depth + 1))
    elif isinstance(obj, list):
        for v in obj:
            pairs.extend(extract_nav_pairs_from_json(v, _depth + 1))
    return pairs


def global_coverage_cap(navigation_status: str, coverage_status: str) -> str:
    """MRI-AUTONOMY-003 rule: while NAVIGATION_DISCOVERY is not PASS, global
    coverage can never be CONFIRMED. A blocked capability cannot be masked by an
    empty local surface frontier."""
    if coverage_status == "CONFIRMED" and navigation_status != "PASS":
        return "PARTIAL"
    return coverage_status


# --- VA-FINAL-RESOLUTION-LOOP-001: RAW vs RELEVANT frontier semantics ---
_FRONTIER_IRRELEVANT_CLASSES = (
    "NON_COMMERCIAL", "BRAND_NAVIGATION", "GENERAL_NAVIGATION", "CORPORATE_NAVIGATION",
)


def _verifiably_irrelevant(cat: dict) -> bool:
    """Deterministic irrelevance rule: non-commercial classification WITH recorded
    evidence. Irrelevance may never be declared because a node "looks" irrelevant."""
    cls = cat.get("category_type") or cat.get("surface_classification") or ""
    if cls not in _FRONTIER_IRRELEVANT_CLASSES:
        return False
    return bool(cat.get("classification_evidence"))


def _proven_relevant(cat: dict) -> bool:
    """BRAND-FIRST COMMERCIAL SCOPE rule:
    A candidate is only PROVEN_RELEVANT if it has direct brand evidence.
    Global discovery candidates (navigation/menu) without evidence are hypotheses,
    not mandatory work (RELEVANT_PENDING_WORK).
    """
    if _verifiably_irrelevant(cat):
        return False
        
    discovery = str(cat.get("discovery_method") or "")
    if discovery.startswith("navigation_") or discovery.startswith("menu_"):
        if cat.get("brand_evidence_found") or cat.get("brand_facet_option_present") or cat.get("nicopoly_present"):
            return True
        return False
        
    return True


def frontier_relevance_accounting(final_categories) -> dict:
    """VA-FINAL-RESOLUTION-LOOP-001.

    RAW_FRONTIER_REMAINING: non-seed nodes never processed at run end
    (stop_reason in None/QUEUED/NOT_VISITED).
    RELEVANT_FRONTIER_REMAINING: raw nodes lacking a verifiable irrelevance rule
    (deterministic classification + recorded evidence). Only these represent work
    that could still modify the audit result.
    Closure decisions must be keyed on RELEVANT_PENDING_WORK; a verifiably pruned
    frontier alone never forces an incomplete relevant census.
    """
    raw, relevant = [], []
    for cat in (final_categories or []):
        if cat.get("is_seed_surface"):
            continue
        if cat.get("stop_reason") not in (None, "QUEUED", "NOT_VISITED"):
            continue
        raw.append(cat)
        if _proven_relevant(cat):
            relevant.append(cat)
    return {
        "raw_frontier_remaining": len(raw),
        "relevant_frontier_remaining": len(relevant),
        "relevant_pending_work": len(relevant) > 0,
        "raw_frontier_names": [c.get("category_name") for c in raw],
        "relevant_frontier_names": [c.get("category_name") for c in relevant],
    }


def parse_navigation_source(source_json, hub_url: str, brand: str, source_sha: str = ""):
    """Parse the marketplace navigation SOURCE (network JSON tree captured on load)
    into validation-ready candidates. BFS order: top levels first (evidence-based
    chain-composed destinations; validated by destination navigation evidence)."""
    import hashlib as _h
    from urllib.parse import urlparse
    p = urlparse(hub_url)
    base = f"{p.scheme}://{p.netloc}"
    levels = {}

    def walk(nodes, chain):
        for n in nodes or []:
            if not isinstance(n, dict):
                continue
            slug = str(n.get("slug") or "").strip().strip("/")
            name = str(n.get("name") or n.get("title") or slug or "")[:80]
            try:
                d = int(n.get("depth") or (len(chain) + 1))
            except Exception:
                d = len(chain) + 1
            c = chain + [slug] if slug else list(chain)
            if slug:
                url = base + "/" + "/".join(c)
                cls = classify_surface(url, {"brand": brand, "nav_container": True})
                cid = "src-" + _h.sha1(url.encode("utf-8")).hexdigest()[:10]
                levels.setdefault(d, []).append({
                    "candidate_id": cid, "url": url, "label": name,
                    "parent": (chain[-1] if chain else None), "depth": d,
                    "discovery_method": "menu_api_source",
                    "evidence_locator": f"menu_api sha16={source_sha}",
                    "classification": cls, "hypothesis": True,
                })
            walk(n.get("categories") or [], c)

    walk(source_json if isinstance(source_json, list) else [source_json], [])
    out = []
    for d in sorted(levels):
        out.extend(levels[d])
    return out


def classify_node_status(certified: bool, stop_reason: str, products: int, brand_present: int) -> str:
    """MRI-AUTONOMY-004 semantic rule:
    BRAND_NOT_VISIBLE_ON_FIRST_PAGE != BRAND_NOT_PRESENT_IN_CATEGORY.
    Only demonstrated exhaustion-with-facet can close a branch without brand.
    """
    if certified:
        return "CERTIFIED"
    if stop_reason == "BLOCKED":
        return "BLOCKED"
    if products > 0:
        return "UNRESOLVED"
    return "FAILED"


def build_facet_url(category_url: str, brand: str, mechanism):
    """MRI-AUTONOMY-005: build the facet application URL from the DISCOVERED
    mechanism. Only URL_QUERY mechanisms are supported; the param name comes
    from the mechanism (never hardcoded) and the value is the runtime brand
    upper-cased (marketplace brand code). No mechanism -> None (no fabrication)."""
    if not mechanism:
        return None
    mtype = mechanism.get("type") or mechanism.get("mechanism_type") or ""
    if not (mtype == "URL_QUERY" or mtype.startswith("URL_QUERY")):
        return None
    param = mechanism.get("param") or mechanism.get("query_param")
    if not param:
        import re
        m_desc = f"{mechanism.get('facet_identifier_source', '')} {mechanism.get('request_or_transition', '')}"
        m_match = re.search(r"par[aá]metro\s+(?:observado\s+)?es\s+['\"]?(\w+)['\"]?", m_desc, re.IGNORECASE)
        if m_match:
            param = m_match.group(1)
        elif "?brand=" in m_desc.lower() or "brand=" in m_desc.lower():
            param = "brand"
    if not param:
        return None
    value = str(brand or "").strip().upper()
    from urllib.parse import urlparse
    p = urlparse(category_url)
    q = p.query
    sep = "&" if q else ""
    return f"{p.scheme}://{p.netloc}{p.path}?{q}{sep}{param}={value}&page=1"


def brand_effect_verified(before: dict, after: dict, brand: str) -> bool:
    """Two+ independent signals that the brand facet took effect:
    url changed AND (total changed OR title includes brand code)."""
    if not before or not after:
        return False
    signals = 0
    if (before.get("url") or "") != (after.get("url") or ""):
        signals += 1
    bcode = str(brand or "").strip().upper()
    if before.get("total") is not None and after.get("total") is not None and before["total"] != after["total"]:
        signals += 1
    if bcode and bcode in (after.get("title") or "").upper():
        signals += 1
    return signals >= 2


def prioritize_children(candidates, certified_urls):
    """Brand routing: certified categories first, then children, then the rest in original order. Evidence-driven frontier policy."""
    cert = {u.rstrip("/") for u in (certified_urls or [])}
    children = [c for c in candidates
                if ((c.get("parent") or "").lower()) in {u.lower().split("/")[-1] for u in cert}
                or any(c.get("url", "").rstrip("/").startswith(u + "/") for u in cert)]
    certified = [c for c in candidates if c.get("url", "").rstrip("/") in cert]
    rest = [c for c in candidates if c not in children and c not in certified]
    return children + certified + rest
