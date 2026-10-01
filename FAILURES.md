# FAILURE LIBRARY

## F-001 — False pagination exhaustion
Ripley pagination links were discovered but discarded, causing unsupported exhaustion.
Resolution: pagination discovery/validation added and later certified.

## F-002 — Resume coverage downgrade
A resumed run lost parent coverage state.
Resolution: resume coverage semantics corrected and re-tested.

## F-003 — Navigation tree unavailable through naive DOM discovery
Headless DOM/anchor extraction did not expose Ripley's commercial tree.
Resolution: structured network navigation source discovered and integrated.

## F-004 — False navigation-positive from PDP carousel
Product links were mistaken for navigation nodes.
Resolution: detector hardened.

## F-005 — Ripley facet application gap
Drawer checkbox could be selected but initial headless application showed no effect.
Resolution: diagnostic identified URL_QUERY + Document GET mechanism; later integrated and MRI-only recertified.

## F-006 — page_signature JavaScript escaping
A JavaScript escaping error caused invalid/empty facet verification signals.
Resolution: raw-string/escaping fix and tests; later reported recertification showed valid before/after signatures with zero exceptions.

## F-007 — Chrome persistent-session conflict
A local browser-session conflict caused TargetClosed/environment failures during recertification attempts.
Resolution status: environmental; later run reported isolated profile working. Do not add architectural workaround unless it recurs reproducibly.

## F-008 — Mercado Libre brand routing
4-marketplace baseline reported core extraction/pagination working, but BRAND_DISCOVERY failed/unresolved.
Resolution in MRI-CROSSMARKET-BLOCKERS-001 & MRI-ML-BRAND-ROUTING-001:
1. Rejection of shipping address URLs (`addresses/v3/navigation/hub?go=...`) via `surface_classifier.py` (`GENERAL_NAVIGATION`).
2. Extraction of real official store commercial categories (`New In`, `Conjuntos`, etc.) via `category_discoverer.py`.
3. Canonical emission of `brand_evidence_count_text` and `brand_present` on all category batches in `autonomous_pipeline.py`.
4. Certified in real run: 525 products observed, 525 direct brand evidence items (100%), independent reconciliation PASS.
Status: RESOLVED_AND_CERTIFIED (PASS).

## F-009 — Paris brand routing
4-marketplace baseline reported core extraction/pagination working, but BRAND_DISCOVERY failed/unresolved.
Resolution in MRI-CROSSMARKET-BLOCKERS-001 & MRI-PARIS-BRAND-ROUTING-001:
1. Rejection of non-commercial navigation URLs (`/mi-cuenta`, `/iniciar-sesion`, `/centro-de-ayuda`, `/seguimiento`, `/legales/`, `/terminos`) and site-wide corporate outlet (`/outlet/`) via `surface_classifier.py`.
2. Extraction of real brand category facets from Next.js App Router streaming RSC chunks (`self.__next_f.push`, `generalFacets.tipoProductoAll`) and brand store route in `category_discoverer.py`, isolating from site-wide uncollapsed Mega-Menu noise.
3. Category query parameter URL routing (`search?q={brand}&tipoProductoAll={category}`) discovered and navigated autonomously.
4. Certified in real run: 539 products observed in brand hub, 24 products observed in navigated commercial category with 100% direct brand evidence (24/24), independent reconciliation PASS.
Status: RESOLVED_AND_CERTIFIED (PASS).

## F-010 — Falabella headless entry
4-marketplace baseline reported initial headless surface blocked/failing before product observation.
Resolution in MRI-CROSSMARKET-BLOCKERS-001 & MRI-FALABELLA-ENTRY-001:
1. Forensic reproduction confirmed CHALLENGE_PAGE on standard Playwright browser requests (Cloudflare HTTP 403).
2. Frontier evaluation confirmed that standard HTTP requests (F1) receive unblocked HTTP 200 with complete 1.97MB Next.js SSR document (48 products in `__NEXT_DATA__`, 100 pods).
3. Surgical fix: `navigate()` override in `FalabellaScraper` activates HTTP SSR acquisition fallback and populates the Playwright page DOM via `set_content()`.
4. Certified in real run: `navigation_success=YES`, `commercial_page=YES`, `challenge_detected=NO`, `dom_usable=YES`, `commercial_content_observed=YES` (100 pods, 48 products in structured data), independent reconciliation PASS.
Status: RESOLVED_AND_CERTIFIED (PASS).


