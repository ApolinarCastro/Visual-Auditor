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
- MRI-4MARKETPLACES-BASELINE-001: bounded cross-marketplace baseline completed. Reported first blockers:
  - Mercado Libre: BRAND_DISCOVERY / brand routing.
  - Paris: BRAND_DISCOVERY / brand routing.
  - Falabella: ENTRY / headless acquisition.
  - Ripley: no new core capability blocker; coverage remains incomplete.

## Current operating decision

Do not continue expanding Ripley's large frontier merely because the mechanism works. Use the four-marketplace capability matrix to drive the smallest next blocker experiment.

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

This GitHub repository currently stores the persistent project state available through the connected repository. Local source and local `outputs/` artifacts are not automatically mirrored here. Statements based only on the latest supplied local execution report are labeled as reported until those artifacts are committed or independently inspected through an available source.

## Next task

Freeze Ripley expansion. Use the 4-marketplace baseline to choose one bounded blocker task, prioritizing cross-marketplace completion rather than deeper work on a single marketplace.
