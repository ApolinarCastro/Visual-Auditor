# CURRENT STATE

## Project
Visual Auditor / MRI

## Status
BLOCKED_ON_RIPLEY_RATE_LIMIT

## Last completed task
MRI-4MP-E2E-CERT-001

## Last reported verdict
MRI_4MP_E2E_CERT_FAIL

## Evidence status
Physical certified evidence persisted in `outputs/mri_4mp_e2e_cert_001/` and `evidence/mri_4mp_e2e_cert_001/`. The first cross-marketplace end-to-end certification demonstrated:
- Mercado Libre: E2E_MARKETPLACE_PASS (524 products observed, 524 brand confirmed, 524 unique products, 3 routes verified: Brand Hub, New In, Conjuntos; duplicate work=0).
- Paris: E2E_MARKETPLACE_PASS (539 products observed, 539 brand confirmed, 539 unique products, 3 routes verified: Brand Hub, Abrigos, Blusas; duplicate work=0).
- Falabella: E2E_MARKETPLACE_PASS (249 products observed, 249 brand confirmed, 249 unique products, 4 routes verified: Brand Hub, Mujer, Pantalones, Blazers; duplicate work=0).
- Ripley: E2E_MARKETPLACE_FAIL (encountered HTTP 429 on search attempt; unconstrained category navigation to `zapatos-y-zapatillas` yielded 0 brand products and 0 membership).
- Global: MRI_4MP_E2E_CERT_FAIL (3/4 PASS, 1/4 FAIL).
- Production code: 0 files changed, 0 new files, 0 new dependencies.
- Independent recount: reconciled = 4/4, false_pass = 0, unsupported_fail = 0, synthetic = 0, hardcoded = 0, autoclaw = 0, manual = 0.
- First global blocker: `FIRST_GLOBAL_BLOCKER = RIPLEY_RATE_LIMIT_AND_UNFILTERED_CATEGORY_ZERO_BRAND`.
- Next smallest task: `TASK_ID: MRI-RIPLEY-RATE-LIMIT-AND-BRAND-FILTER-001`.

## Demonstrated / reported milestones
- MRI-AUTONOMY-006: Ripley facet application recertified MRI-only after fixing `page_signature`; AutoClaw=0, manual=0.
- MRI-AUTONOMY-007: controlled propagation to 3 direct children; 3/3 terminal CERTIFIED; code changes=0; AutoClaw=0; manual=0.
- MRI-4MARKETPLACES-BASELINE-001: bounded diagnostic pass across Mercado Libre, Paris, Falabella and Ripley; code changes=0; AutoClaw=0; manual=0.
- MRI-CROSSMARKET-BLOCKERS-001: forensic root cause resolution completed across Mercado Libre, Paris, Falabella, and Runner.
- MRI-ML-BRAND-ROUTING-001: Mercado Libre autonomous brand routing certified PASS (official store commercial categories, address rejection, 525 products, 100% brand evidence).
- MRI-PARIS-BRAND-ROUTING-001: Paris autonomous brand routing certified PASS (Next.js App Router streaming RSC facets, mega-menu isolation, 539 products, 100% brand evidence).
- MRI-FALABELLA-ENTRY-001: Falabella ENTRY certified PASS (HTTP SSR acquisition fallback F1/F2/F3, 100 pods, 48 products in structured state, independent reconciliation PASS).
- MRI-FALABELLA-BRAND-ROUTING-001: Falabella autonomous brand routing certified PASS (22 routes discovered, 2 routes verified, 157 products observed, 100% brand evidence).
- MRI-4MP-E2E-CERT-001: First transversal E2E certification across 4 marketplaces. 3/4 marketplaces achieved E2E_MARKETPLACE_PASS (ML: 524 products; Paris: 539 products; Falabella: 249 products). Ripley failed on HTTP 429 rate-limiting and zero-brand category navigation. Global verdict: MRI_4MP_E2E_CERT_FAIL.

## Current first blockers by marketplace
- Mercado Libre: E2E Certified PASS (Brand routing, acquisition, products, brand evidence, membership, resume).
- Paris: E2E Certified PASS (RSC brand routing, acquisition, products, brand evidence, membership, resume).
- Falabella: E2E Certified PASS (SSR brand routing, acquisition, products, brand evidence, membership, resume).
- Ripley: BLOCKED by HTTP 429 rate limiting on brand search and unconstrained category navigation yielding zero brand products (`RIPLEY_RATE_LIMIT_AND_UNFILTERED_CATEGORY_ZERO_BRAND`).

## Frozen capabilities
Do not reopen without demonstrated regression:
- Ripley navigation source
- Ripley pagination
- Ripley facet URL_QUERY mechanism
- Ripley page_signature fix
- Ripley controlled child propagation
- Mercado Libre official store commercial category discovery & navigation routing
- Paris Next.js App Router streaming RSC facet discovery & URL query routing
- Falabella HTTP SSR acquisition fallback for ENTRY
- Falabella `__NEXT_DATA__` facet routing and structured product extraction
- checkpoint/resume semantics
- runtime brand normalization
- Experience decision policy

## Next exact action
Execute `TASK_ID: MRI-RIPLEY-RATE-LIMIT-AND-BRAND-FILTER-001` to resolve Ripley HTTP 429 rate-limiting backoff and enforce brand-filtered category discovery/navigation. Do NOT modify production code or reopen ML, Paris, or Falabella.


## Prohibitions
- No blind traversal of Ripley's remaining frontier.
- AutoClaw cannot contribute actions to certified MRI runs.
- No hardcoded brand/category/count results in production logic.
- No new browser/framework/service without a demonstrated blocker and resource gate.
- Do not create a common abstraction for ML and Paris brand discovery.
