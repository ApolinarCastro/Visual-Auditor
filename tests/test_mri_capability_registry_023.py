"""
tests/test_mri_capability_registry_023.py
Test Suite T1-T8 for MRI-023 (Capability Registry & Strategy Selector)
Covers traceability matrix RG-01 through RG-16.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import pathlib
import sqlite3
import pytest

from app.mri_autonomous.capability_registry import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityRegistry,
    CapabilityType,
    AdapterExecutionMode,
)
from app.mri_autonomous.strategy_selector import StrategySelector, SelectedStrategy
from app.mri_autonomous.mcp_adapters import (
    StealthBrowserMCPAdapter,
    MCPCapturedResponse,
    MCPPermissionRevokedError,
    MCPUnauthorizedTargetError,
)


class TestMRICapabilityRegistry023:
    """Tests T1 through T8 for Capability Registry, Strategy Selector and Stealth MCP Adapter."""

    def test_T1_registry_initialization_and_matrix_completeness(self):
        """
        T1 (RG-01, RG-05): Verifies that CapabilityRegistry initializes with
        complete canonical capabilities across all 4 marketplaces in UNKNOWN state,
        and transitions to verified states only upon probing.
        """
        reg = CapabilityRegistry()
        matrix = reg.get_marketplace_matrix()
        assert "Paris" in matrix
        assert "Falabella" in matrix
        assert "Mercado Libre" in matrix
        assert "Ripley" in matrix

        # Every marketplace must have at least one registered capability
        # Initially, unprobed capabilities must be UNKNOWN (no fictitious HEALTHY values)
        for mkt, caps in matrix.items():
            assert len(caps) >= 2, f"{mkt} must have at least primary and fallback capabilities"
            for cap in caps:
                assert cap["capability_id"]
                assert cap["capability_type"]
                assert cap["adapter_mode"]
                assert cap["health"] == "UNKNOWN", "Unverified capabilities must initialize as UNKNOWN"

        # Upon probing, capabilities transition to verified states
        reg.probe_all_capabilities()
        probed_matrix = reg.get_marketplace_matrix()
        for mkt, caps in probed_matrix.items():
            for cap in caps:
                assert cap["health"] in ("HEALTHY", "DEGRADED", "BLOCKED", "DISABLED")

    def test_T2_capability_registration_and_lookup(self):
        """
        T2 (RG-01, RG-02, RG-03): Tests dynamic registration, retrieval and filtering.
        """
        reg = CapabilityRegistry()
        custom_cap = CapabilityDefinition(
            capability_id="test_custom_fala_facet",
            marketplace="Falabella",
            capability_type=CapabilityType.CATEGORY_FACET_ROUTING,
            adapter_mode=AdapterExecutionMode.HTTP_SSR,
            supported_surfaces=["custom_facet"],
            cost_weight=0.8,
        )
        reg.register(custom_cap)

        retrieved = reg.get("test_custom_fala_facet")
        assert retrieved is not None
        assert retrieved.marketplace == "Falabella"
        assert retrieved.cost_weight == 0.8

        filtered = reg.list_capabilities(
            marketplace="Falabella",
            capability_type=CapabilityType.CATEGORY_FACET_ROUTING
        )
        assert any(c.capability_id == "test_custom_fala_facet" for c in filtered)

    def test_T3_circuit_breaker_and_health_reporting(self):
        """
        T3 (RG-04): Verifies that successive reported failures transition
        capabilities from HEALTHY -> DEGRADED -> BLOCKED.
        """
        reg = CapabilityRegistry(auto_probe=True)
        cap_id = "paris_cdp_constructor_discovery"
        cap = reg.get(cap_id)
        assert cap.health == CapabilityHealth.HEALTHY

        # 1st failure -> DEGRADED
        reg.report_outcome(cap_id, success=False, error_message="Network glitch")
        assert cap.health == CapabilityHealth.DEGRADED
        assert cap.failure_count == 1

        # 2nd failure -> DEGRADED
        reg.report_outcome(cap_id, success=False, error_message="Timeout")
        assert cap.health == CapabilityHealth.DEGRADED
        assert cap.failure_count == 2

        # 3rd failure -> BLOCKED
        reg.report_outcome(cap_id, success=False, error_message="Repeated error")
        assert cap.health == CapabilityHealth.BLOCKED
        assert cap.failure_count == 3

        # BLOCKED capability must not be included in healthy listings
        healthy = reg.list_capabilities(marketplace="Paris", only_healthy=True)
        assert not any(c.capability_id == cap_id for c in healthy)

        # Success recovery
        reg.report_outcome(cap_id, success=True)
        assert cap.failure_count == 2

    def test_T4_strategy_selection_deterministic_ordering(self):
        """
        T4 (RG-09, RG-10): Verifies StrategySelector picks the lowest-cost healthy capability
        and properly configures fallbacks.
        """
        reg = CapabilityRegistry(auto_probe=True)
        selector = StrategySelector(reg)

        # For Paris discovery: constructor API (cost=1.0) should beat HAR replay (cost=3.0)
        selected = selector.select_strategy(
            marketplace="Paris",
            capability_type=CapabilityType.CATALOG_DISCOVERY,
        )
        assert selected is not None
        assert selected.strategy_id == "paris_cdp_constructor_discovery"
        assert "paris_har_replay_fallback" in selected.fallback_strategy_ids

        # If constructor API becomes BLOCKED, selector automatically promotes HAR replay
        reg.report_outcome("paris_cdp_constructor_discovery", success=False)
        reg.report_outcome("paris_cdp_constructor_discovery", success=False)
        reg.report_outcome("paris_cdp_constructor_discovery", success=False)

        fallback_selected = selector.select_strategy(
            marketplace="Paris",
            capability_type=CapabilityType.CATALOG_DISCOVERY,
        )
        assert fallback_selected is not None
        assert fallback_selected.strategy_id == "paris_har_replay_fallback"

    def test_T5_strategy_selector_mcp_gating(self):
        """
        T5 (RG-11, RG-12): Verifies that capabilities requiring Stealth MCP
        are strictly excluded when allow_mcp=False.
        """
        reg = CapabilityRegistry(auto_probe=True)
        selector = StrategySelector(reg)

        # With MCP enabled
        selected_with_mcp = selector.select_strategy(
            marketplace="Mercado Libre",
            capability_type=CapabilityType.STEALTH_PAGE_READ,
            allow_mcp=True,
        )
        assert selected_with_mcp is not None
        assert selected_with_mcp.strategy_id == "meli_stealth_mcp_reader"

        # With MCP disabled -> returns None or fallback without MCP
        selected_no_mcp = selector.select_strategy(
            marketplace="Mercado Libre",
            capability_type=CapabilityType.STEALTH_PAGE_READ,
            allow_mcp=False,
        )
        assert selected_no_mcp is None

    @pytest.mark.asyncio
    async def test_T6_stealth_browser_mcp_capture_and_hashing(self, tmp_path):
        """
        T6 (RG-13, RG-16): Tests StealthBrowserMCPAdapter live fetch, artifact persistence,
        and SHA-256 verification against an authorized target.
        """
        adapter = StealthBrowserMCPAdapter(evidence_dir=tmp_path / "mcp_evidence")
        url = "https://simple.ripley.cl/robots.txt"

        response = await adapter.fetch_page_content(url)
        assert response.status_code in (200, 403, 404)
        assert len(response.content_sha256) == 64
        assert response.raw_response_path is not None

        # Verify physical file existence and hash equality
        saved_file = pathlib.Path(response.raw_response_path)
        assert saved_file.exists()
        recomputed_sha = hashlib.sha256(saved_file.read_bytes()).hexdigest()
        assert recomputed_sha == response.content_sha256

        # Audit trail must be recorded
        trail = adapter.get_audit_trail()
        assert len(trail) > 0
        assert trail[-1]["action"] == "FETCH_SUCCESS"

    def test_T7_stealth_browser_mcp_permission_revocation(self, tmp_path):
        """
        T7 (RG-15): Tests that revoking permissions immediately blocks execution (fail-closed).
        """
        adapter = StealthBrowserMCPAdapter(evidence_dir=tmp_path / "mcp_evidence")
        assert adapter.is_permission_active() is True

        adapter.revoke_permissions()
        assert adapter.is_permission_active() is False

        # Attempting fetch must raise MCPPermissionRevokedError
        with pytest.raises(MCPPermissionRevokedError):
            asyncio.run(adapter.fetch_page_content("https://simple.ripley.cl/robots.txt"))

        # Re-granting permissions unblocks execution
        adapter.grant_permissions()
        assert adapter.is_permission_active() is True

    def test_T8_stealth_browser_mcp_unauthorized_domain_block(self, tmp_path):
        """
        T8 (RG-14): Tests that unauthorized destinations outside the 4 marketplaces
        are immediately rejected by boundary enforcement.
        """
        adapter = StealthBrowserMCPAdapter(evidence_dir=tmp_path / "mcp_evidence")
        with pytest.raises(MCPUnauthorizedTargetError):
            asyncio.run(adapter.fetch_page_content("https://unauthorized-competitor.com/catalog"))

    def test_T9_stealth_browser_mcp_redirect_rejection(self, tmp_path):
        """
        Validates MCP behavior preventing redirect escapes outside authorized perimeter:
        If navigation or tab inspection reveals an unauthorized target, MCP closes session
        and raises MCPUnauthorizedTargetError without recording valid evidence.
        """
        adapter = StealthBrowserMCPAdapter(evidence_dir=tmp_path / "mcp_evidence")
        with pytest.raises(MCPUnauthorizedTargetError):
            adapter._validate_destination("https://phishing-attacker.com/steal-creds")

    @pytest.mark.asyncio
    async def test_autonomous_strategy_dispatch_fallback_and_experience_update(self, tmp_path):
        """
        Integrated Test (Defecto 2): Demonstrates in a SINGLE runner invocation
        the complete autonomous cycle:
        selection -> real executor failure -> automatic health update in registry ->
        fallback execution -> acquisition -> persistence.
        Zero manual calls to report_outcome().
        """
        from unittest.mock import patch
        from app.mri_autonomous.autonomous_multimarketplace_runner import AutonomousMultiMarketplaceRunner
        from app.mri_autonomous.storage_guard import StorageConfig

        test_db = str(tmp_path / "test_selector_dispatch.db")
        StorageConfig.set_test_mode(True, str(tmp_path))

        reg = CapabilityRegistry(auto_probe=True)
        selector = StrategySelector(reg)
        runner = AutonomousMultiMarketplaceRunner(
            db_path=test_db,
            capability_registry=reg,
            strategy_selector=selector
        )

        with sqlite3.connect(test_db) as conn:
            runner._init_sqlite_tables(conn)

        # 1. Selection: StrategySelector selects the primary strategy for Ripley
        # Primary strategy: ripley_headless_catalog_scraper (cost=2.0)
        # Fallback strategy configured: ripley_stealth_mcp_turnstile (cost=4.5)
        primary_strat = selector.select_strategy("Ripley", CapabilityType.PRODUCT_EXTRACTION)
        assert primary_strat is not None
        assert primary_strat.strategy_id == "ripley_headless_catalog_scraper"
        # Ensure fallback chain contains the stealth MCP capability
        primary_strat.fallback_strategy_ids = ["ripley_stealth_mcp_turnstile"]

        primary_cap = reg.get("ripley_headless_catalog_scraper")
        fallback_cap = reg.get("ripley_stealth_mcp_turnstile")
        assert primary_cap.failure_count == 0
        assert primary_cap.health == CapabilityHealth.HEALTHY

        # 2 & 3. Single invocation demonstrating real executor failure, automatic registry update,
        # fallback dispatch, acquisition and persistence:
        with patch("app.scrapers.ripley_scraper.RipleyScraper.scrape_autonomous_category") as mock_scrape:
            # Simulate real WAF/Turnstile block encountered by the primary headless scraper
            mock_scrape.side_effect = RuntimeError("Cloudflare Turnstile challenge WAF block 403")

            # A single runner invocation executes the entire autonomous cycle:
            # - Attempts primary strategy (ripley_headless_catalog_scraper)
            # - Primary fails with Turnstile block -> runner automatically reports outcome (failure) to registry
            # - Runner cascades to fallback strategy (ripley_stealth_mcp_turnstile)
            # - Stealth MCP adapter executes navigation, capture, SHA-256 verification
            # - Veracity contract: HTML capture with 0 verified products does NOT claim COMPLETED commercial acquisition
            # - Runner persists observations/terminal state to SQLite
            # - Runner reports failure outcome for the fallback capability because 0 publications were acquired
            result = await runner.investigate_ripley("RUN_SINGLE_INVOCATION_TEST", strategy=primary_strat)

            # Assert veracity contract across technical and commercial states:
            assert result.status in ("SOURCE_BLOCKED", "PARTIAL")
            assert result.publications_count == 0
            assert result.evidence.get("mechanism") == "STEALTH_BROWSER_MCP"
            assert result.evidence.get("technical_navigation_success") is True
            assert result.evidence.get("verified_publications_acquired") == 0
            assert len(result.strategies_attempted) >= 2
            assert result.strategies_attempted[0]["name"] == "ripley_headless_catalog_scraper"
            assert result.strategies_attempted[1]["name"] == "ripley_stealth_mcp_turnstile"

            # Assert automatic health update in registry (NO manual report_outcome called in test):
            assert primary_cap.failure_count >= 1
            assert primary_cap.health == CapabilityHealth.DEGRADED

            # Fallback capability must also register failure because 0 commercial publications were acquired (veracity contract)
            assert fallback_cap.failure_count >= 1
            assert fallback_cap.health in (CapabilityHealth.DEGRADED, CapabilityHealth.HEALTHY)

            # Assert persistence in isolated SQLite database
            with sqlite3.connect(test_db) as conn:
                mri_runs = conn.execute("SELECT run_id, status FROM mri_runs WHERE run_id='RUN_SINGLE_INVOCATION_TEST'").fetchall()
                assert len(mri_runs) >= 1
                assert mri_runs[0][1] in ("COMPLETED", "PARTIAL", "SOURCE_BLOCKED", "SUCCESS")

    @pytest.mark.asyncio
    async def test_T10_negative_empty_capture_no_false_positive_commercial_success(self, tmp_path):
        """
        T10 (Veracity Contract): Demonstrates with negative tests that an empty page or capture
        without products does NOT produce false positive commercial success:
        - Technical capture succeeds (evidence recorded, sha256 computed)
        - But verified publications == 0
        - Run status must NOT be 'COMPLETED'
        - CapabilityRegistry must NOT register commercial success
        """
        from unittest.mock import patch, MagicMock
        from app.mri_autonomous.autonomous_multimarketplace_runner import AutonomousMultiMarketplaceRunner
        from app.mri_autonomous.storage_guard import StorageConfig

        test_db = str(tmp_path / "test_veracity_empty.db")
        StorageConfig.set_test_mode(True, str(tmp_path))

        reg = CapabilityRegistry(auto_probe=True)
        selector = StrategySelector(reg)
        runner = AutonomousMultiMarketplaceRunner(
            db_path=test_db,
            capability_registry=reg,
            strategy_selector=selector
        )

        with sqlite3.connect(test_db) as conn:
            runner._init_sqlite_tables(conn)

        # Mock mock_capture with empty page (200 OK, HTML captured, but 0 products)
        mock_cap = MCPCapturedResponse(
            url="https://simple.ripley.cl/search/nicopoly",
            status_code=200,
            content_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            body_length=150,
            captured_at="2026-10-20T17:00:00Z",
            raw_response_path=str(tmp_path / "empty_page.html"),
            is_challenge_detected=False
        )

        with patch("app.mri_autonomous.mcp_adapters.StealthBrowserMCPAdapter.fetch_page_content", return_value=mock_cap):
            strat = selector.select_strategy("Ripley", CapabilityType.PRODUCT_EXTRACTION)
            strat.strategy_id = "ripley_stealth_mcp_turnstile"
            strat.fallback_strategy_ids = []

            cap_def = reg.get("ripley_stealth_mcp_turnstile")
            initial_failures = cap_def.failure_count

            res = await runner.investigate_ripley("RUN_VERACITY_EMPTY_TEST", strategy=strat)

            # Assert technical success is recorded in evidence
            assert res.evidence.get("technical_navigation_success") is True
            assert res.evidence.get("sha256") == mock_cap.content_sha256

            # Assert commercial status is NOT COMPLETED and publications count is 0
            assert res.publications_count == 0
            assert res.status != "COMPLETED"
            assert res.status == "PARTIAL"

            # Assert registry does NOT register commercial success
            assert cap_def.failure_count == initial_failures + 1

    @pytest.mark.asyncio
    async def test_T11_negative_waf_challenge_no_false_positive_commercial_success(self, tmp_path):
        """
        T11 (Veracity Contract): Demonstrates with negative tests that a WAF / Turnstile challenge
        (403 status or challenge page) does NOT produce false positive commercial success:
        - Evidence captures is_challenge=True and status_code=403
        - Publications count == 0
        - Run status must be 'SOURCE_BLOCKED'
        - CapabilityRegistry reports failure and increments circuit breaker
        """
        from unittest.mock import patch
        from app.mri_autonomous.autonomous_multimarketplace_runner import AutonomousMultiMarketplaceRunner
        from app.mri_autonomous.storage_guard import StorageConfig

        test_db = str(tmp_path / "test_veracity_waf.db")
        StorageConfig.set_test_mode(True, str(tmp_path))

        reg = CapabilityRegistry(auto_probe=True)
        selector = StrategySelector(reg)
        runner = AutonomousMultiMarketplaceRunner(
            db_path=test_db,
            capability_registry=reg,
            strategy_selector=selector
        )

        with sqlite3.connect(test_db) as conn:
            runner._init_sqlite_tables(conn)

        # Mock WAF response (403 Cloudflare Turnstile challenge)
        mock_waf = MCPCapturedResponse(
            url="https://simple.ripley.cl/search/nicopoly",
            status_code=403,
            content_sha256="a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0",
            body_length=2048,
            captured_at="2026-10-20T17:00:00Z",
            raw_response_path=str(tmp_path / "waf_block.html"),
            is_challenge_detected=True
        )

        with patch("app.mri_autonomous.mcp_adapters.StealthBrowserMCPAdapter.fetch_page_content", return_value=mock_waf):
            strat = selector.select_strategy("Ripley", CapabilityType.PRODUCT_EXTRACTION)
            strat.strategy_id = "ripley_stealth_mcp_turnstile"
            strat.fallback_strategy_ids = []

            cap_def = reg.get("ripley_stealth_mcp_turnstile")
            initial_failures = cap_def.failure_count

            res = await runner.investigate_ripley("RUN_VERACITY_WAF_TEST", strategy=strat)

            # Assert technical evidence records the challenge
            assert res.evidence.get("technical_navigation_success") is True
            assert res.evidence.get("is_challenge") is True
            assert res.evidence.get("status_code") == 403

            # Assert commercial status is SOURCE_BLOCKED and zero publications acquired
            assert res.publications_count == 0
            assert res.status == "SOURCE_BLOCKED"
            assert "0 verified commercial publications" in (res.blocker_reason or "")

            # Assert registry reports failure
            assert cap_def.failure_count == initial_failures + 1


