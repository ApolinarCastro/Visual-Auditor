"""
MRI acquisition-truth contracts (P0, 2026-10-22).

Single small module so that the runner, the API and the dashboard share ONE
definition of:

  * the acquisition outcome of a run (FOUND / NOT_FOUND / SOURCE_BLOCKED /
    PARTIAL / EXTRACTOR_FAILURE / PERSISTED_VIEW / NOT_EXECUTED),
  * the commercial identity of a publication (OFFICIAL_VERIFIED /
    THIRD_PARTY_NEW / THIRD_PARTY_USED / SELLER_UNVERIFIED),
  * whether a record may feed the OFFICIAL visibility KPI,
  * the Multivende catalog-reference status.

Design rules (from the certification contract):
  - A title containing "Nicopoly" is NEVER official-seller evidence.
  - Used/Nicopoly items sold by third parties are excluded from the official KPI
    but kept as separate information.
  - A blocked source must never be reported as an absence of publications.
  - Nothing here invents data: every state is derived from observed fields.
"""

from __future__ import annotations

import re

# ── Acquisition states ────────────────────────────────────────────────────────
FOUND = "FOUND"
NOT_FOUND = "NOT_FOUND"
SOURCE_BLOCKED = "SOURCE_BLOCKED"
PARTIAL = "PARTIAL"
EXTRACTOR_FAILURE = "EXTRACTOR_FAILURE"
PERSISTED_VIEW = "PERSISTED_VIEW"
NOT_EXECUTED = "NOT_EXECUTED"

ACQUISITION_STATES = (
    FOUND, NOT_FOUND, SOURCE_BLOCKED, PARTIAL,
    EXTRACTOR_FAILURE, PERSISTED_VIEW, NOT_EXECUTED,
)

#: Scrapers/engines return their own vocabulary. It is normalised here instead of
#: editing the frozen Visual Auditor scrapers (app/scrapers must stay diff-free).
STOP_REASON_MAP = {
    "BLOCKED": SOURCE_BLOCKED,
    "BLOCKED_PAGINATION": SOURCE_BLOCKED,
    "WAF_BLOCKED": SOURCE_BLOCKED,
    "CLOUDFLARE": SOURCE_BLOCKED,
    "CAPTCHA": SOURCE_BLOCKED,
    "LOGIN_REQUIRED": SOURCE_BLOCKED,
    "AUTH_REQUIRED": SOURCE_BLOCKED,
    "RATE_LIMIT": SOURCE_BLOCKED,
    "RATE_LIMITED": SOURCE_BLOCKED,
    "TOO_MANY_REQUESTS": SOURCE_BLOCKED,
    "SOURCE_BLOCKED": SOURCE_BLOCKED,
    "EXTRACTOR_FAILURE": EXTRACTOR_FAILURE,
    "EXTRACTION_FAILED": EXTRACTOR_FAILURE,
    "PARSER_FAILURE": EXTRACTOR_FAILURE,
    "EXHAUSTION": FOUND,
    "COMPLETE": FOUND,
    "COMPLETED": FOUND,
    "PARTIAL": PARTIAL,
    "PAGE_BUDGET_EXCEEDED": PARTIAL,
    "NO_RESULTS": NOT_FOUND,
    "EMPTY": NOT_FOUND,
}

BLOCKING_STATES = (SOURCE_BLOCKED, EXTRACTOR_FAILURE)

# ── Commercial identity states ───────────────────────────────────────────────
OFFICIAL_VERIFIED = "OFFICIAL_VERIFIED"
THIRD_PARTY_NEW = "THIRD_PARTY_NEW"
THIRD_PARTY_USED = "THIRD_PARTY_USED"
SELLER_UNVERIFIED = "SELLER_UNVERIFIED"

IDENTITY_STATES = (OFFICIAL_VERIFIED, THIRD_PARTY_NEW, THIRD_PARTY_USED, SELLER_UNVERIFIED)

