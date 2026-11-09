# MRI_TEST_DEBT_006 — Deuda técnica de la suite (no bloqueante)

**Fecha:** 2026-11-09 · **Estado:** documentada, no corregida (fuera del alcance de MRI-005/006)

## 1. Contaminación de imports en ejecución combinada (`sys.modules['app']`)

- **Síntoma:** `test_module_origins_are_served_tree` y `test_zero_publication_evidence_idempotent`
  fallan solo cuando se ejecutan junto a otros tests; pasan aislados.
- **Causa:** `app/` raíz (copia legacy) y `_integration/app/` comparten el mismo namespace `app`;
  el primero que se importa queda en `sys.modules` y las pruebas posteriores resuelven el árbol
  equivocado. `_integration` además es un **git worktree** enlazado, no un paquete bajo el padre.
- **Propuesta:** marcar `app/` raíz como legacy y excluirlo de la suite; o añadir un `conftest.py`
  que limpie `sys.modules` (`app` y subpaquetes) entre sesiones y fije `sys.path[0]` a
  `_integration` en las pruebas del árbol servido.
- **Evidencia:** ejecución combinada `24 passed, 3 failed`; ejecución individual de los dos tests
  de import: **passed**.

## 2. Baseline de hash desactualizado (`data/sqlite/visibility.db`)

- **Síntoma:** `test_production_sqlite_hashes_unchanged` falla porque el hash actual
  (`2ea4310b8e14c768170705484ba8be79481b476c28b43fccecd0ff0209a2215f`) no coincide con la
  constante histórica `4f2f976b09d2c227564c5eaaa6484b21d7c620362e2c7c3aa71264825b98e536`.
- **Verificación:** la corrida real de MRI-005 (`run_mri_audit_verified_routes_1794229028`) **no
  insertó filas en la base de producción** (0 filas en `mri_runs`/`mri_publications` para ese
  `run_id`); la persistencia fue a `data/sqlite/mri_operational/visibility.db`. Por tanto el cambio
  de hash no proviene de esta corrida.
- **Propuesta:** actualizar el baseline con el hash actual (previa revisión del flujo que escribió
  producción) o marcar el test `xfail` con razón documentada hasta que se audite ese flujo.
- **Impacto:** ninguno en producción; es una aserción de test desactualizada.

## Impacto

Ninguno en producción. Ambos puntos son deuda de la **suite de tests**, no defectos funcionales de
MRI-005. Deben abordarse en una tarea de saneamiento de tests antes de exigir una suite 100% verde.
