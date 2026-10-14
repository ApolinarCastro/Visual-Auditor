# ACQUISITION MECHANISMS

Comprehensive forensic catalog of acquisition procedures, HTTP/SSR mechanisms, selectors, session injection flows, and failover sequences across the four operational marketplaces in Visual Auditor / MRI.

---

## 1. Mercado Libre Chile Acquisition Flow

### Entry Point Hierarchy
1. **Primary Entry**: Official Brand Store:
   `https://tienda.mercadolibre.cl/{brand}` (e.g. `https://tienda.mercadolibre.cl/nicopoly`)
2. **Fallback Entry**: Brand Corridor Listing:
   `https://listado.mercadolibre.cl/{brand}_Tienda_{brand}`
3. **Autonomous Search Entry**:
   `https://listado.mercadolibre.cl/{brand}`

### Authentication & Session Injection
- **Path**: `data/mercadolibre_session.json`
- **Mechanism**: The scraper (`MercadoLibreScraper.start()`) reads the stored JSON cookies and uses `playwright.browser_context.add_cookies()`.
- **Resilience Fallback**: If session cookies are absent or invalid, `mercadolibre_scraper.py` copies the local Google Chrome default profile ("Tu Chrome") in non-locking read-only mode, extracts the valid buyer session, sanitizes tokens, and injects cookies into the headless context in memory.

### Scraping & Parsing Procedure
- **Clean Navigation Guard**:
  `_get_clean_navigation_url(url)` strips tracking queries and anchor fragments without rewriting the URL path, preventing Akamai bot detection triggers.
- **Showcase Carousel Exemption**:
  Standard poly-card extractors ignore carousels to avoid recommendation contamination, but official store showcases use class `ui-ms-polycard-carousel`. `_extract_products_from_html` exempts this class to capture all featured store publications.
- **Product Extraction Selectors**:
  - Item container: `.ui-search-layout__item`
  - Title & URL: `a.poly-component__title`, `h2.poly-box a`
  - Price: `.poly-price__current .andes-money-amount__fraction`, `.price-tag-fraction`
  - Vendor resolution: if seller selector is missing, `vendor` is inferred from the official store URL slug (`tienda/nicopoly` -> `vendor="Nicopoly"`).
- **Pagination**:
  Clicks `.andes-pagination__button--next a` with an intentional delay between `0.8s – 1.2s`.

---

## 2. Falabella Chile Acquisition Flow

### Entry Point Hierarchy
1. **Primary Entry**: Brand Search Document:
   `https://www.falabella.com/falabella-cl/search?Ntt={brand}`
2. **Category Facet Entry**:
   `https://www.falabella.com/falabella-cl/search?Ntt={brand}&f.product.attribute.Tipo={category}`

### Dual-Tier Acquisition Architecture (F1 / Playwright Cutover)
- **Problem**: Cloudflare WAF issues an HTTP 403 Challenge Page to headless Playwright browsers.
- **Certified Solution (Decision D-016)**:
  `FalabellaScraper.navigate(url)` initiates an HTTP GET request using standard Python `urllib.request` with desktop headers (`User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...`).
  - Standard HTTP request receives HTTP 200 OK delivering the complete Next.js SSR document (1.97 MB).
  - The HTML is injected into the headless Playwright page via:
    ```python
    await self.page.set_content(html, wait_until="domcontentloaded")
    ```
  - Zero browser windows, zero external proxy services, zero CAPTCHAs.

### Structured JSON Extraction (`__NEXT_DATA__`)
- **Location**: `<script id="__NEXT_DATA__" type="application/json">`
- **Product Records**: `props.pageProps.results` array:
  - `displayName`: Product title
  - `brandName` / `sellerName`: Brand confirmation
  - `skuId`: Marketplace SKU
  - `prices`: Array of price points (`normalPrice`, `offerPrice`, `eventPrice`)
  - `url`: Relative product link
- **Category Facet Extraction**:
  `props.pageProps.facets` contains:
  - `attribute.Tipo`: Product categories (Pantalones, Vestidos, Blazers, etc.)
  - `L0_category_paths`: High-level taxonomy routes.

---

## 3. Paris Chile Acquisition Flow

### Entry Point Hierarchy
1. **Primary Entry**: Brand Search PLP:
   `https://www.paris.cl/search?q={brand}`
2. **Autonomous Category Routing**:
   `https://www.paris.cl/search?q={brand}&tipoProductoAll={category}`

### Next.js App Router Streaming RSC Acquisition
- **Problem**: Paris migrated from Pages Router (`__NEXT_DATA__`) to Next.js App Router, streaming React Server Components (RSC) chunks via inline scripts (`self.__next_f.push([1, "..."])`).
- **Certified Solution (Decision D-015)**:
  `category_discoverer.py` and `paris_scraper.py` parse inline streaming script chunks, regex-extracting `generalFacets.tipoProductoAll` facet arrays.
  - Non-commercial and navigation noise (Mega-Menu links such as `/mi-cuenta`, `/iniciar-sesion`, `/centro-de-ayuda`, `/seguimiento`, `/legales/`, `/outlet/`) is discarded.
  - Filtered category values are parameterized into clean search routes: `search?q={brand}&tipoProductoAll={category}`.
- **Product Extraction**:
  Product cards in the search grid are parsed for brand text, titles, SKU codes, and offer prices.

---

## 4. Ripley Chile Acquisition Flow

### Entry Point Hierarchy
1. **Primary Entry**: Brand Search Corridor:
   `https://simple.ripley.cl/search/{brand}`
2. **Facet Category Route**:
   `https://simple.ripley.cl/search/{brand}?facet=...` or dynamic query parameters.

### URL_QUERY Mechanism & Schema Compatibility (Decision D-020)
- **Problem**: Previous runs suffered brand constraint loss when navigating category routes, falling back to unconstrained categories (`zapatos-y-zapatillas`) with zero brand products.
- **Certified Solution**:
  `category_discoverer.py:build_facet_url()` supports `URL_QUERY` schema variants, dynamically resolving parameter names (`param`, `query_param`, or regex parsing of mechanism transition text).
  - Target routes prioritize brand-constrained URLs (`_furl`).
  - Empty search state detection: Scraper inspects DOM for `"No existen productos que cumplan con tus criterios de filtrado"`. When detected, immediately halts extraction and reports `Total Nico = 0` and `%TOP30 = 0.0%`, discarding suggested products.

### Product & MPM Identification
- **Selectors**:
  - Container: `.catalog-product-item`
  - Brand: `.brand-name`, `.catalog-product-details__brand`
  - SKU extraction:
    1. Primary: `data-part-number` attribute.
    2. Secondary: Regex extraction of `MPM\d+` from image URL (`img[src*='MPM']`).
    3. Tertiary: Regex extraction from product link href.
