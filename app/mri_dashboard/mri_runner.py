import asyncio
import time
import uuid
import hashlib
import sys
from datetime import datetime

from app.mri_autonomous.experience_store import ExperienceStore


class _NullLearningStore:
    """No-op learning store used when the experience DB is not writable."""

    def get_experience_item(self, *args, **kwargs):
        return None

    def record_experience(self, *args, **kwargs):
        return None


def _safe_experience_store():
    """
    Best-effort learning store.

    Learning persistence must never abort an audit: in read-only dashboard mode
    the protected experience database is intentionally not writable, so we fall
    back to a no-op store instead of propagating ProductionWriteBlockedError.
    """
    try:
        return ExperienceStore()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "[MRI] learning persistence disabled (write not authorized): %s", exc)
        return _NullLearningStore()
from app.scrapers.mercadolibre_scraper import MercadoLibreScraper
from app.scrapers.paris_scraper import ParisScraper
from app.scrapers.ripley_scraper import RipleyScraper
from app.scrapers.falabella_scraper import FalabellaScraper
from app.mri_autonomous.category_evaluator import evaluate_commercial_category
from app.auditor.nicopoly_matcher import is_nicopoly
from mri_commercial_materialization_golden_slice.v001.materializer_engine import GenericCommercialMaterializer
from app.mri_dashboard.acquisition_contract import (
    ACQUISITION_STATES, BLOCKING_STATES, SOURCE_BLOCKED, EXTRACTOR_FAILURE,
    PARTIAL, FOUND, NOT_FOUND,
    normalize_stop_reason, resolve_outcome, classify_commercial_identity,
    identity_is_official_kpi, summarize_identities, catalog_reference_status,
    classification_basis, historical_reference_status,
    position_kind, is_official_kpi_eligible,
)
from app.loaders.multivende_loader import get_multivende_loader
from app.mri_dashboard import coverage as _coverage

import re
import csv
import os

def load_universe(marketplace="ALL", limit=5):
    filepath = os.path.join("outputs", "MRI_PRODUCTION_AUDIT_001.csv")
    products = []
    seen_skus = set()
    
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mkt = row["marketplace"]
                if marketplace != "ALL" and mkt != marketplace:
                    continue
                
                sku = row["sku_parent"]
                if sku in seen_skus:
                    continue
                
                products.append({
                    "sku": sku,
                    "title": row["product_name"],
                    "marketplace": mkt,
                    "vendor": "Nicopoly"
                })
                seen_skus.add(sku)
                
                if limit != "ALL" and len(products) >= int(limit):
                    break
                    
    if not products:
        products = [
            {"sku": "MLC6", "title": "Abrigo Efecto Piel Nicopoly", "marketplace": "Mercado Libre", "vendor": "Nicopoly"},
        ]
    return products



def verify_product_identity_match(expected_title: str, observed_title: str) -> tuple[bool, str]:
    exp = expected_title.lower().replace("nicopoly", "").split()
    obs = observed_title.lower().replace("nicopoly", "").split()
    
    garments = {"chaqueta", "pantalon", "abrigo", "blusa", "falda", "top", "blazer", "vestido", "polera", "sweater", "parka", "jeans"}
    exp_garments = [w for w in exp if w in garments]
    
    for g in exp_garments:
        if g not in obs:
            return False, f"Contradicción material: falta tipo de prenda '{g}'"
            
    materials = {"denim", "gamuza", "cuero", "lino", "algodon", "lana", "polar", "satín", "seda"}
    exp_mat = set(w for w in exp if w in materials)
    obs_mat = set(w for w in obs if w in materials)
    
    if exp_mat and obs_mat:
        if not exp_mat.intersection(obs_mat):
            return False, f"Contradicción material: se esperaba {list(exp_mat)} pero se observó {list(obs_mat)}"
            
    colors = {"negro", "blanco", "azul", "rojo", "verde", "amarillo", "gris", "cafe", "beige", "rosado", "morado", "celeste"}
    exp_col = set(w for w in exp if w in colors)
    obs_col = set(w for w in obs if w in colors)
    
    if exp_col and obs_col:
        if not exp_col.intersection(obs_col):
            return False, f"Contradicción material: se esperaba color {list(exp_col)} pero se observó {list(obs_col)}"
            
    return True, "Identidad de producto coincidente"

def get_scraper(marketplace):
    if marketplace == "Mercado Libre": return MercadoLibreScraper(headless=True)
    elif marketplace == "Paris": return ParisScraper(headless=True)
    elif marketplace == "Ripley": return RipleyScraper(headless=True)
    elif marketplace == "Falabella": return FalabellaScraper(headless=True)
    return None

def build_search_url(marketplace, title):
    import urllib.parse
    q = urllib.parse.quote_plus(title)
    if marketplace == "Mercado Libre": return f"https://listado.mercadolibre.cl/{q}"
    elif marketplace == "Paris": return f"https://www.paris.cl/search?q={q}"
    elif marketplace == "Ripley": return f"https://simple.ripley.cl/search/{q}"
    elif marketplace == "Falabella": return f"https://falabella.com/falabella-cl/search?Ntt={q}"
    return ""

async def audit_product(product, materializer, store, state_dict, scraper_instance=None):
    mkt = product["marketplace"]
    title = product["title"]
    search_url = build_search_url(mkt, title)
    
    state_dict["current_product"] = product
    state_dict["status_message"] = f"Comprobando memoria para {title} en {mkt}..."
    
    # Dimension 1: Identidad histórica conocida
    historical_identity_known = False
    mem = store.get_experience_item(mkt, "Nicopoly", "IDENTITY", title)
    if mem and mem.get("status") in ["VALIDATED", "LAST_GOOD"]:
        historical_identity_known = True
        state_dict["status_message"] = f"Identidad histórica conocida para {title}, iniciando verificación actual..."
    else:
        state_dict["status_message"] = f"Identidad desconocida para {title}, iniciando descubrimiento..."
        
    scraper = scraper_instance or get_scraper(mkt)
    results = []
    blocked = False
    start_time = time.time()
    
    state_dict["status_message"] = f"Adquiriendo {title} en {mkt}..."
    
    try:
        if not scraper_instance:
            await scraper.start()
        
        # Max 2 retries logic
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                results = await asyncio.wait_for(scraper.scrape_top_240(search_url), timeout=45)
                break  # Success
            except Exception as e:
                if attempt == max_retries:
                    blocked = True
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    if not error_msg.strip() or error_msg == "TimeoutError: ":
                        error_msg = "TimeoutError"
                else:
                    await asyncio.sleep(1) # wait a bit before retry
    finally:
        if not scraper_instance:
            await scraper.stop()
        
    duration = round(time.time() - start_time, 2)
    
    # Dimension 2: Estado de adquisición actual
    acquisition_state = "SUCCESS"
    if blocked:
        acquisition_state = "SOURCE_BLOCKED"
    elif not results:
        acquisition_state = "NOT_FOUND"

    if acquisition_state != "SUCCESS":
        store.record_experience(mkt, "Nicopoly", "IDENTITY", title, discovery_method="audit", status=acquisition_state, is_success=False, evidence_reference=error_msg if blocked else "0 results from query")
        return {
            "producto_id": product.get("sku", "UNKNOWN"),
            "producto_nombre": title,
            "marketplace": mkt,
            "url_encontrada": search_url,
            "fecha_observacion": datetime.now().isoformat(),
            "evidencia_identidad": [],
            "estado_final": "BLOCKED" if blocked else "FAIL",
            "motivo_verificable": error_msg if blocked else "0 results from query",
            
            # Dimensiones
            "historical_identity_known": historical_identity_known,
            "acquisition_state": acquisition_state,
            "verification_result": "UNTESTED",
            
            # Compatibilidad dashboard
            "status": "SOURCE_BLOCKED" if blocked else "INCONCLUSIVE",
            "classification": "UNKNOWN",
            "reason": error_msg if blocked else "0 results from query",
            "duration": duration,
            "product": product,
            "url": search_url,
            "timestamp": datetime.now().isoformat()
        }
        
    observed = None
    url_encontrada = search_url
    
    # Iterate to find the best identity match
    for res in results:
        obs_title = res.get('title', '')
        identity_match, _ = verify_product_identity_match(title, obs_title)
        
        # We need an individual URL to confirm
        ind_url = res.get("url") or res.get("link")
        
        if identity_match and ind_url and ind_url != search_url:
            observed = res
            url_encontrada = ind_url
            break
            
    if not observed:
        # Fallback to first if none matched perfectly
        observed = results[0]
        url_encontrada = observed.get("url") or observed.get("link") or search_url
    
    # Dimension 3: Resultado de verificación actual
    state_dict["status_message"] = f"Identificando {title}..."
    is_nico = is_nicopoly(observed, marketplace=mkt)
    
    norm = {
        "sku_master": product['sku'],
        "brand": observed.get('vendor') or observed.get('brand', ''),
        "raw_title": observed.get('title', ''),
        "raw_sku": observed.get('marketplace_sku', ''),
        "is_nicopoly": 1 if is_nico else 0,
        "marketplace": mkt,
        "captured_at": datetime.now().isoformat(),
        "raw_price": observed.get('price', 0.0),
        "source_record_id": f"aud_{hashlib.md5(str(observed).encode()).hexdigest()[:10]}"
    }
    
    _pub_key = (norm.get('raw_sku') or (observed or {}).get('id')
                or (observed or {}).get('url')
                or f"pos{(observed or {}).get('position') or 0}")
    pub_id = f"pub_{mkt.lower().replace(' ', '')}_{hashlib.md5(str(_pub_key).encode()).hexdigest()[:12]}"
    ident = {"publication_id": pub_id, "marketplace_product_id": norm["raw_sku"]}
    
    membership = materializer.validate_nicopoly_membership(norm, ident)
    classification = membership.get('classification', 'UNKNOWN')
    
    verification_result = "INSUFFICIENT_EVIDENCE"
    motivo = "INSUFFICIENT_EVIDENCE"
    if classification == "NICOPOLY_CONFIRMED":
        # IDENTITY GATE
        identity_match, identity_reason = verify_product_identity_match(title, norm["raw_title"])
        
        if identity_match:
            if url_encontrada and url_encontrada != search_url:
                verification_result = "CONFIRMED"
                motivo = "Evidencia suficiente según materializador e Identidad Coincidente con URL individual"
                store.record_experience(mkt, "Nicopoly", "IDENTITY", title, parent_identity=norm["raw_sku"], discovery_method="audit_materializer", status="VALIDATED", evidence_reference=str(membership.get("evidence", [])))
            else:
                verification_result = "REVIEW_REQUIRED"
                motivo = "Identidad coincidente pero falta URL de publicación individual"
                store.record_experience(mkt, "Nicopoly", "IDENTITY", title, discovery_method="audit_materializer", status="INVALIDATED", is_success=False, evidence_reference=motivo)
        else:
            verification_result = "REVIEW_REQUIRED"
            motivo = identity_reason
            store.record_experience(mkt, "Nicopoly", "IDENTITY", title, discovery_method="audit_materializer", status="INVALIDATED", is_success=False, evidence_reference=identity_reason)
    elif classification == "NON_NICOPOLY_CONFIRMED":
        verification_result = "REVIEW_REQUIRED"
        motivo = "NON_NICOPOLY_CONFIRMED"
        store.record_experience(mkt, "Nicopoly", "IDENTITY", title, discovery_method="audit_materializer", status="INVALIDATED", is_success=False, evidence_reference="NON_NICOPOLY_CONFIRMED")
    else:
        store.record_experience(mkt, "Nicopoly", "IDENTITY", title, discovery_method="audit_materializer", status="FAILED", is_success=False, evidence_reference="INSUFFICIENT_EVIDENCE")
    
    return {
        "producto_id": product.get("sku", "UNKNOWN"),
        "producto_nombre": title,
        "marketplace": mkt,
        "url_encontrada": url_encontrada,
        "fecha_observacion": datetime.now().isoformat(),
        "evidencia_identidad": membership.get('evidence', []),
        "estado_final": verification_result,
        "motivo_verificable": motivo,
        
        # Dimensiones
        "historical_identity_known": historical_identity_known,
        "acquisition_state": acquisition_state,
        "verification_result": verification_result,
        
        # Compatibilidad dashboard
        "status": verification_result,
        "product": product,
        "classification": classification,
        "observed_sku": norm["raw_sku"],
        "url": url_encontrada,
        "duration": duration,
        "timestamp": datetime.now().isoformat(),
        "evidence": membership.get('evidence', [])
    }


