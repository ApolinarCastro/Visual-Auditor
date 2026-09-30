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
1. Root cause 1 (Rate Limiting): Initial search navigation attempts to `https://simple.ripley.cl/search/nicopoly` returned HTTP 429 (Too Many Requests), preventing dynamic category discovery on the brand surface.
2. Root cause 2 (Unconstrained Category Navigation): Pipeline fallback / category verification navigated to `https://simple.ripley.cl/zapatos-y-zapatillas`, which is an unconstrained top-level category containing 48 generic store products and 0 Nicopoly products (`products_observed=0`, `direct_brand_evidence=0`, `membership_evidence=0`).
3. Resolution required: Implement backoff / jitter handling for Ripley HTTP 429 responses, and constrain category navigation to verified brand-filtered URLs or preserve brand filter facets during category traversal.
Status: OPEN (`FIRST_GLOBAL_BLOCKER = RIPLEY_RATE_LIMIT_AND_UNFILTERED_CATEGORY_ZERO_BRAND`). Next task: `MRI-RIPLEY-RATE-LIMIT-AND-BRAND-FILTER-001`.

## F-014 — VA Legacy category loss due to unextracted cell hyperlinks and hardcoded rules
In VA Legacy, new categories added to `SVMP.xlsx` (such as Falabella: Poleras mujer, Vestidos y enteritos, Faldas, Shorts; Paris: Fiesta; Ripley: Calzas, Accesorios y complementos) were lost before scraper dispatch:
1. Root cause: `ExcelLoader` used `pandas.read_excel` which ignored cell hyperlinks, producing `AuditTask` objects with `url_base = None` and `url_nicopoly = None`. `AuditRunner` then attempted lookup strictly in `rules["category_urls"]` (from `Logica_Operacional/`), skipping any category without an explicit operational text file entry.
2. Resolution in VA-SVMP-CATEGORY-SYNC-001:
   - `ExcelLoader`: Read workbook via `openpyxl`, extracting `category_marketplace`, `category_nicopoly`, and dynamic target URLs directly from cell hyperlinks (`cell.hyperlink.target`).
   - `AuditRunner`: Prioritize `task.url_base` and `task.url_nicopoly` with fallback to `rules["category_urls"]`, ensuring all 44 categories are dispatched to their respective scrapers.
3. Verification: Red tests reproduced failure; green tests confirmed 15/15 passing; reconciliation demonstrated `difference = 0` across all 4 marketplaces.
Status: RESOLVED_AND_CERTIFIED (PASS).

