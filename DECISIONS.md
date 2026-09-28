# DECISIONS

## D-001 — AutoClaw role
AutoClaw is a diagnostic/teaching tool only. It may reveal a failure mechanism, but its assisted run is non-certifiable. MRI must then reproduce the capability alone in a new run.

## D-002 — Canonical architecture
Do not create parallel auditors. Capability belongs in existing MRI components such as category discovery, autonomous pipeline, scraper, materializer, Experience Store, and independent verifier.

## D-003 — Navigation source
For Ripley, the navigation tree was found through marketplace network JSON at a menucomponent API endpoint observed by MRI itself. The source was reproduced across different PIDs and integrated as a generic navigation-source capability. Do not hardcode historical category names or counts.

## D-004 — Coverage
A local surface frontier reaching zero does not imply global CONFIRMED if a required discovery capability remains blocked.

## D-005 — Evidence semantics
A failed acquisition strategy is not a marketplace-level NOT_FOUND. SOURCE_BLOCKED and NOT_FOUND are distinct terminal semantics.

## D-006 — Resource discipline
No new browser/framework/service unless a demonstrated blocker cannot be solved by the existing stack and the resource/security/rollback cost is justified.
