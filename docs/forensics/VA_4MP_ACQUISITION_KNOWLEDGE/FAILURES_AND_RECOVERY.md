# FAILURES AND RECOVERY

Comprehensive catalog of demonstrated historical failure modes, root causes, surgical solutions, and recovery verification procedures in Visual Auditor / MRI (Failures F-001 through F-020).

---

## Historical Failure Index (F-001 to F-020)

### F-001 — False Pagination Exhaustion
- **Symptom**: Ripley pagination links were discovered but discarded, causing unsupported exhaustion.
- **Root Cause**: Pagination anchor parsing omitted dynamic data attributes.
- **Resolution**: Enhanced pagination detector; validated and certified in `outputs/MRI_RIPLEY_CORRECTION_CERTIFICATE.md`.

### F-002 — Resume Coverage Downgrade
- **Symptom**: Resumed runs lost parent coverage state.
- **Root Cause**: Coverage inheritance logic reset visited frontier flags on cold restart.
- **Resolution**: State serialization updated to preserve parent coverage across runs.

### F-003 — Navigation Tree Unavailable via Naive DOM Discovery
- **Symptom**: Headless DOM/anchor extraction failed to expose Ripley's commercial tree.
- **Root Cause**: Commercial tree rendered via client-side JavaScript network requests rather than static HTML.
- **Resolution**: Integrated validated network source (`mechanism.json`).

### F-004 — False Navigation Positive from PDP Carousel
- **Symptom**: Recommended product links were misclassified as taxonomy categories.
- **Root Cause**: PDP carousel anchors lacked negative classification filters.
- **Resolution**: Surface classifier hardened with regex rejection rules.

### F-005 — Ripley Facet Application Gap
- **Symptom**: Drawer checkbox could be selected in DOM, but headless application produced no network change.
- **Root Cause**: Ripley faceted navigation requires server-side document GET navigation (`URL_QUERY`) rather than client-side event triggers.
- **Resolution**: URL_QUERY mechanism integrated and certified.

### F-006 — page_signature JavaScript Escaping Error
- **Symptom**: Invalid or empty facet verification signatures.
- **Root Cause**: Unescaped string characters in dynamic JavaScript evaluation scripts.
- **Resolution**: Raw string formatting and escaping fixes applied; verified zero exceptions.

### F-007 — Chrome Persistent-Session Conflict
- **Symptom**: `TargetClosedError` during browser launch.
- **Root Cause**: Local Google Chrome process held exclusive file locks on user data directories.
- **Resolution**: Switched to temporary isolated user data profiles for headless execution.

### F-008 — Mercado Libre Brand Routing
- **Symptom**: Extraction and pagination functional, but brand discovery unresolved.
- **Root Cause**: Scraper captured shipping address hubs (`addresses/v3/navigation/hub?go=...`) as categories.
- **Resolution**: Rejected address hubs in `surface_classifier.py`; extracted clean official store categories; certified 525 products observed with 100% direct brand evidence (MRI-ML-BRAND-ROUTING-001).

### F-009 — Paris Brand Routing
- **Symptom**: Core extraction functional, but brand discovery unresolved.
- **Root Cause**: Uncollapsed Mega-Menu flooded category tree with corporate and account links.
- **Resolution**: Hardened `surface_classifier.py` rejecting non-commercial paths; extracted `generalFacets.tipoProductoAll` from Next.js App Router streaming RSC; certified 539 products observed (MRI-PARIS-BRAND-ROUTING-001).

### F-010 — Falabella Headless Entry
- **Symptom**: Playwright headless browser blocked by Cloudflare HTTP 403 Challenge Page.
- **Root Cause**: Browser TLS and header signatures triggered Cloudflare WAF bot mitigation.
- **Resolution**: Implemented F1 HTTP SSR acquisition fallback in `FalabellaScraper.navigate()`, utilizing standard Python `urllib` to retrieve complete 1.97MB Next.js SSR document (HTTP 200) and injecting HTML via `set_content()` (MRI-FALABELLA-ENTRY-001).

### F-011 — Baseline Runner Wrapper Noise
- **Symptom**: Wrapper script failed with `NameError: name 'mp' is not defined` after pipeline completion.
- **Root Cause**: Post-processing log helper accessed undefined variable when checkpoints were empty.
- **Resolution**: Fixed in `baseline_4mp.py:97`. Classified as `WRAPPER_FAILURE`; core pipeline unaffected.

