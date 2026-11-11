# MRI_FRONTEND_VA_STYLE_AND_SEASON_MATRIX_047_REPORT

**Tarea:** MRI-FRONTEND-VA-STYLE-AND-SEASON-MATRIX-047 · **Fecha:** 2026-11-11
**Commit de código:** `b063319a2f1287fff77f9f7c46d1a9a7773a66c0`
**Resultado:** nuevas vistas **G. Visibilidad (Estilo VA)** y **H. Temporada (Matriz de Cruce)**
accesibles con datos reales; secciones A–F intactas.

---

## 1. Endpoints añadidos

```text
GET /api/mri/visibility
GET /api/season/matrix?season_id=SS_2026
```

### `/api/mri/visibility`

Agrupa `mri_publications` por marketplace y categoría; calcula TOP30/60/90/120/240 desde
`position`, porcentajes y nivel de presencia/riesgo.

**65 categorías** devueltas.

Ejemplo real:

```json
{
  "marketplace": "Falabella",
  "category": "Abrigos y Chaquetas",
  "total_marketplace": 390,
  "total_nicopoly": 390,
  "top_30": 26, "top_60": 54, "top_90": 83,
  "top_120": 135, "top_240": 233,
  "pct_30": 6.67, "pct_60": 13.85, "pct_90": 21.28,
  "pct_120": 34.62, "pct_240": 59.74,
  "presence_level": "EXCELENTE",
  "risk_level": "BAJO"
}
```

### `/api/season/matrix?season_id=SS_2026`

Última observación por producto y marketplace:

```text
336 SKU · 1.339 filas de cruce
FOUND=13 · NOT_FOUND=1.326
```

Ejemplo real:

```json
{
  "sku_padre": "N03049A",
  "nombre": "Blazer Manga 3/4 Ajustado con Solapas Blanco Nicopoly",
  "group_id": "GRUPO 1",
  "marketplace": "Falabella",
  "estado": "NOT_FOUND",
  "posicion_observada": null,
  "top_level": null,
  "url_evidencia": null,
  "precio_observado": null,
  "stock_status": "UNKNOWN"
}
```

## 2. Vista G — Visibilidad (Estilo VA)

Menú lateral:

```text
G. Visibilidad (Estilo VA)
```

Contenido:

- Tarjetas por marketplace con total, categorías, TOP30 y TOP240.
- Tabla de 16 columnas:
  Marketplace · Categoría · Total Canal · Total Nico · TOP30 · TOP60 · TOP90 ·
  TOP120 · TOP240 · %TOP30 … %TOP240 · Presencia · Riesgo.
- Filtros: marketplace, nivel de presencia (`EXCELENTE/BUENA/MEDIA/CRITICA`) y buscador de categoría.
- Riesgo coloreado (`CRITICO` rojo, `ALTO` ámbar).

## 3. Vista H — Temporada (Matriz de Cruce)

Menú lateral:

```text
H. Temporada (Matriz de Cruce)
```

KPIs superiores:

```text
Productos temporada          = 336
Publicados en ≥1 marketplace = 13
No encontrados               = 323
Filas de cruce               = 1.339
```

Tabla:

```text
SKU | Producto | Marketplace | Estado | Posición | Top | Precio | Stock | URL
```

- `FOUND` verde, `NOT_FOUND` rojo.
- URL con enlace “abrir”.
- Filtros por marketplace, estado y grupo (`GRUPO 1…6`).
- Se muestran hasta 800 filas por vista para mantener el navegador fluido; los filtros permiten
  inspeccionar el resto.

## 4. Validación

Dashboard reiniciado en `http://127.0.0.1:8055`:

```text
nav G. Visibilidad = true
nav H. Temporada   = true
GET /api/mri/visibility        → 65 filas
GET /api/season/matrix?SS_2026 → 1339 filas
```

Secciones existentes:

```text
ops, hist, learn, multi, mgr, commercial, visibility, season = presentes (1 cada una)
JavaScript inline validado con `node --check` = OK
```

`mri_runner.py`:

```text
git status = sin cambios
```

## 5. Conclusión

| Objetivo | Estado |
|---|---|
| Endpoint visibilidad | **SÍ** (65 categorías reales) |
| Vista G con tabla/tarjetas/filtros | **SÍ** |
| Endpoint matriz temporada | **SÍ** (1.339 filas) |
| Vista H con KPIs/tabla/filtros | **SÍ** |
| A–F intactas | **SÍ** |
| Datos reales | **SÍ** |
| `mri_runner.py` intacto | **SÍ** |
| Criterio de cierre | **CUMPLIDO** |

## 6. Estado

```text
VIEWS=G_VISIBILITY,H_SEASON_MATRIX
VISIBILITY_ROWS=65
MATRIX_ROWS=1339
SEASON_SKUS=336
FOUND_SKUS=13
DASHBOARD=RUNNING
RUNNER_MODIFIED=NO
CODE_COMMIT=b063319
```
