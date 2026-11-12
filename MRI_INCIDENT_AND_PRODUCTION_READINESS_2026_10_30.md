# MRI — Incidente, estado actual y producción

**Fecha:** 2026-10-30  
**Rama:** `integration/mri-deepseek-closure`  
**Último commit documentado:** `60a9e33`  
**Documento:** handover operativo y de producción  
**Regla:** este documento no declara PASS de producción. Separa hechos demostrados, riesgos y pendientes.

---

## 1. Resumen ejecutivo

MRI tiene piezas funcionales y pruebas unitarias, pero **no está listo para producción** porque la corrida real de Ripley puede seguir ejecutando el flujo anterior de categorías, navegando URLs de Mercado Libre bajo el scraper de Ripley.

Hechos confirmados:

1. El servidor MRI inicia y responde `/api/version`.
2. El navegador Chrome ya se abre automáticamente y rápido tras corregir el manejo del `401`.
3. Existe un `build-id` verificable.
4. Existe un lock de instancia única.
5. Existe una limpieza de estado derivado con backup y manifiesto.
6. **La corrida Ripley observada siguió navegando URLs de `listado.mercadolibre.cl` con el scraper `[Ripley]`.**
7. **El estado de esa corrida no publicó `taxonomy` ni `resolution_strategies`.**
8. Por tanto, el `CategoryResolver` nuevo no está gobernando esa ejecución real, aunque el build cargado sea reciente.
9. El VA está separado y no debe tocarse.

Conclusión operativa:

```text
MRI no debe usarse para decisiones de Ripley con las corridas contaminadas.
La causa inmediata es de runtime/selección de flujo, no de falta de scraper.
Producir requiere un supervisor persistente y una prueba end-to-end real.
```

---

## 2. Estado observado al documentar

### 2.1 Servicios

```text
Puerto 8055 (MRI): sin proceso escuchando al momento de este documento
Puerto 8000 (VA):  sin escucha verificable en la consulta
Procesos Python vivos:
  PID 24676  inicio 08:46
  PID 27940  inicio 08:46
```

Los procesos Python vivos no fueron detenidos porque pertenecen/están asociados al VA y el operador pidió preservarlo.

### 2.2 Última corrida MRI observada

```text
run_id: run_mri_discovery_1793366446
marketplace: Ripley
mode: DISCOVERY
stage: adquiriendo
results: 0
build: 60a9e3332958-dirty
```

### 2.3 Evidencia de contaminación

Navegaciones atribuidas al scraper `[Ripley]`:

```text
https://listado.mercadolibre.cl/tienda/nicopoly/listado/vestuario-calzado/abrigos/
https://listado.mercadolibre.cl/tienda/nicopoly/listado/vestuario-calzado/blusas/
https://listado.mercadolibre.cl/tienda/nicopoly/listado/vestuario-calzado/pantalones/
https://listado.mercadolibre.cl/vestuario-calzado/faldas/
https://listado.mercadolibre.cl/vestuario-calzado/vestidos/
```

Conteo de la ventana revisada:

```text
Navegaciones [Ripley]: 71
Navegaciones [Mercado Libre]: 0
Navegaciones [Paris]: 0
```

Interpretación: no era otro scraper de ML ejecutándose; era **Ripley usando categorías de ML**.

### 2.4 Evidencia de que el resolver no se activó

```text
taxonomy: []
discovery_recovery: []
resolution_strategies: ausente
```

La corrida sí usó rutas válidas de Ripley en otros momentos, pero también rutas de ML. Esa inconsistencia demuestra que la selección de categorías provino de una caché/legacy path, no de una resolución única.

---

## 3. Cronología resumida del incidente

