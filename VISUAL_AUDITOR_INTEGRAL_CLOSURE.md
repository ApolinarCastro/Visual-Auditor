# VISUAL AUDITOR — INFORME ÚNICO DE CIERRE INTEGRAL (MRI-022 & MRI-023)

**Ejecutor:** ANTIGRAVITY  
**Auditor independiente:** CODEX  
**Proyecto:** Visual Auditor / Marketplace Research Intelligence  
**Rama:** `fix/mri-022-relational-recovery`  
**Base revisada:** `8e25f44b10779e485aafecd2f27d34f90d85f708`  
**SHA Final Entregado:** `99eb9648b4c35c39a19f0209afb40ee84f271d31`  
**Fecha:** 2026-10-20  

---

## 1. RESUMEN EJECUTIVO Y RESOLUCIÓN DE OBSERVACIONES

En cumplimiento estricto del mandato de cierre integral sin reaperturas y resolviendo las observaciones requeridas:

1. **Certificación Histórica de las 2.533 Observaciones (Algoritmo Canónico de Codex)**:
   - Se ejecutó exactamente el algoritmo canónico de certificación de Codex Gate 025/032 (`evidence/mri_codex_independent_gate_025/check_gate.py`):
     ```python
     d = sqlite3.connect((E/'production_copy.db').as_uri()+'?mode=ro', uri=True)
     cols = [r[1] for r in d.execute('pragma table_info(mri_publications)')]
     rows = []
     for t in ['mri_publications', 'mri_historical_publications']:
         rows.extend(d.execute(f'SELECT {",".join(cols)} FROM {t} WHERE run_id=?', ('run_va_mri_operational_integration_1792000336',)).fetchall())
     sha = hashlib.sha256(json.dumps(sorted(rows, key=str), default=str).encode()).hexdigest()
     ```
   - **Resultado en `data/sqlite/visibility.db`**:
     - Conteo exacto: **2.533** (2.489 en `mri_publications` + 44 en `mri_historical_publications`).
     - Hash SHA-256 exacto: `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`.
     - **Causa de la discrepancia previa explicada**: Un cálculo anterior usó un subconjunto de columnas (`publication_id, product_id, marketplace, status, observed_at, position`), dando `49481608...`. Con el algoritmo canónico completo sobre todas las columnas de `PRAGMA table_info` y serialización ordenada, el hash coincide al 100% con `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b` certificado por Codex.

2. **Despacho Efectivo en los 4 Marketplaces y Ciclo Completo en una Sola Invocación**:
   - Se corrigió el despacho en `AutonomousMultiMarketplaceRunner` para que la estrategia seleccionada determine efectivamente el adaptador ejecutado en los 4 marketplaces:
     - **Paris**: Despacha `CDP_API_PUBLIC` (Constructor.io API direct) o `CONTROLLED_REPLAY` (HAR capture feed) según `strategy.capability.adapter_mode`.
     - **Falabella**: Despacha `HTTP_SSR` (`FalabellaSSREngine`) o `HEADLESS_PLAYWRIGHT` (`FalabellaScraper`) según `strategy.capability.adapter_mode`.
     - **Mercado Libre**: Despacha `HEADLESS_PLAYWRIGHT` (`MercadoLibreScraper`) o `STEALTH_MCP` (`StealthBrowserMCPAdapter`) según `strategy.capability.adapter_mode`.
     - **Ripley**: Despacha `HEADLESS_PLAYWRIGHT` (`RipleyScraper`) o `STEALTH_MCP` (`StealthBrowserMCPAdapter`) según `strategy.capability.adapter_mode`.
   - **Ciclo Completo en una Sola Invocación**:
     - Ante el fallo real de un ejecutor primario, el runner captura la excepción internamente, actualiza automáticamente la salud en el `CapabilityRegistry` (`report_outcome(primary, False)`), conmuta al adaptador de fallback de la cadena, adquiere los datos, persiste las observaciones a SQLite y actualiza la salud del fallback (`report_outcome(fallback, True)`).
     - **Cero llamadas manuales a `report_outcome()` en el test**: Verificado en `test_autonomous_strategy_dispatch_fallback_and_experience_update` mediante una única llamada `await runner.investigate_ripley(...)`.

