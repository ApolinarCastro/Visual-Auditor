"""
Enhanced Dashboard API v2
Endpoints:
  GET /                    → main dashboard (HTML)
  GET /api/audits          → latest audits JSON
  GET /api/summary         → global stats cards
  GET /api/marketplace     → per-marketplace summary
  GET /api/trend           → time-series for charts
  GET /api/alerts          → recent alerts
  POST /api/alerts/{id}/ack → acknowledge alert
  GET /api/health          → system health
  GET /api/selectors       → selector stats (self-learning)
  GET /api/circuit-breakers → CB statuses
  POST /api/audit/trigger  → trigger manual audit
"""
import asyncio
import logging
from fastapi import FastAPI, Request, Response, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import os
from dotenv import load_dotenv

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
load_dotenv()

from app.storage.sqlite_manager import SQLiteManager
from app.intelligence.trend_engine import get_alerts, ack_alert, get_trend
from app.intelligence.health_monitor import health_summary, latency_stats
from app.intelligence.selector_registry import selector_stats
from app.utils.circuit_breaker import all_breaker_statuses
from app.config.settings import BASE_DIR
from app.loaders.rule_loader import RuleLoader
import uvicorn
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from app.auditor.audit_runner import _global_audit_lock

def configure_dashboard_logging():
    os.makedirs(BASE_DIR / "logs", exist_ok=True)
    log_file = str((BASE_DIR / "logs" / "auditor.log").resolve())
    root = logging.getLogger()
    
    # Check if a StreamHandler (to stdout/stderr) already exists
    has_stream = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    )
    # Check if a FileHandler to auditor.log already exists
    has_file = any(
        isinstance(h, logging.FileHandler) and os.path.abspath(getattr(h, "baseFilename", "")) == os.path.abspath(log_file)
        for h in root.handlers
    )
    
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    
    if not has_stream:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        try:
            console.stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
        root.addHandler(console)
        
    if not has_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        
    root.setLevel(logging.INFO)
    logging.getLogger("app").setLevel(logging.INFO)

configure_dashboard_logging()

# In-memory audit tracking state
_audit_state = {
    "status": "IDLE",
    "started_at": None,
    "marketplace": None
}

logger = logging.getLogger(__name__)

security = HTTPBasic()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    import os
    env_user = os.getenv("DASHBOARD_USER")
    env_pass = os.getenv("DASHBOARD_PASS")
    
    if not env_user or not env_pass:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Credenciales de acceso no configuradas en el entorno."
        )

    correct_username = secrets.compare_digest(credentials.username, env_user)
    correct_password = secrets.compare_digest(credentials.password, env_pass)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

app = FastAPI(title="Visibility Auditor", version="2.0.0", dependencies=[Depends(get_current_username)])

@app.on_event("startup")
async def on_startup():
    configure_dashboard_logging()

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.middleware("http")
async def csrf_origin_check(request: Request, call_next):
    if request.method == "POST":
        origin = request.headers.get("origin")
        if origin and "localhost" not in origin and "127.0.0.1" not in origin:
            return JSONResponse(status_code=403, content={"detail": "CSRF verification failed: Invalid Origin."})
    return await call_next(request)

