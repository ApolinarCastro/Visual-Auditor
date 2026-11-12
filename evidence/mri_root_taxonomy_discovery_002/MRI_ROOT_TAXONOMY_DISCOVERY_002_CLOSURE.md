# MRI ROOT TAXONOMY DISCOVERY 002 — CLOSURE

**Task:** `MRI-ROOT-TAXONOMY-DISCOVERY-002`  
**Mode:** IMPLEMENT → TEST → VERIFY  
**Branch:** `integration/mri-deepseek-closure`  
**HEAD:** `089548b6849d`  
**Date:** 2026-11-02  
**Production migration applied:** NO  
**Database mutations:** 0  
**Git commits/pushes:** 0  

---

## 1. Resultado ejecutivo

```text
FINAL_STATUS=READY_FOR_INTEGRATED_VALIDATION
```

Los cuatro adaptadores de raíz están implementados y probados con fuentes inyectadas y fixtures deterministas. La migración de `taxonomy_store.py` sigue preparada, no aplicada.

```text
FALABELLA_ROOT_DISCOVERY=PARTIAL
MELI_ROOT_DISCOVERY=PARTIAL
RIPLEY_ROOT_DISCOVERY=PARTIAL
PARIS_ROOT_DISCOVERY=PARTIAL
```

`PARTIAL` significa que el mecanismo de raíz existe y está probado, pero no se ejecutó contra el marketplace live. No es un fallo de descubrimiento.

---

## 2. CP0 — Estado persistente y precondiciones

```text
worktree: _integration
rama: integration/mri-deepseek-closure
HEAD: 089548b6849d
```

Se preservaron los cambios previos de `MRI-TAXONOMY-FOUNDATION-001`:

```text
app/mri_autonomous/taxonomy_store.py
app/mri_dashboard/mri_runner.py
tests/test_taxonomy_foundation_001.py
```

### DB operativa

```text
integrity_check=ok
mri_categories=113
tablas mri_taxonomy_* en producción=0
```

La migración de taxonomía **no** fue aplicada a producción.

### Servidor

```text
127.0.0.1:8055: sin listener
LIVE_AUDITS=NOT_EXECUTED
```

---

## 3. Fuentes de raíz implementadas

### Falabella

Archivo:

```text
app/mri_autonomous/taxonomy_roots.py
discover_falabella_roots()
```

Fuente:

```text
SSR página genérica de Falabella
→ FalabellaSSREngine.fetch_page_ssr_data()
→ FalabellaSSREngine.extract_taxonomy_tree()
```

Contrato:

- Inicia desde la raíz SSR, no desde `get_brand_catalog()`.
- Conserva `category_id`, `parent_id`, `hierarchical_path`, URL, fuente y evidencia.
- Si el payload de marca se usa como fallback, se marca `BRAND_FALLBACK_NOT_ROOT_TAXONOMY`.
- No afirma exhaustividad.

### Mercado Libre

```text
discover_meli_roots()
```

Fuente:

```text
MeliTaxonomyEngine
→ GET /sites/{site_id}/categories
→ get_category_by_id() para expandir children_categories
```

Contrato:

- La lista raíz proviene de la API oficial.
- Conserva IDs `MLC…`, padre y path.
- No usa la lista hardcodeada de categorías.
- Si la API falla, el fallback existente `DiscoveryKernel` queda marcado `STOREFRONT_FALLBACK_NOT_ROOT_TAXONOMY`.

### Ripley

```text
discover_ripley_roots_async()
discover_ripley_roots_from_urls()
```

Fuente:

```text
category_discoverer.discover_categories_from_page()
→ URLs de navegación de la raíz Ripley
```

Contrato:

- Excluye hosts ajenos.
- Deduplica URLs.
- Padre no demostrado queda `NULL` y `NOT_VERIFIED`; no se infiere desde el slug.
- No usa una lista predefinida de siete rutas.

### Paris

```text
discover_paris_roots_async()
discover_paris_roots_from_urls()
```

Fuente:

```text
category_discoverer RSC/navegación existente
→ capa MRI exclusivamente
```

Contrato:

- No se modifica el scraper Legacy ni el baseline validado.
- Deduplica URLs y filtra host.
- Padre no demostrado queda `NULL` y `NOT_VERIFIED`.
- Sustituye el antiguo `TAXONOMY_NOT_REQUIRED` en la ruta async de MRI.

---

