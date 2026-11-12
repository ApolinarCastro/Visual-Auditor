# MRI TAXONOMY FOUNDATION 001 — CLOSURE

**Task:** `MRI-TAXONOMY-FOUNDATION-001`  
**Mode:** IMPLEMENT → TEST → VERIFY  
**Branch:** `integration/mri-deepseek-closure`  
**HEAD:** `089548b6849d`  
**Date:** 2026-11-02  
**Production migration applied:** NO  
**Database mutations:** 0  
**Scraper executions:** 0  
**Commits/pushes:** 0  

---

## 1. Resultado ejecutivo

```text
SCHEMA_MIGRATION=TESTED
PRODUCTION_MIGRATION=NOT_AUTHORIZED
TAXONOMY_DISCOVERY=PARTIAL
HIERARCHY_PERSISTENCE=PASS
FRONTIER_TRACKING=PASS
CATEGORY_OBSERVATION=PARTIAL
AUTONOMOUS_LEARNING=PARTIAL

FINAL_STATUS=READY_FOR_MIGRATION_APPROVAL
```

Se implementó una migración aditiva, versionada, transaccional e idempotente, y una capa de persistencia de jerarquía/frontera/aprendizaje.

No se aplicó a la SQLite operativa.

---

## 2. CP0 — Estado previo y consumidores

### Repositorio

```text
worktree: _integration
rama: integration/mri-deepseek-closure
HEAD: 089548b6849d
```

El worktree ya tenía cambios preexistentes; no se revirtió ninguno.

### Esquema real de `mri_categories`

```text
category_id TEXT (PK)
marketplace TEXT NOT NULL
category_name TEXT NOT NULL
canonical_url TEXT
created_at TEXT NOT NULL
```

```text
foreign keys: ninguna
índices propios: solo PK
filas: 113
```

Consumidores principales:

```text
mri_api.py
mri_read_model.py
category_alignment.py
recovery_runner.py
falabella_ssr_engine.py
meli_taxonomy_engine.py
riplea_paris_engine.py
ripley_commercial_engine.py
mri_foundation.py
```

La migración **no altera** `mri_categories`; crea tablas nuevas y conserva todos los consumidores.

### StorageGuard

```text
StorageConfig.assert_write_allowed()
StorageConfig.ensure_writable()
```

La persistencia de producción no se ejecutó. La prueba de compatibilidad se hizo sobre una copia.

---

## 3. CP1 — Migración implementada

Archivo:

```text
app/mri_autonomous/taxonomy_store.py
```

### Versión

```text
TAXONOMY_SCHEMA_VERSION=1
```

### Tablas aditivas

**`mri_taxonomy_nodes`**

```text
marketplace
category_id
category_name
parent_category_id
hierarchical_path
canonical_url
taxonomy_source
source_evidence
discovered_at
last_verified_at
discovery_status
run_id
```

Primary key:

```text
(marketplace, category_id)
```

Foreign key compuesta:

```text
(parent_category_id, marketplace)
→ (category_id, marketplace)
```

Esto impide mezclar un padre de otro marketplace.

**`mri_taxonomy_node_history`**

Conserva cada snapshot por `(marketplace, category_id, run_id)` sin borrar historia.

**`mri_taxonomy_frontier_summary`**

```text
roots_discovered
nodes_discovered
edges_verified
leaves_discovered
frontier_pending
frontier_blocked
frontier_exhausted
source_completeness
```

**`mri_taxonomy_learning`**

```text
knowledge_id
marketplace
knowledge_type
observation
source_evidence
first_seen
last_verified
confidence
validation_status
supersedes
```

**`mri_taxonomy_schema_migrations`**

Versión, fecha y checksum del esquema.

### Garantías

- `CREATE TABLE IF NOT EXISTS`.
- migración dentro de una transacción.
- checksum de versión.
- idempotente.
- no hace `DROP`, `DELETE` ni `ALTER` de tablas existentes.
- no inventa padres: padre desconocido queda `NULL` y `NOT_VERIFIED`.
- detecta ciclos y padres de otro marketplace.