_templates_dir = BASE_DIR / "app" / "dashboard" / "templates"
_static_dir = BASE_DIR / "app" / "dashboard" / "static"
os.makedirs(_static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

templates = Jinja2Templates(directory=str(_templates_dir))

db = SQLiteManager()
_rule_loader = RuleLoader()
_cached_rules = {}

def get_rules_cached(marketplace: str):
    mp_key = marketplace.lower()
    if mp_key not in _cached_rules:
        mp_name_lookup = mp_key
        if "falabella" in mp_key:
            mp_name_lookup = "falabella"
        elif "mercado libre" in mp_key or "meli" in mp_key or "mercadolibre" in mp_key:
            mp_name_lookup = "mercado libre"
        
        rules = _rule_loader.get_rules_for_marketplace(mp_name_lookup)
        _cached_rules[mp_key] = rules
    return _cached_rules[mp_key]

def enrich_audits(audits_list):
    enriched = []
    for aud in audits_list:
        r = dict(aud)
        rules = get_rules_cached(r["marketplace"])
        if rules and "category_urls" in rules:
            cat_upper = r["category"].upper()
            brand_url = rules["category_urls"].get(f"{cat_upper}_census")
            if brand_url:
                r["category_brand_url"] = brand_url
            else:
                found = False
                for k, url in rules["category_urls"].items():
                    if k.endswith("_census"):
                        clean_k = k.replace("_census", "")
                        if clean_k in cat_upper or cat_upper in clean_k:
                            r["category_brand_url"] = url
                            found = True
                            break
                if not found:
                    r["category_brand_url"] = r["category_url"]
        else:
            r["category_brand_url"] = r["category_url"]
        enriched.append(r)
    return enriched

# ─── HTML Dashboard ────────────────────────────────────────────────────────────

@app.get("/")
@limiter.limit("20/minute")
async def index(request: Request):
    raw_audits = await db.get_latest_audits()
    audits = enrich_audits(raw_audits)
    summary = await db.get_summary_stats()
    mp_summary = await db.get_marketplace_summary()
    alerts = await get_alerts(limit=10, unack_only=True)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "audits": audits,
            "summary": summary,
            "mp_summary": mp_summary,
            "alerts": alerts,
            "mri_enabled": mri_read_model.is_feature_enabled(),
        },
    )

# ─── JSON API ──────────────────────────────────────────────────────────────────

@app.get("/api/audits")
async def api_audits():
    raw_data = await db.get_latest_audits()
    data = enrich_audits(raw_data)
    return JSONResponse(content={"audits": data})


@app.get("/api/summary")
async def api_summary():
    data = await db.get_summary_stats()
    return JSONResponse(content=data)


@app.get("/api/marketplace")
async def api_marketplace():
    data = await db.get_marketplace_summary()
    return JSONResponse(content={"marketplaces": data})


@app.get("/api/trend")
async def api_trend(marketplace: str, category: str, days: int = 30):
    data = await get_trend(marketplace, category, days)
    return JSONResponse(content={"trend": data})


@app.get("/api/history")
async def api_history(marketplace: str, category: str, days: int = 30):
    data = await db.get_audit_history(marketplace, category, days)
    return JSONResponse(content={"history": data})


@app.get("/api/history/marketplace")
async def api_marketplace_history(marketplace: str, days: int = 7):
    data = await db.get_marketplace_history(marketplace, days)
    return JSONResponse(content={"history": data})


@app.get("/api/alerts")
async def api_alerts(limit: int = 50, unack_only: bool = False):
    data = await get_alerts(limit=limit, unack_only=unack_only)
    return JSONResponse(content={"alerts": data})


@app.post("/api/alerts/{alert_id}/ack")
async def api_ack_alert(alert_id: int):
    await ack_alert(alert_id)
    return JSONResponse(content={"status": "acknowledged", "id": alert_id})


@app.get("/api/health")
async def api_health():
    summary = await health_summary()
    latency = await latency_stats()
    return JSONResponse(content={"health": summary, "latency": latency})


@app.get("/api/selectors")
async def api_selectors(marketplace: str | None = None):
    data = await selector_stats(marketplace)
    return JSONResponse(content={"selectors": data})


@app.get("/api/circuit-breakers")
async def api_circuit_breakers():
    return JSONResponse(content={"breakers": all_breaker_statuses()})


_MP_NAMES = {
    "mercado libre": "Mercado Libre", "meli": "Mercado Libre", "mercadolibre": "Mercado Libre",
    "paris": "Paris",
    "ripley": "Ripley",
    "falabella": "Falabella",
}

@app.get("/api/audit/status")
async def api_audit_status():
    from app.auditor.audit_runner import _global_audit_lock
    is_running = _global_audit_lock.locked() or (_audit_state.get("status") == "RUNNING")
    return JSONResponse(content={
        "status": "RUNNING" if is_running else "IDLE",
        "started_at": _audit_state.get("started_at") if is_running else None,
        "marketplace": _audit_state.get("marketplace") if is_running else None
    })


