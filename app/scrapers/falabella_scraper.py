import asyncio
import logging
import re
from .base_scraper import BaseScraper
try:
    from anansi.parser.adaptive import AdaptiveParser, SelectorConfig
except ImportError:
    AdaptiveParser = None
    SelectorConfig = None

logger = logging.getLogger(__name__)

def detect_challenge_in_text(html: str, status: int = 200) -> tuple[bool, list[str]]:
    """Detects if the HTML content corresponds to a WAF/Cloudflare challenge."""
    html_lower = html.lower()
    markers = []
    is_challenge = False

    if status == 403 or "403" in html_lower:
        markers.append("status_403")
        is_challenge = True
    if "cloudflare" in html_lower:
        markers.append("cloudflare")
        is_challenge = True
    if "just a moment" in html_lower:
        markers.append("just_a_moment")
        is_challenge = True
    if "su acceso ha sido bloqueado" in html_lower or "access has been blocked" in html_lower:
        markers.append("access_blocked")
        is_challenge = True

    return is_challenge, markers

def detect_commercial_content(html: str) -> tuple[bool, list[str]]:
    """Detects if the HTML content corresponds to a legitimate commercial response."""
    html_lower = html.lower()
    markers = []
    is_comm = False

    if "__next_data__" in html_lower:
        markers.append("__next_data__")
        is_comm = True
    if "pod-group" in html_lower or "class=\"pod\"" in html_lower:
        markers.append("pod")
        is_comm = True

    return is_comm, markers

