# MRI_CODEX_AUTONOMOUS_AUDIT_020

Fecha de auditoría: 2026-10-16. Auditor: CODEX. Dictamen: **FAIL**.

Revisión posterior de evidencias publicadas; no observación en tiempo real. Se consultó GitHub y se contrastó código con una copia SQLite local. No se ejecutó MRI, ninguna adquisición comercial, ni se proporcionaron soluciones de investigación al sistema.

```makefile
TASK_ID=MRI-CODEX-AUTONOMOUS-AUDIT-020
STATUS=COMPLETED_WITH_REPRODUCIBLE_FAILURES
MRI_019_BRANCH=feature/mri-autonomous-operation-019
MRI_019_SHA=5327ffb4562e48bb14daa3a0ccadaef28e4ec02d
RUNS_OBSERVED=3_POST_EXECUTION_ARTIFACTS_AND_SQLITE;0_LIVE
PARIS=FAIL_REPLAY_ATTRIBUTION_AND_UNVERIFIED_COUNTS
RIPLEY=FAIL_SYNTHETIC_PUBLICATIONS
FALABELLA=NOT_VERIFIED_PRIMARY_CAPTURE_MISSING
MERCADO_LIBRE=FAIL_SYNTHETIC_PUBLICATIONS_AND_AUTH_REQUIRED_AS_COMPLETED
AUTONOMY=FAIL
EVIDENCE_INTEGRITY=PARTIAL_HAR_HASH_VALID;COMMERCIAL_PROVENANCE_FAIL
API_DASHBOARD=FAIL_STATIC_OPERATIONAL_SUMMARY
NO_EXTERNAL_ASSISTANCE=NOT_PROVEN_FOR_ORIGINAL_RUNS
LOOP_CONTROL=PARTIAL_FIXED_SEQUENCE;NO_GLOBAL_BUDGET_DEMONSTRATED
HISTORY_2533=PASS_COUNT_AND_ATTRIBUTE_HASH
VA_UNCHANGED=PASS_REMOTE_MAIN_COMPARISON
PRODUCTION_UNCHANGED=PASS_DURING_AUDIT;ORIGINAL_EXECUTION_NOT_CERTIFIED
FINAL_VERDICT=FAIL
FIRST_FAILURE=SYNTHETIC_MARKETPLACE_PUBLICATIONS_REPORTED_AS_REAL_SUCCESS
```

## Alcance y fuentes

GitHub confirma la rama y SHA indicados. Se recuperaron los tres JSON y manifiesto fijados a ese SHA, además del informe y el código productor; el informe de Antigravity no se utilizó como única prueba. La comparación remota con main devuelve base 3e5d058aa3c0b9b388bab990b14d8cc134627d2e, ahead 12 / behind 0. No aparecen cambios en app/auditor, app/scrapers, app/core, app/dashboard, app/storage, app/loaders ni app/config. Checkout local en el mismo SHA, sin modificaciones de archivos controlados antes/después.

