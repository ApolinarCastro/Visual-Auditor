"""
Enhanced Base Scraper v3
- Clean Architecture without Monkey Patching
- Integrates SelectorRegistry (self-learning selectors)
- Obscura CDP Primary Engine with Playwright Fallback (Self-Healing)
- Safe Session IDs to prevent Race Conditions
- Process Zombie protection
"""
# pyrefly: ignore [missing-import]
from playwright.async_api import async_playwright
import asyncio
import logging
import random
import re
import os
import uuid
import sys
import subprocess
import atexit

logger = logging.getLogger(__name__)

# Phase B: Structural Constants
DEFAULT_TIMEOUT_MS = 60000
WARMUP_TIMEOUT_MS = 30000
CF_DELAY_MIN_MS = 8000
CF_DELAY_MAX_MS = 15000
NAVIGATION_DELAY_MIN_MS = 3000
NAVIGATION_DELAY_MAX_MS = 5000
BACKOFF_BASE_DELAY = 10
MUTATION_LIMIT = 6
SESSIONS_DIR = os.path.join("data", "sessions")

_global_playwright = None
_playwright_lock = asyncio.Lock()

# Ensure global playwright stops cleanly
def _cleanup_global_playwright():
    global _global_playwright
    if _global_playwright:
        try:
            # We can't use await in atexit easily, so we just run it synchronously if possible
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_global_playwright.stop())
            else:
                loop.run_until_complete(_global_playwright.stop())
        except:
            pass

atexit.register(_cleanup_global_playwright)


