# MRI-022 TRUTH REPAIR DELIVERY REPORT
**Date:** 2026-10-19  
**Task ID:** MRI-EXECUTION-RECOVERY-024 (Trabajo A: Cierre de MRI-022)  
**Implementer:** ANTIGRAVITY  
**Auditor:** CODEX  
**Branch:** `fix/mri-truth-repair-022`  
**Commit SHA:** `061201b40fb251701d63cb209bf4b425dd1fe791`  
**Parent Baseline:** `274005dbef951392d0952253522f645a723b0af4` (feature/mri-autonomy-truth-repair-021)

---

## 1. Executive Summary & Objective

In accordance with `MRI-EXECUTION-RECOVERY-024` and the independent audit findings from `MRI-CODEX-TRUTH-VALIDATION-022`, all material defects identified in MRI-022 have been systematically resolved and verified on branch `fix/mri-truth-repair-022`:
1. **Pre-connect SQLite barrier:** Enforced immediate pre-connect verification of `db_path` right before any SQLite connection across runners, preventing late post-constructor retargeting from touching production.
2. **Elimination of static counts:** Scraper failures on Ripley or other marketplaces strictly record 0 publications, empty category/seller lists, and preserve genuine failure diagnostic causes without attributing synthetic catalog numbers (e.g. 772/772).
3. **Provenance fidelity:** Real acquisition methods are preserved faithfully (e.g. Mercado Libre headless scraper is persisted as `MELI_HEADLESS_CATALOG_SCRAPER` and `LIVE_OBSERVATION` rather than misrepresenting public scraping as `OFFICIAL_MELI_API`).
4. **Scoped API projections:** The `/api/multimarketplace/summary` dashboard endpoint strictly scopes publication and category queries to the requested `target_run_id`, preventing leakage of global table dumps across distinct runs.
5. **Sandbox reproduction & offline validation:** All counterexamples from Codex 022 in `evidence/mri_codex_truth_validation_022/` were reproduced and verified offline.

---

## 2. Defects Resolved & Verifiable Evidence

### Defect 1: Validation of `db_path` immediately before SQLite connection
- **Issue:** `StorageConfig.assert_write_allowed(self.db_path)` was called only in the runner `__init__`. A subsequent retarget (`runner.db_path = "data/sqlite/visibility.db"`) could reach `sqlite3.connect` during `execute_autonomous_order()`.
- **Resolution:**
  - Placed `StorageConfig.assert_write_allowed(self.db_path)` as the absolute first statement in `AutonomousMultiMarketplaceRunner.execute_autonomous_order()`, before any connection or operation.
  - Added `connect_sqlite` guard helper in `app/mri_autonomous/storage_guard.py`.
- **Evidence:** Running the AST slice probe in `validate_offline.py` triggers `ProductionWriteBlockedError` directly on `execute_autonomous_order()` before `sqlite3.connect` sentinel can ever be reached (`calls = []`).

### Defect 2 & 3: Elimination of static counts & faithful status propagation
- **Issue:** On Ripley acquisition failure, the runner asserted a constant 772 brand publications, 3 categories, and forced a generic `COMPLETED` or `PARTIAL` without capturing whether failure was WAF/Turnstile or local failure.
- **Resolution:**
  - In `investigate_ripley()`, implemented regex discrimination for WAF (`\b(waf|turnstile|challenge|403|captcha|cloudflare)\b` while excluding `"not_waf"`).
  - On failure, sets `total_brand_publications = 0`, `total_official_seller_publications = 0`, `categories_found = []`, `sellers_found = []`, captures genuine blocker in `evidence["failure_cause"]`, and persists `terminal_state = "SOURCE_BLOCKED"` (if WAF) or `"PARTIAL"`.
- **Evidence:** `probe_ripley.py` executed with `AUDIT_LOCAL_FAILURE_NOT_WAF` produces:
  - `status: PARTIAL`
  - `publications: 0`
  - `categories: 0`
  - `evidence.failure_cause: Ripley acquisition failed (RuntimeError): AUDIT_LOCAL_FAILURE_NOT_WAF`

### Defect 4: Scoped category & publication queries in dashboard API
- **Issue:** `/api/multimarketplace/summary` fetched total counts from global `mri_categories`, returning category counts even when querying non-existent run `AUDIT_NO_SUCH_RUN`. In addition, it forced `OPERATIONAL` status even when a run was recorded as `BLOCKED`.
- **Resolution:**
  - Modified `app/mri_dashboard/mri_api.py` to query categories and publications strictly filtered by `target_run_id` (via joins with `mri_publications` and `mri_historical_publications`).
  - Prohibited overriding terminal states when persisted status is `BLOCKED`, `SOURCE_BLOCKED`, `PARTIAL`, or `FAILED`.
- **Evidence:**
  - Query for `run_id=AUDIT_NO_SUCH_RUN` returns 0 categories across all 4 marketplaces (`categories_count: 0`).
  - Query for a run marked `BLOCKED` returns `status: BLOCKED` without overriding to `OPERATIONAL`.

### Defect 5: Acquisition method provenance in Mercado Libre
- **Issue:** Mercado Libre headless scraper executions were unconditionally recorded as `source_method = "OFFICIAL_MELI_API"`.
- **Resolution:**
  - Updated `MeliTaxonomyEngine.persist_to_mri_sqlite` and runner to accept `execution_mode` and `source_method` parameters.
  - Persists `MELI_HEADLESS_CATALOG_SCRAPER` and `LIVE_OBSERVATION` with genuine observation IDs (`MELI-OBS-...`).
- **Evidence:** Verified in SQLite schema and runner invocation.

---

## 3. Preservation of Protected Resources

All five protected production files remain completely unchanged:
- `data/sqlite/visibility.db`
- `data/mri_experience.db`
- `data/experience.db`
- `data/mri_history.json`
- `data/mri_categories.json`

Zero synthetic data was introduced. No historical records were retroactively altered or falsely claimed as verified.

---

## 4. Test Suite Verification

- `tests/test_mri_autonomous_operation_019.py`: **PASSED** (3/3)
- `tests/test_mri_4mp_certifier_semantics.py`: **PASSED** (9/9)
- `tests/test_regression_guardrails.py`: **PASSED** (13/13)
- `tests/test_mri_brand_first.py`: **PASSED** (44/44)
- `tests/test_mri_critical_closure_015.py`: **PASSED** (6/6)
- `tests/test_mri_falabella_entry.py`: **PASSED** (4/4)

---

## 5. Artifact Delivery for Independent Audit

- **Delivery Branch:** `fix/mri-truth-repair-022`
- **Delivery Commit SHA:** `061201b40fb251701d63cb209bf4b425dd1fe791`
- **Verification package:** Ready for Codex independent audit.
