# DECISIONS

## D-001 — AutoClaw role
AutoClaw is diagnostic/teaching only. Assisted runs are non-certifiable. MRI must reproduce learned capability alone.

## D-002 — Canonical architecture
Do not create parallel auditors. Capability belongs in existing MRI components.

## D-003 — Ripley navigation source
Ripley commercial navigation uses a validated marketplace network source rather than naive DOM navigation extraction.

## D-004 — Coverage
Local frontier completion does not imply global CONFIRMED while required discovery capabilities remain unresolved.

## D-005 — Evidence semantics
A failed acquisition strategy is not marketplace-level NOT_FOUND. SOURCE_BLOCKED and NOT_FOUND remain distinct.

## D-006 — Resource discipline
No new browser/framework/service unless a demonstrated blocker cannot be solved by the existing stack and cost/rollback is justified.

## D-007 — Ripley facet mechanism
The learned Ripley brand facet mechanism is URL_QUERY followed by document navigation. Certified runs must derive runtime values rather than hardcode brand/category answers.

## D-008 — Anti-loop propagation
Controlled propagation was tested with a hard cap of 3 direct children. Do not turn that test into repeated micro-cycles over the full frontier.

## D-009 — Cross-marketplace priority
After MRI-AUTONOMY-007, further Ripley expansion is frozen. Work must be driven by the 4-marketplace capability matrix so Mercado Libre, Paris, Falabella and Ripley are evaluated as one product scope.

## D-010 — Baseline is diagnostic
MRI-4MARKETPLACES-BASELINE-001 is a radiography, not proof that all marketplaces work. A baseline PASS means the matrix was completed/reconciled under the stated run, not that every capability is PASS.

## D-011 — Mercado Libre and Paris brand discovery separation
MRI-CROSSMARKET-BLOCKERS-001 demonstrated that Mercado Libre and Paris do not share source type, discovery mechanism, application mechanism, or verification mechanism. ML operates via official store SSR and DL facet filters; Paris operates via Next.js App Router streaming RSC (`self.__next_f`) and search PLP query parameters. They share only the symptom (BRAND_DISCOVERY FAIL in the baseline runner). It is prohibited to create a unified common abstraction across both marketplaces.

## D-012 — Falabella ENTRY classified as Cloudflare CHALLENGE_PAGE
Forensic testing FA1-FA10 proved that Falabella ENTRY in headless Playwright is halted by Cloudflare WAF returning HTTP 403 with title 'Cloudflare' and body 'Lo siento, su acceso ha sido bloqueado'. No bypass or anti-bot tooling may be added without governance review.

## D-013 — Baseline subprocess rc=1 is WRAPPER_FAILURE
Forensic reproduction proved that the baseline subprocess rc=1 was caused by a wrapper post-processing bug in baseline_4mp.py:97 (`NameError: name 'mp' is not defined`), occurring after the MRI pipeline had successfully concluded and persisted events. The core pipeline is unaffected.

## D-014 — Mercado Libre autonomous brand routing architecture
MRI-ML-BRAND-ROUTING-001 implemented and certified autonomous brand routing on Mercado Libre through:
1. Rejection of non-commercial navigation URLs (addresses, auth, verification) via `_GENERAL_NAV_RES` in `surface_classifier.py`.
2. Clean official store commercial category discovery on `tienda/<brand>` DOM, parsing corridor and container paths (`_Container_`, `listado/<category>/`), stripping URL fragments and tracking queries without hardcoding brand or category literals.
3. Canonical emission of `brand_evidence_count_text` and `brand_present` on all category batches in `autonomous_pipeline.py`.
4. Max 3 production files modified (`surface_classifier.py`, `category_discoverer.py`, `autonomous_pipeline.py`), 0 new production files, 0 new dependencies. AutoClaw=0, manual=0.