3. **Seguridad MCP y Limitación Arquitectónica en Redirecciones**:
   - `obscura.exe` (`mcp --stealth`) ofrece automatización del navegador pero **carece de hooks de intercepción previa de navegación** antes de que la petición HTTP se despache por la red. Por consiguiente, una redirección HTTP 301/302 hacia un dominio no autorizado no puede prevenirse previamente a nivel de red por el servidor MCP.
   - **Gobernanza y Mitigación Implementada**:
     - Se documentó formalmente esta limitación arquitectónica en `StealthBrowserMCPAdapter` y en este informe.
     - Tras la navegación, el adaptador inspecciona `browser_tab_list`; ante cualquier redirección fuera de los 4 dominios autorizados (`paris.cl`, `falabella.com`, `mercadolibre.cl`, `ripley.cl`), cierra inmediatamente la sesión con `browser_close`, descarta la evidencia y lanza `MCPUnauthorizedTargetError` (fail-closed).
     - La capacidad queda clasificada como **deshabilitada para escenarios de navegación abierta o libre exploración de redirecciones arbitrarias**, restringiéndose exclusivamente a puntos de entrada HTTPS pre-validados en la lista de dominios autorizados.

4. **Eliminación Total de Archivos `.pyc`**:
   - Archivos binarios compilados `.pyc` purgados del índice git. `.gitignore` reforzado. `git ls-files "*.pyc"` = 0.

5. **Pruebas de Integridad, Regresiones y Preservación de Visual Auditor**:
   - Suite relacional (`tests/test_mri_022_relational_recovery.py`): **9/9 PASSED**.
   - Suite de capacidades y MCP (`tests/test_mri_capability_registry_023.py`): **10/10 PASSED**.
   - Total pruebas: **19/19 PASSED**.
   - Preservación de producción: `git diff origin/main -- app/auditor app/scrapers app/dashboard app/loaders app/config` = **0 líneas modificadas** (intacto).

---

## 2. MATRIZ DE OBSERVACIONES Y RESOLUCIÓN

| Observación | Requisito Mandatorio | Causa Previa | Solución Verificada | Evidencia de Ejecución | Estado |
|---|---|---|---|---|---|
| **1. Certificación 2.533 Observaciones** | Ejecutar exactamente el algoritmo de certificación Codex Gate 025; explicar diferencia sin modificar producción. | Cálculo preliminar usó columnas parciales arrojando hash `494816...`. | Ejecución del algoritmo canónico de Gate 025 sobre `data/sqlite/visibility.db` (`cols = PRAGMA table_info(mri_publications)`). Conteo: exactamente 2.533. SHA-256 canónico exacto: `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`. | Script SQLite exacto ejecutado con URI `?mode=ro`. SHA-256 coincide al 100% con la certificación histórica de Codex. | **VERIFICADO (PASS)** |
| **2. Despacho en 4 Marketplaces & Fallbacks Reales** | Integrar despacho efectivo en Paris, Falabella, Ripley y Mercado Libre. Demostrar en una sola invocación del runner el ciclo completo sin llamadas manuales a `report_outcome()`. | Despacho estático o no condicionado por la estrategia; tests requerían llamadas manuales a `report_outcome()`. | Despacho dinámico parametrizado en los 4 marketplaces basado en `strategy.capability.adapter_mode`. El runner captura fallos de ejecución internamente, actualiza automáticamente la salud en el registro, activa el fallback, ejecuta el adaptador secundario y persiste en SQLite. Demostrado en una sola llamada de runner sin `report_outcome()` manual. | `tests/test_mri_capability_registry_023.py::test_autonomous_strategy_dispatch_fallback_and_experience_update` (1 sola invocación, ciclo completo verificado). | **VERIFICADO (PASS)** |
| **3. Comportamiento y Seguridad MCP** | Verificar redirección a dominio no autorizado. Comprobar que tab_list posterior no es prevención previa; documentar limitación y mantener capacidad deshabilitada para ese escenario. | Ausencia de hooks previos de intercepción en el servidor MCP `obscura.exe`. | Documentación formal de la limitación arquitectónica. Inspección post-navegación vía `browser_tab_list` cierra sesión de inmediato con `browser_close` y lanza `MCPUnauthorizedTargetError`. Capacidad deshabilitada para exploración abierta de redirecciones no autorizadas. | `app/mri_autonomous/mcp_adapters/stealth_browser_adapter.py`<br>`tests/test_mri_capability_registry_023.py::test_T9_stealth_browser_mcp_redirect_rejection` | **VERIFICADO (PASS)** |
| **4. Eliminación de `.pyc`** | Eliminar archivos `.pyc` del control de versiones y evitar nuevas incorporaciones. | `.pyc` trackeados accidentalmente en commits pasados. | `git rm --cached` ejecutado sobre todos los `.pyc`. Actualización de `.gitignore` con `__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd`. `git ls-files "*.pyc"` = 0. | `git ls-files "*.pyc"` retorna vacío. | **VERIFICADO (PASS)** |
| **5. Regresiones e Integridad** | Repetir pruebas originales de integridad SQLite, regresiones funcionales y preservación de VA. | Garantizar que ninguna corrección introdujo regresiones en MRI-022 ni alteró producción. | Ejecución completa de suites de prueba (19 pruebas unitarias e integradas). Comprobación de integridad relacional, transaccionalidad atómica y verificación de 0 diffs en el código productivo de Visual Auditor. | `pytest tests/test_mri_022_relational_recovery.py tests/test_mri_capability_registry_023.py` (19/19 PASSED). `git diff origin/main -- app/auditor ...` = 0 líneas. | **VERIFICADO (PASS)** |

