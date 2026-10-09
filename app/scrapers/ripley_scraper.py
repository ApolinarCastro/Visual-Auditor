"""
RipleyScraper — Session Harvesting + Cookie Replay Strategy

Ripley uses Cloudflare Turnstile + WAF that blocks:
1. Headless Playwright (detected via JS fingerprint)
2. Raw httpx/requests (blocked at WAF level, 403 for all IPs)

The only legal, reliable approach:
- Phase 1 (harvest): Use non-headless Playwright to build a real browser session
  and save the cookies + local storage to disk.
- Phase 2 (replay): Inject those cookies into subsequent requests, extending
  session lifetime so the scraper can operate for hours.

This is completely legal — we're just automating a normal browser session.
"""

import asyncio
import json
import logging
import re
import random
import time
from pathlib import Path
try:
    from anansi.parser.adaptive import AdaptiveParser, SelectorConfig
except ImportError:
    AdaptiveParser = None
    SelectorConfig = None

from app.scrapers.base_scraper import BaseScraper
from app.intelligence.trend_engine import record_custom_alert

from app.mri_autonomous.pagination import detect_sort_mode, pagination_url, parse_pager_text

logger = logging.getLogger(__name__)

SESSION_FILE = Path(__file__).parent.parent.parent / "data" / "ripley_session.json"

CATEGORY_PATH_MAP = {
    "abrigo": "moda-mujer/tops-y-chaquetas/abrigos",
    "abrigos": "moda-mujer/tops-y-chaquetas/abrigos",
    "jean": "moda-mujer/jeans-y-pantalones/jeans",
    "jeans": "moda-mujer/jeans-y-pantalones/jeans",
    "pantalon": "moda-mujer/jeans-y-pantalones/pantalones",
    "pantalones": "moda-mujer/jeans-y-pantalones/pantalones",
    "short": "moda-mujer/jeans-y-pantalones/shorts",
    "shorts": "moda-mujer/jeans-y-pantalones/shorts",
    "chaqueta": "moda-mujer/tops-y-chaquetas/chaquetas-y-blazers",
    "chaquetas": "moda-mujer/tops-y-chaquetas/chaquetas-y-blazers",
    "blazer": "moda-mujer/tops-y-chaquetas/chaquetas-y-blazers",
    "polera": "moda-mujer/tops-y-chaquetas/blusas-y-poleras",
    "poleras": "moda-mujer/tops-y-chaquetas/blusas-y-poleras",
    "blusa": "moda-mujer/tops-y-chaquetas/blusas-y-poleras",
    "blusas": "moda-mujer/tops-y-chaquetas/blusas-y-poleras",
    "blusas y poleras": "moda-mujer/tops-y-chaquetas/blusas-y-poleras",
    "poleras y blusas": "moda-mujer/tops-y-chaquetas/blusas-y-poleras",
    "sweater": "moda-mujer/tops-y-chaquetas/sweaters-y-chalecos",
    "sweaters": "moda-mujer/tops-y-chaquetas/sweaters-y-chalecos",
    "chaleco": "moda-mujer/tops-y-chaquetas/sweaters-y-chalecos",
    "chalecos": "moda-mujer/tops-y-chaquetas/sweaters-y-chalecos",
    "enterito": "moda-mujer/vestidos-y-enteritos/enteritos",
    "enteritos": "moda-mujer/vestidos-y-enteritos/enteritos",
    "falda": "moda-mujer/vestidos-y-enteritos/faldas",
    "faldas": "moda-mujer/vestidos-y-enteritos/faldas",
    "vestido": "moda-mujer/vestidos-y-enteritos/vestidos",
    "vestidos": "moda-mujer/vestidos-y-enteritos/vestidos",
    "kimono": "moda-mujer/tops-y-chaquetas/kimonos",
    "kimonos": "moda-mujer/tops-y-chaquetas/kimonos",
    "parka": "moda-mujer/tops-y-chaquetas/parkas",
    "parkas": "moda-mujer/tops-y-chaquetas/parkas",
}


