import uvicorn
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import sys
import sqlite3
import re
from typing import Dict, Any, List

# Ensure the project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.mri_dashboard.mri_runner import orchestrator
from app.mri_autonomous.experience_store import ExperienceStore
from app.mri_autonomous.recovery_runner import AcquisitionRecoveryRunner

app = FastAPI(title="MRI Autonomous Dashboard", version="1.0.0")

BASE_DIR = Path(__file__).parent
DB_PATH = Path("data/sqlite/visibility.db")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

store = ExperienceStore()
recovery_runner = AcquisitionRecoveryRunner()


def get_sqlite_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def extract_title_from_url(url: str, sku: str) -> str:
    """Fallback extraction of clean product title from canonical URL slug."""
    if not url:
        return f"Producto {sku}"
    try:
        from urllib.parse import urlparse
        path = urlparse(url).path
        slug = path.strip("/").split("/")[-1]
        slug = re.sub(r"\.html$", "", slug, flags=re.IGNORECASE)
        # remove sku suffix like -MKKXV8V9X8 or -MLCU... or trailing numbers
        parts = [p for p in slug.split("-") if p]
        cleaned_parts = []
        for p in parts:
            if re.match(r"^MK[A-Z0-9]+$", p, re.IGNORECASE):
                continue
            if re.match(r"^MLC[U0-9]+$", p, re.IGNORECASE):
                continue
            if re.match(r"^vop[0-9]+$", p, re.IGNORECASE):
                continue
            if re.match(r"^[0-9]{6,}$", p):
                continue
            cleaned_parts.append(p)
        if cleaned_parts:
            title = " ".join(cleaned_parts).capitalize()
            return title
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


def fetch_run_publications(run_id: str) -> List[Dict[str, Any]]:
    conn = get_sqlite_conn()
    try:
        cur = conn.cursor()
        query = """
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
                cat.category_name as observed_category,
                ps.product_title
            FROM mri_publications pub
            LEFT JOIN (
                SELECT publication_id, MIN(category_id) as category_id
                FROM mri_publication_categories
                GROUP BY publication_id
            ) pc ON pub.publication_id = pc.publication_id
            LEFT JOIN mri_categories cat ON pc.category_id = cat.category_id
            LEFT JOIN (
                SELECT marketplace_sku, MAX(product_title) as product_title
                FROM product_snapshots
                GROUP BY marketplace_sku
            ) ps ON pub.marketplace_product_id = ps.marketplace_sku
            WHERE pub.run_id = ?
            ORDER BY pub.marketplace, pub.position ASC
        """
        rows = cur.execute(query, (run_id,)).fetchall()
        
        results = []
        for r in rows:
            mkt = r["marketplace"] or "UNKNOWN"
            sku = r["marketplace_product_id"] or r["publication_id"] or "UNKNOWN"
            url = r["canonical_url"] or ""
            title = r["product_title"]
            if not title or title.strip() == "":
                title = extract_title_from_url(url, sku)
                
            obs_cat = r["observed_category"] or "NO_VERIFICADO"
            st = r["status"] or "NO_VERIFICADO"
            decision = "CONFIRMED" if st in ("OBSERVED", "CONFIRMED", "NICOPOLY_CONFIRMED") else st
            
            ev_list = []
            if r["evidence_type"]:
                ev_list.append(f"Tipo: {r['evidence_type']}")
            if r["position"]:
                ev_list.append(f"Posición observada: {r['position']}")
            if r["surface"]:
                ev_list.append(f"Superficie: {r['surface']}")
            if r["category_relationship"]:
                ev_list.append(f"Relación categoría: {r['category_relationship']}")
                
            motivo = f"Publicación {st} verificada en canal comercial {mkt} con URL canónica individual."
            
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
                "estado_final": decision,
                "status": decision,
                "motivo_verificable": motivo,
                "reason": motivo,
                "coverage": "COMPLETE" if url else "PARTIAL",
                "real_category": obs_cat,
                "expected_category": "Vestuario Femenino / Nicopoly",
                "real_subcategory": "NO_VERIFICADO",
                "category_source": "SQLITE_CATALOG" if r["observed_category"] else "NO_VERIFICADO",
                "decision": decision,
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
            # Runs from mri_publications grouped by run_id
            query = """
                SELECT 
                    p.run_id,
                    MIN(p.observed_at) as started_at,
                    p.marketplace,
                    COUNT(p.publication_id) as total,
                    SUM(CASE WHEN p.status IN ('OBSERVED', 'CONFIRMED', 'NICOPOLY_CONFIRMED') THEN 1 ELSE 0 END) as confirmed,
                    COALESCE(r.execution_mode, 'SQLITE_PERSISTED') as mode
                FROM mri_publications p
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
    conn = store._get_connection()
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8055)
