"""Real contradiction / drift rules (core, generic, no I/O).

Two rules with teeth:

1. cartesian_suspect(): a memberships/unique_publications ratio that is a
   near-exact integer >= 3 over a non-trivial sample is the fingerprint of
   fabricated Cartesian assignment (the historical 2180/436 = 5.0 case).
   Healthy multi-membership graphs produce fractional ratios (~1.0x).

2. drift(): set comparison of taxonomy node names between two runs gives
   new / missing / stable surfaces. MEMORY != CURRENT TRUTH: a missing node
   is drift evidence, never proof of absence.
"""

from typing import Dict, List, Set

MIN_SAMPLE_UNIQUE = 50
MIN_INTEGER_RATIO = 3
TOLERANCE = 0.01


def cartesian_suspect(memberships: int, unique_publications: int) -> Dict:
    memberships = int(memberships or 0)
    unique_publications = int(unique_publications or 0)
    if unique_publications < MIN_SAMPLE_UNIQUE or memberships <= 0:
        return {"suspect": False,
                "evidence": "sample below minimum or empty"}
    ratio = memberships / unique_publications
    if ratio >= MIN_INTEGER_RATIO and abs(ratio - round(ratio)) < TOLERANCE:
        return {"suspect": True,
                "ratio": round(ratio, 3),
                "evidence": f"{memberships}/{unique_publications}={ratio:.3f} "
                            f"near-integer {round(ratio)}: Cartesian-assignment fingerprint"}
    return {"suspect": False, "ratio": round(ratio, 3),
            "evidence": f"{memberships}/{unique_publications}={ratio:.3f} fractional: healthy"}


def drift(prior: Set[str], current: Set[str]) -> Dict[str, List[str]]:
    prior = set(prior or [])
    current = set(current or [])
    return {"new": sorted(current - prior),
            "missing": sorted(prior - current),
            "stable": sorted(prior & current)}
