# MRI_ENABLE_PARALLEL_EXECUTION_013_REPORT

**Tarea:** MRI-ENABLE-PARALLEL-EXECUTION-013 · **Fecha:** 2026-11-09
**Modo:** cambios de concurrencia + piloto; **sin commit**
**Base:** `integration/mri-deepseek-closure` @ `1e13728`

---

## 1. Cambios aplicados (listos para commitear)

`git -C _integration diff --stat`:

```text
app/mri_autonomous/experience_store.py |  9 +++-
app/mri_autonomous/recovery_runner.py  | 16 +++++++-
app/mri_dashboard/mri_runner.py        | 75 +++++++++++++++++++++++++++-------
3 files changed, 82 insertions(+), 18 deletions(-)
```

Los tres archivos están modificados y sin commit en el worktree; no se tocó producción.

### 1.1 `mri_runner.py` — semáforo real y stop

```python
try:
    _max_browser = int(_os.environ.get("MRI_MAX_BROWSER_CONCURRENCY", "1"))
except ValueError:
    _max_browser = 1
if _max_browser <= 1:
    self.state["execution_strategy"] = "ALL_SEQUENTIAL_AUTO"
    # ... bucle secuencial de compatibilidad ...
else:
    _semaphore = asyncio.Semaphore(max(1, _max_browser))

    async def _child_limited(mkt):
        async with _semaphore:
            return await _child(mkt)

    tasks = [asyncio.create_task(_child_limited(m)) for m in mkts]
    self._parallel_children = tasks

    async def _monitor():
        while True:
            _sync_children()
            if self.stop_requested:
                for _c in list(_live_children.values()):
                    _c.stop_requested = True
                for _t in tasks:
                    if not _t.done():
                        _t.cancel()
                break
            await asyncio.sleep(2)
```

Además:
- `_child()` aborta si el padre ya pidió stop y marca `child.stop_requested=True` en `finally`.
- La agregación tolera `BaseException`/`CancelledError` (antes `CancelledError` se trataba como si fuera un hijo y lanzaba `AttributeError`).
- Los hijos cancelados se publican como `STOPPED` si el stop fue del usuario.

### 1.2 `experience_store.py` — WAL + busy_timeout

```python
conn = sqlite3.connect(self.db_path, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")
conn.execute("PRAGMA synchronous=NORMAL")
```

### 1.3 `recovery_runner.py` — WAL + busy_timeout

Se añadió `_connect_sqlite_parallel(path)` con las mismas tres PRAGMAs y se reemplazaron
las dos conexiones `sqlite3.connect(self.db_path)` (lectura de snapshots y persistencia).

---

## 2. Prueba de concurrencia (semáforo real)

Prueba aislada con 4 hijos sintéticos (sin I/O de marketplace), `MRI_MAX_BROWSER_CONCURRENCY=2`:

```json
{
  "concurrency": {
    "elapsed_s": 60.01,
    "max_active": 2,
    "started_order": ["Paris", "Falabella", "Ripley", "Mercado Libre"],
    "strategy": "ALL_PARALLEL"
  }
}
```

- 4 tareas de 30 s con límite 2 → **60 s** (2 lotes), no 120 s.
- `max_active=2` demuestra que el semáforo limita de verdad (antes, con `>1`, se habrían
  lanzado los 4).
- Stop: `stop()` a 1 s → **1.0 s** de terminación, solo Paris/Falabella alcanzaron a iniciar
  (2 slots), las 4 tareas fueron canceladas y agregadas sin excepción.

---

## 3. Piloto real Paris + Falabella

Comando lógico (harness aislado que invoca `MRIOrchestrator.run_parallel_discovery`):

```text
MRI_MAX_BROWSER_CONCURRENCY=2
marketplaces=["Paris", "Falabella"], max_pages=1, limit=3
```

Resultado:

