"""
app/mri_autonomous/capability_registry.py
MRI Capability Registry (RG-01 to RG-08)
Maintains registered capabilities, execution adapters, and marketplace capability matrices.
"""
from __future__ import annotations

import enum
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class CapabilityType(str, enum.Enum):
    CATALOG_DISCOVERY = "CATALOG_DISCOVERY"
    CATEGORY_FACET_ROUTING = "CATEGORY_FACET_ROUTING"
    PRODUCT_EXTRACTION = "PRODUCT_EXTRACTION"
    PAGINATION_TRAVERSAL = "PAGINATION_TRAVERSAL"
    OFFICIAL_STORE_ISOLATION = "OFFICIAL_STORE_ISOLATION"
    STEALTH_PAGE_READ = "STEALTH_PAGE_READ"
    WAF_CHALLENGE_DETECTION = "WAF_CHALLENGE_DETECTION"


class AdapterExecutionMode(str, enum.Enum):
    HEADLESS_PLAYWRIGHT = "HEADLESS_PLAYWRIGHT"
    HTTP_SSR = "HTTP_SSR"
    CDP_API_PUBLIC = "CDP_API_PUBLIC"
    STEALTH_MCP = "STEALTH_MCP"
    CONTROLLED_REPLAY = "CONTROLLED_REPLAY"


class CapabilityHealth(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    DISABLED = "DISABLED"


@dataclass
class CapabilityDefinition:
    capability_id: str
    marketplace: str
    capability_type: CapabilityType
    adapter_mode: AdapterExecutionMode
    supported_surfaces: List[str]
    health: CapabilityHealth = CapabilityHealth.HEALTHY
    cost_weight: float = 1.0  # Lower is preferred
    success_rate: float = 1.0
    failure_count: int = 0
    requires_auth: bool = False
    requires_stealth_mcp: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_verified_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "marketplace": self.marketplace,
            "capability_type": self.capability_type.value,
            "adapter_mode": self.adapter_mode.value,
            "supported_surfaces": self.supported_surfaces,
            "health": self.health.value,
            "cost_weight": self.cost_weight,
            "success_rate": self.success_rate,
            "failure_count": self.failure_count,
            "requires_auth": self.requires_auth,
            "requires_stealth_mcp": self.requires_stealth_mcp,
            "metadata": self.metadata,
            "registered_at": self.registered_at,
            "last_verified_at": self.last_verified_at,
        }


