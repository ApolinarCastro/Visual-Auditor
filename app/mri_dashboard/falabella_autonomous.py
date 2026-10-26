"""
Falabella autonomous SSR audit for MRI (verified mechanism, 2026-10-26).

Evidence reused (creao.ai technical report + nicopoly_evidencia.csv):
  * primary source: __NEXT_DATA__ (props.pageProps), no DOM, no browser;
  * reliable total: pagination.count (facets[].count are global/lying);
  * 48 cards/page; ?page=N; page without `pagination` == soft-404, never success;
  * brand 415 cards -> 377 unique productIds (37 duplicated groups);
  * surfaces differ (brand 377 / search 365 / L2 union 399): must union+dedupe;
  * category counts overlap (sum 426 > 415): never sum categories;
  * seller from sellerId/sellerName (JSON-LD says Falabella: not reliable);
  * buildId is the snapshot version; every result carries surface/page/buildId/date.

MRI keeps its own identity/classification contract; this module only ACQUIRES
and normalises evidence. Nothing is written here: the runner persists.
"""
from __future__ import annotations

import json
import time
from datetime import datetime

EXHAUSTION = "EXHAUSTION"
NOT_FOUND = "NOT_FOUND"
SOFT_404 = "SOFT_404"
EXTRACTOR_FAILURE = "EXTRACTOR_FAILURE"
NO_PROGRESS = "NO_PROGRESS"
PAGE_BOUND_REACHED = "PAGE_BOUND_REACHED"
SOURCE_BLOCKED = "SOURCE_BLOCKED"
EMPTY = "EMPTY"
TERMINAL_OK = (EXHAUSTION, EMPTY)


def _page_props(payload):
    pp = (payload or {}).get("props", {})
    if not isinstance(pp, dict):
        return {}
    return pp.get("pageProps") or {}


def _cards(payload):
    results = _page_props(payload).get("results")
    return results if isinstance(results, list) else []


def _count(payload):
    pag = _page_props(payload).get("pagination")
    if not isinstance(pag, dict):
        return None
    try:
        return int(pag.get("count"))
    except (TypeError, ValueError):
        return None


def _has_pagination(payload):
    return isinstance(_page_props(payload).get("pagination"), dict)


def _build_id(payload):
    return (payload or {}).get("buildId")


def _price(card):
    """Prefer internetPrice, then eventPrice, then normalPrice (evidence §4.3)."""
    prices = card.get("prices") or []
    by_type = {}
    for p in prices if isinstance(prices, list) else []:
        if not isinstance(p, dict):
            continue
        raw = p.get("price")
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        try:
            value = float(str(raw).replace(".", "").replace(",", ".")) if raw else None
        except (TypeError, ValueError):
            value = None
        by_type[str(p.get("type") or "").lower()] = value
    for key in ("internetprice", "eventprice", "normalprice"):
        if by_type.get(key) is not None:
            return by_type[key]
    return next((v for v in by_type.values() if v is not None), None)


def _group_id(url, fallback):
    """Stable product/group id: URL /product/<id> wins over per-surface card id."""
    import re as _re
    m = _re.search(r"/product/(\d+)", str(url or ""))
    if m:
        return m.group(1)
    return str(fallback) if fallback is not None else None


def _normalise_card(card, surface, category_name, page, build_id):
    pid = card.get("productId") or card.get("product_id")
    if pid is None:
        return None
    return {
        "marketplace": "Falabella",
        "product_id": _group_id(card.get("url"), pid),
        "variant_id": str(pid),
        "group_url": card.get("url"),
        "sku_id": str(card.get("skuId") or card.get("sku_id") or "") or None,
        "title": card.get("displayName") or card.get("name"),
        "brand": card.get("brand") or card.get("brandName"),
        "seller_id": card.get("sellerId") or card.get("seller_id"),
        "seller_name": card.get("sellerName") or card.get("seller_name"),
        "category_gsc": card.get("GSCCategoryId") or card.get("gscCategoryId"),
        "category_name": category_name,
        "url": card.get("url"),
        "price": _price(card),
        "surface": surface,
        "page": page,
        "build_id": build_id,
        "observed_at": datetime.now().isoformat(),
    }


