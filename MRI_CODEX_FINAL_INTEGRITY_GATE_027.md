# MRI_CODEX_FINAL_INTEGRITY_GATE_027

Fecha: 2026-10-19 (America/Santiago). Auditor independiente: CODEX.
**Dictamen: FAIL. MRI-022 no queda aprobado dentro del alcance de este gate.**

```makefile
TASK_ID=MRI-CODEX-FINAL-INTEGRITY-GATE-027
SHA_AUDITED=e3267801d560f50bb77ff2cb834c4fd4dd4a7c54
RIPLEY_ZERO_STATIC_OBSERVATIONS=PASS_EMPTY_NORMALIZATION_AND_EMPTY_DATABASE
RIPLEY_API_TRUTH=FAIL_PREVIOUS_RUN_REPORTED_AS_CURRENT_OPERATIONAL
MULTIMARKETPLACE_4_STATES=PASS_ISOLATED_PERSISTENCE_AND_SINGLE_MARKETPLACE_UPDATE
MIGRATION_EXISTING_DB=FAIL_FOREIGN_KEYS_INDEX_AND_CONSTRAINT_PRESERVATION
FOREIGN_KEYS=FAIL_FOREIGN_KEY_MISMATCH_AFTER_MIGRATION
MIGRATION_ATOMICITY=FAIL_HIDDEN_ERROR_AND_EMPTY_REPLACEMENT_TABLE
MIGRATION_IDEMPOTENCE=PASS_ON_SUCCESSFUL_SIMPLE_COPY_ONLY
API_HISTORY_CONSISTENCY=FAIL_EMPTY_RUN_STATES_ABSENT_FROM_HISTORY
CATEGORY_ISOLATION_026=PASS_A_B_C_AND_UNKNOWN
MELI_PROVENANCE=PASS_TESTED_LIVE_TYPE_AND_SOURCE_ID
SQLITE_WRITE_GUARDS=PASS_RUNNER_RETARGET_BEFORE_CONNECT
HISTORY_2533=PASS_COUNT_ALL_SHARED_ATTRIBUTES_HASH_AND_ORIGINAL_DB_INTEGRITY
VA_UNCHANGED=VA_RUNTIME_PATHS_ZERO_DIFF;APP_STORAGE_MRI_FOUNDATION_MODIFIED
PRODUCTION_UNCHANGED=PASS_DURING_AUDIT
DATA_ROLLBACK=PASS_EXTERNAL_SQLITE_BACKUP_RESTORE_IN_SANDBOX;DELIVERY_ROLLBACK_INCOMPLETE
FINAL_VERDICT=FAIL
FIRST_MATERIAL_FAILURE=MIGRATION_BREAKS_EXISTING_RUN_FOREIGN_KEYS
NEXT_EXACT_ACTION=CLOSE_RELATIONAL_MIGRATION_AND_ATOMICITY_COUNTEREXAMPLES;REVALIDATE_RIPLEY_RUN_SCOPE
```

## Fuentes, alcance y aislamiento

Se recuperaron desde GitHub el informe MRI_022_FINAL_INTEGRITY_CLOSURE.md, runner, adaptador Ripley, API, mri_foundation.py y pruebas del SHA obligatorio. El checkout local coincide con dicho SHA; las ejecuciones cargan fuentes exactas extraídas de Git, no bytecode local. Se consultó el preflight y las cuatro skills obligatorias.

No hubo adquisiciones comerciales, desarrollo, cambios de código MRI/VA, instalación, procesos MCP ni fusión. Los scrapers se sustituyeron por fallos locales explícitos. Los datos AUDIT_* y LEGACY_* son fixtures de auditoría, nunca evidencia comercial.

Se probaron:
- Una copia SQLite real de MRI-021, con el esquema antiguo y datos existentes, para migración simple, persistencia e idempotencia.
- El esquema completo ADDITIVE_SCHEMA_SQL del SHA anterior 0f523321bd745a8928367379d102358e711ab7f8, con sus relaciones originales, una fila de corrida y una fila dependiente real en mri_evidence_ledger. Se añadió un índice de control para comprobar su conservación.
- Copias independientes de esa base relacionada para transacción activa, fallo de ALTER y restauración.

