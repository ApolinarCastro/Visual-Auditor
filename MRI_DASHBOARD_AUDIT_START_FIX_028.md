# MRI_DASHBOARD_AUDIT_START_FIX_028

**Fecha:** 2026-11-10
**Síntoma:** el tablero devolvía `500 Internal Server Error` al pulsar auditoría y luego `400` en
los siguientes intentos.

## Causa raíz

`POST /api/audit/start` en modo `AUDIT_VERIFIED_ROUTES` llamaba a:

```python
orchestrator.run_verified_routes_audit(...)
```

Ese método **no existía** en `mri_runner.py` (se perdió en una consolidación previa), por lo que
el endpoint lanzaba:

```text
AttributeError: 'MRIOrchestrator' object has no attribute 'run_verified_routes_audit'
```

El API ya había publicado `orchestrator.is_running = True` y estado `RUNNING` **antes** de ese
error; como la tarea nunca arrancó, el flag quedó atascado y los intentos posteriores devolvían
`400 Bad Request` (“Already running”).

## Fix

Se añadió el adaptador en `mri_runner.py`:

```python
async def run_verified_routes_audit(self, run_id, marketplace="ALL",
                                   scope="ALL_VERIFIED", limit=None,
                                   selected_routes=None, resume_run_id=None):
    ...
    result = await execute_verified_routes_audit(
        run_id=run_id, marketplace=marketplace, scope=scope,
        limit=limit, selected_routes=selected_routes,
        resume_run_id=resume_run_id)
    self.results = result.get("routes") or []
    self.state["status_message"] = result.get("run_status") or "RUN_COMPLETED"
    self.state["outcome"] = ...
```

Además se reinició el dashboard una vez para limpiar el `is_running` atascado.

## Validación

```text
POST /api/audit/start
{"mode":"AUDIT_VERIFIED_ROUTES","marketplace":"Paris","scope":"TOP_N","limit":1}
→ 200 Accepted: Auditoría de rutas verificadas
run_id=run_mri_audit_verified_routes_1794323724

estado final: running=False · RUN_COMPLETED · outcome=PASS · routes=1
historial: Paris FOUND · total=1
```

El tablero queda ejecutando en `http://127.0.0.1:8055` con el fix cargado; las auditorías ya se
pueden lanzar.

## Conclusión

```text
ROOT_CAUSE=missing run_verified_routes_audit in mri_runner
SECONDARY=stuck is_running=True after synchronous AttributeError
FIX=adapter restored + dashboard restart
AUDIT_START=200
AUDIT_RESULT=RUN_COMPLETED/PASS
DASHBOARD=RUNNING
```
