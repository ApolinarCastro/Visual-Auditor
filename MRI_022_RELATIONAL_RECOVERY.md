# MRI_022_RELATIONAL_RECOVERY.md

**Fecha:** 2026-10-20  
**Ejecutor:** ANTIGRAVITY  
**Auditor independiente:** CODEX  
**Proyecto:** Visual Auditor / MRI  
**Base certificada de aislamiento A/B/C:** `0f523321bd745a8928367379d102358e711ab7f8`  
**Rama:** `fix/mri-022-relational-recovery`

---

## 1. RESUMEN EJECUTIVO Y OBJETIVO

El presente informe certifica el cierre determinista y material de los tres defectos reproducidos por Codex en el dictamen de integridad independiente `MRI_CODEX_FINAL_INTEGRITY_GATE_027.md` (originados en el SHA descartado `e3267801d560f50bb77ff2cb834c4fd4dd4a7c54`).

Se ha implementado la opción de diseño prioritaria: **separar la entidad de corrida `mri_runs` de sus estados por marketplace mediante la tabla relacional secundaria `mri_run_marketplace_states`**, eliminando de forma total y definitiva la migración destructiva (`DROP TABLE` / `ALTER TABLE`), preservando la unicidad de `run_id` como clave primaria única de `mri_runs`, protegiendo todas las foreign keys hijas (`mri_evidence_ledger`, `mri_shadow_snapshots`, etc.) y garantizando la veracidad y el alcance por corrida de la API comercial de Ripley y el historial unificado.

---

## 2. CIERRE DE LOS DEFECTOS MATERIALES

### Defecto 1: Incompatibilidad Relacional de Claves Foráneas y Destrucción de Esquema
* **Causa raíz en SHA fallido:** El intento anterior de convertir `mri_runs` en clave primaria compuesta `(run_id, marketplace)` rompía las restricciones de integridad relacional en SQLite (`OperationalError: foreign key mismatch`) debido a que las tablas hijas (`mri_evidence_ledger`, `mri_shadow_snapshots`) referencian únicamente `mri_runs(run_id)`. Además, ejecutar `DROP TABLE mri_runs` eliminaba índices creados por usuarios o dependencias (como `audit_runs_status_idx`) y destruía restricciones `NOT NULL`.
* **Solución Implementada:**
  1. Se conserva intacta la definición canónica de `mri_runs` con su clave primaria única:
     ```sql
     CREATE TABLE IF NOT EXISTS mri_runs (
         run_id TEXT PRIMARY KEY,
         started_at TEXT NOT NULL,
         finished_at TEXT,
         marketplace TEXT NOT NULL,
         brand TEXT NOT NULL,
         execution_mode TEXT NOT NULL,
         truth_model_version TEXT NOT NULL,
         terminal_state TEXT,
         source_method TEXT,
         status TEXT NOT NULL,
         created_at TEXT NOT NULL
     );
     ```
  2. Se incorpora en `app/storage/mri_foundation.py` (`ADDITIVE_SCHEMA_SQL`) y en `AutonomousMultiMarketplaceRunner._init_sqlite_tables` la tabla relacional secundaria formal:
     ```sql
     CREATE TABLE IF NOT EXISTS mri_run_marketplace_states (
         run_id TEXT NOT NULL,
         marketplace TEXT NOT NULL,
         terminal_state TEXT,
         source_method TEXT,
         execution_mode TEXT,
         started_at TEXT,
         finished_at TEXT,
         status TEXT NOT NULL,
         created_at TEXT,
         PRIMARY KEY (run_id, marketplace),
         FOREIGN KEY (run_id) REFERENCES mri_runs(run_id)
     );
     ```
  3. En todos los motores de persistencia (`rea_paris_engine.py`, `falabella_ssr_engine.py`, `meli_taxonomy_engine.py`, `ripley_commercial_engine.py`), se eliminó `INSERT OR REPLACE INTO mri_runs`. Ahora se utiliza `INSERT OR IGNORE INTO mri_runs` para registrar y proteger la fila padre sin recrearla ni borrar referencias hijas por cascada. Cada marketplace persiste su estado individual mediante `INSERT OR REPLACE INTO mri_run_marketplace_states`.
  4. Si una corrida involucra múltiples marketplaces, el valor de `mri_runs.marketplace` se actualiza de forma segura a `MULTI_MARKETPLACE`.

### Defecto 2: Eliminación de la Migración Destructiva y Atomicidad
* **Causa raíz en SHA fallido:** El migrador en `autonomous_multimarketplace_runner.py` ejecutaba `DROP TABLE mri_runs` y un `ALTER TABLE mri_runs_new RENAME TO mri_runs`. Si fallaba el renombramiento o se ejecutaba dentro de una transacción con `PRAGMA foreign_keys`, la base de datos quedaba con tablas vacías o esquemas corruptos.
* **Solución Implementada:**
  - Se eliminó totalmente cualquier comando `DROP TABLE mri_runs` o `ALTER TABLE`.
  - La inicialización es 100% aditiva, idempotente y no destructiva a través de `CREATE TABLE IF NOT EXISTS`.
  - Las transacciones con `PRAGMA foreign_keys = ON` pasan limpiamente con `PRAGMA foreign_key_check` devolviendo `[]` (cero violaciones).

