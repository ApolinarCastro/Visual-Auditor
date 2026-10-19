# MRI_CODEX_TRUTH_VALIDATION_022

Fecha: 2026-10-19 (America/Santiago). Auditor: CODEX. **Dictamen: FAIL.**

Auditoría posterior de archivos fijados al SHA obligatorio y de la base aislada de MRI-021. No se realizaron nuevas adquisiciones ni se observó la corrida en tiempo real.

```makefile
TASK_ID=MRI-CODEX-TRUTH-VALIDATION-022
STATUS=COMPLETED_WITH_MATERIAL_FAILURES
RUN_ID=mri_021_real_run_1792178465
PARIS=NO_VERIFICADO_PRIMARY_BODY_MISSING;SELLER_TOTAL_ASSUMED
FALABELLA=NO_VERIFICADO_HASH_WITHOUT_CAPTURE_BODY
MERCADO_LIBRE=FAIL_PERSISTED_SOURCE_TYPE;PUBLICATIONS_NO_VERIFICADO
RIPLEY=FAIL_STATIC_COUNTS_AND_UNSUPPORTED_BLOCK_CAUSE
REAL_PUBLICATIONS_VERIFIED=0_OF_60_PRIMARY_VERIFIED;60_OF_60_SQLITE_ROWS_FOUND
AUTONOMY=NOT_DEMONSTRATED_TO_REQUIRED_STANDARD
PRIMARY_EVIDENCE=INSUFFICIENT_FOR_ALL_60
SQLITE_GUARDS=FAIL_RUNNER_RETARGET_BEFORE_CONNECT
API_DASHBOARD=FAIL_BLOCKED_STATE_OVERRIDDEN_AND_RUN_SCOPE_LOST
HISTORY_2533=PASS_COUNT_AND_ALL_SHARED_ATTRIBUTES_HASH
VA_UNCHANGED=PASS_VS_REMOTE_MAIN
PRODUCTION_UNCHANGED=PASS_DURING_AUDIT;ORIGINAL_EXECUTION_NOT_RETROSPECTIVELY_CERTIFIED
FINAL_VERDICT=FAIL
FIRST_MATERIAL_FAILURE=RUNNER_DB_PATH_RETARGET_REACHES_PRODUCTIVE_SQLITE_BEFORE_VALIDATION
NEXT_EXACT_ACTION=CLOSE_PRECONNECT_RETARGET_GUARD_AND_RETURN_BOUNDED_PROOF;NO_REPEATABILITY_AUTHORIZED
```

## Fuente y método

SHA obligatorio y local comprobado: 274005dbef951392d0952253522f645a723b0af4, rama feature/mri-autonomy-truth-repair-021. Se recuperaron desde GitHub, fijados a ese SHA: informe, manifiesto, JSON del run, script ejecutor, runner, cuatro adaptadores, StorageConfig, API y dashboard. Los contenidos y blobs quedan en remote_files.json. Se consultó el preflight y las cuatro skills obligatorias; se reutilizó evidencia histórica sin repetir adquisiciones ni suites masivas.

Se usó SQLite mode=ro para respaldar las bases a una carpeta de auditoría. Las reproducciones actúan sobre copias o interceptan conexiones antes de I/O. Las funciones API exactas se extrajeron mediante AST y montaron en ASGI aislada, sin importar la aplicación completa ni scrapers. Los mapas del catálogo maestro se sustituyeron por mapas vacíos. Es una comprobación de esas funciones y de la plantilla, no una certificación de navegador ni del arranque completo.

