# MRI_FRONTEND_VISIBILITY_DRILLDOWN_050_REPORT

**Tarea:** MRI-FRONTEND-VISIBILITY-DRILLDOWN-050 · **Fecha:** 2026-11-11
**Commit de código:** `138b3887f1f7a0379ed9be8bc5e7c909205b8cde`
**Resultado:** Vista G con filas clickeables, panel inferior de historial, dos gráficos SVG y links
General/Seller. A–F y H intactas.

---

## 1. Endpoints

### Historial

```text
GET /api/mri/visibility/history?marketplace=Falabella&category=Abrigos y Chaquetas
```

Ejemplo real (10 fechas):

```json
[
  {"date":"2026-10-26","total_nicopoly":50,"top_30":0,"top_60":0,"top_240":14,
   "pct_30":0.0,"pct_60":0.0,"pct_240":28.0},
  {"date":"2026-11-03","total_nicopoly":2,"top_30":1,"top_60":1,"top_240":2,
   "pct_30":50.0,"pct_60":50.0,"pct_240":100.0},
  {"date":"2026-11-10","total_nicopoly":177,"top_30":16,"top_60":32,"top_240":127,
   "pct_30":9.04,"pct_60":18.08,"pct_240":71.75},
  {"date":"2026-11-11","total_nicopoly":82,"top_30":8,"top_60":16,"top_240":59,
   "pct_30":9.76,"pct_60":19.51,"pct_240":71.95}
]
```

### Links en `/api/mri/visibility`

Cada fila ahora incluye:

```json
"category_url": "https://www.falabella.com/falabella-cl/search?Ntt=Abrigos%20y%20Chaquetas",
"category_brand_url": "https://www.falabella.com/falabella-cl/search?Ntt=Abrigos%20y%20Chaquetas&f.product.brandName=nicopoly"
```

Construcción por marketplace:
- Falabella: `/search?Ntt=...` + `f.product.brandName=nicopoly`.
- Paris: `/search/?q=...` + `brand=nicopoly`.
- Ripley: `/search/<categoría>` + `?brand=NICOPOLY`.
- ML: catálogo con búsqueda.

## 2. Vista G — drilldown

La tabla de visibilidad ahora tiene filas:

```text
<tr style="cursor:pointer"
    data-mkt="Falabella"
    data-cat="Abrigos y Chaquetas"
    onclick="selectVisibilityRow(this)">
```

Al hacer clic:

1. Se abre `#visibility-history-panel`.
2. Se consulta `/api/mri/visibility/history`.
3. Se renderizan dos gráficos SVG:
   - **% TOP30** — línea azul.
   - **Total Nicopoly** — línea naranja.
4. Se activan dos botones:
   - **Abrir Catálogo General** → `category_url`.
   - **Abrir Catálogo Nicopoly** → `category_brand_url`.

No se agregó una dependencia externa de Chart.js; se usa un fallback SVG embebido para que el
dashboard siga funcionando sin CDN.

## 3. Validación

```text
GET /api/mri/visibility
→ category_url y category_brand_url presentes

GET /api/mri/visibility/history?marketplace=Falabella&category=Abrigos y Chaquetas
→ 10 puntos históricos reales

Secciones:
ops=True hist=True learn=True multi=True mgr=True commercial=True visibility=True season=True

JavaScript inline: node --check → OK
Dashboard: http://127.0.0.1:8055 operativo
mri_runner.py: sin cambios
```

## 4. Conclusión

| Objetivo | Estado |
|---|---|
| Endpoint historial | **SÍ** (10 fechas reales) |
| Links general/seller | **SÍ** |
| Filas clickeables | **SÍ** |
| Panel inferior | **SÍ** |
| Dos gráficos (%TOP30 y total) | **SÍ** (SVG) |
| Botones de catálogo | **SÍ** |
| A–F y H intactas | **SÍ** |
| `mri_runner.py` intacto | **SÍ** |
| Criterio de cierre | **CUMPLIDO** |

## 5. Estado

```text
VIEW=G_VISIBILITY_DRILLDOWN
HISTORY_POINTS_FALABELLA_ABRIGOS=10
CATEGORY_LINKS=GENERAL+BRAND
CHARTS=SVG_FALLBACK
SECTIONS_A-H=OK
DASHBOARD=RUNNING
RUNNER_MODIFIED=NO
CODE_COMMIT=138b388
```
