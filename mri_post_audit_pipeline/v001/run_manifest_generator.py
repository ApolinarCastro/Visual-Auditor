import os
import sys
import json
import sqlite3
import hashlib

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(BASE_DIR, "data", "sqlite", "visibility.db")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_run_manifest():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    start_ts_env = os.environ.get("MRI_CURRENT_AUDIT_START", "2026-09-22T09:00:00")
    
    c.execute("SELECT id, created_at FROM product_snapshots WHERE created_at >= ? ORDER BY id ASC", (start_ts_env,))
    rows = c.fetchall()
    
    snapshot_ids = [r['id'] for r in rows]
    source_count = len(snapshot_ids)
    
    if source_count == 0:
        return None
        
    start_ts = rows[0]['created_at']
    finish_ts = rows[-1]['created_at']
    
    normalized_metadata = f"START:{start_ts}|FINISH:{finish_ts}|COUNT:{source_count}"
    ordered_ids = ",".join(str(i) for i in snapshot_ids)
    
    raw_fingerprint_data = f"{normalized_metadata}|IDS:{ordered_ids}"
    fingerprint = hashlib.sha256(raw_fingerprint_data.encode('utf-8')).hexdigest()
    
    # Also find corresponding audits
    c.execute("SELECT MIN(id) as min_id, MAX(id) as max_id FROM audits WHERE audit_date >= ?", (start_ts_env,))
    aud = c.fetchone()
    min_audit = aud['min_id'] if aud and aud['min_id'] else 0
    max_audit = aud['max_id'] if aud and aud['max_id'] else 0
    
    return {
        "post_audit_run_id": f"run_{start_ts[:10].replace('-', '_')}_certified_{min_audit}_{max_audit}",
        "audit_run_fingerprint": fingerprint,
        "source_snapshots": source_count,
        "start_timestamp": start_ts,
        "finish_timestamp": finish_ts,
        "min_snapshot_id": snapshot_ids[0],
        "max_snapshot_id": snapshot_ids[-1],
        "raw_fingerprint_data_sample": raw_fingerprint_data[:100] + "..."
    }

def main():
    manifest = get_run_manifest()
    
    with open(os.path.join(OUT_DIR, "03_RUN_IDENTITY.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
