# MRI_COMMERCIAL_INTELLIGENCE_V1_VALIDATE_ALERTS_044_REPORT

**Tarea:** MRI-COMMERCIAL-INTELLIGENCE-V1-VALIDATE-ALERTS-044 · **Fecha:** 2026-11-11
**Commit de código:** `b8c9c3f7a1d69487fd3e255a2f5f60b7accdcee6`
**Resultado:** simulación controlada certificada. Se generaron **PRICE_DROP** y **STOCK_OUTAGE**
reales sobre el mismo producto; los datos simulados se revirtieron.

---

## 1. Producto elegido

```text
sku_padre     = N04273A-5
sku_hijo      = N04273AXL-5
nombre        = Gilet Básico Ajustable Blanco Nicopoly
grupo         = GRUPO 1
marketplace   = Falabella
falabella_id  = 156830976
publication   = FALA_156830976
run           = run_mri_stock_043_1794419073
```

## 2. Estados inyectados

### Estado anterior simulado (`season_observations`)

```text
audit_run_id    = simulated_past_run
precio_observado = 39.990
stock_status     = IN_STOCK
top_level        = TOP30
fecha            = 2026-11-10
```

### Estado actual simulado (`mri_publications`)

```text
price_observed = 24.990
stock_status    = OUT_OF_STOCK
```

## 3. Corrección necesaria del cruce

La primera simulación produjo `PRICE_INCREASE 39990 → 299900` en vez de `PRICE_DROP`.
Causa:

1. El cruce leía solo `commercial_attributes`, no las columnas canónicas.
2. `_safe_float(24990.0)` eliminaba el punto decimal y producía `249900`.

Correcciones en `season_manager.py`:

```python
# Preferir columnas canónicas
for key in ("price_observed", "price_offer"):
    if row.get(key) is not None:
        return _safe_float(row.get(key))

# No tratar floats como texto chileno
if isinstance(v, (int, float)):
    return float(v)
```

Con eso el cruce lee `24990.0` correctamente.

## 4. Alertas generadas

```json
[
  {
    "alert_type": "PRICE_DROP",
    "severity": "WARN",
    "details": {"old": 39990.0, "new": 24990.0}
  },
  {
    "alert_type": "STOCK_OUTAGE",
    "severity": "CRITICAL",
    "details": {"old": "IN_STOCK", "new": "OUT_OF_STOCK"}
  }
]
```

Resultado del cruce:

```json
{"products": 336, "observations": 1339, "alerts": 14}
```

De las 14 alertas nuevas, **2 corresponden al producto simulado** y son exactamente
`PRICE_DROP` + `STOCK_OUTAGE`. Las otras 12 son `PRICE_DROP` históricas de otros productos,
generadas por la misma corrección de parseo.

## 5. Limpieza

Se revirtieron:

```text
season_observations simuladas (audit_run_id='simulated_past_run') = 0
observaciones nuevas insertadas por el cruce de prueba              = eliminadas
season_alerts de la prueba                                          = eliminadas
mri_publications FALA_156830976                                     = restaurada
```

Estado final:

```text
FALA_156830976: price_observed=29.990, stock_status=IN_STOCK
simulated_past_run rows = 0
target alerts = 0
```

## 6. Conclusión

| Objetivo | Estado |
|---|---|
| Producto de prueba | `N04273A-5 / FALA_156830976` |
| Estado anterior simulado | 39.990 / IN_STOCK |
| Estado actual simulado | 24.990 / OUT_OF_STOCK |
| PRICE_DROP generado | **SÍ** (`39990 → 24990`) |
| STOCK_OUTAGE generado | **SÍ** (`IN_STOCK → OUT_OF_STOCK`) |
| Datos limpiados | **SÍ** |
| `mri_runner.py` intacto | **SÍ** |
| Criterio de cierre | **CUMPLIDO** |

La lógica de alertas de precio y stock queda certificada de punta a punta.

## 7. Estado

```text
SIMULATED_PRODUCT=N04273A-5
PUBLICATION=FALA_156830976
OLD=39990/IN_STOCK
NEW=24990/OUT_OF_STOCK
PRICE_DROP=1
STOCK_OUTAGE=1
CLEANED=YES
RUNNER_MODIFIED=NO
CODE_COMMIT=b8c9c3f
```
