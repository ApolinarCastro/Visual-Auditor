# MRI-TARGETED-REPAIR-017 — Informe de Reparación Quirúrgica

**Fecha:** 2026-10-16  
**Ejecutor:** Antigravity  
**Referencia:** `MRI_CODEX_CRITICAL_VALIDATION_016.md`  
**Rama Base:** `feature/mri-critical-closure-015`  
**Rama de Entrega:** `feature/mri-targeted-repair-017`  
**Commit Remoto SHA:** `cdff0775ef777accde69e8e1f585b1a1a1b18715`  
**Estado:** REPAIRED / ALL VERIFIED / ZERO REGRESSIONS

---

## 1. RESUMEN EJECUTIVO

En estricto cumplimiento del mandato `MRI-TARGETED-REPAIR-017` y de las restricciones operacionales:
1. Se corrigieron **exclusivamente los 3 defectos materiales** identificados en Codex 016 sin alterar ninguna capacidad previamente certificada.
2. Se mantuvieron intactas las protecciones de Visual Auditor (`git diff origin/main -- app/auditor/ app/scrapers/ app/core/` = **0 diff**).
3. Se conservaron íntegramente las **2.533 observaciones históricas originales** en `visibility.db` (2.489 activas + 44 históricas).
4. Se verificaron todas las pruebas de aislamiento de producción (CWD-independent) y suites de regresión (009, 012, 015, 017), aprobando al 100%.

---

## 2. DETALLE DE CORRECCIÓN DE LOS TRES DEFECTOS

### Defecto 1 (F1): Procedencia HAR Primaria e Integridad Criptográfica
- **Causa Raíz en 016:** La persistencia utilizaba identificadores genéricos sintéticos (`HAR-REPLAY-{sku}`) sin vincular la evidencia primaria con su hash criptográfico SHA-256 verificado, la ruta del archivo físico y la fecha original declarada en el HAR (`startedDateTime`), arriesgando la invención de procedencia o discrepancias entre la captura original y el procesamiento posterior.
- **Corrección Quirúrgica Aplicada:**
  - Se implementó la resolución e integridad criptográfica en `app/mri_autonomous/rea_paris_engine.py`:
    - Función de resolución `_resolve_har_provenance()` que localiza el archivo primario `paris_search_capture.har`, recalcula dinámicamente su SHA-256 (`1ed56cc6a9453d6b67a64f6c7566b2496a2294db661ff3f7fc3e9e5077483ed9`) y extrae `startedDateTime` (`2026-10-15T18:55:57.608368+00:00`).
    - En caso de ausencia física o alteración, declara explícitamente `raw_source_id = "PROVENANCE_INCOMPLETE:{sku}"` sin inventar valores por defecto.
    - Se persiste en `mri_publications.commercial_attributes`: `source_file_sha256`, `source_file_path`, `source_captured_at`.
    - La propiedad `raw_source_id` se vincula formalmente con formato `HAR-REPLAY-SHA256:{sha[:16]}:{sku}` y `evidence_type = "CONTROLLED_REPLAY"`.
  - El modal del dashboard (`app/mri_dashboard/templates/index.html`) presenta el desglose exacto de evidencia primaria auditada.

### Defecto 2 (F2): Historial y Pertenencias Comerciales Aisladas por Corrida (`run_id`)
- **Causa Raíz en 016:** Al re-ejecutar una publicación existente en una nueva corrida (`run_id`), los enlaces de categoría en `mri_publication_categories` conservaban vínculos de categorías previas como activos, provocando que la publicación consultara categorías de corridas anteriores mezclando estados comerciales.
- **Corrección Quirúrgica Aplicada:**
  - En `app/mri_autonomous/rea_paris_engine.py` (`persist_to_mri_sqlite`):
    - Al detectar que una publicación ya existía en un `run_id` anterior, archiva los enlaces de categoría previos en `mri_historical_publication_categories` y remueve los vínculos de categoría activos previos (`DELETE FROM mri_publication_categories WHERE publication_id = ?`), asegurando que solo las categorías de la corrida en curso queden asociadas a la publicación.
  - En `app/mri_dashboard/mri_api.py` (`fetch_run_publications`):
    - Se aisló la consulta de categorías para filtrar exclusivamente `WHERE status = 'ACTIVE'`, garantizando que corridas sucesivas recuperen única y estrictamente sus pertenencias comerciales.

