# Visual Auditor

Evidence-first marketplace observation and intelligence project.

## Current state — 2026-09-29

Current focus: MRI autonomous marketplace intelligence across four marketplaces:
- Mercado Libre
- Paris
- Falabella
- Ripley

### Latest milestones

- MRI-AUTONOMY-006: Ripley facet application reported PASS in a fresh MRI-only run after the `page_signature` fix.
- MRI-AUTONOMY-007: controlled propagation reported PASS across 3 direct Ripley children, with no code changes and no AutoClaw/manual actions.
- MRI-4MARKETPLACES-BASELINE-001: bounded cross-marketplace baseline completed. First blockers identified across all marketplaces.
- MRI-CROSSMARKET-BLOCKERS-001: forensic root cause resolution completed across all blockers:
  - Mercado Libre: root cause evidenced (evaluator missing key `brand_evidence_count_text` + address URL false capture + store sidebar facet adapter gap).
  - Paris: root cause evidenced (Next.js App Router streaming RSC `self.__next_f` state vs null `__NEXT_DATA__` + DOM Mega-Menu noise pollution).
  - Comparison ML ↔ Paris: strictly proven as `ML_PARIS_SAME_MECHANISM = NO` (zero shared architecture; shared symptom only).
  - Falabella ENTRY: conclusively classified as `CHALLENGE_PAGE` (Cloudflare WAF HTTP 403 challenge interstitial in headless Playwright).
  - Runner rc=1: conclusively classified as `WRAPPER_FAILURE` (NameError at `baseline_4mp.py:97`, MRI pipeline unaffected).
  - Governed execution: code changes = 0, AutoClaw = 0, manual = 0, Ripley actions = 0.
- MRI-ML-BRAND-ROUTING-001: Mercado Libre autonomous brand routing certified PASS:
  - Official store commercial categories discovered autonomously (`New In`, `Conjuntos`).
  - Shipping address URLs (`/addresses/v3/navigation/hub?go=...`) rejected (`address_hub_false_positives = 0`).
  - Discovered category navigated autonomously; 525 products observed with 100% direct brand evidence (525/525).
  - Independent reconciliation PASS (`reconciled = YES`, `false_pass = 0`).
  - Exact 3 production files modified (`surface_classifier.py`, `category_discoverer.py`, `autonomous_pipeline.py`), 0 new production files, 0 new dependencies.
- MRI-PARIS-BRAND-ROUTING-001: Paris autonomous brand routing certified PASS:
  - Next.js App Router streaming RSC category facets (`generalFacets.tipoProductoAll`) discovered autonomously.
  - Non-commercial navigation URLs (`/mi-cuenta`, `/iniciar-sesion`, `/centro-de-ayuda`, `/seguimiento`) and corporate outlet (`/outlet/`) rejected (`mega_menu_false_positives = 0`).
  - Discovered category navigated autonomously via URL query routing (`search?q={brand}&tipoProductoAll={category}`); 24 products observed with 100% direct brand evidence (24/24) and 24 membership evidence items.
  - Independent reconciliation PASS (`reconciled = YES`, `false_pass = 0`, `synthetic_contribution = 0`, `hardcoded_result_contribution = 0`).
  - Exact 2 production files modified (`surface_classifier.py`, `category_discoverer.py`), 0 new production files, 0 new dependencies.

- MRI-FALABELLA-ENTRY-001: Falabella ENTRY certified PASS:
  - Forensic reproduction confirmed CHALLENGE_PAGE on standard headless Playwright browser navigation (Cloudflare HTTP 403).
  - Acquisition frontier evaluation proved F1 (HTTP/response normal existente via standard `urllib`) is completely unblocked (HTTP 200, 1.97MB), delivering 48 products in `__NEXT_DATA__` and 100 pods.
  - Minimal surgical fix: implemented `navigate()` override in `FalabellaScraper` activating legitimate HTTP SSR acquisition fallback and loading DOM via `set_content()`.
  - Certified in real run: `navigation_success=YES`, `commercial_page=YES`, `challenge_detected=NO`, `dom_usable=YES`, `commercial_content_observed=YES` (100 pods, 48 products in structured data), zero evasions, zero proxies, zero CAPTCHAs, zero cookies, exact 1 production file modified (`falabella_scraper.py`), 0 new production files, 0 new dependencies.
  - Independent reconciliation PASS (`reconciled = YES`, `false_pass = 0`, `synthetic_contribution = 0`, `hardcoded_result_contribution = 0`).

