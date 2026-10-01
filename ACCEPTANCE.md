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

## Mercado Libre brand routing gate (MRI-ML-BRAND-ROUTING-001)

A Mercado Libre brand routing PASS requires:
- red_tests_reproduced = YES (4/4 initial tests failed)
- green_tests = PASS (6/6 passed)
- regression = PASS (59/59 passed)
- commercial_category_discovery = PASS (official store categories discovered)
- noncommercial_navigation_rejection = PASS (shipping address hub rejected)
- autonomous_category_navigation = PASS (navigated commercial category without manual URL)
- product_extraction = PASS (products observed > 0)
- direct_brand_evidence = PASS (brand evidence > 0)
- membership_evidence = PASS (surface provenance recorded)
- address_hub_false_positive = 0
- autoclaw_actions = 0
- manual_actions = 0
- synthetic_contribution = 0
- hardcoded_result_contribution = 0
- independent_verification = PASS
- reconciled = YES
- production_files_changed <= 3 (exact: 3)
- new_production_files = 0
- new_dependencies = 0
- pipeline_exit_code = 0

## Paris brand routing gate (MRI-PARIS-BRAND-ROUTING-001)

A Paris brand routing PASS requires:
- red_tests_reproduced = YES (4/4 initial tests failed)
- green_tests = PASS (5/5 passed)
- regression = PASS (70/70 passed across full test suite)
- commercial_category_discovery = PASS (Next.js App Router RSC facets discovered)
- noncommercial_navigation_rejection = PASS (account, help, outlet URLs rejected)
- autonomous_category_navigation = PASS (navigated commercial category via URL query routing without manual URL)
- product_extraction = PASS (products observed > 0)
- direct_brand_evidence = PASS (brand evidence > 0)
- membership_evidence = PASS (surface provenance recorded)
- mega_menu_false_positive = 0
- autoclaw_actions = 0
- manual_actions = 0
- synthetic_contribution = 0
- hardcoded_result_contribution = 0
- independent_verification = PASS
- reconciled = YES
- production_files_changed <= 3 (exact: 2)
- new_production_files = 0
- new_dependencies = 0
- pipeline_exit_code = 0

## Falabella entry gate (MRI-FALABELLA-ENTRY-001)

A Falabella entry PASS requires:
- blocker_reproduced = YES (CHALLENGE_PAGE reproduced on Playwright browser navigation)
- root_cause = EVIDENCED (Cloudflare WAF intercepts Playwright browser requests with HTTP 403)
- working_existing_strategy = EVIDENCED (F1 HTTP/response normal receives unblocked HTTP 200 with 1.97MB SSR document)
- red_tests_reproduced = YES (1/4 failed initially on entry)
- green_tests = PASS (4/4 passed)
- regression = PASS (74/74 passed across full test suite)
- guardrails = PASS (13/13 guardrails)
- navigation_success = YES
- commercial_page = YES
- challenge_detected = NO
- dom_usable = YES
- commercial_content_observed = YES (100 pods, 48 products in structured data)
- autoclaw_actions = 0
- manual_actions = 0
- synthetic_contribution = 0
- hardcoded_result_contribution = 0
- independent_verification = PASS
- reconciled = YES
- production_files_changed <= 2 (exact: 1)
- new_production_files = 0
- new_dependencies = 0
- pipeline_exit_code = 0

## Falabella brand routing gate (MRI-FALABELLA-BRAND-ROUTING-001)

A Falabella brand routing PASS requires:
- entry_regression = PASS
- mechanism_physically_observed = YES (__NEXT_DATA__.props.pageProps.facets)
- mechanism_reproducible = YES
- red_tests_reproduced = YES (2/4 initial tests failed)
- green_tests = PASS (4/4 passed)
- regression = PASS (78/78 passed across full test suite)
- guardrails = PASS (13/13 guardrails)
- commercial_route_discovery = PASS (22 routes discovered)
- route_acquisition = PASS (2 routes acquired)
- product_extraction = PASS (157 products observed)
- direct_brand_evidence = PASS (157/157 direct brand evidence items)
- membership_evidence = PASS (157/157 membership evidence items)
- commercial_routes_verified >= 1 (exact: 2)
- products_observed > 0 (exact: 157)
- direct_brand_evidence > 0 (exact: 157)
- membership_evidence > 0 (exact: 157)
- autoclaw_actions = 0
- manual_actions = 0
- synthetic_contribution = 0
- hardcoded_result_contribution = 0
- independent_verification = PASS
- reconciled = YES
- production_files_changed <= 3 (exact: 3)
- new_production_files = 0
- new_dependencies = 0
- pipeline_exit_code = 0

