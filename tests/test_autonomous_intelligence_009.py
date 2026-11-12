"""Three-run learning/reuse/adaptation test for MRI-AUTONOMOUS-INTELLIGENCE-009."""
from __future__ import annotations

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
from app.mri_autonomous.intelligence_cycle import (
    APPROVED,
    OBSERVED,
    REJECTED,
    VALIDATED,
    IntelligenceCycle,
)

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "evidence_local_validation" / "intelligence_009"


def registry():
    r = CapabilityRegistry(auto_probe=False)
    for sid, cost in (("http_ssr", 1.0), ("browser", 2.0), ("ssr_fallback", 3.0)):
        r.register(CapabilityDefinition(
            capability_id=sid, marketplace="Falabella",
            capability_type=CapabilityType.PRODUCT_EXTRACTION,
            adapter_mode=(AdapterExecutionMode.HTTP_SSR if "http" in sid
                          else AdapterExecutionMode.HEADLESS_PLAYWRIGHT),
            supported_surfaces=["category", "search"],
            health=CapabilityHealth.HEALTHY, cost_weight=cost,
            success_rate=0.0,
        ))
    return r


class IntelligenceCycleTests(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.work = TMP / uuid.uuid4().hex
        self.work.mkdir(parents=True, exist_ok=True)
        self.db = self.work / "experience.db"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.work, ignore_errors=True)

    def _cycle(self):
        return IntelligenceCycle(
            store=ExperienceStore(self.db), registry=registry(),
            brand="Nicopoly")

    def test_three_run_learning_reuse_adaptation(self):
        calls = []

        def execute_a(strategy, ctx):
            calls.append(strategy)
            if strategy == "http_ssr":
                return {"success": False, "failure_type": "HTTP_500",
                        "evidence": {"surface": "category"}}
            return {"success": True, "evidence": {"surface": "category",
                                                  "hypothesis": "fallback"}}

        cycle_a = self._cycle()
        a = cycle_a.execute("Falabella", execute_a, surface="category")
        self.assertTrue(a["success"])
        self.assertEqual(a["attempts"], ["http_ssr", "browser"])
        self.assertEqual(a["selected_strategy"], "browser")
        item = ExperienceStore(self.db).get_experience_item(
            "Falabella", "Nicopoly", "STRATEGY", "browser")
        self.assertEqual(item["status"], OBSERVED)

        calls.clear()

        def execute_b(strategy, ctx):
            calls.append(strategy)
            return {"success": True, "evidence": {"surface": "category"}}

        cycle_b = self._cycle()
        b = cycle_b.execute("Falabella", execute_b, surface="category")
        self.assertTrue(b["success"])
        self.assertEqual(calls, ["browser"])
        self.assertEqual(b["attempts"], ["browser"])

        calls.clear()

        def execute_c(strategy, ctx):
            calls.append(strategy)
            if strategy == "browser":
                return {"success": False, "failure_type": "BROWSER_BLOCKED",
                        "evidence": {"surface": "category"}}
            return {"success": True, "evidence": {"surface": "category"}}

        cycle_c = self._cycle()
        c = cycle_c.execute("Falabella", execute_c, surface="category")
        self.assertTrue(c["success"])
        self.assertEqual(c["attempts"], ["browser", "ssr_fallback"])
        self.assertEqual(c["selected_strategy"], "ssr_fallback")

        gov = cycle_c.validate(
            "Falabella", "ssr_fallback", approved=False,
            evidence="three-run reproducibility")
        self.assertEqual(gov["status"], VALIDATED)
        rejected = cycle_c.reject(
            "Falabella", "http_ssr", "HTTP 500 reproduced twice")
        self.assertEqual(rejected["status"], REJECTED)
        self.assertEqual(
            ExperienceStore(self.db).get_experience_item(
                "Falabella", "Nicopoly", "STRATEGY", "http_ssr")["status"],
            REJECTED)

    def test_memory_retrieval_survives_new_store_instance(self):
        def execute(strategy, ctx):
            if strategy == "http_ssr":
                return {"success": False, "failure_type": "HTTP_500",
                        "evidence": {"surface": "category"}}
            return {"success": True, "evidence": {"surface": "category"}}

        cycle = self._cycle()
        cycle.execute("Falabella", execute, surface="category")
        fresh = IntelligenceCycle(store=ExperienceStore(self.db), registry=registry())
        recalled = fresh.recall("Falabella")
        self.assertGreaterEqual(len(recalled["strategies"]), 1)
        self.assertIn("browser", {s["strategy_id"] for s in recalled["strategies"]})

    def test_success_is_not_auto_promoted(self):
        def execute(strategy, ctx):
            return {"success": True, "evidence": {"surface": "category"}}

        cycle = self._cycle()
        result = cycle.execute("Falabella", execute, surface="category")
        self.assertEqual(result["knowledge_status"], OBSERVED)
        item = ExperienceStore(self.db).get_experience_item(
            "Falabella", "Nicopoly", "STRATEGY", result["selected_strategy"])
        self.assertNotEqual(item["status"], VALIDATED)
        approved = cycle.validate(
            "Falabella", result["selected_strategy"], approved=True,
            evidence="operator-approved reproducible evidence")
        self.assertEqual(approved["status"], APPROVED)

    def test_paris_empty_page_lesson_persists_and_retrieves(self):
        cycle = self._cycle()
        lesson = cycle.remember_paris_empty_page()
        self.assertEqual(lesson["status"], OBSERVED)
        fresh = IntelligenceCycle(
            store=ExperienceStore(self.db), registry=registry())
        recalled = fresh.recall_paris_empty_page()
        self.assertIsNotNone(recalled)
        self.assertEqual(recalled["status"], OBSERVED)
        self.assertIn("1793707172", recalled["evidence_reference"])
        self.assertNotEqual(recalled["status"], VALIDATED)


if __name__ == "__main__":
    unittest.main()
