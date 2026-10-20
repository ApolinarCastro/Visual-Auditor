# VISUAL AUDITOR — INFORME ÚNICO DE CIERRE INTEGRAL (MRI-022 & MRI-023)

**Ejecutor:** ANTIGRAVITY  
**Auditor independiente:** CODEX  
**Proyecto:** Visual Auditor / Marketplace Research Intelligence  
**Rama:** `fix/mri-022-relational-recovery`  
**SHA Entregado y Verificado en Origen:** `0870003ebf8854b976233fd67d80a8bc0ea0a631`  
**Fecha:** 2026-10-20  

---

## 1. RESUMEN EJECUTIVO Y ESTADO DE CIERRE

En estricto cumplimiento de la **Orden Única de Cierre Integral**, se han resuelto de manera definitiva y conjunta todos los defectos materiales identificados en `MRI_CODEX_FINAL_INTEGRITY_GATE_032.md` y dictámenes anteriores, integrando plenamente las capacidades de **MRI-023** en el ejecutor autónomo, garantizando la preservación lógica y física de Visual Auditor (VA) y manteniendo intactas las 2.533 observaciones históricas originales.

No se crearon nuevos proyectos, no se abrieron nuevos `MRI-XXX`, no se alteraron las rutas de producción y se verificó que el repositorio permanezca en un estado determinista, limpio y auditable.

---

## 2. MATRIZ DE CIERRE INTEGRAL DE DEFECTOS

| ID Defecto | Fuente / Dictamen | Causa Raíz Exacta | Corrección Implementada | Pruebas y Evidencias | Estado |
|---|---|---|---|---|---|
| **ATOMICITY-CLEANUP-032** | `MRI_CODEX_FINAL_INTEGRITY_GATE_032` (Caso CREATE + ROLLBACK TO denegados) | En `_init_sqlite_tables`, el bloque `except` ejecutaba incondicionalmente `RELEASE` aun cuando `ROLLBACK TO SAVEPOINT` hubiese fallado, lo cual confirmaba DDL parcial (`mri_runs`) en savepoints de nivel superior cuando no había transacción externa. | Solo se intenta `RELEASE` si `ROLLBACK TO` tuvo éxito. Si `ROLLBACK TO` falla y la transacción es propia del runner, se ejecuta `conn.rollback()` directo y se propaga el error con causa. Si es del llamador, no se hace release y se propaga explícitamente el fallo encadenado (`raise cleanup_err from ex`). | `tests/test_mri_022_relational_recovery.py::test_rollback_to_authorization_denial_does_not_commit_partial_ddl` (0 durable tables tras fallo con y sin tx previa). | **RESUELTO** |
| **PREEXISTING-SCHEMA-032** | `MRI_CODEX_FINAL_INTEGRITY_GATE_032` (Sección 3: Estructura incompatible) | `CREATE TABLE IF NOT EXISTS` ignoraba silenciosamente tablas preexistentes con esquemas incompatibles (p. ej. `mri_runs` sin PRIMARY KEY o `mri_publications` sin FK a productos), permitiendo inconsistencias posteriores. | Se incorporó una validación previa de equivalencia estructural en `_init_sqlite_tables` que inspecciona `PRAGMA table_info`, `PRAGMA foreign_key_list` e `PRAGMA index_list/index_info`. Ante tablas incompatibles con FK activas, se levanta inmediatamente `sqlite3.IntegrityError` bloqueando la operación sin mutaciones. | `tests/test_mri_022_relational_recovery.py::test_preexisting_incompatible_schema_rejection` (bloqueo verificado de `missing_pk` y `weak_publications`). | **RESUELTO** |
| **RELATIONAL-FK-031** | `MRI_CODEX_RELATIONAL_RECOVERY_GATE_028` / Gate 030 | Ausencia de claves foráneas históricas en tablas hijas de publicaciones y categorías. | Restauración de las 6 relaciones canónicas completas con integridad referencial estricta y control huérfano. | `test_relational_model_and_foreign_keys` y harness `check_fk_persistence.py` de Codex (6 relaciones, 6 rechazos huérfanos, foreign_key_check vacío). | **CERTIFICADO (PASS)** |
| **COMMERCIAL-INTEGRITY-026** | `MRI_CODEX_CATEGORY_ISOLATION_GATE_026` / Gate 027 | Contaminación de categorías entre corridas A/B/C y estados comerciales no aislados. | Aislamiento estricto por corrida en `mri_run_marketplace_states` y consultas categorizadas referenciadas a la corrida correspondiente. | Verificado en Test 1 a Test 5 de `test_mri_022_relational_recovery.py` y suite de regresión focalizada de Codex (PASS). | **CERTIFICADO (PASS)** |
| **RIPLEY-TRUTH-027** | `MRI_CODEX_FINAL_INTEGRITY_GATE_027` | Presentación de conteos estáticos de referencia como publicaciones actuales en Ripley cuando no hubo adquisición. | Cero publicaciones (`total_brand_publications = 0`, `categories = []`, `publications_count = 0`) ante bloqueos, con estado explícito `SOURCE_BLOCKED`. | Verificado en Test 4 y Test 5 de `test_mri_022_relational_recovery.py` y suite de regresión de Codex (PASS). | **CERTIFICADO (PASS)** |
| **MRI-023-CAPABILITY-INTEGRATION** | Requisito Mandatorio Orden Única | Módulos de Capability Registry, Strategy Selector y Stealth Browser MCP no estaban plenamente integrados en el runner autónomo principal. | Integración completa de `CapabilityRegistry` y `StrategySelector` en `AutonomousMultiMarketplaceRunner`. Registro y reporte de decisiones en `decisions_log`, circuit breaker ante fallos y adaptación de `StealthBrowserMCPAdapter` con allowlist y revocación fail-closed. | `tests/test_mri_capability_registry_023.py` (T1–T8) y ejecución de corrida autónoma en runner. | **RESUELTO** |
| **PRODUCTION-ATTRIBUTION-030** | `MRI_CODEX_FINAL_INTEGRITY_GATE_032` (Sección 5) | Modificación física de `data/sqlite/visibility.db` durante MRI-030 requería atribución forense formal. | Atribución documentada y corroborada: procesos background PID 26300 y 29328 ejecutando `run.py dashboard` y auditorías programadas de VA (Mercado Libre, Paris, Falabella, Ripley) registraron escrituras en `audits`, `product_snapshots` y `health_log`, seguidas de `SQLiteManager.prune_and_optimize()` con VACUUM a las 13:32, 13:42, 13:43 y 13:55. Las tablas `mri_*` y las 2.533 observaciones permanecieron 100% inalteradas. | Corroborado por `production_forensics.json` de Codex y verificación de hash lógico idéntico. | **DOCUMENTADO Y VERIFICADO** |

