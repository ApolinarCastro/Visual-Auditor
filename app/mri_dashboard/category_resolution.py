"""Single category resolution pipeline for MRI runs.

Order is explicit and auditable:
1. live marketplace discovery;
2. one session recovery + live retry for challenge-prone markets;
3. learned Creao route priors, host-validated;
4. legacy category cache only for marketplaces not yet migrated.

No category URL is invented. Results carry strategy and evidence.
"""
from __future__ import annotations

from datetime import datetime


async def resolve_categories(marketplace: str, scraper, hub_url: str | None,
                             brand: str, state: dict, inject_session,
                             *, full_audit: bool = True) -> dict:
    from app.mri_dashboard import taxonomy as _taxonomy
    from app.mri_dashboard.marketplace_scope import filter_scope
    from app.mri_dashboard.discovery_intelligence import recover_prior_categories

    strategies = []

    async def _discover():
        return await _taxonomy.discover_taxonomy_async(
            marketplace, scraper=scraper, hub_url=hub_url, brand=brand)

    tax = await _discover()
    strategies.append({"strategy": "LIVE_DISCOVERY",
                       "status": tax.get("status"),
                       "categories": len(tax.get("categories") or [])})
    if tax.get("categories"):
        tax["resolution_strategies"] = strategies
        return tax

    # Challenge recovery: one controlled retry, never a loop.
    if marketplace == "Ripley" and scraper is not None:
        try:
            from app.mri_dashboard.session_supervisor import (
                detect_challenge, recover_session)
            challenge = await detect_challenge(getattr(scraper, "page", None))
            if challenge or tax.get("status") == "TAXONOMY_BLOCKED":
                recovered = await recover_session(
                    scraper, marketplace, state, inject_session)
                if recovered:
                    tax = await _discover()
                    strategies.append({"strategy": "SESSION_RECOVERY_LIVE_RETRY",
                                       "status": tax.get("status"),
                                       "categories": len(tax.get("categories") or [])})
                    if tax.get("categories"):
                        tax["resolution_strategies"] = strategies
                        return tax
        except Exception as exc:
            state.setdefault("errors", []).append({
                "stage": "descubrimiento",
                "error": f"TAXONOMY_SESSION_RECOVERY_FAILED: {exc}",
                "at": datetime.now().isoformat()})

    # Learned prior routes from Creao, host-filtered.
    if full_audit and marketplace in ("Ripley", "Mercado Libre"):
        prior = recover_prior_categories(marketplace, state)
        if prior:
            strategies.append({"strategy": "LEARNED_PRIOR_ROUTES",
                               "categories": len(prior)})
            return {
                "marketplace": marketplace,
                "status": "TAXONOMY_DISCOVERED",
                "source": "LEARNED_PRIOR_ROUTES",
                "categories": prior,
                "taxonomy_complete": False,
                "coverage_scope": "PRIOR_ROUTES_RECOVERY",
                "pending_scope": ["LIVE_REVALIDATION"],
                "resolution_strategies": strategies,
            }

    # Paris/Falabella retain their working legacy baseline until migrated.
    if marketplace not in ("Ripley", "Mercado Libre"):
        try:
            from app.mri_dashboard.category_manager import category_manager
            legacy = category_manager.get_categories(marketplace) or {}
            kept, dropped = filter_scope(marketplace, legacy)
            cats = [{"category_id": cid,
                     "name": (c or {}).get("name") or cid,
                     "url": c["url"],
                     "acquisition": (c or {}).get("acquisition", True)}
                    for cid, c in kept.items() if (c or {}).get("url")]
            if cats:
                strategies.append({"strategy": "LEGACY_CATEGORY_CACHE",
                                   "categories": len(cats),
                                   "dropped": len(dropped)})
                return {
                    "marketplace": marketplace,
                    "status": "TAXONOMY_DISCOVERED",
                    "source": "LEGACY_CATEGORY_CACHE",
                    "categories": cats,
                    "taxonomy_complete": False,
                    "resolution_strategies": strategies,
                }
        except Exception:
            pass

    tax["resolution_strategies"] = strategies
    return tax
