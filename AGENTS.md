# Visual Auditor Agent Execution Contract

This repository is evidence-first and operates under Controlled Production Maintenance.

## Mandatory preflight for every MRI executor
Before planning, editing, debugging, testing, or executing MRI:
1. Read README.md, CURRENT_STATE.md, DECISIONS.md, FAILURES.md, and ACCEPTANCE.md.
2. Read skills/MRI_MANDATORY_SKILLS.json.
3. Read every skill listed by that manifest.
4. State the first demonstrated blocker and the evidence that supports it.
5. Prefer the smallest reversible action.
6. Do not declare PASS without execution evidence.

## Mandatory runtime policy
MRI autonomous execution is fail-closed if the mandatory skill manifest or any required skill file is missing. Do not bypass the preflight. Verified marketplace experience must be consulted before rediscovery. NO_PROGRESS and budget exhaustion are valid stop conditions, not reasons for infinite retries.

## Prohibited
- Architecture changes without demonstrated blocker evidence.
- Replacing a working component merely because another framework is interesting.
- Repeating discovery when verified experience remains valid.
- Treating SOURCE_BLOCKED as NOT_FOUND.
- Treating symptoms as root causes.
- Claiming execution, installation, test PASS, or recertification without evidence.