```json
{
  "elapsed_s": 120.01,
  "execution_strategy": "ALL_PARALLEL",
  "marketplace_states": {"Paris": "EXTRACTOR_FAILURE", "Falabella": "IDLE"},
  "child_run_ids": {
    "Paris": "RUN_PARALLEL_013_HTTP__paris",
    "Falabella": "RUN_PARALLEL_013_HTTP__falabella"
  },
  "results": 0,
  "is_running": false,
  "integrity": "ok",
  "runs": [{"run_id": "RUN_PARALLEL_013_HTTP__paris",
            "marketplace": "Paris",
            "terminal_state": "EXTRACTOR_FAILURE",
            "status": "SOURCE_BLOCKED"}]
}
```

- El planificador ejecutó en **ALL_PARALLEL** con 2 slots; no hubo colisión SQLite.
- **Paris** falló al iniciar el navegador en este entorno (mismo `EXTRACTOR_FAILURE` de 012).
- **Falabella** respondió **HTTP 403 Forbidden** en sus fetch SSR (anti-bot externo); quedó `IDLE`
  al cortar a los 120 s.
- **No se completó el piloto real de 4 marketplaces.** No es un fallo del semáforo; son bloqueos
  externos de navegador/anti-bot. No se declara `SOURCE_BLOCKED` como `NOT_FOUND`.

**Ripley/ML:** no se pudieron confirmar arranques de navegador en el CLI; en 012 fallaron por el
mismo límite de entorno. No se ejecutó el par Ripley+ML en este piloto para no repetir un fallo
conocido sin corrección del entorno.

---

## 4. SQLite

| Comprobación | Resultado |
|---|---|
| `ExperienceStore` journal mode | **wal** |
| `busy_timeout` | **30000** |
| `database is locked` en logs | **0 ocurrencias** |
| `PRAGMA integrity_check` (sandbox piloto) | **ok** |
| Filas `mri_evidence_ledger` | 0 (el piloto no llegó a FOUND; no hubo pérdida) |
| `mri_runs` | 1 fila Paris EXTRACTOR_FAILURE; Falabella no finalizó |
| Lock `mri_instance_8055.lock` | **no existe** |

No hay evidencia de corrupción ni de filas perdidas; los fallos ocurrieron antes de materializar
publicaciones.

---

## 5. Confirmaciones y límites

```text
SEMAPHORE_REAL=PASS (max_active=2 con 4 tareas)
STOP_PROPAGATION=PASS (cancelación en 1.0 s)
CANCELLED_CHILD_AGGREGATION=FIXED (sin AttributeError)
SQLITE_WAL=PASS
SQLITE_BUSY_TIMEOUT=30000
DATABASE_LOCKED_ERRORS=0
REAL_PARALLEL_PILOT=PARTIAL (Paris browser falló; Falabella 403; no completó)
RIPLEY_ML_BROWSER_START=NOT_CONFIRMED (entorno CLI bloquea Chrome)
CODE_CHANGES=3 archivos, sin commit
```

---

## 6. Conclusión

- **El paralelismo funciona a nivel de orquestador con 2 navegadores/slots**: semáforo efectivo,
  stop que cancela hijos y agregación segura.
- **No se puede declarar el piloto real de 4 marketplaces completo** en este entorno: Paris no
  inicia navegador y Falabella devuelve 403; Ripley/ML tampoco tienen navegador confirmado.
- **Escalar a 4 no es recomendable todavía**: 2 es el límite seguro; antes hay que resolver el
  arranque de Chrome en el proceso de ejecución y el 403 de Falabella, y luego probar
  2 HTTP + 1 browser, 2 browsers, etc.
- Los cambios están **listos para commitear** en el worktree (`mri_runner.py`,
  `experience_store.py`, `recovery_runner.py`), pendientes de validación del operador.

**Recomendación:** mantener `MRI_MAX_BROWSER_CONCURRENCY=2`, ejecutar el piloto real desde el
dashboard (donde Chrome sí arranca) y no subir a 4 hasta tener evidencia de 2 navegadores
simultáneos sin fallos. 