## Four-marketplace E2E certification gate (MRI-4MP-E2E-CERT-001)

A 4-marketplace E2E certification requires:
- execution_across_4_marketplaces = YES (ML, Paris, Ripley, Falabella)
- no_shared_session_state = YES
- production_files_changed = 0 (exact: 0)
- new_production_files = 0 (exact: 0)
- new_dependencies = 0 (exact: 0)
- autoclaw_actions = 0 (exact: 0)
- manual_actions = 0 (exact: 0)
- code_fix_cycles = 0 (exact: 0)
- hardcoded_result_contribution = 0 (exact: 0)
- synthetic_contribution = 0 (exact: 0)
- independent_recount_reconciled = 4/4
- false_pass_total = 0 (exact: 0)
- unsupported_fail_total = 0 (exact: 0)
- ml_verdict = E2E_MARKETPLACE_PASS (524 products observed, 524 brand confirmed)
- paris_verdict = E2E_MARKETPLACE_PASS (539 products observed, 539 brand confirmed)
- falabella_verdict = E2E_MARKETPLACE_PASS (249 products observed, 249 brand confirmed)
- ripley_verdict = E2E_MARKETPLACE_FAIL (0 products observed; HTTP 429 rate limit + unconstrained category routing)
- global_verdict = MRI_4MP_E2E_CERT_FAIL (3/4 PASS, 1/4 FAIL)
- first_global_blocker = RIPLEY_RATE_LIMIT_AND_UNFILTERED_CATEGORY_ZERO_BRAND
- next_smallest_task = TASK_ID: MRI-RIPLEY-RATE-LIMIT-AND-BRAND-FILTER-001

## VA SVMP Category Synchronization gate (VA-SVMP-CATEGORY-SYNC-001)

A VA SVMP category synchronization PASS requires:
- excel_real_used = YES (SVMP.xlsx)
- excel_sha256 = PRESENT (cbecc32e3e2d56c1455f05850305186141c02fad070919940d57630893db397c)
- excel_valid_categories > 0 (exact: 44)
- loader_categories == excel_valid_categories (44 == 44)
- runner_categories == excel_valid_categories (44 == 44)
- missing_valid_categories = 0
- unexplained_duplicates = 0
- new_or_previously_unprocessed_categories_identified = YES (Falabella: 4, Paris: 1, Ripley: 2, Total: 7 new)
- new_categories_loaded = YES
- new_categories_dispatched = YES
- scraper_receipt_demonstrated = YES
- hardcoded_category_contribution = 0
- regression = PASS (15/15 tests passing)
- production_files_changed <= 2 (exact: 2)
- new_production_files = 0
- new_dependencies = 0
- independent_reconciliation = PASS (difference = 0 across all 4 marketplaces)
- final_verdict = VA_SVMP_CATEGORY_SYNC_PASS

## Ripley Brand Filter & Schema Compatibility gate (MRI-RIPLEY-RATE-LIMIT-AND-BRAND-FILTER-001)

A Ripley brand filter & schema compatibility PASS requires:
- rate_limit_status = NOT_TRIGGERED
- brand_constraint_status = PASS
- causal_classification != UNKNOWN (exact: RIPLEY_CAUSE_BRAND_CONSTRAINT_LOSS_ONLY)
- first_causal_break = FACET_URL_BUILD_MECHANISM_SCHEMA_MISMATCH
- red_reproduced = YES (2/2 failed)
- green_pass = PASS (2/2 passed)
- regression_pass = PASS (94/94 passed across all suites)
- runtime_brand_propagation = PASS (verified with TEST_RUNTIME_BRAND, 0 hardcoding)
- commercial_route_discovered = YES
- brand_constraint_preserved = YES
- acquisition_success = YES
- routes_verified >= 1 (exact: 1)
- products_observed > 0 (exact: 48)
- direct_brand_evidence > 0 (exact: 48)
- membership_evidence > 0 (exact: 48)
- autoclaw_actions = 0 (exact: 0)
- manual_actions = 0 (exact: 0)
- synthetic_contribution = 0 (exact: 0)
- hardcoded_result_contribution = 0 (exact: 0)
- production_files_changed <= 2 (exact: 2)
- new_production_files = 0 (exact: 0)
- new_dependencies = 0 (exact: 0)
- fix_cycles = 1 (exact: 1)
- independent_verification = PASS
- reconciled = YES
- false_pass = 0
- pipeline_exit_code = 0
- final_verdict = MRI_RIPLEY_RATE_LIMIT_AND_BRAND_FILTER_PASS