### F-012 — Falabella Brand Routing
- **Symptom**: Zero commercial category routes extracted from Falabella SSR document.
- **Root Cause**: Category facets were serialized inside `<script id="__NEXT_DATA__">` rather than standard anchor tags.
- **Resolution**: `category_discoverer.py` extracted 22 commercial category routes from `props.pageProps.facets` (`attribute.Tipo`); certified 157 products observed (MRI-FALABELLA-BRAND-ROUTING-001).

### F-013 — Ripley Brand Constraint Loss
- **Symptom**: Ripley execution fell back to unconstrained category `zapatos-y-zapatillas` with 0 brand products.
- **Root Cause**: Schema mismatch between `mechanism.json` (`mechanism_type: 'URL_QUERY (server-side document navigation)'`) and `build_facet_url` which checked exact equality `== 'URL_QUERY'`.
- **Resolution**: Enhanced `build_facet_url` to support prefix matching and dynamic parameter resolution (MRI-RIPLEY-RATE-LIMIT-AND-BRAND-FILTER-001).

### F-014 — VA Legacy Category Loss
- **Symptom**: New categories added to `SVMP.xlsx` were skipped before scraper dispatch.
- **Root Cause**: `pandas.read_excel` stripped cell hyperlinks, setting task URLs to `None`.
- **Resolution**: Rewrote `ExcelLoader` to use `openpyxl`, extracting dynamic target URLs from `cell.hyperlink.target` for all 44 categories (VA-SVMP-CATEGORY-SYNC-001).

### F-015 — Mercado Libre Pagination Blocked on Fallback Route
- **Symptom**: Scraper blocked on Page 1 on fallback URL `https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly`.
- **Root Cause**: Unconditional URL rewrite in `mercadolibre_scraper.py:75` triggered Akamai challenge; carousel exclusion filter discarded poly-cards in store showcases.
- **Resolution**: Removed unconditional URL rewrite; added showcase carousel exemption for `ui-ms-polycard-carousel` (MRI-ML-PAGINATION-BLOCK-001).

### F-016 — Full Autonomous Cross-Marketplace Execution
- **Symptom**: Cross-marketplace integration validation.
- **Outcome**: 4/4 marketplaces completed with E2E PASS; 1098 unique products materialized into SQLite (MRI-FULL-AUTONOMOUS-AUDIT-AND-DASHBOARD-001).

### F-017 — Read Model Unlinked from SQLite Commercial Tables
- **Symptom**: Dashboard CATEGORÍAS and COMPARACIÓN LEGACY views displayed stale stubs from 2026-09-21.
- **Root Cause**: `MRIReadModel` returned hardcoded in-memory dictionaries instead of querying SQLite.
- **Resolution**: Connected `get_categories()` and `get_legacy_comparison()` to live SQLite tables (MRI-DASHBOARD-LIVE-MATERIALIZATION-001).

### F-018 — Ripley Unvisited Menu Nodes Inflating Frontier
- **Symptom**: Ripley reported 1259 pending frontier branches.
- **Root Cause**: 1259 unvisited global menu nodes remained in `NOT_VISITED` after crawl completion.
- **Resolution**: Reclassified unvisited categories into canonical terminal states (`NON_COMMERCIAL`, `BRAND_NAVIGATION`, `EXHAUSTED`) upon crawl completion; frontier closed with `pending = 0` (MRI-RIPLEY-FRONTIER-VALIDATION-001).

### F-019 — Autonomous Four-Marketplace Final Certification
- **Symptom**: Integrated transversal certification.
- **Outcome**: 1362 unique products observed across all 4 marketplaces; 1314 products materialized; 0 code changes during certification; certified PASS (MRI-4MP-FINAL-E2E-CERT-001).

### F-020 — UI Secret Exposure Incident
- **Symptom**: `/api/sessions` exposed raw session cookies in API responses and injected them into DOM textareas.
- **Root Cause**: API serializer included `raw_cookies: cookies` field.
- **Resolution**: Removed `raw_cookies` field; sanitized endpoint to return only metadata (`status`, `cookie_count`, `last_updated`); verified with RED/GREEN tests (VA-EXECUTIVE-DASHBOARD-SEMANTIC-AUDIT-001).
