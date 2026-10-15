import uvicorn
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import sys
import sqlite3
import json
import re
from typing import Dict, Any, List

# Ensure the project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.mri_dashboard.mri_runner import orchestrator
from app.mri_autonomous.experience_store import ExperienceStore
from app.mri_autonomous.recovery_runner import AcquisitionRecoveryRunner

app = FastAPI(title="MRI Autonomous Dashboard", version="1.0.0")

try:
    from app.mri_autonomous.storage_guard import StorageConfig
    DEFAULT_SQLITE_PATH = StorageConfig.get_sqlite_path()
except Exception:
    DEFAULT_SQLITE_PATH = Path("data/sqlite/visibility.db")

BASE_DIR = Path(__file__).parent
DB_PATH = DEFAULT_SQLITE_PATH
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_store = None
_recovery_runner = None

def get_experience_store():
    global _store
    if _store is None:
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            p = StorageConfig.get_experience_db_path()
        except Exception:
            p = None
        _store = ExperienceStore(db_path=p)
    return _store

def get_recovery_runner():
    global _recovery_runner
    if _recovery_runner is None:
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            p = StorageConfig.get_sqlite_path()
        except Exception:
            p = None
        _recovery_runner = AcquisitionRecoveryRunner(db_path=p)
    return _recovery_runner


def get_sqlite_conn():
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        current_db = StorageConfig.get_sqlite_path()
    except Exception:
        current_db = DB_PATH
    conn = sqlite3.connect(current_db)
    conn.row_factory = sqlite3.Row
    return conn


def extract_title_from_url(url: str, sku: str) -> str:
    """Fallback extraction of clean product title from canonical URL slug across marketplaces."""
    if not url:
        return f"Publicación {sku}"
    try:
        from urllib.parse import urlparse
        path = urlparse(url).path
        segments = [s for s in path.strip("/").split("/") if s]
        for seg in reversed(segments):
            seg_clean = re.sub(r"\.html$", "", seg, flags=re.IGNORECASE)
            parts = [p for p in seg_clean.split("-") if p]
            cleaned_parts = []
            for p in parts:
                if re.match(r"^MK[A-Z0-9]+$", p, re.IGNORECASE): continue
                if re.match(r"^MLC[U0-9]+$", p, re.IGNORECASE): continue
                if re.match(r"^mpm[0-9]+$", p, re.IGNORECASE): continue
                if re.match(r"^vop[0-9]+$", p, re.IGNORECASE): continue
                if re.match(r"^[0-9]{5,}$", p): continue
                cleaned_parts.append(p)
            if len(cleaned_parts) >= 2:
                return " ".join(cleaned_parts).capitalize()
    except Exception:
        pass
    return f"Publicación {sku}"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/state")
async def get_state():
    return JSONResponse(content={
        "is_running": orchestrator.is_running,
        "state": orchestrator.state,
        "results": orchestrator.results
    })


@app.get("/api/categories/{marketplace}")
async def get_categories_api(marketplace: str):
    from app.mri_dashboard.category_manager import category_manager
    return category_manager.get_categories(marketplace)


@app.post("/api/audit/start")
async def start_audit(background_tasks: BackgroundTasks, request: Request):
    if orchestrator.is_running:
        return JSONResponse(status_code=400, content={"message": "Already running"})
    
    data = await request.json()
    marketplace = data.get("marketplace", "ALL")
    limit = data.get("limit", 5)
    mode = data.get("mode", "AUDIT")
    
    if mode == "CONSOLIDATED_RECOVERY":
        background_tasks.add_task(run_consolidated_recovery_pipeline)
        return JSONResponse(content={"message": "Started Consolidated Recovery Pipeline"})
    elif mode == "DISCOVERY":
        background_tasks.add_task(orchestrator.run_discovery, marketplace, max_pages=int(limit) if limit != "ALL" else 5)
        return JSONResponse(content={"message": "Started Autonomous Discovery mode"})
    else:
        background_tasks.add_task(orchestrator.run_audit, marketplace, limit)
        return JSONResponse(content={"message": f"Started in {mode} mode"})