## Four-marketplace E2E re-certification gate (MRI-4MP-E2E-CERT-002)

A 4-marketplace E2E re-certification requires:
- execution_across_4_marketplaces = YES (ML, Paris, Ripley, Falabella)
- no_shared_session_state = YES
- production_files_changed = 0 (exact: 0)
- new_production_files = 0 (exact: 0)
- new_dependencies = 0 (exact: 0)
- autoclaw_actions = 0 (exact: 0)
- manual_actions = 0 (exact: 0)
- code_fix_cycles = 0 (exact: 0)
- hardcoded_result_contribution = 0 (exact: 0)
- synthetic_contribution = 0 (exact: 0)
- independent_recount_reconciled = 4/4 (reconciled = YES)
- false_pass_total = 0 (exact: 0)
- unsupported_fail_total = 0 (exact: 0)
- paris_verdict = PASS (539 products observed, 539 brand confirmed)
- ripley_verdict = PASS (48 products observed, 48 brand confirmed, 0 rate limit, brand filter preserved)
- falabella_verdict = PASS (171 products observed, 171 brand confirmed)
- ml_verdict = FAIL (0 products observed; pagination blocked on Page 1 on fallback URL)
- global_verdict = MRI_4MP_E2E_CERT_FAIL (3/4 PASS, 1/4 FAIL)
- first_global_blocker = ML_PAGINATION_BLOCKED_ON_FALLBACK_URL
- next_smallest_task = TASK_ID: MRI-ML-PAGINATION-BLOCK-001

## Mercado Libre pagination and route acquisition gate (MRI-ML-PAGINATION-BLOCK-001)

A Mercado Libre pagination and route acquisition PASS requires:
- first_divergence_stage identified (exact: URL_TRANSFORMATION)
- causal_classification != ML_CAUSE_UNKNOWN (exact: ML_CAUSE_URL_TRANSFORMATION)
- first_causal_break demonstrated (unconditional URL rewriting to blocked search URL + carousel exclusion filter)
- red_reproduced = YES (2/2 failed)
- green_pass = PASS (2/2 passed)
- regression_pass = PASS (42/42 passed across regression suite)
- runtime_brand_propagation = PASS (verified with TEST_RUNTIME_BRAND, 0 hardcoding)
- ENTRY = PASS
- DISCOVERY = PASS
- NAVIGATION_ROUTING = PASS
- CATEGORY = PASS
- BRAND_DISCOVERY = PASS
- ACQUISITION = PASS
- PRODUCT_EXTRACTION = PASS
- IDENTITY = PASS
- MEMBERSHIP = PASS
- EVIDENCE = PASS
- VERIFICATION = PASS
- routes_verified >= 1 (exact: 1)
- products_observed > 0 (exact: 37)
- direct_brand_evidence > 0 (exact: 37)
- membership_evidence > 0 (exact: 37)
- autoclaw_actions = 0 (exact: 0)
- manual_actions = 0 (exact: 0)
- synthetic_contribution = 0 (exact: 0)
- hardcoded_result_contribution = 0 (exact: 0)
- production_files_changed <= 2 (exact: 1)
- new_production_files = 0 (exact: 0)
- new_dependencies = 0 (exact: 0)
- fix_cycles = 1 (exact: 1)
- independent_verification = PASS
- reconciled = YES
- false_pass = 0
- pipeline_exit_code = 0
- final_verdict = MRI_ML_PAGINATION_BLOCK_PASS

