import uvicorn
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import sys

# Ensure the project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.mri_dashboard.mri_runner import orchestrator
from app.mri_autonomous.experience_store import ExperienceStore

app = FastAPI(title="MRI Autonomous Dashboard", version="1.0.0")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

store = ExperienceStore()

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
    
    if mode == "DISCOVERY":
        background_tasks.add_task(orchestrator.run_discovery, marketplace, max_pages=int(limit) if limit != "ALL" else 5)
    else:
        background_tasks.add_task(orchestrator.run_audit, marketplace, limit)
        
    return JSONResponse(content={"message": f"Started in {mode} mode"})

@app.post("/api/audit/stop")
async def stop_audit():
    orchestrator.stop()
    return JSONResponse(content={"message": "Stopping..."})

@app.get("/api/history")
async def get_history():
    return JSONResponse(content={"history": orchestrator.history})

@app.get("/api/learning")
async def get_learning():
    # Fetch from ExperienceStore
    conn = store._get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, value, brand, marketplace, status, discovery_method, confidence, success_count, first_seen_at, last_seen_at FROM experience ORDER BY last_seen_at DESC LIMIT 50")
        rows = cur.fetchall()
        
        experiences = []
        for r in rows:
            experiences.append({
                "hash": str(r[0]),
                "product_name": r[1],
                "brand": r[2],
                "marketplace": r[3],
                "status": r[4],
                "method": r[5] or "AUTONOMOUS_EXTRACTION",
                "score": r[6] if r[6] is not None else 1.0,
                "hits": r[7] if r[7] is not None else 0,
                "created_at": r[8],
                "updated_at": r[9]
            })
            
        cur.execute("SELECT COUNT(*), SUM(success_count) FROM experience WHERE status='VALIDATED' OR status='ACTIVE' OR status='VERIFIED'")
        stats = cur.fetchone()
        
        return JSONResponse(content={
            "experiences": experiences,
            "total_validated": stats[0] or 0,
            "total_reused": stats[1] or 0
        })
    finally:
        conn.close()

if __name__ == "__main__":
    import threading
    import webbrowser
    import time
    import urllib.request
    from urllib.error import URLError

    def open_browser():
        for _ in range(30):
            try:
                response = urllib.request.urlopen("http://127.0.0.1:8055/", timeout=2)
                if response.status == 200:
                    webbrowser.open("http://127.0.0.1:8055/")
                    return
            except Exception:
                pass
            time.sleep(1)
        print("[ERROR] No se pudo conectar al servidor para abrir el navegador.", flush=True)

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8055)
