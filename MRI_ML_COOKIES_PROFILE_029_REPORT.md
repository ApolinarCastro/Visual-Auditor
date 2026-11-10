# MRI_ML_COOKIES_PROFILE_029_REPORT

**Tarea:** MRI-ML-COOKIES-FROM-PROFILE-029 · **Fecha:** 2026-11-10
**Resultado:** las **35 cookies guardadas** de ML ya se inyectan en el motor HTTP.
El conteo de productos **sigue en 39**; las cookies no desbloquean la paginación del storefront.

---

## 1. Dónde estaban las cookies

```text
_integration/data/sessions/mercado_libre_cookies.json
updated_at = 2026-11-06T12:08:43
cookies    = 35
```

El archivo lo administra `app/mri_dashboard/session_store.py` (mismo store del panel de sesiones).

## 2. Cambio en `meli_http_engine.py`

```python
def _cookies(self):
    cookies = {}
    if USE_SAVED_COOKIES != "0":
        from app.mri_dashboard.session_store import load_cookies
        for c in load_cookies("Mercado Libre"):
            cookies[c["name"]] = c["value"]
    if cookies:
        return cookies
    # fallback opcional a Chrome/CDP si no hay cookies guardadas
```

El header HTTP se construye con:

```python
headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
```

- `USE_SAVED_COOKIES=1` (default): usa las 35 cookies del store.
- `USE_CHROME_COOKIES=true`: solo actúa si no hay cookies guardadas.
- No abre Chrome, no usa CDP, no toca archivos bloqueados.

## 3. Validación

```text
cookies inyectadas = 35
GET https://www.mercadolibre.cl/tienda/nicopoly → 200
productos           = 39
stop_reason         = EXHAUSTION
```

Pruebas adicionales:

| Intento | Resultado |
|---|---|
| Storefront con 35 cookies | **39 productos** |
| Storefront con 189 cookies de `storage_*.json` (incluye `ssid`) | **39 productos** |
| `?page=2` / `?_Desde_=49` | ignorados, mismos 39 |
| `listado.mercadolibre.cl` con cookies | 200 pero página de verificación, 0 productos |
| `api.mercadolibre.com/sites/MLC/search` | **403** sin token |

**ML no supera 39.** Las cookies no cambian el HTML SSR del storefront ni habilitan la paginación;
el listado requiere verificación interactiva y la API requiere autenticación de API (token), no
cookies de navegador.

## 4. Conclusión

| Objetivo | Estado |
|---|---|
| Usar cookies guardadas de MRI | **IMPLEMENTADO** |
| 35 cookies inyectadas | **SÍ** |
| ML >39 | **NO** (39) |
| Criterio de cierre | **NO cumplido** |

Para superar 39 hace falta una de estas vías:
1. **Token/API oficial de Mercado Libre** (`api.mercadolibre.com`), no cookies de navegador.
2. Un endpoint interno autenticado del storefront que acepte las cookies y exponga paginación.
3. Playwright como fallback explícito (contradice el modo HTTP-only actual).

El código de inyección queda listo; el bloqueo es del endpoint de ML, no del motor HTTP.

## 5. Estado

```text
COOKIE_SOURCE=_integration/data/sessions/mercado_libre_cookies.json
COOKIES=35
ML_PRODUCTS=39
BROWSER_USED=0
CDP_USED=0
ADMIN_REQUIRED=NO
```