Las funciones reales de API e historial se extrajeron por AST y se ejecutaron contra las copias; no se arrancó la aplicación completa ni se certificó su interfaz en navegador. Los mapas del catálogo maestro quedaron vacíos para evitar depender de archivos privados. No intervienen en los defectos de migración ni en las pertenencias probadas.

## 1. Primer defecto material: migración incompatible con claves foráneas existentes

Reproducción mínima:
1. Crear la base con el ADDITIVE_SCHEMA_SQL anterior: mri_runs(run_id PRIMARY KEY).
2. Insertar LEGACY_RUN y LEGACY_EV, que lo referencia mediante la FK real de mri_evidence_ledger.
3. Activar foreign_keys=ON fuera de una transacción. El control anterior foreign_key_check devuelve [].
4. Ejecutar el método real AutonomousMultiMarketplaceRunner._init_sqlite_tables().
5. El método retorna sin error. La clave pasa a (run_id, marketplace), pero los hijos siguen referenciando únicamente run_id.
6. foreign_key_check falla: OperationalError: foreign key mismatch - "mri_shadow_snapshots" referencing "mri_runs".

El esquema conserva también la referencia incompatible de mri_evidence_ledger. run_id deja de ser único por sí mismo; no puede seguir siendo la clave de referencia de esos hijos sin una migración coherente de su relación.

Otros efectos observados:
- foreign_keys cambia de 1 a 0 y no se restaura.
- Desaparece audit_runs_status_idx, índice existente antes de DROP TABLE.
- La nueva tabla pierde NOT NULL en started_at, brand, execution_mode, truth_model_version, status y created_at, presentes en el esquema anterior.
- La fila de corrida y la evidencia siguen físicamente presentes en el camino nominal, pero sus relaciones ya no son válidas.
- integrity_check devuelve ok: ese resultado por sí solo no detecta la incompatibilidad de claves foráneas.

La misma incompatibilidad aparece en el nuevo ADDITIVE_SCHEMA_SQL: la clave compuesta se añadió al padre y las referencias hijas siguen dirigidas solo a run_id.

Condición mínima de cierre: migrar conjuntamente la identidad del padre y sus referencias, conservando índices y restricciones, y comprobar las relaciones antes de confirmar la operación. No se implementó una corrección ni se eligió una arquitectura alternativa.

## 2. Atomicidad y detección de fallos: FAIL

### PRAGMA foreign_keys dentro de una transacción

Sobre una copia idéntica del respaldo:
1. foreign_keys=ON.
2. BEGIN.
3. Ejecutar la migración real.

PRAGMA foreign_keys=OFF no cambia el ajuste dentro de esa transacción. El método acaba sin propagar error y deja el esquema antiguo junto a una tabla mri_runs_new adicional. No se completó la migración aunque el llamador recibió retorno normal.

### Fallo controlado después de DROP y antes de renombrar

En otra copia se usó sqlite3.set_authorizer para denegar únicamente SQLITE_ALTER_TABLE. Todo lo anterior fue SQL real del migrador:
- Crea mri_runs_new y copia LEGACY_RUN.
- Ejecuta DROP TABLE mri_runs.
- ALTER TABLE es rechazado.
- El except Exception solo registra debug y continúa.
- CREATE TABLE IF NOT EXISTS mri_runs crea una tabla principal nueva vacía.
- conn.commit() confirma ese estado parcial.

Resultado reproducido:
- La llamada retorna sin error.
- mri_runs existe, pero contiene cero filas.
- mri_runs_new queda presente.
- Las relaciones siguen incompatibles.
- No hubo restauración automática ni señal de error al llamador.

Es un fallo material de atomicidad y de detección, no una interrupción ambiental de la prueba. No se actuó sobre producción.

## 3. Ripley: avances y contaminación persistente

