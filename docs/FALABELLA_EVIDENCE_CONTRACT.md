# Contrato de evidencia y variantes — Falabella (MRI)

Este documento fija el contrato único que usan el motor autónomo, el runner,
los snapshots y el dashboard. No duplicar esta lógica en otros módulos.

## 1. Iterador paginado (una sola implementación: `falabella_autonomous._paginate`)

- Página inicial 1; 48 tarjetas/página (dato del sitio, no asumido).
- **Total fiable:** `props.pageProps.pagination.count` (tarjetas, NO productos únicos).
- **Fin real:** página sin `results` (EXHAUSTION). **Nunca** terminar por `rows >= count`
  (con duplicados corta antes) ni por `unique >= count` (count≠únicos).
- **Soft-404:** HTTP 200 sin `pagination`/`results` → `SOFT_404`/`NOT_FOUND`, jamás éxito.
- **Estancamiento:** dos páginas consecutivas con los mismos ids crudos → `NO_PROGRESS`
  (incompleto, nunca AUDIT_PASS).
- **Límite de seguridad:** `PAGE_BOUND_REACHED` ⇒ incompleto; aceptación AUDIT_FAIL.
- **Categoría vacía con filtro de marca:** `EMPTY` sólo si la superficie confirma 0;
  si la categoría contiene productos sin filtro, no se certifica como vacía.
- **Reintentos:** 403/429/5xx con backoff acotado; persistente ⇒ `SOURCE_BLOCKED`.
- **Evidencia por página:** página, cards, ids nuevos, count, buildId.

## 2. Contrato grupo/variante (desde 2026-10-26)

- `group_id`: id estable del producto = `<id>` de la ruta `/product/<id>/...`; si no
  existe, se usa el `productId` de la tarjeta.
- `variant_id`: `productId` observado en la tarjeta (puede variar entre superficies).
- `sku_id`: `skuId` de la tarjeta; `(group_id, sku_id)` es la clave de oferta.
- La unión se hace **por `group_id`**; se conservan `variants[]` y `skus{}`.
- Métricas dobles obligatorias:
  - `unique_products` = grupos distintos (catálogo).
  - `unique_sku_keys` = claves `(group_id, sku_id)` (ofertas/variantes).
- Nunca sumar categorías L2 (se solapan); la cobertura se mide por superficie/unión.

## 3. Categoría observada

- Primaria: superficie más específica (menor `expected_cards`) entre las que contienen
  el producto; se guardan todas en `categories_observed`.
- GSC ambiguo: resolución por título/URL/tokens de las categorías observadas; si no es
  única, se mantiene etiqueta con candidatos (nunca inventar categoría).
- `expected_category`: sólo desde catálogo de referencia verificado; si falta,
  `SIN_REFERENCIA` (no copiar la observada).

## 4. Evidencia normalizada por resultado

`evidence = {surface, query, page, position, build_id, category_observed}`.
`surface` ∈ brand / search / category:<id>; `query` sólo en search (p.ej. nicopoly).

## 5. Snapshots y diff

- Ruta: `<aux_dir>/falabella_snapshots/` (append-only, escritura atómica, nunca sobrescribe).
- Envelope: `captured_at_utc`, `run_id`, `build_id`, `coverage_fingerprint`,
  `complete`, `surfaces[]`, `unique_products`, `unique_keys`, `products[]`
  (`productId`, `groupUrl`, `variants`, `skus`, `skuIds`, `price_min`, categorías).
- Diff sólo entre snapshots con **mismo fingerprint y ambos completos**; si cambia la
  cobertura → `COVERAGE_CHANGED`/no comparable, no altas/bajas falsas.
- Diff producto (grupo) y SKU (oferta), con precios; idempotente para los mismos datos.
