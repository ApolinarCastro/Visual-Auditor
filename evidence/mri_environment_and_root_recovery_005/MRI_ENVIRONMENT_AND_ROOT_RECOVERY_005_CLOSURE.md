# MRI ENVIRONMENT AND ROOT RECOVERY 005 — CLOSURE

**Task:** `MRI-ENVIRONMENT-AND-ROOT-RECOVERY-005`  
**Mode:** DELIMITED CORRECTION → VERIFICATION → PARTIAL LIVE AUDITS  
**Branch:** `integration/mri-deepseek-closure`  
**HEAD:** `089548b6849d`  
**Date:** 2026-11-02  
**Git commits/pushes:** 0  

---

## 1. Resultado

```text
FINAL_STATUS=ENVIRONMENT_BLOCKED
```

La raíz Falabella quedó resuelta y persistida. Playwright sigue bloqueado en la sesión DSH y no hay una consola interactiva del operador disponible desde esta sesión; por eso Mercado Libre, Ripley y Paris no pueden completarse.

---

## 2. CP0 — Estado

```text
MIGRATION_V1=PASS
version=1
checksum=a60bdd293fc43d8ede4ae402c934db27087a9da489b7e6f5f45e780fb0baa22e
integrity_check=ok
mri_categories=113
```

No se repitió la migración ni se cambió el esquema.

---

## 3. CP1 — Playwright

### Estado

```text
PLAYWRIGHT_INTERACTIVE=NOT_EXECUTED
PLAYWRIGHT_DSH=BLOCKED
```

No existe una consola interactiva del operador accesible desde esta sesión. La ejecución directa en DSH ya demostró el fallo:

```text
async_playwright().start()
→ asyncio.create_subprocess_exec
→ windows_utils.pipe
→ _winapi.CreateFile
PermissionError: [WinError 5] Acceso denegado
```

El mismo error aparece en el servidor lanzado en segundo plano y en una ejecución directa, por lo que no es un defecto de un marketplace ni de un scraper.

### Procedimiento correcto

Ejecutar desde la consola interactiva del operador:

```text
lanzar_mri_dashboard.bat
```

No desde un job confinado de DSH.

No se modificaron ACL, antivirus, políticas de seguridad ni scrapers.

---

## 4. CP2 — Raíz Falabella

### Fuente verificada

La página SSR raíz de Falabella expone enlaces comerciales reales:

```text
/falabella-cl/category/cat20002/Moda-Mujer
/falabella-cl/category/cat850068/Zapatillas-Mujer
/falabella-cl/category/cat1320008/Moda-Hombre
...
```

Se adaptó `discover_falabella_roots()` para extraer:

```text
category_id
category_name
canonical_url
source=SSR_ROOT_CATEGORY_LINKS
parent_category_id=NULL
discovery_status=NOT_VERIFIED
```

No se inventaron padres ni jerarquías a partir de slugs.

### Persistencia live

```text
taxonomy_nodes=813
roots=813
edges=0
leaves=813
frontier_pending=813
source=SSR_ROOT_CATEGORY_LINKS
```

La persistencia fue registrada en:

```text
mri_taxonomy_nodes
mri_taxonomy_node_history
mri_taxonomy_frontier_summary
```

### Límite

La página raíz demuestra **nodos raíz**, no la jerarquía completa. Los 813 nodos quedan con padre `NULL` y estado `NOT_VERIFIED` hasta disponer de evidencia de subcategorías.

```text
FALABELLA_ROOT_SOURCE=VERIFIED
FALABELLA_ROOT_PERSISTENCE=PASS
```

---

## 5. CP3 — Pruebas

```text
tests/test_taxonomy_foundation_001.py
tests/test_root_taxonomy_002.py
15 passed in 1.12s
```

Incluye la prueba:

```text
test_falabella_special_route_executes_and_persists
```

Regresión focalizada:

```text
tests/test_live_runtime_fix_001.py
tests/test_guarded_dispatch.py
tests/test_build_instance_cleanup.py
12 passed in 35.25s
```

---

## 6. CP4 — Auditorías

### Falabella

```text
RUN: run_mri_discovery_1793649298
Outcome: PARTIAL
Aceptación: AUDIT_FAIL
Publicaciones nuevas: 405
Raíces persistidas: 813
```

La corrida anterior conserva 406 publicaciones históricas; no se sustituyeron ni se inventaron conteos.

Causa del AUDIT_FAIL:

```text
taxonomía raíz descubierta pero jerarquía/subcategorías no demostradas;
cobertura global no certificada.
```

### Mercado Libre

```text
RUN: run_mri_discovery_1793647220
Outcome: EXTRACTOR_FAILURE
Publicaciones: 0
Causa: BROWSER_LAUNCH_FAILED / WinError 5
```

```text
MELI_AUDIT=BLOCKED
```

### Ripley

```text
RIPLEY_AUDIT=NOT_EXECUTED
```

No se ejecutó porque Playwright está bloqueado.

### Paris

```text
RUN: run_mri_discovery_1793649694
Outcome: EXTRACTOR_FAILURE
Publicaciones: 0
Causa: BROWSER_LAUNCH_FAILED / WinError 5
```

```text
PARIS_AUDIT=BLOCKED
```

El baseline Legacy de Paris no fue modificado.

---

## 7. Integridad final

```text
SQLITE_INTEGRITY=PASS
mri_categories=113
mri_taxonomy_nodes=813
mri_taxonomy_frontier_summary=1
```

No se perdieron datos históricos ni se alteró Paris Legacy.

---

## 8. Contrato final

```text
TASK=MRI-ENVIRONMENT-AND-ROOT-RECOVERY-005

PLAYWRIGHT_INTERACTIVE=NOT_EXECUTED
PLAYWRIGHT_DSH=BLOCKED
FALABELLA_ROOT_SOURCE=VERIFIED
FALABELLA_ROOT_PERSISTENCE=PASS

FALABELLA_AUDIT=FAIL
MELI_AUDIT=BLOCKED
RIPLEY_AUDIT=NOT_EXECUTED
PARIS_AUDIT=BLOCKED

SQLITE_INTEGRITY=PASS
LEGACY_REGRESSION=PASS
PARIS_BASELINE=PASS

GIT_COMMITS=0
GIT_PUSHES=0

FINAL_STATUS=ENVIRONMENT_BLOCKED
```

No se declara `AUDIT_PASS` ni `FULL_AUDIT_VERIFIED`.

---

## 9. Próxima acción

1. Iniciar MRI desde una consola interactiva del operador para habilitar Playwright.
2. Ejecutar Mercado Libre, Ripley y Paris completos.
3. Extender Falabella desde nodos raíz a subcategorías con una fuente verificable.
4. Reconciliar taxonomía, publicaciones, posiciones y checkpoints.
