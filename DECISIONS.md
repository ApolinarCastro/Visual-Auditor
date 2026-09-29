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
