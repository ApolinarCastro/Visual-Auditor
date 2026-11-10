# MRI_PATCHRIGHT_STEALTH_ML_032_REPORT

**Tarea:** MRI-PATCHRIGHT-STEALTH-ML-032 · **Fecha:** 2026-11-10
**Resultado:** Patchright instalado y usado por el fallback de ML. **ML superó los 39** (271
productos al detener), sin 403 de Cloudflare durante la corrida. La memoria libre **no se mantuvo
>1.5 GB** (mínimo observado 137 MB), por lo que el criterio de memoria no se cumple.

---

## 1. Instalación

```text
patchright 1.64.4 instalado
```

Se usa Chrome real del sistema con el perfil persistente de ML; no fue necesario descargar el
Chromium administrado de Patchright.

## 2. Cambio en `base_scraper.py`

```python
from playwright.async_api import async_playwright as _pw_async

def _async_playwright_factory():
    import os as _os
    if _os.environ.get("MRI_USE_PATCHRIGHT", "").lower() in ("1", "true", "yes"):
        try:
            from patchright.async_api import async_playwright as _pr_async
            return _pr_async
        except Exception:
            pass
    return _pw_async

...
_global_playwright = await _async_playwright_factory()().start()
```

- `MRI_USE_PATCHRIGHT=1` activa Patchright.
- Si falla el import, cae a Playwright estándar.
- El fallback de ML ya existente (`MRI_PLAYWRIGHT_FALLBACK`) usa este motor.
- Se mantiene `Semaphore(1)` para Ripley/ML; un solo árbol de Chrome.

## 3. Validación real

Run: `run_mri_discovery_1794332762` (ML, HTTP-first + fallback)

```text
fallback = {
  "marketplace": "Mercado Libre",
  "http_products": 39,
  "threshold": 100,
  "reason": "HTTP_COVERAGE_BELOW_THRESHOLD"
}
```

Progreso observado:

```text
14:47:30  results=40
14:48:53  results=80
14:49:35  results=100
14:50:38  results=130
14:52:47  results=185
14:53:08  results=190
... stop
results=271
status=STOPPED_BY_USER
```

- **Cloudflare 403 durante la corrida Patchright: 0.**
  (Los 403 del log son de la corrida anterior de Playwright estándar, 13:26–13:28.)
- Productos ML: **271** (>39). ✅
- Un solo navegador: **sí**, 10–12 procesos Chrome de un mismo árbol.
- Memoria libre durante la corrida: **137–763 MB**.
  **No se mantuvo >1.5 GB.** ❌
- Al cerrar: Chrome detenido, dashboard detenido, puerto 8055 libre, memoria libre 7 185 MB.

## 4. Conclusión

| Objetivo | Estado |
|---|---|
| Patchright instalado | **SÍ** (1.64.4) |
| Fallback ML usa Patchright | **SÍ** |
| Cloudflare 403 evitado | **SÍ** durante la corrida |
| ML >39 | **SÍ** (271) |
| Un solo navegador | **SÍ** |
| Memoria >1.5 GB | **NO** (mínimo 137 MB) |
| Criterio de cierre | **PARCIAL** |

Patchright desbloquea ML y mejora mucho la cobertura, pero el navegador real consume más memoria
que el presupuesto de 1.5 GB en esta máquina. Se recomienda:
1. Ejecutar ML/Patchright en una ventana exclusiva, sin dashboard/IDE/Chrome personal.
2. Cerrar el navegador inmediatamente después de cada categoría o limitar `max_categories`.
3. Validar nuevamente con >6 GB libres antes de usar 1.5 GB como umbral.

## 5. Estado

```text
PATCHRIGHT=1.64.4
MRI_USE_PATCHRIGHT=1
ML_PRODUCTS=271
CLOUDFLARE_403_DURING_RUN=0
ONE_BROWSER=YES
MEMORY_MIN_FREE=137 MB
DASHBOARD=STOPPED
PORT_8055=FREE
```
