# MRI_PARALLEL_DASHBOARD_VALIDATION_014_REPORT

**Tarea:** MRI-PARALLEL-DASHBOARD-VALIDATION-014 · **Fecha:** 2026-11-09
**Entorno:** dashboard oficial en `127.0.0.1:8055`, build `3af2348381b3-dirty`
**Commit de código:** `3af2348381b37fd5dc40b6cecabf89130dd22ad8`
`feat(mri): paralelismo real con semáforo, stop propagado y SQLite WAL`

---

## 1. Preflight y commit

- Código commiteado y pusheado en `integration/mri-deepseek-closure`
  (`1e13728..3af2348`): `mri_runner.py`, `experience_store.py`, `recovery_runner.py`.
- El dashboard inicial ya estaba lanzado **sin** `MRI_MAX_BROWSER_CONCURRENCY`, por lo que su primer
  run (`run_mri_discovery_1794245730`, 14:35:30) salió `ALL_SEQUENTIAL_AUTO`.
- Ese run se detuvo limpiamente por API (`POST /api/audit/stop` → `STOPPED_BY_USER`).
- Se relanzó el dashboard oficial (`lanzar_mri_dashboard.bat`) con
  **`MRI_MAX_BROWSER_CONCURRENCY=2`**, build `3af2348381b3-dirty`, PID 24264.
- Nuevo run: **`run_mri_discovery_1794246495`**, iniciado 14:48:15.7.

## 2. `execution_strategy`

```text
POST /api/audit/start
{"mode":"DISCOVERY","marketplace":"ALL","limit":3,"parallel":true}
→ 200 Accepted: Autonomous Discovery (ALL_PARALLEL)
```

Estado observado desde el primer poll:

```text
execution_strategy = ALL_PARALLEL
```

Evidencia de simultaneidad real (14:48:28):

```json
{"Mercado Libre":"EN_CURSO","Paris":"EN_CURSO",
 "Ripley":"PENDIENTE","Falabella":"PENDIENTE"}
```

A las 14:53:36, con Paris ya terminado:

```json
{"Mercado Libre":"EN_CURSO","Paris":"FOUND",
 "Ripley":"EN_CURSO","Falabella":"PENDIENTE"}
```

Máximo de **2 hijos activos** a la vez (semáforo=2).

## 3. Tiempos por marketplace

| Marketplace | Inicio | Fin | Duración | Estado final | Navegador |
|---|---|---|---|---|---|
| **Paris** | 14:48:21 | **14:53:04** | **~4 min 43 s** | **FOUND** | **SÍ** (headless) |
| **Mercado Libre** | 14:48:21 | 15:03:43 (stop) | ~15 min (parcial) | **STOPPED** | **SÍ** (14:48:23) |
| **Ripley** | 14:53:22 | 15:03:43 (stop) | ~10 min (parcial) | **STOPPED** | **SÍ** (14:53:24) |
| **Falabella** | — | 15:03:43 (stop) | — | **STOPPED** (nunca inició) | **NO** |

- Paris liberó su slot a las 14:53:04; Ripley arrancó inmediatamente (14:53:22).
- Falabella quedó `PENDIENTE` porque ML y Ripley ocupaban los 2 slots; al hacer stop pasó a
  `STOPPED` sin crear hijo. **No fue un fallo de Falabella.**
- Run completo: 14:48:15 → stop 15:03:42 (**~15 min 27 s**); no se dejó terminar porque Falabella
  no podía obtener slot mientras ML/Ripley seguían.

## 4. Resultados y publicaciones

Fuente: checkpoints de cobertura + `mri_runs` operativa.

| Marketplace | Categorías | Páginas | Publicaciones | Estado |
|---|---:|---:|---:|---|
| **Paris** | 1 (`/search?q=nicopoly`) | 5 | **119** | **FOUND** (`mri_runs` SUCCESS) |
| **Mercado Libre** | 2 (abrigos/chaquetas 151; blusas 74) | 6 | **225** | STOPPED (EN_CURSO) |
| **Ripley** | 4 | 4 | **0** | STOPPED (EN_CURSO) |
| **Falabella** | 0 | 0 | **0** | STOPPED (nunca inició) |
| **Total** | | **15** | **344** | |

- Paris checkpoint: `termination=ALL_CATEGORIES_EXHAUSTED`, `acceptance=AUDIT_FAIL` (aceptación de
  cobertura/taxonomía, no del estado de adquisición); su fila `mri_runs` es `FOUND / SUCCESS`.
- `mri_evidence_ledger` no registró filas para este run (el stop ocurrió antes del cierre del padre);
  la evidencia disponible son los checkpoints y la fila Paris de `mri_runs`.
- `FOUND/NOT_FOUND/SOURCE_BLOCKED`: Paris `FOUND`; los tres restantes `STOPPED` (sin `NOT_FOUND`
  ni `SOURCE_BLOCKED` declarados).

## 5. Preguntas de cierre

| Pregunta | Respuesta |
|---|---|
| `execution_strategy` | **ALL_PARALLEL** |
| ¿Paris/Falabella terminan rápido? | Paris **SÍ** (~4m43); Falabella **no inició** por límite de 2 slots |
| ¿Ripley y ML arrancan navegador? | **SÍ**: ML 14:48:23, Ripley 14:53:24 |
| ¿Colisiones SQLite? | **NO**: `database is locked` = **0**; `PRAGMA integrity_check=ok` |
| ¿Stop funcionó? | **SÍ**: `POST /api/audit/stop` 200 → `is_running=false`; ML/Ripley/Falabella `STOPPED`; Paris conservado `FOUND` |
| ¿Se mató algún proceso a la fuerza? | **NO** |

Errores del estado final: 3 `CancelledError` esperados por la cancelación (ML, Ripley, Falabella),
no errores de SQLite ni de marketplace.

## 6. Conclusión

- **El paralelismo con 2 slots funciona desde el dashboard**: Paris y ML arrancaron simultáneamente;
  Paris terminó en ~4m43; Ripley arrancó al liberarse el slot; el semáforo mantuvo **2 activos**.
- **Falabella no alcanzó slot** en la ventana observada (quedó en cola), por lo que no se puede
  afirmar que los 4 se ejecuten simultáneamente con `MRI_MAX_BROWSER_CONCURRENCY=2`. El diseño es
  correcto: 4 tareas encoladas, 2 en ejecución.
- **Escalar a 4 no está validado**: con 2 el sistema fue estable, sin `database is locked` y con
  stop limpio. Para 4 haría falta más memoria/Chrome y una ventana de prueba específica; no se
  recomienda todavía.
- **El paralelismo queda validado en el entorno correcto** para 2 navegadores; el límite de
  concurrencia y el stop funcionan según diseño.

## 7. Estado operativo

```text
COMMIT=3af2348
EXECUTION_STRATEGY=ALL_PARALLEL
MAX_CONCURRENT_CHILDREN=2
SQLITE_INTEGRITY=ok
DATABASE_LOCKED_ERRORS=0
STOP_PROPAGATED=YES
HARD_KILLS=0
DASHBOARD=RUNNING (PID 24264, lock de instancia del dashboard; sin auditoría activa)
```
