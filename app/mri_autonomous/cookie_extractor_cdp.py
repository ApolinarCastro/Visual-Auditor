"""Chrome DevTools Protocol cookie extractor (MRI-026).

Reads live cookies from an already-open Chrome with --remote-debugging-port.
No admin rights, no cookie-file access, no browser launch.
"""
from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import Any, Dict, List

CDP_BASE = "http://127.0.0.1:9222"


def _http_json(path: str):
    with urllib.request.urlopen(CDP_BASE + path, timeout=4) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def _targets():
    return _http_json("/json") or []


def _ws_url() -> str:
    targets = _targets()
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    for t in pages:
        if "mercadolibre" in str(t.get("url", "")).lower():
            return t["webSocketDebuggerUrl"]
    if pages:
        return pages[0]["webSocketDebuggerUrl"]
    version = _http_json("/json/version")
    return version.get("webSocketDebuggerUrl", "")


async def _cdp_async(domain: str = ".mercadolibre.cl") -> Dict[str, Any]:
    ws_url = _ws_url()
    if not ws_url:
        return {"status": "NO_CHROME_DEBUG", "cookies": [], "source": "cdp"}
    try:
        import websockets
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
            data = {}
            for _ in range(20):
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(raw)
                if data.get("id") == 1:
                    break
        cookies = data.get("result", {}).get("cookies", [])
        matched = [c for c in cookies if domain.lower().lstrip(".") in
                   str(c.get("domain", "")).lower()]
        return {"status": "OK", "cookies": matched, "source": "cdp",
                "count": len(matched)}
    except Exception as exc:
        return {"status": "ERROR", "cookies": [], "source": "cdp",
                "error": f"{type(exc).__name__}: {exc}"}


def get_cookies_via_cdp(domain: str = ".mercadolibre.cl") -> Dict[str, Any]:
    try:
        return asyncio.run(_cdp_async(domain))
    except RuntimeError:
        # Already inside an event loop (dashboard async endpoint): use a thread.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(_cdp_async(domain))).result()
    except Exception as exc:
        return {"status": "ERROR", "cookies": [], "source": "cdp",
                "error": f"{type(exc).__name__}: {exc}"}
