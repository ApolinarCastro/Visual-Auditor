# Correcciones MRI — 29-10-2026

Documento de cierre de las correcciones aplicadas durante la operación del 28–29 de octubre de 2026.

## Alcance

Correcciones sobre MRI y dos correcciones seguras del VA. No se subieron sesiones, cookies, perfiles de navegador, bases SQLite, logs, checkpoints ni evidencia local de ejecución.

## MRI — descubrimiento y taxonomía

- Reemplazo del alcance fijo de 12 categorías por un `DiscoveryKernel` genérico por marca.
- Modelo `DiscoveryTarget(marketplace, brand, store_url)`.
- Estrategias: storefront SSR, enlaces de menú, API pública de categorías y rutas aprendidas.
- Grafo persistente de rutas en `knowledge/discovery_graph.json`.
- Caché de rutas aprendidas para evitar redescubrimiento; TTL y revalidación.
- Sin URLs de VA hardcodeadas.
- `Abrigos` se trata como padre comercial de `Chaquetas, Parkas y Blazers` y `Chalecos, Sweaters y Cardigans`.
- Rollup de resultados y únicas para `Abrigos`.
- `Ropa Interior y de Dormir` se reporta como `Body`.
- `Accesorios de Moda` incorporado como superficie aprendida, con fallback público de Bufandas y Pañuelos.

## MRI — adquisición

- Paginación ALL_PARALLEL con un runner hijo aislado por marketplace.
- Corrección del dispatch de `_guarded_run`: acepta `**kwargs` y reenvía `run_id`.
- Recuperación de página faltante cuando el total declarado supera lo extraído (`meli_pagination`).
- Deduplicación de SKU entre categorías, preservando duplicados intra-categoría para trazabilidad.
- `NO_PROGRESS` cuando una categoría no aporta SKU nuevos.
- G3 corregido: compara posiciones declaradas contra posiciones observadas; los SKU únicos son diagnóstico separado.
- Parseo de `1 resultado` singular y plural.
- Captura de total declarado por categoría.
- Observaciones históricas y únicas separadas en la API de categorías.
- Categorías de API solo se expanden cuando faltan respecto de la memoria y hay evidencia de tienda.

## MRI — sesión

- Canonicalización de marketplace para cookies: `mercadolibre`, `mercado_libre`, `meli` → `Mercado Libre`.
- Aceptación de `.mercadolibre.cl`, `.articulo.mercadolibre.cl` y `.mercadolibre.com`.
- Diagnóstico de dominios rechazados sin exponer valores de cookies.

## MRI — salud, censo y dashboard

- Telemetría por categoría: duración, páginas, observadas, nuevas, duplicadas, estado.
- `source_health` derivado de la corrida real.
- Censo global y cobertura con observaciones, únicas y total declarado conocido.
- Endpoint `GET /api/mri/health`.
- Panel de categorías con columnas `Resultados` y `Únicas`.
- Corregido el endpoint `/api/categories` que devolvía publicaciones en cero.
- Rollup comercial y alias `Body` en el endpoint.

## VA — correcciones seguras

- `source_health` se actualiza en cada categoría normal exitosa; antes solo las reauditorías selectivas lo hacían.
- `MultivendeLoader` emite el warning de archivo faltante una sola vez por proceso.

## Pruebas

- Suite MRI: 165 tests PASS en la última ejecución completa.
- Regresión adicional `test_guarded_run_forwards_kwargs_and_runner_run_id`: PASS.
- Compilación VA: `py_compile` OK.
- La suite del VA no se pudo certificar en este entorno por `sqlite3.OperationalError: unable to open database file` en el sandbox temporal; no es una regresión de los parches.

## Pendientes

- Segunda pasada automática para categorías `PARTIAL` o vacías.
- Persistencia histórica de salud/censo.
- Snapshot/diff completo por corrida.
- Descubrimiento autónomo de facetas desde la página pública de categorías y filtro de marca.
- Alertas con guarda de completitud.

## Restricciones respetadas

- No se modificaron perfiles, sesiones ni cookies.
- No se detuvo ni reinició el VA desde el agente.
- No se hizo push hasta contar con autorización explícita.


## Sesión y desafíos (ampliación)

- Calentamiento de homepage antes de recorrer categorías.
- Detección explícita de challenge: Turnstile, Cloudflare, “verify you are human”, login y bloqueos.
- Recuperación controlada: stop/start del navegador, reinyección de cookies y warmup.
- Telemetría `session_recoveries` y errores de recuperación.
- Reintento único de la categoría solo si la recuperación fue exitosa.
- Sin resolución de CAPTCHA, sin perfil ajeno y sin bucles infinitos.

Pruebas: `test_session_supervisor.py` y `test_guarded_dispatch.py`.

Suite MRI total actualizada: 168 tests PASS.


## Dashboard ALL en vivo

- El coordinador ALL sincroniza cada 2 segundos resultados, taxonomía y estado de los hijos.
- El tablero muestra hallazgos parciales mientras los cuatro marketplaces siguen.
- `marketplace_states` informa EN_CURSO / FOUND / PARTIAL / FAILED por marketplace.
- El resultado final agrega los cuatro hijos y decide FOUND/PARTIAL/STOPPED.
- Los hijos siguen materializando de forma aislada; no se duplica persistencia.


## Ripley-only

- La taxonomía de Ripley ahora también pasa por detección de challenge.
- Si el challenge bloquea la primera página, MRI recupera sesión con stop/start,
  reinyecta cookies, calienta homepage y reintenta la taxonomía una sola vez.
- El perfil Ripley es propio (`_integration/data/ripley_profile`); no se copia el perfil del VA.
- El bloqueo de perfil huérfano se limpia con `ProfileLock` cuando el PID ya no está vivo.
- Aplica solo a `marketplace=Ripley`; no altera ALL_PARALLEL ni los scrapers congelados.