USED_MARKERS = (
    "usado", "usada", "usados", "usadas", "semi nuevo", "seminuevo",
    "segunda mano", "segunda-mano", "reacondicionado", "reacondicionada",
    "refurbished", "pre-owned", "preowned", "moda circular", "outlet usado",
)

NICOPOLY_PATTERNS = (r"nicopoly", r"nicopolo", r"nico\s+poly")


def normalize_stop_reason(raw) -> str:
    """Map an engine stop_reason to a contract acquisition state."""
    if raw is None:
        return FOUND
    key = str(raw).strip().upper().replace(" ", "_")
    if key in STOP_REASON_MAP:
        return STOP_REASON_MAP[key]
    # Unknown reason with failure semantics stays a failure, never a success.
    if any(t in key for t in ("BLOCK", "CAPTCHA", "WAF", "RATE", "FORBIDDEN", "DENIED")):
        return SOURCE_BLOCKED
    if "EXTRACT" in key or "PARSE" in key:
        return EXTRACTOR_FAILURE
    if "PARTIAL" in key or "BUDGET" in key:
        return PARTIAL
    return FOUND


def resolve_outcome(records_count: int, blocked_reason=None,
                    extractor_failure: bool = False,
                    partial: bool = False) -> str:
    """Terminal outcome of a real acquisition.

    SOURCE_BLOCKED wins over "zero results": a source that could not be read
    never proves absence. EXTRACTOR_FAILURE means the response existed but could
    not be turned into records.
    """
    if blocked_reason == SOURCE_BLOCKED:
        return SOURCE_BLOCKED
    if blocked_reason == EXTRACTOR_FAILURE or extractor_failure:
        return EXTRACTOR_FAILURE
    if records_count > 0 and (partial or blocked_reason == PARTIAL):
        return PARTIAL
    if records_count > 0:
        return FOUND
    return NOT_FOUND


def used_signals(*texts, attributes=None) -> list:
    """Return the used/Moda-Circular markers actually found in the observation."""
    blob_parts = [str(t or "") for t in texts]
    if isinstance(attributes, dict):
        for k, v in attributes.items():
            if isinstance(v, (str, int, float)):
                blob_parts.append(f"{k}: {v}")
            elif isinstance(v, (list, tuple)):
                blob_parts.extend(str(x) for x in v)
    blob = " ".join(blob_parts).lower()
    found = []
    for marker in USED_MARKERS:
        if re.search(rf"(?<![a-záéíóúñ]){re.escape(marker)}(?![a-záéíóúñ])", blob):
            found.append(marker)
    return found


def _is_nicopoly_text(text: str) -> bool:
    low = str(text or "").lower()
    return any(re.search(p, low) for p in NICOPOLY_PATTERNS)


