"""Real adapter dispatch for MRI IntelligenceCycle (MRI-INTELLIGENCE-DISPATCH-011).

The dispatcher only executes adapters explicitly supplied by the runner. The
selected capability must resolve to one of those adapters; rejected or blocked
strategies are never executed.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from app.mri_autonomous.capability_registry import CapabilityType
from app.mri_autonomous.intelligence_cycle import IntelligenceCycle


def dispatch_with_learning(
    cycle: IntelligenceCycle,
    marketplace: str,
    adapters: dict[str, Callable[[dict[str, Any]], dict[str, Any]]],
    *,
    capability_type: CapabilityType = CapabilityType.PRODUCT_EXTRACTION,
    surface: Optional[str] = None,
    allow_mcp: bool = False,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Select, execute, evaluate and fall back through real supplied adapters.

    adapters maps capability/strategy IDs to the runner's real adapter callable.
    Every attempted adapter must be in this mapping; a selected strategy without
    a real adapter produces NO_VALID_STRATEGY/INTELLIGENCE_DISPATCH_NOT_APPLIED.
    """
    attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for attempt in range(1, max_attempts + 1):
        decision = cycle.select(marketplace, capability_type,
                                surface=surface, allow_mcp=allow_mcp)
        candidates = []
        if decision.selected_strategy:
            candidates.append(decision.selected_strategy)
        candidates += [s for s in decision.fallback_strategy_ids if s not in candidates]
        strategy = next((s for s in candidates if s in adapters and s not in seen), None)
        if not strategy:
            return {
                "success": False, "reason": "NO_VALID_STRATEGY",
                "decision": decision.to_dict(), "attempts": attempts,
                "selected_strategy": decision.selected_strategy,
                "executed_strategy": None,
            }
        seen.add(strategy)
        ctx = {
            "run_id": f"dispatch_{marketplace}_{attempt}",
            "marketplace": marketplace, "strategy_id": strategy,
            "capability_type": capability_type.value, "surface": surface,
            "attempt_number": attempt,
            "selected_strategy": decision.selected_strategy,
        }
        try:
            outcome = adapters[strategy](ctx) or {}
        except Exception as exc:
            outcome = {"success": False,
                       "failure_type": f"{type(exc).__name__}: {exc}"}
        success = bool(outcome.get("success"))
        evidence = dict(outcome.get("evidence") or {})
        evidence.update({"run_id": ctx["run_id"], "surface": surface or "",
                         "attempt": attempt,
                         "selected_strategy": decision.selected_strategy,
                         "executed_strategy": strategy,
                         "adapter_id": strategy})
        record = cycle.evaluate_and_store(
            marketplace, strategy, capability_type, success=success,
            evidence=evidence,
            failure_type=None if success else str(outcome.get("failure_type") or "ADAPTER_FAILED"))
        attempts.append({
            "attempt": attempt, "selected_strategy": decision.selected_strategy,
            "executed_strategy": strategy, "adapter_id": strategy,
            "success": success, "outcome": outcome,
            "experience": record, "decision": decision.to_dict(),
        })
        if success:
            return {
                "success": True,
                "selected_strategy": decision.selected_strategy,
                "executed_strategy": strategy,
                "adapter_id": strategy,
                "attempts": attempts,
                "experience_recorded": True,
                "dispatch_match": decision.selected_strategy == strategy,
            }
        # A failed strategy is now recorded as FAILED and excluded by recall().
    return {
        "success": False, "reason": "ALL_ADAPTERS_FAILED",
        "attempts": attempts,
        "selected_strategy": attempts[0]["selected_strategy"] if attempts else None,
        "executed_strategy": attempts[-1]["executed_strategy"] if attempts else None,
    }


__all__ = ["dispatch_with_learning"]


async def dispatch_with_learning_async(
    cycle: IntelligenceCycle,
    marketplace: str,
    adapters: dict[str, Callable[[dict[str, Any]], Any]],
    *,
    capability_type: CapabilityType = CapabilityType.PRODUCT_EXTRACTION,
    surface: Optional[str] = None,
    allow_mcp: bool = False,
    default_strategy: Optional[str] = None,
    max_attempts: int = 1,
) -> dict[str, Any]:
    """Async adapter dispatch for the real runner entrypoint."""
    attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for attempt in range(1, max_attempts + 1):
        decision = cycle.select(
            marketplace, capability_type, surface=surface,
            allow_mcp=allow_mcp, default_strategy=default_strategy)
        candidates = []
        if decision.selected_strategy:
            candidates.append(decision.selected_strategy)
        candidates += [s for s in decision.fallback_strategy_ids if s not in candidates]
        strategy = next((s for s in candidates if s in adapters and s not in seen), None)
        if not strategy:
            return {
                "success": False, "reason": "NO_EXECUTABLE_ADAPTER",
                "decision": decision.to_dict(), "attempts": attempts,
                "selected_strategy": decision.selected_strategy,
                "executed_strategy": None,
            }
        seen.add(strategy)
        ctx = {
            "run_id": f"dispatch_{marketplace}_{attempt}",
            "marketplace": marketplace, "strategy_id": strategy,
            "capability_type": capability_type.value, "surface": surface,
            "attempt_number": attempt,
            "selected_strategy": decision.selected_strategy,
        }
        try:
            outcome = await adapters[strategy](ctx)
            if hasattr(outcome, "__await__"):
                outcome = await outcome
            outcome = outcome or {}
        except Exception as exc:
            outcome = {"success": False,
                       "failure_type": f"{type(exc).__name__}: {exc}"}
        success = bool(outcome.get("success"))
        evidence = dict(outcome.get("evidence") or {})
        evidence.update({"run_id": ctx["run_id"], "surface": surface or "",
                         "attempt": attempt,
                         "selected_strategy": decision.selected_strategy,
                         "executed_strategy": strategy,
                         "adapter_id": strategy})
        record = cycle.evaluate_and_store(
            marketplace, strategy, capability_type, success=success,
            evidence=evidence,
            failure_type=None if success else str(outcome.get("failure_type") or "ADAPTER_FAILED"))
        attempts.append({
            "attempt": attempt, "selected_strategy": decision.selected_strategy,
            "executed_strategy": strategy, "adapter_id": strategy,
            "success": success, "outcome": outcome,
            "experience": record, "decision": decision.to_dict(),
        })
        if success:
            return {
                "success": True,
                "selected_strategy": decision.selected_strategy,
                "executed_strategy": strategy,
                "adapter_id": strategy,
                "attempts": attempts,
                "experience_recorded": True,
                "dispatch_match": decision.selected_strategy == strategy,
            }
    return {
        "success": False, "reason": "ALL_ADAPTERS_FAILED",
        "attempts": attempts,
        "selected_strategy": attempts[0]["selected_strategy"] if attempts else None,
        "executed_strategy": attempts[-1]["executed_strategy"] if attempts else None,
    }


__all__ = ["dispatch_with_learning", "dispatch_with_learning_async"]