---

## 3. EVIDENCIA DE EJECUCIÓN REPRODUCIBLE

### 3.1. Algoritmo Canónico de Certificación Histórica (Gate 025)

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

### 3.2. Batería Completa de Pruebas Automatizadas (19/19 PASS)

```bash
python -m pytest tests/test_mri_022_relational_recovery.py tests/test_mri_capability_registry_023.py -v
```

**Salida:**
```text
tests/test_mri_022_relational_recovery.py::test_relational_model_and_foreign_keys PASSED [  5%]
tests/test_mri_022_relational_recovery.py::test_four_marketplaces_independent_states PASSED [ 10%]
tests/test_mri_022_relational_recovery.py::test_ripley_run_scoped_truth_and_zero_static PASSED [ 15%]
tests/test_mri_022_relational_recovery.py::test_empty_runs_preserved_in_history_and_detail PASSED [ 21%]
tests/test_mri_022_relational_recovery.py::test_abc_category_isolation_preserved PASSED [ 26%]
tests/test_mri_022_relational_recovery.py::test_initialization_atomicity_and_caller_transaction PASSED [ 31%]
tests/test_mri_022_relational_recovery.py::test_persistor_atomicity_and_connection_lifecycle PASSED [ 36%]
tests/test_mri_022_relational_recovery.py::test_rollback_to_authorization_denial_does_not_commit_partial_ddl PASSED [ 42%]
tests/test_mri_022_relational_recovery.py::test_preexisting_incompatible_schema_rejection PASSED [ 47%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T1_registry_initialization_and_matrix_completeness PASSED [ 52%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T2_capability_registration_and_lookup PASSED [ 57%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T3_circuit_breaker_and_health_reporting PASSED [ 63%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T4_strategy_selection_deterministic_ordering PASSED [ 68%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T5_strategy_selector_mcp_gating PASSED [ 73%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T6_stealth_browser_mcp_capture_and_hashing PASSED [ 78%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T7_stealth_browser_mcp_permission_revocation PASSED [ 84%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T8_stealth_browser_mcp_unauthorized_domain_block PASSED [ 89%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_T9_stealth_browser_mcp_redirect_rejection PASSED [ 94%]
tests/test_mri_capability_registry_023.py::TestMRICapabilityRegistry023::test_autonomous_strategy_dispatch_fallback_and_experience_update PASSED [100%]

============================= 19 passed =============================
```

### 3.3. Preservación del Código Productivo de Visual Auditor

```bash
git diff origin/main -- app/auditor app/scrapers app/dashboard app/loaders app/config
```
**Resultado:** 0 líneas modificadas (intacto).

---

## 4. REPORTE DE ENTREGA

- **Rama:** `fix/mri-022-relational-recovery`
- **Archivos Modificados:**
  1. `app/mri_autonomous/autonomous_multimarketplace_runner.py` (integración de despacho y manejo de fallbacks en los 4 marketplaces).
  2. `app/mri_autonomous/mcp_adapters/stealth_browser_adapter.py` (seguridad MCP, validación de perímetro y cierre de sesión).
  3. `tests/test_mri_capability_registry_023.py` (pruebas T9 y demostración de fallback por fallo real de ejecutor).
  4. `.gitignore` (exclusión de `.pyc` y `__pycache__`).
  5. `VISUAL_AUDITOR_INTEGRAL_CLOSURE.md` (informe único de evidencia reproducible).

Se entrega para la auditoría integral definitiva de **CODEX**.
