# MRI_COMMERCIAL_INTELLIGENCE_V1_FIX_042_REPORT

**Tarea:** MRI-COMMERCIAL-INTELLIGENCE-V1-FIX-042 · **Fecha:** 2026-11-11
**Commit de código:** `246bc0e6cbe92ebee526aee62d5b4e243a1610f9`
**Resultado:** columnas y persistencia implementadas; precios históricos backfill 1 510.
**Stock sigue UNKNOWN en todas las publicaciones**; no hay fuente de stock en los snapshots/atributos.
Criterio de cierre **NO cumplido** (faltan alertas reales de precio y stock).

---

## 1. Migración SQL

```sql
ALTER TABLE mri_publications ADD COLUMN price_observed REAL;
ALTER TABLE mri_publications ADD COLUMN price_offer REAL;
ALTER TABLE mri_publications ADD COLUMN stock_status TEXT DEFAULT 'UNKNOWN';
```

Implementada:
- en el esquema base (`app/storage/mri_foundation.py`);
- con migración idempotente al inicializar `PostAuditMaterializer`.

### PRAGMA verificado

```text
price_observed  REAL
price_offer     REAL
stock_status    TEXT DEFAULT 'UNKNOWN'
```

## 2. Diff de persistencia

### `post_audit_pipeline/v001/post_audit_materializer.py`

```python
price_observed, price_offer, stock_status = self._commercial_fields(snap, res)
INSERT INTO mri_publications (..., price_observed, price_offer, stock_status)
ON CONFLICT ... SET
  price_observed = COALESCE(excluded.price_observed, mri_publications.price_observed),
  price_offer = COALESCE(excluded.price_offer, mri_publications.price_offer),
  stock_status = CASE WHEN excluded.stock_status <> 'UNKNOWN'
      THEN excluded.stock_status ELSE mri_publications.stock_status END
```

`_commercial_fields()` toma:
- precio desde `snap["price"]` o `res["price"]["effective_price"]`;
- oferta desde `snap["price_multivende_offer"]`;
- stock desde `snap["stock_multivende"]` (`>0 = IN_STOCK`, `0 = OUT_OF_STOCK`).

### `app/mri_autonomous/recovery_runner.py`

Ruta usada por `AUDIT_VERIFIED_ROUTES`:

```python
"price_observed": obs_price,
"price_offer": _attr_num("price_offer", "offer_price", "sale_price", "precio_oferta"),
"stock_status": stock_from(public_attrs)
```

e insert:

```sql
INSERT OR REPLACE INTO mri_publications (..., price_observed, price_offer, stock_status)
```

## 3. Backfill histórico

```text
publicaciones con price_observed = 1 510
stock_status:
  UNKNOWN = 14 106
  IN_STOCK = 0
  OUT_OF_STOCK = 0
```

Backfill de precio desde:

```text
commercial_attributes.observed_attributes.price
commercial_attributes.price_displayed
commercial_attributes.price
```

## 4. Ejecución real pequeña

```text
Falabella TOP_N=1 → RUN_COMPLETED · 1 ruta
Falabella TOP_N=3 → RUN_COMPLETED · 3 rutas
Paris     TOP_N=1 → RUN_COMPLETED · 1 ruta
```

Pero las rutas seleccionadas **no produjeron publicaciones nuevas**:

```text
nuevas publicaciones de esos runs = 0
product_snapshots = 0
```

Por tanto no se pudo validar el llenado en una publicación nueva. El backfill confirma que la
columna funciona con datos existentes (1 510 precios).

## 5. Alertas reales de precio y stock

No se generaron:

```text
PRICE_DROP / PRICE_INCREASE = 0
STOCK_OUTAGE / BACK_IN_STOCK = 0
```

### Bloqueo exacto

1. **Stock:** no existe en la fuente. Búsqueda de claves `stock/availability/quantity` en
   `commercial_attributes` de 3 000 publicaciones → **0 claves**. `product_snapshots.stock_multivende`
   no se está poblando (`0 snapshots`).
2. **Precio:** existe y se backfilló, pero no hay dos runs con precios distintos para los productos
   de temporada; los cambios históricos observados son 0.

Campos que faltan en los adaptadores de origen:
- Falabella: `availability` / `InStock` del SSR.
- Paris: `available` / stock de Constructor.io o DOM.
- Ripley: estado del botón de compra o texto “sin stock”.
- ML: `available_quantity` / `sold_quantity`.

Sin esos campos en `commercial_attributes` o `product_snapshots`, el materializador no puede
inventar `IN_STOCK`/`OUT_OF_STOCK` y las alertas de stock no pueden generarse.

## 6. Integridad

```text
mri_runner.py = sin cambios
scrapers de adquisición = sin cambios
migración = aditiva e idempotente
compilación py_compile = OK
```

## 7. Conclusión

| Objetivo | Estado |
|---|---|
| Columnas en `mri_publications` | **SÍ** |
| Persistencia en materializador | **SÍ** |
| Persistencia en verificación de rutas | **SÍ** |
| Precio en datos existentes | **SÍ** (1 510) |
| Stock en datos existentes | **NO** (0; todo UNKNOWN) |
| Auditoría pequeña con publicaciones | **NO** (0 pubs en rutas elegidas) |
| Alerta real de precio | **NO** |
| Alerta real de stock | **NO** |
| `mri_runner.py` intacto | **SÍ** |
| Criterio de cierre | **NO CUMPLIDO** |

**Primer bloqueador demostrado:** los adaptadores no extraen ni publican stock; los snapshots están
vacíos. Sin ese dato, la columna `stock_status` queda en `UNKNOWN` y no hay alertas de stock.

## 8. Estado

```text
MIGRATION=OK
HISTORICAL_PRICES=1510
HISTORICAL_STOCK=0
SMALL_RUNS=3 COMPLETED / 0 PUBLICATIONS
STOCK_SOURCE=ABSENT
RUNNER_MODIFIED=NO
CODE_COMMIT=246bc0e
```
