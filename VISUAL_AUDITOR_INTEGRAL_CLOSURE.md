# VISUAL AUDITOR — INFORME ÚNICO DE CIERRE INTEGRAL (MRI-022 & MRI-023)

**Ejecutor:** ANTIGRAVITY  
**Auditor independiente:** CODEX  
**Proyecto:** Visual Auditor / Marketplace Research Intelligence  
**Rama:** `fix/mri-022-relational-recovery`  
**Base revisada:** `923d02fcb9fc9f28abe2800082524626aa279e0e`  
**SHA Final Entregado:** `2f9c2e7afad1940bb20f1f1f41b28761066a610e`  
**Fecha:** 2026-10-20  

---

## 1. RESUMEN EJECUTIVO Y ESTADO DE CIERRE

En cumplimiento estricto del mandato de cierre integral sin reaperturas, se han corregido los 5 defectos obligatorios identificados sobre la línea de trabajo existente `fix/mri-022-relational-recovery`:

1. **Stealth Browser MCP**: Se eliminó totalmente el transporte simulado por `urllib` sustituyéndolo por un cliente real stdio JSON-RPC conectado al servidor Stealth Browser MCP nativo (`obscura.exe mcp --stealth`). Incorpora negociación de protocolo (`initialize`), verificación de capacidades y herramientas (`tools/list`), invocación verificable (`browser_navigate`, `browser_snapshot`, `browser_evaluate`, `browser_network_requests`, `browser_close`), validación estricta de esquema HTTPS, comprobación de dominio exacto o subdominio autorizado (`paris.cl`, `falabella.com`, `mercadolibre.cl`, `ripley.cl`), detección de escape por redirección mediante inspección activa de `browser_tab_list`, revocación de permisos previa y mid-operación (fail-closed) y persistencia aislada de artefactos con hash criptográfico SHA-256.
2. **Selector Autónomo y Despacho Real**: Se modificó `AutonomousMultiMarketplaceRunner` para que la estrategia seleccionada determine efectivamente la capacidad y adaptador ejecutado (`investigate_ripley(run_id, strategy=...)` despachando a `StealthBrowserMCPAdapter` en modo `STEALTH_MCP`). Se implementó una prueba integrada que demuestra de principio a fin el ciclo: selección inicial -> ejecución -> fallo acumulado -> bloqueo de capacidad -> fallback dinámico a MCP -> ejecución de herramienta real -> resultado exitoso -> retroalimentación de salud en el registro.
3. **Registry Sin Valores Ficticios**: Se erradicaron los valores iniciales predeterminados ficticios de disponibilidad (`health=HEALTHY` y `success_rate=1.0`). Todas las capacidades no comprobadas inicializan obligatoriamente en `CapabilityHealth.UNKNOWN` con `success_rate=0.0`. Se implementó el motor de sondeo `probe_capability()` y `probe_all_capabilities()` que comprueba binarios reales (`obscura.exe`), dependencias de entorno (`playwright`), archivos primarios HAR y endpoints, asignando el estado verificado (`HEALTHY`, `DEGRADED` o `DISABLED`).
4. **Persistencia SQLite Atómica y Preexistencias (Dictamen MRI-032)**:
   - Se mantienen y verifican íntegramente los contraejemplos de MRI-032:
     - Bloqueo de confirmación parcial: ante fallos en DDL y posterior denegación de `ROLLBACK TO SAVEPOINT`, el runner jamás ejecuta `RELEASE`; ejecuta rollback de la conexión si es propia o propaga el fallo encadenado si es del llamador, dejando 0 tablas durables.
     - Detección y rechazo estricto de esquemas preexistentes incompatibles (`mri_runs` sin PRIMARY KEY y `mri_publications` sin clave foránea a `mri_products`) mediante `sqlite3.IntegrityError` con `PRAGMA foreign_keys = ON`.
5. **Aceptación Original T1–T8 y Preservación de Observaciones**:
   - Se verificaron los requisitos originales T1–T8 en `tests/test_mri_capability_registry_023.py` sin renumerarlos ni omitirlos, más la prueba integrada de despacho y fallback.
   - Se comprobó la integridad intacta de las 2.533 observaciones históricas (2.489 activas en `run_va_mri_operational_integration_1792000336` + 44 históricas) con hash lógico inalterado.
   - Cero modificaciones a código productivo de Visual Auditor (VA) en `app/auditor`, `app/scrapers`, `app/dashboard`, etc.

---

## 2. MATRIZ DE RESOLUCIÓN DE DEFECTOS OBLIGATORIOS

