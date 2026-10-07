"""Unit tests for Experience strategy learning (temp DB, no network)."""
import sys
import os
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestExperienceStrategy(unittest.TestCase):
    def _store(self):
        from app.mri_autonomous.experience_store import ExperienceStore
        tmp = tempfile.mkdtemp()
        return ExperienceStore(db_path=os.path.join(tmp, "exp.db"))

    def test_record_and_select_successful_strategy(self):
        st = self._store()
        st.record_strategy(marketplace="Paris", brand="Nicopoly",
                           strategy_id="s1", strategy_type="skip-known-failures",
                           surface="http://x/y", hypothesis="h",
                           attempt=1, result="SUCCESS", confidence=0.9)
        got = st.select_strategy(marketplace="Paris", brand="Nicopoly",
                                 strategy_type="skip-known-failures",
                                 surface="http://x/y")
        self.assertIsNotNone(got)
        self.assertEqual(got["strategy_id"], "s1")

    def test_no_strategy_returns_none(self):
        st = self._store()
        got = st.select_strategy(marketplace="Paris", brand="Nicopoly",
                                 strategy_type="nope", surface="http://x")
        self.assertIsNone(got)

    def test_decision_recorded_and_listed(self):
        st = self._store()
        st.record_strategy_decision(marketplace="Paris", brand="Nicopoly",
                                    strategy_id="s1", selected=True,
                                    reason="3 consecutive failures",
                                    expected_outcome="skip")
        ds = st.get_strategy_decisions(marketplace="Paris", brand="Nicopoly")
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0]["strategy_id"], "s1")

    def test_failed_strategy_preserved(self):
        st = self._store()
        st.record_strategy(marketplace="Ripley", brand="Nicopoly",
                           strategy_id="f1", strategy_type="pdp-recovery",
                           surface="http://x", hypothesis="h",
                           attempt=3, result="FAILED")
        bad = st.get_failed_strategies(marketplace="Ripley", brand="Nicopoly")
        self.assertTrue(any(r["strategy_id"] == "f1" for r in bad))


if __name__ == "__main__":
    unittest.main()