class MRIOrchestrator:
    def __init__(self):
        self.is_running = False
        self.stop_requested = False
        self.state = {
            "progress": 0,
            "total": 0,
            "current_product": None,
            "status_message": "IDLE"
        }
        self.results = []
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            self.history_file = str(StorageConfig.get_history_json_path())
        except Exception:
            self.history_file = "data/mri_history.json"
        self.history = self._load_history()

    def _load_history(self):
        import json
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save_history(self):
        import json
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            StorageConfig.ensure_writable(self.history_file, reason="Runner history persistence")
            StorageConfig.assert_write_allowed(self.history_file)
        except ImportError:
            pass
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2)

    async def run_discovery(self, marketplace="ALL", max_pages=1, run_id=None,
                            limit=None, full_audit=True):
        if self.is_running:
            return
            
        self.is_running = True
        self.results = []
        
        run_id = run_id or f"mri_disc_{uuid.uuid4().hex[:8]}"
        self.state.update({
            "stage": "preparando",
            "total_known": False,
            "marketplace_states": {m: "PENDIENTE" for m in
                (["Mercado Libre", "Paris", "Ripley", "Falabella"]
                 if marketplace == "ALL" else [marketplace])},
            "products_processed": 0,
            "confirmed": 0,
            "errors": [],
            "last_activity": datetime.now().isoformat(),
        })
        materializer = GenericCommercialMaterializer(run_id)
        self.state.update({
            "run_id": run_id,
            "started_at": datetime.now().isoformat(),
            "marketplace": marketplace,
            "mode": "DISCOVERY",
        })
        store = _safe_experience_store()
        
        from app.mri_dashboard.category_manager import category_manager
        
        # Seed categories if empty - REMOVED for fully autonomous execution
        mkts_to_run = [marketplace] if marketplace != "ALL" else ["Mercado Libre", "Paris", "Ripley", "Falabella"]
        
        self.state["total"] = len(mkts_to_run)
        self.state["progress"] = 0

        # Evidence probe for THIS run: the reference-catalog status is a
        # first-class limitation of the acquisition, and it is checked once
        # (not per product) so a missing file cannot flood the log.
        try:
            get_multivende_loader().reset_reference_check()
            _catalog = catalog_reference_status()
        except Exception as _cat_exc:
            _catalog = {"status": "UNKNOWN", "path": None, "error": str(_cat_exc)}
        self.state["catalog_reference"] = _catalog
        self.state["historical_references"] = historical_reference_status()
        # Fail-closed preflight: skills, browsers, profiles (single owner).
        try:
            from app.mri_autonomous.execution_preflight import run_preflight
            _pre = run_preflight(check_auth=False)
            self.state["preflight"] = _pre
            if not _pre.get("ok"):
                self.state["status_message"] = "PREFLIGHT_FAILED"
                self.state["stage"] = "preflight"
                self.state["terminal_state"] = "SOURCE_BLOCKED"
                self.state["outcome"] = "SOURCE_BLOCKED"
                self.state.setdefault("errors", []).append({
                    "stage": "preflight",
                    "error": "PREFLIGHT_FAILED: " + "; ".join(_pre.get("blockers") or []),
                    "run_id": run_id,
                    "at": datetime.now().isoformat()})
                self.is_running = False
                return
        except Exception as _pre_exc:
            self.state["preflight"] = {"ok": False, "error": f"{type(_pre_exc).__name__}: {_pre_exc}"}
        self.state["acquisitions"] = []
        blocked_reason = None
        _cp_aux = None
        
        try:
            for mkt in mkts_to_run:
                if not self.is_running: break

                # MRI-RUNTIME-RECOVERY-001 / Falabella: autonomous SSR audit.
                # Verified mechanism (creao.ai evidence): __NEXT_DATA__, brand +
                # brand-filtered L2 categories + search, union/dedupe, no browser,
                # soft-404 validated by pagination (never HTTP status).
                if mkt == "Falabella" and full_audit:
                    _fba = None
                    try:
                        from app.mri_dashboard import falabella_autonomous as _fba
                        from app.mri_autonomous.falabella_ssr_engine import FalabellaSSREngine
                        try:
                            from app.mri_autonomous.storage_guard import StorageConfig as _SCfba
                            _fba_aux = _SCfba.get_aux_dir()
                        except Exception:
                            _fba_aux = None
                        import asyncio as _aio_fba
                        _audit = await _aio_fba.to_thread(
                            _fba.run_full_audit, FalabellaSSREngine(),
                            brand="NICOPOLY", run_id=run_id, aux_dir=_fba_aux)
                    except Exception as _fba_exc:
                        _audit = {
                            "marketplace": "Falabella", "complete": False,
                            "observations": [], "surfaces": [],
                            "pending_surfaces": ["FALABELLA_SSR_INIT"],
                            "cause": f"{type(_fba_exc).__name__}: {_fba_exc}",
                            "cards_total": 0, "unique_product_ids": 0,
                            "unique_sku_ids": 0, "build_id": None,
                            "categories_discovered": 0, "categories_used": []}
                    self.state["falabella_ssr_audit"] = {
                        k: v for k, v in _audit.items() if k != "observations"}
                    self.state.setdefault("taxonomy", {})["Falabella"] = {
                        "marketplace": "Falabella", "status": "TAXONOMY_DISCOVERED",
                        "source": "SSR_BRAND_SURFACES",
                        "categories": [{"category_id": c}
                                       for c in _audit.get("categories_used") or []]}
                    self.state.setdefault("taxonomy_status", {})["Falabella"] = {
                        "status": "TAXONOMY_DISCOVERED", "cause": None,
                        "source": "SSR_BRAND_SURFACES"}
                    for _r in (_fba.to_runner_results(
                            _audit.get("observations") or [],
                            catalog_status=_catalog.get("status")) if _fba else []):
                        _r["acquisition"]["run_id"] = run_id
                        self.results.append(_r)
                    for _s in _audit.get("surfaces") or []:
                        _st = (FOUND if _s.get("terminal") in ("EXHAUSTION", "EMPTY")
                               else (PARTIAL if _s.get("terminal") == "PAGE_BOUND_REACHED"
                                     else EXTRACTOR_FAILURE))
                        self.state.setdefault("acquisitions", []).append({
                            "run_id": run_id,
                            "engine": f"FALABELLA_SSR::{_s.get('surface')}",
                            "adapter": "FalabellaSSREngine.fetch_page_ssr_data",
                            "requested_url": _s.get("surface"),
                            "acquisition_state": _st,
                            "raw_stop_reason": _s.get("terminal"),
                            "pages_traversed": _s.get("pages_traversed"),
                            "products_extracted": _s.get("cards"),
                            "failure_type": _s.get("cause"),
                            "observed_at": datetime.now().isoformat(),
                        })
                    if not _audit.get("complete"):
                        self.state["status_message"] = "FALABELLA_SSR_INCOMPLETE"
                        self.state.setdefault("errors", []).append({
                            "stage": "adquiriendo",
                            "error": "FALABELLA_SSR incompleto: " + ", ".join(
                                _audit.get("pending_surfaces") or []),
                            "run_id": run_id,
                            "at": datetime.now().isoformat()})
                    self.state.setdefault("marketplace_states", {})[mkt] = (
                        "TERMINADO" if _audit.get("complete") else "PENDIENTE")
                    self.state["total"] = len(self.results)
                    self.state["products_processed"] = len(self.results)
                    self.state["progress"] = 100 if _audit.get("complete") else self.state.get("progress", 0)
                    self.state["pages_observed"] = sum(
                        int(s.get("pages_traversed") or 0) for s in (_audit.get("surfaces") or []))
                    self.state["pages_total"] = self.state["pages_observed"]
                    self.state["last_activity"] = datetime.now().isoformat()
                    continue

                cats = category_manager.get_categories(mkt)
                
                # Autonomous Entry Point: If no accessible categories exist, generate brand search URL
                if not cats:
                    if mkt == "Mercado Libre":
                        search_url = "https://listado.mercadolibre.cl/nicopoly"
                        category_manager.register_category(mkt, "SEARCH_ML", "Búsqueda Nicopoly", search_url, source="AUTONOMOUS_SEARCH", status="VERIFIED")
                        cats = category_manager.get_categories(mkt)
                    elif mkt == "Paris":
                        search_url = "https://www.paris.cl/search?q=nicopoly"
                        category_manager.register_category(mkt, "SEARCH_PARIS", "Búsqueda Nicopoly", search_url, source="AUTONOMOUS_SEARCH", status="VERIFIED")
                        cats = category_manager.get_categories(mkt)
                    elif mkt == "Ripley":
                        search_url = "https://simple.ripley.cl/search/nicopoly"
                        category_manager.register_category(mkt, "SEARCH_RIPLEY", "Búsqueda Nicopoly", search_url, source="AUTONOMOUS_SEARCH", status="VERIFIED")
                        cats = category_manager.get_categories(mkt)
                    elif mkt == "Falabella":
                        search_url = "https://www.falabella.com/falabella-cl/search?Ntt=nicopoly"
                        category_manager.register_category(mkt, "SEARCH_FALABELLA", "Búsqueda Nicopoly", search_url, source="AUTONOMOUS_SEARCH", status="VERIFIED")
                        cats = category_manager.get_categories(mkt)
                
                self.state.setdefault("marketplace_states", {})[mkt] = "EN_CURSO"
                self.state["stage"] = "adquiriendo"
                self.state["last_activity"] = datetime.now().isoformat()
                scraper = get_scraper(mkt)
                if scraper:
                    try:
                        await scraper.start()
                    except Exception as _se:
                        # Un solo reintento acotado: un Chrome residual puede
                        # mantener bloqueado el perfil persistente (TargetClosedError).
                        try:
                            await scraper.stop()
                        except Exception:
                            pass
                        import asyncio as _aio_retry
                        await _aio_retry.sleep(2)
                        try:
                            await scraper.start()
                        except Exception as _se2:
                            raise RuntimeError(
                                "BROWSER_LAUNCH_FAILED after single retry: "
                                f"{type(_se).__name__}: {_se} | "
                                f"{type(_se2).__name__}: {_se2}")
                    # MRI-CATEGORY-COVERAGE-002: full audits discover the real
                    # marketplace taxonomy through the EXISTING engines. The
                    # brand search remains complementary, never the whole scope.
                    if full_audit:
                        try:
                            from app.mri_dashboard import taxonomy as _taxonomy
                            _hub = {
                                "Ripley": "https://simple.ripley.cl/search/nicopoly",
                                "Falabella": "https://www.falabella.com/falabella-cl/search?Ntt=nicopoly",
                                "Mercado Libre": "https://listado.mercadolibre.cl/nicopoly",
                            }.get(mkt)
                            _tax = await _taxonomy.discover_taxonomy_async(
                                mkt, scraper=scraper, hub_url=_hub, brand="Nicopoly")
                        except Exception as _te:
                            _tax = {"marketplace": mkt,
                                    "status": "TAXONOMY_UNAVAILABLE",
                                    "source": "ERROR", "categories": [],
                                    "notes": [f"{type(_te).__name__}: {_te}"]}
                        _tax_status = _tax.get("status")
                        _tax_cause = ((_tax.get("notes") or [None])[0]) or None
                        self.state.setdefault("taxonomy", {})[mkt] = _tax
                        self.state.setdefault("taxonomy_status", {})[mkt] = {
                            "status": _tax_status, "cause": _tax_cause,
                            "source": _tax.get("source")}
                        if full_audit and _tax_status not in (
                                "TAXONOMY_DISCOVERED", "TAXONOMY_NOT_REQUIRED"):
                            # CP1: la ausencia de taxonomía NUNCA se convierte en
                            # NOT_FOUND ni en una búsqueda de marca presentada
                            # como auditoría completa.
                            self.state.setdefault("taxonomy_blocked", {})[mkt] = (
                                _tax_cause or _tax_status)
                            self.state["status_message"] = "TAXONOMY_BLOCKED"
                            self.state["outcome"] = SOURCE_BLOCKED
                            blocked_reason = SOURCE_BLOCKED
                            self.state.setdefault("marketplace_states", {})[mkt] = "PENDIENTE"
                            self.state.setdefault("errors", []).append({
                                "stage": "descubrimiento",
                                "error": f"TAXONOMY_BLOCKED[{mkt}]: {_tax_cause or _tax_status}",
                                "run_id": run_id,
                                "at": datetime.now().isoformat()})
                            continue
                        for _c in _tax.get("categories") or []:
                            if not _c.get("url"):
                                continue
                            category_manager.register_category(
                                mkt,
                                _c.get("category_id") or _c["url"],
                                _c.get("name") or _c.get("category_id") or "CATEGORY",
                                _c["url"], parent_id=_c.get("parent_id"),
                                source="TAXONOMY_DISCOVERY", status="PENDING")
                        cats = category_manager.get_categories(mkt)
                        # MRI-CATEGORY-COVERAGE-003: Falabella full audits use the
                        # MRI-layer SSR paginator (the frozen scraper stops at 2
                        # pages). Real evidence is persisted through the normal
                        # result pipeline; the brand search is not used as scope.
                        if mkt == "Falabella" and _tax.get("status") == "TAXONOMY_DISCOVERED":
                            try:
                                from app.mri_dashboard import falabella_ssr_coverage as _fb
                                from app.mri_autonomous.falabella_ssr_engine import FalabellaSSREngine
                                try:
                                    from app.mri_autonomous.storage_guard import StorageConfig as _SCfb
                                    _fb_aux = _SCfb.get_aux_dir()
                                except Exception:
                                    _fb_aux = None
                                # SSR pagination is blocking HTTP: move it OFF the
                                # event loop (otherwise /api/state freezes while it
                                # traverses N pages x 15s).
                                import asyncio as _aio_fb
                                _fb_res = await _aio_fb.to_thread(
                                    lambda: _fb.traverse_categories(
                                        FalabellaSSREngine(), _tax["categories"],
                                        run_id=run_id, aux_dir=_fb_aux))
                                self.state["falabella_ssr_audit"] = {
                                    k: v for k, v in _fb_res.items() if k != "observations"}
                                # MRI-RUNTIME-RECOVERY-001: cada categoría deja
                                # evidencia de adquisición y causa real, incluso con
                                # 0 publicaciones; el fallo nunca se vuelve NOT_FOUND.
                                _fb_fail = []
                                for _cres in _fb_res.get("categories") or []:
                                    _term = _cres.get("terminal")
                                    _cst = (FOUND if _term in ("EXHAUSTION", "REPORTED_COUNT_REACHED")
                                            else (SOURCE_BLOCKED if _term == "SOURCE_BLOCKED"
                                                  else (PARTIAL if _term == "PAGE_BOUND_REACHED"
                                                        else EXTRACTOR_FAILURE)))
                                    _cacq = {
                                        "run_id": run_id,
                                        "engine": f"FALABELLA_SSR::{_cres.get('category_id')}",
                                        "adapter": "FalabellaSSREngine.get_category_catalog",
                                        "requested_url": _cres.get("url"),
                                        "acquisition_state": _cst,
                                        "raw_stop_reason": _term,
                                        "pages_traversed": _cres.get("pages_traversed"),
                                        "products_extracted": _cres.get("publications"),
                                        "failure_type": _cres.get("cause"),
                                        "observed_at": datetime.now().isoformat(),
                                    }
                                    self.state.setdefault("acquisitions", []).append(_cacq)
                                    if _cst not in (FOUND, PARTIAL):
                                        _fb_fail.append(
                                            f"{_cres.get('category_id')}: {_term} ({_cres.get('cause')})")
                                _fb_empty_unfinished = (not (_fb_res.get("observations") or [])
                                                        and not _fb_res.get("complete"))
                                if _fb_fail or _fb_empty_unfinished:
                                    blocked_reason = (EXTRACTOR_FAILURE if _fb_fail
                                                      else SOURCE_BLOCKED)
                                    self.state["status_message"] = blocked_reason
                                    self.state.setdefault("errors", []).append({
                                        "stage": "adquiriendo",
                                        "error": "FALABELLA_SSR: " + (
                                            ", ".join(_fb_fail[:5]) or "0 publicaciones"),
                                        "run_id": run_id,
                                        "at": datetime.now().isoformat()})
                                for _o in _fb_res.get("observations") or []:
                                    _ident = classify_commercial_identity(
                                        title=_o.get("title") or "",
                                        brand=_o.get("brand") or "",
                                        seller=_o.get("seller") or "",
                                        attributes={"category": _o.get("category_name") or ""})
                                    _acq = {
                                        "run_id": run_id,
                                        "engine": f"FALABELLA_SSR::{_o.get('category_id')}",
                                        "adapter": "FalabellaSSREngine.get_category_catalog",
                                        "requested_url": _o.get("category_url"),
                                        "observed_url": _o.get("url"),
                                        "acquisition_state": FOUND,
                                        "pages_traversed": _o.get("page"),
                                        "products_extracted": 1,
                                        "evidence": _o.get("evidence"),
                                        "observed_at": datetime.now().isoformat(),
                                    }
                                    # Category-level acquisition is the coverage truth;
                                    # no per-observation acquisition entries.
                                    self.results.append({
                                        "producto_id": _o.get("product_id"),
                                        "producto_nombre": _o.get("title"),
                                        "marketplace": "Falabella",
                                        "url_encontrada": _o.get("url"),
                                        "fecha_observacion": datetime.now().isoformat(),
                                        "real_category": _o.get("category_name"),
                                        "category_source": "SSR_TAXONOMY",
                                        "expected_category": _o.get("category_name"),
                                        "decision": "NO_VERIFICADO",
                                        "identity_status": _ident["state"],
                                        "commercial_attributes": {
                                            "seller": _o.get("seller"),
                                            "category_path": _o.get("category_path")},
                                        "status": "OBSERVED",
                                        "acquisition_status": "OBSERVED",
                                        "position_observed": _o.get("position"),
                                        "classification": "NICOPOLY_CANDIDATE",
                                        "observed_sku": _o.get("product_id"),
                                        "url": _o.get("url"),
                                        "acquisition": _acq,
                                        "commercial_identity": _ident,
                                        "official_kpi": identity_is_official_kpi(_ident),
                                        "catalog_reference": _catalog.get("status"),
                                        "classification_basis": "OBSERVED_FEATURES",
                                        "historical_reference": {
                                            "catalog_status": _catalog.get("status"),
                                            "role": "HISTORICAL_REFERENCE",
                                            "authority": "NONE"},
                                        "timestamp": datetime.now().isoformat(),
                                    })
                                self.state["total"] = len(self.results)
                                self.state["products_processed"] = len(self.results)
                            except Exception as _fbe:
                                self.state.setdefault("errors", []).append({
                                    "stage": "adquiriendo",
                                    "error": f"FALABELLA_SSR_TRAVERSAL: {type(_fbe).__name__}: {_fbe}",
                                    "run_id": run_id,
                                })
                            self.state.setdefault("marketplace_states", {})[mkt] = (
                                "TERMINADO" if (self.state.get("falabella_ssr_audit") or {}).get("complete")
                                else "PENDIENTE")
                            continue
                    
                # CP4: resume from a per-category checkpoint of the SAME run.
                try:
                    from app.mri_autonomous.storage_guard import StorageConfig as _SCp
                    _cp_aux = _SCp.get_aux_dir()
                except Exception:
                    _cp_aux = None
                _cp_done = set()
                if _cp_aux and full_audit:
                    try:
                        _cpk = _coverage.load_checkpoint(_cp_aux, run_id)
                        for _cid0, _c0 in ((_cpk or {}).get("categories") or {}).items():
                            if _c0.get("status") == "COMPLETE":
                                _cp_done.add(_c0.get("url") or _cid0)
                    except Exception:
                        _cp_done = set()
                try:
                    for cat_id, cat_data in list(cats.items()):
                        if not self.is_running: break
                        url = cat_data["url"]
                        if url in _cp_done:
                            # Página/categoría ya confirmada en checkpoint previo.
                            continue
                        
                        self.state["status_message"] = f"Descubriendo {mkt} - {cat_data['name']}..."
                        self.state["current_category"] = f"{mkt} ? {cat_data['name']}"
                        self.state["last_activity"] = datetime.now().isoformat()
                        
                        # Call-site compatibility: only scrapers that declare
                        # `supports_pagination` accept `max_pages`. Visual Auditor
                        # scrapers are frozen (zero diff vs origin/main) and must
                        # not be modified to satisfy an MRI call signature, so the
                        # capability is negotiated here instead.
                        # MRI-CATEGORY-COVERAGE-001: pagination is bounded ONLY
                        # by the source's own terminal condition. The UI `limit`
                        # must never act as an artificial coverage cap (Ripley
                        # stopped at 240 = 5 pages x 48 because limit=5 was mapped
                        # to max_pages; Paris ignored max_pages and reached full
                        # coverage). Visual Auditor scrapers stay frozen.
                        # Watchdog: a frozen page/DOM must not hang the whole run.
                        import asyncio as _aio_cat
                        try:
                            if getattr(scraper, "supports_pagination", False):
                                res = await _aio_cat.wait_for(
                                    scraper.scrape_autonomous_category(
                                        url, max_pages=_coverage.PAGE_SENTINEL),
                                    timeout=240)
                            else:
                                res = await _aio_cat.wait_for(
                                    scraper.scrape_autonomous_category(url),
                                    timeout=240)
                        except _aio_cat.TimeoutError:
                            res = {"products": [], "stop_reason": "NO_PROGRESS",
                                   "pages_traversed": 0,
                                   "failure_type": "CATEGORY_TIMEOUT_240S"}
                        except Exception as _cat_exc:
                            res = {"products": [], "stop_reason": "EXTRACTOR_FAILURE",
                                   "pages_traversed": 0,
                                   "failure_type": f"{type(_cat_exc).__name__}: {_cat_exc}"}

                        discovered_products = res.get("products", []) or []
                        raw_stop = res.get("stop_reason")
                        acq_state = normalize_stop_reason(raw_stop)
                        try:
                            _observed_url = (scraper.page.url
                                             if getattr(scraper, "page", None) else None)
                        except Exception:
                            _observed_url = None
                        acq_evidence = {
                            "run_id": run_id,
                            "engine": f"DISCOVERY::{mkt}",
                            "adapter": type(scraper).__name__,
                            "requested_url": url,
                            "observed_url": _observed_url,
                            "raw_stop_reason": raw_stop,
                            "acquisition_state": acq_state,
                            "pages_traversed": res.get("pages_traversed"),
                            "failure_type": res.get("failure_type"),
                            "products_extracted": len(discovered_products),
                            "observed_at": datetime.now().isoformat(),
                            "catalog_reference": _catalog.get("status"),
                        }
                        self.state.setdefault("acquisitions", []).append(acq_evidence)
                        self.state["current_acquisition"] = acq_evidence
                        # CP4: checkpoint atómico por categoría/página confirmada
                        # (escrito en la ruta de scraper realmente usada).
                        if _cp_aux:
                            try:
                                _cp_cov = _coverage.new_coverage(run_id, marketplace, {})
                                for _a2 in (self.state.get("acquisitions") or []):
                                    _u2 = _a2.get("requested_url") or "cat"
                                    _cp_cov["categories"][_u2] = {
                                        "name": _u2, "url": _u2, "status": "PENDING",
                                        "pages_observed": 0, "termination": None,
                                        "publications": 0, "last_id": None,
                                        "stop_reason": None}
                                    _coverage.record_category(
                                        _cp_cov, _u2,
                                        pages=_a2.get("pages_traversed") or 0,
                                        stop_state=_a2.get("acquisition_state"),
                                        publications=_a2.get("products_extracted") or 0)
                                _coverage.save_checkpoint(_cp_aux, _cp_cov)
                            except Exception:
                                pass

                        if not discovered_products and acq_state in BLOCKING_STATES:
                            # A blocked/failed source must never be reported as an
                            # absence of publications: name the real state.
                            self.state["status_message"] = acq_state
                            blocked_reason = acq_state
                            category_manager.register_category(mkt, cat_id, cat_data["name"], url, status=acq_state)
                            continue

                        coverage = ("COMPLETE" if acq_state == FOUND
                                    else (acq_state or PARTIAL))
                        
                        # Mark category as VERIFIED since we ran it
                        category_manager.register_category(mkt, cat_id, cat_data["name"], url, status="VERIFIED")
                        
                        # No artificial publication cap: every observed product
                        # of every traversed page is evaluated (48/96/240 are
                        # historical technical limits, never coverage totals).
                        self.state["total"] += len(discovered_products)
                        
                        for item_idx, observed in enumerate(discovered_products, 1):
                            if not self.is_running: break
                            
                            # Real observed position: prefer scraper-extracted position, fallback to enumeration order
                            pos_obs = observed.get("position_absolute") or observed.get("position") or item_idx
                            title = observed.get("title", "UNKNOWN")
                            prod_url = observed.get("url") or observed.get("link")
                            raw_sku = observed.get('marketplace_sku', '')

                            # Canonical URL formatting for Paris if missing or relative
                            if mkt == "Paris":
                                if not prod_url or not str(prod_url).startswith("http"):
                                    if raw_sku:
                                        prod_url = f"https://www.paris.cl/{raw_sku}.html"
                                    elif observed.get("id"):
                                        prod_url = f"https://www.paris.cl/{observed.get('id')}.html"

                            self.state["status_message"] = f"Verificando {title[:30]}..."
                            start_time = time.time()
                            
                            is_nico = is_nicopoly(observed, marketplace=mkt)
                            
                            norm = {
                                "sku_master": raw_sku, # Fallback to observed SKU
                                "brand": observed.get('vendor') or observed.get('brand', ''),
                                "raw_title": title,
                                "raw_sku": raw_sku,
                                "is_nicopoly": 1 if is_nico else 0,
                                "marketplace": mkt,
                                "captured_at": datetime.now().isoformat(),
                                "raw_price": observed.get('price', 0.0),
                                "source_record_id": f"disc_{hashlib.md5(str(observed).encode()).hexdigest()[:10]}"
                            }
                            
                            _pub_key = (norm.get('raw_sku') or (observed or {}).get('id')
                                        or (observed or {}).get('url')
                                        or f"pos{(observed or {}).get('position') or 0}")
                            pub_id = f"pub_{mkt.lower().replace(' ', '')}_{hashlib.md5(str(_pub_key).encode()).hexdigest()[:12]}"
                            ident = {"publication_id": pub_id, "marketplace_product_id": norm["raw_sku"]}
                            
                            membership = materializer.validate_nicopoly_membership(norm, ident)
                            classification = membership.get('classification', 'UNKNOWN')
                            
                            # CATEGORY & ATTRIBUTE PUBLIC EXTRACTION
                            real_category = "CATEGORY_UNKNOWN"
                            real_subcategory = "CATEGORY_UNKNOWN"
                            category_source = "NONE"
                            public_attrs = {}
                            corredor_tipo = None
                            
                            # Recover public data from individual URL
                            if prod_url and scraper and scraper.page:
                                self.state["status_message"] = f"Extrayendo categoría y atributos de {title[:30]}..."
                                try:
                                    import random
                                    import asyncio
                                    await scraper.page.goto(prod_url, wait_until="commit", timeout=15000)
                                    await asyncio.sleep(random.uniform(0.5, 1.2))

                                    # Extract breadcrumbs and public attributes depending on marketplace
                                    if mkt == "Mercado Libre":
                                        crumbs = await scraper.page.evaluate('''() => {
                                            return Array.from(document.querySelectorAll('.andes-breadcrumb__link')).map(el => {
                                                return {name: el.innerText.trim(), url: el.href};
                                            });
                                        }''')
                                        if crumbs and len(crumbs) > 0:
                                            real_category = crumbs[0]['name']
                                            if len(crumbs) > 1:
                                                real_subcategory = crumbs[1]['name']
                                            category_source = "PUBLIC_CHANNEL_BREADCRUMBS"
                                            category_manager.register_category(mkt, f"CAT_{real_category.replace(' ', '_')}", real_category, crumbs[0]['url'], source="OBSERVED", status="VERIFIED")
                                            if len(crumbs) > 1:
                                                category_manager.register_category(mkt, f"CAT_{real_subcategory.replace(' ', '_')}", real_subcategory, crumbs[1]['url'], parent_id=f"CAT_{real_category.replace(' ', '_')}", source="OBSERVED", status="VERIFIED")
                                                
                                    elif mkt == "Falabella":
                                        # Breadcrumbs
                                        crumbs = await scraper.page.evaluate('''() => {
                                            return Array.from(document.querySelectorAll('[class*="Breadcrumbs-module_breadcrumb"] a, .breadcrumb a, [class*="breadcrumbs"] a')).map(el => {
                                                return {name: el.innerText.trim(), url: el.href};
                                            });
                                        }''')
                                        if crumbs and len(crumbs) > 0:
                                            real_category = " → ".join(c['name'] for c in crumbs if c['name'] and c['name'] != 'Home')
                                            category_source = "PUBLIC_CHANNEL_BREADCRUMBS"
                                            
                                        # Public Specifications / Attributes from DOM table
                                        specs = await scraper.page.evaluate('''() => {
                                            const attrs = {};
                                            const rows = document.querySelectorAll('tr, [class*="spec-row"], [class*="property-row"]');
                                            rows.forEach(r => {
                                                const cells = r.querySelectorAll('td, th, span, div');
                                                if (cells.length >= 2) {
                                                    const k = cells[0].innerText.trim();
                                                    const v = cells[1].innerText.trim();
                                                    if (k && v && k.length < 50 && v.length < 100) attrs[k] = v;
                                                }
                                            });
                                            return attrs;
                                        }''')
                                        if specs:
                                            public_attrs.update(specs)
                                            if "Tipo" in public_attrs or any("tipo" in k.lower() for k in public_attrs):
                                                category_source = "PUBLIC_CHANNEL_ATTRIBUTES"

                                    elif mkt == "Ripley":
                                        # Breadcrumbs: Moda Mujer → Marcas Casuales → Nicopoly
                                        crumbs = await scraper.page.evaluate('''() => {
                                            const nav = document.querySelector('nav[aria-label*="Breadcrumb" i], [class*="breadcrumb" i], [class*="Breadcrumb" i]');
                                            if (nav) {
                                                const links = Array.from(nav.querySelectorAll('a, li, span')).map(el => el.innerText.trim()).filter(Boolean);
                                                return links;
                                            }
                                            return [];
                                        }''')
                                        if crumbs and len(crumbs) > 0:
                                            # Clean duplicate breadcrumb tokens
                                            clean_crumbs = []
                                            for c in crumbs:
                                                if c not in clean_crumbs and c.lower() not in ('inicio', 'home', '>'):
                                                    clean_crumbs.append(c)
                                            if clean_crumbs:
                                                real_category = " → ".join(clean_crumbs)
                                                category_source = "PUBLIC_CHANNEL_BREADCRUMBS"
                                                if any('marcas casuales' in c.lower() or 'nicopoly' in c.lower() for c in clean_crumbs):
                                                    corredor_tipo = "TIENDA_DE_MARCA"
                                        
                                        # Specifications table & Seller / Brand Store link
                                        specs_and_seller = await scraper.page.evaluate('''() => {
                                            const attrs = {};
                                            const rows = document.querySelectorAll('table tr');
                                            rows.forEach(r => {
                                                const cells = r.querySelectorAll('td, th');
                                                if (cells.length >= 2) {
                                                    const k = cells[0].innerText.trim();
                                                    const v = cells[1].innerText.trim();
                                                    if (k && v) attrs[k] = v;
                                                }
                                            });
                                            
                                            // Check seller / brand store link
                                            let storeUrl = null;
                                            const sLink = document.querySelector('a[href*="/tienda/"], [class*="seller" i] a, [class*="vendor" i] a');
                                            if (sLink && sLink.href) {
                                                storeUrl = sLink.href;
                                            }
                                            return { attrs, storeUrl };
                                        }''')
                                        if specs_and_seller:
                                            if specs_and_seller.get("attrs"):
                                                public_attrs.update(specs_and_seller["attrs"])
                                            if specs_and_seller.get("storeUrl"):
                                                public_attrs["store_url"] = specs_and_seller["storeUrl"]
                                            
                                    elif mkt == "Paris":
                                        crumbs = await scraper.page.evaluate('''() => {
                                            const selectors = [
                                                '.breadcrumb a',
                                                '[class*="breadcrumb" i] a',
                                                '[class*="Breadcrumb" i] a',
                                                '[data-testid*="breadcrumb" i] a',
                                                'nav[aria-label*="breadcrumb" i] a',
                                                'ol[class*="breadcrumb" i] li'
                                            ];
                                            for (const sel of selectors) {
                                                const els = Array.from(document.querySelectorAll(sel)).map(el => el.innerText.trim()).filter(Boolean);
                                                if (els.length > 0) return els;
                                            }
                                            return [];
                                        }''')
                                        if crumbs and len(crumbs) > 0:
                                            clean_crumbs = []
                                            for c in crumbs:
                                                if c not in clean_crumbs and c.lower() not in ('inicio', 'home', '>'):
                                                    clean_crumbs.append(c)
                                            if clean_crumbs:
                                                real_category = " → ".join(clean_crumbs)
                                                category_source = "PUBLIC_CHANNEL_BREADCRUMBS"
                                                
                                except Exception as e:
                                    print(f"Error fetching breadcrumbs/attributes for {prod_url}: {e}")
                            
                            # Master Catalog & Identity Resolution
                            resolved_master_sku = None
                            parent_sku = None
                            variant_sku = None
                            candidate_variants = []
                            expected_category = None
                            identity_status = "IDENTIDAD_NO_VERIFICADA"
                            
                            from app.mri_dashboard.mri_api import get_master_catalog, clean_cat_title, normalize_title_tokens
                            child_to_cat, parent_to_cat, title_to_cat, token_to_entries = get_master_catalog()
                            
                            # 1. Try matching by raw_sku extracted or parsed ID
                            sku_cand = raw_sku
                            if mkt == "Paris" and "MKC" in raw_sku:
                                m_p = re.search(r"(MKC[0-9A-Z]+)", raw_sku)
                                if m_p:
                                    sku_cand = m_p.group(1)
                                    
                            if sku_cand and sku_cand in child_to_cat:
                                m_match = child_to_cat[sku_cand]
                                variant_sku = sku_cand
                                parent_sku = m_match.get("parent")
                                resolved_master_sku = variant_sku
                                expected_category = m_match.get("category")
                                identity_status = "TARGET_IDENTITY_VERIFIED"
                            elif sku_cand and sku_cand in parent_to_cat:
                                m_match = parent_to_cat[sku_cand]
                                parent_sku = sku_cand
                                resolved_master_sku = parent_sku
                                expected_category = m_match.get("category")
                                identity_status = "PARENT_IDENTITY_VERIFIED"
                            elif title:
                                c_key = clean_cat_title(title)
                                if c_key and c_key in title_to_cat:
                                    m_match = title_to_cat[c_key]
                                    parent_sku = m_match.get("parent")
                                    resolved_master_sku = parent_sku
                                    expected_category = m_match.get("category")
                                    # Check if title corresponds to multiple variants
                                    t_toks = normalize_title_tokens(title)
                                    if t_toks and t_toks in token_to_entries:
                                        candidate_variants = [e.get("child") for e in token_to_entries[t_toks] if e.get("child")]
                                    if candidate_variants and len(candidate_variants) > 1:
                                        identity_status = "PARENT_IDENTITY_VERIFIED"
                                    else:
                                        variant_sku = m_match.get("child")
                                        resolved_master_sku = variant_sku or parent_sku
                                        identity_status = "TARGET_IDENTITY_VERIFIED"
                                else:
                                    t_toks = normalize_title_tokens(title)
                                    if t_toks and t_toks in token_to_entries:
                                        entries = token_to_entries[t_toks]
                                        parents = {e.get("parent") for e in entries if e.get("parent")}
                                        if len(parents) == 1:
                                            m_match = entries[0]
                                            parent_sku = m_match.get("parent")
                                            resolved_master_sku = parent_sku
                                            expected_category = m_match.get("category")
                                            candidate_variants = [e.get("child") for e in entries if e.get("child")]
                                            if len(candidate_variants) > 1:
                                                identity_status = "PARENT_IDENTITY_VERIFIED"
                                            else:
                                                variant_sku = candidate_variants[0]
                                                resolved_master_sku = variant_sku or parent_sku
                                                identity_status = "TARGET_IDENTITY_VERIFIED"
                            
                            if parent_sku and not candidate_variants:
                                candidate_variants = [c for c, e in child_to_cat.items() if e.get("parent") == parent_sku]
                            
                            # Commercial Evaluation & Double Membership
                            brand_corridor_val = corredor_tipo if corredor_tipo == "TIENDA_DE_MARCA" else None
                            if not brand_corridor_val and any(m in real_category.lower() for m in ['marcas casuales', 'tienda_de_marca', 'tienda oficial', 'tienda/nicopoly', 'brand store', 'brand hub']):
                                brand_corridor_val = real_category
                            if public_attrs and "store_url" in public_attrs:
                                brand_corridor_val = f"Tienda oficial Nicopoly ({public_attrs['store_url']})"

                            cat_eval = evaluate_commercial_category(
                                product_title=title,
                                expected_category=expected_category or "NO_VERIFICADO",
                                observed_category=real_category,
                                public_attributes=public_attrs,
                                marketplace=mkt,
                                identity_status=identity_status,
                                brand_corridor=brand_corridor_val
                            )
                            category_decision = cat_eval.get("decision", "REVIEW_REQUIRED")
                            category_reason = cat_eval.get("reason", "")
                            
                            verification_result = "INSUFFICIENT_EVIDENCE"
                            motivo = "INSUFFICIENT_EVIDENCE"
                            
                            if classification == "NICOPOLY_CONFIRMED":
                                if prod_url:
                                    verification_result = category_decision
                                    motivo = category_reason or "Evidencia suficiente según materializador"
                                    store.record_experience(mkt, "Nicopoly", "DISCOVERY", title, parent_identity=norm["raw_sku"], discovery_method="autonomous_category", status="VALIDATED", evidence_reference=str(membership.get("evidence", [])))
                                else:
                                    verification_result = "REVIEW_REQUIRED"
                                    motivo = "Pertenece a la marca pero falta URL individual"
                                    store.record_experience(mkt, "Nicopoly", "DISCOVERY", title, discovery_method="autonomous_category", status="INVALIDATED", is_success=False, evidence_reference=motivo)
                            elif classification == "NON_NICOPOLY_CONFIRMED":
                                verification_result = "REVIEW_REQUIRED"
                                motivo = "NON_NICOPOLY_CONFIRMED"
                                store.record_experience(mkt, "Nicopoly", "DISCOVERY", title, discovery_method="autonomous_category", status="INVALIDATED", is_success=False, evidence_reference="NON_NICOPOLY_CONFIRMED")
                            else:
                                store.record_experience(mkt, "Nicopoly", "DISCOVERY", title, discovery_method="autonomous_category", status="FAILED", is_success=False, evidence_reference="INSUFFICIENT_EVIDENCE")

                            evidence_items = list(membership.get('evidence', []))
                            if real_category != "CATEGORY_UNKNOWN":
                                evidence_items.append(f"Ruta pública: {real_category} ({category_source})")
                            if public_attrs:
                                evidence_items.append(f"Atributos públicos: {public_attrs}")
                            if corredor_tipo or brand_corridor_val:
                                evidence_items.append(f"Corredor de marca: {brand_corridor_val or corredor_tipo}")

                            # ── Commercial identity contract (never official from
                            # the title alone; used third-party is excluded from
                            # the official visibility KPI) ─────────────────────
                            _vendor_field = observed.get('vendor') or observed.get('brand', '') or ''
                            _seller_field = (observed.get('seller')
                                             or observed.get('seller_name')
                                             or (public_attrs.get('seller')
                                                 if isinstance(public_attrs, dict) else None)
                                             or '')
                            commercial_identity = classify_commercial_identity(
                                title=title,
                                brand=norm.get("brand", ""),
                                vendor=_vendor_field,
                                seller=_seller_field,
                                attributes={**((public_attrs if isinstance(public_attrs, dict)
                                                else {})),
                                            "category": real_category,
                                            "brand_corridor": brand_corridor_val or ""},
                                official_store=bool(brand_corridor_val),
                                brand_evidence_verified=(identity_status in
                                                         ("TARGET_IDENTITY_VERIFIED",
                                                          "PARENT_IDENTITY_VERIFIED")),
                            )
                            _pk = position_kind(prod_url or "",
                                                public_attrs if isinstance(public_attrs, dict) else {})
                            official_kpi = is_official_kpi_eligible(commercial_identity, _pk)
                            acquisition_evidence = dict(acq_evidence)
                            acquisition_evidence.update({
                                "position": pos_obs,
                                "sku": raw_sku,
                                "url": prod_url,
                            })
                            evidence_items.append(
                                f"Identidad comercial: {commercial_identity['state']} — "
                                f"{commercial_identity['reason']}")

                            # Historical reference may never confirm by itself: a
                            # classification with no observable product feature is
                            # explicitly NO_VERIFICADO.
                            _basis = classification_basis({
                                "title": title,
                                "brand": norm.get("brand", ""),
                                "vendor": _vendor_field,
                                "observed_category": real_category,
                            })
                            if classification == "NICOPOLY_CONFIRMED" and _basis == "HISTORICAL_REFERENCE":
                                verification_result = "NO_VERIFICADO"
                                motivo = ("Solo referencia histórica: sin características "
                                          "observables suficientes del producto")
                            historical_ref = {
                                "catalog_status": _catalog.get("status"),
                                "role": "HISTORICAL_REFERENCE",
                                "authority": "NONE",
                            }

                            self.results.append({
                                "producto_id": resolved_master_sku or raw_sku,
                                "producto_nombre": title,
                                "marketplace": mkt,
                                "url_encontrada": prod_url,
                                "fecha_observacion": datetime.now().isoformat(),
                                "evidencia_identidad": evidence_items,
                                "estado_final": verification_result,
                                "motivo_verificable": motivo,
                                "coverage": coverage,
                                "category_url": url,
                                
                                # category identification & double membership
                                "real_category": real_category,
                                "real_subcategory": real_subcategory,
                                "category_source": category_source,
                                "expected_category": expected_category,
                                "decision": category_decision,
                                "identity_status": identity_status,
                                "parent_sku": parent_sku,
                                "variant_sku": variant_sku,
                                "candidate_variants": candidate_variants,
                                "commercial_attributes": public_attrs,
                                "corredor_tipo": corredor_tipo or ("TIENDA_DE_MARCA" if brand_corridor_val else None),
                                "brand_corridor": brand_corridor_val,
                                
                                # dashboard specific
                                "status": verification_result,
                                "acquisition_status": "OBSERVED",
                                "position_observed": pos_obs,
                                "position": pos_obs,
                                "product": {"title": title, "sku": resolved_master_sku or raw_sku},
                                "classification": classification,
                                "observed_sku": raw_sku,
                                "url": prod_url,
                                "duration": round(time.time() - start_time, 2),
                                "timestamp": datetime.now().isoformat(),

                                # acquisition truth: provenance of the record
                                "acquisition": acquisition_evidence,
                                "commercial_identity": commercial_identity,
                                "official_kpi": official_kpi,
                                "position_kind": _pk,
                                "sponsored": _pk == "SPONSORED",
                                "catalog_reference": _catalog.get("status"),
                                "classification_basis": _basis,
                                "historical_reference": historical_ref,
                            })
                            self.state["progress"] += 1
                            self.state["products_processed"] = self.state.get("progress", 0)
                            self.state["last_activity"] = datetime.now().isoformat()
                    self.state.setdefault("marketplace_states", {})[mkt] = "TERMINADO"
                        
                finally:
                    if scraper:
                        await scraper.stop()
                        
            # ── Terminal outcome driven by the acquisition contract ──────────
            acqs = self.state.get("acquisitions") or []
            blocking_states = [a.get("acquisition_state") for a in acqs
                               if a.get("acquisition_state") in BLOCKING_STATES]
            partial_state = any(a.get("acquisition_state") == PARTIAL for a in acqs)
            if self.stop_requested or not self.is_running:
                outcome = "STOPPED_BY_USER"
            elif self.results:
                # Products were extracted but some acquisition was blocked or
                # partial: the run is PARTIAL, never a clean success.
                outcome = PARTIAL if (blocking_states or partial_state) else FOUND
            else:
                # CP1: a blocked taxonomy/scope must NOT degrade into NOT_FOUND.
                outcome = (blocking_states[0] if blocking_states
                           else (blocked_reason or resolve_outcome(0, None)))

            self.state["outcome"] = outcome
            self.state["status_message"] = {
                FOUND: "COMPLETED",
                NOT_FOUND: "NOT_FOUND",
                PARTIAL: "PARTIAL",
                "STOPPED_BY_USER": "STOPPED_BY_USER",
            }.get(outcome, outcome)
            if self.state.get("taxonomy_blocked"):
                # Preserve the operational cause; acceptance stays AUDIT_FAIL.
                self.state["status_message"] = "TAXONOMY_BLOCKED"
            identity_summary = summarize_identities(self.results)
            self.state["identity_summary"] = identity_summary
            self.state["extracted_records"] = len(self.results)
            if outcome in (SOURCE_BLOCKED, EXTRACTOR_FAILURE):
                self.state.setdefault("errors", []).append({
                    "stage": "adquiriendo",
                    "error": f"{outcome}: 0 publications captured",
                    "run_id": run_id,
                    "at": datetime.now().isoformat(),
                    "acquisitions": acqs,
                })
            
            # Coverage contract (MRI-CATEGORY-COVERAGE-001): binary acceptance.
            _cov = _coverage.new_coverage(run_id, marketplace, {})
            for _a in (self.state.get("acquisitions") or []):
                _cid = _a.get("requested_url") or f"cat_{len(_cov['categories'])}"
                _cov["categories"][_cid] = {
                    "name": _a.get("requested_url"), "url": _a.get("requested_url"),
                    "status": "PENDING", "pages_observed": 0, "termination": None,
                    "publications": 0, "last_id": None, "stop_reason": None}
                _coverage.record_category(
                    _cov, _cid,
                    pages=_a.get("pages_traversed") or 0,
                    stop_state=_a.get("acquisition_state"),
                    publications=_a.get("products_extracted") or 0)
            # CP4: a resumed run that skipped already-confirmed categories must
            # not erase those entries from the coverage/checkpoint.
            if _cp_aux:
                try:
                    _prev_cp = _coverage.load_checkpoint(_cp_aux, run_id) or {}
                    for _k, _v in (_prev_cp.get("categories") or {}).items():
                        _cov["categories"].setdefault(_k, _v)
                except Exception:
                    pass
            _cov = _coverage.finalize(
                _cov,
                unique_publications=identity_summary["unique_marketplace_ids"])
            _cov["publications_observed"] = len(self.results)
            _fba = self.state.get("falabella_ssr_audit") or {}
            if _fba and not _fba.get("complete"):
                # A safety-bound or stalled SSR traversal is NEVER AUDIT_PASS.
                _cov["acceptance"] = _coverage.AUDIT_FAIL
                _cov["termination_condition"] = "INCOMPLETE"
                _cov["acceptance_reasons"].append(
                    "Falabella SSR incompleto: " + ", ".join(
                        "%s:%s" % (c.get("category_id"), c.get("terminal"))
                        for c in (_fba.get("categories") or [])[:5]))
            # Taxonomy evidence is part of acceptance: without a discovered
            # taxonomy the scope is incomplete, so acceptance can only be FAIL.
            try:
                from app.mri_dashboard import taxonomy as _taxonomy_sum
                _tax_summary = _taxonomy_sum.summarize(self.state.get("taxonomy") or {})
            except Exception:
                _tax_summary = {"complete_scope": False, "unavailable": [marketplace]}
            self.state["taxonomy_summary"] = _tax_summary
            if full_audit and not _tax_summary.get("complete_scope"):
                _cov["acceptance"] = _coverage.AUDIT_FAIL
                _cov["acceptance_reasons"].append(
                    "taxonomia no demostrada: " + ", ".join(
                        (_tax_summary.get("unavailable") or [])
                        + (_tax_summary.get("pending") or []) or ["sin descubrimiento"]))
            self.state["coverage"] = _cov
            self.state["acceptance"] = _cov["acceptance"]
            try:
                from app.mri_autonomous.storage_guard import StorageConfig as _SCov2
                _coverage.save_checkpoint(_SCov2.get_aux_dir(), _cov)
            except Exception:
                pass

            # Save to SQLite DB for persistent API querying.
            # The run row is ALWAYS written, even with zero publications, so a
            # blocked run has verifiable provenance instead of disappearing.
            run_marketplaces = sorted({r["marketplace"] for r in self.results
                                       if r.get("marketplace")})
            if len(run_marketplaces) == 1:
                run_marketplace = run_marketplaces[0]
            elif run_marketplaces:
                run_marketplace = "MULTI_MARKETPLACE"
            else:
                run_marketplace = marketplace
            engine_label = "DISCOVERY::" + ("+".join(run_marketplaces) if run_marketplaces
                                            else str(marketplace))
            run_meta = {
                "marketplace": run_marketplace,
                "execution_mode": engine_label,
                "source_method": "DASHBOARD_DISCOVERY_SCRAPER",
                "terminal_state": outcome,
                "started_at": self.state.get("started_at"),
                # CP1: taxonomy outcome is first-class provenance, not a log line.
                "taxonomy_status": {
                    _m: (_v or {}).get("status")
                    for _m, _v in (self.state.get("taxonomy_status") or {}).items()},
                "taxonomy_cause": {
                    _m: (_v or {}).get("cause")
                    for _m, _v in (self.state.get("taxonomy_status") or {}).items()},
            }
            try:
                import json
                from app.mri_autonomous.recovery_runner import AcquisitionRecoveryRunner
                rec_runner = AcquisitionRecoveryRunner()
                obs_to_persist = []
                _seen_pid, _discards = set(), []
                for res in self.results:
                    _pid = res.get("observed_sku") or res.get("producto_id")
                    if _pid in _seen_pid:
                        # CP2: no fabricar registros para igualar contadores;
                        # registrar el descarte con su identificador y motivo.
                        _discards.append({
                            "publication_id": _pid,
                            "url": res.get("url"),
                            "position": res.get("position_observed"),
                            "reason": "DUPLICATE_PUBLICATION_ID"})
                        continue
                    _seen_pid.add(_pid)
                    obs_to_persist.append({
                        "publication_id": _pid,
                        "marketplace": res.get("marketplace"),
                        "observed_url": res.get("url"),
                        "position_observed": res.get("position_observed") or 1,
                        "title": res.get("producto_nombre"),
                        "observation_timestamp": res.get("timestamp"),
                        "status": "OBSERVED",
                        "acquisition_status": "OBSERVED",
                        "identity_status": (res.get("commercial_identity") or {}).get("state")
                        or res.get("identity_status"),
                        "category_observed": res.get("real_category"),
                        "category_source": res.get("category_source"),
                        "category_expected": res.get("expected_category"),
                        "category_decision": res.get("decision"),
                        "commercial_attributes": json.dumps({
                            "observed_attributes": res.get("commercial_attributes") or {},
                            "commercial_identity": res.get("commercial_identity"),
                            "acquisition": res.get("acquisition"),
                            "catalog_reference": res.get("catalog_reference"),
                            "official_kpi": res.get("official_kpi"),
                            "position_kind": res.get("position_kind"),
                            "sponsored": res.get("sponsored"),
                        }, ensure_ascii=False)
                    })
                self.state["persistence"] = {
                    "source_results": len(self.results),
                    "stored_observations": len(obs_to_persist),
                    "duplicates_collapsed": len(_discards),
                    "discard_examples": _discards[:14],
                }
                rec_runner.persist_to_sqlite(
                    {"observations": obs_to_persist, "terminal_state": outcome},
                    run_id, run_meta=run_meta)
            except Exception as e:
                print(f"Error persisting discovery run to SQLite: {e}")

            # Save to history
            self.history.append({
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "marketplace": run_marketplace,
                "total": sum(1 for r in self.results),
                "confirmed": identity_summary["official_kpi_eligible"],
                "results": list(self.results),
                "mode": "DISCOVERY",
                "terminal_state": self.state["status_message"],
                "outcome": outcome,
                "engine": engine_label,
                "identity_summary": identity_summary,
                "acquisitions": acqs,
                "catalog_reference": _catalog,
                "coverage": _cov,
                "acceptance": _cov.get("acceptance"),
                "taxonomy": self.state.get("taxonomy_status") or {},
                "taxonomy_blocked": self.state.get("taxonomy_blocked") or {},
                "falabella_ssr_audit": self.state.get("falabella_ssr_audit"),
                "persistence": self.state.get("persistence") or {},
            })
            self._save_history()

        except Exception as _fatal:
            # An exception during acquisition (e.g. the browser engine cannot
            # start) must still leave a terminal, persisted, provenance-tagged
            # run. It is never silently dropped and never reported as success.
            from app.mri_dashboard.acquisition_contract import EXTRACTOR_FAILURE as _EF
            self.state["failed_stage"] = self.state.get("stage") or "preparando"
            self.state["error"] = f"{type(_fatal).__name__}: {_fatal}"
            self.state["outcome"] = _EF
            self.state["status_message"] = _EF
            self.state["last_activity"] = datetime.now().isoformat()
            self.state["identity_summary"] = summarize_identities(self.results)
            self.state["extracted_records"] = len(self.results)
            self.state.setdefault("errors", []).append({
                "stage": self.state["failed_stage"],
                "error": self.state["error"],
                "run_id": run_id,
                "at": datetime.now().isoformat(),
            })
            _fail_mkt = (marketplace if marketplace != "ALL" else "MULTI_MARKETPLACE")
            try:
                from app.mri_autonomous.recovery_runner import AcquisitionRecoveryRunner
                AcquisitionRecoveryRunner().persist_to_sqlite(
                    {"observations": [], "terminal_state": _EF}, run_id,
                    run_meta={"marketplace": _fail_mkt,
                              "execution_mode": f"DISCOVERY::{marketplace}",
                              "source_method": "DASHBOARD_DISCOVERY_SCRAPER",
                              "terminal_state": _EF,
                              "started_at": self.state.get("started_at")})
            except Exception as _pe:
                print(f"Error persisting failed discovery run to SQLite: {_pe}")
            try:
                self.history.append({
                    "run_id": run_id,
                    "timestamp": datetime.now().isoformat(),
                    "marketplace": _fail_mkt,
                    "total": 0,
                    "confirmed": 0,
                    "results": [],
                    "mode": "DISCOVERY",
                    "terminal_state": _EF,
                    "outcome": _EF,
                    "engine": f"DISCOVERY::{marketplace}",
                    "error": self.state["error"],
                    "errors": self.state.get("errors") or [],
                })
                self._save_history()
            except Exception:
                pass

        finally:
            self.is_running = False
            self.stop_requested = False
        
    async def run_audit(self, marketplace="ALL", limit=5, run_id=None):
        if self.is_running:
            return
            
        self.is_running = True
        self.results = []
        
        run_id = run_id or f"mri_dash_{uuid.uuid4().hex[:8]}"
        self.state.update({
            "stage": "preparando",
            "total_known": False,
            "products_processed": 0,
            "confirmed": 0,
            "errors": [],
            "last_activity": datetime.now().isoformat(),
        })
        materializer = GenericCommercialMaterializer(run_id)
        self.state.update({
            "run_id": run_id,
            "started_at": datetime.now().isoformat(),
            "marketplace": marketplace,
            "mode": "AUDIT",
        })
        store = _safe_experience_store()
        
        products_to_audit = load_universe(marketplace, limit)

            
        self.state["total"] = len(products_to_audit)
        self.state["progress"] = 0
        
        try:
            mkt_groups = {}
            for prod in products_to_audit:
                mkt_groups.setdefault(prod["marketplace"], []).append(prod)
                
            for mkt, prods in mkt_groups.items():
                if not self.is_running: break
                
                self.state.setdefault("marketplace_states", {})[mkt] = "EN_CURSO"
                self.state["stage"] = "adquiriendo"
                self.state["last_activity"] = datetime.now().isoformat()
                scraper = get_scraper(mkt)
                if scraper:
                    await scraper.start()
                    
                try:
                    for prod in prods:
                        if not self.is_running:
                            self.state["status_message"] = "ABORTED"
                            break
                        
                        self.state["progress"] += 1
                        res = await audit_product(prod, materializer, store, self.state, scraper_instance=scraper)
                        self.results.append(res)
                finally:
                    if scraper:
                        await scraper.stop()
                        
            self.state["progress"] = len(products_to_audit)
            if self.stop_requested or not self.is_running:
                self.state["status_message"] = "STOPPED_BY_USER"
            else:
                self.state["status_message"] = "COMPLETED"
            
            # Save to history
            self.history.append({
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "marketplace": marketplace,
                "total": len(products_to_audit),
                "confirmed": sum(1 for r in self.results if r["status"] == "CONFIRMED"),
                "results": list(self.results),
                "terminal_state": self.state["status_message"]
            })
            self._save_history()
            
        finally:
            self.is_running = False
            self.stop_requested = False
            
    def stop(self):
        self.stop_requested = True
        self.is_running = False
        self.state["status_message"] = "STOPPED_BY_USER"

orchestrator = MRIOrchestrator()
