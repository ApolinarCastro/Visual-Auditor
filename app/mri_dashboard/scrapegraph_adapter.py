"""
Optional ScrapeGraphAI adapter for MRI (MRI-SCRAPEGRAPHAI-INTEGRATION-001).

Policy:
  * DISABLED by default (`SCRAPEGRAPHAI_ENABLED=false`).
  * Works ONLY on content already acquired by MRI (HTML/structured payload);
    it never navigates, never writes to SQLite/API/dashboard and never touches
    official results.
  * ScrapeGraphAI PROPOSES values; MRI validates. Unknowns stay `null`.
  * Any failure degrades to `extraction_status != OK` and MRI continues.

The library is imported lazily: MRI must keep working (and stay importable)
when ScrapeGraphAI is not installed.
"""
from __future__ import annotations

import os

FIELDS = (
    "marketplace", "product_id", "title", "brand", "seller", "product_url",
    "category", "subcategory", "category_path", "evidence_source",
    "extraction_status",
)

OK = "OK"
DISABLED = "DISABLED"
UNAVAILABLE = "UNAVAILABLE"
INVALID_RESPONSE = "INVALID_RESPONSE"
ERROR = "ERROR"

_STR_FIELDS = tuple(f for f in FIELDS if f != "extraction_status")

#: Fields whose provenance is owned by the adapter (never taken from the model).
_ADAPTER_OWNED = ("marketplace", "product_url", "evidence_source")
_MODEL_FIELDS = tuple(f for f in _STR_FIELDS if f not in _ADAPTER_OWNED)


def enabled() -> bool:
    return str(os.getenv("SCRAPEGRAPHAI_ENABLED", "false")).strip().lower() in (
        "1", "true", "yes", "on")


def _null_payload() -> dict:
    payload = {f: None for f in FIELDS}
    payload["evidence_source"] = None
    payload["extraction_status"] = DISABLED
    return payload


class ScrapeGraphExtractor:
    """Auxiliary extractor. `backend` is injectable for tests/offline use."""

    def __init__(self, backend=None, enabled_override=None):
        self._backend = backend
        self._enabled = enabled() if enabled_override is None else bool(enabled_override)
        self._availability_error = None
        if self._backend is None and self._enabled:
            self._backend = self._load_default_backend()

    # ── availability ───────────────────────────────────────────────────────
    def _load_default_backend(self):
        try:
            from scrapegraphai.graphs import SmartScraperGraph  # noqa: F401
            return SmartScraperGraph
        except Exception as exc:                      # library or deps missing
            self._availability_error = f"{type(exc).__name__}: {exc}"
            return None

    @property
    def available(self) -> bool:
        return bool(self._enabled and self._backend is not None)

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "available": self.available,
            "library": "scrapegraphai",
            "version_target": "2.3.1",
            "error": self._availability_error,
            "writes_official_results": False,
        }

    # ── extraction ─────────────────────────────────────────────────────────
    def extract(self, content: str | None, source_url: str | None,
                marketplace: str | None) -> dict:
        """Return a validated payload; callers compare, never auto-apply."""
        payload = _null_payload()
        payload["marketplace"] = marketplace or None
        payload["product_url"] = source_url or None
        payload["evidence_source"] = source_url or None

        if not self._enabled:
            payload["extraction_status"] = DISABLED
            return payload
        if not self.available:
            payload["extraction_status"] = UNAVAILABLE
            payload["error"] = self._availability_error or "backend unavailable"
            return payload
        if not content:
            payload["extraction_status"] = ERROR
            payload["error"] = "no acquired content supplied"
            return payload

        try:
            raw = self._backend(content=content, source_url=source_url,
                                marketplace=marketplace)
        except Exception as exc:                      # never abort MRI
            payload["extraction_status"] = ERROR
            payload["error"] = f"{type(exc).__name__}: {exc}"
            return payload

        return self._validate(raw, source_url=source_url, marketplace=marketplace)

    def _validate(self, raw, source_url=None, marketplace=None) -> dict:
        payload = _null_payload()
        payload["marketplace"] = marketplace or None
        payload["product_url"] = source_url or None
        payload["evidence_source"] = source_url or None
        if not isinstance(raw, dict):
            payload["extraction_status"] = INVALID_RESPONSE
            payload["error"] = "backend did not return a mapping"
            return payload

        invalid = False
        for field in _MODEL_FIELDS:
            value = raw.get(field)
            if value is None or value == "":
                payload[field] = None              # unknown stays unknown
            elif isinstance(value, (str, int, float)):
                payload[field] = str(value).strip() or None
            else:
                payload[field] = None
                invalid = True
        # Values the adapter owns: never accept them from the model.
        payload["marketplace"] = payload["marketplace"]
        payload["product_url"] = payload["product_url"]
        payload["evidence_source"] = payload["evidence_source"]
        payload["extraction_status"] = INVALID_RESPONSE if invalid else OK
        if invalid:
            payload["error"] = "backend returned non-scalar field(s); set to null"
        return payload

    # ── evidence comparison (pilot) ────────────────────────────────────────
    @staticmethod
    def compare(ai_payload: dict | None, current: dict | None) -> dict:
        """Compare AI proposal vs current MRI extraction. No mutation."""
        ai_payload = ai_payload or {}
        current = current or {}
        additional, contradictions, equal = [], [], []
        for field in _STR_FIELDS:
            ai_val = ai_payload.get(field)
            cur_val = current.get(field)
            if ai_val is None:
                continue
            if cur_val in (None, ""):
                additional.append(field)
            elif str(ai_val).strip().lower() == str(cur_val).strip().lower():
                equal.append(field)
            else:
                contradictions.append({
                    "field": field, "current": cur_val, "ai_proposed": ai_val})
        return {
            "additional_fields": additional,
            "contradictions": contradictions,
            "equal_fields": equal,
            "ai_fields_present": sum(1 for f in _STR_FIELDS
                                     if ai_payload.get(f) is not None),
            "auto_applied": False,
        }