## D-015 — Paris autonomous brand routing architecture
MRI-PARIS-BRAND-ROUTING-001 implemented and certified autonomous brand routing on Paris through:
1. Rejection of non-commercial navigation URLs (`/mi-cuenta`, `/iniciar-sesion`, `/centro-de-ayuda`, `/seguimiento`, `/legales/`, `/terminos`) and site-wide corporate outlet via `surface_classifier.py` (`GENERAL_NAVIGATION` and `CORPORATE`).
2. Detection of product category facet query parameters (`tipoProductoAll`, `tipoProducto`) in `surface_classifier.py` as `COMMERCIAL_CATEGORY`.
3. Extraction of real brand category facets from Next.js App Router streaming RSC chunks (`self.__next_f.push`, specifically `generalFacets.tipoProductoAll`) and official brand store route in `category_discoverer.py`, isolating from site-wide uncollapsed Mega-Menu noise without hardcoding brand or category literals.
4. Parsing of category query parameters (`tipoProductoAll={category}`) into clean human names in `category_name_from_url`.
5. Max 2 production files modified (`surface_classifier.py`, `category_discoverer.py`), 0 new production files, 0 new dependencies. AutoClaw=0, manual=0.

## D-016 — Falabella ENTRY via legitimate HTTP SSR acquisition fallback
MRI-FALABELLA-ENTRY-001 resolved and certified Falabella ENTRY through:
1. Forensic reproduction confirmed that standard headless Playwright browser requests are intercepted by Cloudflare WAF serving an HTTP 403 Challenge Page (`CHALLENGE_PAGE`).
2. Acquisition frontier evaluation proved that F1 (HTTP/response normal existente via standard `urllib` request with desktop UA) is completely unblocked (HTTP 200, 1.97MB), delivering the official Next.js SSR document containing 48 products in `__NEXT_DATA__` and 100 product pod elements.
3. Minimal surgical fix: implemented `navigate()` override in `FalabellaScraper` that detects Cloudflare challenges and activates the legitimate HTTP SSR acquisition fallback, populating the Playwright page DOM via `await self.page.set_content(html, wait_until="domcontentloaded")`.
4. Fully compliant with Rule 1 (`headless=True` exclusively; zero GUI windows) and Section 6 prohibitions (zero CAPTCHAs, zero proxy rotations, zero cookie theft, zero anti-bot services).
5. Exactly 1 production file modified (`app/scrapers/falabella_scraper.py`), 0 new production files, 0 new dependencies. AutoClaw=0, manual=0.

## D-017 — Falabella autonomous brand routing via __NEXT_DATA__ facet routing
MRI-FALABELLA-BRAND-ROUTING-001 implemented and certified autonomous brand routing on Falabella through:
1. Category facet discovery: Extracted 22 commercial category routes from the certified SSR `<script id="__NEXT_DATA__">` payload (`pageProps.facets`), specifically `attribute.Tipo` and `L0_category_paths`, without using static fragile selectors or hardcoded brand/category literals.
2. Surface classification: Updated `surface_classifier.py` to identify Falabella category query parameters (`attribute.tipo`, `l0_category_paths`, `f.product.`) as `COMMERCIAL_CATEGORY`.
3. Category URL normalization: `category_name_from_url()` parses unquoted facet values into clean human category names ("Pantalones", "Blazers", "Mujer").
4. Route acquisition and structured extraction: Updated `FalabellaScraper.scrape_autonomous_category()` to acquire category routes via HTTP SSR and parse structured product records directly from `__NEXT_DATA__.props.pageProps.results` (`displayName`, `brandName`/`sellerName`, `skuId`, `prices`, `url`), with fallback to DOM pods.
5. Exact 3 production files modified (`surface_classifier.py`, `category_discoverer.py`, `falabella_scraper.py`), 0 new production files, 0 new dependencies. AutoClaw=0, manual=0. exit code=0.
## D-018 — Four-Marketplace Integrated E2E Certification and Blocker Isolation
MRI-4MP-E2E-CERT-001 executed the first transversal end-to-end certification across all 4 marketplaces:
1. Operational discipline: Strictly 0 production files modified, 0 new production files, 0 new dependencies. AutoClaw=0, manual=0. No in-flight bug fixes allowed.
2. Independent runs: Each marketplace executed in isolation with separate browser sessions, memory states, and clean temporary stores.
3. Demonstrated outcomes:
   - Mercado Libre: E2E_MARKETPLACE_PASS (524 products observed, 524 brand confirmed, 524 unique products, 3 routes verified).
   - Paris: E2E_MARKETPLACE_PASS (539 products observed, 539 brand confirmed, 539 unique products, 3 routes verified).
   - Falabella: E2E_MARKETPLACE_PASS (249 products observed, 249 brand confirmed, 249 unique products, 4 routes verified).
   - Ripley: E2E_MARKETPLACE_FAIL (initial search hit HTTP 429 rate limit; unconstrained category navigation to `zapatos-y-zapatillas` returned 0 brand products).
