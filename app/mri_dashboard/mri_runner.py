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
from app.mri_autonomous.category_evaluator import evaluate_commercial_category
from app.auditor.nicopoly_matcher import is_nicopoly
from mri_commercial_materialization_golden_slice.v001.materializer_engine import GenericCommercialMaterializer

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
            StorageConfig.assert_write_allowed(self.history_file)
        except ImportError:
            pass
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2)

    async def run_discovery(self, marketplace="ALL", max_pages=1):
        if self.is_running:
            return
            
        self.is_running = True
        self.results = []
        
        run_id = f"mri_disc_{uuid.uuid4().hex[:8]}"
        materializer = GenericCommercialMaterializer(run_id)
        store = ExperienceStore()
        
        from app.mri_dashboard.category_manager import category_manager
        
        # Seed categories if empty - REMOVED for fully autonomous execution
        mkts_to_run = [marketplace] if marketplace != "ALL" else ["Mercado Libre", "Paris", "Ripley", "Falabella"]
        
        self.state["total"] = len(mkts_to_run)
        self.state["progress"] = 0
        
        try:
            for mkt in mkts_to_run:
                if not self.is_running: break
                
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
                
                scraper = get_scraper(mkt)
                if scraper:
                    await scraper.start()
                    
                try:
                    for cat_id, cat_data in list(cats.items()):
                        if not self.is_running: break
                        url = cat_data["url"]
                        
                        self.state["status_message"] = f"Descubriendo {mkt} - {cat_data['name']}..."
                        
                        res = await scraper.scrape_autonomous_category(url, max_pages=max_pages)
                        discovered_products = res.get("products", [])
                        stop_reason = res.get("stop_reason")
                        if not discovered_products and stop_reason in ("EXTRACTOR_FAILURE", "SOURCE_BLOCKED", "RATE_LIMIT"):
                            self.state["status_message"] = stop_reason
                            category_manager.register_category(mkt, cat_id, cat_data["name"], url, status=stop_reason)
                            continue

                        coverage = "COMPLETE" if stop_reason == "EXHAUSTION" else (stop_reason or "PARTIAL")
                        
                        # Mark category as VERIFIED since we ran it
                        category_manager.register_category(mkt, cat_id, cat_data["name"], url, status="VERIFIED")
                        
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
                            
                            pub_id = f"pub_{mkt.lower().replace(' ', '')}_{hashlib.md5(norm['raw_sku'].encode()).hexdigest()[:12]}"
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
                                "timestamp": datetime.now().isoformat()
                            })
                            self.state["progress"] += 1
                        
                finally:
                    if scraper:
                        await scraper.stop()
                        
            if self.stop_requested or not self.is_running:
                self.state["status_message"] = "STOPPED_BY_USER"
            else:
                self.state["status_message"] = "COMPLETED"
            
            # Save to SQLite DB for persistent API querying
            try:
                import json
                from app.mri_autonomous.recovery_runner import AcquisitionRecoveryRunner
                rec_runner = AcquisitionRecoveryRunner()
                obs_to_persist = []
                for res in self.results:
                    obs_to_persist.append({
                        "publication_id": res.get("observed_sku") or res.get("producto_id"),
                        "marketplace": res.get("marketplace"),
                        "observed_url": res.get("url"),
                        "position_observed": res.get("position_observed") or 1,
                        "title": res.get("producto_nombre"),
                        "observation_timestamp": res.get("timestamp"),
                        "status": "OBSERVED",
                        "acquisition_status": "OBSERVED",
                        "identity_status": res.get("identity_status"),
                        "category_observed": res.get("real_category"),
                        "category_source": res.get("category_source"),
                        "category_expected": res.get("expected_category"),
                        "category_decision": res.get("decision"),
                        "commercial_attributes": json.dumps(res.get("commercial_attributes") or {})
                    })
                if obs_to_persist:
                    rec_runner.persist_to_sqlite({"observations": obs_to_persist}, run_id)
            except Exception as e:
                print(f"Error persisting discovery run to SQLite: {e}")

            # Save to history
            self.history.append({
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "marketplace": marketplace,
                "total": sum(1 for r in self.results),
                "confirmed": sum(1 for r in self.results if r["status"] in ("CONFIRMED", "CORRECT")),
                "results": list(self.results),
                "mode": "DISCOVERY",
                "terminal_state": self.state["status_message"]
            })
            self._save_history()
            
        finally:
            self.is_running = False
            self.stop_requested = False
        
    async def run_audit(self, marketplace="ALL", limit=5):
        if self.is_running:
            return
            
        self.is_running = True
        self.results = []
        
        run_id = f"mri_dash_{uuid.uuid4().hex[:8]}"
        materializer = GenericCommercialMaterializer(run_id)
        store = ExperienceStore()
        
        products_to_audit = load_universe(marketplace, limit)

            
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