@app.post("/api/audit/trigger")
@limiter.limit("5/minute")
async def api_trigger_audit(request: Request, background_tasks: BackgroundTasks, marketplace: str = "all"):
    from app.auditor.audit_runner import AuditRunner, _global_audit_lock
    mp = _MP_NAMES.get(marketplace.lower(), marketplace)

    # 1. Pre-check: Reject if already running
    if _global_audit_lock.locked() or _audit_state.get("status") == "RUNNING":
        active_mp = _audit_state.get("marketplace") or mp
        logger.warning(f"[AuditTrigger] Rechazado: Ya existe una auditoría en ejecución ({active_mp})")
        return JSONResponse(
            status_code=409,
            content={
                "status": "already_running",
                "marketplace": active_mp,
                "message": "Una auditoría ya está en curso."
            }
        )

    # 2. Mark state as RUNNING immediately
    _audit_state["status"] = "RUNNING"
    _audit_state["started_at"] = datetime.now().isoformat()
    _audit_state["marketplace"] = mp

    runner = AuditRunner()

    async def _run():
        try:
            logger.info(f"[AuditRunner] Iniciando ejecución de auditoría en background: {mp}")
            if marketplace.lower() == "all":
                await runner.run_all()
            else:
                async with _global_audit_lock:
                    await runner.run_marketplace_audit(mp)
            logger.info(f"[AuditRunner] Ejecución de auditoría finalizada para: {mp}")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"[AuditRunner] Error fatal no controlado durante auditoría: {e}\n{tb}", exc_info=True)
            print(f"[ERROR] Error fatal no controlado durante auditoría: {e}\n{tb}", file=sys.stderr)
        finally:
            _audit_state["status"] = "IDLE"
            _audit_state["started_at"] = None
            _audit_state["marketplace"] = None

    background_tasks.add_task(_run)
    return JSONResponse(content={
        "status": "triggered",
        "marketplace": mp,
        "message": f"Audit started in background for: {mp}"
    })


# ─── Utility endpoints ─────────────────────────────────────────────────────────

@app.get("/api/categories")
async def api_categories():
    data = await db.get_all_categories()
    return JSONResponse(content={"categories": data})


@app.get("/api/sessions")
async def api_sessions():
    import os
    import json
    import time
    from datetime import datetime
    
    ripley_path = BASE_DIR / "data" / "ripley_session.json"
    ml_path = BASE_DIR / "data" / "mercadolibre_session.json"
    
    def inspect_session(filepath, name):
        if not os.path.exists(filepath):
            return {
                "name": name,
                "exists": False,
                "cookie_count": 0,
                "last_updated": "No encontrado",
                "status": "FALTA",
                "status_class": "badge-err"
            }
        try:
            mtime = os.path.getmtime(filepath)
            last_updated = datetime.fromtimestamp(mtime).isoformat()
            
            with open(filepath, "r", encoding="utf-8") as f:
                cookies = json.load(f)
                
            count = len(cookies) if isinstance(cookies, list) else 0
            diff_hours = (time.time() - mtime) / 3600
            
            if diff_hours < 24:
                status = "ACTIVO"
                status_class = "badge-ok"
            elif diff_hours < 168:
                status = "DEGRADADO"
                status_class = "badge-warn"
            else:
                status = "EXPIRADO"
                status_class = "badge-err"
                
            return {
                "name": name,
                "exists": True,
                "cookie_count": count,
                "last_updated": last_updated,
                "status": status,
                "status_class": status_class
            }
        except Exception as e:
            return {
                "name": name,
                "exists": True,
                "cookie_count": 0,
                "last_updated": "Error de lectura",
                "status": "CORRUPTO",
                "status_class": "badge-err",
                "error": str(e)
            }
            
    return JSONResponse(content={
        "ripley": inspect_session(ripley_path, "Ripley"),
        "mercadolibre": inspect_session(ml_path, "Mercado Libre")
    })


