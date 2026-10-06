# VA-MRI-BRAND-FIRST-CLOSE-001

TASK_ID: VA-MRI-BRAND-FIRST-CLOSE-001

OBJECTIVE: Close the evidence-gated BRAND-FIRST pipeline under the original Definition of Done, without a new 4MP run.

STATE: READY

## Resume — BF18 root cause before fix

STATE: IN_PROGRESS

ROOT_CAUSE: In autonomous_discover_marketplace, the new-SKU branch of Brand Entry assigns `p["_discovered_categories"] = []` and `p["_discovered_category_urls"] = []` (lines 615–616 at HEAD 835f771), then appends Brand Hub. The category-ingestion branch repeats the same assignments (1063–1064). These assignments discard supplied edges. Duplicate-SKU observations also never merge their supplied memberships. No step turns the retained incoming membership pairs into required category records.

MINIMAL_FIX_PLAN: Merge paired membership metadata for every observation, preserve the seed surface as an additional edge, and enqueue only commercial category URLs carried by verified target products. Reuse the existing category loop for auditing and cross-check expansion. No scraper, dependency or architecture changes.

FIRST_BLOCKER: None locally; final commit/push/remote verification pending.

DEPENDENCIES: Existing Python 3.14.0 / pytest 9.0.3 recovered from the project's recorded interpreter. Dependencies added: 0.

ACCEPTANCE: Original mission gates remain unchanged. No PASS without RED, GREEN, full regression and remote verification.

