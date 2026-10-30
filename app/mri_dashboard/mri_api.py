import uvicorn
from fastapi import FastAPI, BackgroundTasks, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pathlib import Path
import os
import sys
import sqlite3
import json
import re
import secrets
import time
from typing import Dict, Any, List, Optional

# Ensure the project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.mri_dashboard.mri_runner import orchestrator
from app.mri_autonomous.experience_store import ExperienceStore
from app.mri_autonomous.recovery_runner import AcquisitionRecoveryRunner

# ── Authentication (B-03) ────────────────────────────────────────────────
# The MRI API previously had NO authentication: no middleware, no dependency,
# bound to 0.0.0.0, with POST /api/audit/start able to spend real scraper quota.
# Mirrors the pattern already proven in app/dashboard/api.py: HTTP Basic applied
# globally, fail-closed when credentials are absent, constant-time comparison.
try:
    from dotenv import load_dotenv
    from app.config.settings import BASE_DIR as _CFG_BASE_DIR
    # Repo-root scoped: avoid inheriting an unrelated parent .env via the
    # upward search that bare load_dotenv() performs.
    load_dotenv(_CFG_BASE_DIR / ".env", override=False)
except Exception:
    pass

security = HTTPBasic()


def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    env_user = os.getenv("DASHBOARD_USER")
    env_pass = os.getenv("DASHBOARD_PASS")

    if not env_user or not env_pass:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Credenciales de acceso no configuradas en el entorno.",
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


app = FastAPI(
    title="MRI Autonomous Dashboard",
    version="1.0.0",
    dependencies=[Depends(get_current_username)],
)

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


def get_sqlite_conn(db_path: Optional[str] = None):
    if db_path:
        current_db = db_path
    else:
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            current_db = StorageConfig.get_sqlite_path()
        except Exception:
            current_db = DB_PATH
    conn = sqlite3.connect(current_db)
    conn.row_factory = sqlite3.Row
    return conn


def _operational_db_path() -> Path:
    """Database that receives NEW audits (operator-scoped, write-authorized)."""
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        return Path(StorageConfig.get_sqlite_path())
    except Exception:
        return Path(DB_PATH)


def _protected_db_path():
    """Read-only historical database (production). Never written by MRI."""
    env = os.getenv("MRI_HISTORICAL_DB")
    candidates = [Path(env)] if env else []
    candidates.append(Path(__file__).resolve().parents[2] / "data" / "sqlite" / "visibility.db")
    for c in candidates:
        try:
            if c.exists() and c.resolve() != _operational_db_path().resolve():
                return c.resolve()
        except Exception:
            continue
    return None


def _connect_ro(path) -> sqlite3.Connection:
    """Open a database strictly read-only (no write authorization requested)."""
    p = Path(path).as_posix()
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _protected_runs():
    """Runs persisted in the PROTECTED database, tagged as such."""
    protected = _protected_db_path()
    if protected is None:
        return []
    items = []
    try:
        conn = _connect_ro(protected)
    except Exception:
        return []
    try:
        cur = conn.cursor()
        has_runs = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mri_runs'").fetchone()
        if has_runs:
            rows = cur.execute(
                """SELECT r.run_id, COALESCE(r.started_at, '') AS started_at, r.marketplace,
                          (SELECT COUNT(*) FROM mri_publications p WHERE p.run_id = r.run_id) AS total,
                          (SELECT COUNT(*) FROM mri_publications p WHERE p.run_id = r.run_id
                             AND p.status IN ('OBSERVED','CONFIRMED','NICOPOLY_CONFIRMED')) AS confirmed,
                          COALESCE(r.execution_mode, 'SQLITE_PERSISTED') AS mode
                   FROM mri_runs r ORDER BY started_at DESC""").fetchall()
            for r in rows:
                items.append({
                    "run_id": r["run_id"],
                    "timestamp": r["started_at"] or "",
                    "marketplace": r["marketplace"] or "MULTI_MARKETPLACE",
                    "total": r["total"] or 0,
                    "confirmed": r["confirmed"] or 0,
                    "mode": r["mode"],
                    "source": "PROTECTED",
                })
    except Exception:
        items = []
    finally:
        conn.close()
    return items


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


@app.get("/api/mri/health")
async def get_mri_health():
    """Operational health/census derived from the live run, never synthetic."""
    st = orchestrator.state or {}
    return JSONResponse(content={
        "health": st.get("health"),
        "source_health": st.get("source_health"),
        "global_coverage": st.get("global_coverage"),
        "run_id": st.get("run_id"),
        "is_running": orchestrator.is_running,
    })


@app.get("/api/mri/sessions")
async def get_mri_sessions():
    """Session-cookie status only; cookie values are never returned."""
    from app.mri_dashboard.session_store import session_status
    return JSONResponse(content={
        "ripley": session_status("Ripley"),
        "mercadolibre": session_status("Mercado Libre"),
    })


@app.post("/api/mri/sessions/{marketplace}")
async def update_mri_session(marketplace: str, request: Request):
    """Import a Cookie-Editor JSON array into MRI's own local session store."""
    from app.mri_dashboard.session_store import (
        canonical_marketplace, save_session)
    name = canonical_marketplace(marketplace)
    try:
        payload = await request.json()
        result = save_session(name, payload)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=400,
                            content={"error": f"COOKIE_IMPORT_FAILED: {type(exc).__name__}"})
    return JSONResponse(content={"ok": True, **result})


@app.get("/api/version")
async def get_version():
    from app.mri_dashboard.build_info import build_info
    return JSONResponse(content=build_info())


@app.get("/api/state")
async def get_state():
    st = orchestrator.state or {}
    from app.mri_dashboard.acquisition_contract import view_metadata
    from app.mri_dashboard.observation_reconciliation import summarize_results
    _view = view_metadata(execution_mode=f"{st.get('mode') or 'UNKNOWN'}",
                          run_id=st.get("run_id"), source="LIVE_MEMORY", live=True)
    return JSONResponse(content={
        "is_running": orchestrator.is_running,
        "state": st,
        "results": orchestrator.results,
        # run context: the UI must show which run/date/marketplace it is showing
        "run_id": st.get("run_id"),
        "started_at": st.get("started_at"),
        "marketplace": st.get("marketplace"),
        "mode": st.get("mode"),
        "source": "LIVE_MEMORY",
        "results_count": len(orchestrator.results or []),
        "build": __import__("app.mri_dashboard.build_info", fromlist=["build_info"]).build_info(),
        "reconciliation": summarize_results(orchestrator.results or []),
        # acquisition truth (live view only; never a persisted historical run)
        **_view,
        "outcome": st.get("outcome"),
        "acquisitions": st.get("acquisitions") or [],
        "identity_summary": st.get("identity_summary"),
        "catalog_reference": st.get("catalog_reference") or _safe_catalog_reference(),
    })


_RUN_ERRORS = []


def _error_log_path():
    from app.mri_autonomous.storage_guard import StorageConfig
    return StorageConfig.get_aux_dir() / "mri_run_errors.json"


def _append_run_error(entry: dict) -> None:
    """Keep a bounded, inspectable history of background failures."""
    _RUN_ERRORS.append(entry)
    del _RUN_ERRORS[:-50]
    try:
        path = _error_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        path.write_text(_json.dumps(_RUN_ERRORS, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    except Exception:
        pass


@app.get("/api/errors")
async def get_run_errors():
    """Background failure history (inspection, never hidden)."""
    return JSONResponse(content={"errors": _RUN_ERRORS[-50:], "count": len(_RUN_ERRORS)})


async def _guarded_run(fn, run_id: str, *args, **kwargs):
    """Run a background task and ALWAYS publish a terminal state.

    HTTP 202 only means "accepted". On failure the stage and error are recorded,
    the state ends as FAILED (never IDLE/INICIANDO) and no exception escapes to
    the ASGI layer.
    """
    from datetime import datetime, timezone
    import inspect
    import traceback
    stage = (orchestrator.state or {}).get("stage") or "preparando"
    # The API marked the run as accepted (RUNNING). The runners guard
    # themselves with `is_running` and would return immediately, so release
    # the dispatch flag here and let the runner own it for the whole execution.
    orchestrator.is_running = False
    try:
        _res = fn(*args, **kwargs)
        if inspect.isawaitable(_res):
            await _res
    except Exception as exc:
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "run_id": run_id,
            "stage": (orchestrator.state or {}).get("stage") or stage,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-2000:],
            "at": now,
        }
        _append_run_error(entry)
        st = dict(orchestrator.state or {})
        _declared = st.get("outcome")
        _contract_states = ("SOURCE_BLOCKED", "EXTRACTOR_FAILURE", "PARTIAL",
                            "NOT_FOUND", "STOPPED_BY_USER")
        st.update({
            # Preserve a contract state declared by the runner; generic FAILED
            # only when the runner did not classify the failure.
            "status_message": (_declared if _declared in _contract_states else "FAILED"),
            "terminal_state": (_declared if _declared in _contract_states else "FAILED"),
            "failed_stage": entry["stage"],
            "error": entry["error"],
            "error_run_id": run_id,
            "last_activity": now,
            "completed_at": now,
        })
        errs = list(st.get("errors") or [])
        errs.append(entry)
        st["errors"] = errs
        states = dict(st.get("marketplace_states") or {})
        for m, v in list(states.items()):
            if v == "EN_CURSO":
                states[m] = "FALLIDO"
        st["marketplace_states"] = states
        orchestrator.state = st
        orchestrator.is_running = False


@app.get("/api/storage/info")
async def get_storage_info():
    """Explicit, verifiable storage selection (operational vs protected)."""
    op = _operational_db_path()
    prot = _protected_db_path()
    authorized = False
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        # ensure_writable both verifies AND registers the scoped grant that the
        # audit path uses; it can never authorize production (B-02 barrier).
        StorageConfig.ensure_writable(op, reason="storage info")
        authorized = True
    except Exception:
        authorized = False
    # Auxiliary run destinations actually used by the discovery flow.
    destinations = {}
    try:
        from app.mri_autonomous.storage_guard import StorageConfig as _SC
        for name, path in {
            "categories_json": _SC.get_categories_json_path(),
            "history_json": _SC.get_history_json_path(),
            "experience_db": _SC.get_experience_db_path(),
        }.items():
            try:
                _SC.assert_write_allowed(path)
                destinations[name] = {"path": str(path), "authorized": True}
            except Exception:
                destinations[name] = {"path": str(path), "authorized": False}
        aux = str(_SC.get_aux_dir())
    except Exception:
        aux = None

    return JSONResponse(content={
        "operational_db": str(op),
        "operational_exists": op.exists(),
        "protected_db": str(prot) if prot else None,
        "protected_role": "READ_ONLY_HISTORICAL",
        "aux_dir": aux,
        "destinations": destinations,
        "write_authorized": authorized,
        "mode": (os.getenv("MRI_ENV") or "PRODUCTION").upper(),
    })


