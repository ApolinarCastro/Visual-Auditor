# MRI_COMMERCIAL_INTELLIGENCE_V1_FIX_043_REPORT

**Tarea:** MRI-COMMERCIAL-INTELLIGENCE-V1-FIX-043 · **Fecha:** 2026-11-11
**Commit de código:** `21530613ea97ec121b92fe1d67e34360bbd04ee3`
**Resultado:** Falabella ya extrae stock real (`IN_STOCK` en 48/48). Se forzó un run nuevo con 48
publicaciones y 48 precios. **No hubo OUT_OF_STOCK**, por lo que no se generó alerta de stock.
`mri_runner.py` intacto.

---

## 1. Diff de adaptadores

### Falabella (`falabella_ssr_engine.py`)

El SSR de Falabella entrega `availability` dentro de `variants[*].options[*].sizes[*].available`.
Se recorre recursivamente:

```python
_avail = []
def _collect_availability(_obj):
    if isinstance(_obj, dict):
        if "available" in _obj:
            _avail.append(bool(_obj.get("available")))
        for _v in _obj.values():
            _collect_availability(_v)
    elif isinstance(_obj, list):
        for _v in _obj:
            _collect_availability(_v)
_collect_availability(item.get("variants") or [])

stock_status = "IN_STOCK" if any(_avail) else (
    "OUT_OF_STOCK" if _avail and not any(_avail) else "UNKNOWN")
```

Se persiste en:

```sql
INSERT INTO mri_publications (..., price_observed, price_offer, stock_status)
VALUES (..., pub.price_displayed, pub.price_displayed, pub.stock_status)
```

Además se agregó `stock_status` a `NormalizedPublication` (`rea_paris_engine.py`) y a
`commercial_attributes`.

### Paris / Ripley / ML

- Paris: el modelo `NormalizedPublication` ya acepta `stock_status`, pero la respuesta
  Constructor.io de estas rutas no expone `available`; no se inventó el valor.
- Ripley/ML: no se modificó la extracción porque sus payloads actuales no traen
  `available_quantity`/estado de botón; se reporta `UNKNOWN` hasta instrumentar el DOM/API.

## 2. Auditoría forzada

Run nuevo, sin caché de snapshots:

```text
run_id = run_mri_stock_043_1794419073
fuente = Falabella SSR / brand NICOPOLY / página 1
```

Resultado:

```text
publications_materialized = 48
price_observed            = 48
stock_status:
  IN_STOCK      = 48
  OUT_OF_STOCK  = 0
  UNKNOWN       = 0
```

Consulta:

```text
run_mri_stock_043_1794419073  48 pubs
  SUM(stock_status='IN_STOCK') = 48
  SUM(stock_status='OUT_OF_STOCK') = 0
  SUM(price_observed IS NOT NULL) = 48
```

## 3. Cruce de temporada

```json
{"products": 336, "observations": 1339, "alerts": 4}
```

Alertas nuevas:

```text
TOP_CHANGE = 4
PRICE_DROP / PRICE_INCREASE = 0
STOCK_OUTAGE / BACK_IN_STOCK = 0
IDENTITY_MISMATCH = 0
```

Ejemplos TOP nuevos:

```text
OUTSIDE_TOP240 → TOP30
OUTSIDE_TOP240 → TOP60
OUTSIDE_TOP240 → TOP30
```

## 4. Alerta de stock (no generada)

No se generó `STOCK_OUTAGE` porque **el 100 % de los 48 productos observados está IN_STOCK**.
Para disparar la alerta se necesita una segunda observación donde el mismo producto pase a
`OUT_OF_STOCK`; el sitio no expone ese estado en esta captura.

La extracción ya está lista: en cuanto exista un producto con todas sus tallas
`available=false`, se persistirá `OUT_OF_STOCK` y el cruce generará la alerta.

## 5. Alerta de precio (no generada)

El run nuevo tiene precios (48), pero los precios no cambiaron respecto a las observaciones
previas de temporada:

```text
PRICE_DROP      = 0
PRICE_INCREASE  = 0
```

Se necesitan dos ejecuciones espaciadas con precios distintos.

## 6. Integridad

```text
mri_runner.py            = sin cambios
flujo DISCOVERY/AUDIT    = sin cambios
persistencia publicaciones = aditiva
py_compile               = OK
dashboard                = no se levantó durante esta prueba
```

## 7. Conclusión

| Objetivo | Estado |
|---|---|
| Falabella extrae `stock_status` | **SÍ** (48/48 IN_STOCK) |
| Nuevas publicaciones (sin caché) | **SÍ** (48) |
| Precio persistido | **SÍ** (48) |
| Alerta real de stock | **NO** (no hubo OUT_OF_STOCK) |
| Alerta real de precio | **NO** (sin segunda ejecución con cambio) |
| `mri_runner.py` intacto | **SÍ** |
| Criterio de cierre | **PARCIAL** |

**Bloqueo exacto:** no existe todavía un producto con `OUT_OF_STOCK` en la fuente. La lógica de
persistencia y extracción está operativa; falta la variación temporal real.

## 8. Estado

```text
FALABELLA_STOCK_EXTRACTED=48
IN_STOCK=48
OUT_OF_STOCK=0
NEW_PUBLICATIONS=48
NEW_PRICES=48
STOCK_ALERTS=0
PRICE_ALERTS=0
TOP_ALERTS_NEW=4
RUNNER_MODIFIED=NO
CODE_COMMIT=2153061
```
