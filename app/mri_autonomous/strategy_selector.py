"""
app/mri_autonomous/strategy_selector.py
Strategy Selector for MRI-023 (RG-09 to RG-12)
Deterministically evaluates available capabilities, consults verified experience,
and orders execution strategies with automatic fallback.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.mri_autonomous.capability_registry import (
    CAPABILITY_STRATEGY_TYPE,
    CAPABILITY_SYSTEM_BRAND,
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityRegistry,
    CapabilityType,
    MIN_SUCCESS_EVIDENCE,
    resolve_strategy_capability,
)

logger = logging.getLogger(__name__)


@dataclass
class SelectedStrategy:
    strategy_id: str
    capability: CapabilityDefinition
    priority: int
    selection_reason: str
    fallback_strategy_ids: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)


class StrategySelector:
    """
    Autonomous Strategy Selector (RG-09 to RG-12).
    Ranks viable capabilities by verified health, persisted experience,
    approved strategies, cost weight and measured success rate.
    """

    def __init__(self, registry: Optional[CapabilityRegistry] = None,
                 experience_store: Any = None, hydrate: bool = True):
        self.registry = registry or CapabilityRegistry()
        self.experience_store = experience_store
        if experience_store is not None and hydrate:
            self.refresh_experience()

    # ------------------------------------------------------------------
    # MRI-LEARNING-CIRCUIT-REPAIR-007: persisted experience is an input
    # ------------------------------------------------------------------

    def refresh_experience(self) -> Dict[str, str]:
        """Re-read authorized persisted capability knowledge into the registry."""
        if self.experience_store is None:
            return {}
        try:
            return self.registry.hydrate_from_experience(self.experience_store)
        except Exception as exc:  # read-only enrichment must not break selection
            logger.warning(f"Experience hydration failed (non-fatal): {exc}")
            return {}

    def _experience_context(self, marketplace: str, candidates: List[CapabilityDefinition]) -> Dict[str, Any]:
        """Evidence consulted for this selection, plus identity resolution."""
        ctx: Dict[str, Any] = {
            "consulted": self.experience_store is not None,
            "evidence": {},
            "approved": set(),
            "identity": {},
        }
        store = self.experience_store
        if store is None:
            return ctx
        try:
            self.registry.hydrate_from_experience(store)
        except Exception:
            pass
        for cap in candidates:
            row = self.registry.capability_evidence(cap.capability_id, store)
            if row:
                ctx["evidence"][cap.capability_id] = {
                    "experience_id": row.get("id"),
                    "success_count": row.get("success_count"),
                    "failure_count": row.get("failure_count"),
                    "consecutive_failures": row.get("consecutive_failures"),
                    "status": row.get("status"),
                }
            ctx["identity"][cap.capability_id] = resolve_strategy_capability(
                CAPABILITY_STRATEGY_TYPE, cap.capability_id, self.registry)
        try:
            rows = store.get_strategies(
                marketplace, CAPABILITY_SYSTEM_BRAND,
                strategy_type=CAPABILITY_STRATEGY_TYPE) or []
        except Exception:
            rows = []
        for row in rows:
            resolved = resolve_strategy_capability(
                row.get("strategy_type") or "", row.get("strategy_id") or "", self.registry)
            if resolved and row.get("result") == "SUCCESS":
                ctx["approved"].add(resolved)
        return ctx

    def _rank_key(self, experience: Dict[str, Any]):
        def sort_key(c: CapabilityDefinition):
            health_score = 0 if c.health == CapabilityHealth.HEALTHY else 1
            row = experience["evidence"].get(c.capability_id)
            evidence_score = 0.0
            if row:
                successes = int(row.get("success_count") or 0)
                failures = int(row.get("failure_count") or 0)
                evidence_score = successes / float(successes + failures) if (successes + failures) else 0.0
            approved = 1 if c.capability_id in experience["approved"] else 0
            return (health_score, -approved, -evidence_score, c.cost_weight, -c.success_rate)
        return sort_key

    def select_strategy(
        self,
        marketplace: str,
        capability_type: CapabilityType,
        allow_mcp: bool = True,
        preferred_surface: Optional[str] = None,
        brand: str = "",
    ) -> Optional[SelectedStrategy]:
        """
        Selects the optimal strategy for a given marketplace and capability requirement (RG-09).
        Deterministic ranking:
        1. Health (HEALTHY before DEGRADED), after hydrating persisted evidence
        2. Capabilities with a persisted approved strategy
        3. Higher persisted evidence success ratio
        4. Lower cost_weight
        5. Higher success_rate
        BLOCKED/DISABLED/UNKNOWN capabilities stay excluded.
        """
        candidates = self.registry.list_capabilities(
            marketplace=marketplace,
            capability_type=capability_type,
            only_healthy=True,
        )
        if self.experience_store is not None:
            self.refresh_experience()
            candidates = self.registry.list_capabilities(
                marketplace=marketplace,
                capability_type=capability_type,
                only_healthy=True,
            )

        if not allow_mcp:
            candidates = [c for c in candidates if not c.requires_stealth_mcp]

        if preferred_surface:
            surface_matches = [
                c for c in candidates if any(preferred_surface.lower() in s.lower() for s in c.supported_surfaces)
            ]
            if surface_matches:
                candidates = surface_matches

        if not candidates:
            logger.warning(f"No viable capability candidates found for {marketplace} / {capability_type.value}")
            return None

        experience = self._experience_context(marketplace, candidates)
        sorted_candidates = sorted(candidates, key=self._rank_key(experience))
        primary = sorted_candidates[0]
        fallbacks = [c.capability_id for c in sorted_candidates[1:]]

        evidence_row = experience["evidence"].get(primary.capability_id) or {}
        reason = (
            f"Selected as primary: health={primary.health.value}, "
            f"cost_weight={primary.cost_weight}, success_rate={primary.success_rate:.2f}, "
            f"persisted_evidence={evidence_row.get('success_count', 0)}"
            f"/{int(evidence_row.get('success_count') or 0) + int(evidence_row.get('failure_count') or 0)}"
            f"{' (approved)' if primary.capability_id in experience['approved'] else ''}"
        )

        return SelectedStrategy(
            strategy_id=primary.capability_id,
            capability=primary,
            priority=1,
            selection_reason=reason,
            fallback_strategy_ids=fallbacks,
            evidence={
                "experience_consulted": experience["consulted"],
                "capability_evidence": experience["evidence"],
                "approved_capabilities": sorted(experience["approved"]),
                "identity_mapping": experience["identity"],
                "brand": brand or None,
                "marketplace": marketplace,
                "capability_type": capability_type.value,
            },
        )

    def get_fallback_chain(
        self,
        marketplace: str,
        capability_type: CapabilityType,
        allow_mcp: bool = True
    ) -> List[SelectedStrategy]:
        """Returns the complete prioritized fallback chain for resilient execution (RG-10)."""
        if self.experience_store is not None:
            self.refresh_experience()
        candidates = self.registry.list_capabilities(
            marketplace=marketplace,
            capability_type=capability_type,
            only_healthy=True,
        )
        if not allow_mcp:
            candidates = [c for c in candidates if not c.requires_stealth_mcp]

        def sort_key(c: CapabilityDefinition):
            health_score = 0 if c.health == CapabilityHealth.HEALTHY else 1
            return (health_score, c.cost_weight, -c.success_rate)

        sorted_candidates = sorted(candidates, key=sort_key)
        chain = []
        for idx, cap in enumerate(sorted_candidates, start=1):
            chain.append(
                SelectedStrategy(
                    strategy_id=cap.capability_id,
                    capability=cap,
                    priority=idx,
                    selection_reason=f"Priority {idx} in fallback sequence",
                    fallback_strategy_ids=[c.capability_id for c in sorted_candidates[idx:]],
                )
            )
        return chain
