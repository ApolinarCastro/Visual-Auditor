"""Read-only replay of the old pending-node evidence, without marketplace I/O.

Write only this task's report. Missing node identities remain unresolved; the
known aggregate is not expanded into invented node records.
"""
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "outputs/mri_4mp_certification/20261006_134523"
OUT = Path(__file__).with_name("offline_reclassification.json")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    results = read_json(RUN / "marketplace_results.json")
    comparison = read_json(RUN / "comparison_va.json")
    report = {"run_id": RUN.name, "navigation_calls": 0,
              "reference_comparison": comparison, "marketplaces": {}}
    missing_total = 0
    for marketplace, original in results.items():
        slug = Path(original["OUTPUT_PATH"].replace("\\", "/")).name
        folder = RUN / slug / (RUN.name + "_" + slug)
        taxonomy = read_json(folder / "taxonomy.json")
        failures = read_json(folder / "failures.json")
        old = original["RELEVANT_FRONTIER_REMAINING"]
        notes = [n for n in failures.get("evidence_notes", [])
                 if n.startswith("CATEGORY_BUDGET_EXHAUSTED:")]
        remainder = sum(int(re.search(r"relevant=(\d+)", n).group(1)) for n in notes)
        pending = [c for c in taxonomy if not c.get("is_seed_surface")
                   and c.get("stop_reason") in (None, "QUEUED", "NOT_VISITED")]
        # These historical artifacts identify no remaining pending taxonomy
        # nodes: the old count comes exclusively from the truncated facet list.
        assert not pending, "Unexpected pending taxonomy: requires per-node evaluation"
        assert old == remainder, "Historical pending count and remainder do not reconcile"
        sources = {}
        explicit_remainder_fields = []
        keys = {"facet_urls", "_remainder_urls", "remainder_urls", "pending_nodes",
                "pending_categories", "remainder_nodes"}

        def inspect(value, source):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in keys:
                        explicit_remainder_fields.append({"source": source, "field": key})
                    inspect(child, source)
            elif isinstance(value, list):
                for child in value:
                    inspect(child, source)

        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            relative = path.relative_to(ROOT).as_posix()
            sources[relative] = hashlib.sha256(data).hexdigest()
            if path.suffix == ".json":
                inspect(json.loads(data.decode("utf-8-sig")), relative)
            elif path.suffix == ".jsonl":
                for line in data.decode("utf-8-sig").splitlines():
                    if line.strip():
                        inspect(json.loads(line), relative)
        assert not explicit_remainder_fields, "Recover persisted remainder identifiers before classifying"
        missing_total += old
        report["marketplaces"][marketplace] = {
            "old": old, "required": 0, "rejected_as_unproven": 0,
            "unresolved": old, "equation": f"{old} = 0 + 0 + {old}",
            "per_node_records": [], "unresolved_without_persisted_node_identity": old,
            "status": "COMPLETE" if not old else "BLOCKED_PER_NODE_RECLASSIFICATION",
            "reason": None if not old else "Only aggregate facet remainder persisted; original ordered URLs and node evidence unavailable",
            "evidence_notes": notes, "pending_taxonomy_nodes": len(pending),
            "explicit_remainder_fields_found": explicit_remainder_fields,
            "source_sha256": sources,
        }
    report["aggregate_accounting_complete"] = True
    report["per_node_reclassification_complete"] = missing_total == 0
    report["missing_old_node_identities"] = missing_total
    report["status"] = "PASS" if not missing_total else "BLOCKED"
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, row in report["marketplaces"].items():
        print(f"{name}: {row['equation']} (required + rejected + unresolved)")
    print(f"MISSING_OLD_NODE_IDENTITIES={missing_total}")
    assert missing_total == 0, f"OFFLINE_NODE_IDENTITIES_NOT_PERSISTED: {missing_total} old pending nodes cannot be reclassified individually"


if __name__ == "__main__":
    main()