@app.get("/api/categories/{marketplace}")
async def get_categories_api(marketplace: str, run_id: Optional[str] = None):
    effective_db = DB_PATH
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        effective_db = StorageConfig.get_sqlite_path()
    except Exception:
        pass

    cats_dict = {}
    if Path(effective_db).exists():
        conn = get_sqlite_conn(str(effective_db))
        try:
            cur = conn.cursor()
            # If run_id is supplied, query categories active for that run
            counts = {}
            if run_id:
                q = """
                    SELECT c.category_id, c.category_name, c.canonical_url,
                           COUNT(DISTINCT p.publication_id) AS n
                    FROM mri_categories c
                    JOIN mri_publication_categories pc ON c.category_id = pc.category_id
                    JOIN mri_publications p ON pc.publication_id = p.publication_id
                    WHERE c.marketplace = ? AND p.run_id = ?
                      AND c.category_name != 'CATEGORY_UNKNOWN'
                    GROUP BY c.category_id, c.category_name, c.canonical_url
                """
                rows = cur.execute(q, (marketplace, run_id)).fetchall()
                try:
                    qh = """
                        SELECT c.category_id, c.category_name, c.canonical_url,
                               COUNT(DISTINCT hp.publication_id) AS n
                        FROM mri_categories c
                        JOIN mri_historical_publication_categories hpc ON c.category_id = hpc.category_id
                        JOIN mri_historical_publications hp
                          ON hp.publication_id = hpc.publication_id AND hp.run_id = hpc.run_id
                        WHERE c.marketplace = ? AND hpc.run_id = ?
                          AND c.category_name != 'CATEGORY_UNKNOWN'
                        GROUP BY c.category_id, c.category_name, c.canonical_url
                    """
                    for r in cur.execute(qh, (marketplace, run_id)).fetchall():
                        counts[r[0]] = max(int(r[3] or 0), counts.get(r[0], 0))
                except Exception:
                    pass
            else:
                rows = cur.execute(
                    "SELECT category_id, category_name, canonical_url FROM mri_categories WHERE marketplace = ?",
                    (marketplace,)
                ).fetchall()
            _display_aliases = {"ropa interior y de dormir": "Body"}
            for r in rows:
                cid, cname, curl = r[0], r[1], r[2]
                cname = _display_aliases.get(str(cname or "").strip().lower(), cname)
                n = int(r[3] or 0) if len(r) > 3 else int(counts.get(cid, 0))
                counts[cid] = max(n, counts.get(cid, 0))
                cats_dict[cid] = {
                    "name": cname,
                    "url": curl or "",
                    "source": "SQLITE_MRI_PERSISTENCE",
                    "status": "VERIFIED",
                    "publications": n,
                }
        except Exception:
            pass
        finally:
            conn.close()

    # The UI filter must also expose categories discovered but with 0
    # publications (otherwise it looks as if only 7 categories exist).
    if run_id:
        try:
            import json as _json
            from app.mri_autonomous.storage_guard import StorageConfig as _SCc
            _hist = Path(_SCc.get_aux_dir()) / "mri_history.json"
            if _hist.exists():
                _entries = _json.loads(_hist.read_text(encoding="utf-8"))
                _hit = next((e for e in _entries if e.get("run_id") == run_id), None)
                _tax = ((_hit or {}).get("taxonomy") or {}).get(marketplace) or {}
                for _c in _tax.get("categories") or []:
                    _name = _c.get("name") or _c.get("category_id")
                    _slug = str(_c.get("category_id") or _name or "cat")
                    _key = f"tax_{_slug}"
                    _n = 0
                    for _existing in cats_dict.values():
                        if str(_existing.get("name") or "").strip().lower() == str(_name or "").strip().lower():
                            _n = int(_existing.get("publications") or 0)
                            break
                    cats_dict.setdefault(_key, {
                        "name": _name,
                        "url": _c.get("url") or "",
                        "source": "TAXONOMY_DISCOVERED",
                        "status": "PENDING",
                        "publications": _n,
                    })
        except Exception:
            pass

    # Attach raw result counts from the run history. `publications` stays the
    # unique persisted count; `observations` is the source's result count.
    if run_id and cats_dict:
        try:
            import json as _json
            import re as _re
            from app.mri_autonomous.storage_guard import StorageConfig as _SCo
            _hp = Path(_SCo.get_aux_dir()) / "mri_history.json"
            _hit2 = next((e for e in _json.loads(_hp.read_text(encoding="utf-8"))
                          if e.get("run_id") == run_id), None) if _hp.exists() else None
            from app.mri_dashboard.category_observations import observations_for
            _acqs = ((_hit2 or {}).get("acquisitions") or [])
            _obs = observations_for(cats_dict, _acqs)
            for _cid, _nraw in _obs.items():
                if _cid in cats_dict:
                    cats_dict[_cid]["observations"] = _nraw
        except Exception:
            pass

    if cats_dict:
        from app.mri_dashboard.category_hierarchy import rollup
        return JSONResponse(content=rollup(cats_dict))

    from app.mri_dashboard.category_manager import category_manager
    return JSONResponse(content=category_manager.get_categories(marketplace))


@app.post("/api/audit/start")
async def start_audit(background_tasks: BackgroundTasks, request: Request):
    # Parse the body FIRST: between the running-guard and the RUNNING
    # publication below there must be no `await`, otherwise two concurrent
    # requests could both pass the guard and start two runs (double-accept).
    data = await request.json()
    if orchestrator.is_running:
        return JSONResponse(status_code=400, content={"message": "Already running"})

    marketplace = data.get("marketplace", "ALL")
    limit = data.get("limit", 5)
    mode = data.get("mode", "AUDIT")
    parallel_all = bool(data.get("parallel", True))

    # Mode-specific parameters are parsed and validated BEFORE any RUNNING state
    # is published. A malformed request must never leave the dashboard stuck in
    # RUNNING with no scheduled task (the old int(limit) ran after publishing).
    discovery_pages = None
    discovery_item_limit = None
    ssr_items = None
    if mode == "DISCOVERY":
        try:
            discovery_pages = int(limit) if str(limit) != "ALL" else 5
        except (TypeError, ValueError):
            discovery_pages = 5
        if str(limit) != "ALL" and str(limit).isdigit():
            discovery_item_limit = int(limit)
    elif mode in ("FALABELLA_SSR", "PARIS_PUBLIC"):
        try:
            ssr_items = int(limit)
        except (TypeError, ValueError):
            ssr_items = 12

    # The audit write destination must be EXPLICITLY authorized by the operator
    # and accepted by the guard. Refuse with an actionable 409 instead of
    # enqueuing a run that would die inside the storage barrier (which used to
    # surface as an ASGI 500 / ProductionWriteBlockedError).
    audit_db = None
    try:
        from app.mri_autonomous.storage_guard import StorageConfig as _SC
        audit_db = str(_SC.get_sqlite_path())
        _SC.ensure_writable(audit_db, reason="dashboard audit persistence")
        # Ensure auxiliary run destinations are authorized in the same operational boundary
        for _aux_p in (_SC.get_categories_json_path(), _SC.get_history_json_path(), _SC.get_experience_db_path()):
            try:
                _SC.ensure_writable(_aux_p, reason="dashboard audit auxiliary persistence")
            except Exception:
                pass
    except Exception as exc:
        return JSONResponse(status_code=409, content={
            "error": "WRITE_DESTINATION_NOT_AUTHORIZED",
            "message": ("La auditoría necesita un destino de escritura autorizado. "
                        "Ejecute MRI en modo aislado con MRI_ENV=TEST y MRI_ISOLATED_DB "
                        "apuntando a una base de trabajo. "
                        "La escritura sobre la base productiva permanece denegada por diseño. "
                        "La consulta de histórico sigue disponible en modo lectura."),
            "detail": str(exc)[:200],
            "audit_db": audit_db,
        })
    
    # 202 = accepted. Publish run identity and RUNNING state NOW, before any
    # background work, so the UI never shows IDLE or inherited progress.
    from datetime import datetime as _dt
    run_id = f"run_mri_{str(mode).lower()}_{int(time.time())}"
    _now = _dt.now().isoformat()
    _mkts = (["Mercado Libre", "Paris", "Ripley", "Falabella"]
             if marketplace == "ALL" else [marketplace])
    orchestrator.is_running = True
    orchestrator.results = []
    orchestrator.state = {
        "progress": 0, "total": 0, "total_known": False,
        "current_product": None, "current_category": None,
        "status_message": "RUNNING", "stage": "preparando",
        "mode": mode, "marketplace": marketplace,
        "brand": data.get("brand", "Nicopoly"),
        "run_id": run_id, "started_at": _now, "last_activity": _now,
        "marketplace_states": {m: "PENDIENTE" for m in _mkts},
        "errors": [],
    }

    if mode == "CONSOLIDATED_RECOVERY":
        # run_consolidated_recovery_pipeline() takes NO arguments. Passing an
        # extra positional argument made this branch raise TypeError inside the
        # background task on every invocation.
        background_tasks.add_task(_guarded_run, run_consolidated_recovery_pipeline, run_id)
        return JSONResponse(status_code=200, content={
            "message": "Accepted: Consolidated Recovery Pipeline", "mode": mode,
            "run_id": run_id, "state": "RUNNING"})
    elif mode == "DISCOVERY":
        pages = discovery_pages
        item_limit = discovery_item_limit
        if marketplace == "ALL" and parallel_all:
            # First run_id is consumed by _guarded_run for error publication;
            # the second is the runner argument.
            background_tasks.add_task(
                _guarded_run, orchestrator.run_parallel_discovery, run_id, run_id,
                marketplaces=None, max_pages=pages, limit=item_limit)
            return JSONResponse(status_code=200, content={
                "message": "Accepted: Autonomous Discovery (ALL_PARALLEL)",
                "mode": mode, "run_id": run_id, "state": "RUNNING",
                "marketplace": marketplace, "max_pages": pages,
                "execution_strategy": "ALL_PARALLEL"})
        background_tasks.add_task(_guarded_run, orchestrator.run_discovery,
                                  run_id, marketplace, pages, run_id, item_limit)
        return JSONResponse(status_code=200, content={
            "message": "Accepted: Autonomous Discovery", "mode": mode,
            "run_id": run_id, "state": "RUNNING",
            "marketplace": marketplace, "max_pages": pages,
            "execution_strategy": "SEQUENTIAL"})
    elif mode == "FALABELLA_SSR":
        # Bounded, browser-free acquisition using the CERTIFIED Falabella HTTP/SSR
        # strategy (DECISIONS.md D-016 / FAILURES.md F-010). No new engine: this
        # exposes the existing proven path through the authenticated audit API,
        # so acquisition -> persistence is one supported, auditable flow.
        brand = data.get("brand", "Nicopoly")
        items = ssr_items
        background_tasks.add_task(_guarded_run, run_falabella_ssr_acquisition,
                                  run_id, brand, items, run_id)
        return JSONResponse(status_code=200, content={
            "message": "Accepted: FALABELLA_SSR acquisition", "mode": mode,
            "brand": brand, "max_items": items, "run_id": run_id,
            "state": "RUNNING"})
    elif mode == "PARIS_PUBLIC":
        # Bounded, browser-free Paris acquisition through the EXISTING
        # REAParisEngine (public Constructor key discovery). Same contract as
        # FALABELLA_SSR: one supported flow acquisition -> persistence.
        brand = data.get("brand", "Nicopoly")
        items = ssr_items
        background_tasks.add_task(_guarded_run, run_paris_public_acquisition,
                                  run_id, brand, items, run_id)
        return JSONResponse(status_code=200, content={
            "message": "Accepted: PARIS_PUBLIC acquisition", "mode": mode,
            "brand": brand, "max_items": items, "run_id": run_id,
            "state": "RUNNING"})
    else:
        background_tasks.add_task(_guarded_run, orchestrator.run_audit,
                                  run_id, marketplace, limit, run_id)
        return JSONResponse(status_code=200, content={
            "message": f"Accepted in {mode} mode", "mode": mode,
            "run_id": run_id, "state": "RUNNING"})