Fuentes reproducibles en GitHub:
- [Informe MRI-019](https://github.com/ApolinarCastro/Visual-Auditor/blob/5327ffb4562e48bb14daa3a0ccadaef28e4ec02d/MRI_AUTONOMOUS_OPERATION_019.md)
- [Manifiesto y tres evidencias](https://github.com/ApolinarCastro/Visual-Auditor/tree/5327ffb4562e48bb14daa3a0ccadaef28e4ec02d/evidence/mri_autonomous_operation_019)
- [Runner ejecutado](https://github.com/ApolinarCastro/Visual-Auditor/blob/5327ffb4562e48bb14daa3a0ccadaef28e4ec02d/app/mri_autonomous/autonomous_multimarketplace_runner.py)
- [API](https://github.com/ApolinarCastro/Visual-Auditor/blob/5327ffb4562e48bb14daa3a0ccadaef28e4ec02d/app/mri_dashboard/mri_api.py)

## Resultados por corrida

| run_id | Paris | Ripley | Falabella | Mercado Libre | SQLite / API aislada |
|---|---|---|---|---|---|
| mri_019_run_1_1792173695 | 20, declarado HAR replay | 3 sintéticas | 20, captura primaria no adjunta | 14 sintéticas, AUTH_REQUIRED | 57 / 57 |
| mri_019_run_2_1792173721 | 20, declarado HAR replay | 3 sintéticas | 20, captura primaria no adjunta | 14 sintéticas, AUTH_REQUIRED | 57 / 57 |
| mri_019_run_3_1792173723 | 20, declarado HAR replay | 3 sintéticas | 20, captura primaria no adjunta | 14 sintéticas, AUTH_REQUIRED | 57 / 57 |

Las primeras dos corridas están archivadas; la tercera está activa. Cada respuesta contiene 57 registros distintos. Esto demuestra recuperación de filas; no convierte datos sintéticos en adquisiciones válidas ni prueba por sí solo aislamiento completo de todas las pertenencias comerciales.

Cada JSON contiene la instrucción inicial y cuatro decisiones textuales predeterminadas. No contiene trazas primarias por solicitud con respuesta, código HTTP, duración y asociación con publicación. No permite certificar ausencia de asistencia externa durante las ejecuciones originales. Durante esta auditoría no hubo asistencia a MRI.

## Defectos materiales

### 1. Publicaciones artificiales aceptadas como éxito comercial

Primer contraejemplo: investigate_mercadolibre() construye fixture_items con id f"MLC{cat['category_id']}", título "Prenda Nicopoly ...", precio 24990 y seller fijo. Una categoría MLC158340 se convierte en supuesto producto MLCMLC158340. Los conteos 350/350 son constantes. get_official_store_summary() usa una lista de categorías precargada y devuelve OPERATIONAL incluso con AUTH_REQUIRED. Los tres JSON contienen precisamente AUTH_REQUIRED junto a COMPLETED, 14 publicaciones y éxito global PASS. No se demuestran consultas autónomas de categorías o domain_discovery por ese camino; sí existe código de consulta de search, cuya respuesta no se aporta como evidencia primaria.

Ripley genera precio 29990 y SKU RIP_{abs(hash(gid)) % 10000000} desde categorías constantes. SQLite confirma, por ejemplo, RIP_4854811 con URL de categoría de sweaters, precio 29990, raw_source_id RIPLEY-OBS-RIP_4854811 y evidence_type FACET_COUNTER_RECORD. get_commercial_summary() suma constantes 284+256+232=772 sin consulta de red. El log de estrategia no es prueba de navegación ni extracción.

Causa: generación de muestras y reutilización de constantes se presentan como adquisición y observación comercial verificadas. Ninguna de las tres corridas demuestra autonomía comercial completa.

### 2. Nuevo escritor inicial sin barrera de producción

execute_autonomous_order() abre sqlite3.connect(self.db_path) y llama _init_sqlite_tables() antes de los adaptadores protegidos. No llama StorageConfig.assert_write_allowed() en ese punto; el constructor admite db_path arbitrario.

Reproducción: probe_writer.py ejecuta el prefijo exacto extraído por AST, con ruta productiva y sqlite3.connect sustituido por un centinela que registra la ruta y lanza excepción antes de I/O. Resultado: la ruta productiva alcanza connect sin barrera. No se abrió ni escribió la base productiva. Es una prueba acotada del punto de entrada, no una ejecución integral del runner. La existencia de las 36 barreras anteriores no protege este escritor nuevo.

### 3. API y presentación declaran operación sin evidencia de corrida

/api/multimarketplace/summary devuelve constantes: Paris 4902/4211, Falabella 368, Ripley 772 y ALL_MARKETPLACES_OPERATIONAL. No consulta SQLite ni run_id. Su cuerpo exacto, ejecutado aisladamente, devuelve esos valores sin dependencia de datos.

index.html consume esa respuesta y dibuja badge-success para el estado; además anuncia consolidación "en vivo". Por tanto, la vista comparativa no verifica concordancia con las tres corridas ni comunica correctamente el bloqueo de Mercado Libre. Se verificaron funciones API y plantilla; no se realizó una sesión de navegador ni se certificó el arranque completo del dashboard.

### 4. Paris: hash correcto no demuestra replay ni adquisición de esta corrida

Los tres JSON identifican CONTROLLED_HAR_REPLAY y el mismo HAR del 15 de octubre. Su SHA-256 recalculado es:
1ed56cc6a9453d6b67a64f6c7566b2496a2294db661ff3f7fc3e9e5077483ed9.

Sin embargo, la rama denominada replay fija 4902/4211 y llama harvest_sample_publications(), que ejecuta browse() mediante urllib.request.urlopen; no reproduce el cuerpo del HAR como entrada. La primera estrategia busca total_brand en get_brand_summary(), cuyo contrato devuelve total_brand_results, y contiene fetch_brand_publications(), método ausente. La etiqueta de estrategia no permite atribuir los 20 registros a un replay efectivo. Falta respuesta primaria por consulta vinculada a cada corrida. El hash valida bytes del archivo, no la narrativa de ejecución ni los totales constantes.

Falabella dispone de extracción SSR implementada y los tres JSON declaran su primera estrategia exitosa. Solo se aportan resumen y conteos, sin respuesta HTML/SSR capturada con hash, fecha y vínculo a cada publicación. No se marca FAIL por falta de una investigación nueva: se deja su adquisición autónoma sin verificar. El fallback contiene además un payload literal; no se atribuye su uso a estas corridas.

## Control de bucles y preservación

El runner recorre una secuencia finita de cuatro marketplaces y continúa tras resultados parciales. Hay timeouts de solicitudes en los adaptadores, pero no se demuestra presupuesto global de tiempo/solicitudes ni registro de causas de cada fallback. No se observó bucle infinito en los artefactos; tampoco se certifica recuperación autónoma mediante nombres de estrategias no ejecutadas.

Se copiaron bases usando conexiones SQLite mode=ro y backup a evidence/mri_codex_autonomous_audit_020. Ambas copias devuelven integrity_check=ok y foreign_key_check=[].

Las 2.533 filas del run original run_va_mri_operational_integration_1792000336 conservan los 21 atributos compartidos. Hash de filas ordenadas:
c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b,
igual a la referencia anterior. Los cinco archivos productivos protegidos tienen hash idéntico antes/después de esta auditoría. Esta comparación no reconstruye el estado previo de la ejecución de Antigravity ni elimina la regresión de aislamiento.

## Evidencias y límites de reproducción

Carpeta local: evidence/mri_codex_autonomous_audit_020/.
- audit_offline.py y offline_results.json: copias, conteos, ejemplos, integridad, hashes de producción.
- probe_writer.py y writer_probe.json: centinela sin I/O productivo.
- probe_api.py y api_results.json: funciones exactas de historial y resumen montadas en ASGI aislada. Se sustituyó el catálogo maestro por mapas vacíos; no es el arranque de la aplicación completa. Las tres rutas /api/history/{run_id} devolvieron HTTP 200 con contenido de 57 registros cada una.
- remote_evidence.json: contenidos y blobs consultados en GitHub.
- SHA256SUMS.txt: archivos de evidencia de esta auditoría.

Reproducción local: python audit_offline.py; python probe_writer.py; python probe_api.py desde esta carpeta del checkout con las bases fuente locales. Las copias SQLite son artefactos locales; no se publican bases privadas en GitHub. Sin esas bases, GitHub permite reproducir los defectos de código y constantes, pero no certificar los conteos SQL locales.

Dos invocaciones iniciales de Python quedaron sin salida bajo el sandbox y fueron interrumpidas; las mismas comprobaciones locales terminaron con permiso de ejecución. La primera prueba API falló por un campo incorrecto del script auditor; se corrigió únicamente ese script y la repetición terminó. No se modificó código MRI/VA.

## Decisión

FAIL: la evidencia accesible existe, por lo que no corresponde WAITING_FOR_EXECUTION. Se examinaron tres corridas posteriores, pero contienen publicaciones generadas, estados de éxito sin evidencia comercial suficiente y un escritor nuevo sin barrera. No se autoriza cierre de autonomía. No se inicia desarrollo, investigación comercial, nueva fase, vigilancia ni fusión.