def _fetch_with_retry(fetch_page, page, retries=2):
    """Bounded retry/backoff for 403/429/5xx (verified site returns 403 under rate)."""
    import time as _time
    last = None
    for attempt in range(retries + 1):
        try:
            return fetch_page(page)
        except Exception as exc:
            last = exc
            msg = str(exc)
            if attempt < retries and any(k in msg for k in ("403", "429", "500", "502", "503", "504")):
                _time.sleep(2.0 * (attempt + 1))
                continue
            raise
    if last:
        raise last


def _brand_card(card, brand):
    blob = " ".join(str(card.get(k) or "") for k in
                    ("brand", "sellerName", "seller_id", "displayName")).lower()
    return brand.lower() in blob


def _paginate(fetch_page, *, surface, category_name=None, max_pages=100,
              delay=0.35, on_page=None, allow_empty=False, filter_brand=None):
    """Paginate one surface until the source's own terminal condition."""
    cards, pages, seen_ids = [], [], set()
    terminal, cause = PAGE_BOUND_REACHED, f"page safety bound {max_pages} reached"
    expected, build_id = None, None
    prev_page_ids, stall = None, 0
    first_payload = None

    for page in range(1, max_pages + 1):
        try:
            payload = _fetch_with_retry(fetch_page, page)
        except Exception as exc:                      # never abort the audit
            terminal, cause = SOURCE_BLOCKED, f"{type(exc).__name__}: {exc}"
            break
        if page == 1:
            first_payload = payload
            expected, build_id = _count(payload), _build_id(payload)
            raw_first = _cards(payload)
            if expected is None and not raw_first:
                # Verified soft-404: HTTP 200, no pagination/results.
                terminal, cause = ((EMPTY, "brand-filtered category has no results")
                                   if allow_empty else
                                   (SOFT_404, "HTTP 200 without pagination/results"))
                break
            if expected is not None and expected <= 0:
                terminal, cause = ((EMPTY, "pagination.count == 0 (brand-filtered empty)")
                                   if allow_empty else
                                   (NOT_FOUND, "pagination.count == 0"))
                break

        raw = _cards(payload)
        if not raw:
            if page == 1:
                terminal, cause = EXTRACTOR_FAILURE, "first page returned no cards"
            else:
                terminal, cause = EXHAUSTION, None
            pages.append({"page": page, "cards": 0, "new_ids": 0, "count": _count(payload)})
            if on_page:
                on_page(page, pages[-1])
            break

        page_ids, new_ids = set(), 0
        for card in raw:
            norm = _normalise_card(card, surface, category_name, page, build_id)
            if norm is None:
                continue
            if filter_brand and not _brand_card(card, filter_brand):
                continue
            page_ids.add(norm["product_id"])
            cards.append(norm)
            if norm["product_id"] not in seen_ids:
                seen_ids.add(norm["product_id"])
                new_ids += 1
        pages.append({"page": page, "cards": len(raw), "new_ids": new_ids,
                      "unique_ids": len(seen_ids), "count": expected})
        if on_page:
            on_page(page, pages[-1])

        stall = stall + 1 if (page > 1 and page_ids == prev_page_ids) else 0
        prev_page_ids = page_ids
        if stall >= 2:
            terminal, cause = NO_PROGRESS, "source repeated the identical page twice"
            break
        if expected is not None and len(cards) >= expected:
            continue                              # next page must confirm exhaustion
        time.sleep(delay)

    return {
        "surface": surface,
        "category_name": category_name,
        "terminal": terminal,
        "cause": cause,
        "expected_cards": expected,
        "cards": len(cards),
        "unique_product_ids": len(seen_ids),
        "pages_traversed": len(pages),
        "build_id": build_id,
        "complete": terminal in TERMINAL_OK,
        "cards_data": cards,
        "first_payload": first_payload,
        "pages": pages,
    }


def _extract_cid(val):
    cid = val.get("id") or val.get("categoryId")
    if cid:
        return str(cid)
    import re as _re, urllib.parse as _up
    raw = _up.unquote(str(val.get("url") or "") + " " + str(val.get("facetType") or ""))
    m = _re.search(r"(cat[0-9A-Za-z]+)", raw)
    return m.group(1) if m else None


