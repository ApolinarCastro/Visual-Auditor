# MRI_HTTP_PAGINATION_022_REPORT

**Tarea:** MRI-HTTP-PAGINATION-022 · **Fecha:** 2026-11-10
**Commit:** `5a1c8bd67059c8c0fb3727cdd9ea022b69baf1a5`
`feat(mri): paginacion HTTP Paris y Ripley sin navegador`
**Resultado:** Paris **400** y Ripley **258** productos sin navegador; **ML queda en 39**
(paginación bloqueada por la API/storefront). Memoria mínima **4 739 MB**.

---

## 1. Parámetros de paginación descubiertos

| Marketplace | Parámetro | Comportamiento |
|---|---|---|
| **Paris** | `page=N` en `REAParisEngine.search` + `num_results=40` | 40 por página, `total_num_results=4882`; 10 páginas → 400 únicos |
| **Ripley** | `&page=N` en la URL de categoría | 48 por página, `findabilityProps.data.total=260`; 6 páginas → 258 únicos |
| **Mercado Libre** | `?page=2`, `?_Desde_=49` | **ignorados** por el storefront; devuelve el mismo conjunto |
| ML API | `api.mercadolibre.com/sites/MLC/search?...` | **HTTP 403** sin autenticación |
| ML listado | `listado.mercadolibre.cl/...` | requiere verificación humana → **SOURCE_BLOCKED** |

## 2. Implementación

### Paris

```python
max_pages = int(os.getenv("MRI_HTTP_MAX_PAGES", "10"))
for page in range(1, max_pages + 1):
    payload = engine.search("nicopoly", page=page, num_results=40)
    ... dedupe por SKU ...
    if not results or new == 0:
        break
```

### Ripley (`ripley_http_engine.py`)

```python
for page in range(1, limit + 1):
    page_url = url + ("&" if "?" in url else "?") + f"page={page}"
    data = fetch __NEXT_DATA__
    ... dedupe por SKU ...
    if not batch or new == 0:
        break
```

### ML

Se mantiene el storefront SSR actual (39 publicaciones). No se fuerza `listado` ni la API 403;
se documenta como límite de cobertura y no se lanza Playwright.

## 3. Resultados medidos (sin navegador)

Ejecución local de `_http_first_discovery` para los 3 marketplaces:

| Marketplace | Antes | Después | Tiempo | Método |
|---|---:|---:|---:|---|
| **Paris** | 40 | **400** | **14.68 s** | `HTTP_CONSTRUCTOR_PAGINATED` |
| **Ripley** | 48 | **258** | **8.93 s** | `HTTP_RIPLEY_SSR` |
| **Mercado Libre** | 39 | **39** | 0.67 s | `HTTP_MELI_SSR` |

Falabella conserva 1 328 publicaciones SSR (referencia 020).

### Memoria

```text
libre inicial = 4 739 MB
mínimo durante 3 marketplaces = 4 739 MB
libre final = 4 876 MB
```

**>2 GB en todo momento**; sin Chromium.

## 4. Diferencias y límites

- **Paris:** cobertura 10× (40 → 400), 14.7 s; dentro del límite `MRI_HTTP_MAX_PAGES=10`.
- **Ripley:** cobertura 5.4× (48 → 258), 8.9 s; 6 páginas hasta agotar 260.
- **ML:** no se supera 39 porque el storefront no expone paginación HTTP y la API pública
  devuelve 403. Se requiere endpoint autenticado o un API interno del storefront.
- **Criterio de 100+:** Paris y Ripley cumplen; **ML no cumple** todavía.

## 5. Conclusión

- **Paris y Ripley alcanzaron cobertura >100 sin Playwright** (400 y 258).
- **ML sigue limitado a 39**; no se debe declarar cobertura completa para ML.
- Memoria estable **>2 GB** y velocidad de segundos; sin navegadores.
- **8 GB: SÍ** para el modo HTTP actual; ML requiere investigación de API autenticada.
- Próxima prioridad: resolver paginación ML (API/token o endpoint interno) y ampliar Paris/Ripley
  más allá de 10 páginas solo si el límite de seguridad se eleva.

## 6. Estado

```text
PARIS=400 HTTP
RIPLEY=258 HTTP
ML=39 HTTP (paginacion bloqueada)
FALABELLA=1328 SSR (referencia)
MEMORY_MIN_FREE=4739 MB
PLAYWRIGHT=0
COMMIT=5a1c8bd
PUSH=origin/integration/mri-deepseek-closure
```
