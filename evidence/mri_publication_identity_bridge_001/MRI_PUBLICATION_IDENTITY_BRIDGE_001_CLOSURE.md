# MRI PUBLICATION IDENTITY BRIDGE 001 — CLOSURE

**Task:** `MRI-PUBLICATION-IDENTITY-BRIDGE-001`  
**Mode:** READ_ONLY / EVIDENCE FIRST  
**Branch:** `integration/mri-deepseek-closure`  
**HEAD:** `089548b6849d`  
**Date:** 2026-11-02  
**Production code changes:** 0  
**Database mutations:** 0  
**Scraper executions:** 0  
**Commits/pushes:** 0  

---

## 1. Resultado ejecutivo

```text
FINAL_STATUS=REFERENCE_GAPS_IDENTIFIED
```

La reconciliación de las ocho corridas se completó desde SQLite, historia y checkpoints.

No existe todavía un puente SKU→publicación verificable:

```text
EXPECTED_SKU_CHANNEL_RELATIONS=8,585
CONFIRMED_LINKS=0
UNLINKED_EXPECTATIONS=8,585
UNMATCHED_OBSERVATIONS=2,556
EXPECTED_PUBLICATIONS_TOTAL=UNKNOWN
```

### Primer bloqueo demostrado

```text
NO_CHANNEL_PUBLICATION_ID
```

El catálogo maestro tiene `SKU_PADRE` y `SKU_HIJO`, pero no contiene `publication_id` ni `marketplace_product_id` por canal. `mri_variants` está vacía y no existe un `seller_sku` que permita unir SKU→publicación.

Sin esa referencia no se puede construir un denominador de publicaciones esperadas ni elevar una coincidencia de título a identidad confirmada.

---

## 2. CP0 — Inventario de fuentes

| SOURCE_ID | PATH | TYPE | AUTHORITY | LIMITATIONS |
|---|---|---|---|---|
| CATALOG_MASTER | `_integration/Actualización masiva de productos.xlsx` | XLSX, 22.4 MB | Catálogo comercial | Sin IDs de publicación por canal |
| SVMP | `SVMP.xlsx` | XLSX histórico | Categorías/totales históricos | Fechas mayo–septiembre 2026, no vigente |
| OPERATIONAL_DB | `data/sqlite/mri_operational/visibility.db` | SQLite | Observaciones y persistencia | No contiene SKU maestro |
| HISTORY | `mri_history.json` | JSON, 174.5 MB | Resultados de corridas | Hijos ALL sin entrada propia en algunos casos |
| CHECKPOINTS | `data/sqlite/mri_operational/mri_coverage_checkpoint_*.json` | JSON | Categorías y estados | Solo alcance observado |
| VARIANTS | tabla `mri_variants` | SQLite | Puente potencial SKU | **0 filas** |

### Estado de la DB

```text
integrity_check=ok
mri_publications=13,128
```

No se modificó ninguna base.

---

## 3. CP1 — Identidad y jerarquía

### Búsqueda de identificadores reales

Se inspeccionaron:

```text
mri_publications.publication_id
mri_publications.marketplace_product_id
mri_publications.product_id
mri_publications.canonical_url
mri_publications.commercial_attributes
mri_variants.seller_sku
```

Resultados:

```text
publication_id por canal en catálogo maestro: NO EXISTE
marketplace_product_id por canal:           NO EXISTE
seller_sku en mri_variants:                 NO EXISTE (tabla vacía)
coincidencias exactas SKU en IDs observados: 0
coincidencias exactas SKU en texto observado: 0
```

### Clasificación del puente

```text
CONFIRMED_DIRECT=0
CONFIRMED_CROSS_SOURCE=0
CANDIDATE_REVIEW=0
UNLINKED=8,585
CONFLICT=0
```

Todos los enlaces potenciales quedaron `UNLINKED`. No se elevó ninguna coincidencia de título ni URL a identidad confirmada.

---

## 4. CP2 — Reconciliación de las ocho corridas

| RUN_ID | MARKETPLACE | OCCURRENCES | UNIQUE | ACTIVE | HISTORICAL | CATEGORY MEMBERSHIPS | DUPLICATES | SOURCE_BLOCKED |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `run_mri_discovery_1793622915` | Falabella | 404 | 404 | 213 | 191 | 595 | 0 | 0 |
| `run_mri_discovery_1793623173` | Mercado Libre | 585 | 571 | 176 | 395 | 966 | 14 | 0 |
| `run_mri_discovery_1793624983__mercado_libre` | Mercado Libre | 357 | 357 | 357 | 0 | 357 | 0 | 9 |
| `run_mri_discovery_1793624983__paris` | Paris | 598 | 598 | 598 | 0 | 598 | 0 | 0 |
| `run_mri_discovery_1793624983__ripley` | Ripley | 766 | 766 | 5 | 761 | 1,527 | 0 | 0 |
| `run_mri_discovery_1793624983__falabella` | Falabella | 406 | 406 | 406 | 0 | 406 | 0 | 0 |
| `run_mri_discovery_1793630598` | Ripley | 766 | 761 | 761 | 0 | 761 | 5 | 0 |
| `run_mri_discovery_1793641074` | Mercado Libre | 40 | 40 | 40 | 0 | 40 | 0 | 8 |