MINIMUM_TEST: BF16 (physical discovery suppression without GAP), BF17 (fallback with GAP), BF18 (preservation of a target product's commercial membership).

EVIDENCE:
- HEAD before work: 835f771ad626f2eba67c4a63f9b7322b474e0c33, branch main.
- Original tracked working-tree diff was empty; numerous preexisting untracked files, including tests/test_mri_brand_first.py, were preserved.
- Confirmed causal divergence: discover_navigation_source(hub_url) is outside the else of the BRAND_FIRST_GAP gate. The subsequent `if not nav_candidates` also permits menu fallback without a gap.
- Added BF16/BF17 and a fake-scraper helper to the existing untracked test file, preserving its original contents. They call the production autonomous_discover_marketplace coroutine, mocking network, sleep and persistent ExperienceStore writes. Tests are NOT EXECUTED.
- Command: python -m pytest tests/test_mri_brand_first.py -k 'BF_16 or BF_17' -v. Exit 1: WindowsApps/python.exe failed to start; system has no access to the file.
- Command: py -0p. Output: No installed Pythons found!
- Existing .venv and venv directory checks returned no entries.
- Command: Codex bundled python.exe -m pytest tests/test_mri_brand_first.py -k 'BF_16 or BF_17' -v. Exit 1: No module named pytest.

RESULT: BF29 fixed. BRAND-FIRST 44 passed, full suite 276 passed / 3 preexisting skipped / 0 failed. All local gates GREEN. Remote pending.

NEXT_ACTION: Commit scoped files, push main, verify remote SHA and versioned fixes, then STOP.

## Continuation evidence — environment recovered, original gate fixed

The earlier environment search was incomplete. The project has an existing venv named `visibility_auditor_env`, and `outputs/va_final_resolution_loop_001/final.json` records a separate working interpreter.

Ordered checks:
1. `python -m pytest --version`: exit 1, WindowsApps alias cannot start.
2. `py -m pytest --version`: exit 1, No installed Python found!
3. `.venv/Scripts/python.exe -m pytest --version`: command not found.
4. `venv/Scripts/python.exe -m pytest --version`: command not found.
5. `visibility_auditor_env/Scripts/python.exe -m pytest --version`: fatal import error, No module named encodings. Its pyvenv.cfg points to C:/Python314; invoking that base interpreter reproduces the error.
6. `C:/Users/ASUS Zenbook/AppData/Local/Python/bin/python.exe -m pytest --version`: exit 0, pytest 9.0.3.
7. `C:/Users/ASUS Zenbook/AppData/Local/Python/pythoncore-3.14-64/python.exe -m pytest --version`: exit 0, pytest 9.0.3.

PYTHON_EXECUTABLE: C:/Users/ASUS Zenbook/AppData/Local/Python/pythoncore-3.14-64/python.exe (reported by sys.executable).

PYTEST_COMMAND: `& 'C:\Users\ASUS Zenbook\AppData\Local\Python\bin\python.exe' -m pytest`

No Python, dependency, virtual environment, or PATH changes were made.

The first asynchronous test stalled inside Windows asyncio event-loop creation. A pytest faulthandler trace identified socket.py:accept -> _fallback_socketpair -> proactor_events.py:_make_self_pipe, before the production coroutine executed. The stalled processes were interrupted. The same offline tests executed successfully outside the sandbox with authorized tool escalation; neither scraper nor persistent ExperienceStore was used.

Initial RED: BF16 failed with `Expected discover_navigation_source to not have been awaited. Awaited 1 times.` BF17 passed (exit 1).

Minimal production fix: both network-source discovery and menu fallback now require `brand_first_gap is not None`. No other production changes.

GREEN: original 15 tests plus BF16 and BF17, 17 passed, exit 0.

Regression: `python -m pytest`, collected 252, 249 passed / 3 skipped / 0 failed, exit 0, 138.12 seconds. Existing atexit cleanup warning: PermissionError on the pytest-current temporary symlink. This run collected before BF18 was added.

New RED: BF18 supplies BrandA SKU-VERIFIED-1 with paired observed category/name URL metadata. Production resets both lists when ingesting that new SKU and returns only Brand Hub. Exact assertion: `assert 'Vestidos' in ['Brand Hub']`. Updated targeted suite: 17 passed / 1 failed, exit 1. This is controlled offline test evidence, not a marketplace observation or a 4MP certification.

The run 20261006_134523 artifacts were located and their schemas inspected read-only; pending nodes were not reclassified. Dashboard files, Search Intent, Season, certifier, dependencies and stored run artifacts remain unmodified by this task. E2E_4MP_EXECUTED=NO.

## Latest continuation — BF18 resolved, offline evidence gate RED

STATE: BLOCKED

The recorded BF18 overwrite was corrected by merging observed name/URL pairs at both product-ingestion sites. The union preserves many-to-many edges and adds Brand Hub as a surface. Missing URLs remain unresolved rather than generating routes. Target-product commercial edges expand the existing category queue through the same cross-check; only same-host HTTP(S) routes classified as COMMERCIAL_CATEGORY are eligible.

BF18 GREEN: 18/18 tests passed, exit 0. Added BF19 specifically for duplicate observations carrying Vestidos and Blusas: one product, three unique edges including Brand Hub, two commercial categories audited, zero global-discovery calls. All original test assertions remain present.

Targeted GREEN: 19 passed, exit 0. Full regression: 254 collected, 251 passed / 3 skipped / 0 failed, exit 0, 71.99 seconds. The preexisting pytest-current temporary-symlink cleanup PermissionError remains an atexit warning; it did not change exit code.

Offline replay executed only after full regression GREEN. Command: existing project Python + evidence/va_mri_brand_first_close_001/offline_reclassification.py. Output:

```text
Mercado Libre: 0 = 0 + 0 + 0
Paris: 20 = 0 + 0 + 20
Falabella: 11 = 0 + 0 + 11
Ripley: 479 = 0 + 0 + 479
MISSING_OLD_NODE_IDENTITIES=510
AssertionError: OFFLINE_NODE_IDENTITIES_NOT_PERSISTED: 510 old pending nodes cannot be reclassified individually
exit_code=1
```

The columns are old = required + rejected_as_unproven + unresolved. No artificial node IDs or relevance labels were generated. The machine-readable report includes hashes of inspected run artifacts and the existing VA comparison unchanged; VA counts were not used as targets or classification evidence.

ROOT_CAUSE_OFFLINE: The pipeline computes `_remainder_urls = facet_urls[max_categories:]` but only retains the raw/relevant/pruned counters in `_facet_remainder_accounting` and a summary note. The run writer serializes discovered_categories to taxonomy.json and notes to failures.json; it does not persist the truncated facet URLs. All four taxonomy files contain zero QUEUED/NOT_VISITED pending nodes. The reported 510 old relevant pending items therefore cannot be associated with original per-node evidence from these artifacts. Logs were also inspected for a saved ordered facet list; none was found.

OFFLINE_RECLASSIFICATION: Aggregate accounting complete; individual node reclassification BLOCKED. UNKNOWN is preserved, not presented as commercial absence or verified rejection. This cannot substantiate a reduction in false frontier work.

UNRELATED_DELTA: git show confirms 835f771 introduced changes in the three Dashboard files (90 insertions, 8 deletions). Their accidental provenance has not been established independently; left untouched, provenance UNKNOWN. No Search/Season/TOP/history/URL or certifier edits in this task.

COMMIT: none. PUSH: not attempted because not all gates are GREEN. DEPENDENCIES_ADDED=0. E2E_4MP_EXECUTED=NO.

## Latest acceptance and persistence continuation

HISTORICAL_510: NOT_RECONSTRUCTABLE_FROM_EXISTING_EVIDENCE, explicitly accepted by the user. The prior offline report remains historical evidence; its former blocker does not apply to current acceptance. No approximation, new node IDs or navigation was used.

PERSISTENCE_RED: BF20 failed with AttributeError (runner had no persist_pending_nodes); BF21 failed with KeyError pending_nodes (pipeline discarded individual budget remainder). Targeted command returned exit 1, 2 failed.

PERSISTENCE_FIX: Retain actual remainder URLs and classify unfinished nodes from direct target evidence, verified non-commercial classification, or UNRESOLVED. Preserve existing identifiers, names, discovery provenance, relevance state/type/evidence, stop/block reasons, and related BRAND_FIRST_GAP. Missing values remain null. Both runner paths write pending_nodes.json to their existing run artifact directories before materialization, with actual marketplace/run_id and counts satisfying old_pending = required + rejected + unresolved. File replacement uses a temporary sibling file; no new DB, dependency or service.

PERSISTENCE_GREEN: BF20 writes and reloads three states including absent identities/URLs without mutation or invention. BF21 uses the production coroutine with two truncated URLs, writes the result and verifies both URLs and UNRESOLVED states after reload. Full BF01–BF21: 21 passed, exit 0.

REGRESSION_AFTER_PERSISTENCE: 256 collected, 253 passed / 3 skipped / 0 failed, exit 0, 57.18 seconds. This run collected before the new BF22 cases. Existing pytest-current atexit cleanup warning remains unchanged.

FINAL_CONTRACT_VERIFICATION_RED: Added BF22 as a three-brand comparison through production discovery and materialize_discovered_products. Each case observes one target product with a real-format identity and a commercial membership. The discovery assertion target_brand_present == 1 passes in all cases. Nicopoly is accepted and retains the category edge. BrandA and BrandB are rejected:

```text
classification: NON_NICOPOLY_CONFIRMED
evidence: Other brand; No Nicopoly in title; Legacy is_nicopoly=0
assert len(materialized['accepted']) == 1
actual: 0
latest BRAND-FIRST run: 22 passed / 2 failed, exit 1
```

ROOT_CAUSE_BRAND_AGNOSTIC: materialize_discovered_products computes is_nicopoly with literal nicopoly checks on vendor/title rather than carrying the requested target scope. GenericCommercialMaterializer.validate_membership also compares the brand specifically to NICOPOLY. The persisted identities and ingestion memberships survive, but the later materialization drops valid targets for other brands. Neither routine was changed after this new causal RED; STOP followed the user's instruction.

FUTURE_NODE_IDENTITY_PERSISTENCE=PASS. MEMBERSHIP_PRESERVATION=PASS at ingestion (BF18/BF19). BRAND_AGNOSTIC=NO. BRAND_FIRST_PIPELINE=NO for the complete materialized result. UNRELATED_DELTA_PROVENANCE=UNKNOWN; Dashboard/Search/Season unchanged. COMMIT=NONE, REMOTE_VERIFIED=NO.


## BF22 continuation and BF24 causal stop

ROOT_CAUSE_BF22: Requested brand was dropped before GenericCommercialMaterializer; process_record and G16 required NICOPOLY_CONFIRMED. The new optional explicit target scope preserves the legacy API while rejecting mismatched or missing marketplace brand evidence. Runner artifacts now preserve actual membership classification and actual run brand/marketplace.

BF22 GREEN: all three parametrized brands accepted; BF23 verifies contradictory brand and title-only/legacy-flag evidence are rejected. Suite: 26 passed, exit 0. Full regression started before BF24 existed: 258 passed, 3 preexisting skipped, exit 0 (62.28 seconds). Pytest emitted the preexisting atexit cleanup PermissionError; this did not change exit status.

BRAND_AGNOSTIC_SCAN: brand_agnostic_scan.json records every case-insensitive match in MRI autonomous modules, scrapers, runner, materializer and BRAND-FIRST tests, with A/B/C/D classification. Remaining scraper matches cannot be dismissed as legacy because production calls those extraction methods.

BF24 RED: Existing Paris HTML extractor assigns vendor Nicopoly from a title-only text mention at app/scrapers/paris_scraper.py:258-259. An offline fixture with no brand element, title Compatible con Nicopoly, native SKU 12345678 and price 10000 is ACCEPTED as TARGET_IDENTITY_VERIFIED. Expected accepted=[]; actual one accepted. Command: existing Python -m pytest tests/test_mri_brand_first.py -k BF_24 -v. Result: 1 failed, 26 deselected, exit 1. No browser initialized and no network navigation.

STATE: BLOCKED. BF24 is a distinct extraction-provenance defect upstream of the repaired BF22 materializer scope. Stop requested on new causal RED. No additional production fix, commit, push, dependency installation or 4MP execution. Dashboard/Search/Season untouched, provenance UNKNOWN. Historical 510 remains accepted as non-reconstructable and is not a blocker.


## BF24 continuation / BF26 stop

Paris adapter fix removes the literal title/text-to-vendor promotion, positional generic-span brand inference and adaptive brand rescue. Only explicit brand DOM fields populate vendor. No target or marketplace special case was added outside the adapter. BF24 GREEN; BF25 three controls GREEN: explicit conflicting vendor rejected, missing vendor insufficient, explicit matching vendor accepted. BF suite: 30 passed (0.60s), exit 0.

Full pytest: 262 passed, 3 preexisting skipped, 35 warnings (65.27s), exit 0. Collected BEFORE BF26 existed; not final-tree verification. Preexisting pytest atexit cleanup PermissionError remains.

Remaining scan finding confirmed: FalabellaScraper.scrape_top_240 at lines 334-335 sets brand Nicopoly from pod_text containing that literal without a brand selector. Recovery path in autonomous_pipeline calls scrape_top_240. BF26 mocks navigation, DOM and sleep; real extraction and materialization produce one accepted TARGET_IDENTITY_VERIFIED with only title/pod-text mention, native SKU and price. Expected no accepted products. Targeted run: 1 failed, 30 deselected, exit 1 (0.29s). Exact evidence: bf24_resolution_bf26_blocker.json.

STATE: BLOCKED. New causal RED triggers STOP per user. No changes to Falabella production, no commit/push, dependencies added=0, 4MP=NO. Dashboard/Search/Season untouched with UNKNOWN provenance. Prior historical510 acceptance preserved.


## BF26 resolution and BF27 stop

TRACE: Falabella scrape_top_240 lines 334-335 assigned brand Nicopoly from pod_text. Removed that assignment and neighboring free-text/adaptive vendor inference; explicit brand DOM selector remains. No other adapter changed this turn. BF26 now parametrized with absent, conflicting and explicit target vendor. All controls pass without changing the negative acceptance contract.

BF suite: 33 passed (0.65s), exit 0. Full pytest: 265 passed, 3 preexisting skips, 35 warnings (56.58s), exit 0. Existing atexit cleanup PermissionError remains nonfatal.

Remaining classified C scan match: Ripley scrape_top_240 has equivalent JS assignment at 1246-1250. BF27 used Python ast/inspect to obtain the actual extracted_data page.evaluate expression from production, evaluated that expression with existing Node and a fixture DOM (brand selector null, title Compatible con Nicopoly, native SKU 12345678). Real JS returned brand Nicopoly; production materializer accepted it as TARGET_IDENTITY_VERIFIED. Expected zero accepted, actual one; assertion exit 1. This standalone diagnostic is not in pytest; existing suite GREEN does not cover this new causal RED. See bf27_ripley_red.json and bf26_resolution_bf27_blocker.json.

STATE: BLOCKED. STOP per user. No Ripley production edits, no commit/push, no dependencies installed, no navigation, no 4MP. Historical510 acceptance unchanged. Dashboard/Search/Season unchanged, provenance UNKNOWN.


## BF27 resolution; complete adapter-pattern scan; BF28 stop

Ripley literal fallback promotion removed. Six BF27 controls execute actual production JS in existing Node with fixture DOM for both scrape_top_240 and scrape_autonomous_category. Missing/other brand do not verify; explicit target does. Initial test harness hit invalid inherited stdin under pytest capture; fixed subprocess stdin=DEVNULL/stderr=PIPE without changing assertions. BF suite then 39 passed. Full pytest executed (274 collected, exit0) before final primary Python cleanup and BF28 addition; do not call that final-tree GREEN.

Scan found equivalent dynamic promotion in Ripley primary JS and Python postprocessing; both removed, together with adaptive brand rescue. Paris/Falabella already preserve explicit brand selectors after previous fixes. Search-by-text rules unchanged. See adapter_identity_scan_bf27.json.

Distinct RED BF28: Mercado Libre lines 533-537 infer vendor from self.page.url tienda slug even with no vendor element. Real HTML extraction of Unbranded accessory in tienda/branda yields vendor Branda; materialization for BrandA accepts as TARGET_IDENTITY_VERIFIED. Expected zero accepted; actual one. BF suite final run: 39 passed / 1 failed, exit1, 0.92s. Evidence bf27_resolution_bf28_blocker.json. This is URL-context promotion, distinct from title/text promotion.

STATE: BLOCKED; STOP as ordered on a distinct causal RED. No Mercado Libre production fix, no commit/push, no new dependencies, no 4MP. Historical510 acceptance and unrelated-delta preservation unchanged.


## BF28 resolution / final-gate BF29

ML no longer derives vendor from tienda URL. Context retained separately as brand_surface_url; explicit product vendor remains authoritative. Adaptive vendor rescue removed. Three BF28 controls pass: absent, conflicting, explicit target. BF suite:42 passed, exit0 (0.70s). Full pytest:274 passed,3 preexisting skipped,35 warnings,exit0 (45.34s), before BF29 added. Existing atexit cleanup warning remains.

Four-adapter assignment scan found no remaining equivalent title/text/URL/surface-to-vendor promotion. Search text routing unchanged. npm audit --json exit0,0 vulnerabilities; pip_audit unavailable and not installed. git diff --check exit0.

Final CROSS_CHECK gate fails: _cross_check_memberships calls brand_match, which accepts title substring even when vendor differs; it sets brand_evidence_found=True and target_membership_product_ids for that competitor. BF29 calls the real discovery coroutine with mocked IO, target BrandA, explicit vendor BrandB, title Compatible con BrandA, incoming Vestidos membership. Actual target witness SKU10003569409 and brand_evidence_found=True. Expected no target membership evidence. Targeted BF29:1 failed,42 deselected,exit1 (0.46s). Exact evidence bf28_resolution_bf29_blocker.json.

STATE:BLOCKED. This supersedes earlier CROSS_CHECK=YES: earlier positive tests did not cover contradictory vendor. No change to search matcher or cross-check production after new RED. STOP per user; no commit/push/4MP/dependencies. Historical510 and unrelated changes preserved.


## BF29 resolution and final local gates

Cross-check/relevance now requires explicit exact target identity; absent/conflicting vendor never becomes a target witness through title/text/context. Applied same rule to hub/category target counts and confirmed-product summary. Facet application stores brand_context_hint rather than brand_evidence_found. Broad search matcher preserved.

BF29 absent/conflicting controls GREEN, positive BF18/BF19/BF22 preserved. BRAND-FIRST:44 passed,0 failed,exit0 (1.07s). Full pytest:276 passed,3 preexisting skipped,35 warnings,exit0 (38.22s). Nonfatal existing pytest atexit cleanup warning persists.

Final A/B/C/D scan is brand_agnostic_scan_final.json. Remaining C literals only affect existing routing/search, not product identity. All four adapters retain explicit fields; context stays separate. final_gates.json records test results, gate evidence, scoped source hashes and review. Prior RED reports retained chronologically as resolved history.

STATE:READY for scoped commit/push/remote verification. Historical510 remains accepted; no 4MP/dependencies/new architecture. Unrelated Dashboard/Search/Season unchanged.
