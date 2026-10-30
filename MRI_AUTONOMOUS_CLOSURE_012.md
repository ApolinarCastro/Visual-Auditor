# MRI-AUTONOMOUS-CLOSURE-012: Reporte de Cierre Funcional y Corrección de Defectos

**ID de Tarea:** MRI-AUTONOMOUS-CLOSURE-012  
**Ejecutor:** Antigravity  
**Validador Independiente:** Codex  
**Referencia Obligatoria:** `MRI_CODEX_INDEPENDENT_VALIDATION_011.md`  
**Base:** commit `a5ec56ddad97596d11c3fc9fc0b6949103f8170e`  
**Fecha:** 2026-10-15  

---

## 1. Resumen Ejecutivo de Cierre

Se ha completado la resolución demostrable de los 5 defectos señalados por la validación independiente Codex 011, completando la integración funcional existente entre el motor `REAParisEngine` y la arquitectura analítica de MRI (descubrimiento → normalización → persistencia aislada → API → dashboard) sin iniciar nuevos ciclos de investigación ni modificar los componentes congelados de Visual Auditor (`VA: FROZEN`).

Todas las correcciones fueron validadas mediante pruebas negativas, pruebas unitarias y suites completas de regresión e integración (`test_mri_autonomous_closure_012.py`, `test_mri_autonomous_repair_009.py`, `test_mri_rea_discovery_010.py`), totalizando **22 pruebas aprobadas (100% PASS)** y cero fallos.

---

## 2. Resolución Detallada de los 5 Defectos de Codex 011

### Defecto 1: Revalidación de Destino en `ExperienceStore` ante Mutación de Atributos
- **Fallo previo (Codex 011):** Si el atributo `db_path` de una instancia de `ExperienceStore` era reasignado a una ruta productiva (`StorageConfig.PRODUCTION_EXPERIENCE`) con posterioridad a la inicialización `__init__`, las escrituras posteriores no revalidaban la barrera de destino.
- **Corrección ejecutada:** En `app/mri_autonomous/experience_store.py`, el método `_get_connection()` invoca explícitamente `StorageConfig.assert_write_allowed(self.db_path)` en cada apertura de conexión. Cualquier intento de mutación a ruta productiva genera inmediatamente `ProductionWriteBlockedError`.
- **Evidencia reproducible:** `evidence/mri_autonomous_closure_012/defect_1_experiencestore_revalidation.json` y `test_01_experience_store_connection_revalidation_defect`.

### Defecto 2: Propagación de `terminal_state` y `stop_reason` sin Falsa Cobertura Completa
- **Fallo previo (Codex 011):** En ejecuciones donde el presupuesto de páginas se agotaba (`PAGE_BUDGET_EXCEEDED`), el valor persistido en `mri_runs.terminal_state` se degradaba a `COMPLETED`, convirtiendo auditorías parciales en pretendidamente completas.
- **Corrección ejecutada:** En `app/mri_autonomous/recovery_runner.py` (`persist_to_sqlite`), se extrae `reconciled_result.get("terminal_state")` y se persiste fidedignamente en `mri_runs.terminal_state`. Si `terminal_state == "PAGE_BUDGET_EXCEEDED"`, el `status` de la corrida se asigna explícitamente a `"STOPPED"`.
- **Evidencia reproducible:** `evidence/mri_autonomous_closure_012/defect_2_terminal_state_propagation.json` y `test_02_terminal_state_propagation_defect`.

### Defecto 3: Preservación de Procedencia Primaria (`raw_source_id` y `evidence_type`)
- **Fallo previo (Codex 011):** Corridas de fixture o replay persistían `raw_source_id = NULL` y `evidence_type = LIVE_OBSERVATION`, fabricando evidencia primaria inexistente.
- **Corrección ejecutada:** En `app/mri_autonomous/recovery_runner.py` (`persist_to_sqlite`), se preserva el campo `raw_source_id` proveniente de la observación hacia `mri_publications.raw_source_id`. Si la observación declara `CONTROLLED_FIXTURE` o `REPLAY`, dicho `evidence_type` se preserva intacto sin sobreescritura a `LIVE_OBSERVATION`.
- **Evidencia reproducible:** `evidence/mri_autonomous_closure_012/defect_3_evidence_provenance.json` y `test_03_raw_source_id_and_provenance_preservation_defect`.

### Defecto 4: Deduplicación Comercial por SKU e Identidad Preservando Multi-Pertenencia
- **Fallo previo (Codex 011):** Ítems duplicados en el feed público generaban múltiples entidades de publicación idénticas en lugar de consolidar una única identidad comercial con multi-pertenencia a categorías, promociones y sellers. Además, se filtraron URLs con subdominios provisionales (`staging.ccom-stg.paris.cl`).
- **Corrección ejecutada:**
  1. En `app/mri_autonomous/rea_paris_engine.py` (`harvest_sample_publications`), se indexan las publicaciones por SKU (`publications_by_sku`). Ante un SKU duplicado, se unifican las categorías (`groups`), sellers y promociones (`collections`) sin crear registros duplicados.
  2. Se sanitizan las URLs de staging convirtiendo `https://staging.ccom-stg.paris.cl/...` al dominio oficial limpio `https://www.paris.cl/...`.
