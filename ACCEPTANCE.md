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

## Global completion


- required marketplaces meet their own acceptance gates
- no unresolved required discovery/acquisition blocker
- no unprocessed viable frontier required by the declared coverage contract
- final evidence is reproducible from persisted artifacts
