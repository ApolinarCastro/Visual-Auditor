"""
Falabella SSR exhaustive traversal in the MRI layer (MRI-CATEGORY-COVERAGE-003).

Why this exists: the frozen Visual Auditor scraper stops at `page_num > 2`.
MRI must paginate by category through the EXISTING SSR engine
(`falabella_ssr_engine.get_category_catalog`) without touching app/scrapers.

Contract per category:
  * pages are requested with the category_id/slug obtained from the discovered
    taxonomy (never a hardcoded limit such as 2);
  * a category is EXHAUSTED only on a verifiable terminal condition:
      - a later page returns no items (after page >= 2), or
      - the source-declared count is reached;
  * an empty FIRST page is EXTRACTOR_FAILURE, never "end of catalog";
  * hitting the safety page bound leaves the category PENDING (never PASS);
  * every page writes an atomic checkpoint with page/cursor, counts, last id;
  * resumes from the last confirmed page without duplicating identifiers.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.mri_dashboard import coverage as _coverage

EXHAUSTED = "EXHAUSTION"
REPORTED_REACHED = "REPORTED_COUNT_REACHED"
EXTRACTOR_FAILURE = "EXTRACTOR_FAILURE"
PENDING = "PAGE_BOUND_REACHED"
BLOCKED = "SOURCE_BLOCKED"
NO_PROGRESS = "NO_NEW_ITEMS"


def _items_of(payload: Dict[str, Any]) -> List[Any]:
    if not isinstance(payload, dict):
        return []
    for key in ("products", "items", "publications", "pods", "results", "docs"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _reported_of(payload: Dict[str, Any]) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    # SSR real (__NEXT_DATA__): props.pageProps.pagination.count
    try:
        nested = (payload.get("props") or {}).get("pageProps") or {}
        pag = nested.get("pagination") or {}
        for key in ("count", "total", "totalResults"):
            value = pag.get(key)
            if value is not None and int(value) >= 0:
                return int(value)
        results = nested.get("results")
        if isinstance(results, list):
            return len(results)
    except Exception:
        pass
    for key in ("reported_count", "total", "total_results", "count", "numFound"):
        value = payload.get(key)
        try:
            if value is not None and int(value) >= 0:
                return int(value)
        except Exception:
            continue
    return None


def _items_from_payload(engine, payload: Dict[str, Any],
                        category: Dict[str, Any]) -> List[Any]:
    """Extract publications from an ALREADY-FETCHED SSR payload.

    `get_category_catalog` returns the __NEXT_DATA__ dict, whose products live
    under props.pageProps.results. The engine's own normalizer is authoritative;
    top-level generic keys are only a fallback.
    """
    try:
        pubs, _entities = engine.harvest_sample_publications(
            brand=(category.get("brand") or "NICOPOLY"),
            max_items=10 ** 9, page_payload=payload)
        if pubs:
            out = []
            for p in pubs:
                sellers = getattr(p, "sellers", None) or []
                out.append({
                    "product_id": getattr(p, "publication_id", None) or getattr(p, "sku", None),
                    "title": getattr(p, "title", None),
                    "url": getattr(p, "canonical_url", None),
                    "seller": sellers[0] if sellers else None,
                    "brand": getattr(p, "brand", None),
                    "condition": getattr(p, "condition", None),
                    "evidence": {
                        "source_file_path": getattr(p, "source_file_path", None),
                        "source_file_sha256": getattr(p, "source_file_sha256", None),
                        "evidence_type": getattr(p, "evidence_type", None),
                    },
                })
            return out
    except Exception:
        pass
    return _items_of(payload)


def _id_of(item: Any) -> Optional[str]:
    if isinstance(item, dict):
        for key in ("publication_id", "product_id", "productId", "skuId", "sku",
                    "marketplace_product_id", "id"):
            if item.get(key) not in (None, ""):
                return str(item[key])
        return None
    return None


def _is_nicopoly_item(item: Any) -> bool:
    """Brand scope: keep only Nicopoly publications inside the category."""
    if not isinstance(item, dict):
        return False
    blob = " ".join(str(item.get(k) or "") for k in ("title", "brand", "seller")).lower()
    return ("nicopoly" in blob or "nicopolo" in blob or "nico poly" in blob)


def _page_evidence(payload: Dict[str, Any], page: int) -> Dict[str, Any]:
    ev = {"page": page}
    if isinstance(payload, dict):
        ev["url"] = payload.get("url") or payload.get("request_url")
        for key in ("sha256", "payload_sha256", "response_sha256", "har_sha256"):
            if payload.get(key):
                ev["response_sha256"] = payload[key]
                break
        ev["reported_count"] = _reported_of(payload)
    return ev


def traverse_category(engine, category: Dict[str, Any], *, max_pages: int = 200,
                      on_page: Optional[Callable[[int, Dict[str, Any]], None]] = None,
                      start_page: int = 1) -> Dict[str, Any]:
    """Paginate one category until a verifiable terminal condition."""
    cid = category.get("category_id")
    slug = category.get("slug") or (category.get("name") or "").replace(" ", "-").lower()
    seen, observations, pages = set(), [], []
    terminal, cause = PENDING, None
    non_brand_skipped, stall = 0, 0
    prev_raw_ids = set()
    page, reported = max(1, int(start_page)), None

    while page <= max_pages:
        try:
            payload = engine.get_category_catalog(category_id=cid, slug=slug, page=page)
        except Exception as exc:
            terminal, cause = BLOCKED, f"{type(exc).__name__}: {exc}"
            break
        raw_items = _items_from_payload(engine, payload, category)
        items = [it for it in raw_items if _is_nicopoly_item(it)]
        non_brand_skipped += len(raw_items) - len(items)
        raw_ids = {str(_id_of(it)) for it in raw_items if _id_of(it) is not None}
        _same_raw_page = (page > 1 and raw_ids == prev_raw_ids)
        ev = _page_evidence(payload, page)
        if page == 1:
            reported = ev.get("reported_count")

        if not raw_items:
            if page == 1:
                terminal, cause = EXTRACTOR_FAILURE, "first page returned no items"
            else:
                terminal = EXHAUSTED
            pages.append(dict(ev, count=0, new=0, terminal=True))
            if on_page:
                on_page(page, pages[-1])
            break

        new_items = []
        for item in items:
            pid = _id_of(item)
            if pid is not None and pid in seen:
                continue
            if pid is not None:
                seen.add(pid)
            new_items.append(item)
            observations.append({
                "marketplace": "Falabella",
                "product_id": pid,
                "title": (item.get("title") or item.get("name")) if isinstance(item, dict) else None,
                "url": (item.get("url") or item.get("canonical_url")) if isinstance(item, dict) else None,
                "seller": (item.get("seller") or item.get("sellerName")) if isinstance(item, dict) else None,
                "brand": (item.get("brand") or item.get("brandName")) if isinstance(item, dict) else None,
                "category_id": cid,
                "category_name": category.get("name"),
                "category_path": category.get("hierarchical_path") or category.get("path"),
                "position": len(observations) + 1,
                "page": page,
                "category_url": category.get("url"),
                "evidence": ({**ev, **(item.get("evidence") or {})}
                             if isinstance(item, dict) else ev),
            })
        pages.append(dict(ev, count=len(items), new=len(new_items), terminal=False))
        if on_page:
            on_page(page, pages[-1])

        # A repeated page means the source ignored the cursor (or the cursor is
        # exhausted): two consecutive no-new-id pages is a STALL, never success.
        stall = stall + 1 if _same_raw_page else 0
        prev_raw_ids = raw_ids
        if stall >= 2:
            terminal, cause = NO_PROGRESS, ("source repeated the identical page twice "
                                            "(cursor ignored; no new ids)")
            break

        if reported is not None and len(seen) >= reported:
            terminal = REPORTED_REACHED
            break
        page += 1
    else:
        terminal, cause = PENDING, f"page safety bound {max_pages} reached"

    return {
        "category_id": cid,
        "name": category.get("name"),
        "url": category.get("url"),
        "terminal": terminal,
        "cause": cause,
        "pages": pages,
        "pages_traversed": len(pages),
        "publications": len(observations),
        "unique_publications": len(seen),
        # Source counter semantics: reported_count belongs to the SAME filtered
        # surface (brand + category), while unique_publications counts observed
        # Nicopoly ids. They are not interchangeable totals.
        "reported_count": reported,
        "observed_unique": len(seen),
        "counter_scope": "BRAND_FILTERED_SURFACE",
        "counter_status": ("MATCHED" if (reported is not None and len(seen) >= reported)
                           else ("BELOW_REPORTED" if reported is not None else "NO_COUNTER")),
        "skipped_non_brand": non_brand_skipped,
        "observations": observations,
        "complete": terminal in (EXHAUSTED, REPORTED_REACHED),
    }


def traverse_categories(engine, categories: List[Dict[str, Any]], *, run_id: str,
                        aux_dir=None, max_pages: int = 200,
                        resume: bool = True) -> Dict[str, Any]:
    """Run all categories with atomic per-page checkpoints and resume."""
    checkpoint = _coverage.load_checkpoint(aux_dir, f"{run_id}_falabella_ssr") if (
        aux_dir and resume) else None
    done = {}
    if checkpoint:
        for cid, cat in (checkpoint.get("categories") or {}).items():
            done[cid] = cat

    results, all_obs = [], []
    for category in categories:
        cid = category.get("category_id")
        prev = done.get(str(cid)) or {}
        _prev_terminal = prev.get("terminal")
        if _prev_terminal in (EXHAUSTED, REPORTED_REACHED):
            start_page = 1
        else:
            # Resume from the last CONFIRMED page (blocked/pending categories).
            start_page = int(prev.get("last_confirmed_page") or 0) + 1
        if _prev_terminal in (EXHAUSTED, REPORTED_REACHED):
            results.append({"category_id": cid, "terminal": prev["terminal"],
                            "pages_traversed": prev.get("pages_traversed", 0),
                            "publications": prev.get("publications", 0),
                            "resumed_from_checkpoint": True})
            continue

        cp = {"run_id": f"{run_id}_falabella_ssr", "marketplace": "Falabella",
              "categories": done, "updated_at": None}

        def _on_page(page, ev, _cid=cid, _cp=cp):
            from datetime import datetime
            entry = _cp["categories"].setdefault(str(_cid), {
                "category_id": _cid, "name": category.get("name"),
                "url": category.get("url"), "last_confirmed_page": 0,
                "pages_traversed": 0, "last_id": None, "publications": 0,
                "terminal": None, "cause": None})
            entry["last_confirmed_page"] = page
            entry["pages_traversed"] = page
            entry["last_id"] = ev.get("last_id") or entry.get("last_id")
            entry["updated_at"] = datetime.now().isoformat()
            _cp["updated_at"] = entry["updated_at"]
            if aux_dir:
                _coverage.save_checkpoint(aux_dir, _cp)

        result = traverse_category(engine, category, max_pages=max_pages,
                                   on_page=_on_page, start_page=start_page)
        entry = cp["categories"].setdefault(str(cid), {})
        entry.update({"category_id": cid, "name": category.get("name"),
                      "url": category.get("url"),
                      "last_confirmed_page": result["pages_traversed"],
                      "pages_traversed": result["pages_traversed"],
                      "publications": result["publications"],
                      "terminal": result["terminal"],
                      "cause": result.get("cause")})
        if aux_dir:
            _coverage.save_checkpoint(aux_dir, cp)
        results.append({k: v for k, v in result.items() if k != "observations"})
        all_obs.extend(result["observations"])

    complete = all(r.get("terminal") in (EXHAUSTED, REPORTED_REACHED) for r in results)
    return {
        "marketplace": "Falabella",
        "run_id": run_id,
        "categories": results,
        "observations": all_obs,
        "categories_traversed": len(results),
        "categories_complete": sum(1 for r in results
                                   if r.get("terminal") in (EXHAUSTED, REPORTED_REACHED)),
        "pages_total": sum(r.get("pages_traversed", 0) for r in results),
        "complete": bool(results) and complete,
        "checkpoint_resumed": bool(checkpoint),
    }