### Defecto 3 (F3): Representación Explícita de Conteos Desconocidos (`UNKNOWN`/`null`)
- **Causa Raíz en 016:** Cuando una fuente externa no entregaba resultados verificables o devolvía un payload vacío `{}` sin llaves de resultados, el motor y la API asignaban `0` por defecto (`.get(..., 0)`), enmascarando fuentes fallidas o no verificadas como si hubiesen acreditado formalmente cero productos.
- **Corrección Quirúrgica Aplicada:**
  - En `REAParisEngine` (`get_brand_summary`, `get_seller_summary`):
    - Si la respuesta no contiene `total_num_results`, retorna `None` (`UNKNOWN`) en lugar de `0`.
  - En `/api/rea/paris` (`app/mri_dashboard/mri_api.py`):
    - Si `total_brand` o `total_official_seller` son `None`, la API responde con `null` en JSON y `status = "NO_EVIDENCE_RECORDED"`.
    - El valor numérico `0` se reserva estricta y exclusivamente para respuestas válidas y certificadas que acrediten ausencia de resultados.
    - Se replica la distinción en `app/mri_dashboard/templates/index.html` para presentación visual en el dashboard.

---

## 3. EVIDENCIA DE EJECUCIÓN Y VALIDACIÓN

### A. Ejecución de la Suite Dirigida (`tests/test_mri_targeted_repair_017.py`)
```bash
python -m pytest tests/test_mri_targeted_repair_017.py -v
```
**Resultado:**
```text
tests/test_mri_targeted_repair_017.py::TestMRITargetedRepair017::test_01_har_provenance_integrity_and_capture_date PASSED [ 33%]
tests/test_mri_targeted_repair_017.py::TestMRITargetedRepair017::test_02_run_scoped_memberships_isolation PASSED [ 66%]
tests/test_mri_targeted_repair_017.py::TestMRITargetedRepair017::test_03_empty_source_returns_unknown_null_counts PASSED [100%]
============================== 3 passed in 16.49s ==============================
```

### B. Ejecución de No-Regresión 015 (`tests/test_mri_critical_closure_015.py`)
```bash
python -m pytest tests/test_mri_critical_closure_015.py -v
```
**Resultado:**
```text
tests/test_mri_critical_closure_015.py::TestMRICriticalClosure015::test_01_cwd_independent_production_isolation PASSED [ 16%]
tests/test_mri_critical_closure_015.py::TestMRICriticalClosure015::test_02_recovery_runner_defined_and_api_offline_storage PASSED [ 33%]
tests/test_mri_critical_closure_015.py::TestMRICriticalClosure015::test_03_rea_master_catalog_identity_and_provenance PASSED [ 50%]
tests/test_mri_critical_closure_015.py::TestMRICriticalClosure015::test_04_rea_observation_history_preservation PASSED [ 66%]
tests/test_mri_critical_closure_015.py::TestMRICriticalClosure015::test_05_coverage_filter_and_dashboard_representation PASSED [ 83%]
tests/test_mri_critical_closure_015.py::TestMRICriticalClosure015::test_06_empty_upstream_not_declared_operational PASSED [100%]
============================== 6 passed in 21.73s ==============================
```

