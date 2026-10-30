# MRI-CRITICAL-CLOSURE-015: Cierre Definitivo de los Seis Defectos de Validación Codex 013

**Ejecutor:** Antigravity  
**Referencia:** `MRI_CODEX_FINAL_VALIDATION_013.md`  
**Base de corrección:** `5a99e3fdd1c8edb77ee47853a9b83c1c6e4495e7`  
**Rama:** `feature/mri-critical-closure-015`  
**Fecha:** 2026-10-15  
**Estado:** CLOSED / READY FOR INDEPENDENT CODEX RE-VALIDATION  

---

## 1. Declaración Preflight y Principio de No Invasión

- **Preflight MRI:** Se leyeron y consultaron `README.md`, `CURRENT_STATE.md`, `DECISIONS.md`, `FAILURES.md`, `ACCEPTANCE.md`, `skills/MRI_MANDATORY_SKILLS.json` y los reportes de validación de Codex 011 y 013.
- **Visual Auditor (VA):** 100% CONGELADO / INTOCABLE.
  - Verificación determinista ejecutada: `git diff origin/main -- app/auditor/ app/scrapers/ app/core/` devolvió 0 diferencias.
- **Bases de Producción:** 100% Protegidas. No se alteró `data/sqlite/visibility.db`, `data/experience.db`, `data/mri_experience.db` ni ningún archivo de datos productivo.
- **Rama MRI-014:** Preservada independientemente en `feature/mri-multimarketplace-014`. No hubo mezclas ni colisiones.

---

## 2. Resolución Quirúrgica de los Seis Defectos de Codex 013

### Defecto 1: Sustitución de protección dependiente de CWD por aislamiento efectivo y universal
- **Problema previo reportado por Codex 013:** `storage_guard.py` derivaba los destinos relativos resolviendo con `Path(...).resolve()` respecto del CWD de importación. Si un proceso cambiaba el target a `data/experience.db`, `data/mri_categories.json` o `data/mri_history.json` desde un checkout aislado, el resolved path no coincidía con el CWD original, permitiendo que llegara a la función de apertura sin ser bloqueado por la aplicación.
- **Solución implementada:**
  - En `app/mri_autonomous/storage_guard.py`, `assert_write_allowed` ahora comprueba de forma canónica y agnóstica de CWD los nombres de archivo base y patrones canónicos relativos (`data/experience.db`, `data/mri_experience.db`, `data/mri_categories.json`, `data/mri_history.json`, `data/sqlite/visibility.db`).
  - Si el proceso se encuentra en modo de prueba (`is_test_mode()`), cualquier re-target hacia los destinos canónicos de producción o hacia rutas que apunten a los almacenes del repositorio lanza inmediatamente `ProductionWriteBlockedError`.
  - Además, si se define un directorio de sandbox (`_ISOLATED_DIR`), cualquier intento de escritura fuera del sandbox que apunte a archivos del catálogo o datos productivos es bloqueado de inmediato.
- **Evidencia generada:** `evidence/mri_critical_closure_015/01_writer_isolation_evidence.json` y `tests/test_mri_critical_closure_015.py::test_01_cwd_independent_production_isolation`.

---

### Defecto 2: Corrección de `recovery_runner` indefinido y consulta directa a SQLite en `/api/rea/paris`
- **Problema previo reportado por Codex 013:** `run_consolidated_recovery_pipeline()` en `app/mri_dashboard/mri_api.py` fallaba con `NameError: name 'recovery_runner' is not defined`. Asimismo, `/api/rea/paris` intentaba abrir conexiones de red y fallaba con HTTP 500 en entornos aislados en vez de consultar los registros SQLite persistidos.
- **Solución implementada:**
  - En `app/mri_dashboard/mri_api.py`, `run_consolidated_recovery_pipeline()` invoca el getter lazy formal `runner = get_recovery_runner()`, eliminando el `NameError`.
  - El endpoint `/api/rea/paris` fue reconstruido para consultar primero `mri_publications` y `mri_categories` de SQLite en modo offline. Si no existen registros o la red está desconectada, responde con estados explícitos de evidencia (`OFFLINE_NO_PERSISTED_RECORDS` o `NO_EVIDENCE_RECORDED`) con HTTP 200, sin lanzar HTTP 500 ni forzar peticiones HTTP de red.
- **Evidencia generada:** `evidence/mri_critical_closure_015/02_api_rea_offline_evidence.json` y `tests/test_mri_critical_closure_015.py::test_02_recovery_runner_defined_and_api_offline_storage`.

---

### Defecto 3: Eliminación de decisiones `CORRECT` e identidades verificadas sin correspondencia con catálogo maestro; preservación de procedencia HAR Replay
- **Problema previo reportado por Codex 013:** El adaptador de REA asignaba `TARGET_IDENTITY_VERIFIED` y `category_decision = "CORRECT"` para cualquier publicación replay sin comprobar su correspondencia contra el catálogo maestro, fabricando la afirmación "verificada contra catálogo maestro".
- **Solución implementada:**
  - En `app/mri_autonomous/rea_paris_engine.py:persist_to_mri_sqlite()`, se consulta `get_master_catalog()` antes de determinar el estatus de identidad o decisión de categoría.
  - Para productos o SKUs no vinculados al catálogo maestro, se asigna rigurosamente `identity_status = "IDENTITY_NOT_LINKED"` y `category_decision = "REVIEW_REQUIRED"`.
  - Se fija y preserva `evidence_type = "CONTROLLED_REPLAY"` y `raw_source_id = "HAR-REPLAY-{sku}"` para reflejar la procedencia real de repetición del tráfico HAR capturado.
  - En `mri_api.py:fetch_run_publications()`, se condiciona el texto de razón para no afirmar correspondencia con catálogo maestro cuando `identity_status == "IDENTITY_NOT_LINKED"`.
