# CURRENT OPERATIONAL STATE

## Metadata & Task Control
- **Task ID**: `VA-4MP-REVERSE-ACQUISITION-001`
- **Project**: Visual Auditor / MRI (Marketplace Research Intelligence)
- **Phase**: CONTROLLED_PRODUCTION_MAINTENANCE (BUILD PHASE CLOSED, ARCHITECTURE FROZEN)
- **Execution Mode**: `FORENSIC → REUSE → EXECUTE → RECONCILE → CLOSE`
- **Executor**: Antigravity / OpenCode
- **Date**: 2026-10-14T08:48:00-03:00
- **Operational Scope**: Mercado Libre Chile, Falabella Chile, Paris Chile, Ripley Chile
- **Brand Target**: Nicopoly

---

## Git State & Cryptographic Lineage
- **Certified Baseline SHA**: `a7df2aeedcda5b8f1f3615fef5fce83f341f47fa`
  - *Milestone*: `MRI-4MP-FINAL-E2E-CERT-001` (Full autonomous certification across 4 marketplaces)
- **Remote SHA (`origin/main`)**: `3e5d058`
  - *Commit Title*: `docs: Add forensic evidence verification report`
- **Local HEAD SHA**: `0163d664cd747f72b9ef898c0f764b502e810eaa`
  - *Commit Title*: `feat(mri): implement autonomous category identification and update dashboard (MRI-AUTONOMOUS-CATEGORY-IDENTIFICATION-005)`
- **Unpushed Local Commits (4 commits ahead of origin/main)**:
  1. `98794a1`: `feat(mri): implement autonomous category discovery pilot (MRI-MARKETPLACE-CATEGORY-DISCOVERY-001)`
  2. `ac3de1c`: `feat(mri): implement category manager and dashboard filters (MRI-CATEGORY-ACQUISITION-RECOVERY-003)`
  3. `7fd1305`: `feat(mri): implement autonomous search fallback for category manager (MRI-AUTONOMOUS-END-TO-END-004)`
  4. `0163d66`: `feat(mri): implement autonomous category identification and update dashboard (MRI-AUTONOMOUS-CATEGORY-IDENTIFICATION-005)`

---

## First Demonstrated Operational Blockers
Forensic evidence collected across runtime logs, test runs, and static code inspection identifies the following distinct blockers:

### 1. Primary Runtime Blocker — AttributeError in Dashboard API (`/api/learning`)
- **Location**: `app/mri_dashboard/mri_api.py:69`
- **Demonstrated Error**:
  ```python
  AttributeError: 'ExperienceStore' object has no attribute '_get_conn'
  ```
- **Forensic Causality**: `app/mri_dashboard/mri_api.py` called `store._get_conn()`, but the canonical method in `app/mri_autonomous/experience_store.py:15` is `_get_connection()`. Furthermore, line 72 attempted to query `identity_experiences`, which does not exist in `data/mri_experience.db` (the active experience table is `experience`, housing 2,522 validated records). This caused HTTP 500 when the dashboard loaded learning metrics.
- **Remediation**: Use `store._get_connection()` and query the canonical `experience` table.

### 2. Iteration Mutation Blocker — Dictionary Changed Size During Discovery Sweep
- **Location**: `app/mri_dashboard/mri_runner.py:356`
- **Demonstrated Error**:
  ```python
  RuntimeError: dictionary changed size during iteration
  ```
- **Forensic Causality**: In `mri_runner.py`, `for cat_id, cat_data in cats.items():` iterated over the live dictionary while `category_manager.register_category()` dynamically appended newly discovered subcategories into `cats`, mutating the hash table during traversal.
- **Remediation**: Iterate over a frozen snapshot `list(cats.items())`.

### 3. Unit Test Fixture Gap — Node Execution Mock Missing `.closest()`
- **Location**: `tests/test_mri_brand_first.py:545` (`test_BF_27`)
- **Demonstrated Error**: `subprocess.CalledProcessError: Command '['node', '-e', ...]` failed because `ripley_scraper.py` introduced `item.closest("a[href]")`, but the inline Node.js DOM mock object in the test lacked a `.closest` method.
- **Remediation**: Add `closest: (sel) => null` to the test mock fixture.

---

## Operating Governance Rules Enforced
1. **Headless Exclusivity**: Mercado Libre, Falabella, and Paris execute strictly under Playwright `headless=True`. No visible GUI windows permitted in production.
2. **Deterministic Speed Controls**: Page pagination delays enforced at `0.8s – 1.2s`.
3. **Evidence Integrity**: `SOURCE_BLOCKED` is never classified as `NOT_FOUND`.
4. **Preservation of Certified Experience**: Proven mechanisms (e.g., Falabella F1 HTTP SSR, Paris streaming RSC, Ripley URL_QUERY) must be executed before any rediscovery.
5. **Zero External Paid Services**: No Apify actors, proxy vendors, or external paid APIs. External cost strictly = $0.00.