def _category_candidates(payload):
    """Category ids/names from facets (live shape: f.product.L*_category_paths)."""
    out, seen = [], set()
    pp = _page_props(payload)
    import re as _re
    for facet in pp.get("facets") or []:
        if not isinstance(facet, dict):
            continue
        blob = f"{facet.get('name') or ''} {facet.get('facetType') or ''}".lower()
        if "categor" not in blob:
            continue
        for val in facet.get("values") or []:
            if not isinstance(val, dict):
                continue
            cid = _extract_cid(val)
            if not cid or cid in seen:
                continue
            seen.add(cid)
            depth = None
            m = _re.search(r"L(\d)_category_paths",
                           str(val.get("url") or "") + " " + str(facet.get("facetType") or ""),
                           _re.I)
            if m:
                depth = int(m.group(1))
            out.append({"category_id": cid,
                        "name": val.get("title") or val.get("name"),
                        "depth": depth})
    return out


def discover_categories(engine, brand, seed_payload, *, max_fetch=40, delay=0.8):
    """Walk brand -> L0 -> L1 -> L2 -> L3 with brand filter; containers are
    discovered through an unfiltered fetch when the brand-filtered view is empty
    (verified: CATG36072 Ropa de Fiesta -> CATG36075 Vestidos de Fiesta)."""
    params = {"f.product.brandName": brand.lower(), "facetSelected": "true"}
    queue = [(c, c.get("depth") if c.get("depth") is not None else 0)
             for c in _category_candidates(seed_payload)]
    visited, tree, nodes, fetched = set(), [], [], 0
    while queue and fetched < max_fetch:
        cat, depth = queue.pop(0)
        cid = cat["category_id"]
        if cid in visited:
            continue
        visited.add(cid)
        try:
            payload = engine.get_category_catalog(category_id=cid, slug="x",
                                                 page=1, extra_params=params)
        except Exception as exc:
            tree.append({**cat, "depth": depth,
                         "error": f"{type(exc).__name__}: {exc}"})
            continue
        fetched += 1
        children = [c for c in _category_candidates(payload)
                    if c["category_id"] not in visited]
        brand_count = _count(payload)
        if not children and depth < 3 and brand_count in (0, None):
            # Empty brand view can still be a CONTAINER (verified L2 Ropa de
            # Fiesta): children only appear in the unfiltered SSR payload.
            try:
                raw = engine.get_category_catalog(category_id=cid, slug="x",
                                                  page=1, extra_params=None)
                children = [c for c in _category_candidates(raw)
                            if c["category_id"] not in visited]
            except Exception:
                pass
        tree.append({**cat, "depth": depth, "brand_count": brand_count,
                     "children": [c["category_id"] for c in children]})
        nodes.append({**cat, "depth": depth, "brand_count": brand_count,
                      "children": [c["category_id"] for c in children]})
        if children and depth < 3:
            queue.extend((c, (c.get("depth") if c.get("depth") is not None
                              else depth + 1)) for c in children)
        if delay:
            time.sleep(delay)
    # Traverse a node if it has products of its own (brand_count>0) or if it is
    # a leaf; a container with brand_count==0 is represented by its children.
    leaves = [{k: n.get(k) for k in ("category_id", "name", "depth",
                                     "brand_count")}
              for n in nodes
              if (n.get("depth") or 0) >= 2
              and ((n.get("brand_count") or 0) > 0 or not n.get("children"))]
    if not leaves:
        leaves = [{k: t.get(k) for k in ("category_id", "name", "depth")}
                  for t in tree]
    depths = [l.get("depth") for l in leaves if l.get("depth") is not None]
    if depths and max(depths) < 2:
        return {"leaves": [], "tree": tree, "fetched": fetched,
                "reason": f"only depth {max(depths)} discovered (L2 required)"}
    uniq, seen = [], set()
    for leaf in leaves:
        if leaf["category_id"] in seen:
            continue
        seen.add(leaf["category_id"])
        uniq.append(leaf)
    return {"leaves": uniq, "tree": tree, "fetched": fetched}


PDP_CACHE = "falabella_pdp_cache.json"


def _specific_category(categories, cat_sizes):
    """Prefer the most specific (smallest) surface; never sum categories."""
    if not categories:
        return None
    return min(categories, key=lambda n: cat_sizes.get(n, 10 ** 9))