| Momento | Hecho | Resultado |
|---|---|---|
| Sesiones previas | Se lanzaron corridas Ripley/ALL | Resultados parciales, dashboard con problemas de agregación |
| 2026-10-29 | Se detectó scraper Ripley navegando ML | Se agregó guard de host |
| 2026-10-29 | Se removieron candidatos fijos de Ripley y fallback persistido | Se exigió taxonomía live |
| 2026-10-29 | Se agregó recuperación con rutas Creao | Se creó `discovery_intelligence` |
| 2026-10-30 | Se unificó resolución en `CategoryResolver` | Suite focalizada pasó |
| 2026-10-30 | Se agregaron build-id, lock y limpieza | Suite focalizada 175 PASS |
| 2026-10-30 | Falló el lock por `_bi` no definido | Corregido en `fd37ca8` |
| 2026-10-30 | Chrome se abría a los 90 s | El helper trataba 401 como fallo; corregido en `60a9e33` |
| 2026-10-30 | Ripley volvió a navegar ML | Blocker de producción actual |

---

## 4. Qué está implementado y probado

### 4.1 Build verificable

Archivo: `_integration/app/mri_dashboard/build_info.py`

```text
GET /api/version
GET /api/state → campo build
```

El build se deriva de commit + estado dirty + PID.

### 4.2 Instancia única

Archivo: `_integration/app/mri_dashboard/instance_lock.py`

```text
data/runtime_tmp/mri_instance_<port>.lock
INSTANCE_ALREADY_RUNNING
PORT_IN_USE
limpieza de PID muerto
release en atexit
```

### 4.3 Limpieza transparente de estado

Archivo: `_integration/scripts/reset_discovery_state.py`

```text
dry-run por defecto
--apply crea backup + sha256 + manifest.json
elimina solo categorías/grafo/memoria de descubrimiento
no toca auditorías, publicaciones, sesiones ni DB operativa
```

Launcher:

```text
set MRI_BAT_RESET_DISCOVERY=1
```

### 4.4 Apertura de Chrome

Archivos:

```text
_integration/open_mri_dashboard.ps1
_integration/lanzar_mri_dashboard.bat
```

Comportamiento:

```text
servidor en primer plano
espera HTTP real
acepta 401/403 como servidor listo
abre Chrome explícitamente con --new-window
escribe data/runtime_tmp/mri_browser_launch.json
```

### 4.5 Resolución de categorías

Archivos:

```text
_integration/app/mri_dashboard/category_resolution.py
_integration/app/mri_dashboard/discovery_intelligence.py
_integration/app/mri_dashboard/marketplace_scope.py
```

Estrategias declaradas:

```text
LIVE_DISCOVERY
SESSION_RECOVERY_LIVE_RETRY
LEARNED_PRIOR_ROUTES
LEGACY_CATEGORY_CACHE (solo Paris/Falabella)
```

**No demostrado en la corrida real de Ripley:** el runtime observado no publicó estas estrategias.

---

## 5. Pruebas y evidencia de calidad

### 5.1 Suite focalizada MRI

Ejecutada antes de los últimos fixes de launcher:

```text
175 passed
```

Incluye:

```text
category_resolution
discovery_intelligence
marketplace_scope
instance_lock
reset_discovery_state
session_supervisor
runtime_recovery
acquisition_truth
historical_reference_decoupling
```

### 5.2 Suite amplia

Ejecución posterior de `pytest tests`:

```text
438 passed
51 failed
52 errors
1 skipped
```

Errores observados de infraestructura:

```text
PermissionError: Acceso denegado sobre directorios temporales de pytest
```

No se debe declarar la suite amplia en verde. Los fallos deben separarse entre:

```text
fixtures/entorno
pruebas legacy que requieren DB/rutas externas
regresiones reales
```

### 5.3 Pruebas que faltan

```text
E2E real: servidor + Chrome + Ripley real + categorías + host guard + resultados
Proceso nuevo desde cero + verificación de /api/version
Prueba de segunda instancia rechazada
Prueba de contaminación cero (ninguna URL de ML bajo Ripley)
Prueba de Ctrl+C y cierre de Chrome
```

---

## 6. Blocker actual y causa raíz

### Confirmado

```text
1. El build nuevo se carga.
2. El servidor responde.
3. El navegador se abre.
4. La corrida Ripley navega URLs de ML.
5. El estado no publica taxonomía/recovery.
```

### Hipótesis de causa

