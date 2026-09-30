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

## Current operating decision

Mercado Libre, Paris, and Falabella ENTRY are certified and frozen. Do not reopen without regression. Do not reopen Ripley.

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

Awaiting next authorized task from product governance. Falabella ENTRY is certified PASS; downstream capabilities (DISCOVERY, CATEGORIES, PRODUCTS) remain NOT_TESTED.