---

## 4. CP2 — Descubrimiento autónomo

No se cambió el mecanismo de descubrimiento de raíz en este ciclo.

Estado real:

| Marketplace | Fuente actual | Estado |
|---|---|---|
| Falabella | Catálogo SSR de marca + facetas | PARTIAL |
| Mercado Libre | Storefront + expansión de categorías | PARTIAL |
| Ripley | URLs de navegación observadas | PARTIAL |
| Paris | `NOT_REQUIRED`; solo Legacy search | FAIL |

### Limitación reconocida

La migración permite **persistir** una jerarquía auténtica cuando el adaptador la entregue, pero no convierte una búsqueda de marca en una taxonomía raíz.

No se añadieron slugs como padres ni relaciones inferidas.

---

## 5. CP3 — Frontera y exhaustividad

La tabla `mri_taxonomy_frontier_summary` se calcula desde el snapshot persistido:

```text
roots_discovered
nodes_discovered
edges_verified
leaves_discovered
frontier_pending
frontier_blocked
frontier_exhausted
source_completeness=NOT_VERIFIED
```

Reglas implementadas:

```text
TAXONOMY_DISCOVERED ≠ TAXONOMY_COMPLETE
SOURCE_BLOCKED ≠ NOT_FOUND
una categoría con 0 publicaciones sigue siendo un nodo
los estados pendientes/bloqueados no se convierten en ausencia
```

La persistencia no permite declarar `source_completeness=VERIFIED` automáticamente.

---

## 6. CP4 — Conexión con el recorrido

Se añadió al runner, después del descubrimiento de taxonomía, una persistencia aislada:

```text
StorageConfig.get_sqlite_path()
→ persist_taxonomy_result()
→ StorageGuard.assert_write_allowed()
→ mri_taxonomy_nodes + history + frontier
```

Si StorageGuard no autoriza, el runner registra:

```text
taxonomy_persistence[mkt] = NOT_RECORDED
```

y no corrompe la auditoría. Esta integración no se validó live porque no hay servidor.

La taxonomía observada sigue usando los motores existentes; no se creó un crawler nuevo.

---

## 7. CP5 — Aprendizaje

Se implementó `record_taxonomy_learning()` sobre `mri_taxonomy_learning`.

Contrato:

```text
confidence=OBSERVED
validation_status=NOT_VERIFIED
```

No se promovió ninguna observación a regla operativa.

La tabla `recovery_experiences` existente no se modificó.

---

## 8. CP6 — Pruebas ejecutadas

### Suite determinista

Archivo:

```text
tests/test_taxonomy_foundation_001.py
```

Comando:

```powershell
python -m pytest tests/test_taxonomy_foundation_001.py -q \
  -p no:cacheprovider \
  --basetemp evidence_local_validation/pytest_taxonomy_foundation_001
```

Resultado:

```text
8 passed in 1.75s
```

Cobertura:

```text
migración idempotente
preservación de mri_categories
copia de DB operativa sin cambios
jerarquía padre-hijo
rechazo de padre cross-marketplace
rechazo de ciclos
historial sin pérdida en repetición
frontera y aprendizaje
compatibilidad de esquema del consumidor
```

### Regresión focalizada

```powershell
python -m pytest tests/test_live_runtime_fix_001.py ^
  tests/test_guarded_dispatch.py ^
  tests/test_build_instance_cleanup.py -q
```

Resultado:

```text
12 passed in 48.21s
```

### Pytest environment

El `WinError 5` de sesiones anteriores no bloqueó esta suite usando `--basetemp` dentro de `evidence_local_validation`.

No se declara PASS de la suite relacional histórica: sigue en `BLOCKED_ENVIRONMENT` por el defecto de directorio temporal ya documentado.

---

