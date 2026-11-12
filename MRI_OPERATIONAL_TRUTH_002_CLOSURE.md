# MRI-OPERATIONAL-TRUTH-002 — CIERRE

**Tarea:** MRI-OPERATIONAL-TRUTH-002  
**Fecha:** 2026-10-28  
**Rama:** `integration/mri-deepseek-closure`  
**HEAD de trabajo:** `7042409` + cambios locales no publicados  
**Baseline publicado de referencia:** `5ad8a1b`  
**Modalidad:** READ ONLY FIRST → correcciones mínimas → pruebas dirigidas → verificación → cierre.  
**Commit/Push:** NO EJECUTADOS (no autorizados por esta tarea).

---

## 1. CP0 — Diagnóstico

### Estado del repositorio
- Rama: `integration/mri-deepseek-closure`.
- HEAD local: `7042409`.
- Cambios locales de esta intervención: `mri_runner.py`, `mri_api.py`, `templates/index.html`, y nuevos `observation_reconciliation.py`, `taxonomy_scope.py`, `test_cp1_cp3.py`.
- No se modificó Visual Auditor Legacy.
- No se modificó la base histórica certificada.
- No había auditoría activa al iniciar las pruebas: MRI `RUNNING=False`, VA sin API en `8000`.

### Corridas del 28-10-2026 (SQLite operativo)
```text
9 corridas
2 FOUND · 6 PARTIAL · 1 STOPPED_BY_USER
2.291 publicaciones materializadas
```

| run_id | Marketplace | Estado | Pubs |
|---|---|---|---:|
| `run_mri_discovery_1793186791` | Falabella | FOUND | 441 |
| `run_mri_discovery_1793187218` | Paris | FOUND | 638 |
| `run_mri_discovery_1793189898` | Ripley | PARTIAL | 753 |
| `run_mri_discovery_1793194174` | Mercado Libre | PARTIAL | 1 |
| `run_mri_discovery_1793195293` | Mercado Libre | PARTIAL | 0 |
| `run_mri_discovery_1793196154` | Mercado Libre | PARTIAL | 0 |
| `run_mri_discovery_1793196620` | Mercado Libre | STOPPED_BY_USER | 0 |
| `run_mri_discovery_1793196683` | Mercado Libre | PARTIAL | 4 |
| `run_mri_discovery_1793201264` | Mercado Libre | PARTIAL | 454 |

---

## 2. CP1 — Falabella: dictamen comercial

### Causa demostrada
Las 441 publicaciones Falabella tienen:

```text
identity_status = OFFICIAL_VERIFIED
category_observed = categoría Falabella válida
category_expected = SIN_REFERENCIA
category_decision = NO_VERIFICADO
```

La ruta Falabella del runner asignaba:

```python
"expected_category": _o.get("category_name")
"decision": "NO_VERIFICADO"
```

Es decir:
- usaba la categoría observada como si fuera esperada;
- no consultaba el maestro;
- no invocaba el clasificador comercial.

No era falta de identidad ni de categoría observada. Era una etapa de dictamen incompleta.

### Corrección
- Nuevo resolvedor independiente por título contra el maestro:
  `resolve_master_category_by_title()`.
- Falabella ahora:
  - resuelve `expected_category` desde el maestro;
  - si no hay referencia, conserva `SIN_REFERENCIA` y `NO_VERIFICADO`;
  - si hay referencia, invoca `evaluate_commercial_category()`;
  - conserva categoría observada, URL, vendedor e identidad originales.

### Evidencia de prueba
```text
Polera Entallada Escote Cuadrado Negro Nicopoly
→ expected = Ropa - Ropa Mujer - Poleras - Poleras Sin Manga
→ observed = Poleras Mujer
→ decision = CORRECT
```

Prueba: `tests/test_cp1_cp3.py::test_falabella_expected_category_is_independent_and_classified`.

### Límite
No se relanzó Falabella. La corrección está probada contra el maestro real y una muestra real de Falabella, pero falta validación operativa completa.

---

## 3. CP2 — Mercado Libre: alcance y bloqueo

### Causas demostradas
1. **Cinco corridas ML con 0–4 publicaciones** por `account-verification`.
2. **Rutas genéricas contaminantes**:
   ```text
   https://listado.mercadolibre.cl/vestuario-calzado/faldas/
   https://listado.mercadolibre.cl/vestuario-calzado/abrigos/
   ...
   ```
   Devolvieron 18 productos cada una, pero no son la tienda oficial Nicopoly.
3. El runner reutilizaba `category_manager` persistente, que arrastraba categorías de corridas anteriores.
4. `session_injection = []`; no se importaron cookies en MRI.
5. No se puede automatizar CAPTCHA; el resultado correcto ante el muro es `SOURCE_BLOCKED`.

### Corrección
- Full audits usan únicamente las categorías de la taxonomía de la corrida actual:
  `categories_from_taxonomy()`.
