# MRI_LIGHTWEIGHT_FINAL — Cierre del modo HTTP-first

**Fecha:** 2026-11-10
**Commit de código:** `7e17429c40dfab2e5766bb80f936095b9461ecb6`
`feat(mri): motores HTTP ligeros para Ripley y ML, estrategia ALL_PARALLEL_HTTP_FIRST`
**Rama:** `integration/mri-deepseek-closure`

---

## 1. Evolución: de Playwright a HTTP

| Aspecto | Antes (Playwright) | Después (HTTP-first) |
|---|---|---|
| Memoria libre mínima | **87 MB** (ML Chrome) | **4 003 MB** |
| Navegadores en ALL | 3 (ML, Paris, Ripley) | **0** |
| Velocidad | ML ~11 min, Paris ~5 min | Paris 2.3 s · Ripley 1.3 s · ML 0.8 s |
| Puerto/estabilidad | memoria al límite, stop frecuente | estable con >4 GB libres |
| Cobertura | catálogo profundo por navegador | hub inicial + Falabella SSR completo |

**Piloto 020:**

```text
run_id = run_mri_discovery_1794312659
execution_strategy = ALL_PARALLEL_HTTP_FIRST
inicio ≈ 09:10:29 → fin 09:16:12
publicaciones persistidas = 532
edges = 532 (sin nulos)
database is locked = 0
integrity = ok
```

## 2. Métricas por marketplace (HTTP)

| Marketplace | Motor | Tiempo | Productos |
|---|---|---:|---:|
| Paris | Constructor HTTP | **2.3 s** | 40 |
| Falabella | SSR `__NEXT_DATA__` | **1.1 s** (prueba aislada) | 48 |
| Ripley | HTML `__NEXT_DATA__` | **1.33 s** | 48 |
| Mercado Libre | Storefront SSR | **0.77 s** | 39 |

Falabella completo en el ALL: 14 categorías, 80 páginas, 1 328 publicaciones (PARTIAL).

## 3. Límite de cobertura actual (documentado)

```markdown
## Modo de adquisición actual (HTTP-first)
- Paris, Ripley, ML: hub inicial (primera página / __NEXT_DATA__ / storefront).
- Falabella: SSR completo.
- Playwright: archivado como fallback para cobertura profunda, solo si es estrictamente necesario.
- Objetivo futuro: ampliar paginación HTTP para alcanzar cobertura completa sin navegador.
```

- **Paris/Ripley/ML** obtienen una muestra real del hub, no todas las categorías/páginas.
- **Falabella** mantiene cobertura SSR equivalente al camino anterior.
- Los checkpoints de cobertura HTTP de Paris/Ripley/ML quedan `INCOMPLETE` hasta implementar
  paginación por categoría; las publicaciones sí se persisten (532/532).
- Playwright **no está en la ruta por defecto**: `MRI_HTTP_FIRST` está activo y
  `MRI_MAX_BROWSER_CONCURRENCY` vale **0** por defecto. Para habilitar el fallback:
  `set MRI_MAX_BROWSER_CONCURRENCY=1`.

## 4. Estado por defecto del sistema

```text
MRI_HTTP_FIRST=1
MRI_MAX_BROWSER_CONCURRENCY=0   # navegador desactivado salvo configuración explícita
Estrategia: ALL_PARALLEL_HTTP_FIRST
Paris/Ripley/ML -> HTTP
Falabella -> SSR HTTP
Playwright -> fallback archivado (opt-in)
```

## 5. Conclusión

MRI pasó de un sistema que agotaba la memoria con Playwright (87 MB libres) a un sistema ligero que
ejecuta los 4 marketplaces **sin navegador**, con **>4 GB libres**, en segundos, y resultados reales
persistidos. La contrapartida es cobertura parcial en Paris/Ripley/ML; la siguiente prioridad es
**ampliar la paginación HTTP** para recuperar cobertura completa sin volver a Chromium.

```text
HTTP_FIRST=DEFAULT
PLAYWRIGHT=ARCHIVED_OPTIONAL_FALLBACK
MEMORY_MIN_FREE=4003 MB
FULL_RUN=run_mri_discovery_1794312659
PUBLICATIONS=532
COVERAGE=LIMITED_HUB (Falabella full SSR)
NEXT=PAGINATE_HTTP_FOR_FULL_COVERAGE
```