## 9. CP7 — Validación funcional

```text
Servidor 8055: sin listener
Autenticación/version: no comprobables
Auditoría concurrente: ninguna
Migración operativa: NO aplicada
Autorización: NO otorgada
```

Auditorías:

```text
FALABELLA_AUDIT=NOT_EXECUTED
MELI_AUDIT=NOT_EXECUTED
RIPLEY_AUDIT=NOT_EXECUTED
PARIS_AUDIT=NOT_EXECUTED
```

No se usaron canaries ni muestras como aceptación.

---

## 10. Integridad y riesgos

```text
SQLITE_INTEGRITY=PASS
LEGACY_REGRESSION=PASS (12/12 focalizada)
PARIS_BASELINE=PASS (sin cambios)
DATABASE_MUTATIONS=0
```

### Riesgos

1. La migración crea tablas nuevas; la aplicación requiere autorización explícita y respaldo.
2. El runner registra fallos de persistencia de taxonomía sin abortar la adquisición; una auditoría con persistencia fallida debe permanecer `PARTIAL/FAIL`, no `PASS`.
3. Falabella/ML siguen partiendo de superficies de marca; la migración no corrige esa fuente.
4. Paris sigue sin descubrimiento MRI.
5. La suite relacional histórica continúa bloqueada por el entorno temporal.

---

## 11. Plan de migración propuesto

No ejecutado.

1. Backup físico:

```text
data/sqlite/mri_operational/visibility.db
→ backup/mri_operational_pre_taxonomy_001.db
```

2. Registrar SHA256 del backup y de la DB original.
3. Ejecutar `apply_taxonomy_migration()` sobre la DB autorizada.
4. Verificar:

```text
PRAGMA integrity_check = ok
mri_categories count unchanged
mri_taxonomy_schema_migrations version=1
mri_taxonomy_nodes exists
mri_taxonomy_node_history exists
mri_taxonomy_frontier_summary exists
```

5. Reversión: restaurar el backup físico; las tablas nuevas no afectan a `mri_categories`.

---

## 12. Archivos modificados/nuevos

Producción:

```text
app/mri_autonomous/taxonomy_store.py   (nuevo)
app/mri_dashboard/mri_runner.py        (integración de persistencia)
```

Pruebas:

```text
tests/test_taxonomy_foundation_001.py
```

Evidencia:

```text
_integration/evidence/mri_taxonomy_foundation_001/MRI_TAXONOMY_FOUNDATION_001_CLOSURE.md
```

---

## 13. Contrato final

```text
TASK=MRI-TAXONOMY-FOUNDATION-001

SCHEMA_MIGRATION=TESTED
PRODUCTION_MIGRATION=NOT_AUTHORIZED
TAXONOMY_DISCOVERY=PARTIAL
HIERARCHY_PERSISTENCE=PASS
FRONTIER_TRACKING=PASS
CATEGORY_OBSERVATION=PARTIAL
AUTONOMOUS_LEARNING=PARTIAL

FALABELLA_AUDIT=NOT_EXECUTED
MELI_AUDIT=NOT_EXECUTED
RIPLEY_AUDIT=NOT_EXECUTED
PARIS_AUDIT=NOT_EXECUTED

SQLITE_INTEGRITY=PASS
LEGACY_REGRESSION=PASS
PARIS_BASELINE=PASS

PRODUCTION_FILES_CHANGED=2
DATABASE_MUTATIONS=0
GIT_COMMITS=0
GIT_PUSHES=0

FINAL_STATUS=READY_FOR_MIGRATION_APPROVAL
```

No se declara `FULL_AUDIT_VERIFIED`: falta la autorización de migración y las cuatro auditorías completas.

### Próxima acción exacta

Aprobar la migración con respaldo y luego ejecutar:

```text
Falabella → Mercado Libre → Ripley → Paris
```

con descubrimiento desde raíz, persistencia jerárquica y validación de frontera.
