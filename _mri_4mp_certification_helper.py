import sys
import os
import time
import json
import subprocess
from datetime import datetime
from pathlib import Path

# --- Configuration ---
# Certification baseline: default = certified core baseline (db3c638); a
# fixed-fix certification declares its frozen baseline via env
# VA_MRI_CERT_EXPECTED_HEAD (VA-MRI-4MP-E2E-FAILURE-RESOLUTION-001).
EXPECTED_HEAD = os.environ.get("VA_MRI_CERT_EXPECTED_HEAD",
                               "db3c63808360c767ba1e3ce43e0fceba67160a75")
BRAND = "NICOPOLY"
MARKETPLACES = ["Mercado Libre", "Paris", "Falabella", "Ripley"]

# Timeouts
MARKETPLACE_TIMEOUT = 1200  # 20 minutes per marketplace
GLOBAL_TIMEOUT = 4800       # 80 minutes total

VA_REFERENCE = {
    "Mercado Libre": 12,
    "Paris": 8,
    "Falabella": 9,
    "Ripley": 14
}

# Exit Codes
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_PRECHECK_BLOCKED = 2
EXIT_TIMEOUT = 3
EXIT_RUNTIME_ERROR = 4
EXIT_PARTIAL = 5

def run_cmd(cmd: list) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout.strip()

def check_cmd(cmd: list) -> int:
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode


def run_precheck():
    print("[PRECHECK] Checking Git state...")
    try:
        branch = run_cmd(["git", "branch", "--show-current"])
        head = run_cmd(["git", "rev-parse", "HEAD"])
        status = run_cmd(["git", "status", "--porcelain"])
        diff_head = run_cmd(["git", "diff", "--name-only", EXPECTED_HEAD, "HEAD"])
    except subprocess.CalledProcessError as e:
        print(f"[PRECHECK] Git command failed: {e}")
        sys.exit(EXIT_PRECHECK_BLOCKED)

    print(f"  Branch: {branch}")
    print(f"  HEAD: {head}")
    
    # 1. Baseline is ancestor
    if check_cmd(["git", "merge-base", "--is-ancestor", EXPECTED_HEAD, "HEAD"]) != 0:
        print(f"[PRECHECK] FAIL: {EXPECTED_HEAD} is not an ancestor of HEAD.")
        print("[PRECHECK] STATUS = BLOCKED")
        sys.exit(EXIT_PRECHECK_BLOCKED)

    # 2. Critical files are not modified in git history since baseline (except runner)
    CRITICAL_PATHS = ["app/mri_autonomous", "app/scrapers", "run_mri_4mp_certification.bat"]
    RUNNER_FILES = ["_mri_4mp_certification_helper.py", "run_mri_4mp_certification.bat"]

    for changed_file in diff_head.splitlines():
        if not changed_file:
            continue
        if changed_file in RUNNER_FILES:
            continue
        for cp in CRITICAL_PATHS:
            if changed_file.startswith(cp):
                print(f"[PRECHECK] FAIL: Critical file modified in history since baseline: {changed_file}")
                sys.exit(EXIT_PRECHECK_BLOCKED)

    # 3. Critical files and runner files are not modified locally (uncommitted changes)
    for line in status.splitlines():
        if not line:
            continue
        # ignore untracked files for critical file check
        is_untracked = line.startswith("?? ")
        
        filepath = line[3:].split(" -> ")[-1].strip()
        
        # We don't want the runner files modified locally AT ALL (even untracked? well, they are tracked now)
        if filepath in RUNNER_FILES and not is_untracked:
            print(f"[PRECHECK] FAIL: Runner file modified locally: {filepath}")
            sys.exit(EXIT_PRECHECK_BLOCKED)
            
        if not is_untracked:
            for cp in CRITICAL_PATHS:
                if filepath.startswith(cp):
                    print(f"[PRECHECK] FAIL: Critical MRI file modified locally: {filepath}")
                    sys.exit(EXIT_PRECHECK_BLOCKED)

    print(f"  Preexisting Changes:\n{status}")
    print("[PRECHECK] Git OK.")

    print("[PRECHECK] Checking Runtime...")
    if not os.path.exists("_mri_autonomous_run.py"):
        print("[PRECHECK] FAIL: _mri_autonomous_run.py not found.")
        sys.exit(EXIT_PRECHECK_BLOCKED)
    print("[PRECHECK] Runtime OK.")

    print("[PRECHECK] Checking Skills...")
    if not os.path.exists("AGENTS.md"):
        print("[PRECHECK] FAIL: AGENTS.md not found.")
        sys.exit(EXIT_PRECHECK_BLOCKED)
    if not os.path.exists("skills/MRI_MANDATORY_SKILLS.json"):
        print("[PRECHECK] FAIL: skills/MRI_MANDATORY_SKILLS.json not found.")
        sys.exit(EXIT_PRECHECK_BLOCKED)
    print("[PRECHECK] Skills OK.")

    return status