- Se elimina la herencia de categorías persistentes/antiguas.
- Se mantiene `SOURCE_BLOCKED` para listados bloqueados.
- Se preservan `sponsored` y `position_kind`:
  ```text
  SPONSORED: 616
  ORGANIC:   147
  ```
- El Control de Sesiones ya existe, pero **no se usó**: 0 cookies importadas.
- No se copiaron credenciales ni se automatizó ningún desafío.

### Evidencia
- `tests/test_cp1_cp3.py::test_taxonomy_scope_does_not_inherit_persistent_categories`.
- Última corrida ML: 454 publicaciones materializadas; 763 observaciones.
- Cinco corridas ML siguen siendo fallos de acceso, no resultados comerciales.

---

## 4. CP3 — 763 vs 454

### Reconciliación determinista
```text
CAPTURADO          763 observaciones
NORMALIZADO        763 identidades resueltas
DUPLICADO          309 observaciones del mismo ID de publicación
PERSISTIDO         454 publicaciones únicas
```

Evidencia:
```text
STATE_RESULTS             763
UNIQUE_IDS                454
STATE_DUP_ROWS            309
DB_PUBLICATIONS           454
DB_NOT_IN_STATE           0
STATE_NOT_IN_DB           0
```

Los 309 son **observaciones repetidas de la misma publicación** en distintas posiciones/categorías, no 309 productos perdidos.

La persistencia ya registraba:
```text
source_results: 763
stored_observations: 454
duplicates_collapsed: 309
discard_examples: DUPLICATE_PUBLICATION_ID
```

### Corrección
- Nuevo módulo `observation_reconciliation.py`.
- `/api/state` expone:
  ```json
  "reconciliation": {
    "observations": 763,
    "unique_publications": 454,
    "duplicate_observations": 309
  }
  ```
- El dashboard muestra:
  ```text
  Mostrando N observaciones de 763 · 454 productos únicos
  ```
- Se mantiene una sola identidad de producto; no se fabricaron 309 publicaciones.
- Límite conocido: SQLite conserva la publicación única; las observaciones duplicadas de categoría/posición siguen en memoria/historial, no como filas de publicación.

Prueba: `test_observations_vs_unique_publications_are_explicit`.

---

## 5. CP4 — Experiencia y aprendizaje

### Evidencia
```text
Entradas de experiencia: 168
Corridas cubiertas:       11
Éxitos:                   56
Fallos:                  112
URLs únicas:              66
URLs repetidas:           42
Experiencias promovidas:   0
Reutilización demostrada:  0
```

### Decisión
No se promovió ninguna experiencia porque no se demostró que una ruta sea:
- independiente de sesión/cookies;
- estable entre corridas;
- no caducada;
- no contradictoria con reglas vigentes;
- verificable sin efectos laterales.

`PROMOTED=0` es el resultado correcto. No se inventaron experiencias ni se reutilizaron cookies como conocimiento.

### Clasificación
```text
EXPERIENCE_LOGGING=PASS
EXPERIENCE_PROMOTION=NOT_JUSTIFIED
EXPERIENCE_REUSE=NOT_EXECUTED
```

---

## 6. CP5 — Preservación Paris/Ripley

- Paris: 638 publicaciones; sin cambios en su ruta validada.
- Ripley: 753 publicaciones; sin cambios en scraper, perfil ni recuperación de navegador.
- No se modificó `app/scrapers`, `app/auditor` ni `app/core`.
- No se relanzaron auditorías masivas.
- La suite transversal sigue pasando.

---

## 7. CP6 — Verificación

```text
142/142 tests PASS
Jinja OK
SQLite integrity previa: ok
```

### Límites de verificación
- El servidor API en ejecución conserva el código anterior; los campos nuevos de `/api/state` requieren reinicio.
- No se ejecutó una nueva auditoría Falabella/ML por restricción de no repetir corridas masivas.
- No se validó en vivo la reclasificación Falabella ni el alcance ML corregido.
- No se importaron cookies de sesión en MRI.
- No se declaró PASS comercial.

---

## 8. Resultado obligatorio

```text
TASK=MRI-OPERATIONAL-TRUTH-002

FALABELLA_441_CAUSES=RECONCILED
FALABELLA_CLASSIFIER=PASS

MELI_SOURCE_ACCESS=SOURCE_BLOCKED
MELI_SCOPE_VALIDATION=PASS
MELI_AD_ORGANIC=PASS

MELI_763_454_RECONCILIATION=PASS

EXPERIENCE_LOGGING=PASS
EXPERIENCE_PROMOTION=NOT_JUSTIFIED
EXPERIENCE_REUSE=NOT_EXECUTED

PARIS_REGRESSION=PASS
RIPLEY_REGRESSION=PASS
SQLITE_API_DASHBOARD=PASS
HISTORICAL_LOGICAL_INTEGRITY=PASS
VA_LEGACY_FREEZE=PASS

LIVE_VERIFIED=NO
AUDIT_PASS=NO
COMMIT=NOT_AUTHORIZED
PUSH=NOT_AUTHORIZED

FINAL_STATUS=READY_FOR_LOCAL_VALIDATION
```

