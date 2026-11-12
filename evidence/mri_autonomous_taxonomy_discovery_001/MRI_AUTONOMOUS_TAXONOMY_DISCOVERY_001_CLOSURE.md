# MRI AUTONOMOUS TAXONOMY DISCOVERY 001 — CLOSURE

**Task:** `MRI-AUTONOMOUS-TAXONOMY-DISCOVERY-001`  
**Mode:** EVIDENCE FIRST → CAPABILITY AUDIT → BLOCKED LIVE VALIDATION  
**Branch:** `integration/mri-deepseek-closure`  
**HEAD:** `089548b6849d`  
**Date:** 2026-11-02  
**Production code changes by this task:** 0  
**Database mutations:** 0  
**Scraper executions:** 0  
**Git commits/pushes:** 0  

---

## 1. Resultado ejecutivo

```text
FINAL_STATUS=BLOCKED
LIVE_VALIDATION=BLOCKED_ENVIRONMENT
```

No hay servidor MRI escuchando en `127.0.0.1:8055` y no se ejecutó ninguna auditoría live.

La auditoría de capacidades encontró dos defectos estructurales independientes:

```text
1. Los tres marketplaces "descubiertos" parten de una búsqueda/catálogo de marca,
   no de una taxonomía raíz del marketplace.
2. mri_categories no puede persistir jerarquía: no tiene parent_id, path,
   source, discovered_at ni last_verified_at.
```

Por eso no se declara `FULL_AUDIT_VERIFIED` ni se modificó código especulativamente.

---

## 2. CP0 — Matriz de capacidades reales

| Marketplace | Entry URL | Motor / método real | Fuente de taxonomía | Parent source | Persistencia | Limitación principal |
|---|---|---|---|---|---|---|
| Falabella | `/brand/Nicopoly` | `taxonomy.falabella_taxonomy` + `FalabellaSSREngine` | `__NEXT_DATA__` del catálogo de marca | Solo en memoria (`extract_taxonomy_tree`) | `mri_categories` sin padre | Brand catalog, no árbol raíz |
| Mercado Libre | `tienda.mercadolibre.cl/nicopoly` | `DiscoveryKernel` | Storefront + API de categorías | `parent_url` parcial | `mri_categories` sin padre | Store scope; 9 categorías bloqueadas en una corrida |
| Ripley | `simple.ripley.cl/search/nicopoly` | `ripely_taxonomy_async` + `category_discoverer` | URLs de navegación observadas | **NO CAPTURADO** | `mri_categories` sin padre | Slugs de URL, no jerarquía |
| Paris | `paris.cl/search?q=nicopoly` | `discover_taxonomy` → `NOT_REQUIRED` | Ninguna; solo legacy search | Ninguno | Categorías legacy | No hay árbol comercial MRI |

### Primer defecto demostrable por marketplace

**Falabella**

```text
taxonomy.py:160-185 → falabella_taxonomy()
get_brand_catalog(brand_name=brand, page=1)
→ extract_taxonomy_tree(payload)
```

La fuente es el catálogo de la marca, no la raíz comercial del marketplace. Se observaron 14 categorías, pero no se demuestra que sean el universo raíz.

**Mercado Libre**

```text
taxonomy.py:188-222 → meli_taxonomy()
DiscoveryKernel.storefront + public category expansion
```

No parte de la taxonomía raíz. Además, en `run_mri_discovery_1793624983__mercado_libre` 9 categorías terminaron `BLOCKED`, y en `1793641074` 8.

**Ripley**

```text
taxonomy.py:67-131 → ripely_taxonomy_async()
discover_categories_from_page / discover_live_categories
→ _cat(slug, ...) con parent=None
```

Las 40 rutas son candidatos de navegación; no hay relación padre-hijo persistida ni clasificación raíz/hoja.

**Paris**

```text
taxonomy.py:146-147 y 228-230
return _result("Paris", NOT_REQUIRED, [], "PARIS_VALIDATED_BASELINE")
```

Paris no hace descubrimiento de taxonomía; usa una superficie legacy de búsqueda.

---

## 3. CP1 — Descubrimiento autónomo

No se implementó un cambio de descubrimiento en este ciclo.

