# VISUAL AUDITOR — INFORME ÚNICO DE CIERRE INTEGRAL (MRI-022 & MRI-023)
## CORRECCIÓN DEFINITIVA DE VERACIDAD OPERATIVA

**Ejecutor:** ANTIGRAVITY  
**Auditor independiente:** CODEX  
**Proyecto:** Visual Auditor / Marketplace Research Intelligence  
**Rama:** `fix/mri-022-relational-recovery`  
**Base revisada:** `40485b9e876cf4fdd46e1494da3374c0a71b127c`  
**Fecha:** 2026-10-20  

---

## 1. RESUMEN EJECUTIVO — CONTRATO DE VERACIDAD OPERATIVA

En cumplimiento estricto del mandato de veracidad operativa, sobre la misma rama y sin abrir nuevas fases MRI:

1. **Corrección de Ripley MCP y Veracidad de Publicaciones Adquiridas**:
   - Una captura técnica exitosa (código HTTP 200/403, outerHTML capturado, sha256 verificado y archivo físico persistido) **no equivale a publicaciones comerciales adquiridas**.
   - Con cero productos verificados (`len(sample_pubs) == 0`), el runner **no declara estado comercial `COMPLETED`** ni contabiliza éxito comercial en `CapabilityRegistry` (`report_outcome(success=False)`).
   - Se elimina la atribución de éxito ficticio cuando un adaptador solo obtiene un snapshot HTML sin ítems del catálogo.

2. **Separación Explícita de las 4 Dimensiones de la Corrida**:
   - **Éxito Técnico de Navegación**: Registrado en `res.evidence["technical_navigation_success"] = True` cuando el transporte o adaptador navegó e interactuó con la interfaz sin fallos de red.
   - **Evidencia Capturada**: Registrado en `res.evidence` con `raw_path`, `sha256`, `status_code`, `is_challenge` y metadatos verificables.
   - **Publicaciones Verificadas**: Registrado estrictamente en `res.publications_count = len(sample_pubs)`.
   - **Estado Comercial de la Corrida**:
     - `COMPLETED`: Únicamente si `publications_count > 0` con productos normalizados y persistidos.
     - `PARTIAL`: Si la navegación técnica ocurrió pero no se adquirieron publicaciones o la API requiere autenticación.
     - `SOURCE_BLOCKED`: Si se detectó un desafío anti-bot (Turnstile, Cloudflare challenge, 403 WAF) o barrera activa.

3. **Contrato de Veracidad Aplicado a los Cuatro Marketplaces**:
   - **Paris**: Requiere `publications_count > 0` tanto para Constructor.io API (`CDP_API_PUBLIC`) como para el feed HAR (`CONTROLLED_REPLAY`); en caso contrario rechaza la adquisición y reporta fallo en el registro.
   - **Falabella**: Requiere `publications_count > 0` tanto para SSR Next.js (`HTTP_SSR`) como para Playwright (`HEADLESS_PLAYWRIGHT`).
   - **Mercado Libre**: Requiere `publications_count > 0` para el scraper público headless y el adaptador MCP. El fallback de taxonomía oficial registra `PARTIAL` (reconociendo que la API de búsqueda requiere OAuth) sin declarar falsamente `COMPLETED`.
   - **Ripley**: Requiere `publications_count > 0` para Playwright y MCP. Si MCP obtiene un snapshot pero no hay productos, o Playwright es bloqueado por WAF/Turnstile, no declara `COMPLETED` y preserva la evidencia técnica como `PARTIAL` o `SOURCE_BLOCKED`.

4. **Prevención Preventiva de Acceso y Perímetro MCP**:
   - Se reforzó la prevención de navegación fuera de perímetro en `StealthBrowserMCPAdapter`:
     - Validación preventiva pre-despacho: verificación HTTPS obligatoria y pertenencia exacta a la lista autorizada (`paris.cl`, `falabella.com`, `mercadolibre.cl`, `ripley.cl`).
     - Detección preventiva de vectores de redirección abierta: se inspeccionan parámetros de consulta (`url`, `redirect`, `dest`, `target`, `next`, `goto`) antes de enviar comandos de navegación RPC; si apuntan fuera del perímetro autorizado, se lanza de inmediato `MCPUnauthorizedTargetError` **antes** de despachar la petición por la red.
     - Inspección posterior de pestañas (`browser_tab_list`) actúa como segundo cerrojo fail-closed de emergencia, cerrando la sesión con `browser_close`.
     - La capacidad MCP se mantiene explícitamente deshabilitada para navegación no acotada fuera del perímetro.

