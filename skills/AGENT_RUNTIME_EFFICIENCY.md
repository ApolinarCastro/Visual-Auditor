# Agent Runtime Efficiency

## Mission
Complete autonomous execution with the minimum justified steps, latency, retries, tool calls, and rediscovery while preserving correctness and evidence.

## Mandatory activation
Use on every MRI autonomous run. Escalate when runtime is slow, repeats work, ignores verified experience, or fails to converge.

## Required metrics
elapsed_total; elapsed_by_phase; actions_total; actions_unique; actions_repeated; tool_calls_by_tool; retry_count; timeout_count; no_progress_cycles; frontier_opened; frontier_closed; frontier_reopened; experience_hits; experience_misses; evidence_items; last_real_progress_at; stop_reason.

## Rules
- Verified strategy -> execute/revalidate; do not rediscover by default.
- Repeated state without new evidence -> NO_PROGRESS.
- Budget exhausted -> checkpoint and stop.
- Investigation requires demonstrated strategy failure or stale evidence.
- Optimize only the dominant measured bottleneck.

## Procedure
Segment runtime -> critical path -> unique vs repeated work -> dominant latency -> NO_PROGRESS cycles -> ignored verified experience -> retry/timeout amplification -> stop-condition reachability -> baseline comparison -> smallest optimization -> re-measure.

## Stop
PASS when autonomous termination and evidence are preserved and measured efficiency improves. BLOCKED when runtime cannot be observed. FAIL when optimization harms correctness/coverage or misses the measured bottleneck.