def _assign_gsc_groups(observations):
    """Ground GSC-only rows in the L2 names actually seen for that group.

    GSC is a coarse group (G08020501 = Poleras + Blusas): if the group maps to
    exactly one L2 seen in this run we can assign it; otherwise we keep an
    explicit label with the candidate L2s (never a fabricated single category).
    """
    from collections import defaultdict
    import re as _re
    mapping = defaultdict(set)
    cat_tokens = defaultdict(set)
    stop = {"mujer", "nicopoly", "negro", "blanco", "cafe", "café", "gris",
            "azul", "rojo", "verde", "beige", "oliva", "burdeo", "rosado",
            "celeste", "mocca", "khaki", "marino", "manga", "mangas",
            "corta", "larga", "sin", "del", "las", "los", "con", "por",
            "para", "the", "and"}
    for obs in observations:
        if obs.get("category_name") and (obs.get("title") or obs.get("url")):
            text = str(obs.get("title") or "") + " " + str(obs.get("url") or "")
            for tok in _re.findall(r"[a-záéíóúñ]+", text.lower()):
                if len(tok) >= 3 and tok not in stop:
                    cat_tokens[obs["category_name"]].add(tok)
    for obs in observations:
        if obs.get("category_name") and obs.get("category_gsc"):
            mapping[obs["category_gsc"]].add(obs["category_name"])
    stats = {"assigned_unique": 0, "assigned_title": 0,
             "assigned_token": 0, "ambiguous": 0}
    for obs in observations:
        if obs.get("category_name"):
            continue
        gsc = obs.get("category_gsc")
        candidates = sorted(mapping.get(gsc) or [])
        if len(candidates) == 1:
            obs["category_name"] = candidates[0]
            obs["category_source"] = "GSC_UNIQUE_L2"
            stats["assigned_unique"] += 1
        elif candidates:
            import re as _re
            title = (str(obs.get("title") or "") + " "
                     + str(obs.get("url") or "")).lower()
            matched = []
            for name in candidates:
                stems = {w.rstrip("s") for w in _re.findall(r"[a-záéíóúñ]+",
                                                           name.lower())
                         if len(w) >= 5 and w not in ("mujer", "chalecos",
                                                     "enteritos")}
                if any(stem in title for stem in stems):
                    matched.append(name)
            if len(matched) == 1:
                obs["category_name"] = matched[0]
                obs["category_source"] = "GSC_TITLE_MATCH"
                stats["assigned_title"] = stats.get("assigned_title", 0) + 1
                continue
            text = (str(obs.get("title") or "") + " "
                    + str(obs.get("url") or ""))
            tokens = {t for t in _re.findall(r"[a-záéíóúñ]+", text.lower())
                      if len(t) >= 3 and t not in stop}
            scores = {name: len(tokens & cat_tokens.get(name, set()))
                      for name in candidates}
            best = max(scores.values()) if scores else 0
            winners = [n for n, v in scores.items() if v == best and v > 0]
            if len(winners) == 1:
                obs["category_name"] = winners[0]
                obs["category_source"] = "GSC_TOKEN_MATCH"
                stats["assigned_token"] = stats.get("assigned_token", 0) + 1
            else:
                obs["category_group_label"] = "%s (L2: %s)" % (
                    gsc, " / ".join(candidates))
                stats["ambiguous"] += 1
        elif gsc:
            obs["category_group_label"] = "%s (grupo; L2 no expuesta)" % gsc
            stats["ambiguous"] += 1
    return stats


def _fetch_pdp_html(url, retries=1):
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8"})
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:
            last = exc
            if attempt < retries:
                time.sleep(2.0)
    raise last


def _parse_breadcrumb(html):
    import re as _re
    for match in _re.finditer(r'<script([^>]*)>(.*?)</script>', html or "", _re.S):
        if "ld+json" not in match.group(1).lower():
            continue
        try:
            data = json.loads(match.group(2))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("@type") == "BreadcrumbList":
            names = [str(i.get("name")) for i in (data.get("itemListElement") or [])
                     if isinstance(i, dict) and i.get("name")]
            if names:
                return names[-1]  # leaf category (breadcrumb may add "Mujer - Moda Mujer")
    return None