def run_falabella_ssr_acquisition(brand: str = "Nicopoly", max_items: int = 12,
                                  run_id: Optional[str] = None):
    """
    Bounded Falabella acquisition via the proven HTTP/SSR strategy, then persist.

    Deliberately explicit about outcome:
        FOUND          brand publications observed with direct seller evidence
        NOT_FOUND      source served successfully but yielded no brand publications
        SOURCE_BLOCKED request/HTTP failure prevented acquisition
        UNKNOWN        observation exists but brand identity is unproven
    Never fabricates categories, sellers, publications or metrics.
    """
    from datetime import datetime, timezone
    from app.mri_autonomous.storage_guard import StorageConfig
    from app.mri_autonomous.falabella_ssr_engine import FalabellaSSREngine

    run_id = run_id or f"run_mri_falabella_ssr_{int(time.time())}"
    orchestrator.is_running = True
    orchestrator.state = {
        "progress": 0,
        "total": 0,
        "current_product": None,
        "status_message": "FALABELLA_SSR_STARTED",
        "mode": "FALABELLA_SSR",
        "marketplace": "Falabella",
        "brand": brand,
        "run_id": run_id,
        "last_run_id": run_id,
    }

    pubs, ents, brand_ok = [], [], 0
    outcome = "UNKNOWN"
    error = None
    try:
        db = str(StorageConfig.get_sqlite_path())
        eng = FalabellaSSREngine()
        try:
            payload = eng.get_brand_catalog(brand_name=brand, page=1)
        except Exception as e:
            payload = None
            outcome = "SOURCE_BLOCKED"
            error = f"{type(e).__name__}: {e}"

        if payload is not None:
            pubs, ents = eng.harvest_sample_publications(
                brand=brand, max_items=max_items, page_payload=payload)
            brand_ok = sum(
                1 for p in pubs
                if any(str(s).strip().lower() == brand.lower() for s in (p.sellers or []))
            )
            if pubs and brand_ok == len(pubs):
                outcome = "FOUND"
            elif pubs:
                outcome = "UNKNOWN"
            else:
                outcome = "NOT_FOUND"

        persisted = {"publications_materialized": 0,
                     "categories_materialized": 0,
                     "category_links_materialized": 0}
        if outcome == "FOUND":
            persisted = eng.persist_to_mri_sqlite(pubs, ents, run_id, db, "COMPLETED")

        orchestrator.state.update({
            "progress": 100,
            "total": len(pubs),
            "status_message": "FALABELLA_SSR_COMPLETED",
            "outcome": outcome,
            "run_id": run_id,
            "last_run_id": run_id,
            "normalized": len(pubs),
            "brand_confirmed": brand_ok,
            "persisted": persisted,
            "db_path": db,
            "error": error,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        orchestrator.state.update({
            "status_message": "FALABELLA_SSR_FAILED",
            "outcome": "UNKNOWN",
            "error": f"{type(e).__name__}: {e}",
        })
    finally:
        orchestrator.is_running = False


def run_paris_public_acquisition(brand: str = "Nicopoly", max_items: int = 12,
                                 run_id: Optional[str] = None):
    """
    Bounded Paris acquisition via the EXISTING engine + public key discovery.

    Outcomes: FOUND / NOT_FOUND / SOURCE_BLOCKED / UNKNOWN (never fabricated).
    Persists into the OPERATIONAL database only.
    """
    from datetime import datetime, timezone
    from app.mri_autonomous.storage_guard import StorageConfig
    from app.mri_autonomous.rea_paris_engine import REAParisEngine

    run_id = run_id or f"run_mri_paris_public_{int(time.time())}"
    orchestrator.is_running = True
    orchestrator.state = {
        "progress": 0, "total": 0, "current_product": None,
        "status_message": "PARIS_PUBLIC_STARTED",
        "mode": "PARIS_PUBLIC", "marketplace": "Paris", "brand": brand,
        "run_id": run_id, "started_at": datetime.now().isoformat(),
    }
    pubs, ents, outcome, error = [], [], "UNKNOWN", None
    try:
        db = str(StorageConfig.get_sqlite_path())
        eng = REAParisEngine()
        try:
            pubs, ents = eng.harvest_sample_publications(brand=brand, max_items=max_items)
        except Exception as e:
            outcome = "SOURCE_BLOCKED"
            error = f"{type(e).__name__}: {e}"

        brand_ok = sum(
            1 for p in pubs
            if any(str(s).strip().upper() == brand.upper() for s in (p.sellers or []))
        )
        if pubs and brand_ok == len(pubs):
            outcome = "FOUND"
        elif pubs:
            outcome = "UNKNOWN"
        elif outcome != "SOURCE_BLOCKED":
            outcome = "NOT_FOUND"

        persisted = {"publications_materialized": 0,
                     "categories_materialized": 0,
                     "category_links_materialized": 0}
        if outcome == "FOUND":
            persisted = eng.persist_to_mri_sqlite(pubs, ents, run_id, db, "COMPLETED")

        orchestrator.state.update({
            "progress": 100, "total": len(pubs),
            "status_message": "PARIS_PUBLIC_COMPLETED", "outcome": outcome,
            "run_id": run_id, "normalized": len(pubs),
            "brand_confirmed": brand_ok, "persisted": persisted,
            "db_path": db, "error": error,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        orchestrator.state.update({"status_message": "PARIS_PUBLIC_FAILED",
                                   "outcome": "UNKNOWN",
                                   "error": f"{type(e).__name__}: {e}"})
    finally:
        orchestrator.is_running = False


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
        runner = get_recovery_runner()
        res = runner.execute_complete_pipeline(reuse_harvest=True)
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

def _resolve_catalog_path() -> Path:
    """Locate the master catalog independently of the process CWD.

    The launcher can run from the repo root while the code lives in a
    worktree; a relative path silently loaded a tiny fixture instead of the
    real 15k-SKU master.
    """
    import os
    name = "Actualización masiva de productos.xlsx"
    candidates = []
    env = os.environ.get("MRI_MASTER_CATALOG_PATH")
    if env:
        candidates.append(Path(env))
    roots = [Path(__file__).resolve().parents[2], Path.cwd(),
             Path(__file__).resolve().parents[3]]
    for root in roots:
        candidates.append(root / name)
    for cand in candidates:
        if cand.exists():
            return cand
    return roots[0] / name


CATALOG_PATH = _resolve_catalog_path()
_master_catalog_cache = None
_master_catalog_source = "MISSING"


def master_catalog_status() -> dict:
    """Status of the OPTIONAL historical master catalog.

    It is a historical reference for lookup only: never an authority for
    current publications, sellers, categories or absence.
    """
    import os
    roots = []
    try:
        roots.append(Path.cwd())
        roots.append(Path(__file__).resolve().parents[2])
    except Exception:
        pass
    found = None
    for root in roots:
        candidate = root / CATALOG_PATH.name
        if candidate.exists():
            found = str(candidate.resolve())
            break
    return {
        "status": "AVAILABLE" if found else "CATALOG_REFERENCE_MISSING",
        "path": found,
        "role": "HISTORICAL_REFERENCE",
        "authority": "NONE",
        "allowed_use": "LOOKUP_BY_IDENTIFIER_ONLY",
        "source_used": _master_catalog_source,
        "blocks_acquisition": False,
    }

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
    global _master_catalog_cache, _master_catalog_source
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
                # Master schema: 7=MARCA, 9=CATEGORIA. Using 7 made the
                # expected category "Nicopoly" (brand) instead of the real leaf.
                cat = str(r[9] or "").strip()
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
            _master_catalog_source = "HISTORICAL_REFERENCE_XLSX"
        except Exception as e:
            print("Error loading master catalog in API:", e)
            _master_catalog_source = "UNREADABLE"
    else:
        # Fallback to versioned JSON fixture for clean checkouts
        fixture_path = Path("data/master_catalog_fixture.json")
        if fixture_path.exists():
            _master_catalog_source = "HISTORICAL_REFERENCE_FIXTURE"
            try:
                import json
                with open(fixture_path, "r", encoding="utf-8") as f:
                    rows = json.load(f)
                for r in rows:
                    p = str(r[2] or "").strip()
                    c = str(r[3] or "").strip()
                    t = str(r[4] or "").strip()
                    cat = str(r[9] or "").strip()
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


def fetch_run_publications(run_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    if db_path:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    else:
        conn = get_sqlite_conn()
    child_to_cat, parent_to_cat, title_to_cat, token_to_entries = get_master_catalog()
    
    try:
        cur = conn.cursor()
        has_product_snapshots = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='product_snapshots'"
        ).fetchone()
        has_hist_pubs = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mri_historical_publications'"
        ).fetchone()

        hist_union = ""
        if has_hist_pubs:
            hist_union = """
                UNION ALL
                SELECT 
                    hp.publication_id, hp.product_id, hp.marketplace, hp.marketplace_product_id,
                    hp.canonical_url, hp.status, hp.observed_at, hp.run_id, hp.position, hp.surface,
                    hp.position_state, hp.category_relationship, hp.evidence_type, hp.raw_source_id,
                    hp.acquisition_status, hp.identity_status, hp.category_observed,
                    hp.category_source, hp.category_expected, hp.category_decision, hp.commercial_attributes
                FROM mri_historical_publications hp
                WHERE hp.run_id = ?
            """

        if has_product_snapshots:
            query = f"""
                WITH unified_pubs AS (
                    SELECT 
                        pub.publication_id, pub.product_id, pub.marketplace, pub.marketplace_product_id,
                        pub.canonical_url, pub.status, pub.observed_at, pub.run_id, pub.position, pub.surface,
                        pub.position_state, pub.category_relationship, pub.evidence_type, pub.raw_source_id,
                        pub.acquisition_status, pub.identity_status, pub.category_observed,
                        pub.category_source, pub.category_expected, pub.category_decision, pub.commercial_attributes
                    FROM mri_publications pub
                    WHERE pub.run_id = ?
                    {hist_union}
                )
                SELECT 
                    pub.publication_id, pub.product_id, pub.marketplace, pub.marketplace_product_id,
                    pub.canonical_url, pub.status, pub.observed_at, pub.position, pub.surface,
                    pub.position_state, pub.category_relationship, pub.evidence_type, pub.raw_source_id,
                    pub.acquisition_status, pub.identity_status, pub.category_observed,
                    pub.category_source, pub.category_expected, pub.category_decision, pub.commercial_attributes,
                    cat.category_name as legacy_cat_name, ps.product_title, ps.sku_master
                FROM unified_pubs pub
                LEFT JOIN (
                    SELECT publication_id, MIN(category_id) as category_id
                    FROM mri_publication_categories
                    WHERE status = 'ACTIVE'
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
        else:
            query = f"""
                WITH unified_pubs AS (
                    SELECT 
                        pub.publication_id, pub.product_id, pub.marketplace, pub.marketplace_product_id,
                        pub.canonical_url, pub.status, pub.observed_at, pub.run_id, pub.position, pub.surface,
                        pub.position_state, pub.category_relationship, pub.evidence_type, pub.raw_source_id,
                        pub.acquisition_status, pub.identity_status, pub.category_observed,
                        pub.category_source, pub.category_expected, pub.category_decision, pub.commercial_attributes
                    FROM mri_publications pub
                    WHERE pub.run_id = ?
                    {hist_union}
                )
                SELECT 
                    pub.publication_id, pub.product_id, pub.marketplace, pub.marketplace_product_id,
                    pub.canonical_url, pub.status, pub.observed_at, pub.position, pub.surface,
                    pub.position_state, pub.category_relationship, pub.evidence_type, pub.raw_source_id,
                    pub.acquisition_status, pub.identity_status, pub.category_observed,
                    pub.category_source, pub.category_expected, pub.category_decision, pub.commercial_attributes,
                    cat.category_name as legacy_cat_name, NULL as product_title, NULL as sku_master
                FROM unified_pubs pub
                LEFT JOIN (
                    SELECT publication_id, MIN(category_id) as category_id
                    FROM mri_publication_categories
                    WHERE status = 'ACTIVE'
                    GROUP BY publication_id
                ) pc ON pub.publication_id = pc.publication_id
                LEFT JOIN mri_categories cat ON pc.category_id = cat.category_id
                ORDER BY pub.marketplace, pub.position ASC
            """
        run_row = cur.execute("SELECT terminal_state FROM mri_runs WHERE run_id = ?", (run_id,)).fetchone()
        run_terminal_state = run_row["terminal_state"] if run_row and "terminal_state" in run_row.keys() else None

        # Build run-scoped category memberships map for publications in this run
        has_hist_pub_cat = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mri_historical_publication_categories'"
        ).fetchone()

        cat_lookup_query = """
            SELECT pc.publication_id, pc.category_id, cat.category_name
            FROM mri_publication_categories pc
            INNER JOIN mri_publications p ON pc.publication_id = p.publication_id AND p.run_id = ?
            LEFT JOIN mri_categories cat ON pc.category_id = cat.category_id
            WHERE pc.status = 'ACTIVE'
        """
        cat_rows = cur.execute(cat_lookup_query, (run_id,)).fetchall()
        
        hist_cat_rows = []
        if has_hist_pub_cat:
            hist_cat_query = """
                SELECT hpc.publication_id, hpc.category_id, cat.category_name
                FROM mri_historical_publication_categories hpc
                INNER JOIN mri_historical_publications hp ON hpc.publication_id = hp.publication_id AND hpc.run_id = hp.run_id
                LEFT JOIN mri_categories cat ON hpc.category_id = cat.category_id
                WHERE hpc.run_id = ?
            """
            hist_cat_rows = cur.execute(hist_cat_query, (run_id,)).fetchall()

        # Combine categories per publication
        run_categories_by_pub: Dict[str, List[Dict[str, str]]] = {}
        for row_c in list(cat_rows) + list(hist_cat_rows):
            p_id = row_c["publication_id"]
            if p_id not in run_categories_by_pub:
                run_categories_by_pub[p_id] = []
            c_id = row_c["category_id"]
            c_name = row_c["category_name"] or c_id
            # Clean PARIS_ prefix if present for group_id
            raw_gid = c_id.removeprefix("PARIS_") if c_id.startswith("PARIS_") else c_id
            if not any(existing_c["group_id"] == raw_gid for existing_c in run_categories_by_pub[p_id]):
                run_categories_by_pub[p_id].append({
                    "group_id": raw_gid,
                    "name": c_name,
                    "category_id": c_id
                })

        params = (run_id, run_id) if has_hist_pubs else (run_id,)
        rows = cur.execute(query, params).fetchall()
        
        results = []
        for r in rows:
            mkt = r["marketplace"] or "UNKNOWN"
            sku = r["marketplace_product_id"] or r["publication_id"] or "UNKNOWN"
            pub_id = r["publication_id"]
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

            # Observed category: prioritize explicit column, then run-scoped joined category
            pub_run_cats = run_categories_by_pub.get(pub_id, [])
            primary_run_cat_name = pub_run_cats[0]["name"] if pub_run_cats else None

            obs_cat = r["category_observed"] or primary_run_cat_name or r["legacy_cat_name"] or "NO_VERIFICADO"
            if obs_cat in ("NONE", "CATEGORY_UNKNOWN", ""):
                obs_cat = "NO_VERIFICADO"
                
            cat_source = r["category_source"] or ("PUBLIC_CHANNEL_BREADCRUMBS" if primary_run_cat_name or r["legacy_cat_name"] else "NO_VERIFICADO")
            
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
                if ident_st == "IDENTITY_NOT_LINKED" or not parent_sku:
                    cat_reason = f"Publicación observada en marketplace ({cat_dec}). Sin correspondencia unívoca verificada en catálogo maestro."
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

            # Primary HAR Provenance formatting in evidence
            raw_src = r["raw_source_id"] or ""
            har_sha = attrs.get("source_file_sha256") if isinstance(attrs, dict) else None
            har_path = attrs.get("source_file_path") if isinstance(attrs, dict) else None
            har_dt = attrs.get("source_captured_at") if isinstance(attrs, dict) else None

            if har_sha and not raw_src.startswith("PROVENANCE_INCOMPLETE"):
                ev_list.append(f"HAR SHA-256: {har_sha} | Ruta: {har_path or 'paris_search_capture.har'} | Captura: {har_dt or 'DECLARADA'}")
            elif raw_src.startswith("PROVENANCE_INCOMPLETE"):
                ev_list.append(f"Procedencia HAR: PROVENANCE_INCOMPLETE ({raw_src})")
                
            motivo = f"Publicación observada en canal comercial {mkt}. {cat_reason}"
            
            # Coverage calculation: preserve PAGE_BUDGET_EXCEEDED and partial limits
            if run_terminal_state == "PAGE_BUDGET_EXCEEDED":
                cov_val = "PAGE_BUDGET_EXCEEDED"
            elif (url and obs_cat != "NO_VERIFICADO" and ident_st in ("TARGET_IDENTITY_VERIFIED", "PARENT_IDENTITY_VERIFIED")):
                cov_val = "COMPLETE"
            else:
                cov_val = "PARTIAL"

            results.append({
                "publication_id": pub_id,
                "producto_id": sku,
                "sku": sku,
                "marketplace_product_id": sku,
                "producto_nombre": title,
                "marketplace": mkt,
                "canonical_url": url,
                "url_encontrada": url,
                "url": url,
                "fecha_observacion": r["observed_at"] or "NO_VERIFICADO",
                "timestamp": r["observed_at"] or "NO_VERIFICADO",
                "evidencia_identidad": ev_list if ev_list else ["NO_VERIFICADO"],
                "evidence": ev_list if ev_list else ["NO_VERIFICADO"],
                "evidence_type": r["evidence_type"] or "LIVE_OBSERVATION",
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
                "categories_observed": (
                    ((attrs.get("observed_attributes") or {}).get("categories_observed"))
                    or attrs.get("categories_observed")
                    or ([obs_cat] if obs_cat and obs_cat != "NO_VERIFICADO" else [])),
                "expected_category": exp_cat,
                "real_subcategory": "NO_VERIFICADO",
                "category_source": cat_source,
                "categories": pub_run_cats,
                "decision": cat_dec,
                "source": "PAGINATED_ADAPTER_HARVEST",
                "observed_sku": sku,
                "commercial_attributes": attrs
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
    Ensures runs with zero publications are preserved and visible.
    """
    history_items = []
    seen_runs = set()
    
    effective_db = DB_PATH
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        effective_db = StorageConfig.get_sqlite_path()
    except Exception:
        pass

    if Path(effective_db).exists():
        conn = get_sqlite_conn(str(effective_db))
        try:
            cur = conn.cursor()
            # Runs starting from mri_runs so empty/blocked runs are never lost
            has_mri_runs = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mri_runs'").fetchone()
            has_mri_pubs = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mri_publications'").fetchone()
            has_hist_pubs = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mri_historical_publications'").fetchone()

            union_parts = []
            if has_mri_pubs:
                union_parts.append("SELECT run_id, observed_at, marketplace, publication_id, status FROM mri_publications")
            if has_hist_pubs:
                union_parts.append("SELECT run_id, observed_at, marketplace, publication_id, status FROM mri_historical_publications")

            if not union_parts:
                union_sql = "SELECT NULL as run_id, NULL as observed_at, NULL as marketplace, NULL as publication_id, NULL as status WHERE 1=0"
            else:
                union_sql = " UNION ALL ".join(union_parts)

            if has_mri_runs:
                query = f"""
                    WITH all_pubs AS (
                        {union_sql}
                    )
                    SELECT 
                        r.run_id,
                        COALESCE(r.started_at, MIN(p.observed_at)) as started_at,
                        r.marketplace,
                        COUNT(p.publication_id) as total,
                        SUM(CASE WHEN p.status IN ('OBSERVED', 'CONFIRMED', 'NICOPOLY_CONFIRMED') THEN 1 ELSE 0 END) as confirmed,
                        COALESCE(r.execution_mode, 'SQLITE_PERSISTED') as mode,
                        r.terminal_state as terminal_state,
                        r.status as run_status,
                        r.source_method as source_method
                    FROM mri_runs r
                    LEFT JOIN all_pubs p ON r.run_id = p.run_id
                    GROUP BY r.run_id
                    ORDER BY started_at DESC
                """
            elif has_mri_pubs or has_hist_pubs:
                query = f"""
                    WITH all_pubs AS (
                        {union_sql}
                    )
                    SELECT 
                        p.run_id,
                        MIN(p.observed_at) as started_at,
                        p.marketplace,
                        COUNT(p.publication_id) as total,
                        SUM(CASE WHEN p.status IN ('OBSERVED', 'CONFIRMED', 'NICOPOLY_CONFIRMED') THEN 1 ELSE 0 END) as confirmed,
                        'SQLITE_PERSISTED' as mode
                    FROM all_pubs p
                    GROUP BY p.run_id
                    ORDER BY started_at DESC
                """
            else:
                query = None

            if query:
                for r in cur.execute(query).fetchall():
                    run_id = r["run_id"]
                    seen_runs.add(run_id)
                    keys = r.keys()
                    terminal = r["terminal_state"] if "terminal_state" in keys else None
                    run_status = r["run_status"] if "run_status" in keys else None
                    source_method = r["source_method"] if "source_method" in keys else None
                    outcome = (terminal or run_status or "").upper() or None
                    history_items.append({
                        "run_id": run_id,
                        "timestamp": r["started_at"] or "2026-10-14T00:00:00",
                        "marketplace": r["marketplace"] if r["marketplace"] else "MULTI_MARKETPLACE",
                        "total": r["total"] or 0,
                        "confirmed": r["confirmed"] or 0,
                        "mode": r["mode"],
                        "engine": r["mode"],
                        "source_method": source_method,
                        "terminal_state": terminal,
                        "outcome": outcome,
                        # Historical query: never presented as a new acquisition.
                        "view_kind": "PERSISTED_VIEW",
                        "live": False,
                        "is_new_acquisition": False,
                        "source": "OPERATIONAL"
                    })
        finally:
            conn.close()
            
    # Also include any orchestrator history not yet in SQLite
    for h in orchestrator.history:
        r_id = h.get("run_id")
        if r_id and r_id not in seen_runs:
            seen_runs.add(r_id)
            item = dict(h)
            _live = bool(orchestrator.is_running and r_id == (orchestrator.state or {}).get("run_id"))
            item.setdefault("source", "LIVE_MEMORY" if _live else "PERSISTED_JSON")
            item["view_kind"] = "LIVE_MEMORY" if _live else "PERSISTED_VIEW"
            item["live"] = _live
            item["is_new_acquisition"] = _live
            item.setdefault("outcome", item.get("outcome") or item.get("terminal_state"))
            item.setdefault("engine", item.get("engine") or item.get("mode") or "DISCOVERY")
            history_items.append(item)
            
    # Add PROTECTED (production) runs that are not already listed. Read-only.
    for item in _protected_runs():
        if item["run_id"] not in seen_runs:
            seen_runs.add(item["run_id"])
            history_items.append(item)

    return JSONResponse(content={
        "history": history_items,
        "catalog_reference": _safe_catalog_reference(),
        "sources": {
            "operational": str(_operational_db_path()),
            "protected": str(_protected_db_path()) if _protected_db_path() else None,
        },
    })


def _safe_catalog_reference() -> dict:
    """Reference-catalog status, surfaced as an explicit limitation."""
    try:
        from app.mri_dashboard.acquisition_contract import catalog_reference_status
        return catalog_reference_status()
    except Exception as exc:
        return {"status": "UNKNOWN", "error": str(exc)}


def _identity_summary_from_publications(pubs) -> dict:
    """Counts by commercial-identity state; unknown is NEVER counted as official."""
    counts = {
        "records": 0, "unique_marketplace_ids": 0,
        "OFFICIAL_VERIFIED": 0, "THIRD_PARTY_NEW": 0,
        "THIRD_PARTY_USED": 0, "SELLER_UNVERIFIED": 0,
        "official_kpi_eligible": 0, "excluded_from_official_kpi": 0,
    }
    skus = set()
    for p in pubs or []:
        if not isinstance(p, dict):
            continue
        counts["records"] += 1
        sku = p.get("marketplace_product_id") or p.get("publication_id")
        if sku:
            skus.add(sku)
        attrs = p.get("commercial_attributes")
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except Exception:
                attrs = None
        identity = attrs.get("commercial_identity") if isinstance(attrs, dict) else None
        state = (identity or {}).get("state")
        if state in ("OFFICIAL_VERIFIED", "THIRD_PARTY_NEW", "THIRD_PARTY_USED"):
            counts[state] += 1
        else:
            # Missing/unverified identity can never feed the official KPI.
            counts["SELLER_UNVERIFIED"] += 1
        if state == "OFFICIAL_VERIFIED" and (identity or {}).get("condition") != "USED":
            counts["official_kpi_eligible"] += 1
        else:
            counts["excluded_from_official_kpi"] += 1
    counts["unique_marketplace_ids"] = len(skus)
    return counts


def _persisted_run_meta(run_id: str) -> dict:
    """Engine/terminal state of a persisted run: what ACTUALLY executed.

    Never claims a new acquisition: the caller is a historical query.
    """
    from app.mri_dashboard.acquisition_contract import view_metadata
    meta = {"execution_mode": None, "terminal_state": None, "run_status": None,
            "source_method": None, "run_marketplace": None}
    for db in (_operational_db_path(), _protected_db_path()):
        if db is None or not Path(db).exists():
            continue
        try:
            conn = _connect_ro(db)
        except Exception:
            continue
        try:
            row = conn.execute(
                "SELECT execution_mode, terminal_state, status, source_method, marketplace "
                "FROM mri_runs WHERE run_id = ?", (run_id,)).fetchone()
        except Exception:
            row = None
        finally:
            conn.close()
        if row:
            keys = row.keys() if hasattr(row, "keys") else []
            meta["execution_mode"] = row["execution_mode"] if "execution_mode" in keys else None
            meta["terminal_state"] = row["terminal_state"] if "terminal_state" in keys else None
            meta["run_status"] = row["status"] if "status" in keys else None
            meta["source_method"] = row["source_method"] if "source_method" in keys else None
            meta["run_marketplace"] = row["marketplace"] if "marketplace" in keys else None
            break
    out = view_metadata(execution_mode=meta["execution_mode"],
                        run_id=run_id, source="PERSISTED_VIEW", live=False)
    out.update({
        "engine": meta["execution_mode"] or "UNKNOWN",
        "terminal_state": meta["terminal_state"],
        "outcome": (meta["terminal_state"] or meta["run_status"] or "").upper() or None,
        "source_method": meta["source_method"],
    })
    return out


def _falabella_audit_metrics(run_id: str) -> Dict[str, Any]:
    """Marketplace-specific reconciliation metrics persisted with the run."""
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        hist = Path(StorageConfig.get_aux_dir()) / "mri_history.json"
        for entry in json.loads(hist.read_text(encoding="utf-8")):
            if entry.get("run_id") == run_id:
                audit = entry.get("falabella_ssr_audit") or {}
                if audit:
                    return {"catalog_summary": audit.get("catalog_summary"),
                            "category_metrics": audit.get("category_metrics")}
    except Exception:
        pass
    return {}


@app.post("/api/checklist/import")
async def import_season_checklist(request: Request):
    """Import the season CHECKLIST strictly as validation reference."""
    import asyncio
    from app.mri_dashboard.checklist_reference import find_checklist, load_checklist
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    requested = payload.get("path") if isinstance(payload, dict) else None

    def _load():
        path = Path(requested) if requested else find_checklist()
        if not path or not path.exists():
            return None
        return load_checklist(path, use_cache=False)

    data = await asyncio.to_thread(_load)
    if not data:
        raise HTTPException(status_code=404, detail="CHECKLIST no encontrado")
    per_channel = {ch: 0 for ch in ("falabella", "ripley", "paris", "mercado libre")}
    for prod in data.get("products") or []:
        for ch, val in (prod.get("channels") or {}).items():
            if val.get("product_id") or val.get("link"):
                per_channel[ch] = per_channel.get(ch, 0) + 1
    return JSONResponse(content={"status": "LOADED", "source": data.get("source"),
                                 "products": len(data.get("products") or []),
                                 "per_channel": per_channel,
                                 "authority": "VALIDATION_ONLY"})


@app.get("/api/preflight")
async def get_execution_preflight(check_auth: bool = True):
    import asyncio
    from app.mri_autonomous.execution_preflight import run_preflight
    report = await asyncio.to_thread(run_preflight, check_auth=check_auth)
    return JSONResponse(content=report)


@app.post("/api/checklist/upload")
async def upload_season_checklist(request: Request):
    """Upload the season CHECKLIST (validation-only; never feeds acquisition)."""
    import asyncio
    import os
    import shutil
    from datetime import datetime
    from app.mri_dashboard.checklist_reference import upload_path, load_checklist
    filename = request.headers.get("x-filename", "checklist.xlsx")
    suffix = Path(filename).suffix.lower()
    if suffix not in (".xlsx", ".xls", ".csv"):
        raise HTTPException(status_code=400, detail="Formato no soportado (.xlsx/.xls/.csv)")
    body = await request.body()
    if not body or len(body) > 350 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Archivo vacío o mayor a 350 MB")
    target = upload_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = target.parent / "catalog_backups"
    backup_dir.mkdir(exist_ok=True)
    if target.exists():
        shutil.copy2(target, backup_dir / (
            f"checklist_{datetime.now().strftime('%Y%m%dT%H%M%S')}{target.suffix}"))
    tmp = target.with_suffix(target.suffix + ".upload.tmp")
    tmp.write_bytes(body)
    os.replace(tmp, target)
    data = await asyncio.to_thread(load_checklist, target, use_cache=False)
    if not data:
        raise HTTPException(status_code=422, detail="El checklist no pudo interpretarse")
    per_channel = {}
    for prod in data.get("products") or []:
        for ch, val in (prod.get("channels") or {}).items():
            if val.get("product_id") or val.get("link"):
                per_channel[ch] = per_channel.get(ch, 0) + 1
    return JSONResponse(content={"status": "LOADED", "filename": filename,
                                 "bytes": len(body),
                                 "products": len(data.get("products") or []),
                                 "per_channel": per_channel,
                                 "authority": "VALIDATION_ONLY",
                                 "path": str(target)})


@app.get("/api/checklist/coverage")
async def season_checklist_coverage(marketplace: str, run_id: Optional[str] = None):
    """Season checklist vs observed (validation only; never feeds acquisition)."""
    import asyncio
    from app.mri_dashboard.checklist_reference import find_checklist, load_checklist, build_checklist_report
    path = find_checklist()
    if not path:
        raise HTTPException(status_code=404, detail="CHECKLIST no encontrado")
    names = {"falabella": "Falabella", "ripley": "Ripley",
             "mercado libre": "Mercado Libre", "paris": "Paris"}
    key = marketplace.lower()
    if key not in names:
        raise HTTPException(status_code=400, detail="marketplace no soportado")
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        db_path = str(StorageConfig.get_sqlite_path())
    except Exception:
        db_path = str(DB_PATH)
    conn = get_sqlite_conn(db_path)
    try:
        cur = conn.cursor()
        if run_id:
            row = cur.execute("SELECT run_id, terminal_state, status FROM mri_runs WHERE run_id = ?",
                              (run_id,)).fetchone()
        else:
            row = cur.execute("SELECT run_id, terminal_state, status FROM mri_runs "
                              "WHERE marketplace = ? ORDER BY rowid DESC LIMIT 1",
                              (names[key],)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No hay corrida para ese marketplace")
    rid = row["run_id"]
    complete = (row["terminal_state"] or row["status"] or "").upper() in (
        "FOUND", "COMPLETED", "SUCCESS")
    if key == "falabella":
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            hist = Path(StorageConfig.get_aux_dir()) / "mri_history.json"
            for entry in json.loads(hist.read_text(encoding="utf-8")):
                if entry.get("run_id") == rid:
                    complete = bool((entry.get("falabella_ssr_audit") or {}).get("complete"))
                    break
        except Exception:
            complete = False
    pubs = await asyncio.to_thread(fetch_run_publications, rid, db_path=db_path)
    report = await asyncio.to_thread(build_checklist_report, load_checklist(path),
                                     names[key], pubs, run_id=rid,
                                     run_complete=complete)
    return JSONResponse(content=report)


@app.get("/api/catalog/coverage")
async def master_coverage(marketplace: str, run_id: Optional[str] = None):
    """Published vs missing against the uploaded master (per marketplace)."""
    from app.loaders.multivende_loader import get_multivende_loader
    from app.mri_dashboard.publication_coverage import build_report
    loader = get_multivende_loader()
    if not loader.reference_available:
        raise HTTPException(status_code=422,
                            detail="CATALOG_REFERENCE_MISSING: suba el catálogo maestro")
    names = {"falabella": "Falabella", "ripley": "Ripley",
             "mercado libre": "Mercado Libre", "paris": "Paris"}
    key = marketplace.lower()
    if key not in names:
        raise HTTPException(status_code=400, detail="marketplace no soportado")
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        db_path = str(StorageConfig.get_sqlite_path())
    except Exception:
        db_path = str(DB_PATH)
    conn = get_sqlite_conn(db_path)
    try:
        cur = conn.cursor()
        if run_id:
            row = cur.execute("SELECT run_id, terminal_state, status FROM mri_runs WHERE run_id = ?",
                              (run_id,)).fetchone()
        else:
            row = cur.execute("SELECT run_id, terminal_state, status FROM mri_runs "
                              "WHERE marketplace = ? ORDER BY rowid DESC LIMIT 1",
                              (names[key],)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No hay corrida para ese marketplace")
    rid = row["run_id"]
    terminal = (row["terminal_state"] or row["status"] or "").upper()
    complete = terminal in ("FOUND", "COMPLETED", "SUCCESS")
    if key == "falabella":
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            hist = Path(StorageConfig.get_aux_dir()) / "mri_history.json"
            for entry in json.loads(hist.read_text(encoding="utf-8")):
                if entry.get("run_id") == rid:
                    complete = bool((entry.get("falabella_ssr_audit") or {}).get("complete"))
                    break
        except Exception:
            complete = False
    # Coverage is CPU/IO heavy (master index + matching): never block the
    # event loop, or /api/state freezes while the operator checks coverage.
    import asyncio
    pubs = await asyncio.to_thread(fetch_run_publications, rid, db_path=db_path)
    try:
        from app.mri_dashboard.checklist_reference import find_checklist, load_checklist
        _checklist_path = find_checklist()
        checklist = (await asyncio.to_thread(load_checklist, _checklist_path)
                     if _checklist_path else None)
    except Exception:
        checklist = None
    report = await asyncio.to_thread(
        build_report, names[key], pubs, loader._master_items,
        run_id=rid, run_complete=complete, checklist=checklist)
    return JSONResponse(content=report)


@app.post("/api/catalog/upload")
async def upload_master_catalog(request: Request):
    """Operator upload of the reference catalog (xlsx/csv). Stock 0 = discard."""
    if getattr(orchestrator, "is_running", False):
        raise HTTPException(status_code=409,
                            detail="No se puede reemplazar el catálogo con una auditoría en curso")
    filename = request.headers.get("x-filename", "catalogo.xlsx")
    suffix = Path(filename).suffix.lower()
    if suffix not in (".xlsx", ".xls", ".csv"):
        raise HTTPException(status_code=400, detail="Formato no soportado (.xlsx/.xls/.csv)")
    body = await request.body()
    if not body or len(body) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Archivo vacío o mayor a 25 MB")
    import os
    import shutil
    from datetime import datetime
    from app.config.settings import MULTIVENDE_EXCEL_PATH
    from app.loaders.multivende_loader import get_multivende_loader
    target = Path(MULTIVENDE_EXCEL_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        backup_dir = Path(StorageConfig.get_aux_dir()) / "catalog_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.copy2(target, backup_dir / (
                f"master_{datetime.now().strftime('%Y%m%dT%H%M%S')}{target.suffix}"))
    except Exception:
        pass
    tmp = target.with_suffix(target.suffix + ".upload.tmp")
    tmp.write_bytes(body)
    os.replace(tmp, target)
    loader = get_multivende_loader()
    if not loader.reload():
        raise HTTPException(status_code=422,
                            detail="El archivo no pudo cargarse como catálogo maestro")
    channels = {}
    for mkt in ("falabella", "ripley", "mercado libre", "paris"):
        r = loader.expected_for_channel(mkt)
        channels[mkt] = {k: r.get(k) for k in
                         ("expected", "discarded_no_stock",
                          "unverified_stock", "not_expected")}
    return JSONResponse(content={
        "status": "LOADED", "filename": filename, "bytes": len(body),
        "reference_available": loader.reference_available,
        "master_items": len(loader._master_items),
        "stock_rule": "stock 0 => DESCARTADO_SIN_STOCK",
        "channels": channels,
    })


@app.get("/api/history/{run_id}")
async def get_history_run_publications(run_id: str):
    """
    Retrieves verifiable publication details for any historical run without re-harvesting.
    If a run exists in SQLite but has 0 publications (e.g. blocked or empty run),
    returns 200 with empty publications list instead of 404.
    """
    effective_db = DB_PATH
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        effective_db = StorageConfig.get_sqlite_path()
    except Exception:
        pass

    # 1. Check the OPERATIONAL database (new audits)
    pubs = fetch_run_publications(run_id, db_path=str(effective_db))
    if pubs:
        return JSONResponse(content={"run_id": run_id, "publications": pubs,
                                     "count": len(pubs), "source": "OPERATIONAL",
                                     **_persisted_run_meta(run_id),
                                     **_falabella_audit_metrics(run_id),
                                     "identity_summary": _identity_summary_from_publications(pubs)})

    # 1b. Fall back to the PROTECTED database, strictly read-only
    protected = _protected_db_path()
    if protected is not None:
        try:
            pubs_p = fetch_run_publications(run_id, db_path=str(protected))
        except Exception:
            pubs_p = []
        if pubs_p:
            return JSONResponse(content={"run_id": run_id, "publications": pubs_p,
                                         "count": len(pubs_p), "source": "PROTECTED",
                                         **_persisted_run_meta(run_id),
                                         **_falabella_audit_metrics(run_id),
                                         "identity_summary": _identity_summary_from_publications(pubs_p)})

    # Check if run exists in mri_runs with 0 publications
    if Path(effective_db).exists():
        conn = get_sqlite_conn(str(effective_db))
        try:
            cur = conn.cursor()
            has_mri_runs = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mri_runs'").fetchone()
            if has_mri_runs:
                run_row = cur.execute("SELECT run_id, terminal_state, status FROM mri_runs WHERE run_id = ?", (run_id,)).fetchone()
                if run_row:
                    return JSONResponse(content={
                        "run_id": run_id,
                        "publications": [],
                        "count": 0,
                        "source": "SQLITE_EMPTY_RUN",
                        "status": run_row["terminal_state"] or run_row["status"] or "COMPLETED",
                        **_persisted_run_meta(run_id),
                        "identity_summary": _identity_summary_from_publications([]),
                    })
        except Exception:
            pass
        finally:
            conn.close()
    
    # 2. Check orchestrator history
    for h in orchestrator.history:
        if h.get("run_id") == run_id:
            _results = h.get("results", []) or []
            return JSONResponse(content={
                "run_id": run_id, "publications": _results, "count": len(_results),
                "source": "ORCHESTRATOR_MEMORY",
                "engine": h.get("engine") or h.get("mode"),
                "outcome": h.get("outcome") or h.get("terminal_state"),
                "view_kind": "PERSISTED_VIEW", "live": False,
                "is_new_acquisition": False,
                "identity_summary": _identity_summary_from_publications(_results),
            })
            
    return JSONResponse(status_code=404, content={"message": f"Run {run_id} not found", "run_id": run_id, "publications": []})


def _readonly_experience_connection():
    """
    READ-ONLY connection to the learning store.

    Reading must never request write authorization on the protected database.
    Previously this endpoint opened the store for writing, so the storage
    barrier raised ProductionWriteBlockedError and the endpoint returned 500.
    Returns None when the database does not exist yet.
    """
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        path = Path(StorageConfig.get_experience_db_path())
        if not path.exists():
            return None
        return StorageConfig.connect_sqlite(path, mode="ro")
    except Exception:
        return None


@app.get("/api/learning")
async def get_learning():
    """
    Returns real experiences, strategies, and re-audit recovery records (read-only).
    """
    conn = _readonly_experience_connection()
    if conn is None:
        return JSONResponse(content={
            "experiences": [],
            "total_validated": 0,
            "total_reused": 0,
            "recovery_experiences": [],
            "source": "EXPERIENCE_DB_ABSENT",
        })
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
async def get_rea_paris_data(run_id: Optional[str] = None):
    """
    Returns normalized Paris commercial intelligence discovered via REA engine:
    - Queries SQLite visibility.db scoped to run_id (or latest run)
    - Reconstructs Brand vs Official Seller breakdown from persisted data
    - Differentiates incomplete/empty evidence from operational truth
    - Operates 100% offline without forcing network requests
    """
    effective_db = DB_PATH
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        effective_db = StorageConfig.get_sqlite_path()
    except Exception:
        pass

    target_run_id = run_id
    rows = []
    cat_rows = []
    try:
        conn = get_sqlite_conn(str(effective_db))
        try:
            cur = conn.cursor()
            if not target_run_id:
                try:
                    r_row = cur.execute("""
                        SELECT run_id FROM mri_runs WHERE marketplace = 'Paris' OR marketplace = 'MULTI_MARKETPLACE'
                        ORDER BY started_at DESC LIMIT 1
                    """).fetchone()
                    if r_row:
                        target_run_id = r_row["run_id"]
                except sqlite3.OperationalError:
                    pass

            # Check persisted Paris publications scoped to target_run_id
            if target_run_id:
                try:
                    rows = cur.execute("""
                        SELECT publication_id, marketplace_product_id, commercial_attributes, category_observed
                        FROM mri_publications
                        WHERE marketplace = 'Paris' AND run_id = ?
                    """, (target_run_id,)).fetchall()
                except sqlite3.OperationalError:
                    rows = []

                if not rows:
                    try:
                        rows = cur.execute("""
                            SELECT publication_id, marketplace_product_id, commercial_attributes, category_observed
                            FROM mri_historical_publications
                            WHERE marketplace = 'Paris' AND run_id = ?
                        """, (target_run_id,)).fetchall()
                    except sqlite3.OperationalError:
                        rows = []

                try:
                    cat_rows = cur.execute("""
                        SELECT DISTINCT c.category_id, c.category_name, c.canonical_url
                        FROM mri_categories c
                        JOIN mri_publication_categories pc ON c.category_id = pc.category_id
                        JOIN mri_publications p ON pc.publication_id = p.publication_id
                        WHERE p.marketplace = 'Paris' AND p.run_id = ?
                    """, (target_run_id,)).fetchall()
                    if not cat_rows:
                        cat_rows = cur.execute("""
                            SELECT DISTINCT c.category_id, c.category_name, c.canonical_url
                            FROM mri_categories c
                            JOIN mri_historical_publication_categories hpc ON c.category_id = hpc.category_id
                            WHERE hpc.run_id = ?
                        """, (target_run_id,)).fetchall()
                except sqlite3.OperationalError:
                    cat_rows = []
            else:
                try:
                    rows = cur.execute("""
                        SELECT publication_id, marketplace_product_id, commercial_attributes, category_observed
                        FROM mri_publications
                        WHERE marketplace = 'Paris'
                    """).fetchall()
                except sqlite3.OperationalError:
                    rows = []
                try:
                    cat_rows = cur.execute("""
                        SELECT category_id, category_name, canonical_url
                        FROM mri_categories
                        WHERE marketplace = 'Paris'
                    """).fetchall()
                except sqlite3.OperationalError:
                    cat_rows = []
        finally:
            conn.close()
    except Exception:
        rows = []
        cat_rows = []

    # If data is persisted in SQLite, serve it directly
    if rows:
        official_seller_count = 0
        all_sellers = set()
        promotions_found = set()
        for r in rows:
            attrs = {}
            try:
                attrs = json.loads(r["commercial_attributes"] or "{}")
            except Exception:
                pass
            sellers = attrs.get("sellers", [])
            for s in sellers:
                all_sellers.add(s)
            if attrs.get("is_official_seller") or any("nicopoly" in s.lower() for s in sellers):
                official_seller_count += 1
            for p in attrs.get("promotions", []):
                promotions_found.add(p)

        total_pubs = len(rows)
        other_sellers = max(0, total_pubs - official_seller_count)

        return JSONResponse(content={
            "marketplace": "Paris",
            "brand": "Nicopoly",
            "total_brand": total_pubs,
            "official_seller": "NICOPOLY",
            "total_official_seller": official_seller_count,
            "other_sellers_total": other_sellers,
            "categories_persisted_count": len(cat_rows),
            "promotions_observed": list(promotions_found),
            "storage_source": "SQLITE_MRI_PERSISTENCE",
            "discovery_engine": "Constructor.io AI Search",
            "status": "OPERATIONAL"
        })

    # If no persisted Paris data in current DB, try querying engine safely if allowed
    try:
        from app.mri_autonomous.rea_paris_engine import REAParisEngine
        engine = REAParisEngine()
        brand_summary = engine.get_brand_summary("Nicopoly")
        seller_summary = engine.get_seller_summary("NICOPOLY")
        tot_b = brand_summary.get("total_brand_results")
        tot_s = seller_summary.get("total_seller_results")

        # Explicitly represent UNKNOWN/null when source does not deliver verifiable results
        if tot_b is None or tot_s is None or (tot_b == 0 and tot_s == 0 and not brand_summary.get("product_types")):
            # If both are verified numbers (e.g., explicit 0), distinguish from None/unverifiable
            if tot_b is None and tot_s is None:
                return JSONResponse(content={
                    "marketplace": "Paris",
                    "brand": "Nicopoly",
                    "total_brand": None,
                    "total_official_seller": None,
                    "other_sellers_total": None,
                    "status": "NO_EVIDENCE_RECORDED",
                    "reason": "Sin datos persistidos en almacenamiento ni respuesta de red válida"
                })
            elif tot_b == 0 and tot_s == 0:
                # Valid response certifying 0 results
                return JSONResponse(content={
                    "marketplace": "Paris",
                    "brand": "Nicopoly",
                    "total_brand": 0,
                    "total_official_seller": 0,
                    "other_sellers_total": 0,
                    "status": "NO_EVIDENCE_RECORDED",
                    "reason": "Respuesta válida certifica cero resultados comerciales"
                })

        return JSONResponse(content={
            "marketplace": "Paris",
            "brand": "Nicopoly",
            "total_brand": tot_b,
            "official_seller": "NICOPOLY",
            "total_official_seller": tot_s,
            "other_sellers_total": max(0, tot_b - tot_s) if (tot_b is not None and tot_s is not None) else None,
            "facets": brand_summary.get("facets_available", []),
            "product_types": brand_summary.get("product_types", []),
            "storage_source": "LIVE_REA_ENGINE",
            "discovery_engine": "Constructor.io AI Search",
            "status": "OPERATIONAL"
        })
    except Exception:
        # When offline and no records yet, return clear NO_EVIDENCE state with null totals instead of fake zeros
        return JSONResponse(content={
            "marketplace": "Paris",
            "brand": "Nicopoly",
            "total_brand": None,
            "total_official_seller": None,
            "other_sellers_total": None,
            "status": "OFFLINE_NO_PERSISTED_RECORDS",
            "message": "No hay registros persistidos de Paris en almacenamiento y la red está aislada."
        })


@app.get("/api/falabella/nicopoly")
async def get_falabella_nicopoly_data(run_id: Optional[str] = None):
    """
    Returns normalized Falabella commercial intelligence dynamically scoped to run_id (or latest run):
    - Reads publications and categories from SQLite
    - If run does not exist or has 0 publications, returns unacquired state without hardcoded figures
    - Status: OPERATIONAL if publications acquired, otherwise verified unacquired terminal state
    """
    effective_db = DB_PATH
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        effective_db = StorageConfig.get_sqlite_path()
    except Exception:
        pass

    target_run_id = run_id
    target_terminal_state = None
    rows = []
    cat_rows = []

    if Path(effective_db).exists():
        conn = get_sqlite_conn(str(effective_db))
        try:
            cur = conn.cursor()
            if not target_run_id:
                try:
                    s_row = cur.execute("""
                        SELECT run_id, terminal_state, status
                        FROM mri_run_marketplace_states
                        WHERE marketplace = 'Falabella'
                        ORDER BY rowid DESC LIMIT 1
                    """).fetchone()
                    if s_row:
                        target_run_id = s_row["run_id"]
                        target_terminal_state = s_row["terminal_state"] or s_row["status"]
                except sqlite3.OperationalError:
                    s_row = None

                if not target_run_id:
                    try:
                        r_row = cur.execute("""
                            SELECT run_id, terminal_state, status
                            FROM mri_runs
                            WHERE marketplace = 'Falabella'
                            ORDER BY rowid DESC LIMIT 1
                        """).fetchone()
                        if r_row:
                            target_run_id = r_row["run_id"]
                            target_terminal_state = r_row["terminal_state"] or r_row["status"]
                        else:
                            # Check publications directly for MULTI_MARKETPLACE runs
                            p_row = cur.execute("""
                                SELECT run_id FROM mri_publications
                                WHERE marketplace = 'Falabella' AND run_id IS NOT NULL
                                ORDER BY rowid DESC LIMIT 1
                            """).fetchone()
                            if p_row:
                                target_run_id = p_row["run_id"]
                                r_st = cur.execute("SELECT terminal_state, status FROM mri_runs WHERE run_id = ?", (target_run_id,)).fetchone()
                                if r_st:
                                    target_terminal_state = r_st["terminal_state"] or r_st["status"]
                    except sqlite3.OperationalError:
                        pass
            else:
                try:
                    s_row = cur.execute("""
                        SELECT terminal_state, status
                        FROM mri_run_marketplace_states
                        WHERE run_id = ? AND marketplace = 'Falabella'
                    """, (target_run_id,)).fetchone()
                    if s_row:
                        target_terminal_state = s_row["terminal_state"] or s_row["status"]
                    else:
                        r_row = cur.execute("""
                            SELECT terminal_state, status
                            FROM mri_runs
                            WHERE run_id = ?
                        """, (target_run_id,)).fetchone()
                        if r_row:
                            target_terminal_state = r_row["terminal_state"] or r_row["status"]
                except sqlite3.OperationalError:
                    pass

            if target_run_id:
                try:
                    rows = cur.execute("""
                        SELECT publication_id, marketplace_product_id, commercial_attributes, category_observed
                        FROM mri_publications
                        WHERE marketplace = 'Falabella' AND run_id = ?
                    """, (target_run_id,)).fetchall()
                except sqlite3.OperationalError:
                    rows = []

                if not rows:
                    try:
                        rows = cur.execute("""
                            SELECT publication_id, marketplace_product_id, commercial_attributes, category_observed
                            FROM mri_historical_publications
                            WHERE marketplace = 'Falabella' AND run_id = ?
                        """, (target_run_id,)).fetchall()
                    except sqlite3.OperationalError:
                        rows = []

                try:
                    cat_rows = cur.execute("""
                        SELECT DISTINCT c.category_id, c.category_name, c.canonical_url
                        FROM mri_categories c
                        JOIN mri_publication_categories pc ON c.category_id = pc.category_id
                        JOIN mri_publications p ON pc.publication_id = p.publication_id
                        WHERE p.marketplace = 'Falabella' AND p.run_id = ?
                    """, (target_run_id,)).fetchall()
                    if not cat_rows:
                        cat_rows = cur.execute("""
                            SELECT DISTINCT c.category_id, c.category_name, c.canonical_url
                            FROM mri_categories c
                            JOIN mri_historical_publication_categories hpc ON c.category_id = hpc.category_id
                            WHERE hpc.run_id = ?
                        """, (target_run_id,)).fetchall()
                except sqlite3.OperationalError:
                    cat_rows = []
        finally:
            conn.close()

    if rows:
        official_seller_count = 0
        cat_counts = {}
        for r in rows:
            attrs = {}
            try:
                attrs = json.loads(r["commercial_attributes"] or "{}")
            except Exception:
                pass
            sellers = attrs.get("sellers", [])
            if attrs.get("is_official_seller") or any("nicopoly" in str(s).lower() for s in sellers):
                official_seller_count += 1
            cat_obs = r["category_observed"] or "Moda Mujer"
            cat_counts[cat_obs] = cat_counts.get(cat_obs, 0) + 1

        total_pubs = len(rows)
        l2_subcategories = [
            {"id": c["category_id"], "name": c["category_name"], "count": cat_counts.get(c["category_name"], 1)}
            for c in cat_rows
        ] if cat_rows else [
            {"id": f"CAT_{k[:8]}", "name": k, "count": v} for k, v in cat_counts.items()
        ]
        return JSONResponse(content={
            "marketplace": "Falabella",
            "run_id": target_run_id,
            "brand": "NICOPOLY",
            "official_seller": "Nicopoly",
            "seller_id": "SC75ABC",
            "total_brand_publications": total_pubs,
            "total_seller_publications": official_seller_count,
            "brand_seller_identity_match": (total_pubs == official_seller_count),
            "l0_department": {"id": "cat7330051", "name": "Mujer", "count": total_pubs},
            "l1_subcategory": {"id": "cat20002", "name": "Moda Mujer", "count": total_pubs},
            "l2_subcategories": l2_subcategories,
            "total_l2_categories": len(l2_subcategories),
            "sum_l2_publications": total_pubs,
            "discovery_mechanism": "NEXT_JS_SSR_EXTRACTION",
            "storage_source": "SQLITE_MRI_PERSISTENCE",
            "status": "OPERATIONAL"
        })

    # When no verified records for target run
    unacquired_status = target_terminal_state or "NO_EVIDENCE_RECORDED"
    return JSONResponse(content={
        "marketplace": "Falabella",
        "run_id": target_run_id,
        "brand": "NICOPOLY",
        "official_seller": "Nicopoly",
        "seller_id": "SC75ABC",
        "total_brand_publications": 0,
        "total_seller_publications": 0,
        "brand_seller_identity_match": False,
        "l0_department": None,
        "l1_subcategory": None,
        "l2_subcategories": [],
        "total_l2_categories": 0,
        "sum_l2_publications": 0,
        "discovery_mechanism": "NEXT_JS_SSR_EXTRACTION",
        "storage_source": "NONE" if not target_run_id else "SQLITE_EMPTY_RUN",
        "status": unacquired_status,
        "message": f"Sin publicaciones verificadas de Falabella adquiridas en la corrida {target_run_id or 'actual'}."
    })


@app.get("/api/meli/nicopoly")
async def get_meli_nicopoly_data():
    """
    Returns normalized Mercado Libre commercial taxonomy discovered via official API:
    - Official store (56574) & Seller (386329223)
    - 14 Product categories discovered and separated from audiovisual Clips
    - OAuth status (AUTH_REQUIRED for protected listings, FOUND for official taxonomy)
    """
    try:
        from app.mri_autonomous.meli_taxonomy_engine import MeliTaxonomyEngine
        engine = MeliTaxonomyEngine()
        summary = engine.get_official_store_summary()
        return JSONResponse(content=summary)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/ripley/nicopoly")
async def get_ripley_nicopoly_data(run_id: Optional[str] = None):
    """
    Returns normalized Ripley commercial intelligence discovered via verified facets and catalog counter:
    - 3 reference categories (Sweaters y Chalecos, Chaquetas y Blazers, Pantalones)
    - Persisted brand publications strictly scoped to run_id (or latest run)
    - Status: OPERATIONAL if publications acquired, otherwise verified unacquired terminal state
    """
    try:
        from app.mri_autonomous.ripley_commercial_engine import RipleyCommercialEngine
        effective_db = DB_PATH
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            effective_db = StorageConfig.get_sqlite_path()
        except Exception:
            pass
        engine = RipleyCommercialEngine()
        return JSONResponse(content=engine.get_commercial_summary(db_path=str(effective_db), run_id=run_id))
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


def _comparative_marketplace_summary() -> dict:
    """COMPARATIVE view: latest verified run per marketplace, with provenance.

    Never merges or sums independent runs as if they were one joint audit. Each
    marketplace shows its own run_id, date, source and terminal state.
    """
    mkt_meta = {
        "Paris": "Constructor.io API / public key discovery",
        "Falabella": "Next.js SSR __NEXT_DATA__ (HTTP)",
        "Mercado Libre": "Official Corridor Scraper & Taxonomy Discovery",
        "Ripley": "Catalog Scraper & Facets Verification",
    }
    out = {m: {"mechanism": mech, "brand_publications": 0,
               "official_seller_publications": 0, "categories_count": 0,
               "status": "NOT_EXECUTED", "run_id": None, "run_date": None,
               "source": None} for m, mech in mkt_meta.items()}

    def scan(db_path, source):
        try:
            conn = _connect_ro(db_path)
        except Exception:
            return
        try:
            cur = conn.cursor()
            has_runs = cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mri_runs'"
            ).fetchone()
            if not has_runs:
                return
            for mkt in list(out.keys()):
                if out[mkt]["run_id"] is not None:
                    continue  # operational data wins over protected
                row = cur.execute(
                    "SELECT r.run_id, r.started_at, r.terminal_state, r.status, r.execution_mode "
                    "FROM mri_runs r "
                    "WHERE r.marketplace = ? "
                    "   OR EXISTS (SELECT 1 FROM mri_publications p "
                    "              WHERE p.run_id = r.run_id AND p.marketplace = ?) "
                    # Runs are inserted when they finish, so rowid is the only
                    # monotonic "latest" key: started_at mixes local naive and
                    # UTC offset strings, which text-sorts incorrectly.
                    "ORDER BY r.rowid DESC LIMIT 1", (mkt, mkt)).fetchone()
                if not row:
                    continue
                run_id, started, terminal, status, mode = row
                # Scope publications to THIS marketplace: discovery runs are
                # persisted with the neutral stamp MULTI_MARKETPLACE, so keying
                # only on mri_runs.marketplace made a real single-marketplace
                # run invisible (absence-of-execution presented as no data) and
                # would otherwise attribute foreign publications to this market.
                try:
                    pubs = cur.execute(
                        "SELECT marketplace_product_id, commercial_attributes "
                        "FROM mri_publications WHERE run_id = ? AND marketplace = ?",
                        (run_id, mkt)).fetchall()
                except Exception:
                    pubs = cur.execute(
                        "SELECT marketplace_product_id, commercial_attributes "
                        "FROM mri_publications WHERE run_id = ?", (run_id,)).fetchall()
                skus, official = set(), 0
                identity_counts = {
                    "OFFICIAL_VERIFIED": 0, "THIRD_PARTY_NEW": 0,
                    "THIRD_PARTY_USED": 0, "SELLER_UNVERIFIED": 0,
                    "official_kpi_eligible": 0, "excluded_from_official_kpi": 0,
                }
                for sku, attrs_raw in pubs:
                    if sku in skus:
                        continue
                    skus.add(sku)
                    try:
                        attrs = json.loads(attrs_raw) if isinstance(attrs_raw, str) else (attrs_raw or {})
                    except Exception:
                        attrs = {}
                    identity = attrs.get("commercial_identity") if isinstance(attrs, dict) else None
                    if identity:
                        st = identity.get("state")
                        if st in ("OFFICIAL_VERIFIED", "THIRD_PARTY_NEW", "THIRD_PARTY_USED"):
                            identity_counts[st] += 1
                        else:
                            identity_counts["SELLER_UNVERIFIED"] += 1
                        if st == "OFFICIAL_VERIFIED" and identity.get("condition") != "USED":
                            official += 1
                            identity_counts["official_kpi_eligible"] += 1
                        else:
                            identity_counts["excluded_from_official_kpi"] += 1
                    else:
                        # Legacy rows: only explicit seller evidence is official.
                        sellers = [str(x).lower() for x in (attrs.get("sellers") or [])]
                        if attrs.get("is_official_seller") or "nicopoly" in sellers:
                            official += 1
                            identity_counts["OFFICIAL_VERIFIED"] += 1
                            identity_counts["official_kpi_eligible"] += 1
                        else:
                            identity_counts["SELLER_UNVERIFIED"] += 1
                            identity_counts["excluded_from_official_kpi"] += 1
                try:
                    cats = cur.execute(
                        "SELECT COUNT(*) FROM mri_publication_categories "
                        "WHERE publication_id IN (SELECT publication_id FROM mri_publications "
                        "WHERE run_id = ? AND marketplace = ?)",
                        (run_id, mkt)).fetchone()[0]
                except Exception:
                    cats = 0
                state = (terminal or status or "").upper()
                if state in ("SOURCE_BLOCKED", "EXTRACTOR_FAILURE", "FAILED", "PARTIAL",
                             "NOT_FOUND", "STOPPED_BY_USER", "STOPPED"):
                    # Keep the real outcome: absence of rows is not "not executed".
                    pass
                elif state in ("", "COMPLETED", "SUCCESS", "PENDING", "RUNNING", "FOUND"):
                    state = "OPERATIONAL" if skus else "NOT_EXECUTED"
                out[mkt].update({
                    "brand_publications": len(skus),
                    "official_seller_publications": official,
                    "categories_count": cats,
                    "status": state,
                    "run_id": run_id,
                    "run_date": started,
                    "source": source,
                    "execution_mode": mode,
                    "engine": mode,
                    # This is a READ of persisted data, never a new acquisition.
                    "view_kind": "PERSISTED_VIEW",
                    "live": False,
                    "is_new_acquisition": False,
                    "identity_summary": identity_counts,
                })
        finally:
            conn.close()

    scan(_operational_db_path(), "OPERATIONAL")
    protected = _protected_db_path()
    if protected is not None:
        scan(protected, "PROTECTED")

    executed = [m for m, d in out.items() if d["status"] not in ("NOT_EXECUTED",)]
    return {
        "brand": "Nicopoly",
        "mode": "COMPARATIVE",
        "marketplaces": out,
        "executed_marketplaces": len(executed),
        "total_marketplaces": len(out),
        "note": ("Cada marketplace muestra su ultima corrida verificada persistida. "
                 "Es una VISTA PERSISTIDA: no se suman corridas independientes y no "
                 "representa una adquisicion nueva."),
        "shared_mri_contract_version": "2.0",
        "status": "COMPARATIVE_READY" if executed else "NO_RUN_DATA",
        "view_kind": "PERSISTED_VIEW",
        "live": False,
        "is_new_acquisition": False,
        "catalog_reference": _safe_catalog_reference(),
    }


@app.get("/api/multimarketplace/summary")
async def get_multimarketplace_summary(run_id: str = None):
    """
    Returns dynamic cross-marketplace comparative summary for Nicopoly across
    all four active marketplaces (Paris, Falabella, Mercado Libre, Ripley).
    Queries real execution data from SQLite associated with run_id (or latest run).
    """
    # Comparative view (no run_id): latest verified run per marketplace.
    if not run_id:
        return JSONResponse(content=_comparative_marketplace_summary())

    effective_db = DB_PATH
    try:
        from app.mri_autonomous.storage_guard import StorageConfig
        effective_db = StorageConfig.get_sqlite_path()
    except Exception:
        pass

    marketplaces_data = {
        "Paris": {
            "mechanism": "Constructor.io API / Controlled HAR Replay",
            "brand_publications": 0,
            "official_seller_publications": 0,
            "categories_count": 0,
            "status": "NOT_EXECUTED"
        },
        "Falabella": {
            "mechanism": "Next.js SSR __NEXT_DATA__",
            "brand_publications": 0,
            "official_seller_publications": 0,
            "categories_count": 0,
            "status": "NOT_EXECUTED"
        },
        "Mercado Libre": {
            "mechanism": "Official Corridor Scraper & Taxonomy Discovery",
            "brand_publications": 0,
            "official_seller_publications": 0,
            "categories_count": 0,
            "status": "NOT_EXECUTED"
        },
        "Ripley": {
            "mechanism": "Catalog Scraper & Facets Verification",
            "brand_publications": 0,
            "official_seller_publications": 0,
            "categories_count": 0,
            "status": "NOT_EXECUTED"
        }
    }

    if not Path(effective_db).exists():
        return JSONResponse(content={
            "brand": "Nicopoly",
            "marketplaces": marketplaces_data,
            "total_active_marketplaces": 4,
            "shared_mri_contract_version": "2.0",
            "status": "NO_RUN_DATA"
        })

    try:
        conn = sqlite3.connect(effective_db)
        cur = conn.cursor()

        # Check if mri_runs table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mri_runs'")
        if not cur.fetchone():
            conn.close()
            return JSONResponse(content={
                "brand": "Nicopoly",
                "marketplaces": marketplaces_data,
                "total_active_marketplaces": 4,
                "shared_mri_contract_version": "2.0",
                "status": "NO_RUN_DATA"
            })

        # Find run_id if not provided
        target_run_id = run_id
        if not target_run_id:
            # Check for latest multi-marketplace run
            cur.execute("SELECT run_id FROM mri_runs ORDER BY started_at DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                target_run_id = row[0]

        if target_run_id:
            # Check secondary table mri_run_marketplace_states first
            has_mkt_states = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mri_run_marketplace_states'").fetchone()
            states_loaded = False
            if has_mkt_states:
                cur.execute("""
                    SELECT marketplace, execution_mode, terminal_state, status
                    FROM mri_run_marketplace_states WHERE run_id = ?
                """, (target_run_id,))
                mkt_states = cur.fetchall()
                if mkt_states:
                    states_loaded = True
                    for mkt, mode, state, st in mkt_states:
                        if mkt in marketplaces_data:
                            marketplaces_data[mkt]["status"] = state or st or "COMPLETED"
                            marketplaces_data[mkt]["mechanism"] = mode or marketplaces_data[mkt]["mechanism"]

            # Fallback to mri_runs if no states in secondary table
            if not states_loaded:
                cur.execute("""
                    SELECT marketplace, execution_mode, terminal_state, status
                    FROM mri_runs WHERE run_id = ?
                """, (target_run_id,))
                runs = cur.fetchall()
                for mkt, mode, state, st in runs:
                    if mkt in marketplaces_data:
                        marketplaces_data[mkt]["status"] = state or st or "COMPLETED"
                        marketplaces_data[mkt]["mechanism"] = mode or marketplaces_data[mkt]["mechanism"]

            # Query publications and official seller counts per marketplace scoped to target_run_id
            has_hist = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mri_historical_publications'").fetchone()
            pub_query = """
                SELECT marketplace, marketplace_product_id, commercial_attributes
                FROM mri_publications WHERE run_id = ?
            """
            if has_hist:
                pub_query += """
                    UNION ALL
                    SELECT marketplace, marketplace_product_id, commercial_attributes
                    FROM mri_historical_publications WHERE run_id = ?
                """
                params = (target_run_id, target_run_id)
            else:
                params = (target_run_id,)

            pub_rows = cur.execute(pub_query, params).fetchall()
            mkt_items = {}
            for r in pub_rows:
                mkt = r[0]
                sku = r[1]
                attrs_raw = r[2] or "{}"
                if mkt not in mkt_items:
                    mkt_items[mkt] = {"skus": set(), "official_count": 0}
                if sku not in mkt_items[mkt]["skus"]:
                    mkt_items[mkt]["skus"].add(sku)
                    try:
                        attrs = json.loads(attrs_raw) if isinstance(attrs_raw, str) else attrs_raw
                    except Exception:
                        attrs = {}
                    sellers = [str(s).lower() for s in attrs.get("sellers", [])]
                    is_official = attrs.get("is_official_seller") or ("nicopoly" in sellers)
                    if is_official:
                        mkt_items[mkt]["official_count"] += 1

            for mkt, data in mkt_items.items():
                if mkt in marketplaces_data:
                    total_pubs = len(data["skus"])
                    marketplaces_data[mkt]["brand_publications"] = total_pubs
                    marketplaces_data[mkt]["official_seller_publications"] = data["official_count"]
                    # If marketplace has publications, default to OPERATIONAL unless an explicit terminal state was persisted
                    curr_st = marketplaces_data[mkt]["status"]
                    if curr_st in ("NOT_EXECUTED", "COMPLETED", "SUCCESS", "PENDING"):
                        if total_pubs > 0:
                            marketplaces_data[mkt]["status"] = "OPERATIONAL"
                    elif curr_st in ("BLOCKED", "SOURCE_BLOCKED", "PARTIAL", "FAILED", "ERROR"):
                        # Strictly respect persisted terminal failure state
                        pass


            # Query categories count per marketplace SCOPED strictly to target_run_id
            try:
                has_active_for_run = cur.execute(
                    "SELECT 1 FROM mri_publications WHERE run_id = ? LIMIT 1", (target_run_id,)
                ).fetchone()
                has_hist_cat = cur.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mri_historical_publication_categories'"
                ).fetchone()

                cat_parts = []
                cat_params = []
                if has_active_for_run:
                    cat_parts.append("""
                        SELECT p.publication_id, p.marketplace, pc.category_id
                        FROM mri_publications p
                        JOIN mri_publication_categories pc ON p.publication_id = pc.publication_id
                        WHERE p.run_id = ? AND pc.status = 'ACTIVE'
                    """)
                    cat_params.append(target_run_id)
                if has_hist_cat:
                    cat_parts.append("""
                        SELECT hp.publication_id, hp.marketplace, hpc.category_id
                        FROM mri_historical_publications hp
                        JOIN mri_historical_publication_categories hpc ON hp.publication_id = hpc.publication_id AND hp.run_id = hpc.run_id
                        WHERE hp.run_id = ?
                    """)
                    cat_params.append(target_run_id)

                if cat_parts:
                    cat_query = f"""
                        SELECT pc.marketplace, COUNT(DISTINCT pc.category_id)
                        FROM ({' UNION ALL '.join(cat_parts)}) pc
                        GROUP BY pc.marketplace
                    """
                    cat_counts = cur.execute(cat_query, tuple(cat_params)).fetchall()
                    for mkt, num_cats in cat_counts:
                        if mkt in marketplaces_data:
                            marketplaces_data[mkt]["categories_count"] = num_cats
            except Exception:
                pass

        conn.close()


        # Determine overall status
        operational_count = sum(1 for m in marketplaces_data.values() if m["status"] in ("OPERATIONAL", "COMPLETED"))
        overall_status = "ALL_MARKETPLACES_OPERATIONAL" if operational_count == 4 else ("PARTIALLY_OPERATIONAL" if operational_count > 0 else "NO_OPERATIONAL_DATA")

        return JSONResponse(content={
            "brand": "Nicopoly",
            "run_id": target_run_id,
            "marketplaces": marketplaces_data,
            "total_active_marketplaces": 4,
            "operational_marketplaces_count": operational_count,
            "shared_mri_contract_version": "2.0",
            "status": overall_status,
            # Scoped read of ONE run: persisted view, not a new acquisition.
            "view_kind": "PERSISTED_VIEW",
            "live": False,
            "is_new_acquisition": False,
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "brand": "Nicopoly", "marketplaces": marketplaces_data})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8055)

