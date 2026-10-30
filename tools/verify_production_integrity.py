"""
PRODUCTION INTEGRITY CHECK (read-only).

Reproduces the project's canonical historical-observation fingerprint exactly as
defined in evidence/mri_codex_final_gate_018r/validate_018r.py:51-55:

    rows  = mri_publications WHERE run_id=:hrun
          + mri_historical_publications WHERE run_id=:hrun
    count = len(rows)
    hash  = sha256(json.dumps(sorted(rows, key=str), default=str))

Expected: count == 2533, hash == c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b

Opened strictly read-only (mode=ro) so this check cannot itself mutate production.
"""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

DB = Path(sys.argv[1] if len(sys.argv) > 1 else
          "data/sqlite/visibility.db").resolve()
HRUN = "run_va_mri_operational_integration_1792000336"
EXPECTED_COUNT = 2533
EXPECTED_HASH = "c4f44dcee641a7bbbf51d8062ed16103d50b13c81f9e3f56809bd0bb3bbd5f3b"

print(f"DB   : {DB}")
print(f"size : {DB.stat().st_size:,} bytes")
print(f"run  : {HRUN}")
print()

conn = sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True)
conn.execute("PRAGMA query_only = ON;")

cols = [r[1] for r in conn.execute("pragma table_info(mri_publications)")]
sel = ",".join(cols)

rows = list(conn.execute(f"SELECT {sel} FROM mri_publications WHERE run_id=?", (HRUN,)).fetchall())
n_pub = len(rows)
rows += list(conn.execute(f"SELECT {sel} FROM mri_historical_publications WHERE run_id=?", (HRUN,)).fetchall())
n_hist = len(rows) - n_pub

digest = hashlib.sha256(json.dumps(sorted(rows, key=str), default=str).encode()).hexdigest()

integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
fk = conn.execute("PRAGMA foreign_key_check").fetchall()
conn.close()

print(f"mri_publications rows           : {n_pub:,}")
print(f"mri_historical_publications rows: {n_hist:,}")
print(f"TOTAL observations              : {len(rows):,}   (expected {EXPECTED_COUNT:,})")
print(f"all_attributes_sha256           : {digest}")
print(f"expected                        : {EXPECTED_HASH}")
print(f"integrity_check                 : {integrity}")
print(f"foreign_key_check violations    : {len(fk)}")
print()

ok = (len(rows) == EXPECTED_COUNT) and (digest == EXPECTED_HASH) and integrity == "ok"
print("=" * 62)
print("PRODUCTION_INTEGRITY =", "PASS" if ok else "FAIL")
print("=" * 62)
if len(rows) != EXPECTED_COUNT:
    print(f"  count mismatch: {len(rows)} != {EXPECTED_COUNT}")
if digest != EXPECTED_HASH:
    print(f"  hash mismatch")
sys.exit(0 if ok else 1)
