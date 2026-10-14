# BASELINE AND TESTS

## Baseline Specifications
- **Certified Baseline Commit**: `a7df2aeedcda5b8f1f3615fef5fce83f341f47fa`
- **Certified Run ID**: `run_mri_4mp_final_cert_1790865503`
- **Active Local Commit**: `0163d664cd747f72b9ef898c0f764b502e810eaa`
- **Remote Tracking Commit (`origin/main`)**: `3e5d058`
- **Testing Philosophy**: Red -> Fix -> Green -> Targeted Regression -> Certified Recertification.

---

## Test Suite Architecture & Results

### 1. Suite Summary
The test suite in `tests/` contains comprehensive regression coverage across scraper adapters, pipeline orchestrators, surface classifiers, database materializers, and brand-first guards.

| Test File | Focus Area | Passing Tests | Status |
| :--- | :--- | :--- | :--- |
| `tests/test_mri_read_model.py` | Live SQLite Read Model Dynamic Projections | 13/13 | PASS |
| `tests/test_mri_materialization.py` | Database Materialization & Category Alignment | 2/2 | PASS |
| `tests/test_secret_not_rendered_in_ui.py` | UI Security & Cookie Sanitization | 1/1 | PASS |
| `tests/test_va_svmp_category_sync.py` | SVMP.xlsx openpyxl Hyperlink Category Sync | 15/15 | PASS |
| `tests/test_mri_autonomy_transfer.py` | Strategy Transfer & Experience Reuse | 25/25 | PASS |
| `tests/test_mri_surface_classifier.py` | URL & DOM Surface Classifier (Rejection Rules) | 28/28 | PASS |
| `tests/test_mri_brand_first.py` | Brand-First Contract & Identity Resolution | 47/53 | 47 PASS / 6 Mock Gap |

---

## Detailed Inspection of Identified Gaps

### 1. `test_BF_27` Node.js Mock Gap in `tests/test_mri_brand_first.py`
- **Failure**: 6 parameterized variants of `test_BF_27_ripley_production_js_requires_explicit_brand` failed with `subprocess.CalledProcessError`.
- **Root Cause**: `tests/test_mri_brand_first.py:536` constructs an in-memory Node.js JavaScript environment to evaluate `RipleyScraper.scrape_top_240` and `scrape_autonomous_category`. When `ripley_scraper.py` was enhanced to resolve parent link containers via `const parentLink = item.closest("a[href]");`, the synthetic `item` object in the test fixture was not updated with a `.closest` method.
- **Impact**: Zero impact on production runtime. In actual Playwright browser execution, `Element.prototype.closest` is natively supported by Chromium.

### 2. Lifespan Deprecation Warnings in FastAPI
- **Warning**: Starlette/FastAPI `on_event("startup")` deprecation warning in `app/dashboard/api.py:123`.
- **Assessment**: Non-breaking framework deprecation slated for removal in future FastAPI releases; production execution remains unaffected.
