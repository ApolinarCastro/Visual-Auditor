# MRI_STRICT_AUTONOMY_CLOSURE_009_REPORT

**Tarea:** MRI-STRICT-AUTONOMY-CLOSURE-009 · **Fecha:** 2026-11-09
**Rama de código:** `integration/mri-deepseek-closure`
**GIT_COMMITS=1 (código) + 1 (documentación) · GIT_PUSHES=2**

---

## 1. Cambios en `run.py` — comandos oficiales

```diff
+def _paris_commercial_facet_urls(top_n=10):
+    # fetch public paris.cl navigation -> surface_classifier -> category tokens
+    # -> https://www.paris.cl/search?q=nicopoly&tipoProductoAll=<Categoria>
+
+async def _mri_cli_main(argv):
+    group = parser.add_mutually_exclusive_group(required=True)
+    group.add_argument("--discovery", action="store_true")
+    group.add_argument("--audit-verified-routes", action="store_true")
+    parser.add_argument("--marketplace", default="Paris")
+    parser.add_argument("--brand", default="Nicopoly")
+    parser.add_argument("--top-n", dest="top_n", type=int, default=10)
+    parser.add_argument("--experience-db", default=None)
+    # discovery: persiste CATEGORY (tipoProductoAll) en el ExperienceStore real
+    # audit: execute_verified_routes_audit(scope=TOP_N)
+
+# __main__: `run.py mri --discovery|--audit-verified-routes` despacha al CLI,
+# sin arrancar el servidor. El servidor sigue igual para `run.py mri --port`.
```

- Normaliza `marketplace` (`paris`→`Paris`) y `brand` (`nicopoly`→`Nicopoly`).
- `MRI_STRICT_AUTONOMY=true` se respeta: el fallback externo queda bloqueado en
  `verified_routes_audit.py`.

## 2. Cambio en `verified_routes_audit.py` — fallback estricto

```diff
+strict_autonomy = str(os.getenv("MRI_STRICT_AUTONOMY","")).lower() in ("1","true","yes")
 if sum(len(v) for v in rows_by_market.values()) == 0:
-    # lectura read-only de data/mri_experience.db
+    if strict_autonomy:
+        experience_source = "STRICT_AUTONOMY_NO_EXTERNAL_READ"
+    else:
+        # comportamiento histórico
...
+if strict_autonomy and total_selected == 0:
+    selection_reason = "NO_ROUTES_FOUND: strict autonomy prohibits external experience reads; run DISCOVERY first..."
```

La vista previa expone `strict_autonomy` y `selection_reason`.

## 3. Rutas descubiertas con filtro comercial (CLI oficial)

Comando ejecutado:

```bash
python run.py mri --discovery --marketplace paris --brand nicopoly --top-n 10
```

`routes_discovered=10`, `routes_new=10`, `routes_known=0` (primera ronda). URLs:

```text
https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Poleras
https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Blusas
https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Jeans
https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Pantalones
https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Vestidos
https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Faldas
https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Chaquetas
https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Abrigos
https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Parkas
https://www.paris.cl/search?q=nicopoly&tipoProductoAll=Short
```

**Segunda ronda** (mismo store real): `routes_new=0`, `routes_known=10` → **no re-descubre**.

## 4. Auditoría CLI con fidelidad de categoría

```bash
python run.py mri --audit-verified-routes --marketplace paris --brand nicopoly --top-n 3
```

`run_id=run_mri_cli_verified_1794232558` · `RUN_COMPLETED` · `experience_source=ExperienceStore`.

| route_id | URL (tipoProductoAll) | Estado | Publicaciones | Evidence | Reason del motor |
|---|---|---|---|---|---|
| `exp_2390` | `...tipoProductoAll=Abrigos` | **FOUND** | 40 | `ev_dcc182761db148e7` | `CONSTRUCTOR_BROWSE_TOTAL=149` |
| `exp_2384` | `...tipoProductoAll=Blusas` | **FOUND** | 40 | `ev_3c258b7c121c5f0e` | `CONSTRUCTOR_BROWSE_TOTAL=711` |
| `exp_2389` | `...tipoProductoAll=Chaquetas` | **FOUND** | 40 | `ev_9a95d1bb37421d4b` | `CONSTRUCTOR_BROWSE_TOTAL=487` |

- `strategy_selected == strategy_executed` (`paris_cdp_constructor_discovery`) en las tres.
- Aceptación `SELECTED_ROUTES_COMPLETE / PASS`; 3/3 procesadas; 0 pendientes.
- **Filtro de categoría, no búsqueda de marca:** las tres URLs llevan `tipoProductoAll` y el motor
  ejecutó `REAParisEngine.browse("tipoProductoAll", ...)`; los totales **difieren** por categoría
  (149/711/487), a diferencia de una búsqueda de marca que devolvería el mismo total.
- **Aprendizaje entre rutas:** la 1.ª selección leyó `persisted_evidence=1/1`, la 2.ª `2/2`, la
  3.ª `3/3` (`paris_cdp_constructor_discovery`, status VALIDATED) — el selector consumió la
  experiencia de las rutas anteriores.

## 5. Store real y autonomía estricta

- Se usó el **ExperienceStore operativo real** (`data/sqlite/mri_operational/mri_experience.db`) y
  la SQLite operativa (`.../visibility.db`), no una base de experimento.
- `MRI_STRICT_AUTONOMY=true`: `experience_source=ExperienceStore` durante la auditoría; el fallback
  a `data/mri_experience.db` no se usó. No se tocó la base histórica de VA.
- Evidencia real: 3 filas `mri_evidence_ledger` VALIDATED, `mri_runs` SUCCESS/FOUND,
  publicaciones materializadas (40 por ruta).

## 6. Commit y push

```text
Código:  1e13728df38dc0b5f232bdc42a85bce1e486aa6a
         feat(mri): autonomía estricta con CLI discovery/audit-verified-routes y filtros comerciales
         Rama: integration/mri-deepseek-closure
         Push: 9f0b445..1e13728  integration/mri-deepseek-closure
```

- https://github.com/ApolinarCastro/Visual-Auditor/tree/integration/mri-deepseek-closure
- Commit de documentación en `fix/mri-022-relational-recovery` (informe 008 + este cierre).

## 7. Conclusión

```text
MRI_STRICT_AUTONOMY=VERIFIED
CLI_DISCOVERY=PASS (10 rutas con tipoProductoAll)
CLI_AUDIT=PASS (3/3 FOUND, 40 pubs/ruta, evidence real)
CATEGORY_FILTER_FIDELITY=PASS (browse por tipoProductoAll; totales distintos por categoría)
SECOND_DISCOVERY_NO_REDISCOVERY=PASS (new=0/known=10)
OWN_LEARNING=PASS (evidencia 1/1 → 2/2 → 3/3)
VA_DATA_READ=NONE
PRODUCTION_VA_DB_TOUCHED=NO
GIT_COMMITS=1 (código) + docs
GIT_PUSHES=2
```

El ciclo completo **DISCOVERY → AUDIT_VERIFIED_ROUTES → aprendizaje** se ejecuta con el CLI oficial,
produce rutas con filtros comerciales, audita con fidelidad de categoría y los cambios están en
GitHub. Autonomía estricta cerrada.

**Nota:** el comando `--discovery` en esta versión descubre mediante HTTP + `surface_classifier`
(no Playwright) y genera variantes `tipoProductoAll` desde las categorías de moda; no sustituye al
pipeline `autonomous_discover_marketplace` para descubrimiento profundo de todas las superficies.