## Full autonomous audit and commercial dashboard materialization gate (MRI-FULL-AUTONOMOUS-AUDIT-AND-DASHBOARD-001)

A full autonomous audit and commercial dashboard materialization PASS requires:
- all 4 marketplaces traversed autonomously (Mercado Libre, Paris, Ripley, Falabella)
- 4/4 marketplace PASS
- ml_verdict = PASS (37 products observed, 37 direct brand evidence)
- paris_verdict = PASS (540 products observed, 540 direct brand evidence)
- ripley_verdict = PASS (96 products observed, 48 direct brand evidence)
- falabella_verdict = PASS (425 products observed, 425 direct brand evidence)
- global_unique_products > 0 (exact: 1098)
- global_direct_brand_evidence > 0 (exact: 1050)
- global_membership_evidence > 0 (exact: 2061)
- global_positions_materialized > 0 (exact: 1098)
- records_written > 0 (exact: 250)
- records_updated >= 0 (exact: 374)
- official SQLite database materialized (`data/sqlite/visibility.db`)
- dashboard MRI V2 updated via official `MRIReadModel` projection
- dashboard_updated = true
- dashboard_reconciled = true
- dashboard_mismatch_count = 0
- production_files_changed = 0
- new_production_files = 0
- new_dependencies = 0
- fix_cycles = 0
- autoclaw_actions = 0
- manual_actions = 0
- synthetic_contribution = 0
- hardcoded_result_contribution = 0
- manual_dashboard_contribution = 0
- independent_verification = PASS
- reconciled = true
- false_pass = 0
- unsupported_fail = 0
## Live dashboard materialization gate (MRI-DASHBOARD-LIVE-MATERIALIZATION-001)

A live dashboard materialization PASS requires:
- scraper_runs = 0
- marketplace_requests = 0
- autoclaw_actions = 0
- manual_marketplace_actions = 0
- field lineage demonstrated for CATEGORÍAS and COMPARACIÓN LEGACY
- run selection demonstrated
- research summary origin demonstrated
- position materialization demonstrated
- first_divergence_stage identified (`READ_MODEL`)
- causal_classification != DASHBOARD_CAUSE_UNKNOWN (`DASHBOARD_CAUSE_READ_MODEL_GAP`)
- red_tests_reproduced = YES (2/2 failed initially)
- green_tests = PASS (2/2 passed)
- regression = PASS (13/13 passed)
- production_files_changed <= 3 (exact: 1, `app/dashboard/mri_read_model.py`)
- new_production_files = 0
- new_dependencies = 0
- fix_cycles = 1
- dashboard regenerates dynamically from SQLite commercial tables
- CATEGORÍAS consumes live active materialization (62 categories) with active timestamps
- COMPARACIÓN LEGACY differentiates legacy baseline vs active MRI observations
- timestamps correspond to real evidence dates
- TopN materialized from valid observed positions
- reconciled = YES
- mismatch_count = 0
- stale_value_count = 0
- false_materialized_count = 0
- unsupported_topn_count = 0
- synthetic_contribution = 0
- hardcoded_result_contribution = 0
- manual_dashboard_contribution = 0
- final_verdict = MRI_DASHBOARD_LIVE_MATERIALIZATION_PASS

## Ripley frontier validation and closure gate (MRI-RIPLEY-FRONTIER-VALIDATION-001)

A Ripley frontier validation and closure PASS requires:
- baseline matches expected commit (`6890363254242619b518af4b86fc825de8a88863`)
- original frontier reconstructed from evidence (1269 discovered, 10 verified, 1259 pending)
- structural profile of 1259 pending nodes demonstrated (220 brand navigation, 177 non-commercial containers, 862 leaf categories)
- deterministic deduplication completed
- offline classification demonstrated without LLM veredict
- cluster grouping and bounded probing respected (marketplace_requests <= 24, actual: 6)
- root_cause != UNKNOWN (`RIPLEY_FRONTIER_CAUSE_GLOBAL_MENU_OVERDISCOVERY`)
- red_tests_reproduced = YES
- green_tests = PASS (75/75 passed)
- regression = PASS (75/75 passed)
- production_files_changed <= 2 (exact: 2, `category_discoverer.py`, `autonomous_pipeline.py`)
- new_production_files = 0
- new_dependencies = 0
- fix_cycles = 1
- clean Ripley certification run: exit_code = 0, products_observed > 0, direct_brand_evidence > 0, membership_evidence > 0
- discovered = terminal + pending
- pending = 0 (`frontier_remaining = 0`, `frontier_exhausted = true`)
- reconciled = true
- false_pass = 0
- synthetic_contribution = 0
- hardcoded_result_contribution = 0
- manual_classification_contribution = 0
- final_verdict = MRI_RIPLEY_FRONTIER_VALIDATION_PASS

