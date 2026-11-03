"""Read-only pre-launch verification for one MRI marketplace.

Usage:
    python scripts/verify_marketplace_launch.py --marketplace "Mercado Libre"

Never starts an audit, never writes data. Exits 0 only if the pre-launch gate
passes; otherwise exits 1 and prints the reasons.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_HOSTS = {
    "Mercado Libre": ("mercadolibre.cl", "mercadolibre.com"),
    "Paris": ("paris.cl",),
    "Falabella": ("falabella.com", "falabella.cl"),
    "Ripley": ("ripley.cl",),
}


def _env() -> dict:
    values = {}
    for candidate in (ROOT / ".env", ROOT / "_integration" / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def _get(path: str, credentials: str) -> dict:
    req = urllib.request.Request("http://127.0.0.1:8055" + path)
    req.add_header("Authorization", "Basic " + credentials)
    with urllib.request.urlopen(req, timeout=8) as response:
        return json.loads(response.read().decode())


def _hosts(value) -> set[str]:
    found = set()
    if isinstance(value, str):
        try:
            host = urlparse(value).hostname or ""
            if host:
                found.add(host.lower())
        except Exception:
            pass
    elif isinstance(value, dict):
        for item in value.values():
            found |= _hosts(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            found |= _hosts(item)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marketplace", required=True,
                        choices=sorted(EXPECTED_HOSTS))
    args = parser.parse_args()
    env = _env()
    if not env.get("DASHBOARD_USER") or not env.get("DASHBOARD_PASS"):
        print("FAIL credentials missing in .env")
        return 1
    token = base64.b64encode(
        (env["DASHBOARD_USER"] + ":" + env["DASHBOARD_PASS"]).encode()).decode()
    failures, warnings = [], []
    try:
        version = _get("/api/version", token)
        state = _get("/api/state", token).get("state") or {}
    except Exception as exc:
        print(f"FAIL server/API unavailable: {type(exc).__name__}: {exc}")
        return 1

    print("build:", version.get("build_id"), "| branch:", version.get("branch"))
    if not version.get("build_id"):
        failures.append("build_id missing")
    if state.get("is_running"):
        failures.append(f"audit already running: {state.get('run_id')}")
    if state.get("marketplace") not in (None, args.marketplace):
        warnings.append(f"state belongs to {state.get('marketplace')}, not {args.marketplace}")
    runtime = state.get("runtime_context") or {}
    if runtime and runtime.get("full_audit") is not True:
        failures.append("full_audit is not true")
    if runtime and runtime.get("marketplace") != args.marketplace:
        warnings.append("runtime_context.marketplace differs from requested")

    expected = EXPECTED_HOSTS[args.marketplace]
    # Only inspect host scope when the live state belongs to the requested
    # marketplace. A previous completed run must not block a new launch.
    same_context = state.get("marketplace") == args.marketplace
    if same_context:
        urls = [state.get(k) for k in ("acquisitions", "taxonomy", "errors")]
        bad = []
        for host in _hosts(urls):
            if not any(host == d or host.endswith("." + d) for d in expected):
                bad.append(host)
        if bad:
            failures.append(f"foreign hosts present in state: {sorted(bad)}")
    else:
        warnings.append("state belongs to a previous marketplace; host scan skipped")

    print("marketplace:", args.marketplace)
    print("expected hosts:", ", ".join(expected))
    print("state is_running:", state.get("is_running"))
    print("taxonomy:", list((state.get("taxonomy") or {}).keys()))
    for warning in warnings:
        print("WARN:", warning)
    for failure in failures:
        print("FAIL:", failure)
    if failures:
        return 1
    print("PASS pre-launch gate (no audit was started)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