### Diferencias exactas por marketplace

**Falabella**

```text
404 vs 406
intersección: 191
solo primera: 213
solo segunda: 215
unión: 619
```

La primera corrida tiene 213 activas + 191 históricas; la segunda 406 activas. Los conjuntos no son idénticos, pero no hay evidencia de pérdida: hay cambios de IDs/alcance y una división activa/histórica.

**Mercado Libre**

```text
571 vs 357 → intersección 355; solo 571: 216; solo 357: 2
357 vs 40  → intersección 0
```

La reducción no es una pérdida de persistencia:

- 357 completó 4 categorías y tuvo 9 bloqueadas.
- 40 completó 5 categorías y tuvo 8 bloqueadas.
- Las categorías completadas son distintas; por eso los IDs observados son disjuntos.

**Ripley**

```text
766 vs 761 → intersección 761; solo hijo ALL: 5
```

La corrida standalone tiene 766 ocurrencias y 761 identidades únicas: 5 duplicados de URL canónica. La corrida hija conserva 766, con 5 activas y 761 históricas.

**Paris**

```text
598 ocurrencias = 598 identidades
```

---

## 5. CP3 — Expected vs observed

```text
Expectativas SKU-canal:       8,585
Confirmadas y enlazadas:          0
Sin enlace:                   8,585
Observaciones únicas:         2,556
Observaciones sin match:      2,556
```

Por marketplace:

| Marketplace | SKU-canal esperadas | Observadas únicas | Enlazadas |
|---|---:|---:|---:|
| Falabella | 1,640 | 619 | 0 |
| Mercado Libre | 2,315 | 573 | 0 |
| Ripley | 2,315 | 766 | 0 |
| Paris | 2,315 | 598 | 0 |

No se clasificó ninguna expectativa como `EXPECTED_NOT_OBSERVED` confirmada: falta denominador de publicación y no hay recorrido completo certificado.

---

## 6. CP4 — Denominador de publicaciones

```text
EXPECTED_SKU_CHANNEL_RELATIONS=8,585
CONFIRMED_PUBLISHED_IDENTITIES=0
EXPECTED_PUBLICATION_IDS=0
OBSERVED_PUBLICATION_IDS=2,556
CONFIRMED_MATCHES=0
UNLINKED_EXPECTATIONS=8,585
UNMATCHED_OBSERVATIONS=2,556
EXPECTED_PUBLICATIONS_TOTAL=UNKNOWN
```

No se usaron las 8,585 relaciones SKU-canal como publicaciones.

---

## 7. CP5 — Categorías

Se conservaron 148 filas de categoría-observación correspondientes a las ocho corridas.

Clasificación de las categorías observadas:

```text
OBSERVED_ONLY: 148 filas
CON INDEPENDENT CATEGORY REFERENCE: 0
NO_VERIFICADO: todas
```

Categorías únicas observadas:

```text
Falabella:     14
Mercado Libre: 13
Ripley:        40
Paris:          1
Total:         68
```

### Sobre los CORRECT históricos

En las ocho corridas hay 2,556 registros activos/históricos de publicación:

```text
CORRECT:          1,597
REVIEW_REQUIRED:    228
NO_VERIFICADO:      726
INCORRECT:            5
```

Los 1,597 `CORRECT` tienen `category_expected` poblado, pero su fuente es una observación del listing/breadcrumb, no una referencia maestra independiente con ID de categoría del marketplace. Por lo tanto:

```text
CORRECT_CON_REFERENCIA_INDEPENDIENTE=0
```

No se modificó ningún estado histórico. Los 406 Falabella `NO_VERIFICADO` conservan ese estado.

---

## 8. CP6 — Cobertura y taxonomía

```text
Falabella:      14/14 categorías observadas
Mercado Libre:   4/13 completas (357) o 5/13 (40)
Ripley:         40/40 categorías observadas
Paris:           1/1 superficie Legacy
```

Tipos de superficie observados:

```text
Falabella:     brand/category surfaces + breadcrumbs
Mercado Libre: store category URLs + listing membership
Ripley:        navigation category URLs
Paris:         search?q=nicopoly
```

No se declara ninguna como taxonomía oficial completa:

```text
GLOBAL_TAXONOMY_COMPLETENESS=NOT_VERIFIED
```

---

## 9. CP7 — Validaciones

