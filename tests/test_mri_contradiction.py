"""Unit tests for the real contradiction/drift rules (no network, no DB)."""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestCartesianRule(unittest.TestCase):
    def test_exact_cartesian_signature_flagged(self):
        from app.mri_autonomous.contradiction import cartesian_suspect
        res = cartesian_suspect(memberships=2180, unique_publications=436)
        self.assertTrue(res["suspect"])
        self.assertIn("5.0", res["evidence"])

    def test_healthy_ratio_not_flagged(self):
        from app.mri_autonomous.contradiction import cartesian_suspect
        res = cartesian_suspect(memberships=540, unique_publications=534)
        self.assertFalse(res["suspect"])

    def test_small_samples_never_flagged(self):
        from app.mri_autonomous.contradiction import cartesian_suspect
        res = cartesian_suspect(memberships=10, unique_publications=2)
        self.assertFalse(res["suspect"])

    def test_zero_pubs_safe(self):
        from app.mri_autonomous.contradiction import cartesian_suspect
        res = cartesian_suspect(memberships=0, unique_publications=0)
        self.assertFalse(res["suspect"])


class TestDrift(unittest.TestCase):
    def test_new_missing_stable_sets(self):
        from app.mri_autonomous.contradiction import drift
        res = drift(prior={"A", "B", "C"}, current={"B", "C", "D"})
        self.assertEqual(res["new"], ["D"])
        self.assertEqual(res["missing"], ["A"])
        self.assertEqual(res["stable"], ["B", "C"])

    def test_empty_prior_means_all_new(self):
        from app.mri_autonomous.contradiction import drift
        res = drift(prior=set(), current={"X"})
        self.assertEqual(res["new"], ["X"])
        self.assertEqual(res["missing"], [])


if __name__ == "__main__":
    unittest.main()
