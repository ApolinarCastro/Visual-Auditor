# MRI_COMMERCIAL_INTELLIGENCE_FRONTEND_045_REPORT

**Tarea:** MRI-COMMERCIAL-INTELLIGENCE-FRONTEND-045 · **Fecha:** 2026-11-11
**Commit de código:** `9b562c1030923b0038dc0bba58298879ddb2acae`
**Resultado:** nueva vista **F. Inteligencia Comercial** operativa con pestañas Precios, Stock y
Certificación TOP. Dashboard A-E intacto. Alertas reales mostradas: 13 precios + 14 TOP.
Stock muestra vacío porque no existen eventos `STOCK_OUTAGE/BACK_IN_STOCK`.

---

## 1. Endpoints añadidos

```text
GET /api/season/alerts?type=PRICE_DROP&marketplace=Falabella&severity=WARN&limit=50
GET /api/season/summary
GET /api/season/certification?marketplace=Falabella&limit=500
```

Implementados en `mri_api.py`, apoyados en `season_manager.py`:

- `list_alerts()`: join `season_alerts` + `season_products`, filtros y `details_json`.
- `alerts_summary()`: conteos por tipo, severidad y marketplace.
- `certification()`: última observación por producto/marketplace + comparación con TOP VA.

## 2. Vista "F. Inteligencia Comercial"

Menú lateral:

```text
A. Operaciones y Resultados
B. Historial de Ejecuciones
C. Aprendizaje y Experiencia
D. Inteligencia Multimarketplace
E. Resumen Gerencial
F. Inteligencia Comercial   ← NUEVO
```

### Pestaña Precios

Tabla:

```text
SKU | Producto | Marketplace | Precio anterior | Precio actual |
Variación | Fecha | Severidad
```

- Filtros: marketplace, severidad, tipo (`PRICE_DROP`, `PRICE_INCREASE`).
- Orden por magnitud de variación descendente.
- `PRICE_DROP` en verde, `PRICE_INCREASE` en rojo.

Ejemplo real renderizado:

```text
N07128E · Top/Blusa Patrón Floral Verde Nicopoly · Falabella
$199.900 → $19.990 · -90.0% · WARN · PRICE_DROP
```

### Pestaña Stock

Tabla:

```text
⚠ | SKU | Producto | Marketplace | Estado anterior | Estado actual | Fecha | Severidad
```

- Filtros por marketplace y tipo (`STOCK_OUTAGE`, `BACK_IN_STOCK`).
- `STOCK_OUTAGE` CRITICAL se marca con ⚠ y fondo rojo.
- Sin eventos reales hoy: mensaje “Sin alertas de stock”.

### Pestaña Certificación TOP

Tabla:

```text
SKU | Producto | Marketplace | Top VA | Top MRI | ¿Coincide? | Acción
```

Resumen superior:

```text
De 336 productos, 0 coinciden, 0 con discrepancia.
VA TOP aún no persistido: se muestra TOP MRI observado.
```

- Si `coincide = NO`: ⚠ y diferencia `VA: TOP30, MRI: …`.
- VA no está persistido en MRI; no se inventaron los 280/56 del ejemplo.

## 3. Validación real

Dashboard iniciado en `http://127.0.0.1:8055` (autenticado):

```text
HTML contiene F. Inteligencia Comercial = true
HTML contiene id="commercial"           = true
```

API:

```json
{"total_alerts": 27, "products": 339,
 "by_type": [{"alert_type":"PRICE_DROP","n":13},
             {"alert_type":"TOP_CHANGE","n":14}],
 "by_severity": [{"severity":"WARN","n":27}],
 "by_marketplace": [{"marketplace":"Falabella","n":24},
                    {"marketplace":"Paris","n":3}]}
```

```text
GET /api/season/alerts?type=PRICE_DROP&limit=3 → 3 filas
GET /api/season/certification?limit=2           → 2 filas
```

JavaScript inline validado con `node --check` → OK.

Secciones A-E:

```text
#ops #hist #learn #multi #mgr = presentes
switchTab('commercial') = conectado
```

Playwright screenshot no se pudo ejecutar por `EPERM` al crear el directorio temporal del navegador
en este entorno; la validación se hizo por HTML + endpoints + parser JS.

## 4. Conclusión

| Objetivo | Estado |
|---|---|
| Vista F en menú | **SÍ** |
| Pestaña Precios | **SÍ** (13 alertas reales) |
| Pestaña Stock | **SÍ** (vacía: sin eventos) |
| Certificación TOP | **SÍ** (14 TOP reales; VA sin dato) |
| Filtros y orden | **SÍ** |
| A-E intactas | **SÍ** |
| `mri_runner.py` intacto | **SÍ** |
| Criterio de cierre | **CUMPLIDO** para visualización; stock queda vacío hasta un evento real |

## 5. Estado

```text
VIEW=INTELIGENCIA_COMERCIAL
TABS=PRECIOS/STOCK/CERTIFICACION_TOP
ALERTS_TOTAL=27
PRICE_ALERTS=13
TOP_ALERTS=14
STOCK_ALERTS=0
VA_TOP=MISSING
DASHBOARD=RUNNING
RUNNER_MODIFIED=NO
CODE_COMMIT=9b562c1
```
