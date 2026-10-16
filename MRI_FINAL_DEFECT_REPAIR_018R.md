# MRI-FINAL-DEFECT-REPAIR-018R

**Ejecutor:** Antigravity  
**Fecha:** 2026-10-16  
**Rama:** `feature/mri-final-defect-repair-018r`  
**Base:** `feature/mri-targeted-repair-017`  
**Commit SHA:** `60a5f50db3daba10016674fcb769e31bae1ca243`  
**Referencia obligatoria:** `MRI_CODEX_VALIDATION_018.md` y reproducciones mínimas.  
**Estado:** COMPLETO PARA REVISIÓN INDEPENDIENTE (No se declara PASS antes de validación de Codex).

---

## 1. Resumen Ejecutivo y Alcance de la Misión

Se corrigieron exclusivamente los dos defectos materiales pendientes identificados por Codex en la validación `MRI_CODEX_VALIDATION_018.md`, sin modificar la base productiva de Visual Auditor ni alterar las 36 barreras de aislamiento, los conteos desconocidos (`null`), ni las 2.533 observaciones originales.

### Matriz de Defectos y Estado de Corrección

| Defecto Codex 018 | Causa Raíz Identificada | Corrección Mínima Implementada | Estado |
|---|---|---|---|
| **F1: Procedencia HAR Primaria** | `_resolve_har_provenance()` comprobaba únicamente existencia de archivo en disco y calculaba SHA-256; `harvest_sample_publications()` lo asignaba a cualquier SKU sin comprobar presencia ni correspondencia en el payload del HAR. En UI (`index.html:896`), existía un literal hardcoded de fallback. | 1. `_resolve_har_provenance()` valida correspondencia exacta de registro (`item_sku` y atributos/grupos de `item_data`) dentro de `entry['response']['content']['text']`.<br>2. SKUs ausentes o con fixtures alteradas reciben `PROVENANCE_INCOMPLETE:{sku}` con ruta, SHA y fecha en `None`.<br>3. En UI se eliminó el literal fijo; se muestra dinámicamente la procedencia recuperada o `PROVENANCE_INCOMPLETE`. | **CORREGIDO** |
| **F2: Historial Comercial por Corrida en Esquema Real** | En la copia del esquema SQLite real, la tabla `mri_historical_publication_categories` no existía. El escritor omitía el archivo de enlaces por existencia condicional, pero ejecutaba incondicionalmente el `DELETE` de enlaces activos. Además, `fetch_run_publications()` en `mri_api.py` no consultaba categorías históricas por corrida ni retornaba la lista de pertenencias. | 1. En `persist_to_mri_sqlite`: se asegura `CREATE TABLE IF NOT EXISTS mri_historical_publication_categories` antes de archivar/eliminar enlaces activos de corridas anteriores.<br>2. En `fetch_run_publications`: se consultan las pertenencias a categorías acotadas estrictamente a `run_id` (combinando enlaces activos para publicaciones activas y enlaces archivados para históricas), retornando el array `categories` completo. | **CORREGIDO** |

---

## 2. Evidencias de los Dos Contraejemplos Originales de Codex 018

Se ejecutó el arnés de reproducción y validación de Codex (`evidence/mri_codex_validation_018/validate_018.py`) tanto sobre el esquema sintético público como sobre la copia del esquema SQLite real (`production_copy.db`).

### Contraejemplo 1: Control Negativo de Procedencia HAR

- **Entrada:** `AUDIT018_ABSENT_FROM_HAR` (SKU no existente en los bytes del archivo `paris_search_capture.har`).
- **Comportamiento Anterior:** Heredaba el hash SHA-256 `1ed56cc6a9453d6b...`, ruta y fecha del archivo positivo; la UI mostraba «EVIDENCIA PRIMARIA».
- **Comportamiento Corregido:**
  - `har_provenance.json`:
    - `negative_sku_occurs_in_har`: `false`
    - `raw_source_id`: `"PROVENANCE_INCOMPLETE:AUDIT018_ABSENT_FROM_HAR"`
    - `source_file_path`: `null`
    - `source_file_sha256`: `null`
    - `source_captured_at`: `null`
  - `negative_provenance_storage.json` (SQLite):
    - `raw_source_id`: `"PROVENANCE_INCOMPLETE:AUDIT018_ABSENT_FROM_HAR"`
    - `commercial_attributes`: Sin claves espurias de archivo HAR.
  - `api_negative_provenance.json` (API HTTP):
    - `evidence`: `["Tipo: CONTROLLED_REPLAY", "Posición observada: 1", ..., "Procedencia HAR: PROVENANCE_INCOMPLETE (PROVENANCE_INCOMPLETE:AUDIT018_ABSENT_FROM_HAR)"]`
  - **Resultado:** **PASA**. Ningún producto ajeno al HAR hereda procedencia primaria.

