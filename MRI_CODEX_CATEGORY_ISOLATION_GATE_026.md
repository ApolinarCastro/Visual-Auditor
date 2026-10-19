# MRI_CODEX_CATEGORY_ISOLATION_GATE_026

Fecha: 2026-10-19 (America/Santiago). Auditor: CODEX.

**PASS limitado al cierre reproducible del defecto de aislamiento de categorías A/B. No constituye aprobación global de MRI-022 ni de MRI-023.**

```makefile
TASK_ID=MRI-CODEX-CATEGORY-ISOLATION-GATE-026
STATUS=COMPLETED
SHA_AUDITED=0f523321bd745a8928367379d102358e711ab7f8
AUDIT_A=PASS_EXCLUSIVELY_CAT_A
AUDIT_B=PASS_EXCLUSIVELY_CAT_B
AUDIT_UNKNOWN=PASS_ZERO_CATEGORIES
THIRD_RUN_ISOLATION=PASS_A_AND_B_UNCHANGED_AFTER_CAT_C
SUMMARY_API=PASS_RUN_SCOPED_COUNTS
HISTORY_API=PASS_RUN_SCOPED_MEMBERSHIPS
HISTORY_2533=PASS_COUNT_AND_SHARED_ATTRIBUTE_HASH
VA_UNCHANGED=PASS_VS_REMOTE_MAIN
FINAL_VERDICT=PASS
FIRST_FAILURE=NONE_WITHIN_AUDITED_SCOPE
```

## Fuentes, alcance y método

Se recuperaron desde GitHub el informe MRI_RUN_CATEGORY_ISOLATION_022_DELIVERY.md y las fuentes del SHA obligatorio: API, persistidor Mercado Libre, contrato normalizado y StorageConfig. El checkout local coincide con ese SHA. El diff respecto de su padre solo contiene el informe de entrega y app/mri_dashboard/mri_api.py.

Se consultó el preflight del proyecto y las cuatro skills obligatorias. Se reutilizó el contraejemplo documentado en Gate 025, sin investigación comercial ni desarrollo. Se extrajeron fuentes exactas desde Git; no se utilizó bytecode local.

La base de prueba es una copia realizada mediante SQLite mode=ro y backup de tmp/mri_021_run/mri_021_truth_repair.db. Se vaciaron únicamente tablas MRI de esa copia para introducir el fixture negativo. Se utilizó el persistidor real MeliTaxonomyEngine.persist_to_mri_sqlite() del SHA auditado y la misma publicación en todas las corridas.

Las funciones exactas get_multimarketplace_summary(), fetch_run_publications() y get_history_run_publications() se montaron en una aplicación ASGI aislada y se consultaron por sus rutas. El catálogo maestro se sustituyó por mapas vacíos; no interviene en la pertenencia por run comprobada. No se arrancó la aplicación completa ni se certificó su interfaz en navegador.

Los datos AUDIT_* son fixtures identificados como tales. No se presentaron como adquisiciones comerciales.

## Reproducción y resultados

Publicación compartida: AUDIT_SHARED_PUBLICATION / AUDIT_SKU.
El adaptador añade su prefijo a los IDs: CAT_A se almacena como MELI_CAT_CAT_A, y análogamente B/C.

| Momento | Corrida | Categoría exclusiva en historial API | Resumen: categorías |
|---|---|---|---:|
| Después de A/B | AUDIT_A | MELI_CAT_CAT_A | 1 |
| Después de A/B | AUDIT_B | MELI_CAT_CAT_B | 1 |
| Después de A/B | AUDIT_UNKNOWN | Ninguna; historial HTTP 404 | 0 |
| Después de A/B/C | AUDIT_A | MELI_CAT_CAT_A | 1 |
| Después de A/B/C | AUDIT_B | MELI_CAT_CAT_B | 1 |
| Después de A/B/C | AUDIT_C | MELI_CAT_CAT_C | 1 |
| Después de A/B/C | AUDIT_UNKNOWN | Ninguna; historial HTTP 404 | 0 |

