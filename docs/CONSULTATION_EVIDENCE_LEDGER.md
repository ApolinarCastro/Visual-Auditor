# Consultation Evidence Ledger

This file defines the mandatory evidence format for material technical work in this repository.

The purpose is to prove which persistent project sources, shared knowledge-library sources, ECC references, official documentation, repository evidence, or other sources were actually consulted, what they contributed, and whether they materially influenced the solution.

## Required entry template

```text
TASK_ID:
PROJECT:
TIMESTAMP:

GAP_OR_BLOCKER:

SOURCES_CONSULTED:
  - SOURCE_TYPE:
    SOURCE_REFERENCE:
    WHY_CONSULTED:
    USEFUL_FINDING:
    APPLIED_TO_SOLUTION: YES | NO
    DECISION_OR_CHANGE_INFLUENCED:
    EVIDENCE_REFERENCE:

RESULT: PASS | FAIL | BLOCKED | NO_MATERIAL_CONTRIBUTION
NEXT_ACTION:
```

## Allowed SOURCE_TYPE values

- PROJECT_STATE
- KNOWLEDGE_LIBRARY
- ECC
- OFFICIAL_DOCS
- REPOSITORY
- OTHER

## Mandatory rules

1. "Library consulted" without an exact source reference and useful finding is invalid evidence.
2. If a source was consulted but did not influence the result, record `APPLIED_TO_SOLUTION: NO`.
3. Do not force irrelevant library consultation. Use the project's consultation router or source-authority policy when available.
4. When a blocker could reasonably benefit from existing technical knowledge, consult the router before inventing a new solution.
5. More sources is not better. Relevance and measurable impact matter.
6. A source recommendation never proves PASS. Project-specific reproducible verification is still required.
7. If a source changes diagnosis, architecture, implementation, testing, or recovery strategy, record exactly what changed.
8. If no source materially contributed, use `RESULT: NO_MATERIAL_CONTRIBUTION`; never manufacture value.
9. Link this ledger entry from the task's evidence or closure artifact whenever the project uses separate evidence files.
10. Periodic reporting should aggregate useful-source contribution without turning source count into a vanity metric.

## Semantic boundary

```text
CONSULTED != USEFUL
USEFUL != APPLIED
APPLIED != VERIFIED
VERIFIED contribution requires evidence
```
