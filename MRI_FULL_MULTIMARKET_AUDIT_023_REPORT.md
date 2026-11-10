# MRI_FULL_MULTIMARKET_AUDIT_023_REPORT

**Tarea:** MRI-FULL-MULTIMARKET-AUDIT-023 · **Fecha:** 2026-11-10
**Run:** `run_mri_discovery_1794316991`
**Estrategia:** `ALL_PARALLEL_HTTP_FIRST`
**Resultado:** auditoría completa de los 4 marketplaces **sin navegadores**, 1 101 publicaciones
persistidas, memoria mínima **1 629 MB**. Estable, pero no siempre >2 GB.

---

## 1. Ejecución

```text
Inicio:  2026-11-10 10:23:12
Fin:     2026-11-10 10:27:51 (Falabella); estado final 10:28:07
Duración total: ~4 min 55 s
execution_strategy=ALL_PARALLEL_HTTP_FIRST
navigators=0
```

## 2. Resultados por marketplace

| Marketplace | Estado | Publicaciones | Inicio → fin | Duración |
|---|---|---|---:|---:|
| **Paris** | **FOUND** | **400** | 10:23:14 → 10:23:28 | 14.4 s |
| **Mercado Libre** | **FOUND** | **39** | 10:23:12 → 10:23:41 | 28.3 s |
| **Ripley** | **FOUND** | **258** | 10:23:53 → 10:24:18 | 25.1 s |
| **Falabella** | **PARTIAL** | **1 315** (checkpoint SSR) | 10:23:40 → 10:27:51 | 4 min 11 s |
| **Persistido** | | **1 101 publications + 1 101 edges** | | |

- `mri_runs`: París/ML/Ripley `FOUND/SUCCESS`; Falabella `PARTIAL/SUCCESS`.
- `mri_evidence_ledger`: **0 filas**; la evidencia quedó en `mri_publications` y
  `mri_publication_categories` (1 101/1 101, sin nulos).
- Checkpoints HTTP de Paris/Ripley/ML: `INCOMPLETE` (paginación no emite coverage por categoría);
  Falabella sí tiene checkpoint completo (80 páginas, 14 categorías, 1 315 pubs).
- Diferencia 1 315 checkpoint vs 1 101 persistido: deduplicación/edges de Falabella al materializar.

## 3. Memoria

| Momento | Memoria libre |
|---|---:|
| Antes del ALL | 3 838 MB |
| Mínimo durante la ejecución | **1 629 MB** |
| Al finalizar | 4 197 MB |
| Dashboard cerrado | 4 338 MB |

- **Siempre >1 GB.**
- **No siempre >2 GB**: el mínimo fue 1 629 MB, por debajo del objetivo de 2 GB.
- Sin navegadores: todo el consumo es HTTP + SQLite + proceso dashboard.

## 4. Navegadores y SQLite

```text
navigators=0
Chrome/Playwright MRI=0 procesos
database is locked=0
PRAGMA integrity_check=ok
```

No se lanzó ningún navegador; Paris, Ripley y ML usaron HTTP y Falabella SSR.

## 5. Límite de Mercado Libre

- **39 productos** desde `https://www.mercadolibre.cl/tienda/nicopoly`.
- `?page=2` y `?_Desde_=49` son ignorados por el storefront.
- `api.mercadolibre.com/sites/MLC/search` devuelve **403** sin token.
- `listado.mercadolibre.cl` requiere verificación humana → no se fuerza.
- **Recomendación:** obtener token/API oficial o endpoint interno autenticado para superar 39.

## 6. Conclusión

| Pregunta | Respuesta |
|---|---|
| ¿Auditoría completa de 4? | **SÍ** (FOUND/PARTIAL, sin navegador) |
| ¿Estable? | **SÍ**, sin locks ni corrupción |
| ¿Rápida? | **SÍ**, ~5 min total; Paris/Ripley/ML en <30 s |
| ¿Ligera? | **SÍ**; mínimo 1 629 MB, siempre >1 GB |
| ¿Memoria >2 GB? | **NO en el mínimo** (1 629 MB) |
| ¿Configuración por defecto? | **SÍ para HTTP-first** con la salvedad de memoria >1 GB, no 2 GB |
| ¿ML cobertura completa? | **NO**; límite 39 por API sin token |

**Veredicto:** el modo HTTP-first es estable, rápido y ligero para los 4 marketplaces. Cumple
>1 GB y funciona en 8 GB, pero no cumple el objetivo estricto >2 GB en esta máquina; ML requiere
token/API para cobertura completa.

## 7. Estado

```text
RUN=run_mri_discovery_1794316991
STRATEGY=ALL_PARALLEL_HTTP_FIRST
PUBLICATIONS=1101
EDGES=1101
NAVIGATORS=0
DB_LOCKED=0
INTEGRITY=ok
MEMORY_MIN=1629 MB
DASHBOARD=STOPPED
PORT_8055=FREE
LOCK=NONE
```
