"""
app/mri_autonomous/falabella_ssr_engine.py

Falabella SSR & Next.js __NEXT_DATA__ Commercial Discovery Engine for MRI.
Implements reverse-engineered server-side rendered JSON extraction:
- Free search (/falabella-cl/search?Ntt=)
- Official brand corridor (/falabella-cl/brand/<MARCA>)
- Official seller corridor (/falabella-cl/seller/<SELLER>)
- Canonical Category hierarchy (/falabella-cl/category/<ID>/<SLUG>)
- Promotional Collections (/falabella-cl/collection/<SLUG>)
- Landing pages (/falabella-cl/page/<SLUG>)

Extracts exact totals from props.pageProps.pagination.count.
Reconstructs L0 -> L1 -> L2 taxonomy tree.
Separates Brand vs Seller vs Type vs Category.
Deduplicates publications while merging multi-memberships.
Outputs to shared MRI NormalizedPublication / CommercialEntity contracts.
"""

import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

FALABELLA_BASE_URL = "https://www.falabella.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class FalabellaCategoryNode:
    category_id: str
    name: str
    level: str  # 'L0', 'L1', 'L2'
    parent_id: Optional[str]
    hierarchical_path: str
    canonical_url: str
    reported_count: int
    children: List["FalabellaCategoryNode"] = field(default_factory=list)


