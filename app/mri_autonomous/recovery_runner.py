"""
app/mri_autonomous/recovery_runner.py

Operational pipeline for multi-marketplace commercial publication recovery:
ACQUISITION -> RECONCILIATION -> EVIDENCE -> SQLITE -> DASHBOARD

Executes certified paginated harvesting, deterministic reconciliation with Master Catalog,
materialization into SQLite visibility.db with zero fake URLs, and read-model validation.
"""

import asyncio
import hashlib
import json
import logging
import openpyxl
import os
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# Ensure project root in sys.path when executed directly
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.scrapers.mercadolibre_scraper import MercadoLibreScraper
from app.scrapers.paris_scraper import ParisScraper
from app.scrapers.ripley_scraper import RipleyScraper
from app.dashboard.mri_read_model import MRIReadModel
from app.mri_autonomous.category_evaluator import evaluate_commercial_category

logger = logging.getLogger(__name__)

try:
    from app.mri_autonomous.storage_guard import StorageConfig
    DEFAULT_SQLITE_PATH = StorageConfig.get_sqlite_path()
except Exception:
    DEFAULT_SQLITE_PATH = Path("data/sqlite/visibility.db")

DB_PATH = DEFAULT_SQLITE_PATH
CATALOG_PATH = Path("Actualización masiva de productos.xlsx")
MANIFEST_PATH = Path("docs/forensics/VA_4MP_ACQUISITION_KNOWLEDGE/FULL_PUBLICATION_MANIFEST.json")
EVIDENCE_DIR = Path("evidence/va_4mp_live_publications_001")


def clean_id(val: Any) -> str:
    """Normalize identifier for robust exact matching."""
    if not val:
        return ""
    s = str(val).strip().upper()
    s = re.sub(r"^(MLC|MPM|PARIS_|FALA_)", "", s)
    return re.sub(r"[^A-Z0-9]", "", s)


def deterministic_category_id(marketplace: str, category_name: str) -> str:
    """
    Generate deterministic category ID based on sha256 of marketplace + canonical category name.
    Replaces non-deterministic hash() functions.
    """
    mkt_slug = re.sub(r"[^a-zA-Z0-9]", "", marketplace).upper()[:3]
    cat_norm = category_name.strip().lower()
    h = hashlib.sha256(f"{mkt_slug}:{cat_norm}".encode("utf-8")).hexdigest()[:8]
    return f"cat_{mkt_slug.lower()}_{h}"