- MRI-FALABELLA-BRAND-ROUTING-001: Falabella autonomous brand routing certified PASS:
  - SSR document inspection revealed real commercial taxonomy facets serialized in `<script id="__NEXT_DATA__">` under `pageProps.facets` (`attribute.Tipo` and `L0_category_paths`).
  - Classification: `surface_classifier.py` updated to classify Falabella category facet query parameters (`attribute.Tipo`, `l0_category_paths`) as `COMMERCIAL_CATEGORY`.
  - Autonomous discovery: `category_discoverer.py` extracts 22 commercial category routes from SSR `__NEXT_DATA__` facets without static hardcoded selectors.
  - Route navigation & structured extraction: `FalabellaScraper.scrape_autonomous_category()` navigates category route and extracts products with 100% direct brand evidence from `__NEXT_DATA__` results (`displayName`, `brandName`/`sellerName`, `skuId`, `prices`, `url`).
  - Certified in real run: 22 commercial routes discovered, 2 commercial routes verified (`Mujer` and `Pantalones`), 157 products observed, 157 direct brand evidence items (100%), 157 category membership items (100%).
  - Zero evasions, zero proxies, zero CAPTCHAs, exact 3 production files modified (`surface_classifier.py`, `category_discoverer.py`, `falabella_scraper.py`), 0 new production files, 0 new dependencies. AutoClaw=0, manual=0.
  - Independent reconciliation PASS (`reconciled = YES`, `false_pass = 0`, `synthetic_contribution = 0`, `hardcoded_result_contribution = 0`).

- MRI-4MP-E2E-CERT-001: First integrated four-marketplace E2E certification run executed:
  - Mercado Libre: `E2E_MARKETPLACE_PASS` (524 products observed, 524 brand confirmed, 524 unique products, 3 routes verified).
  - Paris: `E2E_MARKETPLACE_PASS` (539 products observed, 539 brand confirmed, 539 unique products, 3 routes verified).
  - Falabella: `E2E_MARKETPLACE_PASS` (249 products observed, 249 brand confirmed, 249 unique products, 4 routes verified).
  - Ripley: `E2E_MARKETPLACE_FAIL` (HTTP 429 rate-limiting on initial search navigation; fallback category `zapatos-y-zapatillas` yielded 0 Nicopoly products).
  - First Global Blocker isolated: `RIPLEY_RATE_LIMIT_AND_UNFILTERED_CATEGORY_ZERO_BRAND` (Stage: `BRAND_DISCOVERY / ACQUISITION / PRODUCT_EXTRACTION`).
  - Resource discipline: 0 production files modified, 0 new production files, 0 new dependencies. AutoClaw=0, manual=0.
  - Independent recount: `reconciled_marketplaces=4`, `false_pass_total=0`, `unsupported_fail_total=0`.

- VA-SVMP-CATEGORY-SYNC-001: Visual Auditor Legacy SVMP.xlsx category synchronization certified PASS:
  - Synchronized and certified all 44 valid categories across Falabella (9), Mercado Libre (12), Paris (8), and Ripley (15).
  - Extracted dynamic visibility and census URLs directly from SVMP.xlsx cell hyperlinks via `openpyxl`.
  - Resolved loss of newly introduced categories (Falabella: Poleras mujer, Vestidos y enteritos, Faldas, Shorts; Paris: Fiesta; Ripley: Calzas, Accesorios y complementos).
  - Exact 2 production files modified (`app/loaders/excel_loader.py`, `app/auditor/audit_runner.py`), 0 new production files, 0 new dependencies.
  - Independent reconciliation PASS (`difference = 0` across all 4 marketplaces; `reconciled = True`).

- MRI-RIPLEY-RATE-LIMIT-AND-BRAND-FILTER-001: Ripley autonomous brand routing & brand filter certification certified PASS:
  - Forensic causal isolation demonstrated rate limiting was `NOT_TRIGGERED` in clean attempts, while brand constraint loss was deterministically reproduced (`FAIL`) due to a schema mismatch in `mechanism.json` vs `build_facet_url` and `autonomous_pipeline.py` (failing `== 'URL_QUERY'`, missing `param`), causing fallback to unconstrained category `zapatos-y-zapatillas` with 0 brand products.
  - Minimal surgical fix: Enhanced `build_facet_url` in `category_discoverer.py` to support `URL_QUERY` schema variants and dynamic parameter resolution; updated `autonomous_pipeline.py` to preserve brand-constrained URL targets and avoid falling back to unconstrained category navigation; preserved seed surface across navigation sanitization.
  - Certified in real run: 1439 routes discovered, 1 route verified, 48 products observed, 48 direct brand evidence items (100%), 48 membership evidence items (100%), 0 AutoClaw actions, 0 manual actions, pipeline exit code 0.
  - Zero hardcoding of brand names or category counts (`new_hardcoded_result_contribution = 0`).
  - Independent reconciliation PASS (`reconciled = YES`, `false_pass = 0`).