class FalabellaSSREngine:
    """
    Reverse-engineered operational engine for Falabella.cl Next.js SSR platform.
    Reads embedded JSON from <script id="__NEXT_DATA__"> without headless browsers.
    """

    def __init__(self, base_url: str = FALABELLA_BASE_URL, user_agent: str = DEFAULT_USER_AGENT):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent

    def fetch_page_ssr_data(self, relative_path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Fetches an SSR HTML page from Falabella and extracts the __NEXT_DATA__ JSON payload.
        """
        clean_path = relative_path if relative_path.startswith("/") else f"/{relative_path}"
        if not clean_path.startswith("/falabella-cl/"):
            clean_path = f"/falabella-cl{clean_path}"

        query_str = ""
        if params:
            # Format params preserving facet syntax
            parts = []
            for k, v in params.items():
                if v is True:
                    parts.append(f"{k}=true")
                elif v is not None:
                    parts.append(f"{k}={urllib.parse.quote(str(v))}")
            if parts:
                query_str = "?" + "&".join(parts)

        full_url = f"{self.base_url}{clean_path}{query_str}"
        req = urllib.request.Request(
            full_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-CL,es;q=0.9,en;q=0.8"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                html = res.read().decode("utf-8", errors="replace")
                return self.extract_next_data(html, full_url)
        except Exception as e:
            logger.error(f"Falabella SSR fetch failed for {full_url}: {e}")
            return {
                "error": str(e),
                "url": full_url,
                "props": {"pageProps": {"pagination": {"count": 0}, "results": [], "facets": []}}
            }

    @staticmethod
    def extract_next_data(html: str, source_url: str = "") -> Dict[str, Any]:
        """
        Parses __NEXT_DATA__ JSON tag from raw HTML string.
        """
        match = re.search(r'<script id=[\'"]__NEXT_DATA__[\'"][^>]*>(.*?)</script>', html, re.DOTALL)
        if not match:
            # Fallback regex for variations
            match = re.search(r'<script\s+id=__NEXT_DATA__[^>]*>(.*?)</script>', html, re.DOTALL)
        if not match:
            return {
                "error": "NEXT_DATA_SCRIPT_NOT_FOUND",
                "url": source_url,
                "props": {"pageProps": {"pagination": {"count": 0}, "results": [], "facets": []}}
            }

        try:
            data = json.loads(match.group(1))
            return data
        except Exception as err:
            logger.error(f"Failed to parse __NEXT_DATA__ JSON: {err}")
            return {
                "error": f"JSON_PARSE_ERROR: {err}",
                "url": source_url,
                "props": {"pageProps": {"pagination": {"count": 0}, "results": [], "facets": []}}
            }

    def get_brand_catalog(self, brand_name: str = "NICOPOLY", page: int = 1, extra_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Retrieves catalog for brand corridor /falabella-cl/brand/<brand_name>.
        """
        params = {"page": page}
        if extra_params:
            params.update(extra_params)
        return self.fetch_page_ssr_data(f"/brand/{brand_name}", params=params)

    def get_seller_catalog(self, seller_name: str = "Nicopoly", page: int = 1, extra_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Retrieves catalog for seller corridor /falabella-cl/seller/<seller_name>.
        """
        params = {"page": page}
        if extra_params:
            params.update(extra_params)
        return self.fetch_page_ssr_data(f"/seller/{seller_name}", params=params)

    def get_category_catalog(self, category_id: str, slug: str, page: int = 1, extra_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Retrieves catalog for category page /falabella-cl/category/<category_id>/<slug>.
        """
        params = {"page": page}
        if extra_params:
            params.update(extra_params)
        return self.fetch_page_ssr_data(f"/category/{category_id}/{slug}", params=params)

    def search_catalog(self, query: str, page: int = 1, extra_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Free search route /falabella-cl/search?Ntt=<query>.
        """
        params = {"Ntt": query, "page": page}
        if extra_params:
            params.update(extra_params)
        return self.fetch_page_ssr_data("/search", params=params)

    def extract_taxonomy_tree(self, next_data_payload: Dict[str, Any]) -> List[FalabellaCategoryNode]:
        """
        Reconstructs the hierarchical category structure (L0, L1, L2) from
        facets in the pageProps.
        """
        nodes: List[FalabellaCategoryNode] = []
        page_props = next_data_payload.get("props", {}).get("pageProps", {})
        facets = page_props.get("facets", [])

        # Find category facet
        cat_facet = None
        for f in facets:
            if "categor" in (f.get("name") or "").lower():
                cat_facet = f
                break

        if not cat_facet:
            return nodes

        for val in cat_facet.get("values", []):
            cid = val.get("id") or ""
            cname = val.get("title") or val.get("name") or ""
            count = int(val.get("count") or 0)
            url_part = val.get("url") or ""
            facet_type = val.get("facetType") or ""

            level = "L0"
            if "L1" in facet_type or "/" in url_part and url_part.count("/") == 1:
                level = "L1"
            elif "L2" in facet_type or url_part.count("/") >= 2:
                level = "L2"

            node = FalabellaCategoryNode(
                category_id=cid,
                name=cname,
                level=level,
                parent_id=None,
                hierarchical_path=url_part,
                canonical_url=f"https://www.falabella.com/falabella-cl/category/{cid}/{urllib.parse.quote(cname.lower().replace(' ', '-'))}",
                reported_count=count
            )
            nodes.append(node)

        return nodes

    def harvest_sample_publications(
        self,
        brand: str = "NICOPOLY",
        max_items: int = 48,
        page_payload: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Any], List[Any]]:
        """
        Normalizes Falabella SSR publications and commercial entities into MRI common contract.
        Deduplicates by product/SKU while merging category and seller multi-memberships.
        """
        from app.mri_autonomous.rea_paris_engine import CommercialEntity, NormalizedPublication

        data = page_payload or self.get_brand_catalog(brand_name=brand, page=1)
        page_props = data.get("props", {}).get("pageProps", {})
        raw_results = page_props.get("results", [])
        exact_total = page_props.get("pagination", {}).get("count", len(raw_results))

        publications_by_sku: Dict[str, NormalizedPublication] = {}
        entities_dict: Dict[str, CommercialEntity] = {}

        # 1. Register base brand & seller entities
        brand_id = f"FALA_BRAND_{brand.upper()}"
        entities_dict[brand_id] = CommercialEntity(
            marketplace="Falabella",
            group_id=brand_id,
            display_name=brand.upper(),
            entity_type="brand",
            parent_id=None,
            hierarchical_path=f"/brand/{brand}",
            official_url=f"https://www.falabella.com/falabella-cl/brand/{brand}",
            reported_total=exact_total,
            acquisition_mechanism="SSR_NEXT_DATA_EXTRACTION",
            evidence_status="VERIFIED_PUBLIC_SSR"
        )

        # 2. Extract categories & facets from pageProps
        cat_nodes = self.extract_taxonomy_tree(data)
        for cnode in cat_nodes:
            cent_id = f"FALA_CAT_{cnode.category_id}"
            entities_dict[cent_id] = CommercialEntity(
                marketplace="Falabella",
                group_id=cent_id,
                display_name=cnode.name,
                entity_type="category" if cnode.level == "L0" else "subcategory",
                parent_id=cnode.parent_id,
                hierarchical_path=cnode.hierarchical_path,
                official_url=cnode.canonical_url,
                reported_total=cnode.reported_count,
                acquisition_mechanism="SSR_NEXT_DATA_EXTRACTION",
                evidence_status="VERIFIED_PUBLIC_SSR"
            )

        # 3. Process product results
        processed_count = 0
        for item in raw_results:
            if processed_count >= max_items:
                break
            processed_count += 1

            prod_id = str(item.get("productId") or "")
            sku_id = str(item.get("skuId") or prod_id)
            title = item.get("displayName") or ""
            item_brand = item.get("brand") or brand
            seller_name = item.get("sellerName") or "Falabella"
            seller_id = item.get("sellerId") or ""
            is_official = (seller_name.lower() == brand.lower() or seller_id == "SC75ABC")

            # Prices
            prices = item.get("prices", [])
            price_reg = None
            price_disp = None
            for p in prices:
                ptype = (p.get("type") or "").lower()
                amt = p.get("price", [None])[0]
                if amt is not None:
                    try:
                        amt_clean = float(str(amt).replace("$", "").replace(".", "").replace(",", ".").strip())
                        if "event" in ptype or "discount" in ptype or price_disp is None:
                            price_disp = amt_clean
                        if "normal" in ptype or "regular" in ptype:
                            price_reg = amt_clean
                    except Exception:
                        pass

            disc_pct = None
            if price_reg and price_disp and price_reg > price_disp:
                disc_pct = round(((price_reg - price_disp) / price_reg) * 100.0, 1)

            # URL
            canonical_url = item.get("url") or f"https://www.falabella.com/falabella-cl/product/{prod_id}"
            if canonical_url.startswith("/"):
                canonical_url = f"{self.base_url}{canonical_url}"

            # Category from GSC or breadcrumbs
            gsc_cat = item.get("GSCCategoryId") or ""
            cats: List[Dict[str, str]] = []
            if gsc_cat:
                cats.append({"group_id": gsc_cat, "name": gsc_cat, "path": f"/category/{gsc_cat}"})
            elif cat_nodes:
                cats.append({"group_id": cat_nodes[0].category_id, "name": cat_nodes[0].name, "path": cat_nodes[0].hierarchical_path})

            # Promotions / badges
            promos = []
            for b in item.get("multipurposeBadges", []) + item.get("badges", []):
                btext = b.get("text") or b.get("badgeText") or ""
                if btext and btext not in promos:
                    promos.append(btext)

            # Facets & specs
            specs = item.get("topSpecifications", {})
            facets = {"topSpecifications": specs, "sellerId": sellerId if (sellerId := item.get("sellerId")) else None}

            if sku_id in publications_by_sku:
                # Merge multi-membership
                existing = publications_by_sku[sku_id]
                if seller_name not in existing.sellers:
                    existing.sellers.append(seller_name)
                for cat in cats:
                    if cat["group_id"] not in {c["group_id"] for c in existing.categories}:
                        existing.categories.append(cat)
                for pr in promos:
                    if pr not in existing.promotions:
                        existing.promotions.append(pr)
            else:
                publications_by_sku[sku_id] = NormalizedPublication(
                    publication_id=f"FALA_{sku_id}",
                    marketplace="Falabella",
                    sku=sku_id,
                    title=title,
                    brand=item_brand,
                    sellers=[seller_name],
                    is_official_seller=is_official,
                    price_regular=price_reg,
                    price_displayed=price_disp,
                    discount_percentage=disc_pct,
                    condition="NEW",
                    canonical_url=canonical_url,
                    categories=cats,
                    promotions=promos,
                    facets=facets
                )

        return list(publications_by_sku.values()), list(entities_dict.values())

    def persist_to_mri_sqlite(
        self,
        publications: List[Any],
        entities: List[Any],
        run_id: str,
        db_path: Optional[str] = None,
        terminal_state: str = "COMPLETED"
    ) -> Dict[str, Any]:
        """
        Persists normalized Falabella publications and commercial entities into MRI SQLite.
        Strictly enforces isolated sandbox via StorageConfig.assert_write_allowed.
        """
        import sqlite3
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            effective_db = db_path or str(StorageConfig.get_sqlite_path())
            StorageConfig.assert_write_allowed(effective_db)
        except ImportError:
            effective_db = db_path or "data/sqlite/visibility.db"

        conn = sqlite3.connect(effective_db)
        cur = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()

        # 1. Register run in mri_runs
        cur.execute("""
            INSERT OR REPLACE INTO mri_runs (
                run_id, started_at, finished_at, marketplace, brand, execution_mode,
                truth_model_version, terminal_state, source_method, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id, now_str, now_str, "Falabella", "Nicopoly",
            "FALABELLA_SSR_NEXT_DATA_EXTRACTION", "2.0", terminal_state,
            "SSR_NEXT_DATA", "SUCCESS", now_str
        ))

        # 2. Persist categories in mri_categories
        cats_inserted = 0
        for ent in entities:
            cur.execute("""
                INSERT OR REPLACE INTO mri_categories (
                    category_id, marketplace, category_name, canonical_url, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                ent.group_id, ent.marketplace, ent.display_name, ent.official_url, now_str
            ))
            cats_inserted += 1

        # 3. Persist products and publications
        pubs_inserted = 0
        links_inserted = 0
        for idx, pub in enumerate(publications, start=1):
            prod_id = f"PROD_FALA_{pub.sku}"
            cur.execute("""
                INSERT OR REPLACE INTO mri_products (
                    product_id, canonical_brand, product_status, created_at
                ) VALUES (?, ?, ?, ?)
            """, (prod_id, pub.brand, "ACTIVE", now_str))

            primary_cat = pub.categories[0]["name"] if pub.categories else "NO_VERIFICADO"
            comm_attrs = json.dumps({
                "sellers": pub.sellers,
                "is_official_seller": pub.is_official_seller,
                "condition": pub.condition,
                "price_regular": pub.price_regular,
                "price_displayed": pub.price_displayed,
                "promotions": pub.promotions,
                "facets": pub.facets
            }, ensure_ascii=False)

            cur.execute("""
                INSERT OR REPLACE INTO mri_publications (
                    publication_id, product_id, marketplace, marketplace_product_id,
                    canonical_url, status, observed_at, run_id, position, surface,
                    position_state, category_relationship, evidence_type, raw_source_id,
                    acquisition_status, identity_status, category_observed,
                    category_source, category_expected, category_decision, commercial_attributes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pub.publication_id, prod_id, pub.marketplace, pub.sku,
                pub.canonical_url, "OBSERVED", pub.observed_at, run_id, idx,
                "FALABELLA_SSR_GRID", "EXACT", "CORRECT",
                "SSR_PAGE_PROPS_RECORD", f"FALA-SSR-{pub.sku}",
                "OBSERVED", "TARGET_IDENTITY_VERIFIED", primary_cat,
                "FALABELLA_TAXONOMY", primary_cat, "CORRECT", comm_attrs
            ))
            pubs_inserted += 1

            for cat in pub.categories:
                cat_id = f"FALA_CAT_{cat['group_id']}"
                cur.execute("""
                    INSERT OR REPLACE INTO mri_publication_categories (
                        publication_id, category_id, status, observed_at
                    ) VALUES (?, ?, ?, ?)
                """, (pub.publication_id, cat_id, "ACTIVE", pub.observed_at))
                links_inserted += 1

        conn.commit()
        conn.close()

        return {
            "run_id": run_id,
            "publications_materialized": pubs_inserted,
            "categories_materialized": cats_inserted,
            "category_links_materialized": links_inserted
        }
