# ACCEPTANCE

A certified marketplace intelligence run must prove from persisted evidence:

- autonomous navigation by MRI
- autonomous discovery from marketplace + brand
- taxonomy hypotheses with provenance
- category/facet validation when applicable
- direct publication-category membership evidence
- observed position tied to surface + sort state
- honest EXHAUSTED/PARTIAL/BLOCKED states
- checkpoint/resume when exercised
- Experience behavior when exercised
- G16 remains fail-closed
- broken lineage = 0
- synthetic contribution = 0
- hardcoded result contribution = 0
- independent reported-vs-recounted reconciliation = PASS
- AutoClaw contribution to certified run = 0
- manual contribution to certified run = 0

## Cross-marketplace baseline gate

A 4-marketplace baseline PASS means:
- all 4 marketplaces were executed or legitimately classified under the bounded contract
- capability matrix is complete
- matrix is independently reconciled
- false PASS = 0
- code changes during diagnostic baseline = 0
- AutoClaw actions = 0
- manual actions = 0

It does NOT mean every marketplace capability is PASS.

## Cross-marketplace blockers gate (MRI-CROSSMARKET-BLOCKERS-001)

A cross-market blockers PASS requires:
- ml_blocker_reproduced = YES
- paris_blocker_reproduced = YES
- falabella_entry_blocker_reproduced = YES
- ml_root_cause = EVIDENCED
- paris_root_cause = EVIDENCED
- falabella_root_cause = EVIDENCED
- runner_rc1_classified = YES (WRAPPER_FAILURE)
- ml_paris_comparison = NO (strictly verified across 4 dimensions)
- code_changes = 0
- autoclaw_actions = 0
- manual_actions = 0
- ripley_actions = 0
- independent_verification = PASS

## Global completion

Global CONFIRMED additionally requires:
- required marketplaces meet their own acceptance gates
- no unresolved required discovery/acquisition blocker
- no unprocessed viable frontier required by the declared coverage contract
- final evidence is reproducible from persisted artifacts
