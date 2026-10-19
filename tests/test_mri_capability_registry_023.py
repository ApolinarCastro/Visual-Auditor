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
        complete canonical capabilities across all 4 marketplaces.
        """
        reg = CapabilityRegistry()
        matrix = reg.get_marketplace_matrix()
        assert "Paris" in matrix
        assert "Falabella" in matrix
        assert "Mercado Libre" in matrix
        assert "Ripley" in matrix

        # Every marketplace must have at least one registered capability
        for mkt, caps in matrix.items():
            assert len(caps) >= 2, f"{mkt} must have at least primary and fallback capabilities"
            for cap in caps:
                assert cap["capability_id"]
                assert cap["capability_type"]
                assert cap["adapter_mode"]
                assert cap["health"] in ("HEALTHY", "DEGRADED", "BLOCKED")

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
        reg = CapabilityRegistry()
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
        reg = CapabilityRegistry()
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
        reg = CapabilityRegistry()
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
