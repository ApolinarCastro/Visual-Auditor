from app.scrapers.base_scraper import BaseScraper
from app.intelligence.trend_engine import record_custom_alert
from bs4 import BeautifulSoup
import logging
import os
import shutil
import re
import asyncio
import random
from pathlib import Path
import json
try:
    from anansi.parser.adaptive import AdaptiveParser, SelectorConfig
except ImportError:
    AdaptiveParser = None
    SelectorConfig = None

logger = logging.getLogger(__name__)

SESSION_FILE = Path(__file__).parent.parent.parent / "data" / "mercadolibre_session.json"

_COUNT_SELECTORS = [
    ".ui-search-search-result__quantity-results",
    "span[class*='quantity-results']",
    "div[class*='quantity-results']",
    "h1.ui-search-breadcrumb__title + span",
    ".ui-search-head__quantity-container",
    "span.ui-search-search-result__quantity-results",
]

_PRODUCT_SELECTORS_PAGE = ".ui-search-layout__item, .poly-card, div[class*='poly-card'], li.ui-search-layout__item"


class MercadoLibreScraper(BaseScraper):
    def __init__(self, headless=True):
        # Usamos chromium para emulación móvil completa
        # Activamos modo móvil para saltar el muro de login
        super().__init__(headless=headless, browser_type="chromium", marketplace="Mercado Libre", mobile=True)
        self._warmed = False
        self._session_cookies: list = []
        # FIX ML-5: tras fallback a catalogo publico, no recargar session.json
        # (las cookies con token de colaborador re-disparan el shield de ML).
        self._public_mode: bool = False
        SESSION_FILE.parent.mkdir(exist_ok=True)

    async def navigate(self, url: str, max_retries: int = 3) -> bool:
        await self._load_or_harvest_session()
        # Human Warming: Visit homepage first to acquire cookies/tokens smoothly
        if not self._warmed:
            try:
                logger.info(f"[{self.marketplace}] Initial warming: visiting homepage...")
                await super().navigate("https://www.mercadolibre.cl/")
                await asyncio.sleep(random.uniform(2, 3))
                
                # Accept cookies if modal pops up
                try:
                    cookie_btn = await self.page.query_selector("button[data-testid='action:understood-button']")
                    if cookie_btn: await cookie_btn.click()
                except: pass
                
                await self.page.evaluate("window.scrollBy(0, 300)")
                await asyncio.sleep(1)
                logger.info(f"[{self.marketplace}] Session warmed successfully.")
                self._warmed = True
            except Exception as e:
                logger.warning(f"[{self.marketplace}] Session warming failed: {e}")

        clean_url = self._get_clean_navigation_url(url)
        return await super().navigate(clean_url, max_retries=max_retries)

    def _get_clean_navigation_url(self, url: str) -> str:
        """
        Sanitize and normalize navigation URLs without corrupting official store or category corridor routes.
        Official store routes (tienda/<brand>) and container categories (_Container_) are preserved intact.
        """
        return url

    def _resolve_public_fallback_url(self, url: str) -> str:
        """Resolve public catalog listing URL preserving category subcorridor if present."""
        clean = url.rstrip("/").split("#")[0].split("?")[0]
        if "tienda/nicopoly" in clean.lower():
            parts = clean.split("tienda/nicopoly")
            subpath = parts[-1].strip("/")
            if subpath.startswith("listado/"):
                subpath = subpath[len("listado/"):].strip("/")
            if subpath:
                last_seg = subpath.split("/")[-1]
                return f"https://listado.mercadolibre.cl/{subpath}/{last_seg}_Tienda_nicopoly"
            return "https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly"
        return url

    async def _mutate_context(self) -> None:
        """Override base_scraper _mutate_context to inject session cookies and keep consistent headers."""
        await self._check_and_increment_mutation()

        # Clean up old context/pages safely
        try:
            if self.page:
                await self.page.close()
        except: pass
        
        try:
            if self.context:
                await self.context.close()
        except: pass

        # Recreate context (FIX ML-6b): desktop como la prueba que funciono
        # (invitado puro + viewport desktop 1440x900, 14-Ago 09:4x). El modo movil
        # forzado producia un fingerprint distinto que ML seguia bloqueando.
        self.mobile = False
        ua_list = self._get_ua_list()
        self.user_agent = ua_list[0] if ua_list else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

        try:
            await self.stop()
            await self.start()
            return
        except Exception:
            await self.start()
            return

        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['es-CL', 'es', 'en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        """)

        await self._apply_stealth_scripts()
        self.page = await self.context.new_page()

        # Apply playwright-stealth
        try:
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(self.page)
        except ImportError:
            pass

        if self._session_cookies:
            try:
                sanitized = self._sanitize_cookies(self._session_cookies)
                await self.page.context.add_cookies(sanitized)
                logger.info(f"[Mercado Libre] Re-injected {len(sanitized)} harvested cookies into mutated context")
            except Exception as e:
                logger.warning(f"[Mercado Libre] Failed to re-inject cookies: {e}")

    async def _harvest_session(self) -> bool:
        """
        Navigate to Mercado Libre homepage to pass captcha/challenge and harvest cookies.
        """
        logger.info("[Mercado Libre] Mutating context and harvesting fresh session cookies from homepage...")
        try:
            await self._mutate_context()

            await self.page.goto("https://www.mercadolibre.cl/", wait_until="commit", timeout=60000)
            await self.page.wait_for_timeout(random.randint(4000, 7000))

            # Simulate soft human mouse moves and scrolls on the homepage to warm session
            await self.page.mouse.move(random.randint(100, 500), random.randint(100, 400))
            await self.page.mouse.wheel(0, random.randint(100, 400))
            await self.page.wait_for_timeout(3000)

            # Check if we're through
            title = await self.page.title()
            body_snippet = await self.page.evaluate("document.body?.innerText?.slice(0, 300) || ''")
            
            # Detect blocked or login walls
            login_indicators = ["negative_traffic", "captcha", "/login", "/jwz/", "account-verification"]
            content_indicators = ["para continuar, ingresa a tu cuenta", "suspicious-traffic-frontend"]
            is_blocked = (
                any(ind in self.page.url.lower() for ind in login_indicators)
                or any(ind in body_snippet.lower() for ind in content_indicators)
                or "Just a moment" in title
                or "Cloudflare" in title
            )

            if not is_blocked:
                # Save cookies in memory without overwriting user's authenticated SESSION_FILE
                harvested = await self.page.context.cookies()
                logger.info(f"[Mercado Libre] Session harvested — {len(harvested)} cookies active in memory")
                if not SESSION_FILE.exists() or len(SESSION_FILE.read_text().strip()) < 50:
                    self._session_cookies = harvested
                    SESSION_FILE.write_text(json.dumps(self._session_cookies, ensure_ascii=False))
                return True
            else:
                logger.error("[Mercado Libre] Failed to pass challenge/login wall on homepage")
                return False
        except Exception as e:
            logger.error(f"[Mercado Libre] Session harvest error: {e}")
            return False

    async def _load_or_harvest_session(self) -> bool:
        """Cargar sesion: PRIORIDAD 1 = cookies frescas del perfil persistente
        (ya vienen en el contexto de launch_persistent_context; el usuario resolvio
        el CAPTCHA ahi una vez). PRIORIDAD 2 = session.json SOLO si el contexto no
        tiene cookies de mercadolibre (respaldo para sesiones nuevas).

        FIX ML-4 (14-Ago): NO sobrescribir las cookies frescas del perfil con las
        viejas de session.json (11-Ago) — esas quedaron marcadas por Akamai y son
        las que provocan el muro de login/CAPTCHA aunque el perfil este desbloqueado.
        """
        # 1) Cookies ya en memoria (del perfil persistente): usarlas tal cual.
        if self._session_cookies:
            try:
                sanitized = self._sanitize_cookies(self._session_cookies)
                await self.page.context.add_cookies(sanitized)
                logger.info(f"[Mercado Libre] Loaded {len(sanitized)} cookies from memory")
                return True
            except Exception as e:
                logger.warning(f"[Mercado Libre] Failed to load cookies from memory: {e}")

        # 2) Verificar si el contexto (perfil persistente) ya tiene cookies de ML.
        #    Si las tiene, confiar en ellas: NO inyectar session.json viejo.
        try:
            ctx_cookies = await self.page.context.cookies()
            ml_names = [c.get("name") for c in ctx_cookies if "mercadolibre" in str(c.get("domain", ""))]
            if ml_names:
                logger.info(f"[Mercado Libre] Usando {len(ml_names)} cookies frescas del perfil persistente (FIX ML-4)")
                self._session_cookies = self._sanitize_cookies(ctx_cookies)
                return True
        except Exception as e:
            logger.debug(f"[Mercado Libre] ctx cookies check failed: {e}")

        # 3) Respaldo: session.json (FIX ML-9, 14-Ago): las cookies fueron renovadas
        #    por el usuario (orguserid/orgnickp/ssid frescas) y verificadas en navegacion
        #    real: 192 productos, sin bloqueo. Solo se omiten en modo publico (ML-5)
        #    para evitar el loop del shield de colaboradores.
        if self._public_mode:
            logger.info("[Mercado Libre] Modo publico activo: NO recargando session.json (FIX ML-5)")
            return True
        if SESSION_FILE.exists():
            try:
                cookies = json.loads(SESSION_FILE.read_text())
                if cookies and len(cookies) > 0:
                    sanitized = self._sanitize_cookies(cookies)
                    await self.page.context.add_cookies(sanitized)
                    self._session_cookies = sanitized
                    logger.info(f"[Mercado Libre] Loaded {len(sanitized)} saved session cookies (renovadas 14-Ago)")
                    return True
            except Exception as e:
                logger.warning(f"[Mercado Libre] Failed to load saved session: {e}")

        # FIX ML-2: siempre intentar cargar/harvestear sesion (nunca navegar sin cookies)
        return await self._harvest_session()

    async def _harvest_tu_chrome_cookies(self) -> list:
        """Automatically harvest cookies from user's 'Tu Chrome' (Default) profile if available."""
        src_user_data = os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data")
        default_dir = os.path.join(src_user_data, "Default")
        if not os.path.exists(default_dir):
            return []
            
        try:
            import shutil
            from playwright.async_api import async_playwright
            dst_user_data = os.path.abspath("data/tu_chrome_profile_copy")
            os.makedirs(dst_user_data, exist_ok=True)
            for item in ["Local State", "Default"]:
                src = os.path.join(src_user_data, item)
                dst = os.path.join(dst_user_data, item)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                elif os.path.isdir(src):
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("Singleton*", "LOCK", "*lock*", "Cache*", "Code Cache*"), dirs_exist_ok=True)
                    
            chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            async with async_playwright() as p:
                context = await p.chromium.launch_persistent_context(
                    dst_user_data,
                    executable_path=chrome_exe if os.path.exists(chrome_exe) else None,
                    headless=True,
                    args=["--profile-directory=Default", "--no-sandbox"]
                )
                cookies = await context.cookies()
                await context.close()
                if cookies:
                    sanitized = self._sanitize_cookies(cookies)
                    SESSION_FILE.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
                    logger.info(f"[Mercado Libre] Automatically harvested {len(sanitized)} cookies from 'Tu Chrome' profile")
                    return sanitized
        except Exception as ex:
            logger.debug(f"[Mercado Libre] Failed auto-harvest from 'Tu Chrome': {ex}")
        return []

    async def get_total_count(self, url: str) -> int:
        success = await self.navigate(url)
        if not success:
            return 0

        # Validación de Bloqueo por URL o Contenido (Rule 4 Compliance)
        current_url = self.page.url
        page_content = (await self.page.content()).lower()
        
        # Specific check for collaborator shield redirect: fall back to public store search listing
        if "collaborators/shield" in current_url.lower() or "vendedores.mercadolibre.cl" in current_url.lower():
            logger.warning("[Mercado Libre] Collaborator session token detected. Automatically falling back to public catalog listing...")
            self._session_cookies = []
            self._warmed = False
            self._public_mode = True  # FIX ML-5: no recargar session.json con token de colaborador
            try:
                await self.context.clear_cookies()
            except Exception:
                pass
            fallback_url = self._resolve_public_fallback_url(url)
            logger.info(f"[Mercado Libre] Fallback a catalogo publico en modo publico: {fallback_url}")
            return await self.get_total_count(fallback_url)

        # Muro de login por texto o redirección de colaboradores
        login_indicators = ["negative_traffic", "captcha", "/login", "/jwz/", "account-verification", "collaborators/shield", "vendedores.mercadolibre.cl"]
        content_indicators = ["para continuar, ingresa a tu cuenta", "suspicious-traffic-frontend", "solo la persona que es dueña"]
        if any(ind in current_url.lower() for ind in login_indicators) or any(ind in page_content for ind in content_indicators):
            msg = "[Mercado Libre] Login wall or CAPTCHA detected. Applying automatic fallback..."
            logger.warning(msg)
            self._session_cookies = []
            try:
                await self.context.clear_cookies()
            except:
                pass
            fallback_url = self._resolve_public_fallback_url(url)
            if fallback_url != url:
                logger.info(f"[Mercado Libre] Auto-fallback for store catalog: {fallback_url}")
                return await self.get_total_count(fallback_url)
            
            await self._save_debug_snapshot(url, "meli_login_wall")
            await self._mutate_context() # Self-Healing mutation before retry
            raise Exception("Mercado Libre bloqueó el acceso (Muro de Login detectado)")

        # Intentar aceptar cookies si el banner está presente
        try:
            cookie_btn = await self.page.query_selector("button[data-testid='action:understood-button'], .andes-button--cookie")
            if cookie_btn:
                await cookie_btn.click()
                await asyncio.sleep(1)
        except:
            pass

        # Pequeña espera para renderizado de contadores dinámicos
        await asyncio.sleep(random.uniform(0.8, 1.2))

        # 1. Verificar primero si el texto visible indica inequívocamente que no hay resultados de la tienda oficial
        # o que la búsqueda no arrojó resultados exactos (incluso si Mercado Libre muestra sugerencias abajo).
        body_text = (await self.page.evaluate("document.body?.innerText || ''")).lower()
        
        strict_empty_indicators = [
            "no encontramos publicaciones de la tienda oficial",
            "no encontramos publicaciones que coincidan con tu búsqueda",
            "no hay publicaciones que coincidan con tu búsqueda",
            "oops! no encontramos lo que buscas"
        ]
        for ind in strict_empty_indicators:
            if ind in body_text:
                logger.info(f"[{self.marketplace}] Búsqueda vacía (marca o canal) detectada por texto visible: '{ind}'. Retornando 0.")
                return 0

        # 2. Si no hay productos renderizados en absoluto, aplicar los indicadores generales en el texto visible
        has_products = await self.page.query_selector(_PRODUCT_SELECTORS_PAGE)
        if not has_products:
            empty_indicators = [
                "no encontramos publicaciones",
                "no encontramos resultados", 
                "no hay publicaciones", 
                "no hay resultados",
                "agotado"
            ]
            for ind in empty_indicators:
                if ind in body_text:
                    logger.info(f"[{self.marketplace}] Búsqueda vacía/agotada detectada por indicador general visible: '{ind}'. Retornando 0.")
                    return 0

        # Try ML-ranked selectors (self-learning)
        text, winner = await self.try_selectors(
            _COUNT_SELECTORS, purpose="total_count", timeout=12000
        )
        if text:
            count = self.parse_numeric_text(text)
            if count > 0:
                return count

        # Last resort: scan all spans for "resultados"
        try:
            spans = await self.page.query_selector_all("span, h1, div")
            for span in spans:
                t = await span.inner_text()
                if "resultados" in t.lower():
                    count = self.parse_numeric_text(t)
                    if count > 0 and not self.is_likely_price(t, count):
                        return count
        except Exception:
            pass

        count = await self.get_count_from_title()
        if count == 0:
            logger.warning(f"[{self.marketplace}] Could not determine count for {url} (found 0). Snapshot disabled to prevent disk saturation.")
        return count

    async def scrape_autonomous_category(self, url: str) -> dict:
        await self.navigate(url)
        products = []
        current_page = 1
        anansi_parser = AdaptiveParser() if AdaptiveParser is not None else None
        
        stop_reason = "EXHAUSTION"
        failure_type = None

        while True:
            html = await self.page.content()
            html_lower = html.lower()
            login_indicators = ["negative_traffic", "captcha", "/login", "/jwz/", "account-verification", "collaborators/shield", "vendedores.mercadolibre.cl"]
            content_indicators = ["para continuar, ingresa a tu cuenta", "suspicious-traffic-frontend", "solo la persona que es dueña"]
            
            # Detección de bloqueo durante paginación
            if any(ind in self.page.url.lower() for ind in login_indicators) or any(ind in html_lower for ind in content_indicators):
                msg = f"[Mercado Libre] Blocked during pagination on Page {current_page}."
                logger.warning(msg)
                stop_reason = "BLOCKED"
                break
                
            page_products = await self._extract_products_from_html(html, current_page, len(products), anansi_parser)
            
            if not page_products:
                logger.warning(f"[{self.marketplace}] No se encontraron productos en página {current_page}")
                if current_page == 1:
                    stop_reason = "EXTRACTOR_FAILURE"
                break
                
            products.extend(page_products)
            logger.info(f"[{self.marketplace}] Scraped {len(products)} products (Page {current_page})...")

            if not await self._has_next_page():
                break

            await self._go_to_next_page()
            current_page += 1

        return {
            "products": products,
            "pages_traversed": current_page if stop_reason != "EXTRACTOR_FAILURE" else 0,
            "stop_reason": stop_reason,
            "failure_type": failure_type
        }

    async def scrape_top_240(self, url: str) -> list[dict]:
        await self.navigate(url)
        products = []
        current_page = 1
        anansi_parser = AdaptiveParser() if AdaptiveParser is not None else None

        while len(products) < 240:
            html = await self.page.content()
            html_lower = html.lower()
            login_indicators = ["negative_traffic", "captcha", "/login", "/jwz/", "account-verification", "collaborators/shield", "vendedores.mercadolibre.cl"]
            content_indicators = ["para continuar, ingresa a tu cuenta", "suspicious-traffic-frontend", "solo la persona que es dueña"]
            
            # Detección de bloqueo durante paginación
            if any(ind in self.page.url.lower() for ind in login_indicators) or any(ind in html_lower for ind in content_indicators):
                msg = f"[Mercado Libre] Blocked during pagination on Page {current_page}. Session cookies may be expired. Run 'scratch/harvest_mercadolibre_session.py'."
                logger.warning(msg)
                try:
                    await record_custom_alert(
                        marketplace="Mercado Libre",
                        category="System",
                        alert_type="Session Blocked",
                        message=msg
                    )
                except Exception as alert_err:
                    logger.warning(f"[Mercado Libre] Failed to record custom alert: {alert_err}")
                break
            page_products = await self._extract_products_from_html(html, current_page, len(products), anansi_parser)
            
            if not page_products:
                logger.warning(f"[{self.marketplace}] No se encontraron productos en página {current_page}")
                break
                
            products.extend(page_products)
            logger.info(f"[{self.marketplace}] Scraped {len(products)}/240 products...")

            if len(products) >= 240 or not await self._has_next_page():
                break

            await self._go_to_next_page()
            current_page += 1

        return products[:240]

    async def _extract_products_from_html(self, html: str, page: int, current_total: int, anansi_parser) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        main_container = soup.select_one("section.ui-search-results, ol.ui-search-layout, .ui-search-layout")
        if main_container:
            # FIX ML-13: usar SOLO .ui-search-layout__item (el li), no ".poly-card"
            # en paralelo: el <div class=poly-card> esta ANIDADO dentro del li y
            # matchear ambos duplicaba cada producto (96 items en vez de 48).
            raw_items = main_container.select(".ui-search-layout__item")
            if not raw_items:
                raw_items = main_container.select(".poly-card")
        else:
            raw_items = soup.select(_PRODUCT_SELECTORS_PAGE)

        # Filter out items that belong to recommendation carousels or bottom ads
        # Exception: items inside official store showcase (ui-ms-section-eshops, home--seller, or ui-ms-polycard-carousel)
        items = []
        for item in raw_items:
            parents = [p.get("class", []) for p in item.parents if hasattr(p, "get") and p.get("class")]
            flat_classes = " ".join([" ".join(c) for c in parents if isinstance(c, list)]).lower()
            is_store_showcase = "ui-ms-section-eshops" in flat_classes or "home--seller" in flat_classes or "ui-ms-polycard-carousel" in flat_classes
            if not is_store_showcase:
                if "recommendation" in flat_classes or "carousel" in flat_classes or "promoted-items" in flat_classes:
                    continue
            items.append(item)

        extracted = []

        for idx, item in enumerate(items):
            title_el = (
                item.select_one(".poly-component__title") or
                item.select_one(".ui-search-item__title") or
                item.select_one("h2.poly-box") or
                item.select_one("h2")
            )
            vendor_el = (
                item.select_one(".poly-component__seller") or
                item.select_one(".ui-search-official-store-label") or
                item.select_one(".poly-seller__link")
            )
            price_el = (
                item.select_one(".poly-component__price") or
                item.select_one(".poly-price__current") or
                item.select_one(".andes-money-amount") or
                item.select_one(".andes-money-amount__fraction")
            )

            title = title_el.get_text(strip=True) if title_el else ""
            vendor = vendor_el.get_text(strip=True) if vendor_el else ""
            
            # Store context is surface evidence, not a product brand assertion.
            surface_url = self.page.url if self.page else ""
            brand_surface = surface_url if re.search(r"/tienda/[^/?#]+", surface_url) else None
            
            # --- CAPA DE RESCATE ANANSI ---
            if (not title or not vendor) and anansi_parser is not None:
                item_html = str(item)
                try:
                    rescate = await anansi_parser.extract(item_html, {
                        "rescued_title": SelectorConfig(".title", expected_pattern=r"\w+")
                    }, url="https://www.mercadolibre.cl")
                    
                    if not title and rescate.get("rescued_title"):
                        title = rescate.get("rescued_title")
                        logger.debug(f"[Anansi MeLi] Título rescatado: {title}")
                        
                except Exception as e:
                    logger.warning(f"Fallo en Anansi fallback MeLi: {e}")
            # --- FIN CAPA DE RESCATE ---

            # Extract price and MLC item ID
            price = 0.0
            marketplace_sku = ""
            try:
                if price_el:
                    import copy
                    price_clone = copy.copy(price_el)
                    # Remove installment noise and cents
                    for noise in price_clone.select(".poly-price__installments, .price-tag-cents, .ui-search-price__second-line, [class*='installment']"):
                        noise.decompose()
                    price = self.parse_price_text(price_clone.get_text(separator=" ", strip=True))
                
                link_el = item.select_one("a[href*='articulo.mercadolibre.cl'], a[href*='MLC']")
                product_url = ""
                if link_el and link_el.get("href"):
                    href = link_el.get("href")
                    product_url = href
                    mlc_match = re.search(r"MLC-?(\d+)", href, re.IGNORECASE)
                    if mlc_match:
                        marketplace_sku = f"MLC{mlc_match.group(1)}"
            except Exception:
                pass

            if title:
                extracted.append({
                    "title": title,
                    "vendor": vendor,
                    "brand_surface_url": brand_surface,
                    "price": price,
                    "marketplace_sku": marketplace_sku,
                    "url": product_url if 'product_url' in locals() else "",
                    "page": page,
                    "position_local": idx + 1,
                    "position_absolute": current_total + idx + 1,
                })

        return extracted

    async def _has_next_page(self) -> bool:
        try:
            btn = await self.page.query_selector(".andes-pagination__button--next, [class*='pagination__next']")
            if btn:
                cls = await btn.get_attribute("class") or ""
                return "andes-pagination__button--disabled" not in cls
            return False
        except:
            return False

    async def _go_to_next_page(self):
        import random
        # FIX B (7-Ago): navegacion directa por URL con offset _Desde_N en vez de click.
        # El click en el boton 'siguiente' de ML falla con timeout 30s cuando el DOM
        # cambia o hay overlay -> el scraper re-extraia la misma pagina, generando
        # duplicados y captura incompleta (ej: ML/Abrigos 120 -> 56 productos).
        try:
            url = self.page.url
            # Quitar fragmento y separar query string (si existe)
            url_no_frag = url.split("#")[0]
            if "?" in url_no_frag:
                path_part, query_part = url_no_frag.split("?", 1)
            else:
                path_part, query_part = url_no_frag, None
            m = re.search(r'_Desde_(\d+)', path_part)
            offset = int(m.group(1)) if m else 1
            # ML muestra ~48 items por pagina; siguiente offset = actual + 48
            new_offset = offset + 48
            # FIX ML-12: _Desde_N debe ir como SEGMENTO DE PATH (ej: ..._NoIndex_True_Desde_49).
            # Como query param (?_Desde_49) ML lo ignora y recicla la pagina 1,
            # limitando la captura a 48 SKUs unicos en vez de los N resultados reales.
            if m:
                new_path = path_part.replace(f"_Desde_{offset}", f"_Desde_{new_offset}")
            else:
                new_path = f"{path_part}_Desde_{new_offset}"
            new_url = new_path
            if query_part:
                new_url += f"?{query_part}"
            logger.info(f"[{self.marketplace}] Paginando via URL: {new_url[:120]}")
            await self.page.goto(new_url, wait_until="domcontentloaded", timeout=30000)
            # FIX ML-14: ML redirige la URL de paginacion (path _Desde_N -> reordena
            # a ..._Desde_N_NoIndex_True) y renderiza los items via JS. El wait de
            # ~1s no alcanzaba y la extraccion devolvia 0 productos en pagina 2.
            try:
                await self.page.wait_for_selector(
                    "li.ui-search-layout__item, .poly-card", timeout=15000
                )
                await self.page.wait_for_timeout(random.randint(1500, 2500))
            except Exception:
                await self.page.wait_for_timeout(random.randint(2500, 3500))
        except Exception as e:
            logger.error(f"[{self.marketplace}] Error navegando a siguiente página: {e}")
