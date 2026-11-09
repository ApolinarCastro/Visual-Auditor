# MRI_STRICT_AUTONOMY_008_REPORT

**Tarea:** MRI-STRICT-AUTONOMY-008 · **Fecha:** 2026-11-09
**Árbol:** `_integration/` · **GIT_COMMITS=0 · GIT_PUSHES=0** (cambios sin commit, a la espera de validación)

---

## 1. Cambio en `verified_routes_audit.py` (fallback condicionado)

```diff
  experience_source = "ExperienceStore"
+ strict_autonomy = str(os.getenv("MRI_STRICT_AUTONOMY", "")).lower() in ("1","true","yes")
  if sum(len(v) for v in rows_by_market.values()) == 0:
-     # ... lectura read-only de data/mri_experience.db ...
+     if strict_autonomy:
+         experience_source = "STRICT_AUTONOMY_NO_EXTERNAL_READ"
+     else:
+         # ... lectura read-only histórica (comportamiento anterior) ...
...
  if strict_autonomy and total_selected == 0:
      selection_reason = ("NO_ROUTES_FOUND: strict autonomy prohibits external experience "
                          "reads; run DISCOVERY first to populate MRI's own store")
```

También se añadió `strict_autonomy`/`selection_reason` a la vista previa. **`mri_runner.py` no se tocó.**

Verificación con store vacío y `MRI_STRICT_AUTONOMY=true`:

```json
{
  "routes_available": 0,
  "routes_eligible": 0,
  "routes_selected": 0,
  "experience_source": "STRICT_AUTONOMY_NO_EXTERNAL_READ",
  "selection_reason": "NO_ROUTES_FOUND: strict autonomy prohibits external experience reads; run DISCOVERY first to populate MRI's own store"
}
```

No se leyó `data/mri_experience.db` ni ningún archivo de VA.

---

## 2. Descubrimiento propio (MRI, sin VA)

**Limitación de CLI documentada:** `_integration/run.py` **no expone** `--discovery` ni
`--audit-verified-routes` (solo comandos `audit`/`audit-all`). Por ello el ciclo se ejecutó
invocando los componentes reales de MRI en un entorno aislado:
`experiments/mri_strict_autonomy_008/run_strict_cycle.py`.

Descubrimiento: MRI obtuvo la navegación pública de `https://www.paris.cl/`, extrajo enlaces
internos y los clasificó con su propio `surface_classifier` (`COMMERCIAL_CATEGORY`/
`COMMERCIAL_SUBCATEGORY`). **138 rutas** clasificadas y persistidas como `CATEGORY` con
`discovery_method=MRI_STRICT_HTTP_NAV`, `status=LAST_GOOD`.

Primeras rutas descubiertas (5 de 138):

| id | URL |
|---|---|
| exp_1 | `https://www.paris.cl/mujer/moda/` |
| exp_2 | `https://www.paris.cl/mujer/moda/poleras-blusas/` |
| exp_3 | `https://www.paris.cl/mujer/moda/jeans-pantalones/` |
| exp_4 | `https://www.paris.cl/mujer/moda/vestidos-faldas/` |
| exp_5 | `https://www.paris.cl/mujer/moda/chaquetas-abrigos-parkas/` |

**Segunda ronda de descubrimiento (mismo store):**

```text
discovered=138  persisted=138  second_round_new=0  second_round_known=138
```

No re-descubrió ninguna ruta conocida: el conjunto ya persistido en el ExperienceStore aislado fue
respetado (0 nuevas). La prueba usa el store propio; no se consultó `ROUTE_STATE` de VA.

---

## 3. Auditoría de rutas descubiertas por MRI

`execute_verified_routes_audit` con `MRI_STRICT_AUTONOMY=true`, store aislado, `TOP_N=3`:

| route_id | URL descubierta | state | strategy_selected = executed | publicaciones | evidence_id |
|---|---|---|---|---|---|
| `exp_137` | `https://www.paris.cl/experiencias-y-servicios/gift-cards/moda/` | **FOUND** | `paris_cdp_constructor_discovery` | 40 | `ev_93c220eb149b83b3` |
| `exp_138` | `https://www.paris.cl/experiencias-y-servicios/gift-cards/tecnologia/` | **FOUND** | `paris_har_replay_fallback` | 40 | `ev_58fc86f53a2804da` |
| `exp_134` | `https://www.paris.cl/experiencias-y-servicios/tecnologia/` | **FOUND** | `paris_cdp_constructor_discovery` | 40 | `ev_7ad02315a29b1019` |

- Aceptación: `RUN_COMPLETED`, `SELECTED_ROUTES_COMPLETE`, **PASS**, 3/3 procesadas, 0 pendientes.
- `experience_source=ExperienceStore` (no fallback externo).
- Evidencia persistida: 3 filas `VALIDATED` en `mri_evidence_ledger`; 1 fila `mri_runs` SUCCESS/FOUND.
- `strategy_selected == strategy_executed` en las tres; la 2.ª y 3.ª leyeron la CAPABILITY persistida
  por la primera (aprendizaje entre rutas).

**Limitación de fidelidad:** el motor Paris `_paris_route_publications` usa `search(q=nicopoly)`
cuando la URL no lleva `tipoProductoAll`/`q`; por eso las 40 publicaciones de cada ruta son
resultados de búsqueda de marca, no un filtro exacto de la categoría descubierta. Las rutas y la
evidencia son reales, pero la cobertura por categoría queda **PARTIAL** hasta que el descubrimiento
genere rutas con filtros comerciales (`tipoProductoAll`) o el motor use el path de categoría.

---

## 4. SQLite aislada (solo datos de MRI)

`experiments/mri_strict_autonomy_008/sandbox/`:

- `mri_experience_isolated.db`: **138 CATEGORY** con `discovery_method=MRI_STRICT_HTTP_NAV`
  (las primeras 5 listadas arriba), 2 CAPABILITY (`paris_cdp…`, `paris_har…`), 3 ROUTE_STATE y
  3 DECISION_TRACE; `value` es la URL completa para evitar colisiones de nombre; **ninguna fila de VA**.
- `visibility.db`: 1 `mri_runs` (SUCCESS/FOUND) y 3 `mri_evidence_ledger` VALIDATED.
- Esquema copiado **solo como DDL** desde la base operativa (sin filas); no se leyó
  `data/mri_experience.db` (el flag estricto bloqueó el fallback).
- No se tocó la base operativa/producción ni archivos de VA.

---

## 5. Conclusión

```text
MRI_STRICT_AUTONOMY=VERIFIED (con limitaciones declaradas)
STRICT_FALLBACK_GATE=PASS
OWN_DISCOVERY=PASS (138 rutas desde paris.cl, 0 leídas de VA)
SECOND_DISCOVERY_NO_REDISCOVERY=PASS (new=0/known=138)
OWN_AUDIT=PASS (3/3 FOUND, 3 evidencias, acceptance PASS)
OWN_LEARNING=PASS (selection_reason/capability_evidence leídos del store propio)
VA_DATA_READ=NONE
PRODUCTION_DB_TOUCHED=NO
CLI_DISCOVERY_GAP=DOCUMENTED (run.py no expone --discovery/--audit-verified-routes)
ROUTE_CATEGORY_FIDELITY=PARTIAL (motor Paris usa búsqueda de marca para URLs sin filtros)
GIT_COMMITS=0 / GIT_PUSHES=0
```

**Deuda restante:**
1. Exponer en `run.py` los comandos `--discovery` / `--audit-verified-routes` o un wrapper oficial,
   para que el ciclo se ejecute sin scripts de experimento.
2. Hacer que el descubrimiento produzca rutas con filtros comerciales (`tipoProductoAll`) para que
   la auditoría sea category-specific, no una búsqueda de marca.
3. Commit/push de `verified_routes_audit.py` (condicionamiento estricto) tras validación.

**Limitación de método:** el descubrimiento se implementó con el HTTP fetch propio de MRI +
`surface_classifier` en un script aislado, porque el CLI no ofrece discovery y el pipeline
`autonomous_discover_marketplace` depende de Playwright; no se usó ningún archivo/base de VA.