- **Evidencia reproducible:** `evidence/mri_autonomous_closure_012/defect_4_sku_deduplication.json` y `test_04_sku_deduplication_counterexample_defect`.

### Defecto 5: Integración Operativa de `REAParisEngine` con Persistencia, API y Dashboard
- **Fallo previo (Codex 011):** `REAParisEngine` operaba de forma aislada sin adaptador de persistencia hacia el modelo SQLite de MRI ni endpoint dedicado en el API/dashboard.
- **Corrección ejecutada:**
  1. Se implementó `persist_to_mri_sqlite(...)` en `app/mri_autonomous/rea_paris_engine.py`, mapeando las publicaciones normalizadas a `mri_publications`, `mri_runs` y entidades comerciales en SQLite `visibility.db`.
  2. Se agregó el endpoint `@app.get("/api/rea/paris")` en `app/mri_dashboard/mri_api.py`, permitiendo consultar el estado, métricas y publicaciones descubiertas por REA para Paris.cl.
  3. Se desacoplaron las instancias globales de `ExperienceStore` y `AcquisitionRecoveryRunner` en `mri_api.py` mediante getters perezosos (`get_experience_store()`, `get_recovery_runner()`), garantizando el correcto funcionamiento bajo modo test aislado.
- **Evidencia reproducible:** `evidence/mri_autonomous_closure_012/defect_5_rea_mri_api_integration.json` y `test_05_rea_paris_engine_api_presentation_integration`.

---

## 3. Verificación de Checkout Limpio e Inmutabilidad de VA

- **Catálogo Maestro Reproducible:** Se versionó `data/master_catalog_fixture.json` y se ajustó `get_master_catalog()` en `mri_api.py` para utilizar dicho fallback reproducible en entornos limpios donde no esté disponible `Actualización masiva de productos.xlsx`.
- **Inviolabilidad de Visual Auditor (VA Frozen):**
  ```bash
  git diff origin/main -- app/auditor/ app/scrapers/ app/core/
  # Resultado: 0 diferencias (cero modificaciones)
  ```
- **Preservación Histórica:**
  - El baseline de 2.533 registros históricos (2.489 publicaciones + 44 históricas) en la corrida `run_va_mri_operational_integration_1792000336` permanece 100% intacto y verificado por `test_historical_preservation_2533_records`.

---

## 4. Matriz de Ejecución de Pruebas

| Suite de Pruebas | Archivo | Pruebas | Estado |
|---|---|---|---|
| Cierre Funcional MRI-012 | `tests/test_mri_autonomous_closure_012.py` | 5 | **PASSED** (100%) |
| Reparación Integral MRI-009 | `tests/test_mri_autonomous_repair_009.py` | 10 | **PASSED** (100%) |
| Descubrimiento REA MRI-010 | `tests/test_mri_rea_discovery_010.py` | 7 | **PASSED** (100%) |
| **Total General** | **22 pruebas ejecutadas** | **22** | **100% PASS (0 fallos)** |

---

## 5. Reporte Estándar de Cierre

```text
TASK_ID=MRI-AUTONOMOUS-CLOSURE-012
STATUS=PASS
CODE_SHA=6cea1fa8acaed311eb9f658f4f7c629fd6ca1be4
PRODUCTION_ISOLATION=VERIFIED_AT_CONNECTION_LEVEL
COVERAGE_PERSISTENCE=VERIFIED_PAGE_BUDGET_EXCEEDED_PRESERVED
EVIDENCE_PROVENANCE=VERIFIED_RAW_SOURCE_ID_AND_FIXTURE_PRESERVED
DEDUPLICATION=VERIFIED_SKU_IDENTITY_AND_MULTI_MEMBERSHIP_MERGED
REA_MRI_INTEGRATION=VERIFIED_ADAPTER_SQLITE_API_DASHBOARD
API_PRESENTATION=VERIFIED_ENDPOINT_REA_PARIS_200_OK
CLEAN_CHECKOUT=VERIFIED_VERSIONED_FIXTURE_NO_PRIVATE_LEAKS
HISTORY_2533=VERIFIED_INTACT_2489_PUBS_44_HIST
VA_DIFF=0_FILES_CHANGED_FROZEN
TESTS_PASSED=22
TESTS_FAILED=0
FIRST_UNRESOLVED_FAILURE=NONE
NEXT_EXACT_ACTION=CODEX_FINAL_VALIDATION
```