- MRI-4MP-E2E-CERT-002: Second integrated four-marketplace transversal E2E certification run executed:
  - Paris: `PASS` (539 products observed, 539 direct brand evidence, 539 unique products, 2 routes verified, exit code 0).
  - Ripley: `PASS` (48 products observed, 48 direct brand evidence, 48 unique products, 2 routes verified, 0 rate limit, brand filter URL_QUERY preserved, exit code 0).
  - Falabella: `PASS` (171 products observed, 171 direct brand evidence, 171 unique products, 2 routes verified, exit code 0).
  - Mercado Libre: `FAIL` (0 products observed; pagination blocked on Page 1 on fallback URL `https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly`, yielding 0 products for New In and Conjuntos).
  - First Global Blocker isolated: `ML_PAGINATION_BLOCKED_ON_FALLBACK_URL` (Stage: `ACQUISITION / PRODUCT_EXTRACTION`).
  - Global Verdict: `MRI_4MP_E2E_CERT_FAIL` (3/4 PASS, 1/4 FAIL).
  - Strict resource & governance discipline: 0 production files modified, 0 new production files, 0 new dependencies, 0 fix cycles, AutoClaw=0, manual=0.
  - Independent recount: `reconciled_marketplaces=4`, `false_pass_total=0`, `unsupported_fail_total=0`.

- MRI-ML-PAGINATION-BLOCK-001: Mercado Libre autonomous acquisition and routing certified PASS:
  - Forensic causal isolation demonstrated root cause was `ML_CAUSE_URL_TRANSFORMATION`: unconditional URL rewriting in `mercadolibre_scraper.py:75` forced legitimate store URLs to `nicopoly_Tienda_nicopoly`, triggering Akamai bot detection (`account-verification` challenge). Additionally, carousel exclusion filter previously discarded poly-cards inside store showcases (`ui-ms-polycard-carousel`).
  - Surgical minimal fix: removed unconditional URL rewrite via `_get_clean_navigation_url()`, added official store showcase carousel exemption in `_extract_products_from_html`, added money amount selectors to `price_el`, and made vendor fallback extraction dynamically resolve from the URL slug (`tienda/<brand>`).
  - Red tests reproduced failure; green tests confirmed passing; regression suite confirmed 42/42 tests passing.
  - Certified in clean autonomous run: 3 routes discovered, 1 route verified (Brand Hub: 80 raw products, stop_reason EXHAUSTION), 37 unique products observed, 37 direct brand evidence items (100%), 37 category membership items (100%), pipeline exit code 0.
  - Exact 1 production file modified (`app/scrapers/mercadolibre_scraper.py`), 0 new production files, 0 new dependencies, 1 fix cycle, AutoClaw=0, manual=0.
  - Independent reconciliation PASS (`reconciled = YES`, `false_pass = 0`, `synthetic_contribution = 0`, `hardcoded_result_contribution = 0`).

## Current operating decision

All four marketplaces (Mercado Libre, Paris, Ripley, Falabella) have now individually achieved certified PASS for autonomous entry, brand discovery, category routing, acquisition, product extraction, direct brand evidence, and membership. Next step is executing the transversal four-marketplace certification (MRI-4MP-E2E-CERT-003).

## Core principles

- Input is `marketplace + brand`, not hardcoded answers.
- `SOURCE_BLOCKED != NOT_FOUND`.
- `PUBLICADO != VISIBLE`.
- Deterministic evidence/verification governs truth; AI is bounded investigation/strategy support.
- AutoClaw is diagnostic/teaching support only.
- No synthetic truth, hardcoded result counts, Cartesian category assignment, or self-certified metrics.
- Independent verification must reconcile reported results from persisted evidence.
- VA/Legacy remains protected unless explicitly authorized.

## Repository scope note

This GitHub repository stores the persistent project state and verified forensic artifacts.

## Next task

Execute transversal four-marketplace re-certification (`TASK_ID: MRI-4MP-E2E-CERT-003`).