class BaseScraper:
    def __init__(self, headless: bool = True, browser_type: str = "chromium", marketplace: str = "unknown", mobile: bool = False) -> None:
        self.headless: bool = headless
        self.browser_type: str = browser_type
        self.marketplace: str = marketplace
        self.mobile: bool = mobile
        
        # Prevent Session Race Conditions
        self.session_id = str(uuid.uuid4())[:8]
        
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None
        self._mutation_count: int = 0
        self._last_navigation_successful: bool = False
        
        self.is_using_obscura = False
        self._obscura_anchor_context = None

    def _get_storage_path(self) -> str:
        """Returns the isolated session storage path inside SESSIONS_DIR."""
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        return os.path.join(SESSIONS_DIR, f"storage_{self.marketplace}_{self.mobile}_{self.session_id}.json")

    def _cleanup_storage_files(self) -> None:
        """Purges legacy root storage files and cleans up expired session files (>24h)."""
        # 1. Clean root directory leftover storage files
        try:
            for item in os.listdir("."):
                if item.startswith("storage_") and item.endswith(".json"):
                    try:
                        os.remove(item)
                        logger.info(f"[{self.marketplace}] Removed legacy root session file: {item}")
                    except Exception:
                        pass
        except Exception:
            pass

        # 2. Clean old session files in SESSIONS_DIR (> 24 hours)
        try:
            if os.path.exists(SESSIONS_DIR):
                import time
                now = time.time()
                for item in os.listdir(SESSIONS_DIR):
                    if item.startswith("storage_") and item.endswith(".json"):
                        filepath = os.path.join(SESSIONS_DIR, item)
                        if now - os.path.getmtime(filepath) > 86400:
                            try:
                                os.remove(filepath)
                                logger.info(f"[{self.marketplace}] Purged expired session file: {item}")
                            except Exception:
                                pass
        except Exception:
            pass

    async def start(self) -> None:
        global _global_playwright
        self._cleanup_storage_files()
        from app.intelligence.selector_registry import ranked_selectors, record_selector
        
        # Decide which engine to use
        best_engines = await ranked_selectors(self.marketplace, "browser_engine", ["obscura", "playwright"])
        selected_engine = best_engines[0] if best_engines else "playwright"
        self.is_using_obscura = (selected_engine == "obscura")

        # FIX G (7-Ago): Obscura CDP no soporta add_cookies, screenshot ni
        # page.evaluate para Ripley. Forzar Playwright nativo.
        if self.marketplace.lower() == "ripley" and self.is_using_obscura:
            logger.info(f"[{self.marketplace}] Forzando Playwright nativo (Obscura incompatible con Ripley)")
            self.is_using_obscura = False

        best_profiles = await ranked_selectors(
            self.marketplace, "stealth_profile", [f"mobile={self.mobile}"]
        )
        if best_profiles and "mobile=" in best_profiles[0]:
            self.mobile = "mobile=True" in best_profiles[0]
            if self.browser_type == "firefox":
                self.mobile = False
        # FIX ML-6c/d (14-Ago): forzar DESKTOP para Mercado Libre.
        # La configuracion probada que funciona (14-Ago 09:4x, 192 productos sin
        # bloqueo) es DESKTOP + invitado puro. El fingerprint movil hacia que ML
        # siguiera mostrando login wall/captcha. Se fuerza mobile=False incluso
        # si el perfil aprendido dice mobile=True (corridas anteriores fallidas).
        if self.marketplace.lower() == "mercado libre":
            self.mobile = False
        logger.info(f"[{self.marketplace}] Applied learned stealth profile: mobile={self.mobile}")

        # Fetch best UA from learning layer
        if self.marketplace.lower() == "mercado libre":
            # FIX ML-8 (14-Ago): el UA aprendido dispara account-verification en ML.
            # Se deja el UA del perfil persistente real (probado: 192 productos OK).
            self.user_agent = None
            logger.info("[Mercado Libre] UA aprendido omitido (FIX ML-8): usa UA del perfil persistente")
        else:
            ua_list = self._get_mobile_ua_list() if self.mobile else self._get_ua_list()
            best_uas = await ranked_selectors(self.marketplace, "stealth_ua", ua_list)
            self.user_agent = best_uas[0]
            logger.info(f"[{self.marketplace}] Applied learned UA: {self.user_agent[:40]}...")

        async with _playwright_lock:
            if _global_playwright is None:
                _global_playwright = await async_playwright().start()
        self._playwright = _global_playwright

        if self.is_using_obscura:
            logger.info(f"[{self.marketplace}] IA seleccionó motor primario: OBSCURA")
            try:
                logger.info(f"[{self.marketplace}] Conectando a Obscura CDP en localhost:9222...")
                self.browser = await self._playwright.chromium.connect_over_cdp("http://localhost:9222")
                # Create anchor context
                self._obscura_anchor_context = await self.browser.new_context()
                await self._init_context()
                logger.info(f"[{self.marketplace}] Motor Obscura inicializado correctamente.")
                return
            except Exception as e:
                logger.error(f"[{self.marketplace}] Fallo al inicializar Obscura: {e}")
                await record_selector(self.marketplace, "browser_engine", "obscura", success=False)
                logger.info(f"[{self.marketplace}] Aplicando Plan B (Fallback a Playwright)...")
                self.is_using_obscura = False

        # Fallback / Native Playwright
        logger.info(f"[{self.marketplace}] Inicializando motor Playwright Nativo...")

        # FIX ML-2 (14-Ago): forzar headless=False para ML y Ripley.
        # Sin ventana real, ML redirige a account-verification (deteccion de bot).
        if self.marketplace.lower() in ("ripley", "mercado libre"):
            self.headless = False
            logger.info(f"[{self.marketplace}] Forcing headless=False to bypass Akamai/WAF bot shield natively.")

        chromium_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-position=-32000,-32000" if self.marketplace.lower() in ("ripley", "mercado libre") else "--window-position=0,0",
            "--ignore-certificate-errors",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-gpu" if self.headless else "--enable-gpu",
            "--disable-extensions",
            "--disable-plugins",
        ]

        if self.marketplace.lower() in ["ripley", "mercado libre"]:
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            ]
            browser_exe = next((p for p in chrome_paths if os.path.exists(p)), None)
            if browser_exe:
                user_data_dir = os.path.abspath(os.path.join("data", f"{self.marketplace.lower().replace(' ', '_')}_profile"))
                os.makedirs(user_data_dir, exist_ok=True)

                logger.info(f"[{self.marketplace}] Launching native Chrome browser context with persistent profile ({user_data_dir})...")
                # Proactively remove Chrome singleton lock files left by crashed sessions.
                # These do NOT corrupt the profile — they are only process-lock markers.
                for _lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                    _lock_path = os.path.join(user_data_dir, _lock_name)
                    try:
                        if os.path.exists(_lock_path):
                            os.remove(_lock_path)
                            logger.debug(f"[{self.marketplace}] Removed stale lock: {_lock_path}")
                    except OSError:
                        pass  # If still locked by a live process, launch will fail naturally
                launch_kwargs = dict(
                    user_data_dir=user_data_dir,
                    executable_path=browser_exe,
                    headless=self.headless,
                    args=chromium_args,
                    viewport={"width": 390, "height": 844} if self.mobile else {"width": 1440, "height": 900},
                    locale="es-CL",
                    timezone_id="America/Santiago",
                )
                if self.user_agent:
                    launch_kwargs["user_agent"] = self.user_agent
                try:
                    self.context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)
                    self.browser = self.context.browser
                    self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                    await self._apply_stealth_scripts()
                except Exception as _profile_err:
                    _err_str = str(_profile_err)
                    if "ProcessSingleton" in _err_str or "profile directory" in _err_str or "SingletonLock" in _err_str:
                        logger.warning(
                            f"[{self.marketplace}] Persistent profile locked (ProcessSingleton). "
                            f"Falling back to ephemeral context. Cause: {_err_str[:200]}"
                        )
                        # Ephemeral fallback: same exe, no persistent profile
                        _ephemeral_args = [a for a in chromium_args if "--user-data-dir" not in a]
                        self.browser = await self._playwright.chromium.launch(
                            executable_path=browser_exe,
                            headless=self.headless,
                            args=_ephemeral_args,
                        )
                        await self._init_context()
                    else:
                        raise

            else:
                self.browser = await self._playwright.chromium.launch(headless=self.headless, args=chromium_args)
                await self._init_context()
        elif self.browser_type == "chromium":
            self.browser = await self._playwright.chromium.launch(
                headless=self.headless, args=chromium_args
            )
            await self._init_context()
        else:
            self.browser = await self._playwright.firefox.launch(headless=self.headless)
            await self._init_context()

        # Apply stealth after init
        await self._apply_stealth_scripts()

        # FIX ML-7 (14-Ago): NO aplicar playwright-stealth para Mercado Libre.
        # El perfil persistente real + desktop + invitado puro pasa sin bloqueo
        # (192 productos, 14-Ago 09:4x). El script de evasion es detectable por
        # Akamai y dispara el login wall/captcha.
        if self.marketplace.lower() != "mercado libre":
            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(self.page)
                logger.info(f"[{self.marketplace}] Stealth mode applied (playwright-stealth)")
            except ImportError:
                logger.debug(f"[{self.marketplace}] playwright-stealth not installed - using fallback evasions")
        else:
            logger.info("[Mercado Libre] playwright-stealth omitido (FIX ML-7): perfil persistente real basta")

        await asyncio.sleep(random.uniform(0.5, 1.5))
        logger.info(f"[{self.marketplace}] Browser started (headless={self.headless}, type={self.browser_type})")

    async def _init_context(self) -> None:
        """Helper to init viewport, UA and storage"""
        viewport = {"width": 390, "height": 844} if self.mobile else {"width": 1440, "height": 800}
        ua = self.user_agent
        is_mobile_supported = (self.browser_type != "firefox")
        
        context_kwargs = {
            "viewport": viewport,
            "is_mobile": self.mobile if is_mobile_supported else False,
            "has_touch": self.mobile if is_mobile_supported else False,
            "locale": "es-CL",
            "timezone_id": "America/Santiago",
            "permissions": ["geolocation"],
            "color_scheme": "dark",
            "user_agent": ua,
        }
        
        import time
        storage_path = self._get_storage_path()
        if os.path.exists(storage_path):
            if time.time() - os.path.getmtime(storage_path) < 86400 and self.marketplace.lower() != "mercado libre":
                context_kwargs["storage_state"] = storage_path
                logger.info(f"[{self.marketplace}] Loaded session state from {storage_path}")
            else:
                try: os.remove(storage_path)
                except: pass

        try:
            self.context = await self.browser.new_context(**context_kwargs)
        except Exception as ctx_err:
            # FIX C (7-Ago): algunos motores CDP (Obscura) no soportan
            # Browser.grantPermissions. Reintentar sin 'permissions'.
            if "permissions" in context_kwargs:
                logger.warning(f"[{self.marketplace}] new_context fallo con permissions ({ctx_err}); reintentando sin permissions")
                context_kwargs.pop("permissions", None)
                self.context = await self.browser.new_context(**context_kwargs)
            else:
                raise
        if getattr(self, "page", None) is None:
            self.page = await self.context.new_page()

    async def _apply_stealth_scripts(self) -> None:
        """Applies route blocking and JS evasion techniques to the current context."""
        await self.context.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}",
            lambda route: route.abort()
            if not self.headless
            else route.continue_(),
        )
        await self.context.route(
            "**/analytics*,**/gtag*,**/hotjar*,**/facebook*,**/doubleclick*",
            lambda route: route.abort(),
        )

        # Advanced anti-detection scripts
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
            const ua = navigator.userAgent;
            const platform = ua.includes('Macintosh') ? 'MacIntel' : (ua.includes('iPhone') ? 'iPhone' : (ua.includes('Windows') ? 'Win32' : 'Linux x86_64'));
            Object.defineProperty(navigator, 'platform', { get: () => platform });
            Object.defineProperty(navigator, 'languages', { get: () => ['es-CL', 'es', 'en'] });
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel(R) Iris(TM) Plus Graphics 640';
                return getParameter.apply(this, arguments);
            };
            // Mask Playwright-specific properties
            delete window.__playwright;
            delete window.__pwInitScripts;
        """)

    async def navigate(self, url: str, max_retries: int = 5) -> bool:
        """Navega y soporta self-healing en caso de fallo de Obscura."""
        from app.intelligence.selector_registry import record_selector
        try:
            res = await self._navigate_internal(url, max_retries)
            if res:
                engine_used = "obscura" if self.is_using_obscura else "playwright"
                await record_selector(self.marketplace, "browser_engine", engine_used, success=True)
            return res
        except Exception as e:
            if self.is_using_obscura:
                logger.error(f"[{self.marketplace}] Obscura falló durante la navegación. Error: {e}")
                await record_selector(self.marketplace, "browser_engine", "obscura", success=False)
                logger.info(f"[{self.marketplace}] Activando Self-Healing -> Cambiando a Playwright (Plan B)...")
                
                await self.stop()
                self.is_using_obscura = False
                
                await self.start()
                logger.info(f"[{self.marketplace}] Motor Playwright levantado exitosamente. Reintentando navegación...")
                return await self._navigate_internal(url, max_retries)
            else:
                await record_selector(self.marketplace, "browser_engine", "playwright", success=False)
                raise e

    async def _navigate_internal(self, url: str, max_retries: int = 5) -> bool:
        self._mutation_count = 0
        self._last_navigation_successful = False
        for attempt in range(max_retries):
            try:
                if not self.page or self.page.is_closed() or not self.context:
                    logger.warning(f"[{self.marketplace}] Page or browser closed before navigation attempt {attempt+1}. Restarting browser...")
                    await self.start()

                logger.info(f"[{self.marketplace}] Navigating to {url} (attempt {attempt+1}/{max_retries})")

                if attempt == 0:
                    try:
                        base_url = "https://" + url.split("/")[2]
                        logger.debug(f"[{self.marketplace}] Warming at {base_url}")
                        await self.page.goto(base_url, wait_until="commit", timeout=WARMUP_TIMEOUT_MS)
                        await self.page.wait_for_timeout(random.randint(500, 1000))
                        await self.page.mouse.move(
                            random.randint(100, 500), random.randint(100, 400)
                        )
                        await self.page.mouse.wheel(0, random.randint(200, 500))
                    except Exception as e:
                        logger.debug(f"[{self.marketplace}] Warming phase timed out/failed: {e}")

                await asyncio.sleep(random.uniform(0.5, 1.0))

                try:
                    await self.page.set_extra_http_headers({
                        "Referer": "https://" + url.split("/")[2] + "/",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
                        "Cache-Control": "max-age=0",
                        "Upgrade-Insecure-Requests": "1",
                    })
                except Exception as ex_hdr:
                    logger.debug(f"[{self.marketplace}] Could not set extra headers: {ex_hdr}")

                response = await self.page.goto(
                    url, wait_until="commit", timeout=DEFAULT_TIMEOUT_MS
                )
                await self.page.wait_for_timeout(random.randint(NAVIGATION_DELAY_MIN_MS, NAVIGATION_DELAY_MAX_MS))

                title = await self.page.title()
                status = response.status if response else 0

                if "Just a moment" in title or "Cloudflare" in title or status == 403:
                    wait_ms = random.randint(CF_DELAY_MIN_MS, CF_DELAY_MAX_MS)
                    logger.warning(
                        f"[{self.marketplace}] Cloudflare detected (status={status}). "
                        f"Waiting {wait_ms}ms..."
                    )
                    await self.page.wait_for_timeout(wait_ms)
                    await self.page.mouse.move(
                        random.randint(200, 600), random.randint(200, 500)
                    )
                    await self.page.mouse.click(
                        random.randint(200, 600), random.randint(200, 500)
                    )
                    await self.page.wait_for_timeout(5000)
                    title = await self.page.title()
                    status = 200 if "Just a moment" not in title else 403

                if status == 200:
                    await self.page.wait_for_timeout(random.randint(2000, 4000))
                    await self.page.evaluate("window.scrollBy(0, window.innerHeight / 3)")
                    storage_path = self._get_storage_path()
                    await self.context.storage_state(path=storage_path)
                    
                    from app.intelligence.selector_registry import record_selector
                    await record_selector(self.marketplace, "stealth_profile", f"mobile={self.mobile}", success=True)
                    if hasattr(self, 'user_agent') and self.user_agent:
                        await record_selector(self.marketplace, "stealth_ua", self.user_agent, success=True)
                    self._last_navigation_successful = True
                    return True

                logger.warning(f"[{self.marketplace}] Non-200 (status={status}) on attempt {attempt+1}")
                
                if status == 403 or "Just a moment" in title:
                    await self._mutate_context()

                if attempt == max_retries - 1:
                    await self._save_debug_snapshot(url, f"nav_fail_{attempt}")
                    from app.intelligence.selector_registry import record_selector
                    await record_selector(self.marketplace, "stealth_profile", f"mobile={self.mobile}", success=False)
                    if hasattr(self, 'user_agent') and self.user_agent:
                        await record_selector(self.marketplace, "stealth_ua", self.user_agent, success=False)
                    raise Exception(f"Navigation failed with status {status}")

            except Exception as exc:
                logger.error(f"[{self.marketplace}] Navigation error attempt {attempt+1}: {exc}")
                if attempt == max_retries - 1:
                    await self._save_debug_snapshot(url, f"nav_exc_{attempt}")
                    from app.intelligence.selector_registry import record_selector
                    await record_selector(self.marketplace, "stealth_profile", f"mobile={self.mobile}", success=False)
                    if hasattr(self, 'user_agent') and self.user_agent:
                        await record_selector(self.marketplace, "stealth_ua", self.user_agent, success=False)
                    raise exc
                    
                if "TimeoutError" in str(exc) or "403" in str(exc):
                    await self._mutate_context()

                wait = (2 ** attempt) * BACKOFF_BASE_DELAY + random.uniform(0, 5)
                logger.info(f"[{self.marketplace}] Retrying in {wait:.1f}s...")
                await asyncio.sleep(wait)

        return False

    async def _check_and_increment_mutation(self) -> None:
        self._mutation_count += 1
        if self._mutation_count > MUTATION_LIMIT:
            logger.error(f"[{self.marketplace}] Limit of {MUTATION_LIMIT} mutations exceeded! Aborting.")
            raise Exception(f"[{self.marketplace}] Mutation limit exceeded")

    async def _mutate_context(self) -> None:
        await self._check_and_increment_mutation()
        storage_path = self._get_storage_path()
        if os.path.exists(storage_path):
            try: os.remove(storage_path)
            except: pass
            
        from app.intelligence.selector_registry import record_selector, ranked_selectors
        await record_selector(self.marketplace, "stealth_profile", f"mobile={self.mobile}", success=False)
        if hasattr(self, 'user_agent') and self.user_agent:
            await record_selector(self.marketplace, "stealth_ua", self.user_agent, success=False)
        
        if self.context:
            await self.context.close()
            
        if self.browser_type == "firefox":
            self.mobile = False
        else:
            self.mobile = not self.mobile
            
        ua_list = self._get_mobile_ua_list() if self.mobile else self._get_ua_list()
        best_uas = await ranked_selectors(self.marketplace, "stealth_ua", ua_list)
        if hasattr(self, 'user_agent') and self.user_agent == best_uas[0] and len(best_uas) > 1:
            self.user_agent = best_uas[1]
        else:
            self.user_agent = best_uas[0]
            
        await self._init_context()
        await self._apply_stealth_scripts()
        logger.info(f"[{self.marketplace}] Mutated fingerprint (Self-Healing)")

    async def try_selectors(self, selectors: list[str], purpose: str, timeout: int = 8000) -> tuple[str | None, str | None]:
        from app.intelligence.selector_registry import record_selector, ranked_selectors
        ordered = await ranked_selectors(self.marketplace, purpose, selectors)

        for selector in ordered:
            try:
                el = await self.page.wait_for_selector(selector, timeout=timeout)
                if el:
                    text = await el.inner_text()
                    if text and text.strip():
                        await record_selector(self.marketplace, purpose, selector, success=True)
                        logger.debug(f"[{self.marketplace}] Selector '{selector}' → '{text[:60]}'")
                        return text.strip(), selector
            except Exception:
                pass
            if getattr(self, "_last_navigation_successful", False):
                await record_selector(self.marketplace, purpose, selector, success=False)

        return None, None

    def parse_numeric_text(self, text: str) -> int:
        if not text:
            return 0
        text = text.lower()
        numbers = re.findall(r"[\d\.]+", text)
        if not numbers:
            return 0
        clean = [int(n.replace(".", "")) for n in numbers if len(n) <= 10]
        return max(clean) if clean else 0

    def parse_price_text(self, text: str) -> float:
        """Safely extracts numeric price value from DOM price string (e.g. '$19.990' -> 19990.0)."""
        if not text:
            return 0.0
        try:
            text_str = str(text).strip()
            if ("%" in text_str or "off" in text_str.lower()) and "$" not in text_str:
                return 0.0
            
            # 1. Standard Chilean CLP dot-formatted prices (e.g. 28.990, 25.990, 1.399.912)
            # Matches valid dot groups even if concatenated with trailing digits (e.g. 13.99012 -> 13.990)
            clp_matches = re.findall(r"\b\d{1,3}(?:\.\d{3})+\b|\d{1,3}\.\d{3}", text_str)
            if clp_matches:
                vals = [float(f.replace(".", "")) for f in clp_matches if 1000.0 <= float(f.replace(".", "")) <= 5000000.0]
                if vals:
                    return max(vals)

            # 2. Fallback for unformatted numbers
            text_clean = text_str.replace("$", "").replace("CLP", "").strip()
            if re.match(r"^\(\d+\)$", text_clean):
                return 0.0

            numbers = re.findall(r"[\d\.]+", text_clean)
            if not numbers:
                return 0.0
            clean_nums = []
            for n in numbers:
                # If digits are concatenated without dot (e.g. 699906 or 99906), check if trimming last digit gives valid round price
                raw = n.replace(".", "")
                if len(raw) >= 5 and raw.endswith(("6", "12", "24", "18")):
                    for trim_len in [1, 2]:
                        trimmed = raw[:-trim_len]
                        if len(trimmed) >= 4 and (trimmed.endswith("000") or trimmed.endswith("990") or trimmed.endswith("900") or trimmed.endswith("500")):
                            raw = trimmed
                            break
                val = float(raw)
                if 1000.0 <= val <= 5000000.0:
                    clean_nums.append(val)
            return max(clean_nums) if clean_nums else 0.0
        except Exception:
            return 0.0

    def is_likely_price(self, text: str, value: int) -> bool:
        text_clean = text.strip()
        if "$" in text_clean or "%" in text_clean:
            return True
        if re.search(r'\d+\.\d{3}', text_clean):
            return True
        if value >= 5000 and value % 990 == 0:
            return True
        if value >= 8000 and len(text_clean) < 20:
            return True
        if value in [2024, 2025, 2026] and "result" not in text_clean.lower() and "product" not in text_clean.lower() and "encontrad" not in text_clean.lower():
            return True
        return False

    async def get_count_from_title(self) -> int:
        try:
            title = await self.page.title()
            title_lower = title.lower()
            if "result" not in title_lower and "product" not in title_lower and "encontrad" not in title_lower:
                return 0
            
            count = self.parse_numeric_text(title)
            if self.is_likely_price(title, count):
                return 0
            return count
        except Exception as exc:
            return 0

    async def _save_debug_snapshot(self, url: str, label: str) -> None:
        import time
        folder = "debug_screenshots"
        os.makedirs(folder, exist_ok=True)
        domain = url.split("/")[2] if len(url.split("/")) > 2 else "unknown"
        path = f"{folder}/{domain}_{label}_{int(time.time())}.png"
        
        try:
            await asyncio.wait_for(self.page.screenshot(path=path), timeout=3.0)
            logger.info(f"[{self.marketplace}] Debug snapshot → {path}")
        except Exception as e:
            logger.debug(f"[{self.marketplace}] CDP snapshot failed, fallback to Pillow. {e}")
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                img.save(path)
            except Exception:
                pass

        try:
            files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".png")]
            if len(files) > 100:
                files.sort(key=os.path.getmtime)
                to_remove = files[:-100]
                for f in to_remove:
                    try: os.remove(f)
                    except: pass
        except Exception:
            pass

    async def take_screenshot(self, name: str) -> None:
        await self._save_debug_snapshot("", name)

    def _get_ua_list(self) -> list[str]:
        if self.browser_type == "firefox":
            return [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
            ]
        return [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ]

    def _get_mobile_ua_list(self) -> list[str]:
        return [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 14; Pixel 8 Build/UD1A.230805.019) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.113 Mobile Safari/537.36",
        ]

    def _sanitize_cookies(self, cookies: list) -> list:
        cleaned = []
        for c in cookies:
            if not isinstance(c, dict): continue
            c_copy = dict(c)
            
            # Map Cookie Manager 'expirationDate' -> Playwright 'expires'
            if "expirationDate" in c_copy:
                c_copy["expires"] = c_copy.pop("expirationDate")
                
            # Remove extension-only metadata
            for key in ["storeId", "hostOnly", "session"]:
                c_copy.pop(key, None)
                
            # Fix sameSite
            if "sameSite" in c_copy:
                val = str(c_copy["sameSite"]).strip().lower()
                if val in ["no_restriction", "none"]:
                    c_copy["sameSite"] = "None"
                elif val in ["strict"]:
                    c_copy["sameSite"] = "Strict"
                elif val in ["lax"]:
                    c_copy["sameSite"] = "Lax"
                else:
                    del c_copy["sameSite"]

            # Ensure domain is shared across all subdomains (.mercadolibre.cl)
            if "domain" in c_copy and "mercadolibre" in c_copy["domain"].lower():
                c_copy["domain"] = ".mercadolibre.cl"

            # FIX ML-2 (14-Ago): NO filtrar cookies de autenticacion.
            # ML redirige a account-verification si la sesion no tiene orguserid/orgnickp/ftid.
            # El shield de colaboradores se detecta por URL, no por cookies.

            if "name" in c_copy and "value" in c_copy:
                cleaned.append(c_copy)
        return cleaned

    async def stop(self) -> None:
        try:
            if getattr(self, 'page', None):
                await self.page.close()
            if getattr(self, 'context', None):
                await self.context.close()
            if getattr(self, '_obscura_anchor_context', None):
                await self._obscura_anchor_context.close()
            if getattr(self, 'browser', None):
                await self.browser.close()
            
            # Safe process termination for Windows
            if hasattr(self, "_cdp_process") and self._cdp_process:
                try:
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(self._cdp_process.pid)], capture_output=True)
                    else:
                        self._cdp_process.terminate()
                        self._cdp_process.kill()
                except Exception as e:
                    logger.debug(f"[{self.marketplace}] Process kill error: {e}")
                self._cdp_process = None
                
            self._cleanup_storage_files()
            logger.info(f"[{self.marketplace}] Browser stopped safely.")
        except Exception as exc:
            logger.warning(f"[{self.marketplace}] Error stopping browser: {exc}")
