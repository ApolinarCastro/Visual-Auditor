"""MRI autonomous intelligence cycle.

Integrates the existing ExperienceStore, StrategySelector and CapabilityRegistry.
No new marketplace engine and no automatic promotion of a successful run to
validated commercial knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from app.mri_autonomous.capability_registry import CapabilityRegistry, CapabilityType
from app.mri_autonomous.experience_store import ExperienceStore
from app.mri_autonomous.strategy_selector import SelectedStrategy, StrategySelector

OBSERVED = "OBSERVED"
CANDIDATE = "CANDIDATE"
VALIDATED = "VALIDATED"
REJECTED = "REJECTED"
APPROVED = "APPROVED"
GOVERNANCE_STATES = (OBSERVED, CANDIDATE, VALIDATED, REJECTED, APPROVED)


@dataclass
class CycleDecision:
    marketplace: str
    capability_type: str
    selected_strategy: Optional[str]
    fallback_strategy_ids: list[str] = field(default_factory=list)
    recalled_strategies: int = 0
    excluded_strategies: list[str] = field(default_factory=list)
    selection_reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "marketplace": self.marketplace,
            "capability_type": self.capability_type,
            "selected_strategy": self.selected_strategy,
            "fallback_strategy_ids": self.fallback_strategy_ids,
            "recalled_strategies": self.recalled_strategies,
            "excluded_strategies": self.excluded_strategies,
            "selection_reason": self.selection_reason,
            "evidence": self.evidence,
        }


class IntelligenceCycle:
    """Deterministic, experience-aware strategy execution with governed learning."""

    def __init__(self, store: Optional[ExperienceStore] = None,
                 selector: Optional[StrategySelector] = None,
                 registry: Optional[CapabilityRegistry] = None,
                 brand: str = "Nicopoly"):
        self.registry = registry or CapabilityRegistry(auto_probe=False)
        self.selector = selector or StrategySelector(self.registry)
        self.store = store or ExperienceStore()
        self.brand = brand

    def recall(self, marketplace: str, strategy_type: Optional[str] = None,
               surface: Optional[str] = None) -> dict[str, Any]:
        strategies = self.store.get_strategies(marketplace, self.brand, strategy_type)
        experiences = self.store.get_all_experiences(marketplace, self.brand)
        failed = {s["strategy_id"] for s in strategies if str(s.get("result")).upper() == "FAILED"}
        rejected = {
            str(e.get("value")) for e in experiences
            if str(e.get("knowledge_type")).upper() == "STRATEGY"
            and str(e.get("status")).upper() in ("REJECTED", "FAILED", "RETIRED")
        }
        validated = {
            str(e.get("value")) for e in experiences
            if str(e.get("knowledge_type")).upper() == "STRATEGY"
            and str(e.get("status")).upper() in ("VALIDATED", "APPROVED", "LAST_GOOD")
        }
        failed |= rejected
        return {
            "strategies": strategies,
            "experiences": experiences,
            "failed_strategy_ids": sorted(failed),
            "validated_strategy_ids": sorted(validated),
            "surface": surface,
        }

    def select(self, marketplace: str,
               capability_type: CapabilityType = CapabilityType.PRODUCT_EXTRACTION,
               *, surface: Optional[str] = None, allow_mcp: bool = False,
               default_strategy: Optional[str] = None) -> CycleDecision:
        recalled = self.recall(marketplace, capability_type.value, surface)
        excluded = set(recalled["failed_strategy_ids"])
        candidates = self.selector.get_fallback_chain(
            marketplace, capability_type, allow_mcp=allow_mcp)
        allowed = [c for c in candidates if c.strategy_id not in excluded]
        # Validated/approved history wins ties over unvalidated healthy caps.
        allowed = sorted(
            allowed,
            key=lambda c: (0 if c.strategy_id in recalled["validated_strategy_ids"] else 1),
        )
        chosen = allowed[0] if allowed else None
        chosen_id = chosen.strategy_id if chosen else default_strategy
        decision = CycleDecision(
            marketplace=marketplace,
            capability_type=capability_type.value,
            selected_strategy=chosen_id,
            fallback_strategy_ids=[c.strategy_id for c in allowed[1:]],
            recalled_strategies=len(recalled["strategies"]),
            excluded_strategies=sorted(excluded),
            selection_reason=(chosen.selection_reason if chosen
                              else ("AUTHORIZED_OPERATIONAL_DEFAULT"
                                    if default_strategy else "NO_ALLOWED_STRATEGY")),
            evidence={"recalled": recalled, "candidate_count": len(candidates)},
        )
        if chosen_id:
            self.store.record_strategy_decision(
                marketplace, self.brand, chosen_id, True,
                decision.selection_reason,
                alternative_strategy_id=(decision.fallback_strategy_ids[0]
                                         if decision.fallback_strategy_ids else None),
                expected_outcome="ACQUISITION_SUCCESS")
        for alt in decision.fallback_strategy_ids:
            self.store.record_strategy_decision(
                marketplace, self.brand, alt, False,
                f"fallback after {chosen_id}" if chosen_id else "not selected",
                alternative_strategy_id=chosen_id)
        return decision

    def evaluate_and_store(self, marketplace: str, strategy_id: str,
                           capability_type: CapabilityType, *,
                           success: bool, evidence: dict[str, Any],
                           failure_type: Optional[str] = None) -> dict[str, Any]:
        """Record an observed outcome without auto-promoting it to VALIDATED."""
        self.store.record_strategy(
            marketplace=marketplace, brand=self.brand, strategy_id=strategy_id,
            strategy_type=capability_type.value,
            surface=str(evidence.get("surface") or ""),
            hypothesis=str(evidence.get("hypothesis") or ""),
            attempt=int(evidence.get("attempt") or 1),
            result="SUCCESS" if success else "FAILED",
            failure_type=failure_type,
            evidence=str(evidence),
            confidence=float(evidence.get("confidence") or 0.0),
            last_validated_at=datetime.now(timezone.utc).isoformat() if success else None)
        return self.store.record_experience(
            marketplace=marketplace, brand=self.brand,
            knowledge_type="STRATEGY", value=strategy_id,
            status=OBSERVED, is_success=success,
            discovery_method=capability_type.value,
            evidence_reference=str(evidence))

    def validate(self, marketplace: str, strategy_id: str, *,
                 approved: bool = False, evidence: str) -> dict[str, Any]:
        status = APPROVED if approved else VALIDATED
        return self.store.set_knowledge_status(
            marketplace, self.brand, "STRATEGY", strategy_id, status, evidence)

    def reject(self, marketplace: str, strategy_id: str, evidence: str) -> dict[str, Any]:
        return self.store.set_knowledge_status(
            marketplace, self.brand, "STRATEGY", strategy_id, REJECTED, evidence)

    def remember_paris_empty_page(self) -> dict[str, Any]:
        """Persist the Paris incomplete-page lesson as OBSERVED, never VALIDATED."""
        return self.store.record_experience(
            marketplace="Paris", brand=self.brand,
            knowledge_type="ACQUISITION_FAILURE",
            value="PARIS_EMPTY_PAGE_NOT_FOUND",
            source_url="https://www.paris.cl/search?q=nicopoly",
            page_type="SEARCH",
            discovery_method="empty_page_is_incomplete",
            extractor_used="ParisScraper",
            status=OBSERVED, is_success=False,
            evidence_reference=(
                "runs=run_mri_discovery_1793707172__paris,"
                "run_mri_discovery_1793712901; "
                "products=0 and pages_traversed=0 means SOURCE_INCOMPLETE, not NOT_FOUND"))

    def recall_paris_empty_page(self) -> Optional[dict[str, Any]]:
        return self.store.get_experience_item(
            "Paris", self.brand, "ACQUISITION_FAILURE",
            "PARIS_EMPTY_PAGE_NOT_FOUND")

    def execute(self, marketplace: str,
                execute_fn: Callable[[str, dict[str, Any]], dict[str, Any]],
                capability_type: CapabilityType = CapabilityType.PRODUCT_EXTRACTION,
                *, surface: Optional[str] = None, allow_mcp: bool = False) -> dict[str, Any]:
        """Select, execute, evaluate and fall back through allowed strategies.

        `execute_fn(strategy_id, context) -> {"success": bool, "evidence": ...}`.
        Success is stored as OBSERVED; only validate() may promote it.
        """
        history, tried = [], []
        while True:
            decision = self.select(marketplace, capability_type,
                                   surface=surface, allow_mcp=allow_mcp)
            remaining = [s for s in decision.fallback_strategy_ids if s not in tried]
            if not decision.selected_strategy or decision.selected_strategy in tried:
                return {"success": False, "decision": decision.to_dict(),
                        "attempts": tried, "history": history,
                        "reason": "NO_ALLOWED_STRATEGY"}
            sid = decision.selected_strategy
            tried.append(sid)
            ctx = {"marketplace": marketplace, "brand": self.brand,
                   "capability_type": capability_type.value, "surface": surface,
                   "run_id": evidence_run_id(decision)}
            try:
                outcome = execute_fn(sid, ctx) or {}
            except Exception as exc:
                outcome = {"success": False, "failure_type": f"{type(exc).__name__}: {exc}"}
            success = bool(outcome.get("success"))
            evidence = dict(outcome.get("evidence") or {})
            evidence.setdefault("surface", surface or "")
            evidence.setdefault("attempt", len(tried))
            evidence["run_id"] = ctx["run_id"]
            record = self.evaluate_and_store(
                marketplace, sid, capability_type, success=success,
                evidence=evidence,
                failure_type=None if success else str(outcome.get("failure_type") or "ACQUISITION_FAILED"))
            history.append({"strategy_id": sid, "success": success,
                            "record": record, "evidence": evidence})
            if success:
                return {"success": True, "selected_strategy": sid,
                        "decision": decision.to_dict(), "attempts": tried,
                        "history": history, "knowledge_status": OBSERVED}
            # The failed strategy is now excluded by recall() for this context.
            if not remaining:
                return {"success": False, "decision": decision.to_dict(),
                        "attempts": tried, "history": history,
                        "reason": "ALL_ALLOWED_STRATEGIES_FAILED"}


def evidence_run_id(decision: CycleDecision) -> str:
    return f"intel_{decision.marketplace.replace(' ', '_').lower()}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
