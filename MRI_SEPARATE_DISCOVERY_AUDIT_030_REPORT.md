# MRI_SEPARATE_DISCOVERY_AUDIT_030_REPORT

**Tarea:** MRI-SEPARATE-DISCOVERY-FROM-AUDIT-030 · **Fecha:** 2026-11-10
**Resultado:** DISCOVERY y AUDIT separados, rutas persistidas y reutilizadas.
Paris: **400 rutas guardadas** → auditoría con **410 rutas elegibles** sin volver a descubrir.

---

## 1. Persistencia de rutas (corregida)

`mri_runner.run_discovery` ahora persiste cada URL HTTP descubierta antes de finalizar:

```python
_store = _safe_experience_store()
for _p in _prods:
    _rec = _store.record_experience(
        marketplace=mkt, brand="Nicopoly",
        knowledge_type="CATEGORY", value=_url,
        source_url=_url, page_type="COMMERCIAL_HUB",
        status="LAST_GOOD", is_success=True,
        discovery_method="DASHBOARD_DISCOVERY_HTTP",
        evidence_reference="MRI-030 discovered route")
    _store.record_experience(
        marketplace=mkt, brand="Nicopoly",
        knowledge_type="ROUTE_STATE", value=f"exp_{_rec['id']}",
        status="OBSERVED", is_success=True, ...)
```

También se persiste el agregado del ALL (`run_parallel_discovery`).

### Estado del ExperienceStore tras DISCOVERY Paris

```text
Paris CATEGORY     = 410
Paris ROUTE_STATE  = 412
```

## 2. Dashboard: botones separados

- Botón principal renombrado:
  **“Descubrir rutas”** → ejecuta `DISCOVERY`.
- Bloque separado:
  **“Auditar rutas verificadas”** → ejecuta `AUDIT_VERIFIED_ROUTES` con
  `ALL_VERIFIED / TOP_N / SELECTED_ROUTES`.
- Texto explicativo añadido:

```text
Descubre rutas una vez. Luego audita las rutas verificadas sin volver a descubrir.
```

- El bloque de auditoría indica: “usa el ExperienceStore, no descubre”.

## 3. Validación del flujo

### 1) DISCOVERY Paris

```text
run_id=run_mri_discovery_1794327309
mode=DISCOVERY
results=400
routes_persisted=400
status=COMPLETED
```

### 2) AUDIT_VERIFIED_ROUTES Paris

```text
run_id=run_mri_audit_verified_routes_1794327384
mode=AUDIT_VERIFIED_ROUTES
routes_available=410
routes_selected=1
routes_processed=1
outcome=PASS
status=RUN_COMPLETED
marketplace=Paris
```

**No se lanzó DISCOVERY**: el `mode` quedó `AUDIT_VERIFIED_ROUTES` y la selección provino
del ExperienceStore (`routes_available=410`).

### Historial

```text
run_mri_audit_verified_routes_1794327384  Paris  FOUND  1
run_mri_discovery_1794327309              Paris  FOUND  400
```

## 4. Comportamiento sin rutas

Si un marketplace no tiene rutas en el store, `verified_routes_audit.load_verified_routes` devuelve:

```text
routes_selected=0
selection_reason=NO_ROUTES_FOUND: run DISCOVERY first...
```

y el API responde `409 NO_ELIGIBLE_ROUTES` con el preview, sin iniciar descubrimiento.

## 5. Flujo documentado

```text
1. Selecciona marketplace.
2. Pulsa "Descubrir rutas" una vez (o cuando quieras actualizar).
   → DISCOVERY persiste URLs en ExperienceStore.
3. Pulsa "Auditar rutas verificadas".
   → AUDIT_VERIFIED_ROUTES lee las rutas guardadas; NO descubre.
4. Si no hay rutas: NO_ROUTES_FOUND / “Descubrir rutas primero”.
```

## 6. Conclusión

| Objetivo | Estado |
|---|---|
| Rutas persistidas en ExperienceStore | **SÍ** (410 CATEGORY Paris) |
| Botones separados | **SÍ** |
| AUDIT no lanza DISCOVERY | **SÍ** |
| Flujo documentado | **SÍ** |
| Validación Paris | **SÍ** (400 → 410 disponibles, 1 auditada) |

La separación está operativa. Los demás marketplaces usarán el mismo mecanismo al ejecutar su
DISCOVERY; hoy no tienen rutas persistidas y devolverán `NO_ROUTES_FOUND` hasta descubrirlas.

## 7. Estado

```text
CODE_CHANGES=UNCOMMITTED (mri_runner.py, index.html)
DASHBOARD=RUNNING (con el fix)
PARIS_ROUTES=410
AUDIT_MODE=AUDIT_VERIFIED_ROUTES
AUDIT_RESULT=RUN_COMPLETED/PASS
```
