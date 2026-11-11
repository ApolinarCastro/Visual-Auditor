# MRI_COMMERCIAL_INTELLIGENCE_V1_FIX_041_REPORT

**Tarea:** MRI-COMMERCIAL-INTELLIGENCE-V1-FIX-041 · **Fecha:** 2026-11-11
**Commit de código:** `d9f36b50435c00e79b3dcffb024375cfdf4de026`
**Resultado:** Ripley corregido (330/336 FOUND), precios Falabella extraídos (110 observaciones).
No hay cambios de precio ni campo de stock real; 0 alertas de precio/stock. `mri_runner.py` intacto.

---

## 1. Diagnóstico de Ripley

```text
run 1793024285 (9.381 pubs):
  Ripley = 0 publicaciones

Ripley en toda la base = 1.220 publicaciones
Run Ripley con más datos = run_mri_discovery_1794342386__ripley (734)
```

Dos causas concretas:

1. **El run 1793024285 no incluyó Ripley** — 0 filas para ese marketplace.
2. **Los IDs del Excel no coincidían literalmente**:
   - Excel: `MPM10000316121`
   - `mri_publications.marketplace_product_id`: `10000316121`
   - Coincidencia exacta inicial: **0**.

### Corrección

`season_manager._id_candidates()` ahora prueba:

```text
MPM10000316121 → 10000316121, MPM10000316121
FALA_157780261  → 157780261
MLC-353...      → MLC353...
```

y `_ids_match()` normaliza prefijos `MPM/FALA/MLC/MKP` y IDs embebidos en slugs.

### Resultado Ripley

Cruce con `run_mri_discovery_1794342386__ripley`:

```text
Ripley FOUND     = 330
Ripley NOT_FOUND = 6
Cobertura        = 98.2 %
```

Ejemplo:

```text
N03049A · MPM10000316121 · FOUND · posición 76
https://simple.ripley.cl/blazer-...-mpm10000316121
```

## 2. Run con precio/stock

### Precio: SÍ (Falabella)

El precio real está anidado:

```json
{"observed_attributes": {"price": 34990.0, ...}}
```

`_pub_price()` ahora lee `commercial_attributes.observed_attributes.price`.

```text
Falabella: 110 observaciones con precio_observado
París/ML/Ripley: 0 precios en el run principal
```

### Stock: NO EXISTE

```text
mri_publications.commercial_attributes con stock/stock_status/availability = 0
columnas dedicadas de precio/stock = no existen
```

Campos faltantes exactos:
- `commercial_attributes.observed_attributes.stock_status` (`IN_STOCK`/`OUT_OF_STOCK`)
- o columnas `price` y `stock_status` en `mri_publications`
- histórico de precios por run para detectar cambios reales

Por eso no se pueden generar `STOCK_OUTAGE` / `BACK_IN_STOCK` reales todavía.

## 3. Resultado del cruce

Run principal: `run_mri_discovery_1793024285` (9.381 pubs), temporada `SS_2026`.

```text
products      = 336
observations  = 1.339
alerts        = 7
```

Observaciones:

```text
Falabella     1.324  (110 con precio / 110 con stock inferido)
Mercado Libre 1.344  (0 con precio/stock)
París         1.344  (0 con precio/stock)
Ripley        1.344  (0 con precio/stock)
```

Alertas:

```text
TOP_CHANGE = 7 · WARN
PRICE_DROP / PRICE_INCREASE = 0
STOCK_OUTAGE / BACK_IN_STOCK = 0
IDENTITY_MISMATCH = 0
```

### Por qué 0 alertas de precio

No hay dos runs históricos con precios distintos para los productos de temporada:

```text
Paris diff_products      = 0
Falabella diff_products  = 0
```

El precio se observa (110 valores), pero no cambió entre los runs disponibles.

### Ejemplos TOP reales

```text
TOP240 → OUTSIDE_TOP240
TOP240 → OUTSIDE_TOP240
TOP30  → OUTSIDE_TOP240
```

### Ejemplos de lógica precio/stock (demo aislado de 039)

```text
PRICE_DROP    old 9000  → 8000
PRICE_INCREASE old 20000 → 30000
STOCK_OUTAGE  IN_STOCK → OUT_OF_STOCK
BACK_IN_STOCK OUT_OF_STOCK → IN_STOCK
```

Estos ejemplos son de un run controlado, **no** datos reales del catálogo.

## 4. Integridad

```text
mri_runner.py = sin cambios
season_* = solo persistencia, sin tocar adquisición
py_compile season_manager.py = OK
API /api/season/status, /upload, /cross = activos
```

## 5. Conclusión

| Objetivo | Estado |
|---|---|
| Diagnóstico Ripley | **SÍ**: run sin Ripley + IDs MPM vs numéricos |
| Corregir cruce Ripley | **SÍ** (330/336) |
| Run con precio | **SÍ** (Falabella, nested price) |
| Run con stock | **NO** (campo inexistente) |
| Alertas precio reales | **NO** (sin cambios de precio) |
| Alertas stock reales | **NO** (sin campo de stock) |
| `mri_runner.py` intacto | **SÍ** |
| Criterio de cierre | **PARCIAL** |

**Bloqueo exacto:** falta persistir `stock_status`/`availability` en
`mri_publications.commercial_attributes` y disponer de dos runs con precios distintos.

## 6. Estado

```text
RIPLEY_MATCH=330/336
PRICE_OBSERVED_FALABELLA=110
STOCK_FIELD=ABSENT
PRICE_ALERTS=0
STOCK_ALERTS=0
TOP_ALERTS=7
RUNNER_MODIFIED=NO
CODE_COMMIT=d9f36b5
```
