import asyncio
import time
import uuid
import hashlib
import sys
from datetime import datetime

from app.mri_autonomous.experience_store import ExperienceStore
from app.scrapers.mercadolibre_scraper import MercadoLibreScraper
from app.scrapers.paris_scraper import ParisScraper
from app.scrapers.ripley_scraper import RipleyScraper
from app.scrapers.falabella_scraper import FalabellaScraper
from app.auditor.nicopoly_matcher import is_nicopoly
from mri_commercial_materialization_golden_slice.v001.materializer_engine import GenericCommercialMaterializer

import csv
import os

def load_real_products(limit=5):
    filepath = os.path.join("outputs", "MRI_PRODUCTION_AUDIT_001.csv")
    products = []
    seen_marketplaces = set()
    
    if os.path.exists(filepath):
        # First pass: try to get one from each marketplace
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mkt = row["marketplace"]
                if mkt not in seen_marketplaces:
                    products.append({
                        "sku": row["sku_parent"],
                        "title": row["product_name"],
                        "marketplace": mkt,
                        "vendor": "Nicopoly"
                    })
                    seen_marketplaces.add(mkt)
                    if len(products) >= limit:
                        break
        
        # Second pass: fill the rest if we have less than limit
        if len(products) < limit:
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if len(products) >= limit:
                        break
                    # Avoid duplicates
                    if not any(p["sku"] == row["sku_parent"] for p in products):
                        products.append({
                            "sku": row["sku_parent"],
                            "title": row["product_name"],
                            "marketplace": row["marketplace"],
                            "vendor": "Nicopoly"
                        })
    if not products:
        products = [
            {"sku": "MLC6", "title": "Abrigo Efecto Piel Nicopoly", "marketplace": "Mercado Libre", "vendor": "Nicopoly"},
        ]
    return products

EXPECTED_PRODUCTS = load_real_products(5)

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
                results = await asyncio.wait_for(scraper.scrape_top_240(search_url), timeout=15)
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
    
    pub_id = f"pub_{mkt.lower().replace(' ', '')}_{hashlib.md5(norm['raw_sku'].encode()).hexdigest()[:12]}"
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
        self.state = {
            "progress": 0,
            "total": 0,
            "current_product": None,
            "status_message": "IDLE"
        }
        self.results = []
        self.history = []
        
    async def run_audit(self, marketplace=None):
        if self.is_running:
            return
            
        self.is_running = True
        self.results = []
        
        run_id = f"mri_dash_{uuid.uuid4().hex[:8]}"
        materializer = GenericCommercialMaterializer(run_id)
        store = ExperienceStore()
        
        products_to_audit = EXPECTED_PRODUCTS
        if marketplace and marketplace != "ALL":
            products_to_audit = [p for p in EXPECTED_PRODUCTS if p["marketplace"] == marketplace]
            
        self.state["total"] = len(products_to_audit)
        self.state["progress"] = 0
        
        try:
            mkt_groups = {}
            for prod in products_to_audit:
                mkt_groups.setdefault(prod["marketplace"], []).append(prod)
                
            for mkt, prods in mkt_groups.items():
                if not self.is_running: break
                
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
            self.state["status_message"] = "COMPLETED"
            
            # Save to history
            self.history.append({
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "marketplace": marketplace,
                "total": len(products_to_audit),
                "confirmed": sum(1 for r in self.results if r["status"] == "CONFIRMED"),
                "results": list(self.results)
            })
            
        finally:
            self.is_running = False
            
    def stop(self):
        self.is_running = False
        self.state["status_message"] = "STOPPING..."

orchestrator = MRIOrchestrator()
