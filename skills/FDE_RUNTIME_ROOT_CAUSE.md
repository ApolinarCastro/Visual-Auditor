# FDE Runtime Root Cause

## Mission
Find the first causal divergence between a certified known-good run and a failing runtime before proposing architecture, dependencies, or redesign.

## Mandatory activation
Use for hangs, loops, timeouts, regressions, abnormal latency, non-termination, or failed recertification.

## Rules
- Evidence before hypothesis.
- A symptom is not a root cause.
- Reuse existing evidence before expensive reruns.
- Preserve working capabilities.
- No new architecture while a reproducible failure lacks a demonstrated cause.

## Procedure
1. Recover persistent state and certified baseline.
2. Compare known-good and failing timelines.
3. Compare state transitions, surfaces, retries, waits, tool calls, frontier changes, outputs, and stop reasons.
4. Locate FIRST_DIVERGENCE.
5. Form the smallest falsifiable causal hypothesis.
6. Reproduce it with the smallest bounded test.
7. Apply only a minimum reversible fix after causal confirmation.
8. Execute RED -> FIX -> GREEN -> targeted regression -> real recertification.
9. Persist failure, evidence, solution, and lesson.

## Required output
TASK_STATE; KNOWN_GOOD; FAILING_RUN; FIRST_DIVERGENCE; SYMPTOM; ROOT_CAUSE; EVIDENCE; MINIMAL_FIX; RED; GREEN; REGRESSION; RECERTIFICATION; NEXT_ACTION.

## Stop
PASS only with causal proof and verified fix. BLOCKED when evidence cannot distinguish causes. FAIL when the fix does not remove the demonstrated divergence.
