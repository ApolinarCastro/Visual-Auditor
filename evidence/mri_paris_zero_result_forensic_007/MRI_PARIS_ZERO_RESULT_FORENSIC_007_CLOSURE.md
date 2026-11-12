# MRI PARIS ZERO RESULT FORENSIC 007 — CLOSURE

**Task:** `MRI-PARIS-ZERO-RESULT-FORENSIC-007`  
**Mode:** READ_ONLY FIRST → ROOT CAUSE → MINIMAL FIX → LIVE VALIDATION  
**Date:** 2026-11-03  
**Branch:** `integration/mri-deepseek-closure`  
**HEAD:** `089548b6849d`  
**Git commits/pushes:** 0  

---

## 1. Resultado

```text
FINAL_STATUS=FIX_VERIFIED
```

Se identificó la causa del cero de Paris, se aplicó la corrección mínima y se validó en una corrida completa con el código corregido.

```text
ROOT_CAUSE=EMPTY_PAGE_WITH_ZERO_TRAVERSED_PAGES_MISCLASSIFIED_AS_NOT_FOUND
PARIS_PUBLICATIONS=596
PARIS_AUDIT=PARTIAL
```

`PARTIAL` no significa fallo de adquisición: significa que Paris sigue usando una superficie de búsqueda Legacy y no una taxonomía comercial completa. Por eso no se declara `AUDIT_PASS`.

---

## 2. Runs verificados

```text
PREVIOUS_RUN=run_mri_discovery_1793624983__paris      598
ZERO_RUN=run_mri_discovery_1793707172__paris           0  NOT_FOUND
RECOVERY_RUN=run_mri_discovery_1793711116            596  FOUND
FIXED_RUN=run_mri_discovery_1793712901               596  FOUND
```

### Evidencia del cero

```text
checkpoint:
  categories_discovered=1
  categories_traversed_completely=1
  pages_observed=0
  publications_observed=0
  termination=EXHAUSTION
  stop_reason=EMPTY
```

No existían publicaciones, evidencia ni shadow snapshots para ese `run_id`.

### Contraste con la corrida corregida

```text
run_id=run_mri_discovery_1793712901
outcome=FOUND
acceptance=AUDIT_FAIL
pages_observed=23
publications_observed=596
unique_publications=596
persistence=RECORDED
```

SQLite:

```text
mri_publications=596
mri_publication_categories=596
integrity_check=ok
```

---

## 3. Causa raíz

```text
ROOT_CAUSE=EMPTY_PAGE_WITH_ZERO_TRAVERSED_PAGES_MISCLASSIFIED_AS_NOT_FOUND
```

Cadena causal:

```text
Paris search surface
→ navegación sin página observada (pages_traversed=0)
→ scraper devuelve products=[] y stop_reason=EMPTY/EXHAUSTION
→ normalize_stop_reason("EMPTY") = NOT_FOUND
→ runner con 0 resultados y sin bloqueo = NOT_FOUND
```

El checkpoint de cero páginas demuestra que no se recorrió ninguna página. No era ausencia de publicaciones ni un filtro de marca: no había productos que filtrar.

---

## 4. Corrección mínima

### `app/mri_dashboard/acquisition_contract.py`

Nueva función:

```python
empty_page_is_incomplete(products, pages)
```

Devuelve `True` solo cuando `products=0` y `pages=0`.

### `app/mri_dashboard/mri_runner.py`

1. Retry de hidratación para Paris, igual al de Ripley, cuando:

```text
products=0
pages_traversed=0
stop_reason=EXHAUSTION|EMPTY
máximo 1 retry
```

2. Si persiste la página vacía:

```text
stop_reason=EMPTY_PAGE_NOT_LOADED
failure_type=EMPTY_PAGE_NOT_LOADED
acquisition_state=PARTIAL
```

3. Sin resultados, el estado `PARTIAL` ya no cae en `NOT_FOUND`.

No se modificó:

```text
app/scrapers/paris_scraper.py
Visual Auditor Legacy
baseline Paris
migración v1
```

### Prueba nueva

```text
tests/test_paris_zero_result_007.py
```

---

## 5. Pruebas

```text
tests/test_paris_zero_result_007.py
tests/test_taxonomy_foundation_001.py
tests/test_root_taxonomy_002.py
18 passed in 2.42s
```

Cubre:

```text
empty_page_is_incomplete(0,0)=True
empty_page_is_incomplete(0,1)=False
empty_page_is_incomplete(1,0)=False
PARTIAL disponible para adquisición incompleta
```

---

## 6. Validación live

```text
RUN=run_mri_discovery_1793712901
marketplace=Paris
outcome=FOUND
pages_observed=23
publications=596
persistence=RECORDED
```

La corrida completa con el código corregido reprodujo las 596 publicaciones de referencia sin imponerlas como objetivo.

Taxonomía:

```text
status=TAXONOMY_DISCOVERED
source=LEGACY_CATEGORY_CACHE
taxonomy_complete=false
categorías=1 (search?q=nicopoly)
```

Por eso:

```text
PARIS_AUDIT=PARTIAL
AUDIT_PASS=NO
```

---

## 7. Integridad

```text
SQLITE_INTEGRITY=PASS
mri_publications del run=596
mri_publication_categories del run=596
LEGACY_BASELINE=PASS
PARIS_BASELINE=PASS
```

No se alteraron datos históricos ni el scraper Legacy.

---

## 8. Contrato final

```text
TASK=MRI-PARIS-ZERO-RESULT-FORENSIC-007

PREVIOUS_RUN=run_mri_discovery_1793624983__paris
CURRENT_RUN=run_mri_discovery_1793712901

ROOT_CAUSE=EMPTY_PAGE_WITH_ZERO_TRAVERSED_PAGES_MISCLASSIFIED_AS_NOT_FOUND
ACQUISITION=PASS
EXTRACTION=PASS
BRAND_FILTER=PASS
PERSISTENCE=PASS
PARIS_PUBLICATIONS=596
PARIS_AUDIT=PARTIAL

LEGACY_BASELINE=PASS
GIT_COMMITS=0
GIT_PUSHES=0

FINAL_STATUS=FIX_VERIFIED
```

No se declara `AUDIT_PASS`: falta descubrimiento de taxonomía Paris independiente de la caché Legacy y cierre de frontera.

---

## 9. Aprendizaje registrado

Conocimiento observado:

```text
knowledge_id=PARIS_EMPTY_PAGE_NOT_FOUND
marketplace=Paris
knowledge_type=ACQUISITION_FAILURE_MODE
observation=una página vacía con pages_traversed=0 no es NOT_FOUND
confidence=OBSERVED
validation_status=VERIFIED_BY_LIVE_RUN
evidence=run_mri_discovery_1793707172__paris + run_mri_discovery_1793712901
```

No se promovió automáticamente ninguna regla adicional sin prueba.