## Autonomous Four-Marketplace Final Certification Gate (MRI-4MP-FINAL-E2E-CERT-001)

A final 4-marketplace certification PASS requires:
- baseline matches active baseline (`cd2c8fc9e2e640d69935ffae3853807e07853a1e`)
- execution sequence respected: Mercado Libre → Paris → Ripley → Falabella
- brand_runtime = Nicopoly passed dynamically without hardcoding
- single certified run ID: `run_mri_4mp_final_cert_1790865503`
- production code changes during certification = 0
- new production files = 0
- new dependencies = 0
- fix cycles = 0
- autoclaw actions = 0
- manual actions = 0
- 4/4 marketplaces exit_code = 0
- 4/4 marketplaces unique_products > 0 (ML: 321, Paris: 538, Ripley: 96, Falabella: 407)
- 4/4 marketplaces direct_brand_evidence > 0 (ML: 321, Paris: 538, Ripley: 48, Falabella: 407)
- 4/4 marketplaces membership_evidence > 0 (ML: 348, Paris: 1407, Ripley: 96, Falabella: 500)
- 4/4 marketplaces positions_materialized > 0 (ML: 321, Paris: 538, Ripley: 96, Falabella: 407)
- 4/4 marketplaces frontier reconciled = YES, pending = 0
- Ripley terminal accounting preserved: raw_discovered = 1435 = terminal (1435) + pending (0)
- official SQLite materialization completed: 1314 products materialized, 2303 categories, 2303 memberships, 1314 positions, 1314 evidence ledger records
- dashboard read model projection reconciled: mismatch_count = 0, stale RESEARCH_SUMMARY_NOT_MATERIALIZED recurrence = 0, stale 2026-09-21 dates = 0
- regression suite: 94/94 passing (0 failures)
- independent verification = PASS (0 false passes)
- final_verdict = MRI_4MP_FINAL_E2E_CERT_PASS

## Controlled Production Maintenance Transition Gate (VA-CONTROLLED-PRODUCTION-MAINTENANCE-001)

A transition to Controlled Production Maintenance PASS requires:
- certified baseline verified at commit `a7df2aeedcda5b8f1f3615fef5fce83f341f47fa`
- local SHA matches remote SHA exactly (`a7df2aeedcda5b8f1f3615fef5fce83f341f47fa`)
- certified commit confirmed as reachable ancestor
- 4-marketplace final certification evidence verified in `evidence/mri_4mp_final_e2e_cert_001/` (4/4 PASS, 0 pending, 94/94 regression PASS)
- project phase transition declared: `CONTROLLED_PRODUCTION_MAINTENANCE`
- build phase declared: `CLOSED`
- architecture declared: `FROZEN`
- zero speculative features or unbudgeted fixes permitted
- production code changes during transition = 0
- new dependencies = 0
- maintenance policy persisted in `evidence/va_controlled_production_maintenance_001/maintenance_policy.json`
- health check contract persisted in `evidence/va_controlled_production_maintenance_001/health_check_contract.json`
- incident contract persisted in `evidence/va_controlled_production_maintenance_001/incident_contract.json`
- final verdict = `VA_CONTROLLED_PRODUCTION_MAINTENANCE_PASS`

## Global completion

- required marketplaces meet their own acceptance gates (4/4 PASS: Mercado Libre, Paris, Falabella, Ripley)
- no unresolved required discovery/acquisition blocker
- no unprocessed viable frontier required by the declared coverage contract (Ripley frontier_remaining = 0)
- final evidence is reproducible from persisted artifacts
- system operates under controlled production maintenance with zero modifications without failure evidence