| Defecto Obligatorio | Requisito / Dictamen | Causa Previa | Solución Verificada | Evidencia de Ejecución | Estado |
|---|---|---|---|---|---|
| **1. Stealth Browser MCP** | Sustituir transporte `urllib` por conexión real a servidor MCP stdio con negociación, sesión, HTTPS, redirecciones, revocación y hash SHA-256. | `StealthBrowserMCPAdapter` realizaba peticiones mediante `urllib.request` simulando una interfaz MCP. | Implementación de cliente stdio JSON-RPC contra `obscura.exe mcp --stealth`. Ciclo completo: handshake `initialize`, verificación `tools/list`, invocación de herramientas `browser_navigate`, `browser_tab_list`, `browser_network_requests`, `browser_snapshot`, `browser_close`. Validación HTTPS, comprobación de dominio exacto y subdominios autorizados, bloqueo de escape por redirección, control de revocación en cada llamada RPC y almacenamiento aislado de evidencias. | `tests/test_mri_capability_registry_023.py::test_T6_stealth_browser_mcp_capture_and_hashing`<br>`tests/test_mri_capability_registry_023.py::test_T7_stealth_browser_mcp_permission_revocation`<br>`tests/test_mri_capability_registry_023.py::test_T8_stealth_browser_mcp_unauthorized_domain_block` | **RESUELTO (REAL MCP)** |
| **2. Selector Autónomo** | La capacidad elegida debe determinar efectivamente el adaptador ejecutado; demostrar selección, fallo, fallback, resultado y actualización de experiencia. | El runner registraba el `strategy_id` pero los métodos `investigate_*` ejecutaban siempre la misma lógica fija. | Se integró el parámetro `strategy: Optional[SelectedStrategy]` en el runner. Si la estrategia asigna `STEALTH_MCP`, se invoca efectivamente `StealthBrowserMCPAdapter`. Se conectó el selector al registro para degradar por fallos, promover fallbacks y retroalimentar salud tras ejecución real. | `tests/test_mri_capability_registry_023.py::test_autonomous_strategy_dispatch_fallback_and_experience_update` (demostración integrada de selección -> fallo -> fallback -> ejecución MCP -> resultado -> experiencia). | **RESUELTO (INTEGRADO)** |
| **3. Capability Registry** | Eliminar valores iniciales ficticios de salud/éxito. Unverified debe permanecer `UNKNOWN`. Probing de dependencias y binarios reales. | Las capacidades inicializaban por defecto con `health=HEALTHY` y `success_rate=1.0` sin verificación. | Capacidades inicializan como `CapabilityHealth.UNKNOWN` con `success_rate=0.0`. Implementación de `probe_capability()` y `probe_all_capabilities()` que validan binarios reales (`obscura.exe`), librerías (`playwright`), HAR files y endpoints antes de asignar `HEALTHY`, `DEGRADED` o `DISABLED`. | `tests/test_mri_capability_registry_023.py::test_T1_registry_initialization_and_matrix_completeness` (verifica UNKNOWN inicial y transición por sondeo). | **RESUELTO (PROBE REAL)** |
| **4. SQLite Atomicity & Incompatible Schemas** | Mantener correcciones y comprobar contraejemplos de MRI-032 (RELEASE tras fallo de ROLLBACK TO, esquemas incompatibles, protección de tx del llamador). | `RELEASE` ejecutado tras fallo de `ROLLBACK TO` confirmaba DDL parcial; `IF NOT EXISTS` admitía esquemas sin PK o FK. | Reordenamiento estricto de bloques de excepción: `RELEASE` solo se invoca si `ROLLBACK TO` fue exitoso; en caso de fallo se ejecuta `conn.rollback()` (si es propia) o encadenamiento de error (si es del llamador). Validación de esquema preexistente mediante `PRAGMA foreign_key_list` y `PRAGMA table_info`. | `tests/test_mri_022_relational_recovery.py::test_rollback_to_authorization_denial_does_not_commit_partial_ddl`<br>`tests/test_mri_022_relational_recovery.py::test_preexisting_incompatible_schema_rejection` | **CERTIFICADO (PASS)** |
| **5. Aceptación Original T1–T8 y Observaciones** | Mantener pruebas T1–T8 intactas, 2.533 observaciones, 4 marketplaces, API e historial. | Riesgo de saltarse pruebas o simplificarlas. | Las pruebas T1–T8 se ejecutan íntegramente sobre las implementaciones reales de MCP y Registry, junto con la suite de 9 pruebas relacionales y transaccionales (18 pruebas en total). Las 2.533 observaciones en `data/sqlite/visibility.db` permanecen inalteradas con hash lógico verificado. | `pytest tests/test_mri_022_relational_recovery.py tests/test_mri_capability_registry_023.py` (18 passed). Verificación física SQLite (2.533 registros inalterados). | **CERTIFICADO (PASS)** |

---

## 3. ARQUITECTURA DETALLADA DEL STEALTH BROWSER MCP ADAPTER

El archivo `app/mri_autonomous/mcp_adapters/stealth_browser_adapter.py` opera mediante conexión stdio nativa:

