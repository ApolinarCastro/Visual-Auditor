# MRI_FULL_COVERAGE_VA_PARITY_035_REPORT

**Tarea:** MRI-FULL-COVERAGE-VA-PARITY-035 · **Fecha:** 2026-11-10
**Resultado:** modo secuencial VA-parity implementado; Paris falló al iniciar navegador, Ripley quedó
parcial y la memoria bajó de 1 GB. **Criterio de cierre NO cumplido.**

---

## 1. Cambios en `mri_runner.py`

Nuevo modo `MRI_VA_PARITY=1`:

```python
mkts = ["Paris", "Ripley", "Mercado Libre", "Falabella"]
execution_strategy = "ALL_SEQUENTIAL_VA_PARITY"
_browser_mkts = {"Paris", "Ripley", "Mercado Libre"}
_browser_sem = asyncio.Semaphore(1)
```

- Paris/Ripley **saltan HTTP** y usan sus scrapers Playwright existentes.
- Falabella sigue HTTP SSR.
- ML sigue HTTP + fallback Patchright.
- Un solo navegador a la vez.

## 2. Lógica VA ya existente en los scrapers

- **Paris** (`paris_scraper.py`): clic en `button:has-text("Mostrar más")`, extracción de
  `live_prices` por JS, `__next_f`.
- **Ripley** (`ripley_scraper.py`): carga de `data/ripley_session.json`, calentamiento con mouse y
  scroll, Playwright, paginación.
- **ML**: warming + jerarquía de cookies + `_Desde_N` + Patchright (validado 271 pubs).
- **Falabella**: SSR HTTP.

No se creó motor nuevo; se reutilizaron los scrapers.

## 3. Validación real

Run: `run_mri_discovery_1794333917`

```text
execution_strategy = ALL_SEQUENTIAL_VA_PARITY
orden = Paris → Ripley → Mercado Libre → Falabella
```

| Marketplace | Estado | Resultado |
|---|---|---|
| Paris | **EXTRACTOR_FAILURE / SOURCE_BLOCKED** | navegador se detuvo al iniciar |
| Ripley | EN_CURSO (detenido) | 8 páginas, 71 pubs |
| Mercado Libre | PENDIENTE | no llegó a ejecutarse |
| Falabella | **PARTIAL** | 80 páginas, 1 324 pubs |

Evidencia del fallo Paris:

```text
15:05:41 [Paris] Inicializando motor Playwright Nativo...
15:05:41 [Paris] Browser stopped safely.
```

- Un solo navegador activo: **9 procesos Chrome** de un mismo árbol.
- Memoria libre mínima: **238 MB** → por debajo de 1 GB.
- Stop manual; dashboard cerrado; puerto 8055 libre.
- `database is locked=0`; sin corrupción.

## 4. Conclusión

| Objetivo | Estado |
|---|---|
| Paris Playwright con Mostrar más/precios | **IMPLEMENTADO**, falló en ejecución |
| Ripley Playwright con sesión/warming | **IMPLEMENTADO**, parcial 71 pubs |
| Falabella HTTP | **SÍ** (1 324) |
| ML Patchright | **IMPLEMENTADO**, no se ejecutó por orden/stop |
| Secuencial / un navegador | **SÍ** (9 procesos = 1 árbol) |
| Memoria >1 GB | **NO** (mínimo 238 MB) |
| Cobertura completa 4 | **NO** |
| Criterio de cierre | **NO CUMPLIDO** |

El modo secuencial funciona, pero Paris no logra arrancar el navegador en este entorno y el consumo
de Chrome deja la memoria por debajo de 1 GB. No se declara paridad con VA.

## 5. Siguiente paso

1. Diagnosticar el cierre inmediato del navegador Paris (`Browser stopped safely` sin `started`).
2. Ejecutar Ripley/ML aislados para verificar su cobertura sin Paris.
3. Reservar >3 GB libres y ejecutar secuencialmente, cerrando cada navegador antes del siguiente.
4. Revalidar memoria y cobertura antes de declarar paridad.

## 6. Estado

```text
CODE_CHANGES=UNCOMMITTED (mri_runner.py, modo MRI_VA_PARITY)
STRATEGY=ALL_SEQUENTIAL_VA_PARITY
PARIS=EXTRACTOR_FAILURE
RIPLEY=PARTIAL 71
FALABELLA=PARTIAL 1324
ML=NOT_RUN
MEMORY_MIN=238 MB
DASHBOARD=STOPPED
PORT_8055=FREE
```