## 4. Integración con `taxonomy_store.py`

`taxonomy.py` ahora usa los adaptadores de raíz:

```text
falabella_taxonomy() → discover_falabella_roots()
meli_taxonomy()      → discover_meli_roots()
Paris async          → discover_paris_roots_async()
Ripley async         → discover_ripley_roots_async()/navegación existente
```

`persist_taxonomy_result()` del foundation conecta el resultado con:

```text
mri_taxonomy_nodes
mri_taxonomy_node_history
mri_taxonomy_frontier_summary
mri_taxonomy_learning
```

La persistencia conserva:

```text
parent_category_id
hierarchical_path
taxonomy_source
source_evidence
discovery_status
run_id
```

Padre desconocido:

```text
parent_category_id=NULL
discovery_status=NOT_VERIFIED
```

No se inventan slugs como padres.

---

## 5. Frontera

Cada snapshot produce:

```text
roots_discovered
nodes_discovered
edges_verified
leaves_discovered
frontier_pending
frontier_blocked
frontier_exhausted
source_completeness=NOT_VERIFIED
```

Reglas:

```text
TAXONOMY_DISCOVERED ≠ TAXONOMY_COMPLETE
nodo bloqueado ≠ inexistente
nodo sin productos Nicopoly sigue siendo nodo
```

---

## 6. Pruebas ejecutadas

### Suite nueva de raíces

```text
tests/test_root_taxonomy_002.py
5 passed
```

Cubre:

```text
Meli API root → padre/hijo
Falabella SSR root → padre/path
Ripley host filter + dedupe
Paris MRI root shape
persistencia de raíces en taxonomy_store
```

### Suite de fundación

```text
tests/test_taxonomy_foundation_001.py
8 passed
```

### Ejecución conjunta

```powershell
python -m pytest tests/test_taxonomy_foundation_001.py ^
  tests/test_root_taxonomy_002.py -q --basetemp ...
```

Resultado:

```text
13 passed in 1.86s
```

### Regresión focalizada

```text
tests/test_live_runtime_fix_001.py
tests/test_guarded_dispatch.py
tests/test_build_instance_cleanup.py
12 passed in 41.53s
```

---

## 7. Integridad

```text
PRODUCTION_DB_UNCHANGED=PASS
SQLITE_INTEGRITY=PASS
PRODUCTION_MIGRATION=NOT_AUTHORIZED
```

No se crearon tablas `mri_taxonomy_*` en la DB operativa.

---

## 8. Archivos

Nuevos:

```text
app/mri_autonomous/taxonomy_roots.py
tests/test_root_taxonomy_002.py
```

Modificado:

```text
app/mri_dashboard/taxonomy.py
```

Preexistentes preservados:

```text
app/mri_autonomous/taxonomy_store.py
app/mri_dashboard/mri_runner.py
tests/test_taxonomy_foundation_001.py
```

---

## 9. Contrato final

```text
TASK=MRI-ROOT-TAXONOMY-DISCOVERY-002

FALABELLA_ROOT_DISCOVERY=PARTIAL
MELI_ROOT_DISCOVERY=PARTIAL
RIPLEY_ROOT_DISCOVERY=PARTIAL
PARIS_ROOT_DISCOVERY=PARTIAL

HIERARCHY_INTEGRITY=PASS
FRONTIER_PERSISTENCE=PASS
TAXONOMY_STORE_COMPATIBILITY=PASS
REGRESSION=PASS
PRODUCTION_DB_UNCHANGED=PASS

PRODUCTION_MIGRATION=NOT_AUTHORIZED
LIVE_AUDITS=NOT_EXECUTED
GIT_COMMITS=0
GIT_PUSHES=0

FINAL_STATUS=READY_FOR_INTEGRATED_VALIDATION
```

No se declara exhaustividad ni `FULL_AUDIT_VERIFIED`. El siguiente paso es aprobar la migración con respaldo y ejecutar las cuatro auditorías completas con el servidor operativo.

### Pendientes exactos

1. Aprobar y aplicar la migración `v1` sobre una copia/DB autorizada.
2. Ejecutar Falabella, Mercado Libre, Ripley y Paris completos.
3. Verificar en live que las raíces reales producen categorías y que los bloqueos quedan `SOURCE_BLOCKED`.
4. Validar publicaciones Nicopoly por categoría y posiciones orgánicas.
5. Mantener Paris Legacy intacto.