## F-011 — Baseline runner wrapper noise
The diagnostic wrapper reported a NameError and subprocess rc=1/venv close noise after event logs were persisted.
Resolution in MRI-CROSSMARKET-BLOCKERS-001: Verified physically in `baseline_4mp.py:97`. `capabilities_from(r, events)` accessed undefined variable `mp` when `checkpoints_written` was falsy. Classified as `WRAPPER_FAILURE`. MRI pipeline unaffected.
Status: FORENSICALLY_RESOLVED (`WRAPPER_FAILURE`).

## F-012 — Falabella brand routing
Initial baseline and test suite had zero commercial category routes extracted from Falabella SSR document because facets are rendered inside `<script id="__NEXT_DATA__">` rather than standard anchor tags, and category facet query parameters were misclassified as BRAND_SURFACE.
Resolution in MRI-FALABELLA-BRAND-ROUTING-001:
1. `surface_classifier.py`: recognize `attribute.tipo`, `l0_category_paths`, `f.product.` as `COMMERCIAL_CATEGORY`.
2. `category_discoverer.py`: extract commercial category facet options from `__NEXT_DATA__.props.pageProps.facets`.
3. `falabella_scraper.py`: parse structured product records from `__NEXT_DATA__.props.pageProps.results` with direct brand and membership evidence.
4. Certified in real run: 22 routes discovered, 2 routes verified, 157 products observed, 100% direct brand evidence (157/157), 100% membership evidence (157/157), independent reconciliation PASS.
## F-013 — Ripley HTTP 429 rate limiting and unconstrained category navigation
During MRI-4MP-E2E-CERT-001 transversal certification, Ripley execution failed to observe brand products:
1. Forensic separation in MRI-RIPLEY-RATE-LIMIT-AND-BRAND-FILTER-001:
   - Rate limiting: Tested across 2 clean navigation attempts; received HTTP 200 OK on both hub and filtered routes (`RATE_LIMIT_STATUS = NOT_TRIGGERED`).
   - Brand constraint loss: Deterministically reproduced (`BRAND_CONSTRAINT_STATUS = FAIL`). The root cause was a schema mismatch between `mechanism.json` (`mechanism_type: 'URL_QUERY (server-side document navigation)'`, lacking `param`) and `build_facet_url` / `autonomous_pipeline.py` (which checked `== 'URL_QUERY'` and `param`). This caused `build_facet_url` to return `None`, `_facet_state['applied'] = False`, and line 817 fell back to the unconstrained category `zapatos-y-zapatillas` with 0 brand products.
2. Resolution:
   - Enhanced `build_facet_url` in `category_discoverer.py` to support `URL_QUERY` schema variants and dynamic parameter resolution.
   - Updated `autonomous_pipeline.py` to ensure `_target` prioritizes `_furl` when built so unconstrained raw URLs are never scraped for brand audits.
   - Preserved seed surface across navigation sanitization.
3. Certified in real run: 1439 routes discovered, 1 route verified, 48 products observed, 48 direct brand evidence (100%), 48 membership evidence (100%), independent verification PASS.
Status: RESOLVED_AND_CERTIFIED (PASS).

## F-014 — VA Legacy category loss due to unextracted cell hyperlinks and hardcoded rules
In VA Legacy, new categories added to `SVMP.xlsx` (such as Falabella: Poleras mujer, Vestidos y enteritos, Faldas, Shorts; Paris: Fiesta; Ripley: Calzas, Accesorios y complementos) were lost before scraper dispatch:
1. Root cause: `ExcelLoader` used `pandas.read_excel` which ignored cell hyperlinks, producing `AuditTask` objects with `url_base = None` and `url_nicopoly = None`. `AuditRunner` then attempted lookup strictly in `rules["category_urls"]` (from `Logica_Operacional/`), skipping any category without an explicit operational text file entry.
2. Resolution in VA-SVMP-CATEGORY-SYNC-001:
   - `ExcelLoader`: Read workbook via `openpyxl`, extracting `category_marketplace`, `category_nicopoly`, and dynamic target URLs directly from cell hyperlinks (`cell.hyperlink.target`).
   - `AuditRunner`: Prioritize `task.url_base` and `task.url_nicopoly` with fallback to `rules["category_urls"]`, ensuring all 44 categories are dispatched to their respective scrapers.