Comprobaciones que pasan:
- normalize_items_to_publications([]) devuelve ([], []).
- En base sin publicaciones Ripley, get_commercial_summary() y /api/ripley/nicopoly devuelven cero publicaciones, categories=[] y NO_EVIDENCE_RECORDED.
- Las cantidades históricas 284/256/232 están separadas como reference_categories/reference_count, sin sumarse como observaciones en el caso vacío.
- investigate_ripley() con AUDIT_TECHNICAL_FAILURE produce PARTIAL y causa técnica.
- Con "403 Cloudflare challenge" produce SOURCE_BLOCKED y causa de bloqueo.
- Ambos resultados carecen de publicaciones y categorías adquiridas. Estas son excepciones simuladas de auditoría, no prueba de bloqueos reales del marketplace.

Defecto mínimo de contaminación:
1. Persistir una publicación de prueba y OLD_CATEGORY en AUDIT_OLD_RIPLEY.
2. Persistir listas vacías en AUDIT_NEW_EMPTY_RIPLEY con SOURCE_BLOCKED.
3. Consultar get_commercial_summary() y /api/ripley/nicopoly.

Ambos devuelven una publicación, OLD_CATEGORY y OPERATIONAL. La nueva corrida no adquirió ninguna publicación.

Causa: el resumen busca todas las publicaciones activas y categorías de Ripley, sin run_id ni selección de corrida actual, y decide OPERATIONAL si hay filas. Persistir una corrida vacía no archiva ni invalida por sí mismo las publicaciones activas de corridas anteriores. La API no expone un run_id que delimite esa lectura ni informa que ese resultado pertenece a una ejecución anterior.

También se observó que las excepciones de inspección SQLite se capturan en debug y permiten responder NO_EVIDENCE_RECORDED, por lo que una ausencia de filas y un fallo de lectura no tienen estados suficientemente diferenciados. El contraejemplo de corrida antigua/nueva basta para FAIL de veracidad de esta API.

## 4. Cuatro estados, actualización de Ripley e historial

En la copia migrada simple, los adaptadores reales persistieron el mismo run_id AUDIT_FOUR:

| Marketplace | Estado inicial | Después de actualizar solo Ripley |
|---|---|---|
| Paris | COMPLETED | COMPLETED |
| Falabella | PARTIAL | PARTIAL |
| Mercado Libre | SOURCE_BLOCKED | SOURCE_BLOCKED |
| Ripley | FAILED | SOURCE_BLOCKED |

Los otros tres registros completos consultados permanecen idénticos. El resumen API conserva esos cuatro estados finales sin sustituirlos por OPERATIONAL.

Esto demuestra la coexistencia nominal bajo la clave compuesta. No subsana el fallo de relaciones en una base dependiente.

Los persistidores siguen usando INSERT OR REPLACE: con la nueva clave ya no eliminan las filas de los otros marketplaces del mismo run, como demuestra el cuadro. Eso no prueba preservación de hijos: la migración deja inválidas las referencias anteriores y no aporta una prueba de actualización con esas relaciones válidas.

Defecto de historial: para AUDIT_FOUR se persistieron estados de los cuatro marketplaces con listas de publicaciones vacías. SQLite y el resumen sí conservan la ejecución, pero get_history() devuelve history=[] y el detalle devuelve "Run AUDIT_FOUR not found". El historial parte exclusivamente de publicaciones; los intentos sin observaciones quedan ausentes aunque existan en mri_runs. Es relevante para registrar fuentes bloqueadas y no confundirlas con corridas inexistentes.

La repetición de _init_sqlite_tables() tras la migración nominal de la copia simple no cambió su estado: idempotencia acotada PASS. No se extiende a los caminos de fallo ni a relaciones incompatibles.

## 5. Regresiones y preservación

