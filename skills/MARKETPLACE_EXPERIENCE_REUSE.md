# Marketplace Experience Reuse

## Mission
Turn verified marketplace discoveries into reusable operational knowledge so MRI executes the known path first and investigates only when evidence shows it is stale or broken.

## Mandatory activation
Use before marketplace discovery or reinvestigation.

## Knowledge object
marketplace; capability; surface; method; preconditions; observation; evidence; confidence; first_seen; last_verified; staleness; failure_condition; known_negative_paths; stop_condition; source_version.

## Lifecycle
OBSERVED -> VERIFIED -> PROMOTABLE -> ACTIVE -> STALE -> REVALIDATED or RETIRED.

## Runtime policy
1. Retrieve relevant ACTIVE experience before discovery.
2. Validate preconditions cheaply.
3. Execute the known method.
4. Verify expected evidence.
5. If valid, continue without rediscovery.
6. If invalid/stale, persist the contradiction and enter bounded reinvestigation.
7. Promote a new method only after real verification.
8. Version history; never overwrite it.

## Learn mechanics, not stale facts
Good: filter mechanism, SSR data location, pagination rule, category route semantics.
Bad: hardcoded product/category counts, current rankings, current SKU lists.

## Stop
PASS when applicable experience is reused/revalidated or correctly marked STALE. FAIL when applicable verified experience is ignored and discovery repeats without invalidation evidence.