def classify_commercial_identity(title: str = "", brand: str = "", vendor: str = "",
                                 seller: str = "", attributes=None,
                                 official_store: bool = False,
                                 brand_evidence_verified: bool = False) -> dict:
    """Derive the four commercial-identity states from observed evidence.

    Official requires seller/store/brand-field evidence from the marketplace
    itself. A title mentioning Nicopoly is recorded as evidence but is NOT
    sufficient (spec §6).
    """
    attributes = attributes or {}
    title = str(title or "")
    brand = str(brand or "")
    vendor = str(vendor or "")
    seller = str(seller or attributes.get("seller") or attributes.get("sold_by") or "")
    store_flag = bool(
        official_store
        or attributes.get("is_official_seller")
        or attributes.get("official_store")
        or str(attributes.get("seller_type", "")).upper() in ("OFFICIAL", "BRAND_STORE")
    )

    brand_field_ok = _is_nicopoly_text(brand) or _is_nicopoly_text(vendor)
    seller_ok = _is_nicopoly_text(seller)
    title_ok = _is_nicopoly_text(title)
    used = used_signals(title, brand, vendor, seller, attributes=attributes)

    evidence = []
    if brand_field_ok:
        evidence.append(f"Brand field del marketplace: {brand or vendor}")
    if seller_ok:
        evidence.append(f"Vendedor identificado como oficial: {seller}")
    if store_flag:
        evidence.append("Marca/tienda oficial declarada por el marketplace")
    if title_ok:
        evidence.append("Título contiene 'Nicopoly' (no acredita vendedor)")
    if used:
        evidence.append(f"Indicadores de artículo usado: {used}")
    if seller:
        evidence.append(f"Vendedor observado: {seller}")

    # CP3 (MRI-LIVE-RUNTIME-FIX-001): a brand/vendor field is NOT seller proof.
    # Official requires an explicit official seller or official store signal.
    # Brand-field only => still unverified seller (or third party if identified).
    official = bool(seller_ok or store_flag)

    if official:
        state = OFFICIAL_VERIFIED
        reason = "Vendedor/tienda oficial acreditado por el marketplace"
    elif seller:
        state = THIRD_PARTY_USED if used else THIRD_PARTY_NEW
        reason = ("Tercero identificado con indicios de uso" if used
                  else "Tercero identificado, sin indicios de uso")
    else:
        state = SELLER_UNVERIFIED
        reason = ("Vendedor no comprobado"
                  + (" (solo campo de marca, no acredita vendedor)" if brand_field_ok else "")
                  + (" + indicios de uso" if used else ""))

    if state == OFFICIAL_VERIFIED and used:
        reason += " (artículo usado: excluido del KPI oficial de visibilidad)"

    return {
        "state": state,
        "is_official": state == OFFICIAL_VERIFIED,
        "is_third_party": state in (THIRD_PARTY_NEW, THIRD_PARTY_USED),
        "condition": "USED" if used else "NEW",
        "used_signals": used,
        "seller": seller or None,
        "reason": reason,
        "evidence": evidence,
        "catalog_identity": ("VERIFIED" if brand_evidence_verified
                             else "NOT_VERIFIED_AGAINST_REFERENCE"),
    }


def identity_is_official_kpi(identity: dict) -> bool:
    """Only an official, non-used publication feeds the official visibility KPI."""
    if not identity:
        return False
    return bool(identity.get("state") == OFFICIAL_VERIFIED
                and identity.get("condition") != "USED")


#: Sponsored/advertising surfaces observed in marketplace result pages.
AD_URL_MARKERS = ("is_advertising=true", "click1.mercadolibre", "type=pad",
                  "overlay_label=not_apply", "/mclics/clicks/external",
                  "searchVariation=")


def position_kind(product_url: str = "", attributes=None) -> str:
    """Separate SPONSORED result slots from ORGANIC positions (traceable)."""
    blob = f"{product_url or ''} {attributes or ''}".lower()
    if any(marker in blob for marker in AD_URL_MARKERS):
        return "SPONSORED"
    return "ORGANIC"


def is_official_kpi_eligible(identity: dict, kind: str = "ORGANIC") -> bool:
    """Sponsored slots never feed the organic/official visibility KPI."""
    return bool(identity_is_official_kpi(identity) and kind == "ORGANIC")


def summarize_identities(records) -> dict:
    """Counters that distinguish publications, SKUs, official and third-party."""
    skus, pubs = set(), 0
    counters = {
        "records": 0,
        "unique_marketplace_ids": 0,
        "official_verified": 0,
        "third_party_new": 0,
        "third_party_used": 0,
        "seller_unverified": 0,
        "official_kpi_eligible": 0,
        "excluded_from_official_kpi": 0,
    }
    for r in records or []:
        if not isinstance(r, dict):
            continue
        counters["records"] += 1
        pub_sku = r.get("observed_sku") or r.get("producto_id")
        if pub_sku and pub_sku not in skus:
            skus.add(pub_sku)
            pubs += 1
        identity = r.get("commercial_identity") or {}
        state = identity.get("state")
        if state == OFFICIAL_VERIFIED:
            counters["official_verified"] += 1
        elif state == THIRD_PARTY_NEW:
            counters["third_party_new"] += 1
        elif state == THIRD_PARTY_USED:
            counters["third_party_used"] += 1
        else:
            counters["seller_unverified"] += 1
        if r.get("official_kpi"):
            counters["official_kpi_eligible"] += 1
        else:
            counters["excluded_from_official_kpi"] += 1
    counters["unique_marketplace_ids"] = pubs
    return counters