Motivo:

```text
El primer defecto es de modelo de persistencia y de fuente raíz, no un selector aislado.
Sin esquema de jerarquía y sin servidor para validación live, un cambio sería especulativo.
```

No se creó un crawler nuevo ni se alteró Visual Auditor Legacy o Paris.

---

## 4. CP2 — Base de conocimiento comercial

### Esquema real

```text
mri_categories:
  category_id
  marketplace
  category_name
  canonical_url
  created_at
```

Faltan:

```text
parent_id
hierarchical_path
taxonomy_source
source_evidence
discovered_at
last_verified_at
discovery_status
```

### Estado actual

```text
mri_categories:                113 filas
mri_historical_categories:       0 filas
recovery_experiences:            0 filas
```

La estructura actual puede listar categorías, pero **no puede almacenar el árbol, su procedencia ni su historial**.

```text
TAXONOMY_PERSISTENCE=FAIL
HIERARCHY_INTEGRITY=FAIL
```

No se realizó migración destructiva ni se creó una base paralela.

---

## 5. CP3 — Recorrido de publicaciones

Se recuperaron observaciones reales de la última corrida de cada marketplace:

| Marketplace | Run | Categorías | Completas | Bloqueadas | Publicaciones |
|---|---|---:|---:|---:|---:|
| Falabella | `run_mri_discovery_1793624983__falabella` | 14 | 14 | 0 | 406 |
| Mercado Libre | `run_mri_discovery_1793641074` | 13 | 5 | 8 | 40 |
| Ripley | `run_mri_discovery_1793630598` | 40 | 40 | 0 | 761 |
| Paris | `run_mri_discovery_1793624983__paris` | 1 | 1 | 0 | 598 |

Total de observaciones categoría-publicación en el artefacto:

```text
1,805 filas
```

### Contrato de observación

```text
organic_position=UNKNOWN
sponsored_status=UNKNOWN
product_title=NOT_STORED
page_number=UNKNOWN
position_on_page=UNKNOWN
```

No se inventaron posiciones orgánicas ni separación de patrocinados: SQLite no contiene evidencia suficiente en estas corridas.

---

## 6. CP4 — Aprendizaje autónomo

```text
recovery_experiences: 0
mri_historical_categories: 0
```

El artefacto de aprendizaje contiene 68 observaciones de estado de categoría, todas marcadas:

```text
confidence=OBSERVED
validation_status=NOT_VERIFIED
```

No se promovió ninguna hipótesis a regla operativa.

```text
AUTONOMOUS_LEARNING=FAIL
```

No se reutilizó experiencia verificada porque no existe almacenada para estas categorías.

---

## 7. CP5 — Estado específico

### Falabella

- 14/14 categorías observadas completas.
- 406 publicaciones.
- Taxonomía derivada de catálogo de marca.
- Sin jerarquía persistida.
- `TAXONOMY=PARTIAL`.

### Mercado Libre

- 13 categorías descubiertas.
- 5 completas y 8 bloqueadas en la última corrida.
- 40 publicaciones.
- Storefront scope, no raíz.
- `TAXONOMY=PARTIAL`.

### Ripley

- 40/40 rutas completas.
- 761 publicaciones.
- Sin parent_id; las rutas no se demostraron como árbol.
- `TAXONOMY=PARTIAL`.

### Paris

- 1/1 superficie legacy.
- 598 publicaciones.
- Sin taxonomía MRI; baseline intacto.
- `TAXONOMY=FAIL`.

---

## 8. CP6 — Contrato de exhaustividad

### Descubrimiento

```text
TAXONOMY_ROOTS_FOUND=0
TAXONOMY_NODES_FOUND=68 observados / 181 en unión con caché
TAXONOMY_EDGES_FOUND=0 persistidos
TAXONOMY_LEAVES_FOUND=UNKNOWN
DISCOVERY_FRONTIER_PENDING=UNKNOWN
DISCOVERY_FRONTIER_BLOCKED=8
DISCOVERY_FRONTIER_EXHAUSTED=60 categorías completas
TAXONOMY_SOURCE_COMPLETENESS=NOT_VERIFIED
TAXONOMY_COMPLETENESS=NOT_VERIFIED
```