---

## 3. INTEGRACIÓN EFECTIVA DE MRI-023 COMO SISTEMA OPERATIVO

1. **Capability Registry (`app/mri_autonomous/capability_registry.py`)**:
   - Registro dinámico y consulta de capacidades para los 4 marketplaces (Paris, Ripley, Falabella, Mercado Libre).
   - Metadatos de adaptadores: `CDP_API_PUBLIC` (Constructor.io), `CONTROLLED_REPLAY` (HAR), `HTTP_SSR` (__NEXT_DATA__), `HEADLESS_PLAYWRIGHT`, y `STEALTH_MCP`.
   - Circuit Breaker determinista: tras 3 fallos consecutivos transiciona a `BLOCKED`, excluyendo la herramienta de ejecuciones y promoviendo alternativas.

2. **Strategy Selector (`app/mri_autonomous/strategy_selector.py`)**:
   - Conectado directamente al constructor de `AutonomousMultiMarketplaceRunner`.
   - Selección guiada por salud (`HEALTHY` > `DEGRADED`), costo operativo (`cost_weight`), y tasa de éxito histórica.
   - Enrutamiento de alternativas automáticas (`fallback_chain`) en cada paso de adquisición.

3. **Stealth Browser MCP Adapter (`app/mri_autonomous/mcp_adapters/stealth_browser_adapter.py`)**:
   - Validación estricta de dominios autorizados (`paris.cl`, `falabella.com`, `mercadolibre.cl`, `simple.ripley.cl`, `ripley.cl`).
   - Control de revocación inmediata fail-closed (`revoke_permissions()`).
   - Captura de evidencias con cálculo criptográfico SHA-256 sobre archivos persistidos en `evidence/mri_stealth_mcp_captures/` y bitácora de auditoría inmutable.