- **MRI-026 A/B/C:** cada historial conserva exclusivamente MELI_CAT_CAT_A/B/C, respectivamente; cada resumen cuenta una categoría. AUDIT_UNKNOWN no recupera categorías. PASS del contraejemplo certificado.
- **Barrera previa a conexión:** construir con ruta permitida, redirigir db_path a producción y ejecutar el runner lanza ProductionWriteBlockedError; el centinela registra cero conexiones. PASS del caso de redirección.
- **Mercado Libre:** el persistidor conserva LIVE_OBSERVATION y raw_source_id AUDIT-OBS en la publicación de prueba. PASS de fidelidad de esos campos; no se vuelve a certificar adquisición comercial.
- **Historia original:** 2.533 observaciones de run_va_mri_operational_integration_1792000336; hash de todos los atributos compartidos:
  c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b.
- **Base productiva original copiada de solo lectura:** integrity_check=ok y foreign_key_check=[].
- **Producción durante la auditoría:** hashes de los cinco archivos protegidos iguales antes/después.
- **Checkout:** estado de archivos controlados idéntico antes/después; no se revirtieron cambios ajenos.

Comparación con main remoto consultado, 3e5d058aa3c0b9b388bab990b14d8cc134627d2e:
- Sin cambios en app/auditor, app/scrapers, app/core, app/dashboard, app/loaders y app/config.
- **Sí cambia app/storage/mri_foundation.py**, para modificar el esquema MRI. Se informa expresamente: no corresponde afirmar cero diferencias de todo app/storage. Es un módulo de fundamento MRI; no se demostró una modificación de lógica de VA ajena a ese esquema, pero tampoco se certifica inocuidad de esa alteración, pues sus relaciones fallan.

No se alteró MRI-023 durante la auditoría ni se le extiende aprobación alguna.

## 6. Rollback de datos ejecutado en sandbox

El procedimiento del informe de entrega propone git reset --hard al SHA anterior. No se ejecutó: restaurar código Git no restaura una base ya migrada.

El auditor creó un respaldo SQLite antes de migrar y lo restauró mediante SQLite backup, en sandbox:
- Tras la migración nominal incompatible.
- Tras el fallo controlado que dejó mri_runs vacío.

Se comparó el dump lógico completo: todas las tablas, filas, índices y DDL de ambos destinos restaurados coinciden con el respaldo. Hash del dump lógico en los tres archivos:
27cfd876e376b41079a9215156e20a3539c149ad68883385fbea87564b536cae.
Con foreign_keys=ON, se recuperan la fila, el índice de control, las restricciones originales y foreign_key_check=[].

**PASS de restauración mediante respaldo externo demostrado por Codex.** No se presenta como rollback automático del migrador ni como procedimiento ya entregado por Antigravity. La migración no crea ese respaldo ni revierte automáticamente su error.

## Evidencias reproducibles

Carpeta local: evidence/mri_codex_final_integrity_gate_027/.
- check_integrity.py: carga fuentes exactas, copia bases, ejecuta la migración nominal y negativa, persistencia de estados, API/historial, Ripley y regresiones.
- results.json: estados completos de bases antes/después, errores capturados, respuestas y hashes.
- check_restoration.py y restoration_results.json: igualdad lógica completa tras restauración.
- Fuentes del SHA auditado y ADDITIVE_SCHEMA_SQL de la base anterior.
- remote_evidence.json y SHA256SUMS.txt.

Reproducción local:
python evidence/mri_codex_final_integrity_gate_027/check_integrity.py
python evidence/mri_codex_final_integrity_gate_027/check_restoration.py

Requiere objetos Git y las bases fuente locales indicadas por los scripts. Todos los cambios ocurren dentro de la carpeta de evidencia. Los resultados derivados de SQLite y las copias quedan locales; se publica únicamente este informe.

## Decisión

**FAIL** por migración relacional incompatible, error de migración ocultado con estado parcial y contaminación de la API Ripley desde una corrida anterior.

Primer defecto bloqueante: foreign_key_check deja de ser ejecutable después de la migración nominal por referencias a mri_runs(run_id) que ya no es único. Siguiente acción exacta: cerrar ese contraejemplo y el fallo después de DROP con migración atómica y recuperación de datos verificable; después volver a comprobar el alcance por corrida de Ripley. No se inicia corrección ni nueva fase. No se aprueba MRI-022 ni MRI-023 y no se fusiona a main.