@app.post("/api/sessions/upload")
async def api_upload_session(request: Request):
    import os
    import json
    import shutil
    
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"JSON inválido: {str(e)}"})
        
    marketplace = body.get("marketplace")
    cookies = body.get("cookies")
    
    if not marketplace or marketplace.lower() not in ["ripley", "mercadolibre"]:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Marketplace inválido. Debe ser 'ripley' o 'mercadolibre'."})
        
    if not isinstance(cookies, list):
        if isinstance(cookies, str):
            try:
                cookies = json.loads(cookies)
            except Exception:
                pass
        
        if not isinstance(cookies, list):
            return JSONResponse(status_code=400, content={"status": "error", "message": "Formato de cookies inválido. Debe ser una lista JSON de cookies."})
            
    # Validate each cookie has name and value
    for c in cookies:
        if not isinstance(c, dict) or "name" not in c or "value" not in c:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Cada cookie debe ser un objeto JSON con campos 'name' y 'value'."})
            
    filename = f"{marketplace.lower()}_session.json"
    filepath = BASE_DIR / "data" / filename
    
    # Make backup copy if exists
    if os.path.exists(filepath):
        backup_path = filepath.with_suffix(".json.bak")
        try:
            shutil.copy2(filepath, backup_path)
            logger.info(f"[SESSIONS] Creada copia de respaldo de la sesión: {backup_path}")
        except Exception as e:
            logger.warning(f"[SESSIONS] No se pudo crear copia de respaldo: {e}")
            
    # Write the new cookies
    try:
        os.makedirs(filepath.parent, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
            
        logger.info(f"[SESSIONS] Actualizada sesión para {marketplace} con {len(cookies)} cookies.")
        return JSONResponse(content={
            "status": "success",
            "message": f"Sesión de {marketplace} actualizada con éxito ({len(cookies)} cookies)."
        })
    except Exception as e:
        logger.error(f"[SESSIONS] Error al escribir archivo de sesión: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Error al escribir archivo: {str(e)}"})


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


# ─── Pricing Intelligence & Multivende API ───────────────────────────────────────

@app.get("/api/price-history")
async def api_price_history(sku_master: str, days: int = 30):
    data = await db.get_price_history(sku_master, days)
    return JSONResponse(content={"sku_master": sku_master, "history": data})

@app.get("/api/snapshots")
async def api_snapshots(marketplace: str, category: str, limit: int = 100, only_nicopoly: bool = False):
    data = await db.get_snapshots_for_category(marketplace, category, limit, only_nicopoly)
    return JSONResponse(content={"marketplace": marketplace, "category": category, "only_nicopoly": only_nicopoly, "products": data})

@app.get("/api/multivende/lookup")
async def api_multivende_lookup(marketplace: str = "Paris", query: str = ""):
    from app.loaders.multivende_loader import get_multivende_loader
    loader = get_multivende_loader()
    result = loader.lookup_sku(marketplace, query)
    return JSONResponse(content={"query": query, "marketplace": marketplace, "result": result})

@app.get("/api/category-coverage")
async def api_category_coverage(marketplace: str = "Paris"):
    from app.intelligence.category_discovery import CategoryDiscoveryEngine
    engine = CategoryDiscoveryEngine()
    result = await engine.audit_marketplace_coverage(marketplace)
    return JSONResponse(content={"coverage": result})


# ─── Server ────────────────────────────────────────────────────────────────────


@app.get("/api/audit-discrepancies")
async def api_audit_discrepancies():
    """FIX: Detecta categorias donde total_nicopoly del audit != COUNT de snapshots is_nicopoly=1."""
    async with db._connect() as conn:
        rows = await conn.execute_fetchall(
            """SELECT a.marketplace, a.category, a.audit_date, a.total_nicopoly,
                      COUNT(s.id) as snapshot_count,
                      a.total_nicopoly - COUNT(s.id) as discrepancy
               FROM audits a
               LEFT JOIN product_snapshots s 
                   ON LOWER(s.marketplace) = LOWER(a.marketplace) 
                   AND LOWER(s.category) = LOWER(a.category)
                   AND s.audit_date LIKE substr(a.audit_date, 1, 10) || '%'
                   AND s.is_nicopoly = 1
               WHERE a.total_nicopoly > 0
               GROUP BY a.id
               HAVING a.total_nicopoly != COUNT(s.id)
               ORDER BY discrepancy DESC"""
        )
        results = []
        for row in rows:
            results.append({
                "marketplace": row[0],
                "category": row[1],
                "audit_date": row[2],
                "total_nicopoly_audit": row[3],
                "snapshot_count": row[4],
                "discrepancy": row[5]
            })
        return JSONResponse(content={"discrepancies": results, "total": len(results)})