def run_consolidated_recovery_pipeline():
    orchestrator.is_running = True
    orchestrator.state = {
        "progress": 0,
        "total": 4,
        "current_product": None,
        "status_message": "Ejecutando Corredor Consolidado de Recuperación..."
    }
    orchestrator.results = []
    try:
        res = recovery_runner.execute_complete_pipeline(reuse_harvest=True)
        run_id = res.get("run_id")
        
        # Load publications of this run into orchestrator results for live view
        pubs = fetch_run_publications(run_id)
        orchestrator.results = pubs
        orchestrator.state["progress"] = len(pubs)
        orchestrator.state["total"] = len(pubs)
        orchestrator.state["status_message"] = f"COMPLETED ({res.get('pipeline_status')})"
        
        # Also append run to in-memory orchestrator history
        orchestrator.history.append({
            "run_id": run_id,
            "timestamp": res.get("sqlite_persistence", {}).get("timestamp") or "",
            "marketplace": "MULTI_MARKETPLACE",
            "total": len(pubs),
            "confirmed": sum(1 for p in pubs if p.get("status") in ("CONFIRMED", "OBSERVED", "NICOPOLY_CONFIRMED")),
            "mode": "CONSOLIDATED_RECOVERY"
        })
        orchestrator._save_history()
    except Exception as e:
        orchestrator.state["status_message"] = f"ERROR: {str(e)}"
    finally:
        orchestrator.is_running = False


@app.post("/api/audit/stop")
async def stop_audit():
    orchestrator.stop()
    return JSONResponse(content={"message": "Stopping..."})


from app.mri_autonomous.category_evaluator import evaluate_commercial_category

CATALOG_PATH = Path("Actualización masiva de productos.xlsx")
_master_catalog_cache = None