3. Verification: Red tests reproduced failure; green tests confirmed 15/15 passing; reconciliation demonstrated `difference = 0` across all 4 marketplaces.
Status: RESOLVED_AND_CERTIFIED (PASS).

## F-015 — Mercado Libre pagination blocked on brand store category routes
During MRI-4MP-E2E-CERT-002 transversal certification, Mercado Libre execution failed to observe products in brand store categories:
1. Symptoms: Playwright navigation to fallback route `https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly` resulted in `Blocked during pagination on Page 1` for both `New In` and `Conjuntos`, yielding 0 products observed and failing blocking capabilities (BRAND_DISCOVERY, ACQUISITION, PRODUCT_EXTRACTION, IDENTITY, MEMBERSHIP).
2. Root cause resolution in MRI-ML-PAGINATION-BLOCK-001:
   - Root cause identified as `ML_CAUSE_URL_TRANSFORMATION`: unconditional URL rewriting in `mercadolibre_scraper.py:75` forced legitimate store URLs to `nicopoly_Tienda_nicopoly`, triggering an Akamai bot detection challenge (`account-verification`). Furthermore, carousel exclusion filter previously discarded poly-cards inside store showcases (`ui-ms-polycard-carousel`).
   - Minimal surgical fix: removed unconditional URL rewrite via `_get_clean_navigation_url()`, added official store showcase carousel exemption in `_extract_products_from_html`, added money amount selectors to `price_el`, and made vendor fallback extraction dynamically resolve from the URL slug (`tienda/<brand>`).
   - Certified in real run: 3 routes discovered, 1 route verified (Brand Hub, stop_reason EXHAUSTION), 37 products observed, 37 direct brand evidence items (100%), 37 membership evidence items (100%), independent verification PASS.
3. Status: RESOLVED_AND_CERTIFIED (PASS).

## F-016 — Full Autonomous Cross-Marketplace Audit Verification
During MRI-FULL-AUTONOMOUS-AUDIT-AND-DASHBOARD-001, full autonomous audit executed across all four marketplaces (Mercado Libre, Paris, Ripley, Falabella).
Outcome: 0 failures, 0 fatal blockers. 4/4 marketplaces completed with E2E PASS, yielding 1098 unique products, 1050 direct brand evidence items, 2061 category memberships, and 1098 positions materialized.
Status: FULL_AUDIT_PASS (4/4 PASS).

## F-017 — Read model categories and legacy comparison unlinked from SQLite commercial tables
During post-audit validation, CATEGORÍAS and COMPARACIÓN LEGACY views continued to show frozen stubs from 2026-09-21 with `RESEARCH_SUMMARY_NOT_MATERIALIZED` and TopN = `N/A`:
1. Forensic causal isolation:
   - Root cause identified as `DASHBOARD_CAUSE_READ_MODEL_GAP`.
   - `MRIReadModel.get_categories()` bypassed SQLite database completely, returning an in-memory list `raw_cats = [...]` hardcoded from 2026-09-21.
   - `MRIReadModel.get_legacy_comparison()` similarly returned a static dictionary with hardcoded text and timestamps from 2026-09-21.
   - Materialization gap: Falabella's 425 products had been skipped by `GenericCommercialMaterializer` due to a strict `"NICOPOLY" in title` filter, leaving Falabella categories unmaterialized in DB.
2. Resolution in MRI-DASHBOARD-LIVE-MATERIALIZATION-001:
   - Materialized Falabella 425 products, categories, variants, prices, and memberships from evidence into SQLite.
   - Rewrote `get_categories()` in `app/dashboard/mri_read_model.py` to query `mri_categories`, `mri_publication_categories`, and `mri_publications`, grouping by taxonomy node and computing active Top30..Top240 counts.
   - Rewrote `get_legacy_comparison()` in `app/dashboard/mri_read_model.py` to query active publication counts and timestamps from `mri_publications`.
3. Verification: Red tests reproduced failure; green tests confirmed 2/2 passing; regression suite confirmed 13/13 passing; independent verification confirmed 0 mismatches.
Status: RESOLVED_AND_CERTIFIED (PASS).

