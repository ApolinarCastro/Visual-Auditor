# MRI_COMMERCIAL_INTELLIGENCE_V1_COMPLETE_040_REPORT

**Tarea:** MRI-COMMERCIAL-INTELLIGENCE-V1-COMPLETE-040 · **Fecha:** 2026-11-11
**Commit de código:** `c168a7541c026b42d4f5aa66a5e038b8aab3037c`
**Resultado:** Excel real cargado (6 hojas), cruce ejecutado contra auditoría real y alertas TOP
reales generadas. `mri_runner.py` **no fue modificado**.

---

## 1. Archivo real ingerido

```text
C:\Users\ASUS Zenbook\Documents\Visibility Auditor\Chek List\CHECKLIST (GRUPOS_2026 SS).xlsx
Tamaño: 292,312,870 bytes
Hojas:  GRUPO 1, GRUPO 2, GRUPO 3, GRUPO 4, GRUPO 5, GRUPO 6
```

El parser detecta la fila real de encabezado buscando `SKU_PADRE` (las hojas tienen 3 filas de
título). Temporada creada: **`SS_2026`** (`season_id=3`).

## 2. Desglose por grupo

| Hoja | Filas de datos | Productos únicos almacenados |
|---|---:|---:|
| GRUPO 1 | 268 | 70 |
| GRUPO 2 | 196 | 53 |
| GRUPO 3 | 122 | 34 |
| GRUPO 4 | 180 | 52 |
| GRUPO 5 | 229 | 65 |
| GRUPO 6 | 204 | 62 |
| **Total** | **1 199** | **336** |

- Primera carga: `inserted=336`, `updated=863`, `ignored=0`.
- Segunda carga: `updated=1 199`, `ignored=0` (idempotente).
- Los 863 updates de la primera carga corresponden a tallas/variantes con el mismo `SKU_PADRE`
  (la tabla mantiene un registro por `sku_padre` y el `sku_hijo` de la última fila).

## 3. Primeras 5 filas de `season_products`

```text
sku_padre   sku_hijo      nombre                                                      precio   mpm_ripley       mlc_meli        mkp_paris     falabella_id  group_id
N03049A     N03049AXL     Blazer Manga 3/4 Ajustado con Solapas Blanco Nicopoly        53990    MPM10000316121   MLC3532851244   MKO9LCTA36    156819799     GRUPO 1
N03049B-7   N03049BXL-7   Blazer Manga 3/4 Ajustado con Solapas Negro Nicopoly         53990    MPM10002842879   MLC1827764303   MK4J45OPM8    156819000     GRUPO 1
N03049D-7   N03049DXL-7   Blazer Manga 3/4 Ajustado con Solapas Rojo Nicopoly          53990    MPM10002842868   MLC1626152105   MKF2ODU01R    156820386     GRUPO 1
N03049F     N03049FXL     Blazer Manga 3/4 Ajustado con Solapas Amarillo Nicopoly     53990    MPM10003538037   MLC2181839013   MKF2ODU01R    156820389     GRUPO 1
N03049G-7   N03049GXL-7   Blazer Manga 3/4 Ajustado con Solapas Beige Nicopoly       53990    MPM10002842895   MLC2913507906   MKGLG16D4F    156819792     GRUPO 1
```

## 4. Cruce con auditoría real

Run elegido: **`run_mri_discovery_1793024285`** — 9 381 publicaciones (el de mayor cobertura).
Baseline previo: `run_mri_discovery_1794342386`.

```text
BASELINE run_mri_discovery_1794342386:
  products=336, observations=1339, alerts=0

CURRENT run_mri_discovery_1793024285:
  products=336, observations=1339, alerts=7
```

Observaciones actuales por marketplace/estado:

```text
Falabella      FOUND=101  NOT_FOUND=561
Mercado Libre  FOUND=79   NOT_FOUND=593
Paris          FOUND=326  NOT_FOUND=346
Ripley         NOT_FOUND=672
```

## 5. Alertas por tipo

```text
TOP_CHANGE         WARN      7
PRICE_DROP         0
PRICE_INCREASE     0
STOCK_OUTAGE       0
BACK_IN_STOCK      0
IDENTITY_MISMATCH  0 (falsos positivos FALA_/slug corregidos)
```

### Ejemplos TOP_CHANGE reales

```text
N07068P (GRUPO 5): TOP30  → OUTSIDE_TOP240
N07041U (GRUPO 1): TOP240 → OUTSIDE_TOP240
N06041A (GRUPO 4): TOP240 → OUTSIDE_TOP240
N06040A (GRUPO 4): TOP30  → OUTSIDE_TOP240
N03049M (GRUPO 1): TOP240 → OUTSIDE_TOP240
```

Precio/stock no generaron alertas porque las publicaciones de estos runs no traen
`precio_observado` ni `stock_status` (los campos `commercial_attributes` están vacíos para este
run). La lógica de precios/stock ya fue validada con el demo aislado de 039.

## 6. Motor de adquisición intacto

```text
git status:
  M app/mri_autonomous/season_manager.py
  M app/mri_dashboard/mri_api.py
  app/mri_dashboard/mri_runner.py = sin cambios
```

API disponible:

```text
GET  /api/season/status
POST /api/season/upload   (multipart; acepta season_id=SS_2026)
POST /api/season/cross    {"audit_run_id": "...", "season_id": "SS_2026"}
```

Compilación: `py_compile` OK.

## 7. Conclusión

| Objetivo | Estado |
|---|---|
| Ingerir Excel real (6 hojas) | **SÍ** (1 199 filas, 336 productos únicos) |
| Verificar `season_products` | **SÍ** (SKU, IDs, nombre, precio, grupo) |
| Cruzar contra run real | **SÍ** (1 339 observaciones) |
| Alertas reales | **SÍ** (7 `TOP_CHANGE` reales) |
| Alertas precio/stock reales | **NO** (el run no trae precio/stock) |
| `mri_runner.py` intacto | **SÍ** |
| Criterio de cierre | **PARCIAL**: ingesta y TOP reales OK; precio/stock requieren un run con precios/stock |

## 8. Estado

```text
SEASON=SS_2026 (season_id=3)
SHEETS=6
ROWS=1199
PRODUCTS=336
GROUP_COUNTS=70/53/34/52/65/62
OBSERVATIONS=2678 (baseline+current)
ALERTS=7 TOP_CHANGE
RUNNER_MODIFIED=NO
CODE_COMMIT=c168a75
```
