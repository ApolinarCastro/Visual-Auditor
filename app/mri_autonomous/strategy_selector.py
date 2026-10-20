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
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityRegistry,
    CapabilityType,
)

logger = logging.getLogger(__name__)


@dataclass
class SelectedStrategy:
    strategy_id: str
    capability: CapabilityDefinition
    priority: int
    selection_reason: str
    fallback_strategy_ids: List[str] = field(default_factory=list)


class StrategySelector:
    """
    Autonomous Strategy Selector (RG-09 to RG-12).
    Ranks viable capabilities by cost weight, health, and verified experience history.
    """

    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        self.registry = registry or CapabilityRegistry()

    def select_strategy(
        self,
        marketplace: str,
        capability_type: CapabilityType,
        allow_mcp: bool = True,
        preferred_surface: Optional[str] = None,
    ) -> Optional[SelectedStrategy]:
        """
        Selects the optimal strategy for a given marketplace and capability requirement (RG-09).
        Implements deterministic ranking:
        1. Health == HEALTHY prioritized over DEGRADED
        2. BLOCKED or DISABLED strictly excluded
        3. MCP adapters gated by allow_mcp flag
        4. Lower cost_weight prioritized
        5. Higher success_rate prioritized
        """
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

        # Sort key: (Health ranking, Cost weight, -Success rate)
        def sort_key(c: CapabilityDefinition):
            health_score = 0 if c.health == CapabilityHealth.HEALTHY else 1
            return (health_score, c.cost_weight, -c.success_rate)

        sorted_candidates = sorted(candidates, key=sort_key)
        primary = sorted_candidates[0]
        fallbacks = [c.capability_id for c in sorted_candidates[1:]]

        reason = (
            f"Selected as primary: health={primary.health.value}, "
            f"cost_weight={primary.cost_weight}, success_rate={primary.success_rate:.2f}"
        )

        return SelectedStrategy(
            strategy_id=primary.capability_id,
            capability=primary,
            priority=1,
            selection_reason=reason,
            fallback_strategy_ids=fallbacks,
        )

    def get_fallback_chain(
        self,
        marketplace: str,
        capability_type: CapabilityType,
        allow_mcp: bool = True
    ) -> List[SelectedStrategy]:
        """Returns the complete prioritized fallback chain for resilient execution (RG-10)."""
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
