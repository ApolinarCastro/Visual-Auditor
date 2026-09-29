# CURRENT STATE

## Project
Visual Auditor / MRI

## Status
IN_PROGRESS

## Last completed task
MRI-4MARKETPLACES-BASELINE-001

## Last reported verdict
MRI_4MP_BASELINE_PASS

## Evidence status
This repository state records the execution report supplied on 2026-09-29. The local evidence artifacts under `outputs/` were not uploaded to GitHub by this update, so individual local counts remain reported evidence until mirrored or independently inspected here.

## Demonstrated / reported milestones
- MRI-AUTONOMY-006: Ripley facet application recertified MRI-only after fixing `page_signature`; AutoClaw=0, manual=0.
- MRI-AUTONOMY-007: controlled propagation to 3 direct children; 3/3 terminal CERTIFIED; code changes=0; AutoClaw=0; manual=0.
- MRI-4MARKETPLACES-BASELINE-001: one bounded diagnostic pass across Mercado Libre, Paris, Falabella and Ripley; code changes=0; AutoClaw=0; manual=0.
- Cross-marketplace baseline reports ML and Paris core pipeline operational but brand-routing unresolved.
- Falabella reports ENTRY blocked/failing in headless acquisition.
- Ripley remains the positive control; no further frontier expansion is authorized before cross-marketplace blockers are handled.

## Current first blockers by marketplace
- Mercado Libre: BRAND_DISCOVERY / route from discovered surfaces to brand-relevant categories/facets.
- Paris: BRAND_DISCOVERY / route from discovered surfaces to brand-relevant categories/facets.
- Falabella: ENTRY / headless acquisition access.
- Ripley: no new capability blocker established by the baseline; global coverage remains incomplete.

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
Do not continue Ripley frontier. Select the smallest cross-marketplace blocker experiment from the 4-marketplace matrix, with a bounded stop condition and no architecture expansion.

## Prohibitions
- No blind traversal of Ripley's remaining frontier.
- AutoClaw cannot contribute actions to certified MRI runs.
- No hardcoded brand/category/count results in production logic.
- No new browser/framework/service without a demonstrated blocker and resource gate.
- Do not convert first-page absence of brand into NOT_FOUND.