def catalog_reference_status() -> dict:
    """Multivende reference-catalog status (missing file is a real limitation)."""
    from app.loaders.multivende_loader import get_multivende_loader
    loader = get_multivende_loader()
    path = str(getattr(loader, "excel_path", ""))
    available = bool(getattr(loader, "reference_available", False))
    return {
        "status": "AVAILABLE" if available else "CATALOG_REFERENCE_MISSING",
        "path": path,
        "affects": ("Verificación de identidad contra catálogo maestro (sku_master, "
                    "precio Multivende, stock). Las publicaciones quedan como "
                    "catalog_identity=NOT_VERIFIED_AGAINST_REFERENCE."),
        "decisions_without_support": [
            "sku_master vs catálogo maestro",
            "precio_multivende / oferta",
            "stock_multivende",
        ],
    }


def view_metadata(*, execution_mode=None, run_id=None, source=None,
                  live: bool = False) -> dict:
    """Explicit live-vs-persisted marker used by every read surface."""
    return {
        "view_kind": "LIVE_MEMORY" if live else PERSISTED_VIEW,
        "live": bool(live),
        "engine": execution_mode or "UNKNOWN",
        "run_id": run_id,
        "source": source,
        "is_new_acquisition": bool(live),
    }


# ── Historical references (P0 decoupling 2026-10-22) ────────────────────────
#: These files are OUTDATED HISTORICAL REFERENCES. They are never an authority
#: for current publications, sellers, categories, prices or absence, and their
#: absence must never block an acquisition or degrade an independent validation.
HISTORICAL_REFERENCES = {
    "multivende_catalog": {
        "filename": "Actualización masiva de productos.xlsx",
        "role": "HISTORICAL_REFERENCE",
        "authority": "NONE",
        "allowed_use": "LOOKUP_BY_IDENTIFIER_ONLY",
        "used_by_va": True,
        "mri_dependency": "optional cross-reference (never confirms identity)",
    },
    "search_intents": {
        "filename": "Busquedas_Concretas_Visual_Auditor.csv",
        "role": "HISTORICAL_REFERENCE",
        "authority": "NONE",
        "allowed_use": "HISTORICAL_SEARCH_INTENTS_ONLY",
        "used_by_va": True,
        "mri_dependency": "none in acquisition/evaluation",
    },
    "svmp": {
        "filename": "SVMP.xlsx",
        "role": "HISTORICAL_REFERENCE",
        "authority": "NONE",
        "allowed_use": "VA_LEGACY_CATEGORY_TASKS_ONLY",
        "used_by_va": True,
        "mri_dependency": "none (MRI autonomous modules are SVMP-free)",
    },
}


def historical_reference_status(base_dirs=None) -> dict:
    """Presence/role of the three historical reference files.

    Reported for traceability only; `usable_as_authority` is always False.
    """
    from pathlib import Path
    dirs = base_dirs or [Path.cwd()]
    out = {}
    for key, meta in HISTORICAL_REFERENCES.items():
        found = None
        for base in dirs:
            candidate = Path(base) / meta["filename"]
            if candidate.exists():
                found = str(candidate.resolve())
                break
        out[key] = dict(meta, path=found, present=found is not None,
                        usable_as_authority=False)
    return out


def classification_basis(observed: dict) -> str:
    """What a classification may legitimately rest on.

    OBSERVED_FEATURES: title/brand/vendor/breadcrumbs/category observed in the
    marketplace response. HISTORICAL_REFERENCE: only catalog/legacy matching.
    """
    observed = observed or {}
    for key in ("title", "brand", "vendor", "observed_category", "real_category"):
        if str(observed.get(key) or "").strip():
            return "OBSERVED_FEATURES"
    return "HISTORICAL_REFERENCE"