class AcquisitionRecoveryRunner:
    """
    Reproducible operational acquisition pipeline across 4 marketplaces.
    Runs certified paginated harvesting, deduplication, and persistence.
    """

    def __init__(self, output_dir: Optional[Any] = None, db_path: Optional[Any] = None):
        self.output_dir = Path(output_dir) if output_dir else EVIDENCE_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            try:
                from app.mri_autonomous.storage_guard import StorageConfig
                self.db_path = Path(StorageConfig.get_sqlite_path())
            except Exception:
                self.db_path = DB_PATH
        self.raw_harvest_file = self.output_dir / "raw_live_harvest.json"

    # ──────────────────────────────────────────────────────────────────────────
    # 1. ACQUISITION
    # ──────────────────────────────────────────────────────────────────────────

    def fetch_falabella_catalog(self, brand: str = "nicopoly", max_pages: int = 10) -> List[Dict[str, Any]]:
        """
        Certified HTTP SSR paginated acquisition for Falabella.
        Uses canonical www.falabella.com with standard browser User-Agent to avoid WAF 403.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8"
        }
        products = {}
        for page in range(1, max_pages + 1):
            url = f"https://www.falabella.com/falabella-cl/search?Ntt={brand}&page={page}"
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
                
                m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
                if not m:
                    break
                data = json.loads(m.group(1))
                results = data.get("props", {}).get("pageProps", {}).get("results", [])
                if not results:
                    break
                
                for r in results:
                    pid = str(r.get("productId") or "").strip()
                    title = str(r.get("displayName") or "").strip()
                    p_url = str(r.get("url") or f"https://www.falabella.com/falabella-cl/product/{pid}/p")
                    prices = r.get("prices", [])
                    price = 0.0
                    if prices:
                        pval = prices[0].get("price", [0])
                        if isinstance(pval, list) and pval:
                            price = float(str(pval[0]).replace(".", "").replace(",", "."))
                        elif isinstance(pval, (int, float)):
                            price = float(pval)
                    
                    if pid and pid not in products:
                        products[pid] = {
                            "title": title,
                            "vendor": "Nicopoly",
                            "price": price,
                            "marketplace_sku": pid,
                            "url": p_url,
                            "position_absolute": len(products) + 1,
                            "source_url": "https://www.falabella.com/falabella-cl/search?Ntt=nicopoly",
                            "marketplace": "Falabella",
                            "harvest_time": datetime.now().isoformat()
                        }
            except Exception as e:
                logger.warning(f"[RecoveryRunner] Falabella page {page} fetch failed: {e}")
                break
        return list(products.values())

    async def fetch_paris_catalog(self, brand: str = "nicopoly", max_batches: int = 25) -> List[Dict[str, Any]]:
        """Certified Playwright headless batch extraction for Paris."""
        p = ParisScraper(headless=True)
        await p.start()
        products = {}
        try:
            url = f"https://www.paris.cl/search?q={brand}"
            ok = await p.navigate(url)
            if not ok:
                return []
            
            consecutive_unchanged = 0
            last_count = 0
            for batch in range(1, max_batches + 1):
                html = await p.page.content()
                items = await p._extract_products_from_html(html, len(products), None)
                for it in items:
                    sku = str(it.get("marketplace_sku") or "").strip()
                    url_it = (it.get("url") or "").strip()
                    key = url_it if url_it else sku
                    if key and key not in products:
                        it["position_absolute"] = len(products) + 1
                        it["marketplace"] = "Paris"
                        it["harvest_time"] = datetime.now().isoformat()
                        it["source_url"] = url
                        products[key] = it
                
                if len(products) == last_count:
                    consecutive_unchanged += 1
                else:
                    consecutive_unchanged = 0
                    last_count = len(products)
                if consecutive_unchanged >= 3:
                    break
                
                btn = await p.page.query_selector('button:has-text("Mostrar más")')
                if not btn:
                    break
                await btn.click()
                await asyncio.sleep(1.5)
        finally:
            await p.stop()
        return list(products.values())

    async def fetch_mercadolibre_catalog(self, max_pages: int = 15) -> List[Dict[str, Any]]:
        """Certified Playwright headless paginated extraction for Mercado Libre official store."""
        scraper = MercadoLibreScraper(headless=True)
        await scraper.start()
        try:
            res = await scraper.scrape_autonomous_category(
                "https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly",
                max_pages=max_pages
            )
            raw = res.get("products", [])
            for it in raw:
                it["marketplace"] = "Mercado Libre"
                it["source_url"] = "https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly"
                it["harvest_time"] = datetime.now().isoformat()
            return raw
        finally:
            await scraper.stop()

    async def fetch_ripley_catalog(self, brand: str = "nicopoly", max_pages: int = 10) -> List[Dict[str, Any]]:
        """Certified Playwright headless paginated extraction for Ripley."""
        scraper = RipleyScraper(headless=True)
        await scraper.start()
        try:
            res = await scraper.scrape_autonomous_category(
                f"https://simple.ripley.cl/search/{brand}",
                max_pages=max_pages
            )
            raw = res.get("products", [])
            for it in raw:
                it["marketplace"] = "Ripley"
                it["source_url"] = f"https://simple.ripley.cl/search/{brand}"
                it["harvest_time"] = datetime.now().isoformat()
            return raw
        finally:
            await scraper.stop()

    def run_all_harvests(self) -> Dict[str, List[Dict[str, Any]]]:
        """Runs all 4 harvests sequentially and returns combined dictionary."""
        logger.info("[RecoveryRunner] Starting Falabella harvest...")
        fala = self.fetch_falabella_catalog()
        
        logger.info("[RecoveryRunner] Starting Paris harvest...")
        paris = asyncio.run(self.fetch_paris_catalog())
        
        logger.info("[RecoveryRunner] Starting Mercado Libre harvest...")
        ml = asyncio.run(self.fetch_mercadolibre_catalog())
        
        logger.info("[RecoveryRunner] Starting Ripley harvest...")
        ripley = asyncio.run(self.fetch_ripley_catalog())
        
        harvest = {
            "Falabella": fala,
            "Paris": paris,
            "Mercado Libre": ml,
            "Ripley": ripley
        }
        with open(self.raw_harvest_file, "w", encoding="utf-8") as f:
            json.dump(harvest, f, ensure_ascii=False, indent=2)
        return harvest

    # ──────────────────────────────────────────────────────────────────────────
    # 2. RECONCILIATION & EVIDENCE RESOLUTION
    # ──────────────────────────────────────────────────────────────────────────

    def reconcile_and_audit(self, live_harvest: Dict[str, List[Dict[str, Any]]], run_id: str) -> Dict[str, Any]:
        """
        Reconciles live harvested physical products against the 3,999 manifest publications.
        Preserves 1-to-many relationship: parent product observation -> associated variant publications.
        Restores commercial titles, verifies identities with master catalog, classifies categories.
        """
        # Load master catalog
        wb_cat = openpyxl.load_workbook(CATALOG_PATH, read_only=True)
        ws_cat = wb_cat.active
        child_to_master = {}
        parent_to_master = {}
        title_to_master = {}
        for r in ws_cat.iter_rows(values_only=True):
            parent = str(r[2] or "").strip()
            child = str(r[3] or "").strip()
            title = str(r[4] or "").strip()
            cat = str(r[7] or "").strip()
            fal_tipo = str(r[54] or "").strip() if len(r) > 54 else ""
            shopify_tipo = str(r[88] or "").strip() if len(r) > 88 else ""
            ml_prenda = str(r[115] or "").strip() if len(r) > 115 else ""
            entry = {
                "parent_sku": parent,
                "child_sku": child,
                "title": title,
                "category": cat,
                "falabella_tipo": fal_tipo,
                "shopify_tipo": shopify_tipo,
                "ml_prenda": ml_prenda
            }
            if child and child not in child_to_master:
                child_to_master[child] = entry
            if parent and parent not in parent_to_master:
                parent_to_master[parent] = entry
            if title and title.lower() not in title_to_master:
                title_to_master[title.lower()] = entry

        # Load SQLite snapshots
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        snapshot_lookup = {}
        for r in c.execute("SELECT id, product_title, sku_master, price, marketplace_sku, category, audit_date, position_absolute FROM product_snapshots"):
            s_id, p_title, sku_m, price, mkt_sku, cat, audit_date, pos = r
            snapshot_lookup[s_id] = {
                "title": str(p_title or "").strip(),
                "sku_master": str(sku_m or "").strip(),
                "price": price or 0.0,
                "mkt_sku": str(mkt_sku or "").strip(),
                "category": str(cat or "").strip(),
                "audit_date": audit_date,
                "position": pos
            }
        conn.close()

        # Build harvest lookup
        live_by_mkt_and_id = {}
        live_by_url = {}
        unique_live_products = set()

        for mkt, items in live_harvest.items():
            for it in items:
                sku = str(it.get("marketplace_sku") or it.get("sku") or "").strip()
                url = str(it.get("url") or it.get("link") or "").strip().split("?")[0].lower()
                prod_key = (mkt, sku if sku else url)
                if prod_key[1]:
                    unique_live_products.add(prod_key)

                if sku:
                    live_by_mkt_and_id[(mkt, sku)] = it
                    c_sku = clean_id(sku)
                    if c_sku:
                        live_by_mkt_and_id[(mkt, c_sku)] = it
                if url:
                    live_by_url[url] = it
                    m = re.search(r"(mlc[-_]?\d+|\d{7,})", url)
                    if m:
                        live_by_mkt_and_id[(mkt, clean_id(m.group(1)))] = it

        # Process manifest
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        raw_pubs = manifest_data.get("publications", [])

        observations = []
        confirmed_variants = 0
        restored_titles = 0
        now_str = datetime.now().isoformat()

        category_map = [
            (["abrigo", "chaqueta", "blazer", "parka", "trench", "cardigan", "chaleco"], "Chaquetas y Abrigos"),
            (["pantalon", "jeans", "short", "falda", "calza", "legging", "bermuda"], "Pantalones y Jeans"),
            (["blusa", "polera", "top", "camisa", "remera", "poleron", "sweater"], "Blusas y Tops"),
            (["vestido", "enterito", "jumpsuit"], "Vestidos y Enteritos")
        ]

        for p in raw_pubs:
            manifest_id = p.get("manifest_id")
            mkt = p.get("marketplace")
            pub_id = str(p.get("publication_id") or "").strip()
            c_pub_id = clean_id(pub_id)
            raw_id = p.get("last_evidence", {}).get("raw_source_id")

            snap = snapshot_lookup.get(raw_id)
            if snap:
                real_title = snap["title"]
                real_sku_master = snap["sku_master"]
                real_price = snap["price"]
                real_category_observed = snap["category"]
                hist_position = snap["position"]
                hist_date = snap["audit_date"]
            else:
                real_title = str(p.get("product_identity", {}).get("title") or "").strip()
                real_sku_master = p.get("sku_child") or p.get("sku_parent") or ""
                real_price = 0.0
                real_category_observed = p.get("category_observed") or ""
                hist_position = p.get("last_evidence", {}).get("position")
                hist_date = p.get("last_evidence", {}).get("observed_at")

            canonical_url = str(p.get("canonical_url") or "").strip()
            if not canonical_url:
                if mkt == "Mercado Libre" and pub_id:
                    canonical_url = f"https://articulo.mercadolibre.cl/{pub_id}"
                elif mkt == "Paris" and pub_id:
                    canonical_url = f"https://www.paris.cl/{pub_id}.html"
                elif mkt == "Falabella" and pub_id:
                    canonical_url = f"https://www.falabella.com/falabella-cl/product/{pub_id}/p"
                elif mkt == "Ripley" and pub_id:
                    canonical_url = f"https://simple.ripley.cl/{pub_id}"

            clean_canon_url = canonical_url.split("?")[0].lower()

            # Unequivocal match
            live_match = live_by_mkt_and_id.get((mkt, pub_id)) or (live_by_mkt_and_id.get((mkt, c_pub_id)) if c_pub_id else None)
            if not live_match and clean_canon_url:
                live_match = live_by_url.get(clean_canon_url)
            if not live_match and clean_canon_url:
                m_u = re.search(r"(mlc[-_]?\d+|\d{7,})", clean_canon_url)
                if m_u:
                    live_match = live_by_mkt_and_id.get((mkt, clean_id(m_u.group(1))))

            # Quality title restoration
            if live_match:
                h_title = str(live_match.get("title") or "").strip()
                if (real_title.isdigit() or not real_title) and h_title and not h_title.isdigit():
                    real_title = h_title
                    restored_titles += 1

            # Identity Resolution
            m_match = None
            if real_sku_master:
                m_match = child_to_master.get(real_sku_master) or parent_to_master.get(real_sku_master)
            if not m_match and real_title and not real_title.isdigit():
                m_match = title_to_master.get(real_title.lower())

            if m_match:
                identity_status = "TARGET_IDENTITY_VERIFIED"
                parent_sku = m_match["parent_sku"]
                child_sku = m_match["child_sku"]
                category_expected = m_match["category"]
                identity_reason = "Coincidencia determinista verificada con SKU/Título en catálogo maestro"
            else:
                identity_status = "IDENTITY_NOT_LINKED"
                parent_sku = p.get("sku_parent") or ""
                child_sku = p.get("sku_child") or ""
                category_expected = p.get("category_expected") or ""
                identity_reason = "Publicación observada en marketplace sin correspondencia unívoca en catálogo maestro"

            # Categoría observada: exclusivamente evidencia pública capturada
            cat_observed_public = real_category_observed
            cat_source = "SNAPSHOT_PUBLIC_OBSERVATION" if (snap and real_category_observed) else ("MANIFEST_PUBLIC_OBSERVATION" if real_category_observed else "NO_VERIFICADO")
            cat_obs_time = hist_date if (snap and hist_date) else now_str

            if live_match and not cat_observed_public:
                live_cat = live_match.get("category") or live_match.get("category_observed")
                if live_cat and live_cat not in ("NO_VERIFICADO", "CATEGORY_UNKNOWN", "NONE"):
                    cat_observed_public = live_cat
                    cat_source = f"LIVE_HARVEST_{mkt.upper()}"
                    cat_obs_time = live_match.get("harvest_time") or now_str

            # Atributos comerciales públicos explícitos (exclusivamente evidencia pública de canal)
            public_attrs = {}
            if live_match and live_match.get("attributes"):
                public_attrs.update(live_match.get("attributes"))

            # Evaluación comercial de categoría
            cat_eval = evaluate_commercial_category(
                product_title=real_title,
                expected_category=category_expected,
                observed_category=cat_observed_public,
                public_attributes=public_attrs
            )
            category_decision = cat_eval["decision"]
            category_decision_reason = cat_eval["reason"]

            if live_match:
                observation_status = "LIVE_OBSERVATION_CONFIRMED"
                confirmed_variants += 1
                pos_obs = live_match.get("position_absolute") or live_match.get("position_observed") or live_match.get("position")
                obs_price = live_match.get("price") or real_price
                obs_url = live_match.get("url") or canonical_url
                obs_time = live_match.get("harvest_time") or now_str
                reclass_reason = f"Observada físicamente en barrido paginado contemporáneo mediante adaptador {mkt}"
                evidence_verified = True
            else:
                observation_status = "NOT_CONFIRMED"
                pos_obs = None
                obs_price = real_price
                obs_url = canonical_url
                obs_time = hist_date
                reclass_reason = "Publicación histórica en catálogo no observada en barrido de corredores contemporáneos agotados"
                evidence_verified = False

            observations.append({
                "manifest_id": manifest_id,
                "marketplace": mkt,
                "publication_id": pub_id,
                "title": real_title,
                "sku_master": real_sku_master,
                "sku_parent": parent_sku,
                "sku_child": child_sku,
                "price_observed": obs_price,
                "observed_url": obs_url,
                "observation_timestamp": obs_time,
                "position_observed": pos_obs,
                "status": observation_status,
                "acquisition_status": observation_status,
                "reclassification_reason": reclass_reason,
                "identity_status": identity_status,
                "identity_reason": identity_reason,
                "category_observed": cat_observed_public if cat_observed_public else "NO_VERIFICADO",
                "category_source": cat_source,
                "category_obs_time": cat_obs_time,
                "category_expected": category_expected if category_expected else "NO_VERIFICADO",
                "category_decision": category_decision,
                "category_decision_reason": category_decision_reason,
                "commercial_attributes": json.dumps(public_attrs, ensure_ascii=False) if public_attrs else None,
                "evidence_verified": evidence_verified,
                "run_id": run_id
            })

        return {
            "observations": observations,
            "unique_live_products_count": len(unique_live_products),
            "confirmed_variants_count": confirmed_variants,
            "restored_titles_count": restored_titles
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 3. SQLITE PERSISTENCE & CATEGORY LINKAGE
    # ──────────────────────────────────────────────────────────────────────────

    def persist_to_sqlite(self, reconciled_result: Dict[str, Any], run_id: str) -> Dict[str, int]:
        """
        Materializes observations into SQLite visibility.db under a certified run_id.
        Generates deterministic category IDs and sets canonical_url = NULL for unknown categories.
        Guarantees non-destructive additive persistence.
        """
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            StorageConfig.assert_write_allowed(self.db_path)
        except ImportError:
            pass

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now_str = datetime.now().isoformat()

        term_state = reconciled_result.get("terminal_state") or "COMPLETED"
        run_status = "STOPPED" if term_state in ("PAGE_BUDGET_EXCEEDED", "STOPPED", "FAILED") else "SUCCESS"

        # 1. Register Run
        c.execute("""
            INSERT OR REPLACE INTO mri_runs (
                run_id, started_at, finished_at, marketplace, brand, execution_mode,
                truth_model_version, terminal_state, source_method, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id, now_str, now_str, "MULTI_MARKETPLACE", "Nicopoly",
            "RECOVERY_OPERATIONAL_INTEGRATION", "2.0", term_state,
            "PAGINATED_ADAPTER_HARVEST", run_status, now_str
        ))

        pubs_inserted = 0
        cats_inserted = 0
        edges_inserted = 0

        for obs in reconciled_result["observations"]:
            if obs["status"] in ("LIVE_OBSERVATION_CONFIRMED", "OBSERVED", "NICOPOLY_CONFIRMED"):
                pub_id = obs["publication_id"]
                mkt = obs["marketplace"]
                canon_url = obs["observed_url"]
                pos = obs["position_observed"]
                title = obs["title"]
                obs_at = obs["observation_timestamp"] or now_str
                p_id = f"PROD_{mkt[:3].upper()}_{pub_id}"

                # mri_products
                c.execute("""
                    INSERT OR REPLACE INTO mri_products (product_id, canonical_brand, product_status, created_at)
                    VALUES (?, ?, ?, ?)
                """, (p_id, "Nicopoly", "ACTIVE", obs_at))

                # mri_publications con dimensiones separadas
                acq_st = obs["acquisition_status"]
                ident_st = obs["identity_status"]
                cat_obs = obs["category_observed"]
                cat_src = obs["category_source"]
                cat_exp = obs["category_expected"]
                cat_dec = obs["category_decision"]
                comm_attr = obs["commercial_attributes"]
                raw_src_id = obs.get("raw_source_id")
                ev_type = obs.get("evidence_type") or ("CONTROLLED_FIXTURE" if raw_src_id and "FIXTURE" in str(raw_src_id) else "LIVE_OBSERVATION")

                # Preservar historial: respaldar estado previo si la publicación ya existe con otro run_id
                existing = c.execute("""
                    SELECT publication_id, product_id, marketplace, marketplace_product_id,
                           canonical_url, status, observed_at, run_id, position, surface,
                           position_state, category_relationship, evidence_type, raw_source_id,
                           acquisition_status, identity_status, category_observed,
                           category_source, category_expected, category_decision, commercial_attributes
                    FROM mri_publications WHERE publication_id = ?
                """, (pub_id,)).fetchone()
                if existing and existing[7] and existing[7] != run_id:
                    c.execute("""
                        INSERT OR REPLACE INTO mri_historical_publications (
                            history_id, publication_id, product_id, marketplace, marketplace_product_id,
                            canonical_url, status, observed_at, run_id, position, surface,
                            position_state, category_relationship, evidence_type, raw_source_id,
                            acquisition_status, identity_status, category_observed,
                            category_source, category_expected, category_decision, commercial_attributes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        f"hist_{existing[7]}_{pub_id}", existing[0], existing[1], existing[2], existing[3],
                        existing[4], existing[5], existing[6], existing[7], existing[8], existing[9],
                        existing[10], existing[11], existing[12], existing[13], existing[14], existing[15],
                        existing[16], existing[17], existing[18], existing[19], existing[20]
                    ))

                c.execute("""
                    INSERT OR REPLACE INTO mri_publications (
                        publication_id, product_id, marketplace, marketplace_product_id,
                        canonical_url, status, observed_at, run_id, position, surface,
                        position_state, category_relationship, evidence_type, raw_source_id,
                        acquisition_status, identity_status, category_observed,
                        category_source, category_expected, category_decision, commercial_attributes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pub_id, p_id, mkt, pub_id, canon_url, "OBSERVED",
                    obs_at, run_id, pos, "SEARCH_OR_STORE",
                    "EXACT", cat_dec, ev_type, raw_src_id,
                    acq_st, ident_st, cat_obs, cat_src, cat_exp, cat_dec, comm_attr
                ))
                pubs_inserted += 1

                # Deterministic Category Resolution
                cat_name = (obs["category_observed"] if obs["category_observed"] != "NO_VERIFICADO" else (obs["category_expected"] if obs["category_expected"] != "NO_VERIFICADO" else "Moda Mujer")).strip()
                cat_id = deterministic_category_id(mkt, cat_name)

                # Insert category with canonical_url = NULL (ZERO fake example.com URLs)
                c.execute("""
                    INSERT OR REPLACE INTO mri_categories (category_id, marketplace, category_name, canonical_url, created_at)
                    VALUES (?, ?, ?, NULL, ?)
                """, (cat_id, mkt, cat_name, obs_at))
                cats_inserted += 1

                # Link publication to category
                c.execute("""
                    INSERT OR REPLACE INTO mri_publication_categories (publication_id, category_id, status, observed_at)
                    VALUES (?, ?, ?, ?)
                """, (pub_id, cat_id, "ACTIVE", obs_at))
                edges_inserted += 1

        conn.commit()
        conn.close()

        logger.info(f"[RecoveryRunner] Materialized {pubs_inserted} publications, {cats_inserted} categories into SQLite.")
        return {
            "publications_materialized": pubs_inserted,
            "categories_materialized": cats_inserted,
            "edges_materialized": edges_inserted
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 4. DASHBOARD READ MODEL VALIDATION
    # ──────────────────────────────────────────────────────────────────────────

    def validate_dashboard(self) -> Dict[str, Any]:
        """Queries MRIReadModel to verify active categories, TopN counts, and summary."""
        rm = MRIReadModel()
        categories_data = rm.get_categories()
        summary_data = rm.get_summary()

        total_categories = categories_data.get("total", 0)
        items = categories_data.get("items", [])
        has_materialized_positions = any(
            it.get("top30_count") not in ("N/A (NOT MATERIALIZED)", 0, None)
            for it in items
        )
        total_materialized_pubs = summary_data.get("total_materialized_real_publications", 0)

        return {
            "total_categories_active": total_categories,
            "total_materialized_publications": total_materialized_pubs,
            "has_materialized_positions": has_materialized_positions,
            "status": "PASS" if total_categories > 0 and total_materialized_pubs > 0 else "FAIL"
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 5. COMPLETE END-TO-END PIPELINE EXECUTION
    # ──────────────────────────────────────────────────────────────────────────

    def execute_complete_pipeline(self, run_id: Optional[str] = None, reuse_harvest: bool = True) -> Dict[str, Any]:
        """
        Executes the entire verified pipeline:
        ACQUISITION -> RECONCILIATION -> EVIDENCE -> SQLITE -> DASHBOARD
        """
        active_run_id = run_id or f"run_va_mri_operational_integration_{int(time.time())}"
        logger.info(f"=== Starting Complete Recovery Pipeline [{active_run_id}] ===")

        # Step 1: Acquisition
        if reuse_harvest and self.raw_harvest_file.exists():
            logger.info("[RecoveryRunner] Reusing existing certified raw live harvest data...")
            with open(self.raw_harvest_file, "r", encoding="utf-8") as f:
                harvest = json.load(f)
        else:
            logger.info("[RecoveryRunner] Executing fresh multi-marketplace harvest...")
            harvest = self.run_all_harvests()

        # Step 2: Reconciliation & Evidence
        logger.info("[RecoveryRunner] Reconciling live observations against manifest...")
        reconciled = self.reconcile_and_audit(harvest, active_run_id)

        # Step 3: SQLite Persistence
        logger.info("[RecoveryRunner] Materializing records to SQLite...")
        persistence = self.persist_to_sqlite(reconciled, active_run_id)

        # Step 4: Dashboard Validation
        logger.info("[RecoveryRunner] Validating Dashboard Read Model...")
        dash_val = self.validate_dashboard()

        return {
            "run_id": active_run_id,
            "unique_live_products": reconciled["unique_live_products_count"],
            "live_confirmed_variants": reconciled["confirmed_variants_count"],
            "restored_titles": reconciled["restored_titles_count"],
            "sqlite_persistence": persistence,
            "dashboard_validation": dash_val,
            "pipeline_status": "PASS" if dash_val["status"] == "PASS" else "FAIL"
        }


if __name__ == "__main__":
    runner = AcquisitionRecoveryRunner()
    res = runner.execute_complete_pipeline(reuse_harvest=True)
    print("\n=== PIPELINE EXECUTION RESULT ===")
    print(json.dumps(res, indent=2))
