# EXTERNAL TECH RESEARCH & CONTROLLED REVERSE ENGINEERING

## Objective & Scope
Forensic evaluation of external open-source technologies, architectures, and repository patterns to determine what reusable public mechanisms can improve Visual Auditor / MRI without violating project governance:
- Zero external paid services (cost = $0.00)
- Zero third-party cloud actor dependencies
- Zero architecture replacement of certified working components

### Investigated Sources
1. [cporter202/ecommerce-intelligence-apis](https://github.com/cporter202/ecommerce-intelligence-apis)
2. [Apify Platform & Actor Ecosystem](https://github.com/apify)
3. [Apify Crawlee (TypeScript)](https://github.com/apify/crawlee)
4. [Apify Crawlee Python](https://github.com/apify/crawlee-python)

---

## 1. Source Classification & Architectural Assessment

### A. `cporter202/ecommerce-intelligence-apis`
- **Nature of Source**: Curated markdown directory linking to Apify actors and CoreClaw workers.
- **Source Code Availability**: Contains **zero executable scraper source code** or open APIs. Does not provide native drivers or scrapers for Chilean retail marketplaces (Mercado Libre Chile, Falabella, Paris, Ripley).
- **Classification**: `NOT_APPLICABLE`
- **Finding**: Acts as an affiliate gateway to paid cloud compute actors. No code or architectural component is extractable for local deployment.

### B. `apify` (Platform & Ecosystem)
- **Nature of Source**: Cloud-hosted serverless container platform for web scraping actors.
- **Operational Requirements**: Requires Apify account tokens, paid compute units (CUs), proxy network subscriptions, and cloud orchestration.
- **Classification**: `NOT_APPLICABLE`
- **Finding**: Directly violates MRI governance ("Prohibido instalar actores comerciales de Apify / utilizar servicios de pago").

### C. `crawlee` & `crawlee-python`
- **Nature of Source**: Open-source, self-hosted web scraping and browser automation framework (Apache 2.0 license).
- **Core Abstractions**:
  - `RequestQueue` / `RequestList`: Memory- or file-backed FIFO/LIFO URL queue with deduplication and state persistence.
  - Multi-tier Crawlers: `HttpCrawler` / `BeautifulSoupCrawler` (raw HTTP requests) vs `PlaywrightCrawler` (headless browser execution).
  - Session Management: `SessionPool` managing user agents, cookies, and error states.
  - Autoscaling: Concurrency control dynamically throttled by CPU and memory load.
  - Data Storage: `Dataset` (record store) and `KeyValueStore` (checkpoint/metadata store).

---

## 2. Multi-Dimensional Forensic Comparison

| Engineering Dimension | External Technology Pattern (Crawlee / Apify) | Visual Auditor / MRI Certified Architecture | Classification | Reusability & Differential Assessment |
| :--- | :--- | :--- | :--- | :--- |
| **1. Acquisition Architecture** | Dual crawler hierarchy (`HttpCrawler` -> `PlaywrightCrawler`) with auto-switch. | Explicit tiering: Falabella F1 HTTP SSR fallback (`urllib`) before Playwright DOM; Paris streaming RSC parser; ML/Ripley Playwright headless. | `ALREADY_IMPLEMENTED` | MRI already implements tiering specifically adapted to Chilean WAF boundaries (Cloudflare & Akamai) without generic framework overhead. |
| **2. HTTP / API Priority vs Browser** | Requests sent via HTTP first; browser spawned only when JS rendering is declared necessary. | Priority HTTP SSR in Falabella (`FalabellaScraper.navigate()`); direct REST and streaming JSON parsing in Paris and Ripley. | `ALREADY_IMPLEMENTED` | Certified Decision D-016 established HTTP SSR priority as the canonical solution for Falabella ENTRY. |
| **3. Product Discovery** | Recursive link extraction (`enqueue_links`) using regex globs. | Autonomous category discoverer (`category_discoverer.py`) with noise rejection (`surface_classifier.py`). | `ALREADY_IMPLEMENTED` | MRI discoverer specifically understands official store carousels, corridor paths, and commercial taxonomy parameters. |
| **4. JSON Structure Recovery** | Built-in JSON response parsers and Cheerio/BeautifulSoup script tag extractors. | Dedicated Next.js `<script id="__NEXT_DATA__">` parser in Falabella and streaming RSC chunk extractor in Paris. | `ALREADY_IMPLEMENTED` | MRI extracts full structured payloads directly from `<script>` blocks with 100% brand/price fidelity. |
| **5. Pagination** | `enqueue_links` on pagination selectors or sequential page parameter loops. | Page-click automation (`andes-pagination__button--next`) and query param increments with clean URL preservation. | `ALREADY_IMPLEMENTED` | MRI enforces deterministic speed controls (0.8s – 1.2s delay) to avoid anti-bot triggering. |
| **6. Concurrency Control** | Dynamic autoscaled concurrency (`AutoscaledPool`) based on system CPU/RAM limits. | Controlled sequential batch execution with bounded batch limits (max 3-5 pages per category). | `POTENTIAL_IMPROVEMENT` | Concurrency pooling could accelerate large backfills, but strict sequential delays are intentionally required to avoid WAF rate-limiting. |
| **7. Progress Persistence** | KeyValueStore and RequestQueue state files on disk. | SQLite database (`data/sqlite/visibility.db`) + `data/mri_history.json` + `data/mri_categories.json`. | `ALREADY_IMPLEMENTED` | MRI uses relational SQLite tables with full ledger provenance and ACID guarantees. |
| **8. Partial Response Handling** | Checkpoint state saved per batch; failed requests re-queued. | Bounded stop semantics (`stop_reason: EXHAUSTION`, `BATCH_LIMIT`); state preserved in SQLite ledger. | `ALREADY_IMPLEMENTED` | Partial runs never discard discovered publications; unvisited nodes resolve to terminal states. |
| **9. Retries & Limits** | Configurable exponential backoff (`maxRequestRetries: 3`). | Max 2 retries per failed operation; fail-closed stop on credential/baseline corruption. | `ALREADY_IMPLEMENTED` | MRI adheres strictly to finite budgets and anti-hallucination gates. |
| **10. Publication Identity** | Unique key hashing on product URL or SKU. | Tri-level identity resolution: `sku_parent`, `sku_child`, `mktSku` + brand normalization (`brand_norm.py`). | `ALREADY_IMPLEMENTED` | MRI enforces `TARGET_IDENTITY_VERIFIED` vs `IDENTITY_NOT_LINKED` distinction. |
| **11. Position Traceability** | Array index assignment during parsing. | `position_absolute`, `position_state`, `surface` tied directly to search sort and category context. | `ALREADY_IMPLEMENTED` | MRI records exact position semantics in `mri_publications` and `product_snapshots`. |
| **12. Reproducible Evidence** | Dataset exports to JSON/CSV/Excel. | Cryptographic evidence ledgers (`mri_evidence_ledger`), raw HTML/JSON dumps, run IDs, SHA-256 hashes. | `ALREADY_IMPLEMENTED` | Evidence-first model satisfies complete independent reconciliation gates. |
| **13. Failure Recovery** | Session rotation and proxy failover. | Non-locking profile copy fallback (ML), F1 HTTP SSR fallback (Falabella), URL_QUERY parameter resolution (Ripley). | `ALREADY_IMPLEMENTED` | Certified resolutions F-001 through F-020 document demonstrated causal recoveries. |

---

## 3. Conclusions & Recommendations
1. **No External Paid Adoption**: Neither Apify commercial actors nor CoreClaw APIs should be introduced. They incur recurring monetary costs and lack Chilean marketplace specificity.
2. **Reusability of Crawlee Concepts**: While Crawlee's design validates MRI's architectural choices (HTTP prioritization, structured script parsing, session pooling), **rebuilding MRI on Crawlee would constitute an unjustified architectural rewrite** prohibited by Decision D-002 and D-006.
3. **Actionable Takeaways**:
   - Preserve MRI's proven lightweight HTTP SSR and streaming RSC extractors.
   - Retain local SQLite persistence and session injection.
   - Maintain bounded concurrency and deliberate pagination delays to protect against IP rate-limiting.