Las consultas de resumen de corridas inexistentes devuelven cero categorías en los cuatro marketplaces. Las consultas de historial de A, B y C devuelven HTTP 200 y exactamente una publicación cada una.

Control anterior: la función de resumen del SHA c7ce7e8bb702b4c0cdd4943b33eac13bf29d4c2e, ejecutada sobre el mismo estado A/B, devuelve categories_count=2 para A. Queda demostrado que el fixture reproduce el defecto previo y que el SHA nuevo lo corrige.

Comprobación directa después de C:
- Tabla activa: exclusivamente publicación AUDIT_SHARED_PUBLICATION, run AUDIT_C, categoría MELI_CAT_CAT_C.
- Tabla de pertenencias históricas: AUDIT_A → MELI_CAT_CAT_A; AUDIT_B → MELI_CAT_CAT_B.
- Ninguna categoría de C aparece en las respuestas históricas de A o B.

Las 26 comprobaciones de contenido y coherencia pasan. La aceptación se fundamenta en los IDs, filas y respuestas anteriores, no en la cantidad de comprobaciones.

## Causa y corrección verificada

La consulta anterior unía publicaciones históricas con pertenencias activas por publication_id, heredando categorías posteriores. La nueva proyección:
- une las pertenencias activas con publicaciones activas cuyo run_id coincide;
- une las pertenencias históricas con publicaciones históricas mediante publication_id y run_id;
- exige status ACTIVE en la rama activa.

La consulta histórica de fetch_run_publications() también enlaza la pertenencia con la publicación histórica por ambas claves. El resultado A/B/C confirma el comportamiento esperado para este contraejemplo.

No se amplió la auditoría a los demás defectos de Gate 025, a otros mecanismos comerciales ni a MRI-023.

## Preservación

Se respaldó también la base productiva con conexión de solo lectura para verificar las observaciones originales. El run run_va_mri_operational_integration_1792000336 mantiene 2.533 filas y el hash de todos los atributos compartidos entre sus tablas activa e histórica:
c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b,
igual a la referencia anterior.

Ambas copias SQLite devuelven integrity_check=ok y foreign_key_check=[].

Los cinco archivos productivos protegidos mantienen hashes idénticos antes/después de esta auditoría. No hubo escrituras en producción. Esta comprobación cubre el intervalo auditado.

La comparación remota main→SHA auditado identifica main en 3e5d058aa3c0b9b388bab990b14d8cc134627d2e y no presenta cambios en app/auditor, app/scrapers, app/core, app/dashboard, app/storage, app/loaders ni app/config. El cambio auditado tampoco modifica los módulos de MRI-023 ni la evidencia histórica MRI-021.

El estado de archivos controlados localmente coincide antes/después de la prueba. No se borraron ni restauraron archivos ajenos.

## Evidencias reproducibles

Carpeta local: evidence/mri_codex_category_isolation_gate_026/.
- check_isolation.py: fixture A/B/C, persistencia real, consultas HTTP ASGI, control de código anterior y comprobaciones de preservación.
- results.json: respuestas completas por momento, pertenencias SQL, resultado de las 26 comprobaciones, hashes e integridad.
- subcarpetas con fuentes exactas del SHA auditado y del control anterior.
- remote_evidence.json: fuentes consultadas en GitHub y comparación con main.
- SHA256SUMS.txt: hashes de los artefactos locales.

Comando: python evidence/mri_codex_category_isolation_gate_026/check_isolation.py.
Requiere los dos objetos Git y las bases locales indicadas en el script. Las bases copiadas y resultados derivados se conservan localmente; se publica únicamente este informe.

## Dictamen

**PASS del defecto A/B dentro del alcance solicitado.** La tercera actualización no altera retrospectivamente las categorías de A y B, y resumen e historial son coherentes.

No se aprueba MRI-022 globalmente, no se modifica MRI-023, no se autoriza una nueva fase ni se fusiona a main.
