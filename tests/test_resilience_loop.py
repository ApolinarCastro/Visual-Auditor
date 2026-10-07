import unittest
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.storage.sqlite_manager import SQLiteManager
from app.intelligence.quality_gate import QualityGate, QualityFlag, ReasonCode
from app.utils.circuit_breaker import CircuitBreaker, CircuitState


class TestResilienceLoop(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_file = Path(self.temp_dir.name) / "test_resilience.db"
        self.db = SQLiteManager(db_path=self.db_file)
        asyncio.run(self.db.init_db())

    def tearDown(self):
        self.temp_dir.cleanup()

    # ── 1. QUALITY GATE UNIT TESTS ───────────────────────────────────────────
    def test_quality_gate_normal_fresh(self):
        candidate = {
            "total_marketplace": 2086,
            "total_nicopoly": 106,
            "top_240": 1,
            "products_scraped_count": 240
        }
        previous = {
            "total_marketplace": 2086,
            "total_nicopoly": 106
        }
        flag, reason, _ = QualityGate.evaluate_candidate(candidate, previous)
        self.assertEqual(flag, QualityFlag.FRESH)
        self.assertEqual(reason, ReasonCode.NONE)

    def test_quality_gate_volume_drop_is_suspect(self):
        candidate = {
            "total_marketplace": 2086,
            "total_nicopoly": 90,
            "top_240": 5,
            "products_scraped_count": 240
        }
        previous = {
            "total_marketplace": 2086,
            "total_nicopoly": 140
        }
        flag, reason, _ = QualityGate.evaluate_candidate(candidate, previous)
        self.assertEqual(flag, QualityFlag.SUSPECT)
        self.assertEqual(reason, ReasonCode.VOLUME_DROP)

    def test_quality_gate_zero_anomaly_is_suspect(self):
        candidate = {
            "total_marketplace": 1500,
            "total_nicopoly": 0,
            "top_240": 0,
            "products_scraped_count": 240
        }
        previous = {
            "total_marketplace": 1500,
            "total_nicopoly": 45
        }
        flag, reason, _ = QualityGate.evaluate_candidate(candidate, previous)
        self.assertEqual(flag, QualityFlag.SUSPECT)
        self.assertEqual(reason, ReasonCode.ZERO_ANOMALY)

    def test_quality_gate_scraper_waf_error(self):
        flag, reason, _ = QualityGate.evaluate_candidate(
            candidate=None,
            previous=None,
            scraper_error="403 Forbidden Cloudflare WAF"
        )
        self.assertEqual(flag, QualityFlag.UNAVAILABLE)
        self.assertEqual(reason, ReasonCode.WAF_BLOCK)

    def test_quality_gate_scraper_captcha_error(self):
        flag, reason, _ = QualityGate.evaluate_candidate(
            candidate=None,
            previous=None,
            scraper_error="Captcha challenge encountered"
        )
        self.assertEqual(flag, QualityFlag.UNAVAILABLE)
        self.assertEqual(reason, ReasonCode.CAPTCHA)

    # ── 2. CIRCUIT BREAKER TRANSITIONS ──────────────────────────────────────
    def test_circuit_breaker_transitions(self):
        cb = CircuitBreaker(name="test_cb", failure_threshold=2, recovery_timeout=1, success_threshold=1)
        self.assertEqual(cb.state, CircuitState.CLOSED)

        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)

        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertTrue(cb.is_open())

    # ── 3. RECOVERY EXPERIENCE STORE ─────────────────────────────────────────
    def test_recovery_experience_store(self):
        async def run_test():
            exp_record = {
                "timestamp": datetime.now().isoformat(),
                "marketplace": "Paris",
                "category": "Blazers, Chaquetas y Abrigos",
                "failure_type": "VOLUME_DROP",
                "quality_flag": "RECOVERED",
                "strategy": "Selective Reaudit (test)",
                "attempt": 2,
                "result": "PROMOTED",
                "recovery_seconds": 4.5,
                "previous_value": "90",
                "candidate_value": "106",
                "promoted": True,
                "evidence": "Observed 106 on selective reaudit"
            }
            await self.db.save_recovery_experience(exp_record)
            experiences = await self.db.get_recovery_experiences(10)
            self.assertEqual(len(experiences), 1)
            self.assertEqual(experiences[0]["marketplace"], "Paris")
            self.assertEqual(experiences[0]["candidate_value"], "106")
            self.assertEqual(experiences[0]["promoted"], 1)

        asyncio.run(run_test())

    # ── 4. SOURCE HEALTH ISOLATION ───────────────────────────────────────────
    def test_source_health_isolation(self):
        async def run_test():
            await self.db.update_source_health({
                "marketplace": "Mercado Libre",
                "status": "DEGRADED",
                "consecutive_failures": 2,
                "failure_type": "TIMEOUT"
            })
            await self.db.update_source_health({
                "marketplace": "Paris",
                "status": "HEALTHY",
                "consecutive_failures": 0,
                "failure_type": None
            })

            meli_health = await self.db.get_source_health("Mercado Libre")
            paris_health = await self.db.get_source_health("Paris")

            self.assertEqual(meli_health[0]["status"], "DEGRADED")
            self.assertEqual(meli_health[0]["consecutive_failures"], 2)
            self.assertEqual(paris_health[0]["status"], "HEALTHY")
            self.assertEqual(paris_health[0]["consecutive_failures"], 0)

        asyncio.run(run_test())

    # ── 5. LAST GOOD CACHE & FALSE ZERO PROTECTION ──────────────────────────
    def test_last_good_cache_and_false_zero_protection(self):
        async def run_test():
            good_audit = {
                "audit_date": datetime.now().isoformat(),
                "marketplace": "Paris",
                "category": "Blazers, Chaquetas y Abrigos",
                "category_url": "https://www.paris.cl/mujer/moda/chaquetas-abrigos-parkas/",
                "total_marketplace": 2086,
                "total_nicopoly": 106,
                "top_30": 1,
                "top_60": 1,
                "top_90": 1,
                "top_120": 1,
                "top_240": 1,
                "pct_30": 0.94,
                "pct_60": 0.94,
                "pct_90": 0.94,
                "pct_120": 0.94,
                "pct_240": 0.94,
                "presence_level": "CRITICA",
                "risk_level": "CRITICO",
                "opportunity": "ALTA",
                "duration_seconds": 12.0
            }
            await self.db.save_audit(good_audit)

            last_good = await self.db.get_last_good_audit("Paris", "Blazers, Chaquetas y Abrigos")
            self.assertIsNotNone(last_good)
            self.assertEqual(last_good["total_nicopoly"], 106)
            self.assertEqual(last_good["total_marketplace"], 2086)

        asyncio.run(run_test())

    # ── 6. PARIS 90 -> 106 REGRESSION SCENARIO ──────────────────────────────
    def test_paris_90_to_106_regression_scenario(self):
        baseline_audit = {
            "audit_date": "2026-08-21T08:00:00.000000",
            "marketplace": "Paris",
            "category": "Blazers, Chaquetas y Abrigos",
            "category_url": "https://www.paris.cl/mujer/moda/chaquetas-abrigos-parkas/",
            "total_marketplace": 2086,
            "total_nicopoly": 106,
            "top_30": 1,
            "top_240": 1,
            "pct_30": 0.94,
            "pct_240": 0.94
        }
        candidate_recovered = {
            "total_marketplace": 2086,
            "total_nicopoly": 106,
            "top_240": 1,
            "products_scraped_count": 240
        }
        q, r, _ = QualityGate.evaluate_candidate(candidate_recovered, baseline_audit)
        self.assertEqual(q, QualityFlag.FRESH)
        self.assertEqual(r, ReasonCode.NONE)


if __name__ == "__main__":
    unittest.main()
