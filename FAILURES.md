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
4-marketplace baseline reports core extraction/pagination working, but BRAND_DISCOVERY failed/unresolved from the tested surfaces.
Status: ACTIVE.

## F-009 — Paris brand routing
4-marketplace baseline reports core extraction/pagination working, but BRAND_DISCOVERY failed/unresolved from the tested surfaces.
Status: ACTIVE.

## F-010 — Falabella headless entry
4-marketplace baseline reports initial headless surface blocked/failing before product observation.
Status: ACTIVE.

## F-011 — Baseline runner wrapper noise
The diagnostic wrapper reported a cosmetic NameError and subprocess rc=1/venv close noise after event logs were persisted.
Status: tooling debt. Do not conflate wrapper termination with marketplace capability without event evidence.
