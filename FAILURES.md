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
Resolution in MRI-CROSSMARKET-BLOCKERS-001: Root cause demonstrated causally. Paris uses Next.js App Router streaming RSC (`self.__next_f.push`) rather than `__NEXT_DATA__`. Category discoverer fell back to uncollapsed site-wide Mega-Menu DOM links (`Outlet Televisores`), yielding 0 brand products.
Status: FORENSICALLY_RESOLVED (Awaiting implementation).

## F-010 — Falabella headless entry
4-marketplace baseline reported initial headless surface blocked/failing before product observation.
Resolution in MRI-CROSSMARKET-BLOCKERS-001: FA1-FA10 forensic protocol conclusively classified the blocker as `CHALLENGE_PAGE`. Cloudflare WAF detects standard headless Playwright fingerprint and serves HTTP 403 Challenge Page ('Lo siento, su acceso ha sido bloqueado').
Status: CLASSIFIED (`CHALLENGE_PAGE`).

## F-011 — Baseline runner wrapper noise
The diagnostic wrapper reported a NameError and subprocess rc=1/venv close noise after event logs were persisted.
Resolution in MRI-CROSSMARKET-BLOCKERS-001: Verified physically in `baseline_4mp.py:97`. `capabilities_from(r, events)` accessed undefined variable `mp` when `checkpoints_written` was falsy. Classified as `WRAPPER_FAILURE`. MRI pipeline unaffected.
Status: FORENSICALLY_RESOLVED (`WRAPPER_FAILURE`).