### Interpretación
- **READY_FOR_LOCAL_VALIDATION:** correcciones y pruebas locales listas; falta ejecución real controlada para certificar Falabella y ML.
- **LIVE_VERIFIED=NO:** no se realizó una corrida de certificación real posterior a las correcciones.
- **AUDIT_PASS=NO:** no se declara éxito comercial.
- **COMMIT/PUSH:** no ejecutados.

### Riesgos residuales
1. Falabella: validar en vivo que el maestro resuelve una fracción suficiente y que no se fuerza `CORRECTO`.
2. ML: el muro anti-bot sigue siendo el bloqueo estructural; sesión no importada.
3. Persistencia: las 309 observaciones duplicadas no se materializan como posiciones independientes.
4. Experiencia: sin promoción activa; no hay reutilización demostrada.
5. API/dashboard: requieren reinicio para exponer el contrato de reconciliación.

---

## 9. Archivos modificados/creados

```text
app/mri_dashboard/mri_runner.py
  - Falabella expected category + classifier
  - alcance de taxonomía actual
  - resolvedor maestro por título

app/mri_dashboard/mri_api.py
  - campo reconciliation en /api/state

app/mri_dashboard/templates/index.html
  - observaciones vs productos únicos

app/mri_dashboard/observation_reconciliation.py   [nuevo]
app/mri_dashboard/taxonomy_scope.py               [nuevo]
tests/test_cp1_cp3.py                             [nuevo]
```

**No se ejecutó commit, push, merge, reset ni clean.**

---

## 10. Addendum 2026-10-28 — ML 14 categorías y total declarado

### Causa adicional demostrada
El fetch del storefront usaba el User-Agent de API (`MRI-Autonomous-Research-Engine`), que recibe una variante reducida del HTML con solo 4 categorías.

Con User-Agent de navegador, el mismo SSR entrega el menú completo:
```text
MLC158340 Chaquetas, Parkas y Blazers
MLC158342 Blusas
MLC158583 Pantalones
MLC158425 Vestidos
MLC455528 Abrigos
MLC440371 Chalecos, Sweaters y Cardigans
MLC158467 Poleras
MLC158335 Camisas
MLC440654 Calzas
MLC440714 Enteritos
MLC158457 Faldas
MLC440323 Ropa Interior y de Dormir
MLC158307 Bermudas y Shorts
MLC455550 Kimonos
```

### Corrección
- `STOREFRONT_USER_AGENT` separado del UA de API.
- `fetch_storefront_html()` usa UA de navegador.
- `meli_taxonomy()` devuelve 15 entradas: 1 superficie de adquisición + 14 categorías.
- No se hardcodearon las 14; se extraen del menú SSR.

### Evidencia live
```text
TAXONOMY_DISCOVERED / STOREFRONT_SSR / COUNT=15
```

### Total declarado observado
La captura de la tienda muestra:
```text
Vestuario y Calzado — 658 resultados
```
Ese total no aparece en el HTML de portada; es un contador renderizado de la página de categoría. Se conserva como **observación declarada**, no como dato parseado.

### Estado
- 143/143 tests PASS.
- La captura 658 vs 454 únicas de la última corrida confirma una brecha de cobertura de ~204 publicaciones.
- No se implementó omisión por frescura: no mejora cobertura y puede ocultar cambios intradía.
- Falta una corrida real ML con las 14 categorías y sesión válida para intentar acercarse a 658.

```text
MELI_TAXONOMY_14=PASS
MELI_DECLARED_TOTAL_OBSERVED=658
LIVE_VERIFIED=NO
```

---

## 11. Addendum — cierre de adquisición ML

### Implementado
- `meli_snapshot.py`:
  - `parse_declared_total()` para “658 resultados” y “Mostrando … de …”.
  - `snapshot()` y `diff()` deterministas para precio/estado/nuevos/removidos.
- En adquisición ML de categorías (`/listado/`), tras completar la paginación se lee el total declarado de la página y se entrega a G3 como `pagination.reported_products`.
- No se aplica al root SSR (`/tienda/nicopoly`), porque es una muestra rotativa 37–39, no un total.
- No se implementó skip por frescura.

### Pruebas
```text
145/145 tests PASS
Jinja OK
```

### Pendiente live
- Reiniciar y ejecutar ML-only.
- Verificar 15 entradas de taxonomía (1 superficie + 14 categorías).
- Verificar que G3 recibe conteo por categoría cuando no hay bloqueo.
- Comparar cobertura contra 658.
- Confirmar que el total de página no se confunde con el total site-wide.

```text
MELI_DECLARED_TOTAL_CAPTURE=PASS (unit)
MELI_SNAPSHOT_DIFF=PASS (unit)
MELI_LIVE_COVERAGE=NO_VERIFIED
```
