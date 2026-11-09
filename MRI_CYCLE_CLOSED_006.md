# MRI_CYCLE_CLOSED_006 — Cierre oficial del ciclo MRI-005

**Fecha:** 2026-11-09 · **Estado:** CERRADO (commit + push realizados)
**Rama de código:** `integration/mri-deepseek-closure`
**Rama de informe/limpieza:** `fix/mri-022-relational-recovery`

---

## 1. Hitos alcanzados

```text
VERIFIED_ROUTES_MODE_EXECUTED=YES
NEW_VERIFIED_KNOWLEDGE=2 rutas / 80 publicaciones observadas / 2 evidencias
FALSE_NEGATIVE_FIXED=YES
CAPABILITY_HEALTH=VALIDATED (Paris cdp + har), NO BLOCKED
```

- **Run real:** `run_mri_audit_verified_routes_1794229028` (`AUDIT_VERIFIED_ROUTES / Paris / TOP_N=2`).
- Rutas: `exp_85` `...Abrigos` (40 pubs, `ev_7a018bc7794a37fd`) y
  `exp_87` `...Blusas` (40 pubs, `ev_56b13067e07cf4de`); ambas **FOUND**,
  `strategy_selected == strategy_executed`, evidencia en `mri_evidence_ledger`.
- Aprendizaje: la 2.ª ruta leyó la evidencia de la 1.ª (`paris_cdp… success_count=1`);
  el fallo de una ruta ya no degrada la capacidad (prueba aislada: ruta mala 3 fallos →
  `ROUTE_SKIPPED`, ruta buena FOUND 4/4, capacidad `success=4 failure=0 VALIDATED`).

## 2. Commits y push

| Commit | Rama | Contenido | Push |
|---|---|---|---|
| **`9f0b44568b045a24cc7cc5ca1c722565d88083cc`** | `integration/mri-deepseek-closure` | `capability_registry.py`, `verified_routes_audit.py` (código MRI-005) | ✅ `origin/integration/mri-deepseek-closure` |
| **`e0ed481668c4e3ae96fe89192e2b7d158b79cfd4`** | `fix/mri-022-relational-recovery` | `MRI_ROUTE_HEALTH_SEPARATION_FINAL_005_REPORT.md`, `experiments/mri_route_health_separation_005/*` | ✅ `origin/fix/mri-022-relational-recovery` |
| `8f14b9e` (previo) | `fix/mri-022-relational-recovery` | limpieza Fase 1/2 (evidence/outputs, .gitignore) | ✅ (ya estaba) |

Verificación remota:

```text
e0ed481…  refs/heads/fix/mri-022-relational-recovery
9f0b445…  refs/heads/integration/mri-deepseek-closure
```

URLs:

- https://github.com/ApolinarCastro/Visual-Auditor/tree/integration/mri-deepseek-closure
- https://github.com/ApolinarCastro/Visual-Auditor/tree/fix/mri-022-relational-recovery

### Nota estructural importante

`_integration/` es un **git worktree enlazado** de la misma repo (gitdir
`.git/worktrees/_integration`, rama `integration/mri-deepseek-closure`). El branch padre
`fix/mri-022-relational-recovery` no puede contener archivos dentro de un worktree ajeno sin
convertirlo en submódulo o reestructurar el repo. Por eso:

- el **código servido** se commiteó y pusheó en `integration/mri-deepseek-closure` (9f0b445);
- el **informe y experimentos** se commiteó y pusheó en `fix/mri-022-relational-recovery` (e0ed481).

Ambas ramas están en GitHub y DSH puede leerlas. No se forzó una reescritura de árbol ni un
submódulo para no corromper la estructura.

## 3. Estado del repositorio

- **Limpieza Fase 1/2:** `evidence/` y `outputs/` desafectados de Git (390 archivos; siguen en
  disco), `.gitignore` ampliado, 409 temporales/cachés/logs eliminados, 8 directorios legacy
  movidos a `C:\Users\ASUS Zenbook\Documents\_MRI_ARCHIVE_20261109\` (611.9 MB) sin borrar backups.
- **Working tree:** no queda “limpio” en sentido estricto: el padre conserva 313 entradas
  (modificaciones legacy de `app/`, documentación no versionada) y el worktree servido conserva 137
  modificaciones previas no relacionadas con MRI-005. **No se tocaron** en este ciclo.
- **Código de MRI-005:** dos archivos versionados/commiteados en el worktree; `mri_runner.py` intacto.

## 4. Núcleo

- `py_compile` de `mri_runner.py`, `verified_routes_audit.py`, `capability_registry.py`: **exit 0**.
- Hashes de los archivos críticos verificados antes/después de la limpieza (Fase 1). El cambio de
  MRI-005 en `verified_routes_audit.py`/`capability_registry.py` es intencional y está commiteado;
  `mri_runner.py`, scrapers y launchers no se modificaron.
- SQLite de producción sin filas del run real; la evidencia está en la base operativa.

## 5. Deuda técnica documentada

Ver [MRI_TEST_DEBT_006.md](MRI_TEST_DEBT_006.md):

1. Contaminación de imports en suite combinada (`app/` raíz vs `_integration/app`).
2. Baseline de hash de `data/sqlite/visibility.db` desactualizado.

**Impacto:** ninguno en producción; deuda de tests.

## 6. Próxima prioridad

Ejecutar una auditoría más amplia (`TOP_N > 2`) en los cuatro marketplaces para producir cobertura
comercial real, partiendo de esta base ya separada (capacidad vs ruta) y con la suite de tests
saneada.

## Conclusión

El ciclo MRI-005 se declara **cerrado oficialmente**: corrección estructural, ejecución real con
evidencia, commit y push verificados, deuda de tests documentada y núcleo intacto.