class FalabellaScraper(BaseScraper):
    def __init__(self, headless=True):
        super().__init__(headless=headless, browser_type="chromium", marketplace="Falabella")

    async def navigate(self, url: str, max_retries: int = 1) -> bool:
        """
        Navigates to Falabella surface using the certified HTTP SSR acquisition strategy
        (F1_HTTP_RESPONSE_NORMAL). Populates page DOM with server-rendered HTML.
        Falls back to Playwright browser navigation if HTTP SSR is unavailable.
        """
        if not self.page or self.page.is_closed() or not self.context:
            await self.start()

        # 1. Direct HTTP SSR acquisition (certified strategy F1_HTTP_RESPONSE_NORMAL)
        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
                }
            )
            loop = asyncio.get_event_loop()
            def _fetch():
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status == 200:
                        return resp.read().decode("utf-8", errors="replace")
                return None

            html = await loop.run_in_executor(None, _fetch)
            if html and len(html) > 5000 and "su acceso ha sido bloqueado" not in html.lower():
                await self.page.set_content(html, wait_until="domcontentloaded")
                self._last_navigation_successful = True
                logger.info(f"[Falabella] HTTP SSR acquisition succeeded ({len(html)} bytes). Page DOM populated.")
                return True
        except Exception as fe:
            logger.debug(f"[Falabella] HTTP SSR acquisition attempt failed: {fe}")

        # 2. Browser navigation fallback
        browser_ok = False
        try:
            browser_ok = await super().navigate(url, max_retries=1)
        except Exception as e:
            logger.debug(f"[Falabella] super().navigate exception: {e}")

        # Detect challenge state
        is_challenge = False
        if self.page and not self.page.is_closed():
            try:
                title = (await self.page.title()).lower()
                content_snip = (await self.page.content())[:2000].lower()
                is_challenge, _ = detect_challenge_in_text(title + " " + content_snip)
            except Exception:
                is_challenge = True

        if browser_ok and not is_challenge:
            return True

        return False

    async def get_total_count(self, url: str) -> int:
        await self.navigate(url)

        # Extended wait for Falabella's dynamic React counter
        selectors = [
            '#testId-ProductLandingContainer-totalResults',
            '#testId-SearchCount',
            '#search_numResults',
            '.search-results-count',
            '[class*="results-count"]',
            '[class*="total-results"]',
            'div[id*="SearchCount"]',
            'span[class*="results"]',
            'div[class*="results"]'
        ]

        # Wait specifically for the counter to be visible and have text
        for _ in range(3): # 3 attempts of 5 seconds
            for selector in selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=5000, state="visible")
                    if el:
                        text = await el.inner_text()
                        count = self.parse_numeric_text(text)
                        if count > 0 and not self.is_likely_price(text, count):
                            logger.info(f"Falabella count found: {count} using {selector}")
                            return count
                except:
                    continue
            # Smooth scroll to trigger lazy loading if needed
            await self.page.evaluate("window.scrollBy(0, 300)")
            await asyncio.sleep(2)

        return 0

    async def scrape_autonomous_category(self, url: str) -> dict:
        """Scrape autonomous category handling block detection and structured data."""
        products = []
        page_num = 1
        anansi_parser = AdaptiveParser() if AdaptiveParser else None
        product_selector = ".pod, .product-grid-item, div[id*='testId-pod']"
        seen_keys = set()
        stop_reason = "EXHAUSTION"
        failure_type = None

        while True:
            page_url = url if page_num == 1 else f"{url}{'&' if '?' in url else '?'}page={page_num}"
            try:
                ok = await self.navigate(page_url)
                if not ok:
                    if page_num == 1:
                        stop_reason = "BLOCKED"
                        failure_type = "Navigation Failure"
                    break
            except Exception as e:
                if page_num == 1:
                    stop_reason = "BLOCKED"
                    failure_type = "Navigation Error"
                break

            html = await self.page.content()
            title = await self.page.title()
            html_lower = html.lower()
            title_lower = title.lower()

            if "attention required! | cloudflare" in html_lower or "just a moment..." in html_lower or "access denied" in title_lower or "403 forbidden" in title_lower or "error 403" in title_lower or "blocked" in title_lower:
                if page_num == 1:
                    stop_reason = "BLOCKED"
                    failure_type = "WAF Block"
                break

            items_added = 0

            # 1. Primary: Extract structured products from __NEXT_DATA__ SSR payload
            next_data_el = await self.page.query_selector("#__NEXT_DATA__")
            if next_data_el:
                try:
                    import json
                    raw_json = await next_data_el.inner_text()
                    data = json.loads(raw_json)
                    results = data.get("props", {}).get("pageProps", {}).get("results", [])
                    for p in results:
                        p_title = (p.get("displayName") or p.get("title") or "").strip()
                        vendor = (p.get("brandName") or p.get("brand") or p.get("sellerName") or "").strip()
                        sku = str(p.get("skuId") or p.get("productId") or "")
                        p_url = p.get("url") or ""

                        price = 0.0
                        prices = p.get("prices") or []
                        if isinstance(prices, list) and len(prices) > 0:
                            p_list = prices[0].get("price") or []
                            if isinstance(p_list, list) and len(p_list) > 0:
                                price = self.parse_price_text(str(p_list[0]))
                            elif isinstance(p_list, (int, float)):
                                price = float(p_list)

                        key = f"{sku}_{p_title}"
                        if (p_title or vendor) and key not in seen_keys:
                            seen_keys.add(key)
                            products.append({
                                "title": p_title,
                                "vendor": vendor,
                                "price": price,
                                "marketplace_sku": sku,
                                "url": p_url,
                                "position_absolute": len(products) + 1
                            })
                            items_added += 1
                except Exception as je:
                    logger.debug(f"[Falabella] Error extracting products from __NEXT_DATA__: {je}")

            # 2. Fallback: Query DOM selector pods
            if items_added == 0:
                # Scroll to trigger lazy loading
                for i in range(3):
                    await self.page.evaluate(f"window.scrollTo(0, {i * 1000})")
                    await asyncio.sleep(0.3)

                items = await self.page.query_selector_all(product_selector)
                for idx, item in enumerate(items):
                    brand = ""
                    p_title = ""
                    price = 0.0
                    marketplace_sku = ""

                    brand_el = await item.query_selector("b[class*='pod-brand']")
                    title_el = await item.query_selector("b[class*='pod-title']")
                    price_el = await item.query_selector("li.price-1")

                    if brand_el: brand = await brand_el.inner_text()
                    if title_el: p_title = await title_el.inner_text()
                    if price_el:
                        txt = await price_el.inner_text()
                        price = self.parse_price_text(txt)

                    link_el = await item.query_selector("a")
                    if link_el:
                        href = await link_el.get_attribute("href")
                        if href:
                            match = re.search(r'-(\d+)', href)
                            if match: marketplace_sku = match.group(1)

                    if brand or p_title:
                        key = f"{marketplace_sku}_{p_title}"
                        if key not in seen_keys:
                            seen_keys.add(key)
                            products.append({
                                "title": p_title.strip(),
                                "vendor": brand.strip(),
                                "price": price,
                                "marketplace_sku": marketplace_sku,
                                "position_absolute": len(products) + 1
                            })
                            items_added += 1

            if items_added == 0:
                if page_num == 1:
                    stop_reason = "EXTRACTOR_FAILURE"
                break

            page_num += 1
            if page_num > 2:
                break

        return {
            "products": products,
            "pages_traversed": page_num if stop_reason != "EXTRACTOR_FAILURE" else 0,
            "stop_reason": stop_reason,
            "failure_type": failure_type
        }

    async def scrape_top_240(self, url: str) -> list:
        products = []
        anansi_parser = AdaptiveParser() if AdaptiveParser else None
        product_selector = ".pod, .product-grid-item, div[id*='testId-pod']"
        seen_keys = set()

        is_brand_search = "brandname=" in url.lower() or "brand=" in url.lower() or "nicopoly" in url.lower()
        max_pages = 3 if is_brand_search else 1
        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                page_url = url
            else:
                sep = "&" if "?" in url else "?"
                page_url = f"{url}{sep}page={page_num}"

            logger.info(f"[Falabella] Paginando a página {page_num}: {page_url}")
            await self.navigate(page_url)

            # Scroll to trigger lazy loading
            for i in range(6):
                await self.page.evaluate(f"window.scrollTo(0, {i * 1000})")
                await asyncio.sleep(0.5)

            items = await self.page.query_selector_all(product_selector)
            if not items:
                logger.info(f"[Falabella] No se encontraron pods en la página {page_num}. Finalizando paginación.")
                break

            items_added = 0
            for i, item in enumerate(items):
                if len(products) >= 240:
                    break

                try:
                    brand_el = await item.query_selector(".pod-brand, b.pod-title, [id^='testId-pod-display-brand']")
                    title_el = await item.query_selector(".pod-subTitle, [id^='testId-pod-displaySubTitle-'], [id^='testId-pod-display-name']")

                    brand = await brand_el.inner_text() if brand_el else ""
                    title = await title_el.inner_text() if title_el else ""

                    brand = brand.replace("Por ", "").replace("por ", "").strip()
                    title = title.strip()

                    if not brand or not title:
                        pod_text = await item.inner_text()
                        lines = [line.strip() for line in pod_text.split("\n") if line.strip()]
                        if len(lines) >= 2:
                            # Free text can help recover a title, never vendor identity.
                            if not title:
                                title = lines[1] if len(lines) > 1 else lines[0]

                    if (not brand or not title) and anansi_parser:
                        try:
                            item_html = await item.evaluate("el => el.outerHTML")
                            rescate = await anansi_parser.extract(item_html, {
                                "rescued_title": SelectorConfig(".title", expected_pattern=r"\w+")
                            }, url="https://www.falabella.com")
                            if not title and rescate.get("rescued_title"):
                                title = rescate.get("rescued_title")
                        except Exception:
                            pass

                    price = 0.0
                    marketplace_sku = ""
                    try:
                        price_el = await item.query_selector("[class*='price'], [class*='Price']")
                        if price_el:
                            price_text = await price_el.inner_text()
                            price = self.parse_price_text(price_text)

                        sku_attr = (
                            await item.get_attribute("data-sku-id") or
                            await item.get_attribute("data-pod-id") or
                            await item.get_attribute("data-key") or
                            await item.get_attribute("id") or ""
                        )
                        if sku_attr:
                            marketplace_sku = str(sku_attr).replace("testId-pod-display-", "").strip()
                        if not marketplace_sku:
                            link_el = await item.query_selector("a[href*='/product/'], a[href*='/falabella-cl/product/'], a[href]")
                            if link_el:
                                href = await link_el.get_attribute("href") or ""
                                sku_match = re.search(r"/product/(\d+)", href) or re.search(r"/(\d{6,15})(?:/|\?|$)", href)
                                if sku_match:
                                    marketplace_sku = sku_match.group(1)
                    except Exception:
                        pass

                    key = marketplace_sku if marketplace_sku else title.lower()
                    if key and key in seen_keys:
                        continue
                    if key:
                        seen_keys.add(key)

                    if title or brand:
                        products.append({
                            "position_absolute": len(products) + 1,
                            "title": title,
                            "vendor": brand,
                            "price": price,
                            "marketplace_sku": marketplace_sku,
                            "page": page_num,
                        })
                        items_added += 1
                except Exception as e:
                    logger.debug(f"Error parsing Falabella product {i+1}: {e}")

            logger.info(f"[Falabella] Página {page_num}: agregados {items_added} productos (Total acumulado: {len(products)})")
            if items_added == 0:
                logger.info(f"[Falabella] 0 productos nuevos en la página {page_num}. Finalizando paginación.")
                break

        return products
