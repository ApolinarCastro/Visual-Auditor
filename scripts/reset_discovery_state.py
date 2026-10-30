"""Transparent reset of MRI-derived discovery state.

Creates a timestamped backup and manifest before removing only discovery
caches: categories, learned graph and discovery memory. Audit runs,
publications, sessions and the operational DB are untouched.

Default is dry-run. Use --apply to delete the derived files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = ROOT / "_integration"
TARGETS = [
    ROOT / "data" / "mri_categories.json",
    ROOT / "data" / "sqlite" / "mri_operational" / "mri_categories.json",
    INTEGRATION / "data" / "mri_categories.json",
    INTEGRATION / "data" / "sqlite" / "mri_categories.json",
    INTEGRATION / "knowledge" / "discovery_graph.json",
    INTEGRATION / "knowledge" / "discovery_memory.json",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(apply: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = ROOT / "data" / "backups" / f"discovery_state_{stamp}"
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "APPLY" if apply else "DRY_RUN",
        "backup_dir": str(backup),
        "targets": [],
    }
    existing = [p for p in TARGETS if p.exists()]
    if apply and existing:
        backup.mkdir(parents=True, exist_ok=True)
    for path in existing:
        entry = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "backup": None,
            "deleted": False,
        }
        if apply:
            dest = backup / path.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            entry["backup"] = str(dest)
            path.unlink()
            entry["deleted"] = True
        manifest["targets"].append(entry)
    manifest["missing"] = [str(p) for p in TARGETS if not p.exists()]
    manifest_path = backup / "manifest.json"
    if apply:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="backup and delete derived discovery files")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    result = run(apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
