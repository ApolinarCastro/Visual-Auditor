"""Unit tests for the hub-retry experience policy (no network, temp DB)."""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestHubRetryPolicy(unittest.TestCase):
    def test_retry_allowed_below_threshold(self):
        from app.mri_autonomous.autonomous_pipeline import should_retry_hub
        self.assertTrue(should_retry_hub(0))
        self.assertTrue(should_retry_hub(1))

    def test_retry_skipped_at_threshold(self):
        from app.mri_autonomous.autonomous_pipeline import should_retry_hub
        self.assertFalse(should_retry_hub(2))
        self.assertFalse(should_retry_hub(5))

    def test_streak_recorded_on_double_empty(self):
        import tempfile
        from app.mri_autonomous.experience_store import ExperienceStore
        tmp = tempfile.mkdtemp()
        st = ExperienceStore(db_path=os.path.join(tmp, "exp.db"))
        st.record_experience(marketplace="Falabella", brand="Nicopoly",
                             knowledge_type="SURFACE", value="Brand Hub",
                             is_success=False)
        st.record_experience(marketplace="Falabella", brand="Nicopoly",
                             knowledge_type="SURFACE", value="Brand Hub",
                             is_success=False)
        row = st.get_experience_item("Falabella", "Nicopoly", "SURFACE", "Brand Hub")
        self.assertEqual(row["consecutive_failures"], 2)

    def test_success_resets_streak(self):
        import tempfile
        from app.mri_autonomous.experience_store import ExperienceStore
        tmp = tempfile.mkdtemp()
        st = ExperienceStore(db_path=os.path.join(tmp, "exp.db"))
        for _ in range(2):
            st.record_experience(marketplace="Falabella", brand="Nicopoly",
                                 knowledge_type="SURFACE", value="Brand Hub",
                                 is_success=False)
        st.record_experience(marketplace="Falabella", brand="Nicopoly",
                             knowledge_type="SURFACE", value="Brand Hub",
                             is_success=True)
        row = st.get_experience_item("Falabella", "Nicopoly", "SURFACE", "Brand Hub")
        self.assertEqual(row["consecutive_failures"], 0)


if __name__ == "__main__":
    unittest.main()