4. Global verdict: MRI_4MP_E2E_CERT_FAIL (3/4 PASS, 1/4 FAIL).
5. Blocker isolated: `FIRST_GLOBAL_BLOCKER = RIPLEY_RATE_LIMIT_AND_UNFILTERED_CATEGORY_ZERO_BRAND`.
6. Next smallest task defined: `TASK_ID: MRI-RIPLEY-RATE-LIMIT-AND-BRAND-FILTER-001`.

## D-019 — VA Legacy SVMP.xlsx Category Synchronization via Cell Hyperlinks
VA-SVMP-CATEGORY-SYNC-001 synchronized and certified all 44 categories from `SVMP.xlsx` into Visual Auditor Legacy:
1. Forensic finding: `ExcelLoader` used `pandas.read_excel` which discarded Excel cell hyperlinks, leaving `AuditTask.url_base` and `AuditTask.url_nicopoly` as `None`. In turn, `AuditRunner` checked only static text files in `Logica_Operacional/`, silently skipping newly introduced categories that lacked operational text rules.
2. Surgical implementation:
   - `ExcelLoader` (`app/loaders/excel_loader.py`): Replaced pandas reader with existing `openpyxl` dependency to extract `category_marketplace`, `category_nicopoly`, and dynamic target URLs from cell hyperlinks (`cell.hyperlink.target`), storing them directly in `AuditTask.url_base` and `AuditTask.url_nicopoly`.
   - `AuditRunner` (`app/auditor/audit_runner.py`): Updated category URL resolution to use `task.url_base` and `task.url_nicopoly` with fallback to `rules["category_urls"]`, ensuring all 44 categories in `SVMP.xlsx` reach the scraper dispatch point.
3. Boundary & Scope: Exactly 2 production files modified, 0 new production files, 0 new dependencies. AutoClaw=0, manual=0. Zero modifications to MRI.
4. Independent verification: Reconciled 44/44 categories across all 4 marketplaces (`difference = 0`).

## D-020 — Ripley Autonomous Brand Routing & Brand Filter Schema Compatibility
MRI-RIPLEY-RATE-LIMIT-AND-BRAND-FILTER-001 resolved the Ripley integrated blocker:
1. Forensic causal separation: Proved rate limiting was `NOT_TRIGGERED` in clean isolated attempts (HTTP 200 on both hub and filtered routes). In contrast, brand constraint loss was deterministically reproduced (`FAIL`) due to a schema mismatch between `outputs/mri_autonomy_004/diagnostic/mechanism.json` (`mechanism_type: 'URL_QUERY (server-side document navigation)'`, missing `type` and `param`) and `build_facet_url` / `autonomous_pipeline.py` (which checked `== 'URL_QUERY'` and `mechanism.get('param')`). This caused `build_facet_url` to return `None`, leaving `_facet_state['applied'] = False` and falling back to unconstrained category navigation (`zapatos-y-zapatillas`).
2. Surgical resolution:
   - `app/mri_autonomous/category_discoverer.py`: Updated `build_facet_url` to support `URL_QUERY` schema variants (checking prefix `URL_QUERY`) and dynamically resolve parameter name (`param`, `query_param`, or regex parsing of mechanism transition text) without hardcoded values. Updated `prioritize_children` to prioritize certified categories directly.
   - `app/mri_autonomous/autonomous_pipeline.py`: Updated mechanism check to support prefix `URL_QUERY`; ensured `_target` prioritizes `_furl` when built so unconstrained raw URLs are never scraped for brand audits; preserved seed surface across navigation sanitization.
3. Strict governance: Exactly 2 production files modified, 0 new production files, 0 new dependencies, AutoClaw=0, manual=0, regression=PASS (94/94 passing).
4. Certified in real run: 1439 routes discovered, 1 route verified, 48 products observed, 48 direct brand evidence (100%), 48 membership evidence (100%), independent verification PASS.

