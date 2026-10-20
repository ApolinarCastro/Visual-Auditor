# VISUAL AUDITOR — INFORME ÚNICO DE CIERRE INTEGRAL (MRI-022 & MRI-023)

**Ejecutor:** ANTIGRAVITY  
**Auditor independiente:** CODEX  
**Proyecto:** Visual Auditor / Marketplace Research Intelligence  
**Rama:** `fix/mri-022-relational-recovery`  
**Base revisada:** `71f348eceb9620b1a516b48fed516386e6992ca8`  
**SHA Final Entregado:** `619d519b208ffe5a304093bd5b0cad6e9fdb2603`  
**Fecha:** 2026-10-20  

---

## 1. RESUMEN EJECUTIVO Y RESOLUCIÓN DE OBSERVACIONES

En cumplimiento estricto del mandato de cierre integral sin reaperturas y resolviendo las 5 observaciones requeridas:

1. **Certificación Histórica de las 2.533 Observaciones (Algoritmo Exacto de Codex)**:
   - Se ejecutó exactamente el algoritmo de certificación histórica de Codex Gate 025/032 (`evidence/mri_codex_independent_gate_025/check_gate.py`):
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
     - **Causa de la discrepancia previa explicada**: Un script preliminar calculó el hash sobre un subconjunto arbitrario de columnas (`publication_id, product_id, marketplace, status, observed_at, position`), arrojando `49481608...`. Al ejecutar el algoritmo canónico con todas las columnas de `PRAGMA table_info` y serialización canónica ordenada, el hash resultante coincide al 100% con `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b` certificado por Codex. La base productiva no fue tocada ni sustituida.

2. **Despacho Efectivo e Integrado del Strategy Selector en los 4 Marketplaces**:
   - Se parametrizó la firma de investigación en los 4 marketplaces de `AutonomousMultiMarketplaceRunner`:
     - `investigate_paris(run_id, strategy=paris_strat)`
     - `investigate_ripley(run_id, strategy=ripley_strat)`
     - `investigate_falabella(run_id, strategy=falabella_strat)`
     - `investigate_mercadolibre(run_id, strategy=meli_strat)`
   - La selección efectiva de estrategia determina el adaptador y la ejecución.
   - **Demostración de Fallbacks por Fallo Real**: Se eliminaron llamadas manuales simuladas a `report_outcome()` en las pruebas de despacho. En `test_autonomous_strategy_dispatch_fallback_and_experience_update`, la falla primaria es provocada por una excepción real de ejecución (Cloudflare Turnstile WAF block 403 en el scraper). El runner captura el fallo real, clasifica el estado en `SOURCE_BLOCKED`/`PARTIAL`, alimenta el registro y el selector activa automáticamente el fallback secundario (`STEALTH_MCP`), ejecutando la herramienta y actualizando la experiencia.

3. **Seguridad y Comportamiento MCP (Perímetro, Redirecciones, Revocaciones y Cierres)**:
   - `StealthBrowserMCPAdapter` opera con garantías preventivas completas:
     - **Validación preventiva de perímetro**: Esquema strictly HTTPS y lista blanca de dominios exactos y subdominios autorizados (`paris.cl`, `falabella.com`, `mercadolibre.cl`, `ripley.cl`).
     - **Control anti-escape por redirección**: Tras la navegación, consulta `browser_tab_list`; si el destino redirigido se encuentra fuera del perímetro autorizado, cierra inmediatamente la sesión con `browser_close`, descarta la captura y lanza `MCPUnauthorizedTargetError` (verificado en `test_T9_stealth_browser_mcp_redirect_rejection`).
     - **Revocación fail-closed**: Comprobación de permisos tanto previa como mid-operación antes de cada llamada RPC (`initialize`, `tools/call`, `browser_snapshot`). Ante revocación, se aborta y limpia el subproceso (`test_T7`).
     - **Limpieza garantizada de sesión**: El bloque `finally` garantiza el cierre de `stdin`, terminación del proceso (`proc.terminate()`) y fallback a `kill()` en caso de cuelgue o error del servidor MCP.