```
+-----------------------------------------------------------------------------------------+
|                              StealthBrowserMCPAdapter                                   |
|                                                                                         |
|  1. Pre-Flight Boundary Checks:                                                         |
|     - Fail-Closed Permission Gate (is_permission_active() -> MCPPermissionRevokedError)  |
|     - Scheme Enforcement: strictly "https" (MCPUnauthorizedTargetError)                |
|     - Hostname Allowlist: exact or subdomain of authorized marketplaces                |
|       ["paris.cl", "falabella.com", "mercadolibre.cl", "ripley.cl"]                     |
|                                                                                         |
|  2. stdio JSON-RPC MCP Session Lifecycle:                                               |
|     - Process: obscura.exe mcp --stealth (pipes stdin/stdout/stderr)                    |
|     - Handshake: send initialize -> receive protocolVersion & serverInfo                |
|     - Tools Discovery: tools/list -> verify browser_navigate, browser_snapshot          |
|     - Mid-Operation Revocation Gate checked before every send_rpc() call                |
|     - Navigate: tools/call browser_navigate                                             |
|     - Redirect Validation: tools/call browser_tab_list -> parse active URL              |
|       * If redirected domain/scheme violates boundary -> close session & raise error     |
|     - Network Extraction: tools/call browser_network_requests -> HTTP status code       |
|     - Snapshot: tools/call browser_evaluate / browser_snapshot                          |
|     - Cryptographic Hash: SHA-256 computed on rendered bytes                            |
|     - Evidence Isolated: written to evidence/mri_stealth_mcp_captures/mcp_{sha[:16]}.html|
|     - Safe Shutdown: tools/call browser_close -> terminate process cleanly              |
+-----------------------------------------------------------------------------------------+
```

---

## 4. RESULTADOS DE VERIFICACIÓN Y PRUEBAS REPRODUCIBLES

### 4.1. Batería Completa de Pruebas Automatizadas (18/18 PASS)

Comando ejecutado:
```bash
python -m pytest tests/test_mri_022_relational_recovery.py tests/test_mri_capability_registry_023.py -v
```

Resultado obtenido:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\ASUS Zenbook\Documents\Visibility Auditor
plugins: anyio-4.13.0, asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False
collected 18 items

tests/test_mri_022_relational_recovery.py::test_relational_model_and_foreign_keys PASSED [  5%]
tests/test_mri_022_relational_recovery.py::test_four_marketplaces_independent_states PASSED [ 11%]
tests/test_mri_022_relational_recovery.py::test_ripley_run_scoped_truth_and_zero_static PASSED [ 16%]
tests/test_mri_022_relational_recovery.py::test_empty_runs_preserved_in_history_and_detail PASSED [ 22%]
tests/test_mri_022_relational_recovery.py::test_abc_category_isolation_preserved PASSED [ 27%]
tests/test_mri_022_relational_recovery.py::test_initialization_atomicity_and_caller_transaction PASSED [ 33%]
tests/test_mri_022_relational_recovery.py::test_persistor_atomicity_and_connection_lifecycle PASSED [ 38%]
tests/test_mri_022_relational_recovery.py::test_rollback_to_authorization_denial_does_not_commit_partial_ddl PASSED [ 44%]
tests/test_mri_022_relational_recovery.py::test_preexisting_incompatible_schema_rejection PASSED [ 50%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T1_registry_initialization_and_matrix_completeness PASSED [ 55%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T2_capability_registration_and_lookup PASSED [ 61%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T3_circuit_breaker_and_health_reporting PASSED [ 66%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T4_strategy_selection_deterministic_ordering PASSED [ 72%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T5_strategy_selector_mcp_gating PASSED [ 77%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T6_stealth_browser_mcp_capture_and_hashing PASSED [ 83%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T7_stealth_browser_mcp_permission_revocation PASSED [ 88%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T8_stealth_browser_mcp_unauthorized_domain_block PASSED [ 94%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_autonomous_strategy_dispatch_fallback_and_experience_update PASSED [100%]

============================= 18 passed in 29.93s =============================
```

### 4.2. Integridad de la Base de Datos Productiva

- **Base de Datos:** `data/sqlite/visibility.db`
- **Observaciones Históricas del Certificado:**
  - Activas (`run_id = 'run_va_mri_operational_integration_1792000336'`): **2.489**
  - Históricas (`mri_historical_publications`): **44**
  - Total Observaciones Comprobadas: **2.533**
  - Hash Lógico SHA-256: `49481608cb433a8438a7e1137507a6af94035d13ba7e8be94c7f6bea99a50b27` (idéntico e inalterado).
- **Aislamiento Total de Visual Auditor (VA)**:
  - `git diff origin/main -- app/auditor app/scrapers app/dashboard app/loaders app/config` devuelve **0 líneas modificadas**.

---

## 5. REPORTE DE ENTREGA Y COMMIT

- **Rama:** `fix/mri-022-relational-recovery`
- **Archivos Modificados:**
  1. `app/mri_autonomous/mcp_adapters/stealth_browser_adapter.py`
  2. `app/mri_autonomous/capability_registry.py`
  3. `app/mri_autonomous/autonomous_multimarketplace_runner.py`
  4. `tests/test_mri_capability_registry_023.py`
  5. `VISUAL_AUDITOR_INTEGRAL_CLOSURE.md`

El sistema se entrega cerrado, verificado y respaldado por evidencia demostrable para la auditoría integral independiente de **CODEX**.
