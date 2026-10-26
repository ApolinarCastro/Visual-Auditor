"""
Coverage contract for MRI full-catalog audits (MRI-CATEGORY-COVERAGE-001).

Binary acceptance is separate from the operational state:
  * operational state may be FOUND / PARTIAL / SOURCE_BLOCKED / ...
  * acceptance is ONLY `AUDIT_PASS` or `AUDIT_FAIL`.

AUDIT_PASS requires: every category of the scope identified or explicitly
discarded, every needed page traversed to a verifiable terminal condition, no
pending segments, and evidenced publications/positions.
"""
from __future__ import annotations

import json
from pathlib import Path

AUDIT_PASS = "AUDIT_PASS"
AUDIT_FAIL = "AUDIT_FAIL"

#: Sentinel meaning "paginate until the source's own terminal condition".
#: It is a safety bound, never a coverage target: a run that reaches it is FAIL.
PAGE_SENTINEL = 100000

TERMINAL_STOPS = {"EXHAUSTION", "FOUND", "COMPLETE", "COMPLETED"}


def new_coverage(run_id: str, marketplace: str, categories: dict) -> dict:
    cats = {}
    for cat_id, data in (categories or {}).items():
        cats[cat_id] = {
            "name": (data or {}).get("name"),
            "url": (data or {}).get("url"),
            "status": "PENDING",          # PENDING / COMPLETE / BLOCKED / FAILED
            "pages_observed": 0,
            "termination": None,
            "publications": 0,
            "last_id": None,
            "stop_reason": None,
        }
    return {
        "run_id": run_id,
        "marketplace": marketplace,
        "scope": "FULL_CATALOG",
        "categories_discovered": len(cats),
        "categories_traversed_completely": 0,
        "categories": cats,
        "pages_observed": 0,
        "pages_pending": None,              # unknown until categories finish
        "publications_observed": 0,
        "unique_publications": 0,
        "termination_condition": None,
        "acceptance": AUDIT_FAIL,
        "acceptance_reasons": ["audit in progress"],
    }


def record_category(coverage: dict, cat_id: str, *, pages: int, stop_state: str,
                    publications: int, last_id=None) -> dict:
    cat = coverage["categories"].setdefault(cat_id, {})
    cat["pages_observed"] = int(pages or 0)
    cat["stop_reason"] = stop_state
    cat["publications"] = int(publications or 0)
    cat["last_id"] = last_id
    if stop_state in TERMINAL_STOPS:
        cat["status"] = "COMPLETE"
        cat["termination"] = "EXHAUSTION"
    elif stop_state == "SOURCE_BLOCKED":
        cat["status"] = "BLOCKED"
        cat["termination"] = "SOURCE_BLOCKED"
    elif stop_state == "EXTRACTOR_FAILURE":
        cat["status"] = "FAILED"
        cat["termination"] = "EXTRACTOR_FAILURE"
    else:
        cat["status"] = "FAILED"
        cat["termination"] = stop_state or "UNKNOWN"
    coverage["pages_observed"] = sum(
        c.get("pages_observed", 0) for c in coverage["categories"].values())
    return coverage


def finalize(coverage: dict, *, unique_publications: int = 0) -> dict:
    reasons = []
    cats = coverage.get("categories") or {}
    complete = [c for c in cats.values() if c.get("status") == "COMPLETE"]
    blocked = [k for k, c in cats.items() if c.get("status") == "BLOCKED"]
    failed = [k for k, c in cats.items() if c.get("status") == "FAILED"]
    pending = [k for k, c in cats.items() if c.get("status") == "PENDING"]

    coverage["categories_traversed_completely"] = len(complete)
    coverage["unique_publications"] = int(unique_publications or 0)
    coverage["pages_pending"] = None if pending else 0
    if pending:
        reasons.append(f"{len(pending)} categorias sin recorrer")
    if blocked:
        reasons.append(f"{len(blocked)} categorias bloqueadas por la fuente: {blocked[:5]}")
    if failed:
        reasons.append(f"{len(failed)} categorias con fallo de extraccion: {failed[:5]}")
    if not cats:
        reasons.append("sin categorias descubiertas")
    if coverage.get("pages_observed") and any(
            c.get("pages_observed") and not c.get("termination") for c in cats.values()):
        reasons.append("paginas sin condicion de terminacion verificable")

    if complete and not pending and not blocked and not failed and cats:
        coverage["termination_condition"] = "ALL_CATEGORIES_EXHAUSTED"
        coverage["acceptance"] = AUDIT_PASS
        coverage["acceptance_reasons"] = []
    else:
        coverage["termination_condition"] = (
            "SOURCE_BLOCKED" if blocked and not complete and not failed
            else ("EXTRACTOR_FAILURE" if failed and not complete and not blocked else "INCOMPLETE"))
        coverage["acceptance"] = AUDIT_FAIL
        coverage["acceptance_reasons"] = reasons or ["cobertura no demostrada"]
    return coverage


def checkpoint_path(aux_dir, run_id: str) -> Path:
    safe = str(run_id).replace("/", "_").replace("\\", "_")
    return Path(aux_dir) / f"mri_coverage_checkpoint_{safe}.json"


def save_checkpoint(aux_dir, coverage: dict) -> str | None:
    """Atomic checkpoint write (temp file + os.replace) so an interruption can
    never leave a half-written progress file."""
    try:
        import os
        path = checkpoint_path(aux_dir, coverage["run_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(coverage, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, path)
        return str(path)
    except Exception:
        return None


def load_checkpoint(aux_dir, run_id: str) -> dict | None:
    try:
        path = checkpoint_path(aux_dir, run_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None