### Contraejemplo 2: Dos Corridas con Pertenencias Distintas en Esquema Real

- **Entrada:** Publicación `PARIS-MKRMXN8EXC` evaluada en:
  - `audit018_run1`: 2 categorías (`mujModEnteritosJardineras`, `mujMrcNicopoly`), seller `NICOPOLY`, promociones originales.
  - `audit018_run2`: 1 categoría (`AUDIT018_C`), seller `Vopero`, promoción `AUDIT018_PROMO2`.
- **Comportamiento Anterior:** En la copia del esquema productivo real, se perdían los enlaces anteriores (`TABLE_ABSENT`), y la API no devolvía las categorías de la primera corrida.
- **Comportamiento Corregido:**
  - `history_real_production_schema_copy.json`:
    - `mri_historical_publication_categories`: Contiene íntegros los enlaces archivados de `audit018_run1` (`hist_audit018_run1_PARIS-MKRMXN8EXC_PARIS_mujModEnteritosJardineras` y `..._PARIS_mujMrcNicopoly`).
    - `mri_publication_categories`: Contiene exclusivamente el enlace activo de `audit018_run2` (`PARIS_AUDIT018_C`).
  - `api_real_production_schema_copy_audit018_run1.json`:
    - `categories`: `[{"group_id": "mujModEnteritosJardineras", "name": "Enteritos y Jardineras"}, {"group_id": "mujMrcNicopoly", "name": "Nicopoly"}]`
    - `real_category`: `"Enteritos y Jardineras"`
    - `HAR SHA-256`: Presente y verificado para la corrida 1.
  - `api_real_production_schema_copy_audit018_run2.json`:
    - `categories`: `[{"group_id": "AUDIT018_C", "name": "Categoría C - fixture segunda corrida"}]`
    - `real_category`: `"Categoría C - fixture segunda corrida"`
    - `Procedencia HAR`: Declarada `PROVENANCE_INCOMPLETE` por ser fixture alterada.
  - **Resultado:** **PASA**. Ambas corridas se recuperan íntegramente desde persistencia y API sin mezcla de estados.

---

## 3. Verificación de Integridad y Regresiones

1. **Barreras de Aislamiento Productivo:**
   - Evaluadas las 36 variantes (`execution_summary.json`):
   - `protection_checks`: 36
   - `protection_checks_blocked`: 36 (bloqueadas antes de I/O)
   - Solicitudes a marketplaces vivos: 0
2. **Conservación de las 2.533 Observaciones Originales:**
   - `history_2533.json`:
     - Recuento: 2.533
     - Hash de todos los atributos antes: `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`
     - Hash de todos los atributos después: `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`
     - `historical_2533_preserved`: `true`
3. **Verificación de Esquema e Integridad SQLite:**
   - `integrity.json`:
     - `public_test_schema`: `integrity_check = [["ok"]]`, `foreign_key_check = []`
     - `real_production_schema_copy`: `integrity_check = [["ok"]]`, `foreign_key_check = []`
4. **Suites Automatizadas de Regresión:**
   - `tests/test_mri_targeted_repair_017.py`: **3 passed** en 22.97s.
   - `tests/test_mri_autonomous_repair_009.py`: **10 passed** en 22.45s.
5. **Aislamiento de Visual Auditor (VA):**
   - Comando: `git diff origin/main -- app/auditor/ app/scrapers/ app/core/`
   - Salida: vacía (0 bytes modificados).

---

## 4. Archivos Modificados

- `app/mri_autonomous/rea_paris_engine.py`:
  - Validación de correspondencia de registros HAR (`item_sku`, `item_data`).
  - Creación garantizada de `mri_historical_publication_categories` en persistencia.
  - Asignación declarativa de `PROVENANCE_INCOMPLETE`.
- `app/mri_dashboard/mri_api.py`:
  - Consulta de pertenencias a categorías activas e históricas acotadas a `run_id`.
  - Inclusión de lista `categories` en la respuesta JSON.
  - Formateo explícito de metadatos HAR primarios versus procedencia incompleta.
- `app/mri_dashboard/templates/index.html`:
  - Eliminación del literal de fallback en el modal de detalle; renderizado dinámico de la procedencia real.

---

## 5. Primer Fallo Pendiente y Siguiente Acción

- **Primer Fallo Pendiente:** Ningún fallo material pendiente detectado en las suites locales ni en el arnés `validate_018.py`.
- **Siguiente Acción:** Validación independiente focalizada por parte de Codex sobre el commit `60a5f50db3daba10016674fcb769e31bae1ca243`. Conforme al contrato, no se declara PASS previo a dicha validación externa.
