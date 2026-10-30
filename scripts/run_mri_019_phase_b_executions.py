"""
scripts/run_mri_019_phase_b_executions.py

Executes three independent, bounded autonomous runs for Phase B of MRI-AUTONOMOUS-OPERATION-019.
Saves structured JSON reports and run manifest in evidence/mri_autonomous_operation_019/.
"""

import asyncio
import json
import pathlib
import sys

# Ensure root in path
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.mri_autonomous.storage_guard import StorageConfig
from app.mri_autonomous.autonomous_multimarketplace_runner import (
    AutonomousMultiMarketplaceRunner,
    MANDATORY_ORDER
)


async def run_phase_b():
    out_dir = BASE_DIR / "evidence" / "mri_autonomous_operation_019"
    out_dir.mkdir(parents=True, exist_ok=True)

    StorageConfig.set_test_mode(True, sandbox_dir="tmp/mri_019_phase_b")
    db_path = str(BASE_DIR / "tmp" / "mri_019_phase_b" / "visibility_mri_019.db")

    runner = AutonomousMultiMarketplaceRunner(brand="Nicopoly", db_path=db_path)

    runs_manifest = []
    for run_idx in range(1, 4):
        print(f">>> Executing Autonomous Run {run_idx}/3...")
        report = await runner.execute_autonomous_order(
            instruction=MANDATORY_ORDER,
            run_id_prefix=f"mri_019_run_{run_idx}"
        )

        rep_dict = {
            "run_id": report.run_id,
            "run_index": run_idx,
            "instruction": report.instruction,
            "target_brand": report.target_brand,
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "truth_model_version": report.truth_model_version,
            "summary": report.summary,
            "decisions_log": report.decisions_log,
            "marketplaces": {
                mkt: {
                    "status": res.status,
                    "active_strategy": res.active_strategy,
                    "strategies_attempted": res.strategies_attempted,
                    "total_brand_publications": res.total_brand_publications,
                    "total_official_seller_publications": res.total_official_seller_publications,
                    "sellers_found": res.sellers_found,
                    "categories_found": res.categories_found,
                    "publications_count": res.publications_count,
                    "blocker_reason": res.blocker_reason,
                    "evidence": res.evidence
                }
                for mkt, res in report.marketplaces.items()
            }
        }

        run_file = out_dir / f"run_{run_idx}_evidence.json"
        with open(run_file, "w", encoding="utf-8") as f:
            json.dump(rep_dict, f, ensure_ascii=False, indent=2)

        runs_manifest.append({
            "run_index": run_idx,
            "run_id": report.run_id,
            "evidence_file": str(run_file.relative_to(BASE_DIR)),
            "status": report.summary.get("cross_marketplace_status"),
            "total_marketplaces": report.summary.get("total_marketplaces_audited"),
            "successful_marketplaces": report.summary.get("successful_marketplaces"),
            "total_publications": report.summary.get("total_publications_persisted")
        })
        print(f">>> Run {run_idx} finished: status={report.summary.get('cross_marketplace_status')}, publications={report.summary.get('total_publications_persisted')}")

    manifest_path = out_dir / "MRI_019_RUNS_MANIFEST.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "order": MANDATORY_ORDER,
            "runs": runs_manifest
        }, f, ensure_ascii=False, indent=2)
    print(f">>> 3 autonomous runs completed and manifest written to {manifest_path}")


if __name__ == "__main__":
    asyncio.run(run_phase_b())
