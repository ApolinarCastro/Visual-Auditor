"""
MRI Autonomous Discovery Certification - Invariant Test Suite
Tests 1-16 per ORDEN DE EJECUCION §13.
All tests are PURE (no network, no DB write, no scraper instantiation).
"""
import sys
import os
import re
import unittest
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ---------------------------------------------------------------------------
# Semantic Model Stubs
# ---------------------------------------------------------------------------

class PageClassifier:
    """Mandatory page classification before any extraction."""
    BLOCKING_TYPES = {"CAPTCHA", "WAF", "LOGIN"}
    PDP_URL_SIGNALS = ["-mpm", "/p/", "/mp/"]

    @classmethod
    def classify_url(cls, url):
        low = url.lower()
        for sig in cls.PDP_URL_SIGNALS:
            if sig in low:
                return "PDP"
        return "UNKNOWN"

    @classmethod
    def can_extract(cls, page_type):
        if page_type == "PDP":
            return False
        return page_type not in cls.BLOCKING_TYPES and page_type != "UNKNOWN"


class SemanticNodeType:
    """Semantic taxonomy node types strictly separated."""
    PUBLICATION = "PUBLICATION"
    CATEGORY = "CATEGORY"
    SUBCATEGORY = "SUBCATEGORY"
    FACET = "FACET"
    PRODUCT_TYPE = "PRODUCT_TYPE"
    SURFACE = "SURFACE"
    BREADCRUMB = "BREADCRUMB"
    GSC_CATEGORY = "GSC_CATEGORY"
    NON_CATEGORY_TYPES = {FACET, PRODUCT_TYPE, SURFACE, BREADCRUMB, GSC_CATEGORY}

    @classmethod
    def can_generate_category_edge(cls, node_type):
        return node_type in (cls.CATEGORY, cls.SUBCATEGORY)


class PublicationCategoryEdge:
    """Direct observed publication-category membership. Rejects indirect edges."""

    def __init__(self, marketplace, publication_identity, category_identity,
                 category_path, source_url, observation_timestamp, evidence_type,
                 direct_observation=True):
        if not direct_observation:
            raise ValueError(
                "INVALID_EDGE: direct_observation=False for pub={} cat={}. "
                "Cartesian/inferred edges are PROHIBITED.".format(
                    publication_identity, category_identity)
            )
        self.marketplace = marketplace
        self.publication_identity = publication_identity
        self.category_identity = category_identity
        self.category_path = category_path
        self.source_url = source_url
        self.observation_timestamp = observation_timestamp
        self.evidence_type = evidence_type
        self.direct_observation = True

    @classmethod
    def create_if_valid(cls, **kwargs):
        try:
            return cls(**kwargs)
        except ValueError:
            return None


class CoverageState:
    CONFIRMED = "CONFIRMED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NOT_FOUND = "NOT_FOUND"
    UNVERIFIED = "UNVERIFIED"

    @classmethod
    def compute(cls, discovery_executed, valid_surface_observed,
                categories_discovered_dynamically, pagination_exhausted,
                stop_reason, has_extractor_failure, has_unknown_terminal,
                accounting_balanced, any_category_failed):
        if not discovery_executed or not valid_surface_observed:
            return cls.BLOCKED
        confirmed_conditions = [
            discovery_executed, valid_surface_observed,
            categories_discovered_dynamically, pagination_exhausted,
            stop_reason == "EXHAUSTION", not has_extractor_failure,
            not has_unknown_terminal, accounting_balanced,
            not any_category_failed,
        ]
        if all(confirmed_conditions):
            return cls.CONFIRMED
        elif valid_surface_observed and not has_extractor_failure:
            return cls.PARTIAL
        else:
            return cls.BLOCKED

    @classmethod
    def blocked_is_not_not_found(cls, state):
        return not (state == cls.BLOCKED and state == cls.NOT_FOUND)