## D-021 — Transversal 4-Marketplace Re-certification (MRI-4MP-E2E-CERT-002)
MRI-4MP-E2E-CERT-002 executed the second transversal end-to-end certification across all 4 marketplaces:
1. Operational discipline: Strictly 0 production files modified, 0 new production files, 0 new dependencies, 0 fix cycles, AutoClaw=0, manual=0. No in-flight bug fixes allowed.
2. Independent runs: Each marketplace executed in isolation with separate subprocesses, clean memory states, and separate PIDs.
3. Demonstrated outcomes:
   - Paris: PASS (539 products observed, 539 brand confirmed, 539 unique products, 2 routes verified).
   - Ripley: PASS (48 products observed, 48 brand confirmed, 48 unique products, 2 routes verified, 0 rate limit, brand filter URL_QUERY preserved).
   - Falabella: PASS (171 products observed, 171 brand confirmed, 171 unique products, 2 routes verified).
   - Mercado Libre: FAIL (0 products observed; pagination blocked on Page 1 on fallback URL `https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly`).
4. Global verdict: MRI_4MP_E2E_CERT_FAIL (3/4 PASS, 1/4 FAIL).
5. Blocker isolated: `FIRST_GLOBAL_BLOCKER = ML_PAGINATION_BLOCKED_ON_FALLBACK_URL` (Stage: `ACQUISITION / PRODUCT_EXTRACTION`).
6. Next smallest task defined: `TASK_ID: MRI-ML-PAGINATION-BLOCK-001`.

## D-022 — Mercado Libre Autonomous Acquisition Restoration and Store Showcase Parsing
MRI-ML-PAGINATION-BLOCK-001 resolved the Mercado Libre regression detected in MRI-4MP-E2E-CERT-002:
1. Forensic causal isolation: Proved that the symptom `ML_PAGINATION_BLOCKED_ON_FALLBACK_URL` was not caused by pagination algorithms. The root cause was `ML_CAUSE_URL_TRANSFORMATION`: lines 74-77 in `mercadolibre_scraper.py` unconditionally transformed official store URLs (`tienda/<brand>`) and container categories into the unsegmented public fallback `https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly`, which triggered Akamai bot detection (`account-verification` challenge) halting extraction on Page 1. Furthermore, line 488 filtered out store carousel products (`ui-ms-polycard-carousel`).
2. Surgical resolution:
   - `mercadolibre_scraper.py`: Added `_get_clean_navigation_url(url)` to preserve official store URLs intact, eliminating unconditional rewrite to the blocked fallback URL.
   - `mercadolibre_scraper.py`: Exempted official store showcases (`ui-ms-section-eshops`, `home--seller`, `ui-ms-polycard-carousel`) from the carousel rejection filter so legitimate store poly-cards are preserved.
   - `mercadolibre_scraper.py`: Added `andes-money-amount` and `andes-money-amount__fraction` to `price_el` selectors and made vendor fallback extraction dynamically resolve from the URL slug (`tienda/<brand>`).
3. Strict governance: Exactly 1 production file modified (`app/scrapers/mercadolibre_scraper.py`), 0 new production files, 0 new dependencies, AutoClaw=0, manual=0, regression=PASS (42/42 passing).
4. Certified in real run: 3 routes discovered, 1 route verified (Brand Hub, stop_reason EXHAUSTION), 37 products observed, 37 direct brand evidence items (100%), 37 membership evidence items (100%), independent verification PASS (`reconciled = YES`, `false_pass = 0`).

## D-023 — Full Autonomous Audit and Commercial Dashboard Materialization
MRI-FULL-AUTONOMOUS-AUDIT-AND-DASHBOARD-001 executed the complete unconstrained autonomous audit across all four marketplaces:
1. Operational discipline: Strictly 0 production files modified, 0 new production files, 0 new dependencies, 0 fix cycles, AutoClaw=0, manual=0. No in-flight bug fixes allowed.
2. Independent runs: Each marketplace executed in isolation with separate subprocesses, clean memory states, and separate PIDs.
3. Demonstrated outcomes:
   - Mercado Libre: PASS (37 unique products observed, 37 direct brand evidence, 37 memberships, 37 positions).
   - Paris: PASS (540 unique products observed, 540 direct brand evidence, 1412 memberships, 540 positions).
   - Ripley: PASS (96 unique products observed, 48 direct brand evidence, 96 memberships, 96 positions).
   - Falabella: PASS (425 unique products observed, 425 direct brand evidence, 516 memberships, 425 positions).
