# FAILURE LIBRARY

## F-001 — False pagination exhaustion
MRI discovered Ripley pagination links but classified/discarded them, closing the Brand Hub after page 1 with unsupported EXHAUSTION.
Resolution: pagination discovery and validation added; later certified across multiple pages.

## F-002 — Resume coverage downgrade
A resumed run lost parent coverage state and reported NOT_DISCOVERED despite completed parent frontier.
Resolution: resume coverage semantics corrected and re-tested.

## F-003 — Navigation tree unavailable through naive DOM discovery
MRI could open navigation but headless DOM/anchor extraction did not expose the real commercial tree.
Resolution: MRI-AUTONOMY-003 forensic sequence H1-H8. H4 network response produced the real structured source.

## F-004 — False navigation-positive from product carousel PDPs
Product-detail links inside nav-like containers were initially mistaken for commercial navigation nodes.
Resolution: detector hardened to exclude PDP/product patterns and require commercial destination structure.

## F-005 — Remaining facet blocker
Headless facet panel did not expose a validated brand facet in the last certified run. This remains the active blocker. It must not be converted into NOT_FOUND.
