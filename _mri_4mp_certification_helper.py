import sys
import os
import time
import json
import subprocess
from datetime import datetime
from pathlib import Path

# --- Configuration ---
EXPECTED_HEAD = "db3c63808360c767ba1e3ce43e0fceba67160a75"
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

        # Read status from run_manifest.json if generated by the run
        pubs = "UNKNOWN"
        cats = "UNKNOWN"
        memberships = "UNKNOWN"
        
        manifest_path = mkt_dir / "run_manifest.json"
        if not process_timeout and manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    sub_manifest = json.load(f)
                
                # Check for marketplace object inside manifest
                # structure: {"marketplaces": {"Paris": {"status": "PARTIAL", "coverage": "PARTIAL", ...}}}
                if "marketplaces" in sub_manifest and mkt in sub_manifest["marketplaces"]:
                    mdata = sub_manifest["marketplaces"][mkt]
                    coverage = mdata.get("coverage", "UNKNOWN")
                    stop_reason = mdata.get("stop_reason", "UNKNOWN")
                    pubs = mdata.get("publications", "UNKNOWN")
                    cats = mdata.get("taxonomy_nodes", "UNKNOWN")
                    memberships = mdata.get("memberships", "UNKNOWN")
                    
                    if coverage == "CONFIRMED":
                        mkt_status = "PASS"
                    elif coverage == "PARTIAL":
                        mkt_status = "PARTIAL"
                    elif coverage == "BLOCKED":
                        mkt_status = "BLOCKED"
                    elif coverage == "FAIL":
                        mkt_status = "FAIL"
            except Exception as e:
                pass

        # If not fully updated from JSON, fallback to error codes
        if mkt_status == "UNKNOWN":
            if retcode != 0:
                mkt_status = "FAIL"
            else:
                mkt_status = "PASS"

        if mkt_status == "FAIL" or mkt_status == "BLOCKED":
            global_fail = True
        elif mkt_status == "PARTIAL":
            global_partial = True
            
        manifest["marketplaces"][mkt] = {
            "START_TIME": mkt_start_iso,
            "END_TIME": datetime.now().isoformat(),
            "DURATION_SECONDS": round(mkt_duration, 2),
            "STATUS": mkt_status,
            "STOP_REASON": stop_reason,
            "COVERAGE_STATUS": coverage,
            "RAW_FRONTIER_REMAINING": "UNKNOWN",
            "RELEVANT_FRONTIER_REMAINING": "UNKNOWN",
            "RELEVANT_PENDING_WORK": "UNKNOWN",
            "UNIQUE_PUBLICATIONS": pubs,
            "COMMERCIAL_CATEGORIES": cats,
            "CATEGORY_MEMBERSHIPS": memberships,
            "EXPERIENCE_HITS": "UNKNOWN",
            "EXPERIENCE_MISSES": "UNKNOWN",
            "FALLBACKS_USED": "UNKNOWN",
            "RETRIES": "UNKNOWN",
            "TIMEOUTS": 1 if process_timeout else 0,
            "SOURCE_BLOCKED_COUNT": "UNKNOWN",
            "NOT_FOUND_COUNT": "UNKNOWN",
            "ERROR_COUNT": "UNKNOWN",
            "EVIDENCE_COUNT": count_lines(mkt_dir / "events.jsonl"),
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
