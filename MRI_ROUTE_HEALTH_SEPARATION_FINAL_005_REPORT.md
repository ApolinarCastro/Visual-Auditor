# MRI_ROUTE_HEALTH_SEPARATION_FINAL_005_REPORT

**Tarea:** MRI-ROUTE-HEALTH-SEPARATION-FINAL-005 · **Fecha:** 2026-11-09
**Árbol:** `_integration/` · **HEAD:** `8f14b9e` (sin commit nuevo)
**GIT_COMMITS=0 · GIT_PUSHES=0** (cambios de MRI-005 sin commit, a la espera de validación)

---

## 1. Cambios de código (diff conceptual)

> `_integration/` no está versionado en Git, por lo que no hay `git diff`; se documentan los cambios
> exactos aplicados. **`mri_runner.py` NO se modificó** (no hizo falta pasar `scope` desde el runner).

### `capability_registry.py` — `report_outcome(...)`

```diff
- def report_outcome(self, capability_id, success, error_message=None):
+ def report_outcome(self, capability_id, success, error_message=None,
+                    scope="capability", route_id=None, marketplace=None,
+                    state=None, evidence=None):
      cap = self.get(capability_id)
      if not cap:
          return
+     if scope == "route":
+         store = self._experience()
+         if store is not None and route_id:
+             store.record_experience(
+                 marketplace=marketplace or cap.marketplace, brand="Nicopoly",
+                 knowledge_type="ROUTE_STATE", value=route_id,
+                 page_type=state or ("VALIDATED" if success else "FAILED"),
+                 status="VALIDATED" if success else "FAILED",
+                 is_success=success, evidence_reference=(evidence or "")[:900])
+         return          # NO toca failure_count / health de la capacidad
      cap.last_verified_at = ...
      # comportamiento histórico para scope="capability"
```

### `verified_routes_audit.py` — elegibilidad por ruta

```diff
+ ROUTE_STATES += ("ROUTE_SKIPPED",)
+ TERMINAL_STATES += ("ROUTE_SKIPPED",)
+ RESUME_SKIP_STATES += ("ROUTE_SKIPPED",)
+
+ def _route_history(store, route):
+     return store.get_experience_item(
+         route["marketplace"], "Nicopoly", "ROUTE_STATE", route["route_id"])
+
+ def _route_is_exhausted(row):
+     return (int(row.get("failure_count") or 0) >= 3
+             and row.get("page_type") in ("SOURCE_BLOCKED","AUTH_REQUIRED","EMPTY_VERIFIED"))

  # antes de adquirir
+ _history = _route_history(experience_store, route)
+ if _route_is_exhausted(_history):
+     acquisition = {"state": "ROUTE_SKIPPED", "failure_class": "ROUTE_SKIPPED",
+                    "scraper_started": False, "publications": []}
+     strategy_id = None
+ elif not strategy_id:
      ...
```

Y en la atribución del resultado:

```diff
+ if failure_class in ("INTERNAL_CONTRACT_ERROR","NO_STRATEGY","USER_CANCELLED","ROUTE_SKIPPED"):
+     pass                                   # nunca degrada la capacidad
+ elif _success:
+     registry.report_outcome(cap, True, scope="capability")   # aprende éxito
+     registry.report_outcome(cap, True, scope="route", route_id=..., state=...)
+ elif not acquisition.get("scraper_started"):
+     registry.report_outcome(cap, False, scope="capability")  # fallo de capacidad/config
+ else:
+     registry.report_outcome(cap, False, scope="route", route_id=..., state=...)
+     # fallo comercial/extracción de UNA ruta: NO bloquea la capacidad
```

Se añadió `ROUTE_STATE` persistido por ruta (`knowledge_type="ROUTE_STATE"`,
`value=route_id`, `page_type=state`, `failure_count`). El skip se activa con **3 fallos terminales
de esa ruta** (`SOURCE_BLOCKED`/`AUTH_REQUIRED`/`EMPTY_VERIFIED`).

---

## 2. Prueba aislada: ruta mala no bloquea ruta buena

Script: `experiments/mri_route_health_separation_005/run_separation.py`
Resultado: `experiments/mri_route_health_separation_005/separation_result.json`
(Store temporal; adquisición simulada; sin producción.)

- 2 rutas Ripley: `abrigos` (falla `SOURCE_BLOCKED`) y `blusas` (FOUND).
- 4 ejecuciones `TOP_N=2`:

| Run | Ruta mala | Ruta buena | Capability (Ripley) |
|---|---|---|---|
| 1 | SOURCE_BLOCKED (1.º fallo) | **FOUND** | success=1 |
| 2 | SOURCE_BLOCKED (2.º) | **FOUND** | success=2 |
| 3 | SOURCE_BLOCKED (3.º) | **FOUND** | success=3 |
| 4 | **ROUTE_SKIPPED** (sin scraper) | **FOUND** | success=4, **failure=0, VALIDATED** |

- Llamadas de adquisición: ruta mala **3**, ruta buena **4** (la buena nunca fue bloqueada).
- `ROUTE_STATE exp_1`: `page_type=SOURCE_BLOCKED`, `failure_count=3`, `status=FAILED`.
- Capacidad `ripley_headless_catalog_scraper`: `success_count=4`, `failure_count=0`, **VALIDATED**
  (no BLOCKED). **Falso negativo estructural corregido.**

---

## 3. Ejecución real (dashboard + API interna)