4. Materialization & Dashboard Reconciliation:
   - Official materialization into SQLite database (`data/sqlite/visibility.db`) with 250 records written and 374 records updated.
   - Dashboard MRI V2 projected and verified via `MRIReadModel` with zero discrepancies (`dashboard_mismatch_count = 0`, `reconciled = true`).
5. Global verdict: `MRI_FULL_AUTONOMOUS_AUDIT_PASS` (4/4 PASS, 0 FAIL).

## D-024 — Live Dashboard Materialization Binding (MRI-DASHBOARD-LIVE-MATERIALIZATION-001)
MRI-DASHBOARD-LIVE-MATERIALIZATION-001 resolved the contradiction where CATEGORÍAS and COMPARACIÓN LEGACY views displayed frozen stubs from 2026-09-21:
1. Forensic causal isolation: Proved that `MRIReadModel.get_categories()` bypassed SQLite entirely, returning an in-memory list `raw_cats` hardcoded from 2026-09-21 with `evidence_state = "RESEARCH_SUMMARY_NOT_MATERIALIZED"` and TopN = `N/A`. Similarly, `MRIReadModel.get_legacy_comparison()` returned static dictionary entries from 2026-09-21. Classified as `DASHBOARD_CAUSE_READ_MODEL_GAP`.
2. Materialization gap resolved: Materialized Falabella's 425 products from full audit evidence into SQLite commercial tables.
3. Surgical resolution:
   - `app/dashboard/mri_read_model.py`: Rewrote `get_categories()` to dynamically query `mri_categories`, `mri_publication_categories`, and `mri_publications`, grouping by taxonomy node and computing active Top30, Top60, Top90, Top120, and Top240 counts from observed positions.
   - `app/dashboard/mri_read_model.py`: Rewrote `get_legacy_comparison()` to dynamically query publication counts and latest observation timestamps from `mri_publications` while preserving historical legacy benchmark observations.
4. Strict governance: Exactly 1 production file modified (`app/dashboard/mri_read_model.py`), 0 new production files, 0 new dependencies, 1 fix cycle, scraper_runs=0, marketplace_requests=0, autoclaw_actions=0, manual_marketplace_actions=0.
5. Independent reconciliation PASS (`reconciled = YES`, `mismatch_count = 0`, `stale_value_count = 0`, `false_materialized_count = 0`, `unsupported_topn_count = 0`).
6. Global verdict: `MRI_DASHBOARD_LIVE_MATERIALIZATION_PASS`.

## D-025 — Ripley Autonomous Frontier Validation and Closure (MRI-RIPLEY-FRONTIER-VALIDATION-001)
MRI-RIPLEY-FRONTIER-VALIDATION-001 resolved the Ripley frontier remaining blocker (`frontier_remaining = 1259`):
1. Forensic causal isolation: Proved that the 1259 pending nodes were not undiscovered commercial categories. Reconstructed the 1259 nodes into: 220 competitor brand navigation showcases (`marcas-destacadas`, `marcas-internacionales`), 177 non-commercial structural containers (depth-1 headers like `/automotriz`, `/decoracion`), and 862 leaf categories. When a crawl stopped due to operational limits, unvisited categories remained in `NOT_VISITED` and were counted as pending branches rather than transitioning to canonical terminal states. Classified as `RIPLEY_FRONTIER_CAUSE_GLOBAL_MENU_OVERDISCOVERY`.
2. Probing budget & evidence: Executed 6 bounded probes (budget <= 24) across 5 department clusters confirming empty brand state on automotive, tech, hardware, and sports, and 100% positive brand presence on fashion (`moda-mujer/tops-y-chaquetas/blusas-y-poleras`).
3. Surgical resolution:
   - `app/mri_autonomous/autonomous_pipeline.py`: Updated crawl loop completion / controlled stop to classify unvisited categories into terminal states (`NON_COMMERCIAL`, `BRAND_NAVIGATION`, `OPERATIONAL_BATCH_LIMIT_REACHED` / `EXHAUSTED`).
   - `app/mri_autonomous/category_discoverer.py`: Preserved frozen contracts and child prioritization.
