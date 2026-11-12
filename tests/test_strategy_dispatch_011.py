"""Integrated dispatch tests for MRI-INTELLIGENCE-DISPATCH-011."""
from __future__ import annotations

import shutil
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.mri_autonomous.capability_registry import (
    AdapterExecutionMode,
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityRegistry,
    CapabilityType,
)
from app.mri_autonomous.experience_store import ExperienceStore
from app.mri_autonomous.intelligence_cycle import IntelligenceCycle
from app.mri_autonomous.strategy_dispatch import dispatch_with_learning

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "evidence_local_validation" / "dispatch_011"


def registry():
    r = CapabilityRegistry(auto_probe=False)
    for sid, cost in (("A", 1.0), ("B", 2.0), ("C", 3.0)):
        r.register(CapabilityDefinition(
            capability_id=sid, marketplace="Falabella",
            capability_type=CapabilityType.PRODUCT_EXTRACTION,
            adapter_mode=(AdapterExecutionMode.HTTP_SSR if sid == "A"
                          else AdapterExecutionMode.HEADLESS_PLAYWRIGHT),
            supported_surfaces=["category"], health=CapabilityHealth.HEALTHY,
            cost_weight=cost, success_rate=0.0))
    return r


class DispatchTests(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.work = TMP / uuid.uuid4().hex
        self.work.mkdir(parents=True, exist_ok=True)
        self.db = self.work / "experience.db"

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def cycle(self):
        return IntelligenceCycle(store=ExperienceStore(self.db), registry=registry())

    def test_real_dispatch_fallback_and_reuse(self):
        calls = []

        def a(ctx):
            calls.append("A")
            return {"success": False, "failure_type": "HTTP_500",
                    "evidence": {"surface": "category"}}

        def b(ctx):
            calls.append("B")
            return {"success": True, "evidence": {"surface": "category"}}

        first = dispatch_with_learning(
            self.cycle(), "Falabella", {"A": a, "B": b}, surface="category")
        self.assertTrue(first["success"])
        self.assertEqual(calls, ["A", "B"])
        self.assertEqual(first["attempts"][0]["executed_strategy"], "A")
        self.assertEqual(first["attempts"][1]["executed_strategy"], "B")
        self.assertTrue(first["experience_recorded"])

        calls.clear()
        second = dispatch_with_learning(
            self.cycle(), "Falabella", {"A": a, "B": b}, surface="category")
        self.assertTrue(second["success"])
        self.assertEqual(calls, ["B"])
        self.assertEqual(second["executed_strategy"], "B")

    def test_adaptive_recovery_and_rejected_never_executed(self):
        calls = []

        def a(ctx):
            calls.append("A")
            return {"success": False, "failure_type": "HTTP_500"}

        def b(ctx):
            calls.append("B")
            return {"success": False, "failure_type": "BROWSER_BLOCKED"}

        def c(ctx):
            calls.append("C")
            return {"success": True}

        cycle = self.cycle()
        # A and B fail; dispatcher must adapt to C.
        first = dispatch_with_learning(
            cycle, "Falabella", {"A": a, "B": b, "C": c}, surface="category")
        self.assertTrue(first["success"])
        self.assertEqual(first["executed_strategy"], "C")
        self.assertEqual(calls, ["A", "B", "C"])

        cycle.reject("Falabella", "A", "reproduced HTTP failure")
        calls.clear()
        result = dispatch_with_learning(
            cycle, "Falabella", {"A": a, "B": b, "C": c}, surface="category")
        self.assertTrue(result["success"])
        self.assertNotIn("A", calls)
        self.assertEqual(result["executed_strategy"], "C")


if __name__ == "__main__":
    unittest.main()
