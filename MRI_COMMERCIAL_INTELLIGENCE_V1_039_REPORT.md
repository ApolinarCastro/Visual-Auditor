# MRI_COMMERCIAL_INTELLIGENCE_V1_039_REPORT

**Tarea:** MRI-COMMERCIAL-INTELLIGENCE-V1-039 · **Fecha:** 2026-11-11
**Commit:** `452a254258ebb63a90eab42c2769cb7ba061c68e`
`feat(mri): capa de temporada, ingesta y alertas comerciales`
**Resultado:** esquema, ingesta upsert, cruce y alertas implementados. El motor de adquisición
(`mri_runner.py`) **no fue modificado**.

---

## 1. Esquema creado

`_integration/app/mri_autonomous/season_manager.py` crea automáticamente las tablas al iniciar el
dashboard (`init_season_schema()`).

### PRAGMA table_info

```text
season_registry:
  season_id, name, year, status

season_products:
  id, season_id, sku_padre, sku_hijo, nombre, precio_venta,
  mpm_ripley, mlc_meli, mkp_paris, falabella_id, ultima_actualizacion

season_observations:
  id, season_product_id, marketplace, audit_run_id, estado,
  precio_observado, precio_oferta, stock_status, posicion_observada,
  top_level, url_evidencia, fecha_observacion

season_alerts:
  id, season_product_id, marketplace, alert_type, severity,
  details, created_at, is_read
```

Índices: `idx_season_obs_product`, `idx_season_alert_product`.

## 2. Ingesta flexible

`POST /api/season/upload` (multipart) y `POST /api/season/cross`; parser con pandas que busca
columnas por alias (`SKU_PADRE`, `SKU_HIJO`, `MPM_RIPLEY`, `MLC_MELI`, `MKP_PARIS`,
`FALABELLA_ID`, etc.).

### Prueba de ingesta

No se encontró en el workspace el archivo adjunto `CHECKLIST (GRUPOS_2026 SS)`; solo están
`SVMP.xlsx` y `Actualización masiva de productos.xlsx`. Para validar el pipeline se generó
`experiments/mri_commercial_039/CHECKLIST_DEMO_039.csv` a partir de **3 publicaciones Paris reales**
del run `run_mri_discovery_1794342386__paris`.

```text
mapping: todas las columnas clave detectadas
inserted=3, updated=0, ignored=0 (primera carga)
inserted=0, updated=3, ignored=0 (segunda carga idempotente)
```

## 3. Cruce con auditoría real

`cross_audit(run_id="run_mri_discovery_1794342386__paris", season_id=1, db_path=operational)`

```json
{"ok": true, "season_id": 1, "products": 3,
 "observations": 12, "alerts": 3}
```

- 3 productos × 4 marketplaces = 12 observaciones.
- Paris: FOUND con posición observada (fuera del top 240 en la demo).
- Mercado Libre/Ripley/Falabella: NOT_FOUND para los IDs de la temporada demo.
- Alertas generadas: 3 × `TOP_CHANGE` (`TOP30 → OUTSIDE_TOP240`).

### Demostración aislada de los 3 tipos de alerta

Con un run controlado `DEMO_RUN` y 3 productos:

```json
[
  {"alert_type":"PRICE_DROP","severity":"WARN","details":{"old":9000,"new":8000}},
  {"alert_type":"PRICE_INCREASE","severity":"INFO","details":{"old":20000,"new":30000}},
  {"alert_type":"STOCK_OUTAGE","severity":"CRITICAL","details":{"old":"IN_STOCK","new":"OUT_OF_STOCK"}},
  {"alert_type":"BACK_IN_STOCK","severity":"INFO","details":{"old":"OUT_OF_STOCK","new":"IN_STOCK"}},
  {"alert_type":"TOP_CHANGE","severity":"WARN","details":{"old":"TOP30","new":"TOP90"}}
]
```

(6 alertas en total; se muestran las 5 representativas.)

## 4. API añadida

```text
GET  /api/season/status
POST /api/season/upload   (multipart file, season, year)
POST /api/season/cross    {"run_id": "...", "season_id": 1}
```

## 5. Motor de adquisición intacto

```text
git status: app/mri_runner.py = sin cambios
```

Solo se modificaron:
- `app/mri_autonomous/season_manager.py` (nuevo)
- `app/mri_dashboard/mri_api.py` (endpoints + init idempotente)

## 6. Conclusión

| Objetivo | Estado |
|---|---|
| Tablas `season_*` | **SÍ** |
| Ingesta Excel/CSV flexible | **SÍ** (probada con CSV demo; falta el Excel real adjunto) |
| UPSERT idempotente | **SÍ** (3 insertadas, luego 3 actualizadas) |
| Cruce con auditoría real | **SÍ** (12 observaciones, 3 alertas TOP) |
| Alertas precio/stock/top | **SÍ** (demostración aislada con 5 tipos) |
| `mri_runner.py` intacto | **SÍ** |
| Criterio de cierre | **PARCIAL**: falta cargar el Excel CHECKLIST real adjunto |

## 7. Estado

```text
SEASON_TABLES=CREATED
DEMO_SEASON=DEMO_039 (3 products)
OBSERVATIONS=18 (pruebas repetidas)
ALERTS=3 production demo + 6 isolated demo
RUNNER_MODIFIED=NO
CODE_COMMIT=452a254
```