El proceso real está entrando por una ruta heredada que usa `category_manager` persistido, no por el `CategoryResolver`. Esto puede ocurrir por:

```text
- una rama de dispatch distinta de la esperada;
- full_audit/límite con valores no previstos;
- un módulo cacheado por un proceso anterior;
- una ruta legacy dentro de run_discovery/run_audit.
```

No está probado todavía cuál de esas condiciones ocurre. No se debe “arreglar” adivinando.

### Evidencia que falta para cerrar la causa

Agregar y consultar en `/api/state`:

```text
full_audit
effective_category_source
resolver_strategies
loaded_module_paths
build_id
```

y comparar con el commit esperado.

---

## 7. Datos en riesgo

No usar para decisiones de Ripley las corridas con navegación de ML bajo Ripley. Revisar/aislar al menos:

```text
run_mri_discovery_1793304187
run_mri_discovery_1793363629
run_mri_discovery_1793364991
run_mri_discovery_1793365234
run_mri_discovery_1793366446
```

La lista no implica que todas estén completamente contaminadas; deben auditarse por `requested_url` y `observed_url`.

No borrar evidencia ni DB sin backup. La limpieza implementada solo elimina estado derivado de descubrimiento.

---

## 8. Limitaciones del entorno del agente

| Limitación | Efecto | Mitigación |
|---|---|---|
| El servidor lanzado por el agente muere al terminar su sesión | No puede supervisar entre turnos | Tarea programada/servicio iniciado por el operador |
| No puede ver ni controlar Chrome/UI | No completa Basic Auth ni observa ventanas | Marcador de Chrome + operador autentica |
| WMI/Win32_Process denegado | No distingue Chrome MRI vs VA | Marcador con PID; no matar Chrome a ciegas |
| No puede resolver CAPTCHA/WAF | Ripley puede bloquear | Sesión propia y pausa humana |
| No puede operar escritorio | No controla clics finales | Automatización de API/servidor |
| No puede certificar E2E sin operador | Tests no equivalen a producción | Prueba de aceptación conjunta |

Estas limitaciones **no se resuelven con más parches de código**.

---

## 9. Qué se necesita para poner MRI en producción

### 9.1 Decisión del operador

Autorizar una de estas dos formas de ejecución persistente:

**A. Tarea programada de Windows “MRI-Autopilot”**

```text
- corre en la sesión del usuario;
- sobrevive a los turnos del agente;
- inicia un único servidor;
- permite start/stop por API;
- no toca el VA.
```

**B. Servicio de Windows**

```text
- requiere permisos de administrador;
- más robusto;
- necesita política de sesión interactiva para Chrome.
```

Sin una de estas, el agente solo puede controlar mientras el servidor esté vivo, y no puede garantizar continuidad.

### 9.2 Diagnóstico de runtime

Antes de otra auditoría:

```text
1. /api/version coincide con el commit esperado.
2. /api/state expone full_audit y fuente efectiva de categorías.
3. Una sola instancia.
4. Logs sin URLs de host distinto.
```

### 9.3 Prueba end-to-end de Ripley

```text
1. limpiar estado con backup;
2. iniciar servidor limpio;
3. verificar build;
4. lanzar Ripley-only;
5. comprobar taxonomy/resolución;
6. comprobar que ninguna URL sea de ML;
7. verificar resultados y sesión;
8. detener y comprobar limpieza de Chrome.
```

### 9.4 Sesión Ripley

Definir explícitamente:

```text
- perfil persistente propio;
- warmup;
- detección de challenge;
- recuperación/renovación de sesión;
- pausa humana cuando corresponda;
- nunca resolver CAPTCHA automáticamente.
```

### 9.5 Observabilidad y alertas

```text
- build_id en cada run;
- host esperado vs host navegado;
- categorías descubiertas/adquiridas;
- source_health;
- alerta si Ripley navega a ML;
- alerta si taxonomy queda vacía en full audit;
- retención de logs y evidencia.
```

### 9.6 Seguridad

