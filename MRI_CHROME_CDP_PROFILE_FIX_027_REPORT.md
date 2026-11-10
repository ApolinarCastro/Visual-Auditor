# MRI_CHROME_CDP_PROFILE_FIX_027_REPORT

**Tarea:** MRI-CHROME-CDP-PROFILE-FIX-027 · **Fecha:** 2026-11-10
**Commit:** `TBD`
**Resultado:** launcher corregido con perfil dedicado `%LOCALAPPDATA%\MRI_Chrome_Profile`;
**no se pudo validar el puerto 9222 desde este proceso**: Chrome se cierra al lanzarse desde el
entorno DSH. Cookies 0; ML sigue en 39.

---

## 1. Cambio aplicado

`POST /api/mri/chrome/open-debug` ahora:

```python
profile = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()),
                       "MRI_Chrome_Profile")
os.makedirs(profile, exist_ok=True)
subprocess.Popen([
    exe,
    "--remote-debugging-port=9222",
    f"--user-data-dir={profile}",          # perfil dedicado, no el personal
    "--remote-allow-origins=*",
    "--no-first-run",
    "--no-default-browser-check",
    "--new-window",
    "https://www.mercadolibre.cl",
])
```

- Perfil **persistente** en `C:\Users\ASUS Zenbook\AppData\Local\MRI_Chrome_Profile`.
- Separado del perfil personal.
- `--remote-allow-origins=*` añadido para el handshake WebSocket CDP.
- Se mantiene el botón **ABRIR CHROME PARA ML** y el endpoint `POST /api/mri/chrome/open-debug`.

## 2. Intento de validación

Comando equivalente ejecutado desde Python:

```text
chrome.exe --remote-debugging-port=9222
  --user-data-dir=C:\Users\ASUS Zenbook\AppData\Local\MRI_Chrome_Profile
  --remote-allow-origins=* --no-first-run --no-default-browser-check
  --new-window https://www.mercadolibre.cl
```

Resultado:

```text
proceso Chrome: se cierra
GET http://127.0.0.1:9222/json/version: conexión rechazada / timeout
CDP_FAIL
```

No fue un problema de perfil por defecto: el perfil dedicado se creó y se pasó correctamente.
Chrome **no mantiene el proceso** cuando se lanza desde el proceso DSH (contexto sin sesión de
escritorio interactiva); no hay puerto 9222 que consultar.

### Cookies / ML

```text
get_meli_cookie_status() → NO_COOKIES · count=0
ML → 39 productos
```

No se pudo validar `>39` ni `source=cdp`.

## 3. Qué falta para cerrar

1. Abrir el dashboard en la sesión de escritorio del usuario.
2. Pulsar **ABRIR CHROME PARA ML** (debe devolver `status=OPEN`, `port=9222`).
3. Iniciar sesión manualmente en ML en esa ventana.
4. Pulsar **IMPORTAR COOKIES DESDE CHROME** → debe devolver `count>0`, `source=cdp`.
5. Ejecutar ML con `USE_CHROME_COOKIES=true` y verificar >39.

El código ya está preparado para esos pasos; el bloqueo actual es de entorno de ejecución, no de
lógica CDP.

## 4. Conclusión

| Objetivo | Estado |
|---|---|
| Perfil dedicado no-default | **IMPLEMENTADO** |
| `--remote-debugging-port=9222` | **IMPLEMENTADO** |
| `GET /json/version` 200 | **NO en este entorno** |
| Cookies `.mercadolibre.cl` | **0** |
| ML >39 | **NO** |
| Criterio de cierre | **NO cumplido** (bloqueo de sesión de escritorio) |

Estado:

```text
PROFILE=%LOCALAPPDATA%\MRI_Chrome_Profile
CDP_PORT=9222 (no responde desde DSH)
COOKIES=0
ML_PRODUCTS=39
ADMIN_REQUIRED=NO
DASHBOARD=STOPPED
```
