from app.scrapers.base_scraper import BaseScraper
# pyrefly: ignore [missing-import]
from bs4 import BeautifulSoup
import logging
import re
import asyncio
try:
    from anansi.parser.adaptive import AdaptiveParser, SelectorConfig
except ImportError:
    AdaptiveParser = None
    SelectorConfig = None

logger = logging.getLogger(__name__)

class ParisScraper(BaseScraper):
    def __init__(self, headless=True):
        super().__init__(headless=headless, browser_type="chromium", marketplace="Paris")

    async def get_total_count(self, url: str) -> int:
        await self.navigate(url)  # uses full stealth+retry from BaseScraper
        selectors = [
            ".total-products",
            "span[class*='total-products']",
            "span:has-text('productos encontrados')",
            ".js-results-count",
            ".search-count"
        ]

        for selector in selectors:
            try:
                element = await self.page.wait_for_selector(selector, timeout=7000)
                if element:
                    text = await element.inner_text()
                    count = self.parse_numeric_text(text)
                    if count > 0 and not self.is_likely_price(text, count):
                        return count
            except:
                continue

        # Fallback to title
        return await self.get_count_from_title()

    async def scrape_autonomous_category(self, url: str) -> dict:
        await self.navigate(url)

        pages_traversed = 1
        consecutive_unchanged = 0
        last_count = 0

        # Click Mostrar más until exhaustion
        while True:
            items_count = await self.page.evaluate('''() => {
                return document.querySelectorAll('a[id^="product-"], div[id^="product-"], .product-item, [class*="ProductCard"]').length;
            }''')

            if items_count == last_count:
                consecutive_unchanged += 1
            else:
                consecutive_unchanged = 0
                last_count = items_count

            if consecutive_unchanged >= 3:
                break

            next_btn = await self.page.query_selector('button:has-text("Mostrar más")')
            if not next_btn:
                break

            await next_btn.click()
            await self.page.wait_for_timeout(4000)
            pages_traversed += 1

        # Extraer live prices
        live_prices = {}
        try:
            live_prices = await self.page.evaluate(r"""
                () => {
                    const result = {};
                    const cards = document.querySelectorAll(
                        'a[id^="product-"], div[id^="product-"], .product-item, [class*="ProductCard"]'
                    );
                    cards.forEach(card => {
                        const idAttr = card.id || card.getAttribute('data-product-id') || '';
                        const priceEl = card.querySelector(
                            '.price-text, .offer-price, .default-price, ' +
                            '[class*="price-text"], [class*="Price-text"], ' +
                            '[class*="ProductPrice"], [class*="product-price"], ' +
                            '[class*="offer"], [class*="Offer"], span[class*="price"]'
                        );
                        if (priceEl) {
                            const txt = priceEl.textContent.replace(/[\s\u00a0]/g, '');
                            const match = txt.match(/\$([0-9.]+)/);
                            if (match) {
                                const numStr = match[1].replace(/\./g, '');
                                const val = parseFloat(numStr);
                                if (!isNaN(val) && val >= 1000) {
                                    result[idAttr] = val;
                                }
                            }
                        }
                    });
                    return result;
                }
            """)
        except Exception as e:
            logger.warning(f"[Paris] Live price extraction failed: {e}")

        html = await self.page.content()
        anansi_parser = AdaptiveParser() if AdaptiveParser else None
        products = await self._extract_products_from_html(html, 0, anansi_parser, live_prices)

        return {
            "products": products,
            "pages_traversed": pages_traversed,
            "stop_reason": "EXHAUSTION",
            "failure_type": None
        }

    async def scrape_top_240(self, url: str) -> list[dict]:
        await self.navigate(url)
        products = []

        # Instanciamos el parser de Anansi si está disponible
        anansi_parser = AdaptiveParser() if AdaptiveParser else None

        while len(products) < 240:
            # --- Extracción de precios en VIVO desde el DOM con Playwright ---
            # Paris renderiza precios con JS; BS4 sobre HTML estático siempre devuelve 0.
            live_prices: dict[str, float] = {}
            try:
                live_prices = await self.page.evaluate(r"""
                    () => {
                        const result = {};
                        const cards = document.querySelectorAll(
                            'a[id^="product-"], div[id^="product-"], .product-item, [class*="ProductCard"]'
                        );
                        cards.forEach(card => {
                            const idAttr = card.id || card.getAttribute('data-product-id') || '';
                            const priceEl = card.querySelector(
                                '.price-text, .offer-price, .default-price, ' +
                                '[class*="price-text"], [class*="Price-text"], ' +
                                '[class*="ProductPrice"], [class*="product-price"], ' +
                                '[class*="offer"], [class*="Offer"], span[class*="price"]'
                            );
                            if (priceEl) {
                                const txt = priceEl.textContent.replace(/[\s\u00a0]/g, '');
                                const match = txt.match(/\$([0-9.]+)/);
                                if (match) {
                                    const numStr = match[1].replace(/\./g, '');
                                    const val = parseFloat(numStr);
                                    if (!isNaN(val) && val >= 1000) {
                                        result[idAttr] = val;
                                    }
                                }
                            }
                            if (!result[idAttr]) {
                                const allText = card.querySelectorAll('span, strong, b, p, div');
                                for (const el of allText) {
                                    if (el.children.length > 0) continue;
                                    const t = el.textContent.replace(/[\s\u00a0]/g, '');
                                    const m = t.match(/^\$([0-9.]{4,})$/);
                                    if (m) {
                                        const v = parseFloat(m[1].replace(/\./g, ''));
                                        if (!isNaN(v) && v >= 1000 && v <= 10000000) {
                                            result[idAttr] = v;
                                            break;
                                        }
                                    }
                                }
                            }
                        });
                        return result;
                    }
                """)
                logger.debug(f"[Paris] Live DOM prices extracted: {len(live_prices)} items")
            except Exception as e:
                logger.warning(f"[Paris] Live price extraction via evaluate() failed: {e}")
            # --- Fin extracción live ---

            html = await self.page.content()
            page_products = await self._extract_products_from_html(html, len(products), anansi_parser, live_prices)
            products.extend(page_products)

            if len(products) >= 240:
                break

            # Paris uses "Mostrar más" button
            next_btn = await self.page.query_selector('button:has-text("Mostrar más")')
            if next_btn:
                await next_btn.click()
                await self.page.wait_for_timeout(4000)
            else:
                break # No more products

        return products[:240]

    async def _extract_products_from_html(self, html: str, current_total: int, anansi_parser, live_prices: dict | None = None) -> list[dict]:
        soup = BeautifulSoup(html, 'lxml')
        # Paris products are often in <a> tags with id starting with product-, or generic product cards
        items = soup.select('a[id^="product-"], div[id^="product-"], .product-item, [class*="ProductCard"]')
        extracted = []
        live_prices = live_prices or {}

        for idx, item in enumerate(items):
            brand_el = item.select_one('[class*="brand"], [class*="Brand"], span.ui-font-semibold.ui-line-clamp-2')
            title_el = item.select_one('[class*="name"], [class*="title"], [class*="Title"], span.ui-line-clamp-2:not(.ui-font-semibold)')

            brand = brand_el.get_text(strip=True) if brand_el else ""
            title = title_el.get_text(strip=True) if title_el else ""

            # --- NUEVA HEURÍSTICA QUIRÚRGICA ROBUSTA PARA PARIS ---
            if not brand or not title:
                spans = [s.get_text(strip=True) for s in item.find_all('span') if s.get_text(strip=True)]
                ruidos = ['vista previa', 'agregar al carro', 'envío rápido', 'despacho gratis', 'vista rápida', '⚡', 'quick view', 'vista pr']
                filtered_spans = []
                for s in spans:
                    s_lower = s.lower()
                    # Evitar ruidos, precios y valoraciones (ej: '0 (0)' o puntuaciones de estrellas)
                    if not any(r in s_lower for r in ruidos) and not s.startswith('$') and not re.match(r'^\d+(\s*\(\d+\))?$', s):
                        filtered_spans.append(s)

                if len(filtered_spans) >= 2:
                    if not title:
                        title = filtered_spans[1]

            # --- CAPA DE RESCATE ANANSI ---
            # Si a pesar de la heurística falla en encontrar los campos clave:
            if (not brand or not title) and anansi_parser:
                item_html = str(item)
                try:
                    # Usamos las clases reales encontradas en el DOM para alimentar el parser adaptativo
                    rescate = await anansi_parser.extract(item_html, {
                        "rescued_title": SelectorConfig("span.ui-line-clamp-2", expected_pattern=r"\w+")
                    }, url="https://www.paris.cl") # URL base como contexto

                    if not title and rescate.get("rescued_title"):
                        # Evitar que se rescate "Vista Previa" como título
                        r_title = rescate.get("rescued_title")
                        if "vista previa" not in r_title.lower():
                            title = r_title
                            logger.debug(f"[Anansi] Título rescatado: {title}")

                except Exception as e:
                    logger.warning(f"Fallo en Anansi fallback: {e}")
            # --- FIN CAPA DE RESCATE ---

            # Only the explicit brand DOM field above supplies vendor identity.
            # Titles, arbitrary spans and adaptive rescues are identity hints only.

            # Extract price and marketplace SKU
            price = 0.0
            marketplace_sku = ""
            try:
                # 1. Use live DOM price if available (keyed by product id attr)
                item_id_attr = item.get("id", "") or item.get("data-product-id", "")
                if item_id_attr and item_id_attr in live_prices:
                    price = live_prices[item_id_attr]

                # 2. Fallback: BS4 parse from static HTML selectors
                if price == 0.0:
                    price_el = item.select_one(".price-text, .offer-price, .default-price, .price, [class*='price-text'], [class*='Price-text'], [class*='price'], [class*='Price']")
                    if price_el:
                        price = self.parse_price_text(price_el.get_text(separator=" ", strip=True))

                # 3. Last resort: scan leaf text nodes for Chilean price pattern
                if price == 0.0:
                    for child in item.find_all(['span', 'div', 'p', 'b', 'strong']):
                        txt = child.get_text(strip=True)
                        if '$' in txt and '%' not in txt and '(' not in txt:
                            val = self.parse_price_text(txt)
                            if val >= 1000.0:
                                price = val
                                break

                # Extract MK code or item ID
                if "product-" in item_id_attr:
                    marketplace_sku = item_id_attr.replace("product-", "").strip()
                elif item.name == "a" and item.get("href"):
                    href = item.get("href")
                    mk_match = re.search(r"([A-Z0-9]{8,12})\.html", href)
                    if mk_match:
                        marketplace_sku = mk_match.group(1)
            except Exception:
                pass

            if title or brand:
                extracted.append({
                    "title": title,
                    "vendor": brand,
                    "price": price,
                    "marketplace_sku": marketplace_sku,
                    "position_absolute": current_total + idx + 1
                })

        return extracted
