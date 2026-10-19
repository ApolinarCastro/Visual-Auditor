# MRI_RUN_CATEGORY_ISOLATION_022_DELIVERY.md
**Misión:** MRI-022 — CIERRE DEL DEFECTO A/B  
**Ejecutor:** ANTIGRAVITY  
**Auditor:** CODEX  
**Fuente:** `MRI_CODEX_INDEPENDENT_GATE_025.md`  
**Base:** `c7ce7e8bb702b4c0cdd4943b33eac13bf29d4c2e`  
**Rama:** `fix/mri-run-category-isolation-022`  
**Fecha:** 2026-10-19  

---

## 1. Declaración de Alcance y Cierre de Defecto

En estricto cumplimiento de la directiva de misión:
1. **Defecto resuelto:** Contaminación cruzada de categorías entre corridas históricas y activas (contraejemplo A/B de Codex en `evidence/mri_codex_independent_gate_025/`).
2. **Sin ampliación innecesaria:** No se rediseñó la persistencia completa, no se modificaron archivos fuera de `app/mri_dashboard/mri_api.py`, y no se alteró la producción.
3. **No declaración de aprobación global:** Se reconoce explícitamente que las constantes comerciales de Ripley y el modelo de estados multimarketplace permanecen abiertos según lo observado por Codex. Se solicita a Codex **únicamente la comprobación de este defecto**.

---

## 2. Causa Raíz y Corrección Quirúrgica

### Causa Raíz
En `app/mri_dashboard/mri_api.py`, la consulta de conteo de categorías por marketplace (`get_multimarketplace_summary`) realizaba una unión (`JOIN`) por `publication_id` combinando `mri_publication_categories` con publicaciones filtradas por corrida (`WHERE run_id = ?`). Debido a que `mri_publication_categories` solo almacena el estado activo actual sin columna `run_id`, cuando una misma publicación existía en una corrida histórica `AUDIT_A` y una corrida activa posterior `AUDIT_B`, la categoría activa de `AUDIT_B` (`CAT_B`) se asociaba a la publicación histórica de `AUDIT_A`, resultando en `categories_count = 2` en lugar de `1`.

Similarmente, en `fetch_run_publications`, la consulta histórica `hist_cat_query` no validaba la relación unívoca con `mri_historical_publications` por corrida.

### Corrección Quirúrgica (`app/mri_dashboard/mri_api.py`)
1. **Delimitación estricta de categorías activas:** La rama de `mri_publication_categories` solo se incluye si la corrida solicitada posee publicaciones activas en `mri_publications`, y se une estrictamente por `p.run_id = target_run_id AND p.publication_id = pc.publication_id AND pc.status = 'ACTIVE'`.
2. **Delimitación estricta de categorías históricas:** La rama histórica se une a `mri_historical_publications hp` mediante `hpc.publication_id = hp.publication_id AND hpc.run_id = hp.run_id WHERE hp.run_id = ?`.
3. **Aislamiento total:** Ninguna pertenencia activa de otra corrida se filtra en una corrida histórica, y una corrida inexistente (`AUDIT_UNKNOWN`) devuelve 0 categorías.

---

## 3. Criterio de Aceptación Verificado

Ejecución del contraejemplo reproducible de Codex en base SQLite aislada:

```text
AUDIT_A:
  categories_count = 1
  categories = [MELI_CAT_CAT_A]
  brand_publications = 1
  status = BLOCKED

AUDIT_B:
  categories_count = 1
  categories = [MELI_CAT_CAT_B]
  brand_publications = 1
  status = BLOCKED

AUDIT_UNKNOWN:
  categories_count = 0
  categories = []
  brand_publications = 0
  status = NOT_EXECUTED
```

---

## 4. Preservación de Evidencias y Producción

- **Observaciones originales:** 2.533
- **Hash de observaciones:** `c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b`
- **Integrity check:** `ok`
- **Foreign keys check:** `[]`
- **Archivos protegidos:** Hashes SHA-256 idénticos antes y después.
  - `data/sqlite/visibility.db`: `1e570a8c8198881438236126ecf27042a44fb9420e2a70574d5c52df0296440f`
  - `data/mri_experience.db`: `3fe09cff9489acb1530c340db82ad2679430ab24a8de7f8fabc3c5feb75efcb8`
  - `data/experience.db`: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
  - `data/mri_history.json`: `16f57fe895c262d09c3f754be4b0fed9086afe3feaa37220eff76306d4b81fde`
  - `data/mri_categories.json`: `b805f3b5659cc64c0ededa878c9c244eb699233bc1646e3e89ee1315bd138233`