### C. Ejecución de Regresión Histórica MRI (009 y 012)
```bash
python -m pytest tests/test_mri_autonomous_closure_012.py tests/test_mri_autonomous_repair_009.py -v
```
**Resultado:**
```text
tests/test_mri_autonomous_closure_012.py::TestMRIAutonomousClosure012::test_01_experience_store_connection_revalidation_defect PASSED [  6%]
tests/test_mri_autonomous_closure_012.py::TestMRIAutonomousClosure012::test_02_terminal_state_propagation_defect PASSED [ 13%]
tests/test_mri_autonomous_closure_012.py::TestMRIAutonomousClosure012::test_03_raw_source_id_and_provenance_preservation_defect PASSED [ 20%]
tests/test_mri_autonomous_closure_012.py::TestMRIAutonomousClosure012::test_04_sku_deduplication_counterexample_defect PASSED [ 26%]
tests/test_mri_autonomous_closure_012.py::TestMRIAutonomousClosure012::test_05_rea_paris_engine_api_presentation_integration PASSED [ 33%]
tests/test_mri_autonomous_repair_009.py::test_production_write_barrier_rejection PASSED [ 40%]
tests/test_mri_autonomous_repair_009.py::test_historical_preservation_2533_records PASSED [ 46%]
tests/test_mri_autonomous_repair_009.py::test_position_accuracy_distinct_positions PASSED [ 53%]
tests/test_mri_autonomous_repair_009.py::test_coverage_preserves_page_budget_exceeded PASSED [ 60%]
tests/test_mri_autonomous_repair_009.py::test_parent_variant_resolution PASSED [ 66%]
tests/test_mri_autonomous_repair_009.py::test_rejection_of_fraction_collisions_3_4_vs_1_2 PASSED [ 73%]
tests/test_mri_autonomous_repair_009.py::test_brand_corridor_separation_ripley PASSED [ 80%]
tests/test_mri_autonomous_repair_009.py::test_primary_evidence_integrity PASSED [ 86%]
tests/test_mri_autonomous_repair_009.py::test_clean_checkout_modules_presence PASSED [ 93%]
tests/test_mri_autonomous_repair_009.py::test_zero_va_modifications PASSED [100%]
============================== 15 passed in 17.37s ==============================
```

### D. Verificación de Preservación de Observaciones Históricas (2.533 registros)
```python
# Consulta directa de solo lectura sobre data/sqlite/visibility.db y backup_production_009/visibility.db
# Run ID: run_va_mri_operational_integration_1792000336
# Activas: 2.489
# Históricas: 44
# Total: 2.533 observaciones intactas
```

### E. Verificación de Congelamiento de Visual Auditor
```bash
git diff origin/main -- app/auditor/ app/scrapers/ app/core/
# Output: (vacío, 0 líneas modificadas)
```

---

## 4. ARCHIVOS MODIFICADOS Y CAMBIOS EXACTOS

- `app/mri_autonomous/rea_paris_engine.py`:
  - Incorporación de `_resolve_har_provenance()` con cálculo de SHA-256 e inspección de `startedDateTime`.
  - Atributos de procedencia en `NormalizedPublication` (`evidence_type`, `raw_source_id`, `source_file_path`, `source_file_sha256`, `source_captured_at`).
  - Declaración explícita de `PROVENANCE_INCOMPLETE` si falta evidencia primaria.
  - Aislamiento de categorías por corrida en `persist_to_mri_sqlite()`.
  - Retorno de `None` para conteos desconocidos en `get_brand_summary()` y `get_seller_summary()`.
- `app/mri_dashboard/mri_api.py`:
  - Filtrado `WHERE status = 'ACTIVE'` en `fetch_run_publications()` para evitar contaminación de pertenencias comerciales entre corridas.
  - Distinción explícita en `/api/rea/paris` entre conteos no verificables (`null`, `NO_EVIDENCE_RECORDED`) y cero certificado (`0`).
- `app/mri_dashboard/templates/index.html`:
  - Visualización explícita de Procedencia Primaria HAR (SHA-256, path y fecha de captura declarada).
- `tests/test_mri_targeted_repair_017.py`:
  - Suite de pruebas de validación reproducible para los 3 defectos.

---

## 5. CONCLUSIÓN Y SIGUIENTE PASO

La reparación quirúrgica `MRI-TARGETED-REPAIR-017` se encuentra lista, verificada de forma determinista y publicada en el remoto:

- **Branch:** `feature/mri-targeted-repair-017`
- **Commit:** `cdff0775ef777accde69e8e1f585b1a1a1b18715`

Queda a disposición para la validación independiente focalizada por parte de Codex y su posterior conciliación con MRI-014. No se iniciará ninguna otra fase de arquitectura.