# ─── Resilience & Selective Reaudit API ──────────────────────────────────────────

@app.post("/api/reaudit")
async def api_selective_reaudit(request: Request):
    """Executes an isolated selective reaudit for a specific marketplace and category."""
    try:
        body = await request.json()
        marketplace = body.get("marketplace")
        category = body.get("category")
        if not marketplace or not category:
            return JSONResponse(status_code=400, content={"status": "error", "message": "marketplace y category son requeridos"})

        from app.intelligence.provider_manager import MarketplaceProviderManager
        pm = MarketplaceProviderManager(db)
        result = await pm.execute_selective_reaudit(marketplace, category, caller="dashboard_api")
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"[API] Error in selective reaudit: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/source-health")
async def api_get_source_health(marketplace: str | None = None):
    """Retrieves source health statuses for all or a specific marketplace."""
    health = await db.get_source_health(marketplace)
    return JSONResponse(content={"source_health": health})

@app.get("/api/recovery-experiences")
async def api_get_recovery_experiences(limit: int = 50):
    """Retrieves the recent recovery experience logs."""
    experiences = await db.get_recovery_experiences(limit)
    return JSONResponse(content={"recovery_experiences": experiences})


# ─── MRI V2 Read-Only Inspection API (Shadow Mode / Zero Cutover) ─────────────
from app.dashboard.mri_read_model import MRIReadModel

mri_read_model = MRIReadModel()

def _check_mri_enabled():
    if not mri_read_model.is_feature_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MRI V2 Dashboard is currently disabled. Check COMMERCIAL_READ_MODE."
        )

@app.get("/api/mri/status")
async def api_mri_status():
    return JSONResponse(content=mri_read_model.get_status())

@app.get("/api/mri/unresolved_observations")
async def api_mri_unresolved_observations(
    marketplace: str = "Ripley",
    limit: int = 100
):
    _check_mri_enabled()
    return JSONResponse(content=mri_read_model.get_unresolved_observations(
        marketplace=marketplace,
        limit=limit
    ))

@app.get("/api/mri/summary")
async def api_mri_summary():
    _check_mri_enabled()
    return JSONResponse(content=mri_read_model.get_summary())

@app.get("/api/mri/publications")
async def api_mri_publications(
    marketplace: str | None = None,
    category: str | None = None,
    surface: str | None = None,
    top_n: str | None = None,
    evidence_state: str | None = None,
    page: int = 1,
    limit: int = 50
):
    _check_mri_enabled()
    return JSONResponse(content=mri_read_model.get_publications(
        marketplace=marketplace,
        category=category,
        surface=surface,
        top_n=top_n,
        evidence_state=evidence_state,
        page=page,
        limit=limit
    ))

@app.get("/api/mri/categories")
async def api_mri_categories(marketplace: str | None = None):
    _check_mri_enabled()
    return JSONResponse(content=mri_read_model.get_categories(marketplace=marketplace))

@app.get("/api/mri/evidence")
async def api_mri_evidence(
    marketplace: str | None = None,
    claim_type: str | None = None,
    page: int = 1,
    limit: int = 50
):
    _check_mri_enabled()
    return JSONResponse(content=mri_read_model.get_evidence(
        marketplace=marketplace,
        claim_type=claim_type,
        page=page,
        limit=limit
    ))

@app.get("/api/mri/search_intents")
async def api_mri_search_intents():
    _check_mri_enabled()
    return JSONResponse(content=mri_read_model.get_search_intents())

@app.get("/api/mri/season_products")
async def api_mri_season_products():
    _check_mri_enabled()
    return JSONResponse(content=mri_read_model.get_season_products())

@app.get("/api/mri/health")
async def api_mri_health():
    _check_mri_enabled()
    return JSONResponse(content=mri_read_model.get_source_health())

@app.get("/api/mri/comparison")
async def api_mri_comparison():
    _check_mri_enabled()
    return JSONResponse(content=mri_read_model.get_legacy_comparison())


async def start_dashboard(host: str = "0.0.0.0", port: int = 8000):
    config = uvicorn.Config(app, host=host, port=port, loop="asyncio", log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