Fuentes remotas:
- [Informe de Antigravity](https://github.com/ApolinarCastro/Visual-Auditor/blob/274005dbef951392d0952253522f645a723b0af4/MRI_AUTONOMY_TRUTH_REPAIR_021.md)
- [Evidencia de ejecución](https://github.com/ApolinarCastro/Visual-Auditor/blob/274005dbef951392d0952253522f645a723b0af4/evidence/mri_autonomy_truth_repair_021/mri_021_real_run_1792178465_evidence.json)
- [Script ejecutor](https://github.com/ApolinarCastro/Visual-Auditor/blob/274005dbef951392d0952253522f645a723b0af4/scripts/run_mri_021_real_execution.py)
- [Runner](https://github.com/ApolinarCastro/Visual-Auditor/blob/274005dbef951392d0952253522f645a723b0af4/app/mri_autonomous/autonomous_multimarketplace_runner.py)
- [API](https://github.com/ApolinarCastro/Visual-Auditor/blob/274005dbef951392d0952253522f645a723b0af4/app/mri_dashboard/mri_api.py)

## 1. Primer fallo material: barrera posterior a apertura

Se reconoce el avance: el constructor ahora rechaza una ruta productiva. Sin embargo, execute_autonomous_order() sigue abriendo sqlite3.connect(self.db_path) antes de _init_sqlite_tables(), donde se vuelve a validar. Una redirección posterior al constructor evita la validación previa a apertura.

Reproducción mínima en validate_offline.py:
1. Activar TEST y sandbox.
2. Construir el runner con sandbox/allowed.db: permitido.
3. Cambiar runner.db_path por la ruta absoluta data/sqlite/visibility.db.
4. Ejecutar el prefijo exacto de execute_autonomous_order(), con sqlite3.connect sustituido por un centinela que registra el destino y lanza excepción antes de I/O.
5. Resultado: el destino productivo llega a connect. No se abre ni modifica producción.

Se extrajeron por AST el constructor y el prefijo exacto hasta el primer with; el centinela hace imposible continuar. Esto demuestra el defecto anterior a conexión, sin afirmar una escritura productiva realizada. La validación posterior a apertura no satisface el requisito. Corrección mínima: validar el destino efectivo inmediatamente antes de conectar, manteniendo la coherencia entre ruta validada y utilizada; repetir únicamente este contraejemplo y sus controles. No se implementó la corrección.

Los persist_to_mri_sqlite de Paris, Falabella, Mercado Libre y Ripley sí contienen assert_write_allowed(effective_db) antes de connect; ExperienceStore revalida en su conexión y el persistidor de recovery_runner comprueba antes de escribir. Se revisó ese orden en código; no se declara PASS global de todos los escritores ni se repitieron las 36 pruebas anteriores, dado el nuevo contraejemplo bloqueante.

## 2. Verificación de las 60 publicaciones

La base tmp/mri_021_run/mri_021_truth_repair.db conserva 60 publicaciones distintas del run: 20 Paris, 20 Falabella, 20 Mercado Libre, 0 Ripley. Las 60 filas fueron inspeccionadas individualmente en results.json: identificador, SKU, URL canónica, tipo de evidencia, raw_source_id, origen, hash y fecha de captura cuando existen. Recuperar filas o reconocer una URL comercial no demuestra autenticidad de su adquisición.

| Marketplace | Filas | Fuente primaria recuperable vinculada | Resultado |
|---|---:|---|---|
| Paris | 20 | Sin ruta/hash/fecha de captura primaria en las 20 filas; CONSTRUCTOR-LIVE-API:SKU no identifica una respuesta conservada | 20 NO_VERIFICADO |
| Falabella | 20 | Misma URL de catálogo y SHA declarado para las 20; no se aporta el cuerpo HTML identificado | 20 NO_VERIFICADO |
| Mercado Libre | 20 | Sin captura DOM/respuesta primaria y hash vinculados; persistidas como OFFICIAL_API_RECORD | 20 NO_VERIFICADO |

Ejemplos publicados: Paris MKYBS8MTEG; Falabella 152147936, URL de producto padre 152147934; Mercado Libre MLC1573366415. Se conservan los 60 identificadores y sus campos en la evidencia local. No se consultaron sus URLs, porque sería una adquisición nueva y tampoco demostraría qué se recibió el 16 de octubre.

Falabella declara SHA 01bcdb5364e052f864eabc9e80ec2f2577ca72b7406b684d0b375452643f18aa y captura 2026-10-16T19:21:22.336775+00:00. El adaptador calcula el hash del HTML pero devuelve datos extraídos sin conservar ese cuerpo como archivo en el camino examinado. El source_file_path persistido es una URL, no acceso al cuerpo histórico. No se aceptó el hash como prueba autosuficiente.

En Paris, get_brand_summary() asigna total_official_seller=total_brand sin medir el vendedor. El runner presenta 4904/4904 como dos recuentos comerciales. Además, harvest_sample_publications() marca LIVE_OBSERVATION cuando no hay coincidencia con HAR, pero no conserva la respuesta ni su hash en esas publicaciones. La ausencia de coincidencia con un HAR no certifica por sí misma una adquisición en vivo.

Mercado Libre normaliza observaciones del scraper como LIVE_OBSERVATION y MELI-OBS-..., pero persist_to_mri_sqlite() escribe literalmente OFFICIAL_API_RECORD y MELI-API-SKU. SQLite confirma esa transformación en las 20 filas, y mri_runs termina con source_method=OFFICIAL_MELI_API aunque el JSON declara MELI_HEADLESS_CATALOG_SCRAPER. Es una alteración reproducible de procedencia. El adaptador también completa vendedor/store desde constantes; una identidad comercial inferida no equivale a identidad observada.

No se detectan los antiguos SKUs RIP_hash o MLCMLC en estas 60 filas. Esto reconoce su retirada, pero no prueba cero datos ficticios: el detector del script solo incrementa cuando además aparece la cadena literal hash en un RIP_ SKU; no detectaría el antiguo RIP_4854811. Varios criterios del manifiesto son True literales y no resultados de comprobaciones. No se afirma que las 60 publicaciones sean falsas; se clasifican NO_VERIFICADO por evidencia insuficiente.

## 3. Autonomía y Ripley

La orden inicial se conserva en el JSON, junto con cuatro decisiones predeterminadas. El código tiene caminos reales de API/SSR/scraper y los nuevos artefactos son compatibles con su uso; no bastan para reconstruir cada solicitud y decisión efectivamente ejecutada. Faltan respuestas primarias y logs por acción. No se certifica ausencia de ayuda externa retrospectivamente.

Ripley declara una llamada headless a search/nicopoly y después un fallback de facetas. El segundo camino no consulta Ripley: get_commercial_summary() suma constantes 284+256+232=772, y normalizar una lista vacía genera entidades a partir de esas mismas categorías. El runner registra PARTIAL y cero publicaciones, lo cual es un avance, pero sigue afirmando metadatos observados sin adquisición que los respalde.

Reproducción independiente probe_ripley.py: se ejecuta el método exacto con una excepción local explícita AUDIT_LOCAL_FAILURE_NOT_WAF en el scraper y persistencia simulada sin I/O. El resultado sigue diciendo WAF/Turnstile y devuelve 772/772. La prueba es un contraejemplo controlado, no evidencia comercial ni prueba del error original. Demuestra que la causa se atribuye sin discriminar el fallo. El JSON original no conserva la excepción, HTTP, captura del bloqueo ni recuperación, por lo que la causa real del intento original queda NO_VERIFICADO. Una llamada headless más lectura de constantes no demuestra agotamiento de capacidades; RIPLEY_WAF_DOCUMENTATION es un estado, no otra adquisición.

## 4. API y dashboard

La función de historial recupera las 60 filas con contenido. La comparativa ya consulta conteos, pero falla en fidelidad de estado y alcance:

- mri_runs tiene run_id como clave única; cada adaptador usa INSERT OR REPLACE. Para este run solo queda la fila de Mercado Libre. Desaparece de ese registro la condición PARTIAL de Ripley. La API devuelve Ripley NOT_EXECUTED en vez de la parcialidad informada.
- Cualquier marketplace con total_pubs>0 se fuerza a OPERATIONAL. En la copia se cambió únicamente el estado persistido del run a BLOCKED; la API siguió devolviendo Mercado Libre OPERATIONAL. Se trata de un fixture negativo en copia, no de modificación de la corrida original.
- Los conteos de categorías se obtienen globalmente de mri_categories, sin run_id ni pertenencia del run. Un run inexistente devuelve 11/2/15/3 categorías de Paris/Falabella/ML/Ripley.
- official_seller_publications se iguala al número de publicaciones, sin filtrar identidad/vendedor.
- Las vistas específicas aún llaman rutas que construyen datos estáticos o efectúan consultas nuevas. La plantilla carga /api/multimarketplace/summary sin el run_id elegido en historial; el selector histórico no prueba que Tab D refleje la misma corrida. La ruta Ripley sigue devolviendo OPERATIONAL y 772 constantes.
- Se reconoce que el color de la comparativa ahora distingue algunos estados parciales. Eso no corrige el origen de los valores ni el estado ya sobrescrito por la API.

Las pruebas usaron las funciones exactas en ASGI, SQLite aislada y catálogo vacío. No hubo sesión de navegador, nuevas solicitudes comerciales ni declaración de integración visual completa.

## 5. Integridad y recursos protegidos

Ambas copias SQLite: integrity_check=ok y foreign_key_check=[].

Las 2.533 observaciones del run original run_va_mri_operational_integration_1792000336 conservan el hash de todos los atributos compartidos entre tablas activa e histórica:
c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b,
coincidente con la referencia anterior.

Los cinco archivos productivos protegidos mantienen hashes iguales antes/después de la auditoría. No se atribuye retrospectivamente esa garantía a toda la ejecución de Antigravity sin una línea base anterior accesible.

La comparación GitHub main→SHA obligatorio identifica main en 3e5d058aa3c0b9b388bab990b14d8cc134627d2e y cero cambios en app/auditor, app/scrapers, app/core, app/dashboard, app/storage, app/loaders y app/config. No se modificaron archivos controlados localmente. El checkout contiene archivos no versionados preexistentes; no se presenta como checkout limpio ni se usaron como prueba de código versionado.

## Evidencias y decisión

Carpeta local: evidence/mri_codex_truth_validation_022/.
- remote_files.json: respuestas GitHub de los 12 archivos fijados al SHA.
- validate_offline.py y results.json: copia de bases, las 60 filas, matriz individual de procedencia, controles SQLite, hashes de conservación, pruebas de barrera y API.
- probe_ripley.py y ripley_probe.json: contraejemplo de clasificación de fallo sin red.
- remote_compare.json: comparación contra main remoto.
- SHA256SUMS.txt: hashes locales.

Reproducir desde el mismo checkout, con Python y dependencias disponibles: python evidence/mri_codex_truth_validation_022/validate_offline.py y python evidence/mri_codex_truth_validation_022/probe_ripley.py. El primer script requiere las bases locales indicadas; solo escribe copias y evidencia bajo su carpeta. Los resultados y copias derivados de SQLite permanecen locales; se publica únicamente este informe, sin volcar bases ni datos privados.

**FAIL** por defectos materiales reproducibles, aunque la verificación primaria por sí sola quedaría bloqueada por ausencia de cuerpos históricos. Primer defecto bloqueante: redirección del runner antes de apertura. Siguiente acción exacta: cerrar esa barrera y devolver la reproducción mínima; las demás condiciones de procedencia y fidelidad quedan documentadas para cierre acotado. No se autoriza repetibilidad, no se inicia desarrollo ni una fase nueva y no se fusiona ninguna rama.