### Defecto 3: Veracidad y Alcance de Corrida en Ripley
* **Causa raíz en SHA fallido:** `get_commercial_summary()` en `ripley_commercial_engine.py` consultaba todas las publicaciones activas en `mri_publications WHERE marketplace = 'Ripley'` sin filtrar por `run_id`, asignando las publicaciones de una corrida anterior (`AUDIT_OLD_RIPLEY`) a una corrida nueva vacía o bloqueada (`AUDIT_NEW_EMPTY_RIPLEY`).
* **Solución Implementada:**
  1. `get_commercial_summary(db_path=None, run_id=None)` ahora acepta `run_id` explícito o resuelve dinámicamente la última corrida ejecutada para Ripley desde `mri_run_marketplace_states`.
  2. Las publicaciones consultadas quedan estrictamente acotadas a `run_id = ?` (tanto en activas como en históricas).
  3. Si la corrida objetivo no adquirió publicaciones (por ejemplo, corrida con estado terminal `SOURCE_BLOCKED` o `FAILED`), la API reporta:
     - `total_brand_publications = 0`
     - `total_official_seller_publications = 0`
     - `categories = []`
     - `status = SOURCE_BLOCKED` (o el estado terminal exacto registrado en `mri_run_marketplace_states`).
  4. La ruta FastAPI `/api/ripley/nicopoly` acepta `run_id: Optional[str] = None` y delega a `engine.get_commercial_summary(db_path=..., run_id=run_id)`.

### Defecto 4: Preservación de Corridas sin Publicaciones en Historial
* **Causa raíz en SHA fallido:** `get_history()` partía de una consulta sobre `all_pubs` (`mri_publications UNION ALL mri_historical_publications`), por lo que cualquier corrida que no hubiera adquirido publicaciones quedaba completamente excluida del historial (`history = []`), y su detalle arrojaba error 404 (`"Run not found"`).
* **Solución Implementada:**
  1. En `app/mri_dashboard/mri_api.py`, `get_history()` ahora parte de `mri_runs r LEFT JOIN all_pubs p ON r.run_id = p.run_id`, garantizando que corridas existentes con cero publicaciones figuren en el historial con `total = 0`, `confirmed = 0` y su modo de ejecución real.
  2. `get_history_run_publications(run_id)` verifica si `run_id` existe en `mri_runs` aun cuando tenga 0 publicaciones en SQLite. Si existe, retorna HTTP 200 con `publications = []`, `count = 0`, `source = "SQLITE_EMPTY_RUN"` y su `status` correspondiente.

---

## 3. RESULTADOS DE VERIFICACIÓN Y PRUEBAS REPRODUCIBLES

Se diseñó y ejecutó la suite de integración exhaustiva `tests/test_mri_022_relational_recovery.py`:

```
tests/test_mri_022_relational_recovery.py::test_relational_model_and_foreign_keys PASSED
tests/test_mri_022_relational_recovery.py::test_four_marketplaces_independent_states PASSED
tests/test_mri_022_relational_recovery.py::test_ripley_run_scoped_truth_and_zero_static PASSED
tests/test_mri_022_relational_recovery.py::test_empty_runs_preserved_in_history_and_detail PASSED
tests/test_mri_022_relational_recovery.py::test_abc_category_isolation_preserved PASSED
```

### Resultados de los Contraejemplos de Codex 027:
1. **Prueba Relacional y Foreign Keys:** `mri_runs` conserva `run_id PRIMARY KEY`. Las claves foráneas de `mri_evidence_ledger` y `mri_run_marketplace_states` son verificadas con `PRAGMA foreign_key_check;` devolviendo `[]` (cero violaciones).
2. **Prueba de Cuatro Marketplaces:** En una misma corrida compartida `RUN_SHARED_4MP_001`, Paris (`COMPLETED`), Falabella (`PARTIAL`), Mercado Libre (`SOURCE_BLOCKED`) y Ripley (`FAILED`) coexisten simultáneamente. Actualizar el estado de Ripley a `SOURCE_BLOCKED` no muta ni afecta a los otros tres marketplaces.
3. **Prueba de Ripley y Cero Estáticos:**
   - Corrida anterior `AUDIT_OLD_RIPLEY`: 1 publicación, categoría recuperada, estado `OPERATIONAL`.
   - Corrida nueva `AUDIT_NEW_EMPTY_RIPLEY`: 0 publicaciones, 0 categorías, estado `SOURCE_BLOCKED`. Sin contaminación cruzada.
4. **Prueba de Corridas sin Publicaciones en Historial:**
   - La corrida con 4 estados y 0 publicaciones figura en `get_history()` con `total: 0`, `confirmed: 0`.
   - `get_history_run_publications()` devuelve status 200 con `source: "SQLITE_EMPTY_RUN"` y `count: 0`.
5. **Prueba de Preservación A/B/C (MRI-026):**
   - Las corridas A, B y C mantienen estricto aislamiento de categorías sin contaminación cruzada.

---

## 4. INTEGRIDAD DE DATOS Y PRODUCCIÓN

1. **Hash de las 2.533 Observaciones Históricas:**
   - Recuento verificado: `2,533`
   - Hash SHA-256 verificado:
     `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`
     *(Consistente y 100% idéntico a la base de certificación).*
2. **Archivos de Producción y VA:**
   - Se verificó `git diff --stat -- app/auditor app/scrapers app/core app/dashboard app/loaders app/config` obteniendo **exactamente cero diferencias**.
   - No se modificó MRI-023.
   - No se modificó la base productiva `data/sqlite/visibility.db`.

---

## 5. CONCLUSIÓN Y SOLICITUD DE AUDITORÍA

Los defectos materiales de integridad relacional, atomicidad de migración, veracidad de Ripley y preservación de corridas sin publicaciones quedan formal y técnicamente resueltos bajo el diseño no destructivo y modular solicitado.

Se solicita formalmente al auditor independiente **CODEX** la ejecución de la auditoría independiente sobre esta entrega en la rama `fix/mri-022-relational-recovery`.