- Dashboard iniciado con `lanzar_mri_dashboard.bat` (launcher oficial), puerto **8055**, auth Basic.
- Vista previa Paris: `available=20`, `eligible=19`, `selected=2`.
- `POST /api/audit/start` con:
  `mode=AUDIT_VERIFIED_ROUTES`, `marketplace=Paris`, `scope=TOP_N`, `limit_routes=2`.
- **run_id:** `run_mri_audit_verified_routes_1794229028`.
- Checkpoint: `data/sqlite/mri_operational/mri_verified_routes_checkpoint_run_mri_audit_verified_routes_1794229028.json`
  → `RUN_COMPLETED`, 2/2 rutas, 0 fallos, 0 pendientes.
- Snapshot: `..._selection_...1794229028.json`, fingerprint `66a3eec5…2671`,
  `experience_source=authorized_experience_read_only:...data/mri_experience.db`.

| # | route_id | URL | strategy_selected = executed | state | publicaciones | evidence_id |
|---|---|---|---|---|---|---|
| 1 | `exp_85` | `https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Abrigos` | `paris_cdp_constructor_discovery` | **FOUND** | 40 | `ev_7a018bc7794a37fd` |
| 2 | `exp_87` | `https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Blusas` | `paris_har_replay_fallback` | **FOUND** | 40 | `ev_56b13067e07cf4de` |

- Evidencia SQLite (`mri_evidence_ledger`): 2 filas `VALIDATED`, `claim_value=FOUND`, con URL,
  route_id, estrategia y `publications=40` en `raw_reference`.
- `mri_runs`: run `SUCCESS`, `terminal_state=FOUND`, `source_method=VERIFIED_ROUTE_AUDIT`.
- **La corrida real no insertó filas en la base de producción**: consulta read-only de
  `data/sqlite/visibility.db` para ese `run_id` → 0 filas; la persistencia fue a
  `data/sqlite/mri_operational/visibility.db`.

### Aprendizaje de capacidad en la ejecución real
- `paris_cdp_constructor_discovery`: `success_count=1`, `failure_count=0`, **VALIDATED**.
- `paris_har_replay_fallback`: `success_count=1`, `failure_count=0`, **VALIDATED**.
- La **2.ª ruta** se seleccionó con evidencia persistida de la 1.ª:
  `experience_evidence.paris_cdp_constructor_discovery = {experience_id: 2367, success_count: 1,
  status: VALIDATED}` → el selector leyó el historial de la primera ruta, sin bloquear la segunda.
- `ROUTE_STATE` `exp_85` y `exp_87`: `page_type=FOUND`, `success_count=1`, `failure_count=0`.

---

## 4. Estado del modo y conocimiento nuevo

```text
VERIFIED_ROUTES_MODE_EXECUTED=YES
NEW_VERIFIED_KNOWLEDGE=2 rutas / 80 publicaciones observadas / 2 evidence_id
  (40 + 40 publicaciones; 2 ROUTE_STATE + 2 DECISION_TRACE)
CAPABILITY_HEALTH=VALIDATED (Paris cdp + har), NO BLOCKED
FALSE_NEGATIVE_FIXED=YES
```

---

## 5. Regresión y estado del núcleo

- `py_compile` de los módulos modificados: **exit 0**.
- Tests ejecutados (`test_verified_routes_audit_008`, `test_hotfix_010`,
  `test_operational_integration_009`): **24 passed, 3 failed**.
  - `test_zero_publication_evidence_idempotent` y `test_module_origins_are_served_tree`
    fallan **solo en la ejecución combinada** por contaminación de `sys.modules['app']`/orden de
    tests; **pasan aislados**.
  - `test_production_sqlite_hashes_unchanged` falla porque el hash actual de
    `data/sqlite/visibility.db` (`2ea4310b…`) no coincide con la constante histórica del test
    (`4f2f976b…`). La corrida real de MRI-005 **no escribió filas en producción** (run_id ausente);
    es una aserción de baseline desactualizada, no una regresión funcional de este cambio.
- `mri_runner.py` no fue modificado; dashboard arrancó y respondió (`/api/state` 200,
  `/api/history` 200, `/` 401 auth) antes y después de los cambios.
- Servidores de prueba detenidos; puerto 8055 cerrado; sin procesos Python residuales del dashboard.

---

## 6. Pendiente

- Los cambios de MRI-005 están **sin commit** (como se pidió). Cuando valides:
  1. revisar el diff conceptual y los archivos modificados;
  2. ejecutar la suite completa (idealmente corrigiendo primero las dos aserciones de test
     desactualizadas: hash de producción y aislamiento de import);
  3. autorizar commit local (sin push).
- No se tocó `_integration/app/mri_dashboard/mri_runner.py`, SQLite de producción, cookies,
  perfiles ni checkpoints históricos.

## Conclusión

El falso negativo estructural está corregido: los fallos de una ruta se registran como
`ROUTE_STATE` y no incrementan el `failure_count` de la capacidad; una ruta con 3 fallos terminales
se salta (`ROUTE_SKIPPED`) sin bloquear a las demás. La ejecución real en Paris produjo **2 rutas
FOUND con 80 publicaciones y 2 evidencias**, y la segunda ruta consumió el aprendizaje de la primera.
`FINAL_STATUS=VERIFIED` (con la salvedad de las 3 aserciones de test desactualizadas, no del núcleo).
