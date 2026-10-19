# MRI-022 — INFORME DE CIERRE DEFINITIVO DE INTEGRIDAD COMERCIAL

**Ejecutor:** ANTIGRAVITY  
**Auditor independiente:** CODEX  
**Proyecto:** Visual Auditor / MRI  
**Fecha:** 2026-10-19  
**Rama de entrega:** `fix/mri-022-final-integrity`  
**Base obligatoria:** `0f523321bd745a8928367379d102358e711ab7f8`  
**Estado MRI-026:** PASS independiente conservado e intacto.

---

## 1. RESUMEN EJECUTIVO

Se ejecutaron quirúrgicamente las correcciones definitivas requeridas para los dos defectos materiales pendientes de MRI-022 señalados en `MRI_CODEX_INDEPENDENT_GATE_025.md`:

1. **Eliminación Total de Datos Comerciales Estáticos de Ripley:**
   - Se removió la inyección de constantes internas (`RIPLEY_VERIFIED_CATEGORIES` con conteos 284 + 256 + 232 = 772) en publicaciones o categorías supuestamente observadas.
   - `normalize_items_to_publications([])` devuelve deterministamente `([], [])`. Ninguna adquisición fallida inventa categorías ni publicaciones.
   - Las categorías de referencia históricas se preservan como `RIPLEY_REFERENCE_CATEGORIES` para conocimiento estático documental, identificadas inequívocamente con `reference_count` y sin presentarse jamás como observaciones vivas de la corrida.
   - `get_commercial_summary()` y el endpoint `/api/ripley/nicopoly` consultan SQLite primero; ante la ausencia de adquisiciones verificadas en la corrida, devuelven deterministamente `0` publicaciones verificadas y estado `NO_EVIDENCE_RECORDED`.
   - La causa del fallo de adquisición distingue estrictamente entre bloqueos WAF/Turnstile (`SOURCE_BLOCKED`) y fallos técnicos ordinarios (`PARTIAL`).

2. **Persistencia Simultánea de Estados por Marketplace en Corridas Multimarketplace:**
   - Se actualizó el esquema de `mri_runs` para utilizar clave primaria compuesta: `PRIMARY KEY (run_id, marketplace)`.
   - Los adaptadores (`rea_paris_engine.py`, `falabella_ssr_engine.py`, `meli_taxonomy_engine.py`, `ripley_commercial_engine.py`) registran su estado mediante `INSERT OR REPLACE INTO mri_runs` sin sobrescribir los estados de los demás marketplaces de la misma corrida.
   - Se implementó auto-migración determinista no destructiva en `autonomous_multimarketplace_runner.py` para bases existentes.
   - La API (`/api/multimarketplace/summary`) y el historial (`/api/history`) leen y proyectan simultáneamente los cuatro marketplaces (Paris, Falabella, Mercado Libre y Ripley) sin omitir estados fallidos, parciales o bloqueados, y sin inventar estados `OPERATIONAL` por la mera presencia de publicaciones.

3. **Preservación Estricta de Integridad y Recursos Protegidos:**
   - La barrera previa a toda conexión SQLite (`StorageConfig.assert_write_allowed`) se mantiene activa en todos los adaptadores y runners.
   - El aislamiento de pertenencias de categorías por corrida certificado en MRI-026 se mantiene íntegro (cero fugas entre corridas A y B).
   - Las 2.533 observaciones originales en `data/sqlite/visibility.db` arrojan el hash exacto: `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`.
   - Cero modificaciones a los archivos de producción de Visual Auditor (`app/auditor/`, `app/scrapers/`, `app/core/`, `app/dashboard/`).

---

## 2. MATRIZ DE DEFECTOS Y CORRECCIONES

