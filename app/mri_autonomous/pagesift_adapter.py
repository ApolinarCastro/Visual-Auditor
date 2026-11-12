"""Optional local HTTP adapter for PageSift (AGPL-3.0, external process).

MRI never vendors PageSift and never treats Markdown as verified publications.
The adapter is a candidate capability until real comparative evidence exists.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Optional

DEFAULT_URL = "http://127.0.0.1:3002"


class PageSiftAdapter:
    strategy_id = "pagesift_local_http"

    def __init__(self, base_url: Optional[str] = None, timeout: float = 45):
        self.base_url = (base_url or os.environ.get("MRI_PAGESIFT_URL")
                         or DEFAULT_URL).rstrip("/")
        self.timeout = timeout

    def health(self) -> dict:
        started = time.monotonic()
        try:
            req = urllib.request.Request(self.base_url + "/health",
                                         headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return {"status": "UP" if resp.status < 500 else "DEGRADED",
                        "http_status": resp.status,
                        "elapsed_ms": round((time.monotonic() - started) * 1000)}
        except Exception as exc:
            return {"status": "DOWN", "error": f"{type(exc).__name__}: {exc}",
                    "elapsed_ms": round((time.monotonic() - started) * 1000)}

    def scrape(self, url: str, *, formats=None) -> dict:
        started = time.monotonic()
        payload = json.dumps({"url": url, "formats": formats or ["markdown", "links"]}).encode()
        req = urllib.request.Request(
            self.base_url + "/v2/scrape", data=payload, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as exc:
            return {
                "marketplace": None, "strategy_id": self.strategy_id,
                "source_url": url, "acquisition_method": "PAGESIFT_HTTP",
                "raw_evidence_reference": None,
                "categories_discovered": 0, "hierarchy_edges_verified": 0,
                "publications_observed": 0, "pagination_status": "NOT_APPLICABLE",
                "source_status": "SOURCE_BLOCKED",
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "peak_memory_mb": "UNKNOWN",
                "errors": [f"{type(exc).__name__}: {exc}"], "warnings": [],
                "content": None,
            }
        data = raw.get("data", raw) if isinstance(raw, dict) else {}
        markdown = data.get("markdown") if isinstance(data, dict) else None
        links = data.get("links") or [] if isinstance(data, dict) else []
        warnings = data.get("warnings") or [] if isinstance(data, dict) else []
        return {
            "marketplace": None,
            "strategy_id": self.strategy_id,
            "source_url": url,
            "acquisition_method": "PAGESIFT_HTTP",
            "raw_evidence_reference": self.base_url + "/v2/scrape",
            "categories_discovered": 0,
            "hierarchy_edges_verified": 0,
            # Markdown is content evidence, never a verified publication.
            "publications_observed": 0,
            "pagination_status": "NOT_APPLICABLE",
            "source_status": "CONTENT_ONLY" if markdown else "INCOMPLETE",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "peak_memory_mb": "UNKNOWN",
            "errors": [],
            "warnings": list(warnings) + ([] if markdown else ["NO_MARKDOWN_CONTENT"]),
            "content": {"markdown": markdown, "links": links[:500],
                        "metadata": data.get("metadata") if isinstance(data, dict) else None},
            "observed_at": datetime.now().isoformat(),
        }


def register_pagesift_capabilities(registry, marketplaces=None) -> int:
    """Register PageSift as UNKNOWN/CANDIDATE; never HEALTHY without evidence."""
    from app.mri_autonomous.capability_registry import (
        AdapterExecutionMode, CapabilityDefinition, CapabilityHealth,
        CapabilityType)
    count = 0
    for mkt in marketplaces or ["Falabella", "Mercado Libre", "Ripley", "Paris"]:
        cid = f"pagesift_local_{mkt.lower().replace(' ', '_')}"
        try:
            registry.register(CapabilityDefinition(
                capability_id=cid, marketplace=mkt,
                capability_type=CapabilityType.PRODUCT_EXTRACTION,
                adapter_mode=AdapterExecutionMode.HTTP_SSR,
                supported_surfaces=["page"], health=CapabilityHealth.UNKNOWN,
                cost_weight=0.4, success_rate=0.0))
            count += 1
        except Exception:
            pass
    return count


def probe() -> dict:
    adapter = PageSiftAdapter()
    return {"base_url": adapter.base_url, "health": adapter.health(),
            "license": "AGPL-3.0", "installed": False,
            "status": "CANDIDATE_UNVERIFIED"}