| Validación | Resultado |
|---|---|
| Ocho corridas reconciliadas | PASS |
| Identidades únicas vs ocurrencias | PASS; duplicados explicados (ML 14, Ripley 5) |
| Aislamiento por marketplace | PASS |
| SKU padre/variante | 15,833 variantes, 4,337 padres; sin IDs de publicación |
| Conflictos de identidad | 8 registros en `MRI_IDENTITY_CONFLICTS_001.csv` |
| URLs canónicas duplicadas | 5 en Ripley standalone; 14 ocurrencias en ML standalone |
| Persistencia histórica | PARTIAL; hay filas históricas sin historia JSON propia |
| Membresías de categoría | calculadas desde tablas activas e históricas |
| SQLite vs historia/checkpoints | PASS con diferencias explicadas |
| Separación orgánico/patrocinado | no verificable desde el puente actual |
| Integridad física | PASS (`integrity_check=ok`) |

---

## 10. CP8 — Entregables

Ruta:

```text
_integration/evidence/mri_publication_identity_bridge_001/
```

Archivos:

```text
MRI_PUBLICATION_IDENTITY_BRIDGE_001_CLOSURE.md
MRI_PUBLICATION_IDENTITY_BRIDGE_001.csv        (8,585 filas, todas UNLINKED)
MRI_RUN_IDENTITY_RECONCILIATION_001.csv        (8 corridas)
MRI_EXPECTED_OBSERVED_GAPS_001.csv             (4 marketplaces)
MRI_CATEGORY_REFERENCE_VALIDATION_001.csv      (148 filas)
MRI_IDENTITY_CONFLICTS_001.csv                 (8 conflictos/brechas)
identity_bridge_summary.json
```

---

## 11. Respuestas explícitas

### 1. ¿Cuántas publicaciones esperadas pueden identificarse con certeza?

```text
0
```

Hay 8,585 relaciones SKU-canal, pero ninguna tiene un ID de publicación de canal.

### 2. ¿Cuántas están vinculadas con observaciones MRI?

```text
0
```

### 3. ¿Cuántas relaciones permanecen sin resolver?

```text
8,585 expectativas sin enlace
2,556 observaciones sin match
```

### 4. ¿Qué fuentes faltan?

```text
publication_id por marketplace
marketplace_product_id por SKU
seller_sku en mri_variants
taxonomía oficial del marketplace
referencia vigente de categoría esperada
```

### 5. ¿Cuáles son las diferencias reales entre las ocho auditorías?

- Falabella cambió de 404 a 406 identidades; intersección 191.
- ML pasó de 571 a 357 y luego a 40; la caída se explica por categorías completadas distintas y bloqueos, no por borrado.
- Ripley tiene 766 ocurrencias/761 únicas y 5 duplicados de URL; la corrida hija conserva 761 históricas + 5 activas.
- Paris tiene 598 identidades estables en una única superficie legacy.

### 6. ¿Qué categorías pueden validarse con evidencia independiente?

```text
0
```

Ninguna categoría observada tiene un ID oficial de categoría del marketplace en las fuentes disponibles.

### 7. ¿Qué condiciones faltan para una auditoría certificable?

1. ID de publicación por canal vinculado a SKU.
2. Denominador de publicaciones esperadas.
3. Categoría esperada con ID oficial y fecha de vigencia.
4. Taxonomía global con fuente independiente.
5. Cobertura completa del alcance sin bloqueos.
6. Reconciliación publicación-categoría-posición.

---

## 12. Contrato final

```text
TASK=MRI-PUBLICATION-IDENTITY-BRIDGE-001

MODE=READ_ONLY
MARKETPLACES_ANALYZED=4
RUNS_RECONCILED=8

CATALOG_SOURCE=VERIFIED
MULTIVENDE_REFERENCE=PARTIAL
IDENTITY_BRIDGE=FAIL
PUBLICATION_DENOMINATOR=UNKNOWN
CATEGORY_REFERENCE=PARTIAL

FALABELLA_LINKED=0
MELI_LINKED=0
RIPLEY_LINKED=0
PARIS_LINKED=0

IDENTITY_CONFLICTS=8
UNLINKED_EXPECTATIONS=8585
UNMATCHED_OBSERVATIONS=2556

RUN_RECONCILIATION=PASS
PERSISTENCE_INTEGRITY=PASS
HISTORICAL_EVIDENCE=PARTIAL
LEGACY_BASELINE=PASS

PRODUCTION_CODE_CHANGES=0
DATABASE_MUTATIONS=0
SCRAPER_EXECUTIONS=0
GIT_COMMITS=0
GIT_PUSHES=0

FINAL_STATUS=REFERENCE_GAPS_IDENTIFIED
```

No se declara `IDENTITY_BRIDGE_VERIFIED` ni `AUDIT_PASS`.

### Condición de cierre P0

La siguiente intervención debe recibir una exportación de Multivende o del integrador con:

```text
SKU padre
SKU variante
marketplace
publication_id
marketplace_product_id
estado de publicación
categoría asignada
fecha de actualización
```

Sin esa fuente, MRI puede reconciliar observaciones entre corridas, pero no puede unirlas al catálogo maestro ni certificar publicaciones esperadas.