5. **Pruebas Negativas contra Falsos Positivos**:
   - **Prueba Negativa T10 (`test_T10_negative_empty_capture_no_false_positive_commercial_success`)**: Demuestra que un snapshot HTML con 200 OK pero cero productos verificados produce `res.status = 'PARTIAL'`, `res.publications_count = 0` y registra fallo en el `CapabilityRegistry`, sin atribuir éxito comercial.
   - **Prueba Negativa T11 (`test_T11_negative_waf_challenge_no_false_positive_commercial_success`)**: Demuestra que un bloqueo Turnstile / WAF (403 o desafío detectado) produce `res.status = 'SOURCE_BLOCKED'`, `res.publications_count = 0` y registra fallo en el circuito de salud del registro.

6. **Conservación de Regresiones y Hash Canónico de las 2.533 Observaciones**:
   - Algoritmo canónico de certificación de Codex Gate 025 verificado sobre `data/sqlite/visibility.db`:
     - Total observaciones: **exactamente 2.533** (2.489 en `mri_publications` + 44 en `mri_historical_publications`).
     - Hash SHA-256 canónico exacto: `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`.
   - Batería completa de pruebas: **21/21 PASSED** (9 relacionales + 12 de registro, selector, MCP y pruebas negativas).
   - Preservación absoluta de producción: `git diff origin/main -- app/auditor app/scrapers app/dashboard app/loaders app/config` = **0 líneas modificadas** (código original intacto).

---

## 2. MATRIZ DE OBSERVACIONES Y RESOLUCIÓN DEFINITIVA

| Requisito / Defecto | Causa Previa | Corrección Implementada | Evidencia Demostrada | Estado |
|---|---|---|---|---|
| **1. Ripley MCP: 0 productos != COMPLETED** | Con captura HTML exitosa pero 0 productos, el runner marcaba `status = 'COMPLETED'` y `registry.report_outcome(success=True)`. | Se condicionó el estado comercial y la actualización de salud a `publications_count > 0`. Con 0 productos verificados, se preserva la evidencia técnica pero se declara `PARTIAL` o `SOURCE_BLOCKED` y `report_outcome(success=False)`. | `tests/test_mri_capability_registry_023.py::test_T10_negative_empty_capture_no_false_positive_commercial_success` | **CORREGIDO Y VERIFICADO (PASS)** |
| **2. Separación de 4 dimensiones operativas** | Mezcla entre éxito de navegación HTTP y éxito comercial de adquisición. | Separación explícita en el modelo de resultado: `technical_navigation_success`, evidencia física con `sha256`, `publications_count` verificado, y `status` comercial (`COMPLETED`, `PARTIAL`, `SOURCE_BLOCKED`). | Verificado en runner y aserciones de prueba en los 4 marketplaces. | **CORREGIDO Y VERIFICADO (PASS)** |
| **3. Contrato en 4 marketplaces** | Inconsistencia entre adaptadores en París, Falabella, Mercado Libre y Ripley. | Regla universal aplicada a todos los adaptadores: ninguna corrida sin publicaciones verificadas computa `COMPLETED` ni suma éxito en el registro de capacidades. | Pruebas integradas y unitarias en `test_mri_capability_registry_023.py` (12/12 PASS). | **CORREGIDO Y VERIFICADO (PASS)** |
| **4. Prevención preventiva de perímetro MCP** | La revisión posterior de redirecciones vía `tab_list` no prevenía navegación previa fuera de perímetro. | Incorporación de validación previa estricta en `_validate_destination` que analiza la URL y parámetros de consulta (`url`, `redirect`, `dest`, etc.) antes de despachar el RPC `browser_navigate`. Si no se garantiza el perímetro, se rechaza preventivamente con `MCPUnauthorizedTargetError`. | `app/mri_autonomous/mcp_adapters/stealth_browser_adapter.py`<br>`test_T8_stealth_browser_mcp_unauthorized_domain_block`<br>`test_T9_stealth_browser_mcp_redirect_rejection` | **CORREGIDO Y VERIFICADO (PASS)** |
| **5. Pruebas negativas contra falsos positivos** | Faltaban pruebas que demostraran que páginas vacías o WAF no provocan falsos positivos comerciales. | Se crearon las pruebas `test_T10` (página vacía) y `test_T11` (bloqueo WAF/Turnstile), confirmando que ambas arrojan estados no-COMPLETED, cero publicaciones y fallo en el registro. | `test_T10` PASSED<br>`test_T11` PASSED | **CORREGIDO Y VERIFICADO (PASS)** |
| **6. Hash canónico y regresiones intactas** | Riesgo de alterar observaciones históricas o romper suites previas. | Ejecución reproducible del script de certificación de Codex Gate 025: 2.533 filas y SHA `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`. Suite completa 21/21 PASS. Cero diffs con producción. | Comprobación SQLite exacta ejecutada en modo solo lectura (`?mode=ro`). | **CORREGIDO Y VERIFICADO (PASS)** |

