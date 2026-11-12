# MRI — límites del entorno del agente y verificación transparente

## Lo que el agente puede hacer

- Editar y probar código.
- Ejecutar suites de pruebas.
- Inspeccionar SQLite, logs y archivos de estado.
- Calcular y publicar build-id.
- Verificar endpoints HTTP de MRI cuando el servidor está levantado por el operador.
- Leer el marcador de apertura de Chrome generado por el launcher.

## Lo que el agente no puede hacer desde este contexto

| Límite | Efecto | Alternativa |
|---|---|---|
| No puede mantener vivo un servidor después de su sesión | Uvicorn muere al terminar la herramienta | El operador lanza el `.bat` en su consola |
| No puede ver ni controlar la UI del navegador | No confirma clics/ventanas | Marcador `mri_browser_launch.json` |
| WMI/Win32_Process devuelve acceso denegado | No puede inspeccionar command-line de Chrome | No usar WMI; usar marcador y logs |
| No puede resolver CAPTCHA/WAF | Ripley puede bloquear | Sesión propia, pausa humana, `SOURCE_BLOCKED` |
| No puede certificar un flujo end-to-end sin el operador | Los tests son unitarios/fixtures | Prueba de arranque + auditoría supervisada |
| No puede garantizar el estado de una instancia vieja | Puede escuchar un proceso anterior | Lock de instancia + `/api/version` + aborto por puerto |

## Verificación de build

Al iniciar:

```text
build : <commit>[-dirty] (<branch>)
```

Endpoints:

```text
GET /api/version
GET /api/state  → campo build
```

Si el build mostrado no coincide con el commit esperado, el operador debe detener el proceso y relanzar.

## Instancia única

`InstanceLock`:

- usa `data/runtime_tmp/mri_instance_<port>.lock`;
- rechaza una segunda instancia viva con `INSTANCE_ALREADY_RUNNING`;
- rechaza `PORT_IN_USE`;
- limpia locks de PID muerto;
- se libera en `atexit`.

## Limpieza de estado derivado

Comando explícito:

```powershell
python scripts/reset_discovery_state.py --apply
```

Hace:

```text
backup en data/backups/discovery_state_<timestamp>/
sha256 por archivo
manifest.json
elimina SOLO categorías/grafo/memoria de descubrimiento
NO toca mri_runs, publicaciones, sesiones ni DB operativa
```

Sin `--apply` es dry-run.

En el launcher:

```text
set MRI_BAT_RESET_DISCOVERY=1
```

activa la limpieza antes de iniciar el servidor.

## Documento principal del incidente

Ver [MRI_INCIDENT_AND_PRODUCTION_READINESS_2026_10_30.md](MRI_INCIDENT_AND_PRODUCTION_READINESS_2026_10_30.md)
para cronología, evidencia, riesgos de datos y plan de producción.

## Marcador de Chrome

`open_mri_dashboard.ps1` escribe:

```text
_integration/data/runtime_tmp/mri_browser_launch.json
```

con:

```json
{
  "opened_at": "...",
  "browser": "...chrome.exe",
  "url": "http://127.0.0.1:8055/",
  "pid": 1234
}
```

Eso permite verificar la apertura sin WMI ni permisos elevados.
