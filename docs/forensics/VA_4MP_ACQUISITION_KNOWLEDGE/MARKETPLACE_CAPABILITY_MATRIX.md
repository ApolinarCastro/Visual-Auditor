# MARKETPLACE CAPABILITY MATRIX

## Transversal 4-Marketplace Acquisition & Intelligence Architecture

| Capability Dimension | Mercado Libre Chile | Falabella Chile | Paris Chile | Ripley Chile |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Scraper Script** | `app/scrapers/mercadolibre_scraper.py` | `app/scrapers/falabella_scraper.py` | `app/scrapers/paris_scraper.py` | `app/scrapers/ripley_scraper.py` |
| **Execution Mode** | Playwright Headless (`headless=True`) | HTTP SSR Fallback (F1) + Playwright Headless | Playwright Headless (`headless=True`) | Playwright Headless + Turnstile Handler |
| **Official Store / Brand Hub** | `https://tienda.mercadolibre.cl/nicopoly` | `https://www.falabella.com/falabella-cl/search?Ntt=nicopoly` | `https://www.paris.cl/search?q=nicopoly` | `https://simple.ripley.cl/search/nicopoly` |
| **Fallback Catalog Route** | `https://listado.mercadolibre.cl/nicopoly_Tienda_nicopoly` | Faceted routes (`f.product.attribute.Tipo`) | Query routes (`&tipoProductoAll={cat}`) | URL_QUERY facet (`?facet=...`) |
| **Authentication & Session** | Cookie injection (`data/mercadolibre_session.json` or Tu Chrome non-locking copy) | Sessionless (Standard Desktop UA bypasses challenge) | Sessionless (Clean context) | Session cookie storage (`data/ripley_session.json`) + WAF |
| **WAF / Anti-Bot Profile** | Akamai Bot Manager (avoid URL rewrite, honor clean URLs) | Cloudflare WAF (HTTP 403 on browser -> F1 HTTP 200 via `urllib`) | Next.js dynamic challenge | Cloudflare Turnstile |
| **Category Discovery Source** | Official store showcase DOM & corridor categories (`_Container_`) | Embedded `<script id="__NEXT_DATA__">` (`pageProps.facets`) | Streaming React Server Components (`self.__next_f.push`) | Network navigation tree (`mechanism.json`) |
| **Noise Filtering / Rejection** | Rejects shipping hubs (`addresses/v3/navigation/hub?go=...`) | Rejects non-commercial navigation nodes | Rejects `/mi-cuenta`, `/iniciar-sesion`, `/seguimiento`, `/outlet/` | Rejects competitor brand containers (`marcas-destacadas`) |
| **Product Data Extraction** | `.ui-search-layout__item` + carousel exemption (`ui-ms-polycard-carousel`) | Direct parsing from `__NEXT_DATA__.props.pageProps.results` | PLP card DOM + React stream objects | `.catalog-product-item` + image MPM ID regex |
| **Vendor / Brand Resolution** | Inferred from slug (`tienda/<brand>`), vendor fallback to `Nicopoly` | Direct field `brandName` / `sellerName` | Direct field `brand` or title | `.brand-name` element or image URL regex |
| **Pagination Mechanism** | Next link click (`.andes-pagination__button--next a`) | Query parameter `page={N}` (48 products/page) | Query parameter `page={N}` (40 products/page) | Query parameter `page={N}` + infinite scroll |
| **Empty State Handling** | Zero layout items found | `results.length === 0` | Empty product grid | Explicit detection: `"No existen productos..."` -> TOP30=0% |
| **Frontier & Batch Control** | Bounded category batch limits (max 3-5 pages per run) | Bounded category batch limits | Bounded category batch limits | Canonical terminal states (`BRAND_NAVIGATION`, `EXHAUSTED`) |
| **Persistence Contract** | SQLite `visibility.db` + `mri_history.json` + `mri_categories.json` | SQLite `visibility.db` + `mri_history.json` + `mri_categories.json` | SQLite `visibility.db` + `mri_history.json` + `mri_categories.json` | SQLite `visibility.db` + `mri_history.json` + `mri_categories.json` |
| **Certified Publications Universe** | 1,811 known publications | 1,063 known publications | 763 known publications | 362 known publications |
| **Direct Brand Evidence Rate** | 100% on observed items | 100% on observed items | 100% on observed items | 100% on observed items |
| **Operational Status** | OPERATIONAL (CERTIFIED PASS) | OPERATIONAL (CERTIFIED PASS) | OPERATIONAL (CERTIFIED PASS) | OPERATIONAL (CERTIFIED PASS) |

---

## Detailed Capability Analysis by Marketplace

### 1. Mercado Libre Chile
- **Capabilities Proven**:
  - Direct buyer session injection avoiding login blocks and collaborator redirect shields.
  - Official brand store showcase carousel extraction (`ui-ms-polycard-carousel`) without triggering exclusion filters.
  - Navigation URL preservation avoiding Akamai bot detection triggers.
  - Vendor fallback defaulting to "Nicopoly" on official brand store paths.
- **Acquisition Cost**: $0.00.

### 2. Falabella Chile
- **Capabilities Proven**:
  - Automatic detection of Cloudflare WAF HTTP 403 challenge in Playwright headless.
  - Immediate cutover to legitimate HTTP SSR acquisition (F1) via standard library `urllib` with desktop User-Agent, returning HTTP 200 with complete 1.97MB payload.
  - Parsing of 48 products directly from `__NEXT_DATA__.props.pageProps.results` with full prices, brand names, and SKUs.
  - Extraction of 22 commercial category routes from `pageProps.facets` (`attribute.Tipo`).
- **Acquisition Cost**: $0.00.

### 3. Paris Chile
- **Capabilities Proven**:
  - Streaming RSC parser extracting `generalFacets.tipoProductoAll` from `self.__next_f.push` chunks.
  - Autonomous category routing via search query parameter (`search?q=nicopoly&tipoProductoAll={cat}`).
  - Strict isolation from site-wide Mega-Menu noise, filtering out corporate and account links.
- **Acquisition Cost**: $0.00.

### 4. Ripley Chile
- **Capabilities Proven**:
  - `URL_QUERY` brand filter preservation preventing fallback to unconstrained categories.
  - Structured catalog extraction with regex-based MPM product ID parsing from image sources.
  - Empty search state detection preventing false-positive recommendations.
  - Frontier closure classifying unvisited competitor brand trees into canonical terminal states (`pending = 0`).
- **Acquisition Cost**: $0.00.