```text
- credenciales solo en .env, nunca en URL ni logs;
- HTTP Basic en loopback;
- no exponer 8055 a red;
- backups de DB protegidos;
- no commitear sesiones/cookies/DB;
- limpieza de estado solo con backup y confirmación.
```

### 9.7 Rollback

```text
- tag/commit estable anterior;
- backup de DB antes de migraciones;
- backup de discovery antes de limpieza;
- restauración documentada;
- ningún borrado destructivo sin manifiesto.
```

---

## 10. Plan de producción propuesto

### Fase 0 — Contención
- No ejecutar Ripley con el runtime actual.
- Preservar VA.
- No usar datos contaminados.
- Cerrar procesos MRI antiguos.

### Fase 1 — Diagnóstico y corrección del dispatch
- Instrumentar `full_audit`, fuente de categorías y módulo cargado.
- Reproducir con Ripley-only.
- Corregir la ruta real, no agregar otro fallback.
- Añadir test de regresión que falle si Ripley navega a ML.

### Fase 2 — Supervisor persistente
- Implementar tarea programada/servicio.
- Verificar build y lock antes de auditar.
- Iniciar/detener por API.
- Logs y marcadores verificables.

### Fase 3 — Piloto Ripley
- Ejecutar una sola corrida supervisada.
- Validar G3/cobertura/taxonomía.
- Revisar evidencia manual contra VA.
- No ampliar a otros marketplaces hasta pasar.

### Fase 4 — Multimarketplace
- Repetir aceptación por ML, Paris y Falabella.
- Mantener aislamiento de perfiles y hosts.
- Criterios de rollback por marketplace.

### Fase 5 — Producción
- Backup programado.
- Monitoreo y alertas.
- Runbook de incidentes.
- Revisión de seguridad.
- Aprobación formal del operador.

---

## 11. Criterios de aceptación para declarar producción

```text
[ ] build_id visible y coincide con el commit desplegado
[ ] una sola instancia, segunda rechazada
[ ] /api/state expone runtime y resolución
[ ] Ripley-only sin ninguna URL de ML
[ ] taxonomy/live o learned prior con provenance
[ ] adquisición completa o PARTIAL justificado
[ ] resultados conciliados contra evidencia
[ ] Ctrl+C detiene servidor y Chrome
[ ] backup/restauración probados
[ ] monitoreo y alertas activos
[ ] aprobación del operador
```

Ningún punto puede marcarse por inferencia: requiere evidencia de ejecución.

---

## 12. Comandos operativos

### Verificar build
```powershell
curl -u admin:<clave> http://127.0.0.1:8055/api/version
```

### Limpieza (dry-run)
```powershell
python _integration/scripts/reset_discovery_state.py
```

### Limpieza con backup
```powershell
python _integration/scripts/reset_discovery_state.py --apply
```

### Suite focalizada
```powershell
cd _integration
..\visibility_auditor_env\Scripts\python.exe -m pytest tests/test_category_resolution.py tests/test_discovery_intelligence.py tests/test_marketplace_scope.py tests/test_build_instance_cleanup.py -q
```

### Verificar puerto
```powershell
netstat -ano | findstr :8055
```

---

## 13. Decisión requerida

Para continuar se necesita autorización explícita de **una** opción:

```text
A. Crear y controlar la tarea programada MRI-Autopilot.
B. Habilitar un servicio persistente.
C. Mantener una consola interactiva donde el agente pueda operar por API.
```

Sin eso, el agente puede corregir código y documentar, pero **no puede controlar el proceso completo de forma continua**.

---

## 14. Referencias

- `_integration/MRI_ENVIRONMENT_LIMITATIONS.md`
- `_integration/MRI_CORRECTIONS_2026_10_29.md`
- `_integration/app/mri_dashboard/build_info.py`
- `_integration/app/mri_dashboard/instance_lock.py`
- `_integration/app/mri_dashboard/category_resolution.py`
- `_integration/scripts/reset_discovery_state.py`
- `_integration/open_mri_dashboard.ps1`
- `_integration/lanzar_mri_dashboard.bat`