class CapabilityRegistry:
    """
    Central Capability Registry for Visual Auditor MRI (MRI-023).
    Implements Requirements RG-01 through RG-08.
    """

    def __init__(self):
        self._capabilities: Dict[str, CapabilityDefinition] = {}
        self._init_default_capabilities()

    def _init_default_capabilities(self):
        """Initializes canonical, certified capabilities across 4 marketplaces."""
        # 1. Paris.cl
        self.register(
            CapabilityDefinition(
                capability_id="paris_cdp_constructor_discovery",
                marketplace="Paris",
                capability_type=CapabilityType.CATALOG_DISCOVERY,
                adapter_mode=AdapterExecutionMode.CDP_API_PUBLIC,
                supported_surfaces=["search", "browse", "groups"],
                cost_weight=1.0,
                metadata={"provider": "Constructor.io", "api_key": "key_6PvQHDnR0zdWgEPh"},
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="paris_har_replay_fallback",
                marketplace="Paris",
                capability_type=CapabilityType.CATALOG_DISCOVERY,
                adapter_mode=AdapterExecutionMode.CONTROLLED_REPLAY,
                supported_surfaces=["search"],
                cost_weight=3.0,
                metadata={"file_target": "evidence/mri_rea_discovery_010/paris_search_capture.har"},
            )
        )

        # 2. Falabella.cl
        self.register(
            CapabilityDefinition(
                capability_id="falabella_ssr_next_data",
                marketplace="Falabella",
                capability_type=CapabilityType.PRODUCT_EXTRACTION,
                adapter_mode=AdapterExecutionMode.HTTP_SSR,
                supported_surfaces=["category", "brand", "search"],
                cost_weight=1.2,
                metadata={"dom_target": "__NEXT_DATA__"},
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="falabella_headless_playwright",
                marketplace="Falabella",
                capability_type=CapabilityType.PRODUCT_EXTRACTION,
                adapter_mode=AdapterExecutionMode.HEADLESS_PLAYWRIGHT,
                supported_surfaces=["category"],
                cost_weight=2.5,
                health=CapabilityHealth.DEGRADED,  # WAF 403 fallback trigger
                metadata={"challenge": "Cloudflare HTTP 403"},
            )
        )

        # 3. Mercado Libre
        self.register(
            CapabilityDefinition(
                capability_id="meli_official_store_crawler",
                marketplace="Mercado Libre",
                capability_type=CapabilityType.OFFICIAL_STORE_ISOLATION,
                adapter_mode=AdapterExecutionMode.HEADLESS_PLAYWRIGHT,
                supported_surfaces=["tienda/nicopoly", "listado"],
                cost_weight=1.5,
                metadata={"official_store_id": "56574"},
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="meli_stealth_mcp_reader",
                marketplace="Mercado Libre",
                capability_type=CapabilityType.STEALTH_PAGE_READ,
                adapter_mode=AdapterExecutionMode.STEALTH_MCP,
                supported_surfaces=["item", "catalog"],
                cost_weight=4.0,
                requires_stealth_mcp=True,
                metadata={"mcp_tool": "stealth_browser_page_read"},
            )
        )

        # 4. Ripley
        self.register(
            CapabilityDefinition(
                capability_id="ripley_headless_catalog_scraper",
                marketplace="Ripley",
                capability_type=CapabilityType.PRODUCT_EXTRACTION,
                adapter_mode=AdapterExecutionMode.HEADLESS_PLAYWRIGHT,
                supported_surfaces=["search", "category"],
                cost_weight=2.0,
                metadata={"profile": "Default"},
            )
        )
        self.register(
            CapabilityDefinition(
                capability_id="ripley_stealth_mcp_turnstile",
                marketplace="Ripley",
                capability_type=CapabilityType.STEALTH_PAGE_READ,
                adapter_mode=AdapterExecutionMode.STEALTH_MCP,
                supported_surfaces=["search", "pdp"],
                cost_weight=4.5,
                requires_stealth_mcp=True,
                metadata={"mcp_tool": "stealth_browser_page_read", "target_waf": "Cloudflare Turnstile"},
            )
        )

    def register(self, cap: CapabilityDefinition) -> None:
        """Registers or updates a capability in the registry (RG-01)."""
        self._capabilities[cap.capability_id] = cap
        logger.info(f"Registered capability: {cap.capability_id} for {cap.marketplace} [{cap.adapter_mode.value}]")

    def get(self, capability_id: str) -> Optional[CapabilityDefinition]:
        """Retrieves a capability by its unique ID (RG-02)."""
        return self._capabilities.get(capability_id)

    def list_capabilities(
        self,
        marketplace: Optional[str] = None,
        capability_type: Optional[CapabilityType] = None,
        only_healthy: bool = True
    ) -> List[CapabilityDefinition]:
        """Lists capabilities matching filters (RG-03)."""
        res = list(self._capabilities.values())
        if marketplace:
            res = [c for c in res if c.marketplace.lower() == marketplace.lower()]
        if capability_type:
            res = [c for c in res if c.capability_type == capability_type]
        if only_healthy:
            res = [c for c in res if c.health in (CapabilityHealth.HEALTHY, CapabilityHealth.DEGRADED)]
        return res

    def report_outcome(self, capability_id: str, success: bool, error_message: Optional[str] = None) -> None:
        """
        Updates capability health and success metrics following execution (RG-04).
        Implements circuit breaker when failures accumulate.
        """
        cap = self.get(capability_id)
        if not cap:
            return

        cap.last_verified_at = datetime.now(timezone.utc).isoformat()
        if success:
            cap.failure_count = max(0, cap.failure_count - 1)
            cap.success_rate = min(1.0, cap.success_rate * 0.9 + 0.1)
            if cap.health == CapabilityHealth.DEGRADED and cap.failure_count == 0:
                cap.health = CapabilityHealth.HEALTHY
        else:
            cap.failure_count += 1
            cap.success_rate = max(0.0, cap.success_rate * 0.9)
            if cap.failure_count >= 3:
                cap.health = CapabilityHealth.BLOCKED
                logger.warning(f"Capability {capability_id} transitioned to BLOCKED due to {cap.failure_count} consecutive failures.")
            elif cap.failure_count >= 1:
                cap.health = CapabilityHealth.DEGRADED

    def get_marketplace_matrix(self) -> Dict[str, List[Dict[str, Any]]]:
        """Returns the full 4-marketplace capability matrix (RG-05)."""
        mkts = ["Paris", "Falabella", "Mercado Libre", "Ripley"]
        matrix = {}
        for m in mkts:
            caps = self.list_capabilities(marketplace=m, only_healthy=False)
            matrix[m] = [c.to_dict() for c in caps]
        return matrix