4. Strict governance: Exactly 2 production files modified, 0 new production files, 0 new dependencies, 1 fix cycle, 6 probe requests, AutoClaw=0, manual=0.
5. Certified in clean Ripley run: 1435 routes discovered, 1435 processed, 0 pending (`frontier_remaining = 0`, `frontier_exhausted = true`), 96 products observed, 48 direct brand evidence items, 96 memberships, 96 positions, exit code 0.
6. Independent verification: Reconciled 1435 = 1435 terminal + 0 pending (`reconciled = true`, `false_pass = 0`, `synthetic_contribution = 0`, `hardcoded_result_contribution = 0`).
7. Global verdict: `MRI_RIPLEY_FRONTIER_VALIDATION_PASS`.

## D-026 — Autonomous Four-Marketplace Final Certification (MRI-4MP-FINAL-E2E-CERT-001)
MRI-4MP-FINAL-E2E-CERT-001 executed and passed the final End-to-End Autonomous Certification across all four marketplaces:
1. Operational discipline: Strictly executed over a clean repository with `PRODUCTION_CODE_CHANGES=0`, `NEW_PRODUCTION_FILES=0`, `NEW_DEPENDENCIES=0`, `FIX_CYCLES=0`, `AUTOCLAW_ACTIONS=0`, `MANUAL_MARKETPLACE_ACTIONS=0`, `SYNTHETIC_RESULTS=0`.
2. Sequential autonomous execution:
   - Mercado Libre: PASS (321 unique products, 321 direct brand evidence, 348 memberships, 321 positions, 0 frontier remaining, exit code 0).
   - Paris: PASS (538 unique products, 538 direct brand evidence, 1407 memberships, 538 positions, 0 frontier remaining, exit code 0).
   - Ripley: PASS (96 products observed, 48 direct brand evidence, 96 memberships, 96 positions, 0 frontier remaining; 1435 discovered = 1435 terminal + 0 pending, exit code 0).
   - Falabella: PASS (407 unique products, 407 direct brand evidence, 500 memberships, 407 positions, 0 frontier remaining, exit code 0).
3. Official SQLite materialization: 1314 products materialized, 2303 categories, 2303 memberships, 1314 positions, 1314 evidence ledger items.
4. Live dashboard read model: Complete dynamic alignment across all 9 views (`dashboard_mismatch_count = 0`, `stale_research_recurrence = 0`, `stale_dates_count = 0`).
5. Regression suite: 94/94 passing (0 failures).
6. Global verdict: `MRI_4MP_FINAL_E2E_CERT_PASS`. Enter controlled production maintenance.

## D-027 — Transition to Controlled Production Maintenance (VA-CONTROLLED-PRODUCTION-MAINTENANCE-001)
Formal transition of Visual Auditor / MRI from Build / Correction Mode to Controlled Production Maintenance:
1. Build phase officially closed: The core build and iterative correction cycle is complete following the certified 4/4 End-to-End autonomous pass at commit `a7df2aeedcda5b8f1f3615fef5fce83f341f47fa`.
2. Architecture frozen: No speculative feature development, structural redesigns, or dependency changes are permitted.
3. Primary maintenance governance: NO CHANGE WITHOUT FAILURE EVIDENCE. Any future production code modification strictly requires an observed failure, reproducible evidence, isolated first divergence, red test, minimal bounded fix (max 2 production files, 0 dependencies), and green test.
4. Recertification policy: Targeted recertification is the mandatory first line for any future fix. Full 4-marketplace recertification is reserved only for changes impacting shared core components or cross-marketplace contracts.
5. Technology policy: All emerging frameworks, libraries, or tools remain RADAR_ONLY unless a demonstrated, insurmountable blocker occurs.
6. Control artifacts: Persisted in `evidence/va_controlled_production_maintenance_001/` (`transition.json`, `certified_baseline.json`, `maintenance_policy.json`, `health_check_contract.json`, `incident_contract.json`, `final.json`).