def _load_pdp_cache(aux_dir):
    try:
        path = Path(aux_dir) / PDP_CACHE if aux_dir else None
        if path and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_pdp_cache(aux_dir, cache):
    try:
        if aux_dir:
            (Path(aux_dir) / PDP_CACHE).write_text(
                json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def enrich_missing_categories(observations, *, aux_dir=None, max_items=20,
                              delay=1.0, fetcher=None):
    """PDP BreadcrumbList enrichment for rows without L2 (bounded + cached)."""
    missing = [o for o in observations if not o.get("category_name")]
    cache = _load_pdp_cache(aux_dir)
    stats = {"attempted": 0, "enriched": 0, "blocked": 0, "cache_hits": 0}
    for obs in missing[:max_items]:
        url = obs.get("url")
        if not url:
            continue
        cached = cache.get(url) or {}
        if cached.get("category_name"):
            obs["category_name"] = cached["category_name"]
            obs["category_source"] = "PDP_BREADCRUMB_CACHE"
            stats["cache_hits"] += 1
            continue
        stats["attempted"] += 1
        try:
            html = (fetcher or _fetch_pdp_html)(url)
            name = _parse_breadcrumb(html)
            if name:
                obs["category_name"] = name
                obs["category_source"] = "PDP_BREADCRUMB"
                stats["enriched"] += 1
                cache[url] = {"category_name": name,
                              "fetched_at": datetime.now().isoformat()}
            else:
                stats["blocked"] += 1
                cache[url] = {"status": "NO_BREADCRUMB",
                              "fetched_at": datetime.now().isoformat()}
        except Exception as exc:
            stats["blocked"] += 1
            cache[url] = {"status": f"{type(exc).__name__}: {exc}"[:200],
                          "fetched_at": datetime.now().isoformat()}
        if delay:
            time.sleep(delay)
    _save_cache = _save_pdp_cache(aux_dir, cache)
    return stats


def run_full_audit(engine, *, brand="NICOPOLY", run_id=None, aux_dir=None,
                   max_pages=100, delay=0.8, include_search=True, pdp_fetcher=None):
    """Autonomous Falabella audit: brand + brand-filtered categories + search."""
    started = datetime.now().isoformat()
    surfaces = []

    brand_res = _paginate(lambda p: engine.get_brand_catalog(brand_name=brand, page=p),
                          surface=f"brand:{brand}", category_name=None,
                          max_pages=max_pages, delay=delay)
    surfaces.append(brand_res)

    discovery = discover_categories(
        engine, brand, brand_res.get("first_payload") or {}, delay=delay)
    categories = discovery["leaves"]
    for cat in categories[:30]:
        cid, cname = cat["category_id"], cat.get("name")
        params = {"f.product.brandName": brand.lower(), "facetSelected": "true"}
        brand_surface = _paginate(
            lambda p, _cid=cid, _params=params: engine.fetch_page_ssr_data(
                f"/category/{_cid}/x", {**_params, "page": p}),
            surface=f"category:{cid}", category_name=cname,
            max_pages=min(max_pages, 20), delay=delay, allow_empty=True)
        if (brand_surface["cards"] == 0
                and brand_surface["terminal"] in (EMPTY, NOT_FOUND)):
            # L3 verified behaviour: brand filter yields 0 even with Nicopoly
            # products inside; scan the category unfiltered and filter in code.
            fallback = _paginate(
                lambda p, _cid=cid: engine.fetch_page_ssr_data(
                    f"/category/{_cid}/x", {"page": p}),
                surface=f"category:{cid}", category_name=cname,
                max_pages=min(max_pages, 60), delay=delay,
                allow_empty=True, filter_brand=brand)
            if fallback["cards"] > 0 or fallback["complete"]:
                fallback["fallback_unfiltered"] = True
                brand_surface = fallback
        surfaces.append(brand_surface)

    if include_search:
        surfaces.append(_paginate(
            lambda p: engine.fetch_page_ssr_data(
                "/search", {"Ntt": brand.lower(), "page": p}),
            surface=f"search:{brand.lower()}", category_name=None,
            max_pages=max_pages, delay=delay))

    # Union + dedupe by productId (variants keep their skuId; categories/surfaces kept)
    union = {}
    for surface in surfaces:
        for card in surface["cards_data"]:
            gid = card.get("product_id")
            existing = union.get(gid)
            if existing is None:
                card = dict(card, categories=[], surfaces=[], skus={}, variants=set())
                union[gid] = card
                existing = card
            existing["variants"].add(str(card.get("variant_id") or ""))
            sku = card.get("sku_id")
            if sku and str(sku) not in existing["skus"]:
                existing["skus"][str(sku)] = {"price": card.get("price")}
            if card.get("category_name") and card["category_name"] not in existing["categories"]:
                existing["categories"].append(card["category_name"])
            if card["surface"] not in existing["surfaces"]:
                existing["surfaces"].append(card["surface"])

    gsc_stats = _assign_gsc_groups(list(union.values()))

    observations = []
    for index, card in enumerate(union.values(), start=1):
        card = dict(card)
        card["position"] = index
        card["category_name"] = (card["categories"][0] if card["categories"]
                                 else card.get("category_name"))
        card["categories_observed"] = list(card["categories"])
        card["variants"] = sorted(v for v in (card.get("variants") or set()) if v)
        observations.append(card)

    pdp_stats = (enrich_missing_categories(
        observations, aux_dir=aux_dir, delay=max(delay, 1.0), fetcher=pdp_fetcher)
        if aux_dir else {"attempted": 0, "enriched": 0, "blocked": 0,
                         "cache_hits": 0})
    cat_sizes = {s.get("category_name"): s.get("expected_cards")
                 for s in surfaces
                 if str(s.get("surface", "")).startswith("category:")
                 and s.get("category_name")}
    for obs in observations:
        cats = obs.get("categories") or []
        if len(cats) > 1:
            best = _specific_category(cats, cat_sizes)
            if best and best != obs.get("category_name"):
                obs["category_name"] = best
                obs["category_source"] = "SURFACE_SPECIFIC"
    sku_keys, sku_id_set, multi_sku = set(), set(), 0
    for o in observations:
        skus = o.get("skus") or {}
        for sku in skus:
            sku_keys.add((o.get("product_id"), str(sku)))
            sku_id_set.add(str(sku))
        if len(skus) > 1:
            multi_sku += 1
    complete = (bool(surfaces) and all(s["complete"] for s in surfaces)
                and bool(categories))
    pending = [s["surface"] for s in surfaces if not s["complete"]]
    if not categories:
        # Never AUDIT_PASS with brand+search only: the 9 L2 surfaces are part
        # of the verified scope (36 products were L2-only on 2026-10-21).
        complete = False
        pending.append("categories:L2_NOT_DISCOVERED")
    cards_total = sum(s["cards"] for s in surfaces)
    result = {
        "marketplace": "Falabella",
        "brand": brand,
        "run_id": run_id,
        "started_at": started,
        "finished_at": datetime.now().isoformat(),
        "build_id": brand_res.get("build_id"),
        "surfaces": [{k: v for k, v in s.items()
                      if k not in ("cards_data", "first_payload")} for s in surfaces],
        "categories_discovered": len(categories),
        "categories_used": [c["category_id"] for c in categories],
        "category_tree": discovery["tree"],
        "category_discovery_fetched": discovery["fetched"],
        "gsc_grouping": gsc_stats,
        "pdp_enrichment": pdp_stats,
        "cards_total": cards_total,
        "unique_product_ids": len(observations),
        "unique_sku_ids": len(sku_id_set),
        "unique_sku_keys": len(sku_keys),
        "products_with_multiple_skus": multi_sku,
        "avg_skus_per_product": (round(len(sku_keys) / len(observations), 2)
                                 if observations else None),
        "duplicated_cards": cards_total - len(observations),
        "complete": complete,
        "pending_surfaces": pending,
        "observations": observations,
    }
    if aux_dir:
        from app.mri_dashboard import falabella_snapshots as _snapshots
        result["_aux_dir"] = str(aux_dir)
        try:
            snap_path, snap = _snapshots.capture(result, observations, run_id=run_id)
            result["snapshot_path"] = str(snap_path)
            result["freshness"] = _snapshots.compare_and_write(
                aux_dir, snap_path, snap)
        except Exception as exc:
            result["freshness"] = {"comparable": False,
                                   "reason": f"{type(exc).__name__}: {exc}"}
        finally:
            result.pop("_aux_dir", None)
    return result


def to_runner_results(observations, *, catalog_status=None):
    """Map SSR observations to the MRI runner/persistence contract."""
    from app.mri_dashboard.acquisition_contract import (
        classify_commercial_identity, is_official_kpi_eligible, position_kind)
    out = []
    for obs in observations or []:
        identity = classify_commercial_identity(
            title=obs.get("title") or "",
            brand=obs.get("brand") or "",
            seller=obs.get("seller_name") or "",
            attributes={"category": obs.get("category_name") or "",
                        "category_gsc": obs.get("category_gsc")})
        kind = position_kind(obs.get("url") or "", {})
        acquisition = {
            "run_id": None,  # filled by caller if needed
            "engine": f"FALABELLA_SSR::{obs.get('surface')}",
            "adapter": "FalabellaSSREngine.fetch_page_ssr_data",
            "requested_url": obs.get("url"),
            "observed_url": obs.get("url"),
            "surface": obs.get("surface"),
            "page": obs.get("page"),
            "build_id": obs.get("build_id"),
            "acquisition_state": "FOUND",
            "products_extracted": 1,
            "observed_at": obs.get("observed_at"),
        }
        observed_category = (obs.get("category_name")
                             or obs.get("category_group_label")
                             or obs.get("category_gsc"))
        observed_source = obs.get("category_source") or (
            "SSR_L2" if obs.get("category_name") else "GSC_ONLY")
        out.append({
            "producto_id": obs.get("product_id"),
            "producto_nombre": obs.get("title"),
            "marketplace": "Falabella",
            "url_encontrada": obs.get("url"),
            "fecha_observacion": obs.get("observed_at"),
            "real_category": observed_category,
            "category_source": observed_source,
            # Expected category comes ONLY from a verified reference catalog;
            # never copy the observation (circular evidence).
            "expected_category": "SIN_REFERENCIA",
            "decision": "NO_VERIFICADO",
            "identity_status": identity["state"],
            "commercial_attributes": {
                "seller_id": obs.get("seller_id"),
                "seller_name": obs.get("seller_name"),
                "category_gsc": obs.get("category_gsc"),
                "price": obs.get("price"),
                "surfaces": obs.get("surfaces"),
                "build_id": obs.get("build_id"),
                "category_observation_status": ("L2_EXPOSED" if obs.get("category_name")
                                                else "GSC_GROUP_ONLY"),
                "evidence": {
                    "surface": obs.get("surface"),
                    "query": "nicopoly" if str(obs.get("surface") or "").startswith("search:") else None,
                    "page": obs.get("page"),
                    "position": obs.get("position"),
                    "build_id": obs.get("build_id"),
                    "category_observed": observed_category,
                },
                "categories_observed": (obs.get("categories_observed")
                                        or ([obs["category_name"]]
                                            if obs.get("category_name") else [])),
                "expected_category_status": "SIN_REFERENCIA",
            },
            "status": "OBSERVED",
            "acquisition_status": "OBSERVED",
            "position_observed": obs.get("position"),
            "classification": "NICOPOLY_BRAND_SURFACE",
            "observed_sku": obs.get("sku_id") or obs.get("product_id"),
            "sku_ids": sorted(str(k) for k in (obs.get("skus") or {})),
            "variant_ids": obs.get("variants") or ([obs.get("variant_id")]
                                                    if obs.get("variant_id") else []),
            "group_url": obs.get("group_url") or obs.get("url"),
            "sku_count": len(obs.get("skus") or {}),
            "prices_by_sku": {str(k): v.get("price")
                              for k, v in (obs.get("skus") or {}).items()},
            "url": obs.get("url"),
            "timestamp": obs.get("observed_at"),
            "acquisition": acquisition,
            "commercial_identity": identity,
            "official_kpi": is_official_kpi_eligible(identity, kind),
            "position_kind": kind,
            "sponsored": kind == "SPONSORED",
            "catalog_reference": catalog_status,
            "classification_basis": "OBSERVED_FEATURES",
            "historical_reference": {"catalog_status": catalog_status,
                                     "role": "HISTORICAL_REFERENCE",
                                     "authority": "NONE"},
        })
    return out