4. **Flujo Integrado en el Runner**:
   - En `execute_autonomous_order()`, cada marketplace consulta `self.selector.select_strategy()`, registra la decisión y su cadena de contingencia en `decisions_log`, ejecuta la adquisición autorizada, persiste el resultado relacional y retroalimenta la salud en el registro mediante `report_outcome()`.

---

## 4. RESULTADOS DE LA BATERÍA DE PRUEBAS DE ACEPTACIÓN

Se ejecutó la suite completa de 17 pruebas unitarias y de integración end-to-end con resultado **100% PASS**:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\ASUS Zenbook\Documents\Visibility Auditor
plugins: anyio-4.13.0, asyncio-1.4.0
collected 17 items

tests\test_mri_022_relational_recovery.py .........                      [ 52%]
tests\test_mri_capability_registry_023.py ........                       [100%]

============================= 17 passed in 14.59s =============================
```

### Desglose de Pruebas:
- **`test_mri_022_relational_recovery.py`**:
  1. `test_relational_model_and_foreign_keys`: PASS (claves foráneas activadas y modelo padre/hijo intacto).
  2. `test_idempotent_initialization_preserves_runs`: PASS (no destructivo, preserva datos e índices).
  3. `test_four_independent_marketplace_states`: PASS (4 estados independientes por corrida en `mri_run_marketplace_states`).
  4. `test_ripley_truth_no_ghost_publications`: PASS (cero publicaciones fantasma, SOURCE_BLOCKED).
  5. `test_ripley_empty_run_preservation_and_api_scoping`: PASS (corridas vacías visibles en API sin datos estáticos).
  6. `test_category_isolation_abc_preserved`: PASS (aislamiento de categorías entre corridas A/B/C).
  7. `test_persistor_atomicity_and_connection_lifecycle`: PASS (cierre de conexiones e integridad ante fallos).
  8. `test_rollback_to_authorization_denial_does_not_commit_partial_ddl`: PASS (contraejemplo Codex Gate 032: nunca ejecuta RELEASE tras fallo de ROLLBACK TO).
  9. `test_preexisting_incompatible_schema_rejection`: PASS (rechazo explícito de esquemas incompatibles preexistentes).

- **`test_mri_capability_registry_023.py`**:
  1. `test_T1_registry_initialization_and_matrix_completeness`: PASS (matriz completa en los 4 marketplaces).
  2. `test_T2_capability_registration_and_lookup`: PASS (registro y búsqueda dinámica).
  3. `test_T3_circuit_breaker_and_health_reporting`: PASS (degradación a BLOCKED y recuperación).
  4. `test_T4_strategy_selection_deterministic_ordering`: PASS (ordenamiento por costo y promoción de fallbacks).
  5. `test_T5_strategy_selector_mcp_gating`: PASS (gating estricto de adaptadores MCP).
  6. `test_T6_stealth_browser_mcp_capture_and_hashing`: PASS (captura real, persistencia y hash SHA-256).
  7. `test_T7_stealth_browser_mcp_permission_revocation`: PASS (revocación fail-closed y reautorización).
  8. `test_T8_stealth_browser_mcp_unauthorized_domain_block`: PASS (bloqueo fuera de dominios autorizados).

---

## 5. PROTECCIÓN DE PRODUCCIÓN Y OBSERVACIONES HISTÓRICAS

- **Preservación de 2.533 Observaciones Originales**:
  - Run ID: `run_va_mri_operational_integration_1792000336`
  - Conteo total: **2.533** registros (2.489 activos + 44 históricos).
  - Hash criptográfico SHA-256 verificado:
    `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`
  - Integridad física: `PRAGMA integrity_check = ok`, `PRAGMA foreign_key_check = []`.

- **Aislamiento Total de Visual Auditor (VA)**:
  - Diff en código productivo de VA frente a la referencia `3e5d058aa3c0b9b388bab990b14d8cc134627d2e`: **CERO CAMBIOS** (`git diff` vacío en `app/auditor`, `app/scrapers`, `app/core`, `app/dashboard`, `app/loaders`, `app/config`).
  - Barrera de escritura pre-connect activa (`StorageConfig.assert_write_allowed`).

---

## 6. ENTREGA REMOTA

- **Rama:** `fix/mri-022-relational-recovery`
- **SHA Remoto en GitHub:** `0870003ebf8854b976233fd67d80a8bc0ea0a631`
- **Estado de Trabajo:** Limpio y comiteado sin artefactos temporales en control de versiones.

Queda a disposición de **CODEX** para la auditoría independiente integral final.
