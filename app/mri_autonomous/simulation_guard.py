"""Simulation guardrail for operational MRI runs.

Fails fast if any simulation / mock / fixture / artifact-generator module
contributes to observations, metrics, events, heartbeats, checkpoints,
experience, certification, or the final report.

This module contains no metrics, no fixtures, no expected counts.
"""

import re
import sys

FORBIDDEN_MODULE_NAMES = (
    "_mock_mri_run",
    "_paris_generate_artifacts",
)


def _is_forbidden(name: str) -> bool:
    base = name.rsplit(".", 1)[-1]
    return base in FORBIDDEN_MODULE_NAMES or base == "mock_mri"

# marketplace_product_id values that prove fabrication, never real identity
FORBIDDEN_SKU_PATTERNS = (
    re.compile(r"^pub_\d+$"),
    re.compile(r"^(GEN|PAR-100|FAL-300|RIP-200|MLC4000|SKU-)-"),
)

# metric literals known to come from generators, never from a recount
FORBIDDEN_METRIC_FINGERPRINTS = (526, 128, 2180)


def assert_no_simulation(context: str = "operational_run") -> dict:
    """Raise AssertionError if a simulation module is loaded in this process."""
    loaded = sorted(name for name in sys.modules if _is_forbidden(name))
    if loaded:
        raise AssertionError(
            f"SIMULATION_CONTRIBUTION>0 in {context}: forbidden modules loaded: {loaded}"
        )
    return {"context": context, "forbidden_modules_loaded": [], "simulation_contribution": 0}


def check_publications_real(publications: list) -> dict:
    """Verify every publication carries real marketplace identity.

    Returns evidence dict; raises AssertionError on fabrication markers.
    """
    bad = []
    for pub in publications:
        sku = (pub.get("marketplace_product_id") or "").strip()
        if not sku:
            bad.append({"publication_id": pub.get("publication_id"), "reason": "empty identity"})
            continue
        if any(pat.match(sku) for pat in FORBIDDEN_SKU_PATTERNS):
            bad.append({"publication_id": pub.get("publication_id"), "reason": f"synthetic sku {sku}"})
    if bad:
        raise AssertionError(f"SIMULATION_CONTRIBUTION>0: fabricated identities: {bad[:5]}")
    return {"publications_checked": len(publications), "fabricated": 0, "simulation_contribution": 0}
