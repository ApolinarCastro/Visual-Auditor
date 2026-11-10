# MRI_FIX_DASHBOARD_AND_COOKIES_025_REPORT

**Tarea:** MRI-FIX-DASHBOARD-AND-AUTOMATE-COOKIES-025 · **Fecha:** 2026-11-10
**Resultado:** persistencia padre/checkpoints/evidencia **corregida y validada**; extractor de cookies
y botón **implementados**, pero Chrome no entregó cookies (0) por bloqueo de su base.

---

## 1. Persistencia del run padre (corregido)

`mri_runner.run_parallel_discovery` ahora, al cerrar el `gather`:

1. Persiste una fila **padre** en `mri_runs` con
   `marketplace=MULTI_MARKETPLACE`, `terminal_state=PARTIAL/FOUND`, `status=SUCCESS`.
2. Añade una entrada **padre** en `mri_history.json` con:
   - `child_run_ids` de los 4 marketplaces
   - `marketplace_states`
   - `total`, `outcome`, `execution_strategy`, `source_method`.
3. Escribe **coverage checkpoint** `HTTP_HUB_LIMITED` para Paris/Ripley/ML.
   Falabella conserva su checkpoint SSR completo (se excluye explícitamente para no sobrescribirlo).
4. Inserta filas en `mri_evidence_ledger` por cada child HTTP con resultados.

### Validación real

Run `run_mri_discovery_1794320207`:

```json
{
  "parent": ["run_mri_discovery_1794320207",
             "MULTI_MARKETPLACE", "PARTIAL", "SUCCESS"],
  "children": [
    ["__paris", "Paris", "FOUND"],
    ["__mercado_libre", "Mercado Libre", "FOUND"],
    ["__ripley", "Ripley", "FOUND"],
    ["__falabella", "Falabella", "PARTIAL"]
  ],
  "history_parent": "presente",
  "evidence_rows": 4,
  "http_checkpoints": 4,
  "checkpoint_scope": "HTTP_HUB_LIMITED",
  "checkpoint_acceptance": "AUDIT_PASS"
}
```

Resultados: **1 102 publicaciones**, memoria libre mínima **681 MB**, `integrity=ok`,
`database is locked=0`.

> Nota: en esa validación Falabella también recibió checkpoint HTTP_HUB por el primer fix; se
> corrigió después (`skip Falabella`) para que la próxima corrida conserve el checkpoint SSR
> completo.

## 2. Extractor automático de cookies

### `cookie_extractor.py`

- Usa `browser_cookie3` (instalado: `browser_cookie3 0.20.1`).
- Configura un `TEMP` escribible para pywin32/gencache.
- Recorre perfiles Chrome (`Default`, `Profile 1/6/7`) y copia `Network/Cookies` a un temporal.
- Si Chrome mantiene el archivo bloqueado, intenta la copia y luego el archivo original; nunca
  inventa cookies.
- Devuelve `{}` cuando no puede leer.

### `meli_http_engine.py`

Con `USE_CHROME_COOKIES=true`:

```python
cookies = get_meli_cookies()
headers["Cookie"] = "; ".join(f"{k}={v}" ...)
```

Si no hay cookies, conserva el camino actual (39 productos).

### Dashboard

- Endpoint: `POST /api/mri/cookies/import`.
- Botón: **“IMPORTAR COOKIES DESDE CHROME”**.
- Respuesta real probada:

```json
{"marketplace":"mercadolibre","status":"NO_COOKIES","count":0,
 "cookies":[],"source":"chrome_profile"}
```

## 3. Resultado de cookies / ML

**Chrome estaba abierto** y su base `Network/Cookies` no fue legible:
`browser_cookie3` cae a shadowcopy y Windows devuelve `RequiresAdminError`; la copia directa
falla por bloqueo exclusivo.

- **Cookies importadas: 0.**
- **ML sigue en 39 productos**, no se pudo demostrar >39 con cookies.
- El botón y el endpoint funcionan, pero el criterio “ML supera 39” **NO se cumple** en esta
  ejecución.

Para completar la validación: cerrar Chrome, pulsar “Importar cookies desde Chrome” y repetir el
ALL; o ejecutar el extractor con permisos de administrador (shadowcopy).

## 4. Dashboard / run padre

El dashboard ya recibe:

```text
mri_runs:      fila padre MULTI_MARKETPLACE
mri_history:   entrada padre con child_run_ids y estados
checkpoints:   HTTP_HUB_LIMITED (Paris/Ripley/ML), Falabella SSR
evidence:      4 filas HTTP
```

La ejecución manual anterior (`1794318185`) ya no debería verse como “incompleta”: ahora produce
una fila padre consolidada y checkpoints por marketplace.

## 5. Conclusión

| Objetivo | Estado |
|---|---|
| Persistencia run padre | **CORREGIDA** |
| Checkpoints HTTP visibles | **CORREGIDOS** (scope limitado) |
| Evidencia ledger HTTP | **AÑADIDA** |
| Extractor de cookies | **IMPLEMENTADO** |
| Botón dashboard | **IMPLEMENTADO** |
| Cookies leídas de Chrome | **NO** (Chrome abierto / 0 cookies) |
| ML >39 | **NO validado** (sigue 39) |

Código listo para commit; la única brecha restante es la lectura de cookies con Chrome abierto,
que requiere cerrar Chrome o permisos elevados.

## 6. Estado

```text
PARENT_PERSISTENCE=PASS
HTTP_CHECKPOINTS=PASS (HTTP_HUB_LIMITED)
EVIDENCE_LEDGER=4
COOKIE_EXTRACTOR=IMPLEMENTED
COOKIE_IMPORT=NO_COOKIES (0)
ML_PRODUCTS=39
DASHBOARD=STOPPED
PORT_8055=FREE
```
