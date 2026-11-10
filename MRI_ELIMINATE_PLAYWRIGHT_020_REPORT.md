# MRI_ELIMINATE_PLAYWRIGHT_020_REPORT

**Tarea:** MRI-ELIMINATE-PLAYWRIGHT-020 · **Fecha:** 2026-11-10
**Resultado:** los 4 marketplaces corrieron **sin Playwright**, con memoria libre mínima
**4 003 MB** (>1 GB) y **532 publicaciones** persistidas. La cobertura HTTP es parcial frente a
Playwright, pero el objetivo de bajo consumo se cumple.

---

## 1. Endpoints identificados

### Ripley — HTML SSR con `__NEXT_DATA__`

```text
GET https://simple.ripley.cl/{categoria}?brand=NICOPOLY
→ 200 text/html (~2.2 MB)
→ <script id="__NEXT_DATA__">
   props.pageProps.findabilityProps.data.products[]  (48 productos)
   props.pageProps.findabilityProps.data.total
```

Campos del producto: `sku`, `parentProductID`, `name`, `brand`, `priceNumber`, `masterPriceNumber`,
`primaryImage`, `shop`.

### Mercado Libre — storefront SSR

```text
GET https://www.mercadolibre.cl/tienda/nicopoly
→ 200 text/html (~430 KB)
→ tarjetas/polycards y enlaces MLC-<id>
```

- `https://listado.mercadolibre.cl/...` sigue requiriendo verificación humana → **SOURCE_BLOCKED**
  (no se fuerza).
- `https://api.mercadolibre.com` existe pero no se usó para catálogo completo por autenticación;
  se documenta como endpoint disponible para una fase posterior.

## 2. Nuevos motores HTTP

### `ripley_http_engine.py`
- `urllib` directo, UA Chrome, timeout 30 s.
- Extrae `__NEXT_DATA__`, normaliza 48 productos con SKU, URL, nombre, marca y precio.
- Resultado medido: **48 productos en 1.33 s**.

### `meli_http_engine.py`
- `urllib` directo, UA Chrome, timeout 20 s.
- Extrae enlaces `MLC-*` del storefront, excluye enlaces de categoría (`/c/`), deduplica.
- Resultado medido: **39 publicaciones en 0.77 s**.

### Integración
- `_http_first_discovery` ahora cubre **Paris, Ripley y ML**; Falabella ya usaba SSR.
- `run_discovery` usa HTTP-first para Paris/Ripley/ML cuando `MRI_HTTP_FIRST != 0`.
- No se lanza Playwright en ninguno de los 4 caminos.

## 3. Ejecución real ALL (4 marketplaces HTTP)

```text
run_id = run_mri_discovery_1794312659
execution_strategy = ALL_PARALLEL_HTTP_FIRST
inicio ≈ 09:10:29
fin = 09:16:12
```

| Marketplace | Estado | Publicaciones / evidencia |
|---|---|---|
| **Paris** | **FOUND** | 40 productos HTTP; run `...__paris` SUCCESS |
| **Mercado Libre** | **FOUND** | 39 productos storefront HTTP |
| **Ripley** | **FOUND** | 48 productos HTML `__NEXT_DATA__` |
| **Falabella** | **PARTIAL** | 1 328 publicaciones SSR (14 categorías, 80 páginas) |
| **Total** | | **532 publicaciones persistidas** (+ Falabella SSR en checkpoint) |

- `mri_publications` del run: **532**.
- `mri_publication_categories`: **532 edges**, sin nulos.
- `mri_evidence_ledger`: 0 filas (la evidencia comercial quedó en publications/edges, no en ledger).
- Checkpoints HTTP de Paris/ML/Ripley: `INCOMPLETE` (el camino HTTP no escribe coverage por categoría
  todavía); Falabella sí tiene checkpoint completo.
- **Navegadores lanzados: 0** (no hay procesos Chrome/Playwright de MRI).
- `database is locked`: **0**; `PRAGMA integrity_check`: **ok**.

### Memoria

| Momento | Memoria libre |
|---|---:|
| Antes del dashboard | **7 762 MB** |
| Dashboard listo | **7 448 MB** |
| Inicio ALL | 5 749 MB |
| Mínimo durante la ejecución | **4 003 MB** |
| Al finalizar | 6 363–6 892 MB |

**Memoria libre siempre >1 GB**, con mínimo de 4 GB. Sin navegadores, el consumo es bajo y estable.

## 4. Comparación con Playwright

| Marketplace | Playwright (previo) | HTTP (020) | Delta |
|---|---|---|---|
| Paris | 595 pubs, 23 páginas, ~5 min | 40 pubs, **2.3 s** | Menos cobertura, mucho más rápido |
| ML | 225 pubs, 6 páginas, ~11 min | 39 pubs, **0.8 s** | Menos cobertura, sin browser |
| Ripley | 4 categorías, 0 pubs, browser | 48 pubs, **1.3 s** | Mejor resultado y sin browser |
| Falabella | 1 311–1 328 pubs, SSR | 1 328 pubs, SSR | Comparable |
| Memoria | <100 MB libre (ML) | **>4 GB libre** | Mejora radical |

**Conclusión de cobertura:** HTTP permite ejecutar los 4 sin navegador y con memoria holgada, pero
Paris/ML/Ripley quedan en **un hub inicial**, no en el catálogo completo que recorría Playwright.
Para equivalencia total hay que añadir paginación/descubrimiento HTTP por categorías.

## 5. Conclusión

| Pregunta | Respuesta |
|---|---|
| ¿MRI puede ejecutar los 4 sin Playwright? | **SÍ** (piloto real completado) |
| ¿Memoria >1 GB durante toda la ejecución? | **SÍ**, mínimo 4 003 MB |
| ¿Estable en 8 GB? | **SÍ para el modo HTTP actual**; con margen |
| ¿Resultados comparables a Playwright? | **Parcial**: mismos tipos de campos, menor cobertura en Paris/ML/Ripley |
| ¿Evidencia persistida? | 532 publications + 532 edges; ledger vacío |

**Recomendación:** usar el modo **HTTP_ONLY** para operación ligera y 8 GB; ampliar la paginación
HTTP de Paris/ML/Ripley para recuperar cobertura; mantener Playwright solo como fallback manual
aislado, nunca en la ruta por defecto.

## 6. Estado

```text
PLAYWRIGHT_IN_DEFAULT_PATH=NO
HTTP_ENGINES=Ripley 48/1.33s, ML 39/0.77s, Paris 40/2.3s, Falabella SSR 1328
FULL_RUN=run_mri_discovery_1794312659
MEMORY_MIN_FREE=4003 MB
SQLITE_LOCKED=0
INTEGRITY=ok
DASHBOARD=STOPPED
PORT_8055=FREE
CODE_CHANGES=UNCOMMITTED (autonomous_pipeline.py, mri_runner.py,
              base_scraper.py, ripley_http_engine.py, meli_http_engine.py)
```