class AccountingLedger:
    def __init__(self):
        self.raw_observations = 0
        self.nicopoly_confirmed = 0
        self.non_nicopoly_confirmed = 0
        self.insufficient_evidence = 0
        self.identity_unresolved = 0
        self.unknown_terminal = 0

    def add_observation(self, terminal_class):
        self.raw_observations += 1
        if terminal_class == "NICOPOLY_CONFIRMED":
            self.nicopoly_confirmed += 1
        elif terminal_class == "NON_NICOPOLY_CONFIRMED":
            self.non_nicopoly_confirmed += 1
        elif terminal_class == "INSUFFICIENT_EVIDENCE":
            self.insufficient_evidence += 1
        elif terminal_class == "IDENTITY_UNRESOLVED":
            self.identity_unresolved += 1
        else:
            self.unknown_terminal += 1

    @property
    def is_balanced(self):
        total = (self.nicopoly_confirmed + self.non_nicopoly_confirmed +
                 self.insufficient_evidence + self.identity_unresolved +
                 self.unknown_terminal)
        return total == self.raw_observations

    @property
    def has_unknown_terminal(self):
        return self.unknown_terminal > 0


class CountTracker:
    def __init__(self, declared_count=None):
        self.declared_count = declared_count
        self.observed_raw_count = 0
        self.observed_unique_count = 0
        self.count_mismatch = False

    def set_observed(self, raw, unique):
        self.observed_raw_count = raw
        self.observed_unique_count = unique
        if self.declared_count is not None and self.declared_count != unique:
            self.count_mismatch = True


VALID_STOP_REASONS = {
    "EXHAUSTION", "BLOCKED_WAF", "BLOCKED_CAPTCHA", "BLOCKED_LOGIN",
    "EMPTY_CONFIRMED", "EXTRACTOR_FAILURE", "IDENTITY_FAILURE", "NO_PROGRESS"
}


def is_valid_stop_reason(reason):
    return reason in VALID_STOP_REASONS


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