| ID Defecto | Componente | Comportamiento Anterior | Corrección Implementada | Verificación |
|---|---|---|---|---|
| **DEF-022-RIP-01** | `ripley_commercial_engine.py` | `normalize_items_to_publications([])` pre-poblaba `entities_map` con 3 categorías de `RIPLEY_VERIFIED_CATEGORIES` (284, 256, 232) e insertaba filas en `mri_categories` sin adquisiciones reales. | Si `raw_items` está vacío, devuelve inmediatamente `([], [])`. Si hay items, las categorías se derivan exclusivamente de los atributos del item. Las constantes se renombraron a `RIPLEY_REFERENCE_CATEGORIES` como metadatos de referencia. | `test_ripley_static_data_elimination_unit`, `test_ripley_investigate_failure_leaves_zero_static_categories_in_db` (PASS) |
| **DEF-022-RIP-02** | `ripley_commercial_engine.py` / `/api/ripley/nicopoly` | `get_commercial_summary()` sumaba 772 publicaciones ficticias y devolvía `OPERATIONAL` por defecto. | Consulta SQLite primero. Si no hay registros verificados, devuelve `total_brand_publications = 0`, `categories = []`, `status = "NO_EVIDENCE_RECORDED"`. | `test_ripley_get_commercial_summary_offline`, `test_ripley_api_route_offline` (PASS) |
| **DEF-022-RIP-03** | `autonomous_multimarketplace_runner.py` | `investigate_ripley` pasaba entidades estáticas al persistir fallos, insertando filas de categorías Ripley vacías. | `get_commercial_summary(db_path=self.db_path)` consulta SQLite del sandbox; la persistencia recibe listas vacías y no inserta filas espurias. Clasificación estricta WAF (`SOURCE_BLOCKED`) vs técnico (`PARTIAL`). | `test_ripley_waf_versus_technical_failure_classification` (PASS) |
| **DEF-022-RUN-01** | `mri_runs` schema (`mri_foundation.py`, `runner.py`) | `run_id` era `PRIMARY KEY` simple; cada adaptador ejecutaba `INSERT OR REPLACE`, sobrescribiendo el estado del marketplace previo en la misma corrida. | Se estableció `PRIMARY KEY (run_id, marketplace)`. Los 4 marketplaces coexisten simultáneamente en la misma corrida. Migración no destructiva automática incluida. | `test_multimarketplace_simultaneous_run_states` (PASS) |
| **DEF-022-API-01** | `mri_api.py` (`get_multimarketplace_summary`) | Si existían publicaciones en SQLite, forzaba el estado a `OPERATIONAL` ignorando estados terminales persistidos. | Se eliminó la asignación indiscriminada de `OPERATIONAL`. Se respeta estrictamente el `terminal_state` o `status` registrado en `mri_runs`. | `test_multimarketplace_simultaneous_run_states` (PASS) |

---

## 3. SUITE DE PRUEBAS REPRODUCIBLES Y EVIDENCIA

Se desarrolló la suite completa e independiente:
`tests/test_mri_022_final_integrity.py`

Comando de ejecución:
```bash
python -m unittest tests/test_mri_022_final_integrity.py
```

Resultados obtenidos:
- `test_multimarketplace_simultaneous_run_states`: **PASS** (Persistencia simultánea de Paris=COMPLETED, Falabella=COMPLETED, Mercado Libre=SOURCE_BLOCKED, Ripley=PARTIAL en la misma corrida).
- `test_mri_026_category_isolation_across_runs_repro`: **PASS** (Aislamiento estricto de membresías RUN_A vs RUN_B; conteo exacto de 1 categoría cada una).
- `test_production_database_integrity_and_hash`: **PASS** (2.533 registros históricos, integridad ok, FK ok, hash de referencia `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`).
- `test_ripley_api_route_offline`: **PASS** (Endpoint devuelve 0 publicaciones y status NO_EVIDENCE_RECORDED).
- `test_ripley_get_commercial_summary_offline`: **PASS** (Total 0 publicaciones, 0 categorías observadas).
- `test_ripley_investigate_failure_leaves_zero_static_categories_in_db`: **PASS** (0 filas insertadas en `mri_categories` tras fallo).
- `test_ripley_normalize_derives_only_from_real_items`: **PASS** (Categorías derivadas solo de items reales).
- `test_ripley_static_data_elimination_unit`: **PASS** (0 publicaciones, 0 entidades para entrada vacía).
- `test_ripley_waf_versus_technical_failure_classification`: **PASS** (Distinción WAF -> SOURCE_BLOCKED vs error técnico -> PARTIAL).

**Resultado total: 9 tests, 0 failures, 0 errors (OK).**

---

## 4. REGISTRO DE INTEGRIDAD Y ROLLBACK

- **Punto base garantizado:** `0f523321bd745a8928367379d102358e711ab7f8`
- **Procedimiento de Rollback:**
  En caso de requerir reversión completa a la base de partida:
  ```bash
  git checkout fix/mri-022-final-integrity
  git reset --hard 0f523321bd745a8928367379d102358e711ab7f8
  ```
- **Hashes de Archivos Protegidos:**
  - `data/sqlite/visibility.db`: `05450b3d938eae5fa799ea77b9ac38ad513c93d0cb2487535b90fe6d6ba87ed3`
  - `data/mri_experience.db`: `3fe09cff9489acb1530c340db82ad2679430ab24a8de7f8fabc3c5feb75efcb8`
  - `data/experience.db`: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
  - `data/mri_history.json`: `16f57fe895c262d09c3f754be4b0fed9086afe3feaa37220eff76306d4b81fde`
  - `data/mri_categories.json`: `b805f3b5659cc64c0ededa878c9c244eb699233bc1646e3e89ee1315bd138233`
  - Diff con producción (`app/auditor/`, `app/scrapers/`, `app/core/`, `app/dashboard/`): **CERO DIFERENCIAS**.