def slugify(text: str) -> str:
    return text.lower().replace(" ", "_")

def count_lines(filepath):
    if not os.path.exists(filepath):
        return 0
    with open(filepath, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def extract_marketplace_metrics(mkt_dir: str) -> dict:
    """VA-MRI-4MP-E2E-FAILURE-RESOLUTION-001: read the REAL artifacts of one marketplace run.

    The run artifacts live in a NESTED directory (<outroot>/<run_id>/); extract
    COVERAGE_STATUS, recount, frontier accounting (RAW vs RELEVANT), budget
    remainder, SOURCE_BLOCKED signals and evidence sufficiency from files only.
    """
    import re as _re
    from pathlib import Path as _P
    base = _P(mkt_dir)
    out = {"found_artifacts": {}, "coverage_status": None, "stop_reason_hint": None,
           "recount": None, "raw_frontier_remaining": None, "relevant_frontier_remaining": None,
           "relevant_pending_work": None, "source_blocked_count": 0, "not_found_count": 0,
           "evidence_count": 0, "evidence_sufficient": False, "notes": []}

    candidates = [qp.parent for qp in base.glob("*/run_manifest.json")]
    if (base / "run_manifest.json").exists():
        candidates.append(base)
    if not candidates:
        out["notes"].append("no run_manifest.json found under outroot")
        return out
    run_dir = max(candidates, key=lambda q: q.stat().st_mtime)
    out["found_artifacts"]["run_dir"] = str(run_dir)

    try:
        sub = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        out["recount"] = sub.get("recount")
        out["run_id"] = sub.get("run_id")
    except Exception as e:
        out["notes"].append("run_manifest parse failed: %s" % e)

    cov = None
    fr = run_dir / "final_report.md"
    if fr.exists():
        out["found_artifacts"]["final_report"] = True
        text = fr.read_text(encoding="utf-8", errors="ignore")
        m = _re.search(r"STOP:\s*([A-Z_]+)\s*\(categories:\s*(\d+),\s*timeouts:\s*(\d+)\)", text)
        if m:
            cov = m.group(1)
            out["stop_reason_hint"] = "%s (categories=%s, timeouts=%s)" % (m.group(1), m.group(2), m.group(3))
    ev = run_dir / "events.jsonl"
    if ev.exists():
        out["found_artifacts"]["events"] = True
        if cov is None:
            for line in ev.read_text(encoding="utf-8", errors="ignore").splitlines():
                if '"DISCOVERY_END"' in line:
                    try:
                        cov = json.loads(line).get("status") or cov
                    except Exception:
                        pass
    out["coverage_status"] = cov

    raw = rel = 0
    blocked = 0
    tx = run_dir / "taxonomy.json"
    if tx.exists():
        out["found_artifacts"]["taxonomy"] = True
        try:
            cats = json.loads(tx.read_text(encoding="utf-8"))
            from app.mri_autonomous.category_discoverer import frontier_relevance_accounting
            acc = frontier_relevance_accounting(cats)
            raw += int(acc["raw_frontier_remaining"])
            rel += int(acc["relevant_frontier_remaining"])
            blocked += sum(1 for c in cats if c.get("coverage_status") == "BLOCKED")
        except Exception as e:
            out["notes"].append("taxonomy accounting failed: %s" % e)

    fl = run_dir / "failures.json"
    if fl.exists():
        out["found_artifacts"]["failures"] = True
        try:
            fj = json.loads(fl.read_text(encoding="utf-8"))
            notes = " | ".join(fj.get("evidence_notes", []) or [])
            m = _re.search(r"raw=(\d+),\s*relevant=(\d+)", notes)
            if m:
                raw += int(m.group(1))
                rel += int(m.group(2))
            blocked += len(_re.findall(r"BLOCKED", notes))
            out["not_found_count"] += len(_re.findall(r"NOT_FOUND", notes))
        except Exception as e:
            out["notes"].append("failures parse failed: %s" % e)

    out["raw_frontier_remaining"] = raw
    out["relevant_frontier_remaining"] = rel
    out["relevant_pending_work"] = bool(rel > 0)
    out["source_blocked_count"] = blocked

    recount = out.get("recount") or {}
    out["evidence_count"] = sum(int(recount.get(k) or 0) for k in
                                ("RAW_OBSERVATIONS", "NORMALIZED_OBSERVATIONS",
                                 "PUBLICATIONS", "MEMBERSHIPS"))
    out["evidence_sufficient"] = bool(out["recount"] is not None and cov is not None
                                      and out["found_artifacts"].get("taxonomy", False))
    return out


def classify_marketplace_semantics(metrics: dict, *, process_exit_code: int,
                                   timed_out: bool) -> dict:
    """Semantic status from PROCESS_RESULT + COVERAGE + RELEVANT_PENDING_WORK +
    STOP_REASON + SOURCE_BLOCKED + EVIDENCE. The process exit code alone is NEVER
    sufficient for PASS. SOURCE_BLOCKED is never converted to NOT_FOUND."""
    if timed_out:
        return {"STATUS": "FAIL",
                "reason": "TIMEOUT: process killed; no semantic completion"}
    if not metrics.get("evidence_sufficient"):
        return {"STATUS": "UNKNOWN",
                "reason": "insufficient artifacts to demonstrate coverage (never PASS by default)"}
    cov = metrics.get("coverage_status")
    rel = metrics.get("relevant_pending_work")
    if cov == "BLOCKED":
        return {"STATUS": "BLOCKED",
                "reason": "coverage BLOCKED (source blocked / incomplete); distinct from NOT_FOUND"}
    if rel is True:
        return {"STATUS": "PARTIAL",
                "reason": "PARTIAL with RELEVANT_PENDING_WORK>0"}
    if cov == "CONFIRMED":
        return {"STATUS": "PASS",
                "reason": "CONFIRMED with RELEVANT_PENDING_WORK=0"}
    if cov == "PARTIAL" and rel is False:
        return {"STATUS": "PASS", "qualifier": "RELEVANT_SCOPE_COMPLETE",
                "reason": "PARTIAL resolved by termination contract: relevant scope complete "
                          "(RELEVANT_PENDING_WORK=0); not decided by the word PARTIAL"}
    if process_exit_code not in (0,) and cov is None:
        return {"STATUS": "FAIL", "reason": "process failed with no semantic artifacts"}
    return {"STATUS": "UNKNOWN",
            "reason": "unresolved semantics (coverage=%s, relevant=%s)" % (cov, rel)}


def main():
    try:
        pre_status = run_precheck()
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        print(f"[PRECHECK] Unhandled exception: {e}")
        sys.exit(EXIT_RUNTIME_ERROR)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = Path(f"outputs/mri_4mp_certification/{run_id}")
    out_root.mkdir(parents=True, exist_ok=True)
    
    global_start = time.time()
    
    manifest = {
        "run_id": run_id,
        "global_start_time": datetime.now().isoformat(),
        "marketplaces": {},
        "va_reference_summary_inconsistency": True,
        "preexisting_changes_preserved": True,
        "autoclaw_runtime_usage": 0,
        "antigravity_runtime_usage": 0,
        "manual_navigation": 0,
        "manual_fixes": 0,
        "launcher": sys.executable,
        "pid": os.getpid(),
        "global_status": "UNKNOWN",
        "marketplace_timeout_seconds": MARKETPLACE_TIMEOUT,
        "global_timeout_seconds": GLOBAL_TIMEOUT,
    }

    all_stdout_log = out_root / "stdout.log"
    all_stderr_log = out_root / "stderr.log"

    print(f"\n[RUNNER] Output directory: {out_root}")
    
    global_fail = False
    global_partial = False
    global_unknown = False
    
    for mkt in MARKETPLACES:
        elapsed_global = time.time() - global_start
        if elapsed_global > GLOBAL_TIMEOUT:
            print(f"\n[RUNNER] GLOBAL TIMEOUT EXCEEDED before starting {mkt}")
            manifest["global_status"] = "TIMEOUT"
            sys.exit(EXIT_TIMEOUT)

        print(f"\n[RUNNER] Starting {mkt}...")
        mkt_slug = slugify(mkt)
        mkt_dir = out_root / mkt_slug
        mkt_dir.mkdir(parents=True, exist_ok=True)
        
        mkt_start = time.time()
        mkt_start_iso = datetime.now().isoformat()
        
        cmd = [
            sys.executable, "_mri_autonomous_run.py", "marketplace-e2e",
            "--mkt", mkt,
            "--outroot", str(mkt_dir),
            "--run-id", f"{run_id}_{mkt_slug}"
        ]
        
        mkt_status = "UNKNOWN"
        stop_reason = "UNKNOWN"
        coverage = "UNKNOWN"
        
        mkt_stdout = mkt_dir / "stdout.log"
        mkt_stderr = mkt_dir / "stderr.log"
        
        process_timeout = False
        try:
            with open(mkt_stdout, "w", encoding="utf-8") as fout, open(mkt_stderr, "w", encoding="utf-8") as ferr:
                proc = subprocess.run(cmd, stdout=fout, stderr=ferr, timeout=MARKETPLACE_TIMEOUT)
                retcode = proc.returncode
        except subprocess.TimeoutExpired:
            print(f"[RUNNER] MARKETPLACE TIMEOUT on {mkt}")
            retcode = 1
            process_timeout = True
            stop_reason = "TIMEOUT"
            mkt_status = "FAIL"
            coverage = "BLOCKED"
        except Exception as e:
            print(f"[RUNNER] Runtime error running {mkt}: {e}")
            retcode = 1
            stop_reason = "RUNTIME_ERROR"
            mkt_status = "FAIL"
            coverage = "FAIL"

        mkt_duration = time.time() - mkt_start
        
        with open(all_stdout_log, "a", encoding="utf-8") as fa, open(mkt_stdout, "r", encoding="utf-8") as fr:
            fa.write(fr.read())
        with open(all_stderr_log, "a", encoding="utf-8") as fa, open(mkt_stderr, "r", encoding="utf-8") as fr:
            fa.write(fr.read())

        # VA-MRI-4MP-E2E-FAILURE-RESOLUTION-001: artifact-based semantic certification.
        # PASS must NEVER be derived from the process exit code alone.
        metrics = extract_marketplace_metrics(str(mkt_dir))
        verdict = classify_marketplace_semantics(metrics, process_exit_code=retcode,
                                                 timed_out=process_timeout)
        mkt_status = verdict["STATUS"]
        coverage = metrics.get("coverage_status") or "UNKNOWN"
        if metrics.get("stop_reason_hint"):
            stop_reason = metrics.get("stop_reason_hint")
        _recount = metrics.get("recount") or {}
        pubs = _recount.get("PUBLICATIONS", "UNKNOWN")
        cats = _recount.get("TAXONOMY_NODES", "UNKNOWN")
        memberships = _recount.get("MEMBERSHIPS", "UNKNOWN")
        semantic_reason = verdict.get("reason", "")

        if mkt_status in ("FAIL", "BLOCKED"):
            global_fail = True
        elif mkt_status == "PARTIAL":
            global_partial = True
        elif mkt_status == "UNKNOWN":
            global_unknown = True
            
        manifest["marketplaces"][mkt] = {
            "START_TIME": mkt_start_iso,
            "END_TIME": datetime.now().isoformat(),
            "DURATION_SECONDS": round(mkt_duration, 2),
            "STATUS": mkt_status,
            "SEMANTIC_REASON": semantic_reason,
            "STOP_REASON": stop_reason,
            "COVERAGE_STATUS": coverage,
            "RAW_FRONTIER_REMAINING": metrics.get("raw_frontier_remaining"),
            "RELEVANT_FRONTIER_REMAINING": metrics.get("relevant_frontier_remaining"),
            "RELEVANT_PENDING_WORK": metrics.get("relevant_pending_work"),
            "UNIQUE_PUBLICATIONS": pubs,
            "COMMERCIAL_CATEGORIES": cats,
            "CATEGORY_MEMBERSHIPS": memberships,
            "EXPERIENCE_HITS": "UNKNOWN",
            "EXPERIENCE_MISSES": "UNKNOWN",
            "FALLBACKS_USED": "UNKNOWN",
            "RETRIES": "UNKNOWN",
            "TIMEOUTS": 1 if process_timeout else 0,
            "SOURCE_BLOCKED_COUNT": metrics.get("source_blocked_count", 0),
            "NOT_FOUND_COUNT": metrics.get("not_found_count", 0),
            "ERROR_COUNT": 1 if process_timeout else 0,
            "EVIDENCE_COUNT": metrics.get("evidence_count", count_lines(mkt_dir / "events.jsonl")),
            "OUTPUT_PATH": str(mkt_dir)
        }
        
    # Global verification
    manifest["global_end_time"] = datetime.now().isoformat()
    manifest["global_duration_seconds"] = round(time.time() - global_start, 2)
    
    if global_fail:
        manifest["global_status"] = "FAIL"
        exit_code = EXIT_FAIL
    elif global_partial:
        manifest["global_status"] = "PARTIAL"
        exit_code = EXIT_PARTIAL
    elif global_unknown:
        manifest["global_status"] = "UNKNOWN"
        exit_code = EXIT_PARTIAL
    else:
        manifest["global_status"] = "PASS"
        exit_code = EXIT_PASS

    # Create Comparison VA
    ripley_cats = manifest["marketplaces"].get("Ripley", {}).get("COMMERCIAL_CATEGORIES", "UNKNOWN")
    ripley_regression = "TRUE" if isinstance(ripley_cats, int) and ripley_cats > VA_REFERENCE["Ripley"] else "FALSE"

    comparison = {
        "VA_REFERENCE": VA_REFERENCE,
        "MRI_OBSERVED": {k: manifest["marketplaces"][k]["COMMERCIAL_CATEGORIES"] for k in MARKETPLACES},
        "RIPLEY_FRONTIER_REGRESSION": ripley_regression
    }
    
    with open(out_root / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    with open(out_root / "comparison_va.json", "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)
        
    with open(out_root / "marketplace_results.json", "w", encoding="utf-8") as f:
        json.dump(manifest["marketplaces"], f, indent=2)
        
    with open(out_root / "final_report.md", "w", encoding="utf-8") as f:
        f.write(f"# MRI 4MP AUTONOMOUS CERTIFICATION RUN\n\n")
        f.write(f"Run ID: {run_id}\n")
        f.write(f"Status: {manifest['global_status']}\n")
        f.write(f"Duration: {manifest['global_duration_seconds']}s\n\n")
        f.write(f"## Marketplaces\n")
        for mkt, data in manifest["marketplaces"].items():
            f.write(f"- {mkt}: {data['STATUS']} (Coverage: {data['COVERAGE_STATUS']})\n")

    print(f"\n[RUNNER] Certification finished. Status: {manifest['global_status']}")
    print(f"[RUNNER] Manifest written to {out_root / 'manifest.json'}")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
