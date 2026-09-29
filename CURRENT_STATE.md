# CURRENT STATE

## Project
Visual Auditor / MRI

## Status
IN_PROGRESS

## Last completed task
MRI-CROSSMARKET-BLOCKERS-001

## Last reported verdict
MRI_CROSSMARKET_BLOCKERS_PASS

## Evidence status
Physical forensic evidence persisted and certified in `outputs/mri_crossmarket_blockers_001/` and `evidence/mri_crossmarket_blockers_001/`. All root causes demonstrated with zero synthetic contribution and zero code changes to production.

## Demonstrated / reported milestones
- MRI-AUTONOMY-006: Ripley facet application recertified MRI-only after fixing `page_signature`; AutoClaw=0, manual=0.
- MRI-AUTONOMY-007: controlled propagation to 3 direct children; 3/3 terminal CERTIFIED; code changes=0; AutoClaw=0; manual=0.
- MRI-4MARKETPLACES-BASELINE-001: bounded diagnostic pass across Mercado Libre, Paris, Falabella and Ripley; code changes=0; AutoClaw=0; manual=0.
- MRI-CROSSMARKET-BLOCKERS-001: forensic root cause resolution completed across Mercado Libre, Paris, Falabella, and Runner:
  - Mercado Libre: root cause evidenced (evaluator missing key `brand_evidence_count_text` + address URL false capture + store sidebar facet adapter gap).
  - Paris: root cause evidenced (Next.js App Router streaming RSC `self.__next_f` state vs null `__NEXT_DATA__` + DOM Mega-Menu noise pollution).
  - ML vs Paris comparison: strictly evaluated as `ML_PARIS_SAME_MECHANISM = NO` (zero shared architectural components; shared symptom only).
  - Falabella ENTRY: conclusively classified as `CHALLENGE_PAGE` (Cloudflare WAF HTTP 403 challenge interstitial in headless Playwright).
  - Runner rc=1: conclusively classified as `WRAPPER_FAILURE` (NameError at `baseline_4mp.py:97`, MRI pipeline unaffected).
  - Execution bounds respected: code_changes=0, autoclaw_actions=0, manual_actions=0, ripley_actions=0.

## Current first blockers by marketplace
- Mercado Libre: BRAND_DISCOVERY adapter gap (needs official store sidebar facet extractor in `category_discoverer.py` and emission key fix).
- Paris: BRAND_DISCOVERY adapter gap (needs Next.js App Router RSC streaming facet parser and Mega-Menu isolation).
- Falabella: ENTRY challenge page (Cloudflare WAF in headless Playwright).
- Ripley: Frozen (positive control intact).

## Frozen capabilities
Do not reopen without demonstrated regression:
- Ripley navigation source
- Ripley pagination
- Ripley facet URL_QUERY mechanism
- Ripley page_signature fix
- Ripley controlled child propagation
- checkpoint/resume semantics
- runtime brand normalization
- Experience decision policy

## Next exact action
Select the smallest actionable fix identified in MRI-CROSSMARKET-BLOCKERS-001 under strict governance: either (A) fix the runner wrapper / emission key, (B) implement ML store sidebar facet discovery, or (C) implement Paris Next.js App Router RSC facet parser. Do not attempt Falabella bypass without explicit governance authorization.

## Prohibitions
- No blind traversal of Ripley's remaining frontier.
- AutoClaw cannot contribute actions to certified MRI runs.
- No hardcoded brand/category/count results in production logic.
- No new browser/framework/service without a demonstrated blocker and resource gate.
- Do not create a common abstraction for ML and Paris brand discovery.
