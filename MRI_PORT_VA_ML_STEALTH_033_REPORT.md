# MRI_PORT_VA_ML_STEALTH_033_REPORT

**Tarea:** MRI-PORT-VA-ML-STEALTH-033 · **Fecha:** 2026-11-10
**Resultado:** la lógica de VA (warming, jerarquía de cookies, modo público y paginación
`_Desde_N`) **ya estaba portada** en `mercadolibre_scraper.py`; no requirió diff nuevo.
Validación con Patchright: **271 productos**, **0 Cloudflare 403** en la corrida.

---

## 1. Diff

**No se modificó `mercadolibre_scraper.py`**: las cuatro técnicas ya están implementadas.
Se validó su ejecución con el motor Patchright (`MRI_USE_PATCHRIGHT=1`).

## 2. Correspondencia con los pasos

| Paso VA | Implementación existente |
|---|---|
| **Warming** | `start()` líneas 48–66: visita homepage, acepta banner, scroll, marca `_warmed` |
| **Jerarquía de cookies** | `_load_or_harvest_session()` líneas 191–243: contexto persistente > memoria > `data/mercadolibre_session.json` > cosecha/Chrome |
| **Modo público** | `_detect_challenge` líneas 293–300: detecta `collaborators/shield` / `vendedores.mercadolibre.cl`, limpia cookies, activa `_public_mode`, usa `listado.mercadolibre.cl/nicopoly_Tienda_nicopoly` |
| **Paginación por URL** | `_go_to_next_page()` líneas 601–636: calcula `_Desde_49/97/145...` como segmento de path, navega, espera `li.ui-search-layout__item, .poly-card`; corta por SKUs reciclados |
| **Selectores hidratados** | `_PRODUCT_SELECTORS_PAGE` línea 31 y wait_for_selector |

## 3. Evidencia de ejecución

Run: `run_mri_discovery_1794332762` (ML, fallback Patchright)

```text
14:46:43 [Mercado Libre] Initial warming: visiting homepage...
14:46:56 [Mercado Libre] Session warmed successfully.
14:47:16 Paginando via URL: .../chaquetas-parkas-blazers/_Desde_49
14:47:20 Paginando via URL: .../_Desde_97
14:47:23 Paginando via URL: .../_Desde_145
14:53:02 Loaded 183 cookies from memory
```

### Resultado

```text
HTTP inicial = 39
Patchright fallback = 271 productos (al detener)
Cloudflare 403 durante la corrida = 0
Un solo navegador = SÍ
Memoria libre = 137–763 MB (baja, pero no es el criterio de esta tarea)
```

El modo público no se disparó porque no hubo redirección a `collaborators/shield`; el warming y la
paginación por URL sí se ejecutaron (evidencia de log).

## 4. Conclusión

| Objetivo | Estado |
|---|---|
| Warming portado | **SÍ** (ya existía, ejecutado) |
| Jerarquía de cookies | **SÍ** (183 cookies del perfil/memoria) |
| Modo público | **IMPLEMENTADO** (no disparado) |
| Paginación `_Desde_N` | **SÍ** (49/97/145) |
| ML >39 | **SÍ** (271) |
| Cloudflare 403 | **NO durante Patchright** |
| Criterio de cierre | **CUMPLIDO** |

La lógica de VA ya estaba replicada en MRI. La combinación **Patchright + warming + cookies del
perfil + paginación por URL** desbloquea ML y supera ampliamente los 39 productos.

## 5. Estado

```text
CODE_DIFF=NONE (already implemented)
ML_PRODUCTS=271
CLOUDFLARE_403=0
WARMING=EXECUTED
COOKIE_HIERARCHY=183 cookies
PAGINATION=_Desde_49/97/145
BROWSERS=1
MEMORY_MIN=137 MB
DASHBOARD=STOPPED
PORT_8055=FREE
```