### Observación

```text
CATEGORIES_IN_SCOPE=68
CATEGORIES_COMPLETED=60
CATEGORIES_PARTIAL=0
CATEGORIES_BLOCKED=8
PAGES_OBSERVED=variable por corrida; ver checkpoints
PUBLICATIONS_OBSERVED=1,805
PUBLICATIONS_UNIQUE=1,805
OBSERVATIONS_PERSISTED=1,805
```

`FOUND`, `TAXONOMY_DISCOVERED` y `CATEGORY_TRAVERSED` no se promovieron a `AUDIT_PASS`.

---

## 9. CP7 — Pruebas y regresiones

No se ejecutaron pruebas live porque no hay servidor.

Comprobaciones deterministas realizadas:

| Comprobación | Resultado |
|---|---|
| Integridad SQLite | PASS (`ok`) |
| Esquema de categorías | FAIL: sin jerarquía/fuente/fechas |
| `mri_historical_categories` | 0 filas |
| `recovery_experiences` | 0 filas |
| Aislamiento de categorías por marketplace | PASS en consultas |
| Categorías observadas | 68 |
| Publicaciones categoría | 1,805 filas |
| Código funcional modificado por esta tarea | 0 |
| Baseline Paris | no modificado |

```text
LIVE_VALIDATION=BLOCKED_ENVIRONMENT
LEGACY_REGRESSION=FAIL (no ejecutada; no se declara PASS sin evidencia)
```

---

## 10. CP8 — Entregables

Ruta:

```text
_integration/evidence/mri_autonomous_taxonomy_discovery_001/
```

Archivos:

```text
MRI_AUTONOMOUS_TAXONOMY_DISCOVERY_001_CLOSURE.md
MRI_MARKETPLACE_TAXONOMY_001.csv       (4 marketplaces)
MRI_TAXONOMY_HIERARCHY_001.csv         (181 nodos; parent UNKNOWN)
MRI_TAXONOMY_FRONTIER_001.csv          (181 filas)
MRI_CATEGORY_PUBLICATIONS_001.csv      (1,805 observaciones)
MRI_AUTONOMOUS_LEARNING_001.csv        (68 observaciones, no verificadas)
MRI_MARKETPLACE_ACCEPTANCE_001.csv     (4 marketplaces)
taxonomy_summary.json
```

---

## 11. Contrato final

```text
TASK=MRI-AUTONOMOUS-TAXONOMY-DISCOVERY-001

MARKETPLACES=4
MULTIVENDE_DEPENDENCY=NONE

FALABELLA_TAXONOMY=PARTIAL
MELI_TAXONOMY=PARTIAL
RIPLEY_TAXONOMY=PARTIAL
PARIS_TAXONOMY=FAIL

FALABELLA_AUDIT=BLOCKED
MELI_AUDIT=BLOCKED
RIPLEY_AUDIT=BLOCKED
PARIS_AUDIT=BLOCKED

TAXONOMY_PERSISTENCE=FAIL
HIERARCHY_INTEGRITY=FAIL
DISCOVERY_FRONTIER=FAIL
CATEGORY_OBSERVATION=PARTIAL
AUTONOMOUS_LEARNING=FAIL
HISTORICAL_INTEGRITY=PASS
LEGACY_REGRESSION=FAIL
PARIS_BASELINE=PASS

LIVE_VALIDATION=BLOCKED_ENVIRONMENT
PRODUCTION_FILES_CHANGED=0
DATABASE_MUTATIONS=0
GIT_COMMITS=0
GIT_PUSHES=0

FINAL_STATUS=BLOCKED
```

### Condición para desbloquear

1. Añadir al esquema una representación no destructiva de jerarquía y procedencia.
2. Descubrir desde raíz comercial, no desde búsqueda de marca.
3. Persistir nodos, padres, fuente y fechas.
4. Implementar frontera persistente y estados `PENDING/BLOCKED/EXHAUSTED`.
5. Iniciar MRI y ejecutar las cuatro auditorías completas.
6. Validar jerarquía, paginación, publicaciones, patrocinados y baseline.

No se declara `FULL_AUDIT_VERIFIED`.
