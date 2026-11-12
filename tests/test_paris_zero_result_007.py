"""Regression tests for Paris empty-page classification (MRI-PARIS-007)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.mri_dashboard.acquisition_contract import (
    PARTIAL,
    empty_page_is_incomplete,
)


class ParisZeroResultTests(unittest.TestCase):
    def test_zero_results_with_zero_pages_is_incomplete(self):
        self.assertTrue(empty_page_is_incomplete(0, 0))
        self.assertNotEqual(empty_page_is_incomplete(0, 0), False)

    def test_real_empty_page_is_not_incomplete(self):
        self.assertFalse(empty_page_is_incomplete(0, 1))
        self.assertFalse(empty_page_is_incomplete(1, 0))
        self.assertFalse(empty_page_is_incomplete(3, 2))

    def test_partial_state_exists_for_incomplete_acquisition(self):
        self.assertEqual(PARTIAL, "PARTIAL")


if __name__ == "__main__":
    unittest.main()