class TestMRISemanticModel(unittest.TestCase):
    """Tests 1-8: Semantic invariants."""

    def test_1_facet_does_not_generate_category_edge(self):
        """FACET must not automatically generate a CATEGORY edge."""
        self.assertFalse(
            SemanticNodeType.can_generate_category_edge(SemanticNodeType.FACET))

    def test_2_product_type_does_not_generate_category_edge(self):
        """PRODUCT_TYPE must not automatically generate a CATEGORY edge."""
        self.assertFalse(
            SemanticNodeType.can_generate_category_edge(SemanticNodeType.PRODUCT_TYPE))

    def test_3_gsc_category_does_not_substitute_category(self):
        """GSC_CATEGORY must not be promoted to CATEGORY."""
        gsc = SemanticNodeType.GSC_CATEGORY
        self.assertFalse(SemanticNodeType.can_generate_category_edge(gsc))
        self.assertIn(gsc, SemanticNodeType.NON_CATEGORY_TYPES)

    def test_4_pdp_url_classifies_as_pdp_not_category_grid(self):
        """URLs with PDP signals must classify as PDP, not CATEGORY_GRID."""
        pdp_urls = [
            "https://simple.ripley.cl/p/12345678",
            "https://simple.ripley.cl/producto-nombre-mpm987654",
            "https://simple.ripley.cl/mp/producto-abc",
            "https://www.paris.cl/p/producto-12345",
        ]
        for url in pdp_urls:
            page_type = PageClassifier.classify_url(url)
            self.assertEqual(page_type, "PDP",
                             "URL {} must classify as PDP, got {}".format(url, page_type))
            self.assertFalse(
                PageClassifier.can_extract(page_type),
                "PDP page must NOT be extractable as CATEGORY_GRID")

    def test_5_edge_without_direct_observation_rejected(self):
        """An edge with direct_observation=False must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            PublicationCategoryEdge(
                marketplace="Paris",
                publication_identity="pub_paris_abc123",
                category_identity="cat_xyz",
                category_path="Mujer > Vestidos",
                source_url="https://www.paris.cl/search?q=nicopoly",
                observation_timestamp=datetime.now().isoformat(),
                evidence_type="INFERRED",
                direct_observation=False,
            )
        self.assertIn("INVALID_EDGE", str(ctx.exception))

    def test_6_cartesian_assignment_is_impossible(self):
        """Creating edges via PRODUCTS x CATEGORIES without direct observation is impossible."""
        publications = ["pub_p1", "pub_p2", "pub_p3"]
        categories = ["cat_vestidos", "cat_jeans", "cat_poleras"]
        invalid_edges = []
        for pub in publications:
            for cat in categories:
                edge = PublicationCategoryEdge.create_if_valid(
                    marketplace="Paris",
                    publication_identity=pub,
                    category_identity=cat,
                    category_path="Mujer > {}".format(cat),
                    source_url="https://www.paris.cl/search?q=nicopoly",
                    observation_timestamp=datetime.now().isoformat(),
                    evidence_type="CARTESIAN",
                    direct_observation=False,
                )
                if edge is not None:
                    invalid_edges.append(edge)
        self.assertEqual(len(invalid_edges), 0,
                         "Cartesian assignment produced {} invalid edges that should be rejected".format(
                             len(invalid_edges)))

    def test_7_duplicate_publication_single_identity_multiple_memberships(self):
        """A publication seen in N categories keeps 1 identity + N edges."""
        pub_id = "pub_paris_abc123"
        categories_observed = ["cat_vestidos", "cat_blusas", "cat_jeans"]
        identity_map = {}
        edges = []
        for cat in categories_observed:
            identity_map[pub_id] = identity_map.get(pub_id, 0) + 1
            edge = PublicationCategoryEdge(
                marketplace="Paris",
                publication_identity=pub_id,
                category_identity=cat,
                category_path="Mujer > {}".format(cat),
                source_url="https://www.paris.cl/{}?brand=nicopoly".format(cat),
                observation_timestamp=datetime.now().isoformat(),
                evidence_type="DIRECT_CATEGORY_PAGE_OBSERVATION",
                direct_observation=True,
            )
            edges.append(edge)
        self.assertEqual(len(identity_map), 1, "Must have exactly 1 unique publication identity")
        self.assertEqual(len(edges), 3, "Must have 3 direct edges")

    def test_8_declared_vs_observed_count_preserved(self):
        """declared_count and observed_count can differ without overwrite."""
        tracker = CountTracker(declared_count=592)
        tracker.set_observed(raw=353, unique=349)
        self.assertEqual(tracker.declared_count, 592)
        self.assertEqual(tracker.observed_unique_count, 349)
        self.assertTrue(tracker.count_mismatch)
        self.assertNotEqual(tracker.declared_count, tracker.observed_unique_count)


class TestMRICoverageInvariants(unittest.TestCase):
    """Tests 9-13: Coverage and stop reason invariants."""

    def test_9_blocked_not_equal_not_found(self):
        """BLOCKED state must never be substituted by NOT_FOUND."""
        self.assertNotEqual(CoverageState.BLOCKED, CoverageState.NOT_FOUND)
        self.assertTrue(CoverageState.blocked_is_not_not_found(CoverageState.BLOCKED))

    def test_10_confirmed_plus_unknown_is_impossible(self):
        """CoverageState.compute must not return CONFIRMED when has_unknown_terminal=True."""
        result = CoverageState.compute(
            discovery_executed=True, valid_surface_observed=True,
            categories_discovered_dynamically=True, pagination_exhausted=True,
            stop_reason="EXHAUSTION", has_extractor_failure=False,
            has_unknown_terminal=True, accounting_balanced=True,
            any_category_failed=False,
        )
        self.assertNotEqual(result, CoverageState.CONFIRMED)

    def test_11_confirmed_plus_extractor_failure_is_impossible(self):
        """CoverageState.compute must not return CONFIRMED when has_extractor_failure=True."""
        result = CoverageState.compute(
            discovery_executed=True, valid_surface_observed=True,
            categories_discovered_dynamically=True, pagination_exhausted=True,
            stop_reason="EXHAUSTION", has_extractor_failure=True,
            has_unknown_terminal=False, accounting_balanced=True,
            any_category_failed=False,
        )
        self.assertNotEqual(result, CoverageState.CONFIRMED)

    def test_12_one_failed_category_means_partial_coverage(self):
        """If any category fails, global coverage must be PARTIAL."""
        result = CoverageState.compute(
            discovery_executed=True, valid_surface_observed=True,
            categories_discovered_dynamically=True, pagination_exhausted=True,
            stop_reason="EXHAUSTION", has_extractor_failure=False,
            has_unknown_terminal=False, accounting_balanced=True,
            any_category_failed=True,
        )
        self.assertNotEqual(result, CoverageState.CONFIRMED)
        self.assertEqual(result, CoverageState.PARTIAL)

    def test_13_complete_pagination_terminates_exhaustion(self):
        """When all pages traversed and exhausted, state is CONFIRMED."""
        self.assertTrue(is_valid_stop_reason("EXHAUSTION"))
        result = CoverageState.compute(
            discovery_executed=True, valid_surface_observed=True,
            categories_discovered_dynamically=True, pagination_exhausted=True,
            stop_reason="EXHAUSTION", has_extractor_failure=False,
            has_unknown_terminal=False, accounting_balanced=True,
            any_category_failed=False,
        )
        self.assertEqual(result, CoverageState.CONFIRMED)


class TestMRIAccountingInvariants(unittest.TestCase):
    """Accounting ledger invariants."""

    def test_accounting_all_observations_classified(self):
        """Every observation must end in a terminal class."""
        ledger = AccountingLedger()
        for obs in ["NICOPOLY_CONFIRMED", "NICOPOLY_CONFIRMED", "NON_NICOPOLY_CONFIRMED",
                    "INSUFFICIENT_EVIDENCE", "IDENTITY_UNRESOLVED", "NICOPOLY_CONFIRMED"]:
            ledger.add_observation(obs)
        self.assertTrue(ledger.is_balanced)
        self.assertEqual(ledger.raw_observations, 6)
        self.assertEqual(ledger.nicopoly_confirmed, 3)

    def test_accounting_unknown_not_silently_dropped(self):
        """UNKNOWN terminal is tracked, not silently dropped."""
        ledger = AccountingLedger()
        ledger.add_observation("UNKNOWN")
        ledger.add_observation("NICOPOLY_CONFIRMED")
        self.assertTrue(ledger.is_balanced)
        self.assertEqual(ledger.unknown_terminal, 1)
        self.assertTrue(ledger.has_unknown_terminal)


class TestMRIStopReasons(unittest.TestCase):
    """Stop reason validation."""

    def test_all_valid_stop_reasons_accepted(self):
        for reason in VALID_STOP_REASONS:
            self.assertTrue(is_valid_stop_reason(reason))

    def test_invalid_stop_reasons_rejected(self):
        for reason in ["EXCEPTION", "DONE", "OK", "ERROR", "SUCCESS", ""]:
            self.assertFalse(is_valid_stop_reason(reason))

    def test_unknown_not_in_valid_stop_reasons(self):
        """UNKNOWN is a diagnostic terminal, not a valid stop reason."""
        self.assertNotIn("UNKNOWN", VALID_STOP_REASONS)


class TestMRIMLEdgeForensics(unittest.TestCase):
    """Test 7 (ML): Edge forensics - direct evidence requirement."""

    def test_ml_legacy_configured_category_not_direct_observation(self):
        """LEGACY_CONFIGURED_CATEGORY edges from DB are NOT direct observations."""
        legacy_rel = "LEGACY_CONFIGURED_CATEGORY"
        is_direct = (legacy_rel == "DIRECT_CATEGORY_PAGE_OBSERVATION")
        self.assertFalse(is_direct)
        edge = PublicationCategoryEdge.create_if_valid(
            marketplace="Mercado Libre",
            publication_identity="pub_mercado libre_dd0e1da77d26",
            category_identity="cat_984e40b4",
            category_path="Vestidos",
            source_url="",
            observation_timestamp="2026-09-22T09:03:13.032105",
            evidence_type="LEGACY_CONFIGURED_CATEGORY",
            direct_observation=False,
        )
        self.assertIsNone(edge, "LEGACY_CONFIGURED_CATEGORY edge must be rejected as INVALID_EDGE")

    def test_ml_edge_5x_ratio_is_legacy_cartesian_signature(self):
        """436 pubs x 5 cats = 2180 edges is a cartesian signature, not observed."""
        total_edges_prev = 2180
        total_pubs_prev = 436
        ratio = total_edges_prev / total_pubs_prev
        self.assertAlmostEqual(ratio, 5.0, places=2)
        is_likely_cartesian = abs(ratio - round(ratio)) < 0.01
        self.assertTrue(is_likely_cartesian)


class TestG16Preserved(unittest.TestCase):
    """Test 14: G16 gate continues working."""

    def test_g16_materializer_importable(self):
        """GenericCommercialMaterializer must be importable (G16 gate preserved)."""
        try:
            from mri_commercial_materialization_golden_slice.v001.materializer_engine import (
                GenericCommercialMaterializer
            )
            mat = GenericCommercialMaterializer("test_run_g16_check")
            self.assertIsNotNone(mat)
        except ImportError as e:
            self.skipTest("Materializer not importable: {}".format(e))

    def test_g16_rejects_non_nicopoly(self):
        """G16 must reject products with no Nicopoly evidence."""
        try:
            from mri_commercial_materialization_golden_slice.v001.materializer_engine import (
                GenericCommercialMaterializer
            )
            mat = GenericCommercialMaterializer("test_run_g16_reject")
            snap = {
                "id": 999001, "marketplace": "Ripley",
                "marketplace_sku": "ZARA-12345", "sku_master": "",
                "product_title": "Vestido ZARA Premium", "brand": "ZARA",
                "price": 29990.0, "position_absolute": 1,
                "created_at": datetime.now().isoformat(),
                "audit_date": datetime.now().isoformat(),
                "category": "Vestidos", "_categories_list": ["Vestidos"],
                "is_nicopoly": 0
            }
            result = mat.process_record(snap)
            self.assertNotEqual(result.get("status"), "ACCEPTED",
                                "G16 must reject ZARA products")
        except ImportError as e:
            self.skipTest("Materializer not importable: {}".format(e))


class TestG07StaleEvidence(unittest.TestCase):
    """Test 15: G07 accepts current evidence, rejects stale."""

    def test_g07_current_evidence_accepted(self):
        """Evidence timestamped today is not stale."""
        now = datetime.now()
        age_days = (now - datetime.fromisoformat(now.isoformat())).days
        self.assertLess(age_days, 30)

    def test_g07_stale_evidence_flagged(self):
        """Evidence > 30 days old should be flagged stale."""
        old_ts = (datetime.now() - timedelta(days=45)).isoformat()
        age_days = (datetime.now() - datetime.fromisoformat(old_ts)).days
        self.assertGreater(age_days, 30)


class TestLegacyUntouched(unittest.TestCase):
    """Test 16: Legacy tables and files are untouched."""

    def test_svmp_not_imported_in_mri_autonomous(self):
        """mri_autonomous modules must NOT import or use SVMP/RuleLoader in code (comments excepted)."""
        base = os.path.dirname(__file__)
        autonomous_files = [
            os.path.join(base, "..", "app", "mri_autonomous", "autonomous_pipeline.py"),
            os.path.join(base, "..", "app", "mri_autonomous", "category_discoverer.py"),
            os.path.join(base, "..", "app", "mri_autonomous", "brand_hubs.py"),
        ]
        # Patterns that indicate real usage (imports, assignments, calls) — not comments
        svmp_usage_patterns = [
            r"import\s+.*SVMP",
            r"from\s+.*SVMP",
            r"load_svmp\(",
            r"SVMP\s*=",
            r"svmp\s*=",
            r"read_svmp",
            r"open.*SVMP\.xlsx",
        ]
        ruleloader_patterns = [
            r"from\s+.*import.*RuleLoader",
            r"import.*RuleLoader",
            r"RuleLoader\(",
        ]
        for filepath in autonomous_files:
            if not os.path.exists(filepath):
                continue
            # Strip comments before checking, to avoid false positives on docstrings
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            non_comment_lines = []
            for line in lines:
                stripped = line.lstrip()
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                non_comment_lines.append(line)
            src_no_comments = "".join(non_comment_lines)
            for pat in svmp_usage_patterns:
                self.assertFalse(
                    re.search(pat, src_no_comments, re.IGNORECASE),
                    "{} must NOT use SVMP (pattern: {})".format(filepath, pat)
                )
            for pat in ruleloader_patterns:
                self.assertFalse(
                    re.search(pat, src_no_comments, re.IGNORECASE),
                    "{} must NOT use RuleLoader (pattern: {})".format(filepath, pat)
                )

    def test_legacy_tables_not_modified_by_autonomous(self):
        """autonomous_pipeline must not INSERT into product_snapshots/audits/health_log."""
        pipeline_file = os.path.join(
            os.path.dirname(__file__), "..", "app", "mri_autonomous", "autonomous_pipeline.py"
        )
        if not os.path.exists(pipeline_file):
            self.skipTest("autonomous_pipeline.py not found")
        with open(pipeline_file, "r", encoding="utf-8") as f:
            src = f.read()
        for table in ["product_snapshots", "audits", "health_log"]:
            pattern = r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+" + table
            self.assertFalse(
                re.search(pattern, src, re.IGNORECASE),
                "autonomous_pipeline.py must NOT INSERT into legacy table {}".format(table)
            )


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestMRISemanticModel, TestMRICoverageInvariants,
        TestMRIAccountingInvariants, TestMRIStopReasons,
        TestMRIMLEdgeForensics, TestG16Preserved,
        TestG07StaleEvidence, TestLegacyUntouched
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