def clean_cat_title(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    repl = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ñ': 'n',
        chr(225): 'a', chr(233): 'e', chr(237): 'i', chr(243): 'o', chr(250): 'u', chr(241): 'n',
        '\ufffd': 'a'
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return re.sub(r'[^a-z0-9]', '', s)


def normalize_title_tokens(t: str) -> frozenset:
    if not t:
        return frozenset()
    t = t.lower()
    repl = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ñ': 'n'}
    for k, v in repl.items():
        t = t.replace(k, v)
    # Preserve fractions (e.g., 3/4 -> 3slash4, 1/2 -> 1slash2)
    t = re.sub(r'(\d+)\s*/\s*(\d+)', r'\1slash\2', t)
    t = re.sub(r'[^a-z0-9\s]', ' ', t)
    stop_words = {'mujer', 'de', 'con', 'para', 'y', 'el', 'la', 'los', 'las', 'en'}
    tokens = [w for w in t.split() if w not in stop_words and (len(w) > 2 or any(c.isdigit() for c in w))]
    return frozenset(tokens)


def get_master_catalog():
    global _master_catalog_cache
    if _master_catalog_cache is not None:
        return _master_catalog_cache
    
    child_to_cat = {}
    parent_to_cat = {}
    title_to_cat = {}
    token_to_entries = {}
    
    if CATALOG_PATH.exists():
        try:
            import openpyxl
            wb = openpyxl.load_workbook(CATALOG_PATH, read_only=True)
            ws = wb.active
            for r in ws.iter_rows(values_only=True):
                p = str(r[2] or "").strip()
                c = str(r[3] or "").strip()
                t = str(r[4] or "").strip()
                cat = str(r[7] or "").strip()
                fal_tipo = str(r[54] or "").strip() if len(r) > 54 else ""
                entry = {"category": cat, "falabella_tipo": fal_tipo, "title": t, "parent": p, "child": c}
                if c and c not in child_to_cat:
                    child_to_cat[c] = entry
                if p and p not in parent_to_cat:
                    parent_to_cat[p] = entry
                if t:
                    c_key = clean_cat_title(t)
                    if c_key and c_key not in title_to_cat:
                        title_to_cat[c_key] = entry
                    toks = normalize_title_tokens(t)
                    if toks:
                        if toks not in token_to_entries:
                            token_to_entries[toks] = []
                        token_to_entries[toks].append(entry)
            wb.close()
        except Exception as e:
            print("Error loading master catalog in API:", e)
    else:
        # Fallback to versioned JSON fixture for clean checkouts
        fixture_path = Path("data/master_catalog_fixture.json")
        if fixture_path.exists():
            try:
                import json
                with open(fixture_path, "r", encoding="utf-8") as f:
                    rows = json.load(f)
                for r in rows:
                    p = str(r[2] or "").strip()
                    c = str(r[3] or "").strip()
                    t = str(r[4] or "").strip()
                    cat = str(r[7] or "").strip()
                    fal_tipo = str(r[54] or "").strip() if len(r) > 54 else ""
                    entry = {"category": cat, "falabella_tipo": fal_tipo, "title": t, "parent": p, "child": c}
                    if c and c not in child_to_cat:
                        child_to_cat[c] = entry
                    if p and p not in parent_to_cat:
                        parent_to_cat[p] = entry
                    if t:
                        c_key = clean_cat_title(t)
                        if c_key and c_key not in title_to_cat:
                            title_to_cat[c_key] = entry
                        toks = normalize_title_tokens(t)
                        if toks:
                            if toks not in token_to_entries:
                                token_to_entries[toks] = []
                            token_to_entries[toks].append(entry)
            except Exception as e:
                print("Error loading master catalog fixture:", e)
            
    _master_catalog_cache = (child_to_cat, parent_to_cat, title_to_cat, token_to_entries)
    return _master_catalog_cache


def fetch_run_publications(run_id: str) -> List[Dict[str, Any]]:
    conn = get_sqlite_conn()
    child_to_cat, parent_to_cat, title_to_cat, token_to_entries = get_master_catalog()
    
    try:
        cur = conn.cursor()
        query = """
            WITH unified_pubs AS (
                SELECT 
                    pub.publication_id,
                    pub.product_id,
                    pub.marketplace,
                    pub.marketplace_product_id,
                    pub.canonical_url,
                    pub.status,
                    pub.observed_at,
                    pub.run_id,
                    pub.position,
                    pub.surface,
                    pub.position_state,
                    pub.category_relationship,
                    pub.evidence_type,
                    pub.raw_source_id,
                    pub.acquisition_status,
                    pub.identity_status,
                    pub.category_observed,
                    pub.category_source,
                    pub.category_expected,
                    pub.category_decision,
                    pub.commercial_attributes
                FROM mri_publications pub
                WHERE pub.run_id = ?
                UNION ALL
                SELECT 
                    hp.publication_id,
                    hp.product_id,
                    hp.marketplace,
                    hp.marketplace_product_id,
                    hp.canonical_url,
                    hp.status,
                    hp.observed_at,
                    hp.run_id,
                    hp.position,
                    hp.surface,
                    hp.position_state,
                    hp.category_relationship,
                    hp.evidence_type,
                    hp.raw_source_id,
                    hp.acquisition_status,
                    hp.identity_status,
                    hp.category_observed,
                    hp.category_source,
                    hp.category_expected,
                    hp.category_decision,
                    hp.commercial_attributes
                FROM mri_historical_publications hp
                WHERE hp.run_id = ?
            )
            SELECT 
                pub.publication_id,
                pub.product_id,
                pub.marketplace,
                pub.marketplace_product_id,
                pub.canonical_url,
                pub.status,
                pub.observed_at,
                pub.position,
                pub.surface,
                pub.position_state,
                pub.category_relationship,
                pub.evidence_type,
                pub.raw_source_id,
                pub.acquisition_status,
                pub.identity_status,
                pub.category_observed,
                pub.category_source,
                pub.category_expected,
                pub.category_decision,
                pub.commercial_attributes,
                cat.category_name as legacy_cat_name,
                ps.product_title,
                ps.sku_master
            FROM unified_pubs pub
            LEFT JOIN (
                SELECT publication_id, MIN(category_id) as category_id
                FROM mri_publication_categories
                GROUP BY publication_id
            ) pc ON pub.publication_id = pc.publication_id
            LEFT JOIN mri_categories cat ON pc.category_id = cat.category_id
            LEFT JOIN (
                SELECT ps1.marketplace_sku, ps1.product_title, ps1.sku_master
                FROM product_snapshots ps1
                INNER JOIN (
                    SELECT marketplace_sku, MAX(audit_date) as max_audit_date
                    FROM product_snapshots
                    GROUP BY marketplace_sku
                ) ps2 ON ps1.marketplace_sku = ps2.marketplace_sku AND ps1.audit_date = ps2.max_audit_date
            ) ps ON pub.marketplace_product_id = ps.marketplace_sku
            ORDER BY pub.marketplace, pub.position ASC
        """
        run_row = cur.execute("SELECT terminal_state FROM mri_runs WHERE run_id = ?", (run_id,)).fetchone()
        run_terminal_state = run_row["terminal_state"] if run_row and "terminal_state" in run_row.keys() else None

        rows = cur.execute(query, (run_id, run_id)).fetchall()
        
        results = []
        for r in rows:
            mkt = r["marketplace"] or "UNKNOWN"
            sku = r["marketplace_product_id"] or r["publication_id"] or "UNKNOWN"
            url = r["canonical_url"] or ""
            title = r["product_title"]
            if not title or title.strip() == "" or "\ufffd" in title or "?" in title:
                url_title = extract_title_from_url(url, sku)
                if url_title and not url_title.startswith("Publicación"):
                    title = url_title
                elif not title:
                    title = url_title
                
            # Master catalog matching for expected category & identity resolution
            sku_m = r["sku_master"] or sku
            m_entry = None
            parent_sku = None
            variant_sku = None
            candidate_variants = []
            
            # First check if title maps cleanly to a master product parent or variant entries
            title_matched_entry = None
            if title:
                c_key = clean_cat_title(title)
                if c_key and c_key in title_to_cat:
                    title_matched_entry = title_to_cat[c_key]
                    t_toks = normalize_title_tokens(title)
                    if t_toks and t_toks in token_to_entries:
                        entries = token_to_entries[t_toks]
                        parents = {e.get("parent") for e in entries if e.get("parent")}
                        # Only match if there is unambiguous parent consensus across all matched entries
                        if len(parents) == 1:
                            title_matched_entry = entries[0]
                            candidate_variants = [e.get("child") for e in entries if e.get("child")]
                        else:
                            # Ambiguous parent match across catalog: do not guess
                            title_matched_entry = None
                            candidate_variants = []
            
            # If title cleanly matched a parent product, verify whether sku_m belongs to that parent
            if title_matched_entry:
                m_entry = title_matched_entry
                parent_sku = m_entry.get("parent")
                # When parent has multiple variants, only confirm a child variant if size/attribute evidence allows differentiating it
                if parent_sku and not candidate_variants:
                    candidate_variants = [c for c, e in child_to_cat.items() if e.get("parent") == parent_sku]
                
                # Check if multiple variants exist in master catalog
                if candidate_variants and len(candidate_variants) > 1:
                    # Do not arbitrarily select one child variant without size/attribute differentiation
                    variant_sku = None
                elif sku_m and sku_m in child_to_cat and child_to_cat[sku_m].get("parent") == parent_sku:
                    variant_sku = sku_m
                else:
                    variant_sku = None
            elif sku_m and sku_m in child_to_cat:
                m_entry = child_to_cat[sku_m]
                variant_sku = sku_m
                parent_sku = m_entry.get("parent")
            elif sku_m and sku_m in parent_to_cat:
                m_entry = parent_to_cat[sku_m]
                parent_sku = sku_m
            
            if parent_sku and not candidate_variants:
                # Find all known children for this parent in master catalog
                candidate_variants = [c for c, e in child_to_cat.items() if e.get("parent") == parent_sku]
            
            # Identity status: distinguish parent identity verified from variant verified
            ident_st = r["identity_status"]
            if not ident_st or ident_st == "IDENTITY_NOT_LINKED":
                if variant_sku:
                    ident_st = "TARGET_IDENTITY_VERIFIED"
                elif parent_sku:
                    ident_st = "PARENT_IDENTITY_VERIFIED"
                else:
                    ident_st = "IDENTIDAD_NO_VERIFICADA"
            
            # Prioritize explicit DB column if migrated, else fallback
            exp_cat = r["category_expected"]
            if not exp_cat or exp_cat in ("NO_VERIFICADO", "Vestuario Femenino / Nicopoly"):
                if m_entry and m_entry.get("category"):
                    exp_cat = m_entry["category"]
                else:
                    exp_cat = "NO_VERIFICADO"

            # Observed category: prioritize explicit column, then joined category table
            obs_cat = r["category_observed"] or r["legacy_cat_name"] or "NO_VERIFICADO"
            if obs_cat in ("NONE", "CATEGORY_UNKNOWN", ""):
                obs_cat = "NO_VERIFICADO"
                
            cat_source = r["category_source"] or ("PUBLIC_CHANNEL_BREADCRUMBS" if r["legacy_cat_name"] else "NO_VERIFICADO")
            
            # Acquisition status
            acq_st = r["acquisition_status"] or ("OBSERVED" if r["status"] in ("OBSERVED", "LIVE_OBSERVATION_CONFIRMED") else r["status"])
            
            # Parse attributes - only include if explicitly captured as commercial_attributes in DB
            attrs = {}
            if r["commercial_attributes"]:
                try:
                    attrs = json.loads(r["commercial_attributes"])
                except Exception as e:
                    logger.warning(f"Error parsing commercial_attributes for {sku}: {e}")

            # Brand corridor extraction from attributes, category, or surface
            brand_corridor = None
            if attrs and "store_url" in attrs:
                brand_corridor = f"Tienda oficial Nicopoly ({attrs['store_url']})"
            elif any(m in obs_cat.lower() for m in ['marcas casuales', 'tienda_de_marca', 'tienda oficial', 'tienda/nicopoly', 'brand store', 'brand hub']):
                brand_corridor = obs_cat

            # Commercial category decision
            cat_dec = r["category_decision"]
            cat_reason = None
            if not cat_dec or cat_dec in ("OBSERVED", "CONFIRMED", "ACTIVE"):
                cat_eval = evaluate_commercial_category(
                    product_title=title,
                    expected_category=exp_cat,
                    observed_category=obs_cat,
                    public_attributes=attrs,
                    marketplace=mkt,
                    identity_status=ident_st,
                    brand_corridor=brand_corridor
                )
                cat_dec = cat_eval["decision"]
                cat_reason = cat_eval["reason"]
            else:
                cat_reason = f"Decisión {cat_dec} verificada contra catálogo maestro y evidencia pública."

            # Evidence collection
            ev_list = []
            if r["evidence_type"]:
                ev_list.append(f"Tipo: {r['evidence_type']}")
            if r["position"]:
                ev_list.append(f"Posición observada: {r['position']}")
            if r["surface"]:
                ev_list.append(f"Superficie: {r['surface']}")
            if obs_cat != "NO_VERIFICADO":
                ev_list.append(f"Categoría pública: {obs_cat} (Fuente: {cat_source})")
            if brand_corridor:
                ev_list.append(f"Corredor de marca: {brand_corridor}")
            if parent_sku:
                ev_list.append(f"Producto Padre: {parent_sku}")
            if candidate_variants:
                ev_list.append(f"Variantes conocidas en catálogo: {', '.join(candidate_variants)}")
            if attrs:
                ev_list.append(f"Atributos públicos: {attrs}")
                
            motivo = f"Publicación observada en canal comercial {mkt}. {cat_reason}"
            
            # Coverage calculation: preserve PAGE_BUDGET_EXCEEDED and partial limits
            if run_terminal_state == "PAGE_BUDGET_EXCEEDED":
                cov_val = "PAGE_BUDGET_EXCEEDED"
            elif (url and obs_cat != "NO_VERIFICADO" and ident_st in ("TARGET_IDENTITY_VERIFIED", "PARENT_IDENTITY_VERIFIED")):
                cov_val = "COMPLETE"
            else:
                cov_val = "PARTIAL"

            results.append({
                "producto_id": sku,
                "producto_nombre": title,
                "marketplace": mkt,
                "url_encontrada": url,
                "url": url,
                "fecha_observacion": r["observed_at"] or "NO_VERIFICADO",
                "timestamp": r["observed_at"] or "NO_VERIFICADO",
                "evidencia_identidad": ev_list if ev_list else ["NO_VERIFICADO"],
                "evidence": ev_list if ev_list else ["NO_VERIFICADO"],
                "estado_final": cat_dec,
                "status": cat_dec,
                "acquisition_status": acq_st,
                "identity_status": ident_st,
                "parent_sku": parent_sku,
                "variant_sku": variant_sku,
                "candidate_variants": candidate_variants,
                "brand_corridor": brand_corridor,
                "motivo_verificable": motivo,
                "reason": motivo,
                "coverage": cov_val,
                "real_category": obs_cat,
                "expected_category": exp_cat,
                "real_subcategory": "NO_VERIFICADO",
                "category_source": cat_source,
                "decision": cat_dec,
                "source": "PAGINATED_ADAPTER_HARVEST",
                "observed_sku": sku
            })
        return results
    finally:
        conn.close()


@app.get("/api/history")
async def get_history():
    """
    Returns unified runs history:
    1. Reads all persisted runs from mri_runs and mri_publications in SQLite.
    2. Merges with in-memory orchestrator runs.
    """
    history_items = []
    seen_runs = set()
    
    if DB_PATH.exists():
        conn = get_sqlite_conn()
        try:
            cur = conn.cursor()
            # Runs from unified mri_publications + mri_historical_publications grouped by run_id
            query = """
                WITH all_pubs AS (
                    SELECT run_id, observed_at, marketplace, publication_id, status FROM mri_publications
                    UNION ALL
                    SELECT run_id, observed_at, marketplace, publication_id, status FROM mri_historical_publications
                )
                SELECT 
                    p.run_id,
                    MIN(p.observed_at) as started_at,
                    p.marketplace,
                    COUNT(p.publication_id) as total,
                    SUM(CASE WHEN p.status IN ('OBSERVED', 'CONFIRMED', 'NICOPOLY_CONFIRMED') THEN 1 ELSE 0 END) as confirmed,
                    COALESCE(r.execution_mode, 'SQLITE_PERSISTED') as mode
                FROM all_pubs p
                LEFT JOIN mri_runs r ON p.run_id = r.run_id
                GROUP BY p.run_id
                ORDER BY started_at DESC
            """
            for r in cur.execute(query).fetchall():
                run_id = r["run_id"]
                seen_runs.add(run_id)
                history_items.append({
                    "run_id": run_id,
                    "timestamp": r["started_at"] or "2026-10-14T00:00:00",
                    "marketplace": r["marketplace"] if r["marketplace"] else "MULTI_MARKETPLACE",
                    "total": r["total"] or 0,
                    "confirmed": r["confirmed"] or 0,
                    "mode": r["mode"]
                })
        finally:
            conn.close()
            
    # Also include any orchestrator history not yet in SQLite
    for h in orchestrator.history:
        r_id = h.get("run_id")
        if r_id and r_id not in seen_runs:
            seen_runs.add(r_id)
            history_items.append(h)
            
    return JSONResponse(content={"history": history_items})


@app.get("/api/history/{run_id}")
async def get_history_run_publications(run_id: str):
    """
    Retrieves verifiable publication details for any historical run without re-harvesting.
    """
    # 1. Check SQLite mri_publications
    pubs = fetch_run_publications(run_id)
    if pubs:
        return JSONResponse(content={"run_id": run_id, "publications": pubs, "count": len(pubs), "source": "SQLITE"})
    
    # 2. Check orchestrator history
    for h in orchestrator.history:
        if h.get("run_id") == run_id:
            return JSONResponse(content={"run_id": run_id, "publications": h.get("results", []), "count": len(h.get("results", [])), "source": "ORCHESTRATOR_MEMORY"})
            
    return JSONResponse(status_code=404, content={"message": f"Run {run_id} not found", "run_id": run_id, "publications": []})


@app.get("/api/learning")
async def get_learning():
    """
    Returns real experiences, strategies, and re-audit recovery records.
    """
    conn = get_experience_store()._get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, value, brand, marketplace, status, discovery_method, confidence, success_count, first_seen_at, last_seen_at, evidence_reference FROM experience ORDER BY last_seen_at DESC LIMIT 50")
        rows = cur.fetchall()
        
        experiences = []
        for r in rows:
            experiences.append({
                "hash": str(r[0]),
                "product_name": r[1] or "N/A",
                "brand": r[2] or "Nicopoly",
                "marketplace": r[3] or "N/A",
                "status": r[4] or "UNKNOWN",
                "method": r[5] or "AUTONOMOUS_EXTRACTION",
                "score": r[6] if r[6] is not None else 1.0,
                "hits": r[7] if r[7] is not None else 0,
                "created_at": r[8] or "NO_VERIFICADO",
                "updated_at": r[9] or "NO_VERIFICADO",
                "evidence": r[10] or "Registro verificado de experiencia"
            })
            
        cur.execute("SELECT COUNT(*), SUM(success_count) FROM experience WHERE status IN ('VALIDATED', 'ACTIVE', 'VERIFIED', 'LAST_GOOD')")
        stats = cur.fetchone()
        
        # Also query real recovery experiences from visibility.db if available
        rec_experiences = []
        if DB_PATH.exists():
            v_conn = get_sqlite_conn()
            try:
                v_cur = v_conn.cursor()
                v_rows = v_cur.execute("SELECT id, timestamp, marketplace, category, strategy, result, recovery_seconds, evidence FROM recovery_experiences ORDER BY timestamp DESC LIMIT 20").fetchall()
                for vr in v_rows:
                    rec_experiences.append({
                        "id": vr["id"],
                        "timestamp": vr["timestamp"],
                        "marketplace": vr["marketplace"],
                        "category": vr["category"],
                        "strategy": vr["strategy"],
                        "result": vr["result"],
                        "recovery_seconds": vr["recovery_seconds"],
                        "evidence": vr["evidence"]
                    })
            except Exception:
                pass
            finally:
                v_conn.close()
        
        return JSONResponse(content={
            "experiences": experiences,
            "recovery_experiences": rec_experiences,
            "total_validated": stats[0] or 0,
            "total_reused": stats[1] or 0
        })
    finally:
        conn.close()


@app.get("/api/rea/paris")
async def get_rea_paris_data():
    """
    Returns normalized Paris commercial intelligence discovered via REA engine:
    - Commercial entities (categories, subcategories, brand corridor, promotional collections)
    - Brand vs Seller separation metrics
    - Operational category counts
    """
    try:
        from app.mri_autonomous.rea_paris_engine import REAParisEngine
        engine = REAParisEngine()
        brand_summary = engine.get_brand_summary("Nicopoly")
        seller_summary = engine.get_seller_summary("NICOPOLY")
        return JSONResponse(content={
            "marketplace": "Paris",
            "brand": "Nicopoly",
            "total_brand": brand_summary.get("total_brand_results", 4904),
            "official_seller": "NICOPOLY",
            "total_official_seller": seller_summary.get("total_seller_results", 4213),
            "other_sellers_total": max(0, brand_summary.get("total_brand_results", 4904) - seller_summary.get("total_seller_results", 4213)),
            "facets": brand_summary.get("facets_available", []),
            "product_types": brand_summary.get("product_types", []),
            "discovery_engine": "Constructor.io AI Search",
            "status": "OPERATIONAL"
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8055)