- **Evidencia generada:** `evidence/mri_critical_closure_015/03_replay_identity_provenance_evidence.json` y `tests/test_mri_critical_closure_015.py::test_03_rea_master_catalog_identity_and_provenance`.

---

### Defecto 4: Preservación íntegra de observaciones REA de corridas anteriores en `mri_historical_publications`
- **Problema previo reportado por Codex 013:** El adaptador REA ejecutaba `INSERT OR REPLACE` sobre `mri_publications` sin archivar las observaciones previas de la publicación, provocando que una segunda corrida eliminara el historial de la primera.
- **Solución implementada:**
  - En `app/mri_autonomous/rea_paris_engine.py:persist_to_mri_sqlite()`, antes de actualizar una publicación existente cuyo `run_id` difiere del actual, el registro previo se archiva deterministamente en la tabla `mri_historical_publications` generando una clave única `hist_{run_id}_{publication_id}`.
- **Evidencia generada:** `evidence/mri_critical_closure_015/04_observation_history_preservation_evidence.json` y `tests/test_mri_critical_closure_015.py::test_04_rea_observation_history_preservation`.

---

### Defecto 5: Corrección del filtro y visualización de coberturas parciales, incluido `PAGE_BUDGET_EXCEEDED`
- **Problema previo reportado por Codex 013:** En `index.html`, el dropdown de filtro `<select id="filterCoverage">` solo tenía `ALL`, `COMPLETE` y `PARTIAL`. Al filtrar por "Parcial", una corrida con `coverage = "PAGE_BUDGET_EXCEEDED"` mostraba 0 registros debido a una comparación literal. Tampoco se visualizaba el límite de presupuesto de páginas en el modal de detalle.
- **Solución implementada:**
  - En `app/mri_dashboard/templates/index.html`:
    1. Se agregó la opción explícita `<option value="PAGE_BUDGET_EXCEEDED">Presupuesto de Páginas Excedido</option>` al filtro de cobertura.
    2. En la función de filtrado JS `renderMainTable()`, la selección `PARTIAL` ahora agrupa tanto `PARTIAL` como `PAGE_BUDGET_EXCEEDED`.
    3. En el modal de detalle (`modalDetail`), se incorporó una fila específica para `"Cobertura y Límite"` que expone el valor exacto de `coverage` y el motivo de detención (`stop_reason`).
- **Evidencia generada:** `evidence/mri_critical_closure_015/05_coverage_filter_representation_evidence.json` y `tests/test_mri_critical_closure_015.py::test_05_coverage_filter_and_dashboard_representation`.

---

### Defecto 6: Diferenciación de respuestas vacías de resultados comerciales válidos (Fin de Falsos Ceros)
- **Problema previo reportado por Codex 013:** Ante una respuesta upstream vacía `{}` o nula, `/api/rea/paris` devolvía `status = "OPERATIONAL"` con 0 resultados de marca y seller, transformando la ausencia de evidencia en una afirmación operacional de "cero demostrado".
- **Solución implementada:**
  - En `app/mri_dashboard/mri_api.py:get_rea_paris_data()`, si la consulta no devuelve publicaciones persistidas y las respuestas del motor REA arrojan 0 resultados o están vacías, el endpoint responde con:
    ```json
    {
      "status": "NO_EVIDENCE_RECORDED",
      "reason": "Sin datos persistidos en almacenamiento ni respuesta de red válida"
    }
    ```
    Bajo ninguna circunstancia se declara `status = "OPERATIONAL"` sin evidencia comercial demostrada.
- **Evidencia generada:** `evidence/mri_critical_closure_015/06_empty_upstream_handling_evidence.json` y `tests/test_mri_critical_closure_015.py::test_06_empty_upstream_not_declared_operational`.

---

## 3. Matriz de Pruebas Automatizadas y Regresiones

Todas las suites de prueba fueron ejecutadas y pasaron al 100%:

1. **Suite de Cierre Crítico 015 (`tests/test_mri_critical_closure_015.py`):**
   - `test_01_cwd_independent_production_isolation`: **PASSED**
   - `test_02_recovery_runner_defined_and_api_offline_storage`: **PASSED**
   - `test_03_rea_master_catalog_identity_and_provenance`: **PASSED**
   - `test_04_rea_observation_history_preservation`: **PASSED**
   - `test_05_coverage_filter_and_dashboard_representation`: **PASSED**
   - `test_06_empty_upstream_not_declared_operational`: **PASSED**
   - **Resultado:** 6 passed en 20.19s.

2. **Suite de Regresión Closure 012 (`tests/test_mri_autonomous_closure_012.py`):**
   - 5 tests pasados al 100% (**5 passed**).

3. **Suite de Regresión Repair 009 (`tests/test_mri_autonomous_repair_009.py`):**
   - 10 tests pasados al 100% (**10 passed**), incluyendo preservación histórica de 2.533 registros y barrera de producción.

4. **Suite de Descubrimiento REA 010 (`tests/test_mri_rea_discovery_010.py`):**
   - 7 tests pasados al 100% (**7 passed**).

---

## 4. Compromisos y Verificación de Límites

- **Visual Auditor Diff:** 0 líneas modificadas en `app/auditor/`, `app/scrapers/`, `app/core/`.
- **Producción:** Inalterada.
- **Rama:** `feature/mri-critical-closure-015`.
- **Siguiente acción:** Validación independiente por Codex y posterior conciliación ordenada con `feature/mri-multimarketplace-014`.
