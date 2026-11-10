# MRI_PLAYWRIGHT_FALLBACK_031_REPORT

**Tarea:** MRI-PLAYWRIGHT-FALLBACK-ML-RIPLEY-031 · **Fecha:** 2026-11-10
**Resultado:** fallback secuencial implementado; ML lo ejecutó con **un solo navegador** y memoria
libre **>3.8 GB**, pero **ML sigue en 39 productos** por bloqueo Cloudflare 403.

---

## 1. Cambio en `mri_runner.py`

En el camino HTTP-first:

```python
_min_http = int(os.getenv("MRI_MIN_HTTP_PRODUCTS", "100"))
_fallback_on = os.getenv("MRI_PLAYWRIGHT_FALLBACK", "1") not in ("0", ...)

_needs_browser = (
    mkt in ("Ripley", "Mercado Libre")
    and len(_prods) < _min_http
    and _fallback_on)

if _needs_browser:
    self.state["playwright_fallback"].append({
        "marketplace": mkt,
        "http_products": len(_prods),
        "threshold": _min_http,
        "reason": "HTTP_COVERAGE_BELOW_THRESHOLD"})
    # cae al camino Playwright existente
else:
    continue
```

- Paris/Falabella: siempre HTTP (`continue`).
- Ripley/ML: HTTP primero; si `< MRI_MIN_HTTP_PRODUCTS` (>100), usa el scraper existente.
- El padre mantiene `_browser_sem = Semaphore(1)` para Ripley/ML.
- Se reutilizan `ripley_scraper.py` / `mercadolibre_scraper.py`; no se creó motor nuevo.
- Flags ligeros ya existentes: `MRI_FORCE_HEADLESS=1`, `MRI_LIGHT_BROWSER=1`,
  `imagesEnabled=false`, `--js-flags=--max-old-space-size=512`.

## 2. Validación real (ML)

Comando lógico:

```text
MRI_HTTP_FIRST=1
MRI_MAX_BROWSER_CONCURRENCY=1
MRI_PLAYWRIGHT_FALLBACK=1
MRI_FORCE_HEADLESS=1
MRI_LIGHT_BROWSER=1
```

Run: `run_mri_discovery_1794327744`

```text
fallback = {"marketplace":"Mercado Libre",
            "http_products":39,
            "threshold":100,
            "reason":"HTTP_COVERAGE_BELOW_THRESHOLD"}
```

Durante el fallback:

- Procesos Chrome/headless: **8** (un solo árbol de navegador, no dos).
- Memoria libre mínima observada: **3 896 MB** (>1.5 GB).
- Categorías recorridas: Chaquetas, Blusas, Pantalones, Vestidos, Chalecos, Poleras,
  Camisas, Calzas, Enteritos, Faldas, Bermudas, Kimonos.
- Cada página devolvió **Cloudflare 403 / “No se encontraron productos”**.
- Al final: `Browser stopped safely`, Chrome=0, resultados=39, estado **PARTIAL**.

Conclusión parcial:

```text
HTTP=39
Playwright=0 adicionales (403 Cloudflare)
RESULTS=39
BROWSER_CLOSED=YES
ONE_BROWSER=YES
MEMORY_MIN_FREE=3896 MB
```

## 3. Paris/Falabella

No se tocaron: siguen en HTTP-first y no pasan por el fallback.
Ripley HTTP obtuvo 258 en pruebas previas (>100), por lo que no dispara Playwright con el umbral
actual; para forzarlo se puede subir `MRI_MIN_HTTP_PRODUCTS` por encima de 258.

## 4. Conclusión

| Objetivo | Estado |
|---|---|
| Fallback secuencial para ML/Ripley | **IMPLEMENTADO** |
| Un solo navegador a la vez | **SÍ** (un árbol Chrome) |
| Memoria >1.5 GB | **SÍ** (mínimo 3.9 GB) |
| Paris/Falabella HTTP | **SÍ** (sin cambios) |
| ML >39 | **NO** (Cloudflare 403 en listado) |
| Criterio de cierre | **PARCIAL** |

El mecanismo es correcto y ligero; el bloqueo de cobertura de ML es del sitio (Cloudflare 403), no
del fallback. Para superar 39 hace falta una sesión/token de ML válida o un endpoint no bloqueado.

## 5. Estado

```text
FALLBACK=IMPLEMENTED
ML_HTTP=39
ML_PLAYWRIGHT=0 (403)
BROWSERS_CONCURRENT=1
BROWSER_CLOSED=YES
MEMORY_MIN_FREE=3896 MB
DASHBOARD=RUNNING
```

Cambios de código pendientes de commit en esta tarea.