class RipleyScraper(BaseScraper):
    """
    Ripley scraper with session harvesting.
    Starts non-headless to pass Cloudflare, saves cookies, then uses them.
    """

    def __init__(self, headless=True):
        # Using chromium to align perfectly with Chromium harvested session cookies
        super().__init__(headless=headless, browser_type="chromium", marketplace="Ripley")
        self._session_cookies: list = []
        SESSION_FILE.parent.mkdir(exist_ok=True)

    async def _mutate_context(self) -> None:
        """Override base_scraper _mutate_context to rotate UA via SelectorRegistry while keeping desktop."""
        await self._check_and_increment_mutation()

        # Clean up old context safely
        try:
            if self.page:
                await self.page.close()
        except Exception:
            pass
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass

        from app.intelligence.selector_registry import record_selector, ranked_selectors
        await record_selector(self.marketplace, "stealth_profile", f"mobile={self.mobile}", success=False)
        if hasattr(self, 'user_agent') and self.user_agent:
            await record_selector(self.marketplace, "stealth_ua", self.user_agent, success=False)

        self.mobile = False

        ua_list = self._get_ua_list()
        best_uas = await ranked_selectors(self.marketplace, "stealth_ua", ua_list)
        if hasattr(self, 'user_agent') and self.user_agent == best_uas[0] and len(best_uas) > 1:
            self.user_agent = best_uas[1]
        else:
            self.user_agent = best_uas[0]

        self.context = await self.browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1366, "height": 768},
            locale="es-CL",
            timezone_id="America/Santiago",
            is_mobile=False,
            has_touch=False
        )

        await self._apply_stealth_scripts()
        self.page = await self.context.new_page()

        if self._session_cookies:
            try:
                sanitized = self._sanitize_cookies(self._session_cookies)
                await self.page.context.add_cookies(sanitized)
                logger.info(f"[Ripley] Re-injected {len(sanitized)} harvested cookies into mutated context (UA: {self.user_agent[:40]}...)")
            except Exception as e:
                logger.warning(f"[Ripley] Failed to re-inject cookies: {e}")

    def _url_to_category_path(self, url: str) -> str:
        """Extract category path from Ripley URL."""
        # Search URL: /search/Nicopoly?facet%3DTipo%20de%20Prenda=Jeans
        if "/search/" in url:
            match = re.search(r"facet[^=]+=([^&]+)", url)
            if match:
                import urllib.parse
                facet_raw = match.group(1)
                facet = urllib.parse.unquote(facet_raw)
                facet = facet.replace("+", " ").lower().strip()
                # Match any keyword in the facet
                for key, path in CATEGORY_PATH_MAP.items():
                    if key in facet:
                        return path
                return facet

        # Category URL: .../moda-mujer/jeans-y-pantalones/jeans
        for path in CATEGORY_PATH_MAP.values():
            if path in url:
                return path

        # Fallback: last 3 segments
        parts = url.rstrip("/").split("/")
        return "/".join(parts[-3:]) if len(parts) >= 3 else parts[-1]

    async def _harvest_session(self) -> bool:
        """
        Navigate to Ripley homepage to pass Cloudflare challenge and harvest cookies.
        Using a completely mutated browser context to clean and refresh session fingerprints.
        """
        logger.info("[Ripley] Mutating context and harvesting fresh session cookies from homepage...")
        try:
            # Recreate browser context to clear any bad history or CDN flag
            await self._mutate_context()

            await self.page.goto("https://simple.ripley.cl/", wait_until="commit", timeout=60000)
            await self.page.wait_for_timeout(random.randint(4000, 7000))

            # Simulate soft human mouse moves and scrolls on the homepage to warm session
            await self.page.mouse.move(random.randint(100, 500), random.randint(100, 400))
            await self.page.mouse.wheel(0, random.randint(100, 400))
            await self.page.wait_for_timeout(3000)

            # Check if we're through
            title = await self.page.title()
            body_snippet = await self.page.evaluate("document.body?.innerText?.slice(0, 300) || ''")
            is_blocked = (
                "Just a moment" in title
                or "espera un momento" in body_snippet.lower()
                or "comprobando tu navegador" in body_snippet.lower()
                or "Access denied" in title
                or "blocked" in title.lower()
                or "error en ripley" in title.lower()
            )

            if not is_blocked:
                # Save cookies
                self._session_cookies = await self.page.context.cookies()
                logger.info(f"[Ripley] Session harvested — {len(self._session_cookies)} cookies saved")
                SESSION_FILE.write_text(json.dumps(self._session_cookies, ensure_ascii=False))
                return True
            else:
                logger.error("[Ripley] Failed to pass Cloudflare challenge on homepage")
                return False
        except Exception as e:
            logger.error(f"[Ripley] Session harvest error: {e}")
            return False

    async def _load_or_harvest_session(self) -> bool:
        """Load saved session or harvest a new one."""
        # Check if already loaded in memory (e.g. injected during testing)
        if self._session_cookies:
            try:
                sanitized = self._sanitize_cookies(self._session_cookies)
                await asyncio.wait_for(
                    self.page.context.add_cookies(sanitized),
                    timeout=15.0,
                )
                logger.info(f"[Ripley] Loaded {len(sanitized)} cookies from memory")
                return True
            except Exception as e:
                logger.warning(f"[Ripley] Failed to load cookies from memory (continuing without): {e}")

        # Try loading saved session first
        if SESSION_FILE.exists():
            try:
                cookies = json.loads(SESSION_FILE.read_text())
                if cookies:
                    sanitized = self._sanitize_cookies(cookies)
                    try:
                        await asyncio.wait_for(
                            self.page.context.add_cookies(sanitized),
                            timeout=15.0,
                        )
                    except Exception as ck_err:
                        logger.warning(f"[Ripley] add_cookies timed out (Obscura?), continuing without: {ck_err}")
                    self._session_cookies = sanitized
                    logger.info(f"[Ripley] Loaded {len(sanitized)} saved session cookies")
                    return True
            except Exception as e:
                logger.warning(f"[Ripley] Failed to load saved session: {e}")

        if not self.headless:
            return await self._harvest_session()
        else:
            logger.info("[Ripley] No session cookies found. Attempting headless background harvest with learned profile...")
            success = await self._harvest_session()
            if not success:
                msg = "[Ripley] Automated headless harvest failed. WAF is too strict."
                logger.error(msg)
                try:
                    await record_custom_alert(
                        marketplace="Ripley",
                        category="System",
                        alert_type="Session Expired",
                        message=msg
                    )
                except Exception as alert_err:
                    logger.warning(f"[Ripley] Failed to record custom alert: {alert_err}")
            return success

    async def _navigate_ripley(self, url: str) -> bool:
        """Navigate to a Ripley URL with stealth mode active and self-healing retries."""
        self._mutation_count = 0
        self._last_navigation_successful = False
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                logger.info(f"[Ripley] Navigating to {url} (attempt {attempt+1}/{max_attempts})")
                await self.page.goto(url, wait_until="commit", timeout=60000)
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=15000)
                except:
                    pass
                await self.page.wait_for_timeout(random.randint(3000, 5000))

                title = await self.page.title()
                body_snippet = await self.page.evaluate("document.body?.innerText?.slice(0, 300) || ''")

                # Detect Cloudflare Turnstile challenge (Spanish or English)
                is_blocked = (
                    "Just a moment" in title
                    or "espera un momento" in body_snippet.lower()
                    or "comprobando tu navegador" in body_snippet.lower()
                    or "Access denied" in title
                    or "cf-browser-verification" in body_snippet
                    or "blocked" in title.lower()
                    or "error en ripley" in title.lower()
                )

                if not is_blocked:
                    # Simulate soft human mouse moves and scrolls on successful load
                    await self.page.mouse.move(random.randint(100, 500), random.randint(100, 400))
                    await self.page.mouse.wheel(0, random.randint(100, 300))
                    logger.info(f"[Ripley] Page loaded OK: '{title[:70]}'")
                    self._last_navigation_successful = True
                    return True

                logger.warning(f"[Ripley] Cloudflare Turnstile or Block page detected (attempt {attempt+1}/{max_attempts}): '{title}' - '{body_snippet[:150]}'")

                if attempt < max_attempts - 1:
                    if not self.headless:
                        if await self._harvest_session():
                            continue
                    else:
                        logger.warning(f"[Ripley] Blocked in headless mode. Mutating context and retrying...")
                        await self._mutate_context()
                        await asyncio.sleep(random.randint(8, 15))
                else:
                    msg = "[Ripley] Blocked or Turnstile challenged in headless mode. Session cookies may be expired. Run 'scratch/harvest_ripley_session.py'."
                    logger.error(msg)
                    try:
                        await record_custom_alert(
                            marketplace="Ripley",
                            category="System",
                            alert_type="Session Blocked",
                            message=msg
                        )
                    except Exception as alert_err:
                        logger.warning(f"[Ripley] Failed to record custom alert: {alert_err}")
                    return False
            except Exception as e:
                logger.error(f"[Ripley] Navigation to {url} failed on attempt {attempt+1}: {e}")
                if attempt < max_attempts - 1:
                    await self._mutate_context()
                    await asyncio.sleep(random.randint(8, 15))
                else:
                    msg = f"[Ripley] Navigation to {url} failed on all attempts in headless mode: {e}. Session cookies may be expired. Run 'scratch/harvest_ripley_session.py'."
                    logger.error(msg)
                    try:
                        await record_custom_alert(
                            marketplace="Ripley",
                            category="System",
                            alert_type="Navigation Error",
                            message=msg
                        )
                    except Exception as alert_err:
                        logger.warning(f"[Ripley] Failed to record custom alert: {alert_err}")
                    return False
        return False

    async def _dismiss_popups(self):
        """Dismiss Ripley notification/cookie popups that block page interaction."""
        try:
            # OneSignal notification popup - "No gracias" button
            for btn_text in ["No gracias", "no gracias", "Cerrar", "cerrar"]:
                btn = await self.page.query_selector(f"button:has-text('{btn_text}')")
                if btn:
                    await btn.click()
                    logger.info(f"[Ripley] Dismissed popup via '{btn_text}'")
                    await self.page.wait_for_timeout(1000)
                    return
            # Try clicking outside the popup overlay
            overlay = await self.page.query_selector(".onesignal-customlink-container, [class*='notification'], [class*='modal-overlay']")
            if overlay:
                await self.page.keyboard.press("Escape")
                logger.info("[Ripley] Dismissed popup via Escape key")
                await self.page.wait_for_timeout(1000)
        except Exception as e:
            logger.debug(f"[Ripley] Popup dismiss attempt: {e}")



    supports_pagination = True
    supports_navigation = True
    NAV_BUTTON_JS_PRIORITY = ("Array.from(document.querySelectorAll('button, [role=button], a'))"
                              ".filter(el => /categor/i.test((el.getAttribute('aria-label')||'') + ' ' + (el.innerText||'')))")
    NAV_BUTTON_JS_FALLBACK = ("Array.from(document.querySelectorAll('button, [role=button], a'))"
                              ".filter(el => /abr.*men|men[uú]/i.test((el.getAttribute('aria-label')||'') + ' ' + (el.innerText||'')))")

    async def _click_visible_js(self, expr: str) -> dict:
        """Click the first VISIBLE element matched by a JS expression."""
        return await self.page.evaluate(f"""() => {{
            const cands = {expr};
            for (const el of cands) {{
                if (el && el.offsetParent !== null) {{
                    el.click();
                    return {{clicked: true, label: (el.getAttribute('aria-label') || el.innerText || '').trim().slice(0, 80)}};
                }}
            }}
            return {{clicked: false, label: null}};
        }}""")

    async def discover_navigation_source(self, url: str, timeout_s: float = 25.0) -> dict:
        """Capture the navigation data SOURCE (network JSON tree served on load).
        Listener attached BEFORE navigation; read-only; returns parsed JSON."""
        import hashlib as _h
        result = {"found": False, "url": None, "sha16": None, "json": None}
        try:
            loop = asyncio.get_event_loop()
            fut = loop.create_future()

            async def _on_resp(resp):
                try:
                    u = resp.url.lower()
                    if "menucomponent" in u and "menu" in u and "json" in (resp.headers or {}).get("content-type", ""):
                        body = await resp.text()
                        if not fut.done():
                            fut.set_result({"url": resp.url, "body": body})
                except Exception:
                    pass

            self.page.on("response", _on_resp)
            try:
                await self._navigate_ripley(url)
                try:
                    hit = await asyncio.wait_for(fut, timeout=timeout_s)
                except asyncio.TimeoutError:
                    hit = None
                if hit is None:
                    try:
                        await self._click_visible_js(self.NAV_BUTTON_JS_PRIORITY)
                        await self.page.wait_for_timeout(3000)
                    except Exception:
                        pass
                    if fut.done():
                        hit = fut.result()
                if hit and hit.get("body"):
                    result["found"] = True
                    result["url"] = hit["url"]
                    result["sha16"] = _h.sha256(hit["body"].encode("utf-8", errors="replace")).hexdigest()[:16]
                    try:
                        result["json"] = json.loads(hit["body"])
                    except Exception:
                        result["json"] = None
            finally:
                try:
                    self.page.remove_listener("response", _on_resp)
                except Exception:
                    pass
        except Exception as e:
            result["error"] = str(e)[:150]
        return result

    async def discover_navigation(self, raw_only: bool = False) -> dict:
        # Network-visible navigation state (MRI-AUTONOMY-002 lesson): JS menus load
        # their tree from an API; anchors alone are insufficient. We listen to JSON
        # responses BEFORE opening the control, then merge API pairs with anchors.
        opened = False
        click_label = None
        nodes = []
        evidence_locator = "raw_dom_anchors"
        _menu_json_pair_list = []
        _captured_responses = []

        async def _on_response(resp):
            try:
                ctype = (resp.headers or {}).get("content-type", "")
                if "json" not in ctype:
                    return
                u = resp.url.lower()
                if any(bad in u for bad in ("analytics", "tracking", "ads", "pixel", "gtm", "collect")):
                    return
                data = await resp.json()
                from app.mri_autonomous.category_discoverer import extract_nav_pairs_from_json as _ex
                pairs = _ex(data)
                _captured_responses.append({"url": resp.url[:120], "pairs": len(pairs)})
                if pairs:
                    _menu_json_pair_list.extend(pairs)
            except Exception:
                pass

        async def _harvest_best_container():
            return await self.page.evaluate("""() => {
                const sels = ["[role='dialog']", "aside", "[class*='drawer']", "[class*='Drawer']",
                              "[class*='menu']", "[class*='Menu']", "[class*='submenu']",
                              "[class*='modal']", "[id*='menu']", "[id*='Menu']",
                              "[class*='overlay']", "[class*='nav']"];
                let best = null, bestCount = 0, bestSel = null;
                for (const s of sels) {
                    document.querySelectorAll(s).forEach(el => {
                        if (el.offsetParent === null && el.getClientRects().length === 0) return;
                        const c = el.querySelectorAll('a[href]').length;
                        if (c > bestCount) { bestCount = c; best = el; bestSel = s; }
                    });
                }
                const out = [];
                (best || document.body).querySelectorAll('a[href]').forEach(a => out.push({
                    href: a.getAttribute('href') || '',
                    label: (a.innerText || '').trim().slice(0, 60)}));
                return {anchors: out, best_count: bestCount, best_sel: bestSel,
                        used_body: !best, container_tag: best ? (best.tagName || '').toLowerCase() : 'body'};
            }""")

        try:
            if not raw_only:
                self.page.on("response", _on_response)
                res = await self._click_visible_js(self.NAV_BUTTON_JS_PRIORITY)
                if not res.get("clicked"):
                    res = await self._click_visible_js(self.NAV_BUTTON_JS_FALLBACK)
                opened = bool(res.get("clicked"))
                click_label = res.get("label")
                if opened:
                    await self.page.wait_for_timeout(3200)
                    evidence_locator = "menu_dialog_anchors"
            harvest = await _harvest_best_container()
            if opened and harvest.get("best_count", 0) < 12 and not _menu_json_pair_list:
                # one bounded retry with the fallback predicate; kept only if better
                try:
                    await self.page.keyboard.press("Escape")
                    await self.page.wait_for_timeout(600)
                except Exception:
                    pass
                res2 = await self._click_visible_js(self.NAV_BUTTON_JS_FALLBACK)
                if res2.get("clicked"):
                    await self.page.wait_for_timeout(2500)
                    h2 = await _harvest_best_container()
                    if h2.get("best_count", 0) > harvest.get("best_count", 0):
                        harvest = h2
                        click_label = res2.get("label")
                        evidence_locator = evidence_locator + "+fallback_second_click"
            data = harvest.get("anchors", [])
            container = "menu_dialog" if (opened or _menu_json_pair_list) else "dom"
            nodes = [{"href": d["href"], "label": d["label"], "container": container} for d in data]
            _seen_urls = {n["href"] for n in nodes}
            for _lbl, _href in (_menu_json_pair_list or []):
                if _href not in _seen_urls:
                    nodes.append({"href": _href, "label": _lbl, "container": "menu_dialog"})
                    _seen_urls.add(_href)
            if _menu_json_pair_list:
                evidence_locator = (evidence_locator
                                    + f":menu_json_pairs={len(_menu_json_pair_list)}"
                                    + f":responses={len(_captured_responses)}")
            if opened:
                try:
                    await self.page.keyboard.press("Escape")
                    await self.page.wait_for_timeout(500)
                except Exception:
                    pass
        except Exception as e:
            try:
                self.page.remove_listener("response", _on_response)
            except Exception:
                pass
            return {"opened": opened, "click_label": click_label, "nodes": [],
                    "anchors_total": 0, "evidence_locator": f"error:{e}"}
        try:
            self.page.remove_listener("response", _on_response)
        except Exception:
            pass
        return {"opened": opened, "click_label": click_label, "nodes": nodes,
                "anchors_total": len(nodes), "evidence_locator": evidence_locator}

    async def discover_facets(self) -> dict:
        """Open the filter panel (visible) and enumerate visible option labels."""
        out = {"panel_opened": False, "sections": [], "checkbox_count": 0,
               "evidence_locator": "filter_panel"}
        try:
            res = await self._click_visible_js(
                "Array.from(document.querySelectorAll('button, [role=button]'))"
                ".filter(el => /filtr/i.test((el.getAttribute('aria-label')||'') + ' ' + (el.innerText||'')))")
            if not res.get("clicked"):
                return out
            await self.page.wait_for_timeout(1800)
            out["panel_opened"] = True
            data = await self.page.evaluate("""() => {
                const res = {checkboxes: 0, labels: [], scoped: false};
                const roots = ['[role=dialog]', 'aside', '[class*=filter]', '[class*=Filter]', '[class*=facet]', '[class*=Facet]'];
                let root = null;
                for (const sel of roots) {
                    const el = document.querySelector(sel);
                    if (el && el.offsetParent !== null) { root = el; break; }
                }
                res.scoped = !!root;
                const scope = root || document;
                res.checkboxes = scope.querySelectorAll('input[type=checkbox]').length;
                const seen = new Set();
                scope.querySelectorAll('label, li, button, span, a, h1, h2, h3, h4, div').forEach(n => {
                    if (n.offsetParent === null) return;
                    const t = (n.innerText || '').trim();
                    if (t && t.length <= 50 && !seen.has(t)) { seen.add(t); res.labels.push(t); }
                });
                res.labels = res.labels.slice(0, 250);
                return res;
            }""")
            out["checkbox_count"] = data.get("checkboxes", 0)
            out["scoped"] = bool(data.get("scoped"))
            out["unscoped"] = not bool(data.get("scoped"))
            out["sections"] = [{"header": "visible_options", "options": data.get("labels", [])}]
            out["evidence_locator"] = f"filter_panel:labels={len(data.get('labels', []))},checkboxes={data.get('checkboxes', 0)}"
            try:
                await self.page.keyboard.press("Escape")
                await self.page.wait_for_timeout(400)
            except Exception:
                pass
        except Exception as e:
            out["evidence_locator"] = f"error:{e}"
        return out

    async def page_signature(self) -> dict:
        try:
            js = r"""() => {
                const m = (document.body.innerText || '').match(/([\\d\\.]{1,12})\\s+Resultados/i);
                const titles = [];
                document.querySelectorAll('.product-item--wrapper a').forEach(a => { const t=(a.innerText||'').trim().split('\\n')[0]; if (t && titles.length<3) titles.push(t.slice(0, 40)); });
                return {url: location.href, count: m ? parseInt(m[1].replace(/\\./g, ''), 10) : null, titles: titles};
            }"""
            return await self.page.evaluate(js)
        except Exception as e:
            return {"url": "", "count": None, "titles": [], "error": str(e)[:120]}

    async def apply_brand_facet(self, brand: str) -> dict:
        """Apply the brand facet via the visible filter panel; capture signals."""
        bl = (brand or "").strip().lower()
        before = await self.page_signature()
        result = {"applied": False, "before": before, "after": None, "steps": []}
        try:
            await self._click_visible_js(
                "Array.from(document.querySelectorAll('button, [role=button]'))"
                ".filter(el => /filtr/i.test((el.getAttribute('aria-label')||'') + ' ' + (el.innerText||'')))")
            await self.page.wait_for_timeout(1500)
            typed = await self.page.evaluate(f"""() => {{
                const inputs = Array.from(document.querySelectorAll('input[type=text], input[type=search], input:not([type])'));
                const box = inputs.find(i => i.offsetParent !== null);
                if (!box) return {{typed: false}};
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(box, "{bl}");
                box.dispatchEvent(new Event('input', {{bubbles: true}}));
                return {{typed: true, placeholder: (box.getAttribute('placeholder') || '').slice(0, 40)}};
            }}""")
            result["steps"].append({"type_brand": typed})
            await self.page.wait_for_timeout(1500)
            clicked = await self.page.evaluate(f"""() => {{
                const b = "{bl}";
                if (!b) return {{clicked: false}};
                const nodes = Array.from(document.querySelectorAll('label, li, span, a, div'));
                const cand = nodes.find(n => n.offsetParent !== null
                    && (n.innerText || '').trim().toLowerCase().includes(b)
                    && (n.innerText || '').trim().length < 60);
                if (!cand) return {{clicked: false}};
                const t = (cand.innerText || '').trim();
                let box = cand.querySelector('input[type=checkbox]');
                if (!box && cand.closest('label')) box = cand.closest('label').querySelector('input[type=checkbox]');
                if (box) {{ box.click(); }} else {{ cand.click(); }}
                return {{clicked: true, label: t.slice(0, 50)}};
            }}""")
            result["steps"].append({"click_option": clicked})
            await self.page.wait_for_timeout(900)
            applied_btn = await self._click_visible_js(
                "Array.from(document.querySelectorAll('button, [role=button]'))"
                ".filter(el => /^filtrar$/i.test((el.innerText||'').trim()) && !el.disabled)")
            result["steps"].append({"apply": applied_btn})
            await self.page.wait_for_timeout(3500)
            result["after"] = await self.page_signature()
            result["applied"] = bool(applied_btn.get("clicked"))
        except Exception as e:
            result["steps"].append({"error": str(e)})
        return result


    async def get_total_count(self, url: str) -> int:
        """Get product count for the given category URL.

        Strategy (in priority order):
        1. CSS selectors targeting known count elements
        2. Regex over body text for "X Resultados en..." pattern
        3. DataLayer JS objects
        4. Physical product item count on page
        """
        # Ensure session is ready
        await self._load_or_harvest_session()

        category_path = self._url_to_category_path(url)
        category_url = f"https://simple.ripley.cl/{category_path}"
        search_url = url  # The search-filtered URL

        logger.info(f"[Ripley] Counting products for: {category_path}")

        max_insist = 1
        for attempt in range(max_insist):
            # Navigate to the exact requested URL
            ok = await self._navigate_ripley(search_url)
            if not ok:
                logger.error(f"[Ripley] Blocked or failed to load URL {url} — attempt {attempt+1}/{max_insist}")
                if attempt < max_insist - 1:
                    logger.info("[Ripley] Insisting on count due to failure... mutating context.")
                    await self._mutate_context()
                    await asyncio.sleep(random.uniform(5, 10))
                    continue
                else:
                    return 0

            # Dismiss notification popups that block content
            await self._dismiss_popups()

            # Wait for dynamic content
            try:
                await self.page.wait_for_selector(".catalog-product-item, .product-item--wrapper", state="attached", timeout=5000)
            except Exception:
                await asyncio.sleep(1.5)
            await self.page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(0.8)  # Short random wait to mimic human reading

            # Take debug screenshot to see what Ripley renders (best-effort:
            # Obscura CDP engine does NOT support Page.captureScreenshot)
            try:
                from pathlib import Path
                Path("debug_screenshots").mkdir(exist_ok=True)
                safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', category_path)[:50]
                await asyncio.wait_for(
                    self.page.screenshot(path=f"debug_screenshots/ripley_{safe_name}.png"),
                    timeout=3.0,
                )
                logger.info(f"[Ripley] Debug screenshot saved: debug_screenshots/ripley_{safe_name}.png")
            except Exception as e:
                logger.debug(f"[Ripley] Debug screenshot skipped (engine: {type(e).__name__}): {e}")

            # ── Strategy 0: Strict Empty State Detection ──
            body_text = await self.page.evaluate("document.body?.innerText || ''")
            body_text_lower = body_text.lower()
            strict_empty_indicators = [
                "no existen productos que cumplan con tus criterios de filtrado",
                "intenta ajustar los filtros aplicados",
                "no encontramos resultados",
            ]
            # FIX RIP-2: "0 resultados" NO debe ser substring (10/20/100 resultados
            # lo contienen). Usar regex con lookbehind negativo.
            if any(ind in body_text_lower for ind in strict_empty_indicators) or re.search(r'(?<!\d)0\s+resultados', body_text_lower):
                logger.info(f"[Ripley] Zero products confirmed via explicit empty state indicator ('{category_path}')")
                return 0

            # ── Strategy 1: CSS selectors targeting known count elements ──
            selectors = [
                ".catalog-header__results",
                "span.catalog-page__results-count",
                ".catalog-page__results-count",
                ".results-count-number",
                "[data-testid='results-count']",
                ".catalog-results-count",
                ".catalog-page__total-results",
                ".results-count",
                "span.catalog-header__count",
                ".catalog-header__count",
            ]

            for selector in selectors:
                try:
                    el = await self.page.query_selector(selector)
                    if el:
                        text = await el.inner_text()
                        count = self.parse_numeric_text(text)
                        if count > 0 and not self.is_likely_price(text, count):
                            logger.info(f"[Ripley] Count: {count} via selector '{selector}' (text='{text.strip()}')")
                            return count
                        elif count > 0:
                            logger.debug(f"[Ripley] Rejected price-like value {count} from '{selector}' (text='{text.strip()}')")
                except:
                    continue

            # ── Strategy 2: Regex over body text — "X Resultados en ..." ──
            # This is the most reliable method based on test evidence
            try:
                body_text = await self.page.evaluate("document.body?.innerText || ''")
                # Pattern: "1424 Resultados en Jeans mujer" or "5 Resultados en Enteritos Mujer NICOPOLY"
                result_patterns = [
                    r'(\d[\d.]*)\s+[Rr]esultados?\s+en\s+',
                    r'(\d[\d.]*)\s+[Pp]roductos?\s+encontrados?',
                    r'(\d[\d.]*)\s+[Rr]esultados?',
                ]
                for pattern in result_patterns:
                    match = re.search(pattern, body_text)
                    if match:
                        raw = match.group(1).replace(".", "")
                        count = int(raw)
                        if count > 0:
                            logger.info(f"[Ripley] Count: {count} via regex '{pattern}' (matched: '{match.group(0).strip()}')")
                            return count
            except Exception as e:
                logger.debug(f"[Ripley] Body text regex fallback error: {e}")

            # ── Strategy 3: DataLayer JS objects ──
            try:
                dl_count = await self.page.evaluate("""
                    () => {
                        try {
                            if (window.digitalData?.customData?.prop44)
                                return parseInt(window.digitalData.customData.prop44);
                            if (window.dataLayer) {
                                const found = window.dataLayer.find(i => i.numResults !== undefined);
                                if (found) return parseInt(found.numResults);
                            }
                        } catch(e) {}
                        return null;
                    }
                """)
                if dl_count and dl_count > 0:
                    logger.info(f"[Ripley] DataLayer count: {dl_count}")
                    return dl_count
            except:
                pass

            # ── Strategy 4: count physical product items on page ──
            try:
                await self.page.wait_for_timeout(1000)
                items = await self.page.query_selector_all(
                    ".product-item--wrapper, .catalog-product-item, .product-item, div[class*='ProductItem'], "
                    "li[class*='product'], article[class*='product']"
                )
                if items:
                    logger.info(f"[Ripley] Physical fallback count: {len(items)}")
                    return len(items)
            except:
                pass

            logger.warning(f"[Ripley] Could not determine count for {url} (found 0) — attempt {attempt+1}/{max_insist}")
            if attempt < max_insist - 1:
                logger.info("[Ripley] Insisting on count (0 found)... mutating context.")
                await self._mutate_context()
                await asyncio.sleep(random.uniform(5, 10))
                continue

        logger.warning(f"[Ripley] Could not determine count for {url} after {max_insist} attempts.")
        return 0

    async def scrape_autonomous_category(self, url: str, pagination: dict | None = None, brand: str = "", max_pages: int = 40) -> dict:
        """Autonomous extraction without 240 limit (pagination-capable).

        Capability transferred per MRI-AUTONOMY-001: observed pager text and/or a
        discovered pagination plan drive real page-to-page traversal with state
        validation. EXHAUSTION is returned only when the last page was
        explicitly observed (or a single page declared). Every other outcome is
        an honest partial stop (PAGE_BUDGET_EXCEEDED / PAGE_TIME_BUDGET /
        NO_PROGRESS / FAILED_TRANSITION / UNKNOWN_TOTAL_PAGES /
        PAGINATION_PARAM_NOT_FOUND).
        """
        _brand_low = (brand or "").strip().lower()
        _brand_title = (brand or "").strip()
        max_insist = 1
        ok = False
        for attempt in range(max_insist):
            ok = await self._navigate_ripley(url)
            if not ok:
                if attempt < max_insist - 1:
                    await self._mutate_context()
                    await asyncio.sleep(5)
                    continue
                break
        if not ok:
            return {"products": [], "pages_traversed": 0, "stop_reason": "BLOCKED",
                    "failure_type": "Cloudflare/WAF", "pagination": None, "sort_mode": None}

        body_text = await self.page.evaluate("document.body?.innerText || ''")
        body_text_lower = body_text.lower()
        strict_empty_indicators = [
            "no existen productos que cumplan con tus criterios de filtrado",
            "intenta ajustar los filtros aplicados",
            "no encontramos resultados",
            "la p\u00e1gina que buscas ya no se encuentra disponible",
            "la pagina que buscas ya no se encuentra disponible",
        ]
        if any(ind in body_text_lower for ind in strict_empty_indicators) or re.search(r'(?<!\d)0\s+resultados', body_text_lower):
            return {"products": [], "pages_traversed": 1, "stop_reason": "EXHAUSTION",
                    "failure_type": None, "pagination": None, "sort_mode": None}

        current_url = self.page.url
        is_pdp = bool(re.search(r'-mpm\d+', current_url) or '/p/' in current_url or '/mp/' in current_url)
        products = []
        if is_pdp:
            next_data = await self.page.evaluate("""() => {
                const el = document.getElementById('__NEXT_DATA__');
                return el ? el.innerText : null;
            }""")
            if next_data:
                try:
                    data = json.loads(next_data)
                    product_data = data.get("props", {}).get("pageProps", {}).get("product", {})
                    if product_data:
                        b = product_data.get("brand", "")
                        title = product_data.get("name", "")
                        price = 0.0
                        prices = product_data.get("prices", {})
                        if prices.get("offerPrice"):
                            price = float(prices["offerPrice"])
                        elif prices.get("listPrice"):
                            price = float(prices["listPrice"])
                        sku = product_data.get("partNumber", "") or product_data.get("uniqueID", "")
                        products.append({
                            "title": title,
                            "vendor": b,
                            "price": price,
                            "marketplace_sku": sku,
                            "position_absolute": 1,
                        })
                except Exception as e:
                    logger.warning(f"[Ripley] Failed to parse NEXT_DATA for PDP: {e}")
            if not products:
                return {"products": [], "pages_traversed": 0, "stop_reason": "EXTRACTOR_FAILURE",
                        "failure_type": "PDP Extraction Failed", "pagination": None, "sort_mode": None}
            return {"products": products, "pages_traversed": 1, "stop_reason": "EXHAUSTION",
                    "failure_type": "PDP_REDIRECT", "pagination": None, "sort_mode": None}

        product_selector = ".product-item--wrapper, .catalog-product-item"

        async def _load_and_extract_page():
            prev_count = 0
            unchanged_count = 0
            for _scroll_step in range(250):
                await self.page.evaluate("""() => {
                    const scrollAmount = window.innerHeight * 0.8 + Math.random() * 200;
                    window.scrollBy({ top: scrollAmount, behavior: 'smooth' });
                }""")
                try:
                    await self.page.wait_for_function(
                        f"document.querySelectorAll('{product_selector}').length > {prev_count}",
                        timeout=3000)
                except Exception:
                    await asyncio.sleep(0.8)
                items = await self.page.query_selector_all(product_selector)
                curr_count = len(items)
                is_bottom = await self.page.evaluate("window.innerHeight + window.scrollY >= document.body.offsetHeight - 100")
                if curr_count == prev_count:
                    unchanged_count += 1
                else:
                    unchanged_count = 0
                prev_count = curr_count
                if unchanged_count >= 3 or (is_bottom and unchanged_count >= 1):
                    break
                await asyncio.sleep(random.uniform(0.4, 0.9))
            if prev_count == 0:
                return None
            extracted_data = await self.page.evaluate(f"""
            () => {{
                    const __bn = "{_brand_low}";
                    const __bt = "{_brand_title}";
                const items = Array.from(document.querySelectorAll('{product_selector}'));
                return items.map((item, index) => {{
                    const brandEl = item.querySelector(".brand-name, .catalog-product-details__logo, .catalog-product-details__brand, [class*='brand']");
                    const titleEl = item.querySelector(".catalog-product-details__name, [class*='name'], [class*='title']");
                    const priceEl = item.querySelector(".catalog-prices__offer-price, .catalog-prices__card-price, .catalog-prices__list-price, .catalog-product-details__prices, [class*='price'], [class*='Price']");
                    const linkEl = item.querySelector("a[href*='/p/'], a[href*='/mp/'], a[href]");
                    const parentLink = item.closest("a[href]");

                    let brand = brandEl ? brandEl.innerText.trim() : "";
                    let title = titleEl ? titleEl.innerText.trim() : "";
                    let priceText = priceEl ? priceEl.innerText.trim() : "";

                    let mktSku = item.getAttribute("data-part-number") || item.getAttribute("data-sku-id") || item.getAttribute("data-product-id") || item.getAttribute("id") || "";
                    const itemLink = linkEl ? linkEl.getAttribute("href") : (parentLink ? parentLink.getAttribute("href") : (item.tagName === 'A' ? item.getAttribute("href") : ""));

                    // FIX MRI-RIPLEY-IDENTITY-001: Extract product ID from image URL
                    // Ripley image URLs contain the product ID: .../MPM10002617343/full_image-4
                    const imgEl = item.querySelector("img[src*='MPM'], img[src*='mpm']");
                    if (imgEl) {{
                        const imgSrc = imgEl.getAttribute("src") || "";
                        const mpmMatch = imgSrc.match(/(MPM\\d+)/i);
                        if (mpmMatch) {{
                            mktSku = mpmMatch[1].toUpperCase();
                        }}
                    }}

                    // Fallback: extract from href if image didn't work
                    if (!mktSku && itemLink) {{
                        const mpmMatch = itemLink.match(/(mpm\\d+)/i);
                        if (mpmMatch) {{
                            mktSku = mpmMatch[1].toUpperCase();
                        }} else {{
                            const numMatch = itemLink.match(/(\\d{{7,15}})/);
                            if (numMatch) {{
                                mktSku = numMatch[1];
                            }}
                        }}
                    }}

                    brand = brand.replace(/^Por\\s+/i, "").trim();

                    return {{
                        index: index,
                        brand: brand,
                        title: title,
                        priceText: priceText,
                        mktSku: mktSku,
                        url: itemLink,
                        html: (!brand || !title) ? item.outerHTML : null
                    }};
                }});
            }}
            """)

            rows = []
            anansi_parser = AdaptiveParser() if AdaptiveParser else None
            for data in extracted_data:
                try:
                    brand_out = data['brand']
                    title = data['title']
                    price_text = data.get('priceText', '')
                    marketplace_sku = str(data.get('mktSku', '')).strip()
                    if marketplace_sku:
                        digit_match = re.search(r"(\d{7,15})", marketplace_sku)
                        if digit_match:
                            marketplace_sku = digit_match.group(1)
                    price = self.parse_price_text(price_text) if price_text else 0.0
                    if (not brand_out or not title) and anansi_parser:
                        try:
                            item_html = data['html']
                            rescate = await anansi_parser.extract(item_html, {
                                "rescued_title": SelectorConfig(".title", expected_pattern=r"\w+")
                            }, url="https://simple.ripley.cl")
                            if not title and rescate.get("rescued_title"):
                                title = rescate.get("rescued_title")
                        except Exception:
                            pass
                    if title or brand_out:
                        rows.append({"title": title, "vendor": brand_out, "price": price,
                                     "marketplace_sku": marketplace_sku, "url": f"https://simple.ripley.cl{data.get('url', '')}" if data.get('url', '').startswith('/') else data.get('url', '')})
                except Exception as e:
                    logger.warning(f"[Ripley] Error parsing extracted data: {e}")
            return rows

        t_start = time.time()
        page_rows = await _load_and_extract_page()
        if page_rows is None:
            return {"products": [], "pages_traversed": 0, "stop_reason": "EXTRACTOR_FAILURE",
                    "failure_type": "No items found on category", "pagination": None, "sort_mode": None}

        try:
            body_text_after = await self.page.evaluate("document.body?.innerText || ''")
        except Exception:
            body_text_after = body_text
        pager = parse_pager_text(body_text_after)

        next_data_cat = await self.page.evaluate("""() => {
            const el = document.getElementById('__NEXT_DATA__');
            return el ? el.innerText : null;
        }""")
        if next_data_cat:
            try:
                import math
                data_json = json.loads(next_data_cat)
                findability = data_json.get("props", {}).get("pageProps", {}).get("findabilityProps", {})
                cat_data = findability.get("data", {})
                if cat_data:
                    cat_total = int(cat_data.get("total") or 0)
                    cat_limit = int(cat_data.get("limit") or 1)
                    if cat_total and cat_limit:
                        total_pages = int(math.ceil(cat_total / cat_limit))
                        current_page = int(findability.get("currentPage", 1))
                        pager = {"current": current_page, "total": total_pages}
            except Exception as e:
                logger.warning(f"[Ripley] Failed to parse NEXT_DATA for pagination: {e}")

        sort_mode = detect_sort_mode(body_text_after)
        plan = pagination or {}
        param = plan.get("param")
        if not param:
            m = re.search(r"[?&](page|p|offset)=\d+", self.page.url)
            if m:
                param = m.group(1)
            elif pager:
                m2 = re.search(r"[?&](page|p|offset)=\d+", url)
                if m2:
                    param = m2.group(1)
                else:
                    param = "page"
        total = (pager or {}).get("total")
        if total is None and param:
            _mo = plan.get("max_observed")
            if _mo:
                total = _mo + 1

        all_rows = []
        seen_skus = set()
        page_records = []

        def _annotate(rows, page_number):
            new_unique = 0
            for i, r in enumerate(rows):
                sku = r.get("marketplace_sku") or r.get("title", "")
                if sku and sku not in seen_skus:
                    seen_skus.add(sku)
                    new_unique += 1
                r["page_or_batch"] = page_number
                r["position_in_batch"] = i + 1
                r["position_observed"] = len(all_rows) + i + 1
                r["position_absolute"] = r["position_observed"]
                r["page_url"] = self.page.url
                r["surface_url"] = url
            all_rows.extend(rows)
            return new_unique

        _last_obs_first = bool(pager and total is not None and pager.get("current") == total)
        page_records.append({"page": 1, "url": self.page.url, "items": len(page_rows),
                             "new_unique": _annotate(page_rows, 1),
                             "last_page_observed": _last_obs_first})

        stop_reason = "EXHAUSTION" if (total is not None and total <= 1) else "UNKNOWN"
        if param and total is not None and int(total) > 1:
            base = plan.get("base_url") or url
            current = int((pager or {}).get("current") or 1)
            total = int(total)
            while current < total and current < max_pages:
                if time.time() - t_start > 480:
                    stop_reason = "PAGE_TIME_BUDGET"
                    break
                nxt = current + 1
                next_url = pagination_url(base, param, nxt)
                try:
                    await self.page.goto(next_url, wait_until="commit", timeout=45000)
                    await self.page.wait_for_timeout(random.randint(2000, 4000))
                    navigated = bool(re.search(rf"[?&]{re.escape(param)}={nxt}(&|$)", self.page.url))
                except Exception as nav_exc:
                    page_records.append({"page": nxt, "url": next_url, "items": 0, "new_unique": 0,
                                         "error": str(nav_exc), "last_page_observed": False})
                    stop_reason = "FAILED_TRANSITION"
                    break
                if not navigated:
                    page_records.append({"page": nxt, "url": next_url, "items": 0, "new_unique": 0,
                                         "error": "state-not-validated", "last_page_observed": False})
                    stop_reason = "FAILED_TRANSITION"
                    break
                rows = await _load_and_extract_page()
                if rows is None:
                    page_records.append({"page": nxt, "url": self.page.url, "items": 0, "new_unique": 0,
                                         "error": "no-items", "last_page_observed": False})
                    stop_reason = "NO_PROGRESS"
                    break
                new_unique = _annotate(rows, nxt)
                last_obs = (nxt == total)
                page_records.append({"page": nxt, "url": self.page.url, "items": len(rows),
                                     "new_unique": new_unique, "last_page_observed": last_obs})
                if new_unique == 0:
                    stop_reason = "NO_PROGRESS"
                    break
                current = nxt
            if stop_reason == "UNKNOWN":
                if current >= total:
                    stop_reason = "EXHAUSTION" if page_records[-1].get("last_page_observed") else "PARTIAL_LAST_PAGE_UNOBSERVED"
                elif current >= max_pages:
                    stop_reason = "PAGE_BUDGET_EXCEEDED"
                else:
                    stop_reason = "PARTIAL"
        elif total is not None and total <= 1:
            stop_reason = "EXHAUSTION"
        elif param and total is None:
            stop_reason = "UNKNOWN_TOTAL_PAGES"
        elif total is not None and total > 1 and not param:
            stop_reason = "PAGINATION_PARAM_NOT_FOUND"
        else:
            stop_reason = "PAGINATION_PARAM_NOT_FOUND"

        pagination_info = {
            "param": param,
            "base_url": plan.get("base_url") or url,
            "total_declared": total,
            "pages": page_records,
            "last_page_observed": bool(page_records and page_records[-1].get("last_page_observed")),
        }
        return {"products": all_rows, "pages_traversed": len(page_records),
                "stop_reason": stop_reason, "failure_type": None,
                "pagination": pagination_info, "sort_mode": sort_mode}

    async def scrape_top_240(self, url: str) -> list[dict]:
        """Scrape top 240 products from a Ripley category."""
        category_path = self._url_to_category_path(url)
        category_url = f"https://simple.ripley.cl/{category_path}"

        max_insist = 1
        for attempt in range(max_insist):
            # Navigate to the exact requested URL
            ok = await self._navigate_ripley(url)
            if not ok:
                logger.error(f"[Ripley] Cannot navigate to {url} — attempt {attempt+1}/{max_insist}")
                if attempt < max_insist - 1:
                    logger.info("[Ripley] Insisting on scraping due to failure... mutating context.")
                    await self._mutate_context()
                    await asyncio.sleep(random.uniform(5, 10))
                    continue
                else:
                    return []

            # Check for explicit empty state before attempting to scroll or extract items
            body_text = await self.page.evaluate("document.body?.innerText || ''")
            body_text_lower = body_text.lower()
            strict_empty_indicators = [
                "no existen productos que cumplan con tus criterios de filtrado",
                "intenta ajustar los filtros aplicados",
                "no encontramos resultados",
            ]
            # FIX RIP-2: "0 resultados" NO debe ser substring (10/20/100 resultados).
            if any(ind in body_text_lower for ind in strict_empty_indicators) or re.search(r'(?<!\d)0\s+resultados', body_text_lower):
                logger.info(f"[Ripley] Scrape aborted: empty state indicator present on page ('{category_path}')")
                return []

            products = []
            anansi_parser = AdaptiveParser() if AdaptiveParser else None
            product_selector = ".product-item--wrapper, .catalog-product-item"

            # Scroll to load lazy content with dynamic, organic waits
            prev_count = 0
            unchanged_count = 0
            max_scrolls = 25  # Allow more scrolls since they will be smaller and more organic

            for scroll_step in range(max_scrolls):
                # Organic scroll: scroll by roughly the viewport height plus a random offset
                await self.page.evaluate("""() => {
                    const scrollAmount = window.innerHeight * 0.8 + Math.random() * 200;
                    window.scrollBy({ top: scrollAmount, behavior: 'smooth' });
                }""")

                # Wait dynamically for items to increase or a small timeout
                try:
                    await self.page.wait_for_function(
                        f"document.querySelectorAll('{product_selector}').length > {prev_count}",
                        timeout=3000
                    )
                except Exception:
                    await asyncio.sleep(0.8)  # Wait a bit longer if elements are slow to load

                items = await self.page.query_selector_all(product_selector)
                curr_count = len(items)

                # Check if we've reached the bottom of the page
                is_bottom = await self.page.evaluate("window.innerHeight + window.scrollY >= document.body.offsetHeight - 100")

                if curr_count == prev_count:
                    unchanged_count += 1
                else:
                    unchanged_count = 0

                prev_count = curr_count

                if prev_count >= 240:
                    logger.info(f"[Ripley] Reached target product count: {prev_count}")
                    break

                if unchanged_count >= 3 or (is_bottom and unchanged_count >= 1):
                    logger.info(f"[Ripley] No new products loaded (unchanged: {unchanged_count}, is_bottom: {is_bottom}). Stopping early at {prev_count}.")
                    break

                # Additional small human-like pause to avoid anti-bot triggers
                await asyncio.sleep(random.uniform(0.4, 0.9))

            items = await self.page.query_selector_all(product_selector)
            logger.info(f"[Ripley] Found {len(items)} product pods")

            # Batch extraction via page.evaluate to minimize IPC overhead
            extracted_data = await self.page.evaluate(f"""
                () => {{
                    const items = Array.from(document.querySelectorAll('{product_selector}')).slice(0, 240);
                    return items.map((item, index) => {{
                        const brandEl = item.querySelector(".brand-name, .catalog-product-details__logo, .catalog-product-details__brand, [class*='brand']");
                        const titleEl = item.querySelector(".catalog-product-details__name, [class*='name'], [class*='title']");
                        const priceEl = item.querySelector(".catalog-prices__offer-price, .catalog-prices__card-price, .catalog-prices__list-price, .catalog-product-details__prices, [class*='price'], [class*='Price']");
                        const linkEl = item.querySelector("a[href*='/p/'], a[href*='/mp/'], a[href]");

                        const parentLink = item.closest("a[href]");
                        let brand = brandEl ? brandEl.innerText.trim() : "";
                        let title = titleEl ? titleEl.innerText.trim() : "";
                        let priceText = priceEl ? priceEl.innerText.trim() : "";

                        let mktSku = item.getAttribute("data-part-number") || item.getAttribute("data-sku-id") || item.getAttribute("data-product-id") || item.getAttribute("id") || "";
                        const itemLink = linkEl ? linkEl.getAttribute("href") : (parentLink ? parentLink.getAttribute("href") : (item.tagName === 'A' ? item.getAttribute("href") : ""));
                        if (itemLink) {{
                            const numMatch = itemLink.match(/(\\d{{7,15}})/);
                            if (numMatch) {{
                                mktSku = numMatch[1];
                            }} else {{
                                const match = itemLink.match(/\\/(?:m?p|producto|p)\\/([^\\?\\/#]+)/i);
                                if (match) {{
                                    mktSku = match[1];
                                }} else {{
                                    const parts = itemLink.split("/").filter(Boolean);
                                    if (parts.length > 0) mktSku = parts[parts.length - 1].split("?")[0];
                                }}
                            }}
                        }}

                        brand = brand.replace(/^Por\\s+/i, "").trim();

                        return {{
                            index: index,
                            brand: brand,
                            title: title,
                            priceText: priceText,
                            mktSku: mktSku,
                            url: itemLink,
                            html: (!brand || !title) ? item.outerHTML : null
                        }};
                    }});
                }}
            """)

            for data in extracted_data:
                try:
                    i = data['index']
                    brand = data['brand']
                    title = data['title']
                    price_text = data.get('priceText', '')
                    marketplace_sku = str(data.get('mktSku', '')).strip()
                    if marketplace_sku:
                        digit_match = re.search(r"(\d{7,15})", marketplace_sku)
                        if digit_match:
                            marketplace_sku = digit_match.group(1)

                    price = self.parse_price_text(price_text) if price_text else 0.0

                    # --- CAPA DE RESCATE ANANSI (Only runs if JS failed to find title/brand) ---
                    if (not brand or not title) and anansi_parser:
                        try:
                            item_html = data['html']
                            rescate = await anansi_parser.extract(item_html, {
                                "rescued_title": SelectorConfig(".title", expected_pattern=r"\w+")
                            }, url="https://simple.ripley.cl")

                            if not title and rescate.get("rescued_title"):
                                title = rescate.get("rescued_title")
                                logger.debug(f"[Anansi Ripley] Título rescatado: {title}")

                        except Exception as e:
                            logger.warning(f"Fallo en Anansi fallback Ripley: {e}")
                    # --- FIN CAPA DE RESCATE ---

                    if title or brand:
                        products.append({
                            "position_absolute": i + 1,
                            "title": title,
                            "vendor": brand,
                            "price": price,
                            "marketplace_sku": marketplace_sku,
                            "url": f"https://simple.ripley.cl{data.get('url', '')}" if data.get('url', '').startswith('/') else data.get('url', ''),
                            "page": (i // 40) + 1,
                        })
                except Exception as e:
                    logger.debug(f"[Ripley] Error parsing product {data.get('index', 'unknown')}: {e}")

            if products:
                logger.info(f"[Ripley] Scraped {len(products)} products from {category_path}")
                return products

            logger.warning(f"[Ripley] Scraped 0 products from {category_path} — attempt {attempt+1}/{max_insist}")
            if attempt < max_insist - 1:
                logger.info("[Ripley] Insisting on scraping (0 found)... mutating context.")
                await self._mutate_context()
                await asyncio.sleep(random.uniform(5, 10))
                continue

        logger.warning(f"[Ripley] Scraped 0 products from {category_path} after {max_insist} attempts.")
        return []