4. **Eliminación Total de Archivos `.pyc` del Control de Versiones**:
   - Se eliminaron todos los archivos binarios compilados `.pyc` del índice de git (`git rm -r --cached "app/mri_autonomous/__pycache__" "app/mri_dashboard/__pycache__"`).
   - Se agregaron las reglas `__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd` a `.gitignore`.
   - `git ls-files "*.pyc"` retorna estrictamente **0 archivos**.

5. **Pruebas de Integridad SQLite, Regresiones y Preservación de Visual Auditor**:
   - Suite relacional (`tests/test_mri_022_relational_recovery.py`): **9/9 PASSED**.
   - Suite de capacidades y MCP (`tests/test_mri_capability_registry_023.py`): **10/10 PASSED**.
   - Total pruebas: **19/19 PASSED**.
   - Preservación de producción: `git diff origin/main -- app/auditor app/scrapers app/dashboard app/loaders app/config` = **0 líneas modificadas** (intacto).

---

## 2. MATRIZ DE OBSERVACIONES Y RESOLUCIÓN

| Observación | Requisito Mandatorio | Causa Previa | Solución Verificada | Evidencia de Ejecución | Estado |
|---|---|---|---|---|---|
| **1. Certificación 2.533 Observaciones** | Ejecutar exactamente el algoritmo de certificación Codex Gate 025; explicar diferencia sin modificar producción. | Cálculo preliminar usó columnas parciales arrojando hash `494816...`. | Ejecución del algoritmo canónico de Gate 025 sobre `data/sqlite/visibility.db` (`cols = PRAGMA table_info(mri_publications)`). Conteo: exactamente 2.533. SHA-256 canónico exacto: `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`. | Script SQLite exacto ejecutado con URI `?mode=ro`. SHA-256 coincide al 100% con la certificación histórica de Codex. | **VERIFICADO (PASS)** |
| **2. Despacho en 4 Marketplaces & Fallbacks Reales** | Integrar despacho de selector en Paris, Ripley, Falabella y Mercado Libre. Demostrar fallbacks por fallos reales del ejecutor. | La llamada `investigate_*` solo recibía `strategy` en Ripley y los tests llamaban artificialmente a `report_outcome()`. | Despacho parametrizado en los 4 marketplaces en `execute_autonomous_order()`. El runner ejecuta el adaptador seleccionado y actualiza el registro con base en el resultado del ejecutor. Demostración en test mediante inyección de fallo de adquisición real (WAF/Turnstile exception) que activa la transición a BLOCKED y promueve el fallback secundario sin llamadas manuales espurias. | `tests/test_mri_capability_registry_023.py::test_autonomous_strategy_dispatch_fallback_and_experience_update` | **VERIFICADO (PASS)** |
| **3. Comportamiento y Seguridad MCP** | Validar redirecciones, bloqueos, revocaciones y fallos de servidor. Impedir destinos no autorizados. | Necesidad de evidencia demostrable sobre redirecciones y fail-closed preventivo. | Comprobación estricta de destino con inspección de `browser_tab_list` post-navegación. Si el destino final sale del perímetro, se cierra el navegador inmediatamente con `browser_close` y se lanza `MCPUnauthorizedTargetError`. Pruebas T7 (revocación), T8 (bloqueo fuera de perímetro) y T9 (rechazo de redirección no autorizada). | `tests/test_mri_capability_registry_023.py::test_T7_stealth_browser_mcp_permission_revocation`<br>`tests/test_mri_capability_registry_023.py::test_T8_stealth_browser_mcp_unauthorized_domain_block`<br>`tests/test_mri_capability_registry_023.py::test_T9_stealth_browser_mcp_redirect_rejection` | **VERIFICADO (PASS)** |
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