---

## 3. EVIDENCIA DE EJECUCIÓN REPRODUCIBLE

### 3.1. Certificación Canónica de las 2.533 Observaciones

```python
import sqlite3, hashlib, json, pathlib

E = pathlib.Path('data/sqlite').resolve()
d = sqlite3.connect(E.joinpath('visibility.db').as_uri() + '?mode=ro', uri=True)
cols = [r[1] for r in d.execute('pragma table_info(mri_publications)')]
col_str = ','.join(cols)
rows = []
rows.extend(d.execute('SELECT ' + col_str + ' FROM mri_publications WHERE run_id=?', ('run_va_mri_operational_integration_1792000336',)).fetchall())
rows.extend(d.execute('SELECT ' + col_str + ' FROM mri_historical_publications WHERE run_id=?', ('run_va_mri_operational_integration_1792000336',)).fetchall())
sha = hashlib.sha256(json.dumps(sorted(rows, key=str), default=str).encode()).hexdigest()

print('Count:', len(rows))
print('SHA:', sha)
```

**Salida obtenida:**
```text
Count: 2533
SHA: c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b
```

### 3.2. Batería Completa de Pruebas Automatizadas (21/21 PASS)

```bash
python -m pytest tests/test_mri_022_relational_recovery.py tests/test_mri_capability_registry_023.py -v
```

**Salida:**
```text
tests/test_mri_022_relational_recovery.py::test_relational_model_and_foreign_keys PASSED [  4%]
tests/test_mri_022_relational_recovery.py::test_four_marketplaces_independent_states PASSED [  9%]
tests/test_mri_022_relational_recovery.py::test_ripley_run_scoped_truth_and_zero_static PASSED [ 14%]
tests/test_mri_022_relational_recovery.py::test_empty_runs_preserved_in_history_and_detail PASSED [ 19%]
tests/test_mri_022_relational_recovery.py::test_abc_category_isolation_preserved PASSED [ 23%]
tests/test_mri_022_relational_recovery.py::test_initialization_atomicity_and_caller_transaction PASSED [ 28%]
tests/test_mri_022_relational_recovery.py::test_persistor_atomicity_and_connection_lifecycle PASSED [ 33%]
tests/test_mri_022_relational_recovery.py::test_rollback_to_authorization_denial_does_not_commit_partial_ddl PASSED [ 38%]
tests/test_mri_022_relational_recovery.py::test_preexisting_incompatible_schema_rejection PASSED [ 42%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T1_registry_initialization_and_matrix_completeness PASSED [ 47%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T2_capability_registration_and_lookup PASSED [ 52%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T3_circuit_breaker_and_health_reporting PASSED [ 57%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T4_strategy_selection_deterministic_ordering PASSED [ 61%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T5_strategy_selector_mcp_gating PASSED [ 66%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T6_stealth_browser_mcp_capture_and_hashing PASSED [ 71%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T7_stealth_browser_mcp_permission_revocation PASSED [ 76%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T8_stealth_browser_mcp_unauthorized_domain_block PASSED [ 80%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T9_stealth_browser_mcp_redirect_rejection PASSED [ 85%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_autonomous_strategy_dispatch_fallback_and_experience_update PASSED [ 90%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T10_negative_empty_capture_no_false_positive_commercial_success PASSED [ 95%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T11_negative_waf_challenge_no_false_positive_commercial_success PASSED [100%]

============================= 21 passed in 16.61s =============================
```

### 3.3. Preservación del Código Productivo de Visual Auditor

```bash
git diff origin/main -- app/auditor app/scrapers app/dashboard app/loaders app/config
```
**Resultado:** 0 líneas modificadas (intacto).

---

## 4. REPORTE DE ENTREGA Y CERTIFICACIÓN FINAL

- **Rama de Trabajo:** `fix/mri-022-relational-recovery`
- **Archivos Modificados:**
  1. `app/mri_autonomous/autonomous_multimarketplace_runner.py`: Contrato de veracidad operativa en los cuatro marketplaces; separación explícita de éxito técnico de navegación, captura de evidencias, conteo de publicaciones y estado comercial (`COMPLETED`, `PARTIAL`, `SOURCE_BLOCKED`).
  2. `app/mri_autonomous/mcp_adapters/stealth_browser_adapter.py`: Prevención preventiva de desbordamiento de perímetro y redirección abierta previa al despacho RPC.
  3. `tests/test_mri_capability_registry_023.py`: Actualización del test de integración de despacho y agregado de pruebas negativas T10 y T11.
  4. `VISUAL_AUDITOR_INTEGRAL_CLOSURE.md`: Informe único consolidado y actualizado.

Se hace entrega a **CODEX** para la auditoría independiente integral definitiva.
