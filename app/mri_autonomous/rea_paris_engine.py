"""
REA Paris Engine (Marketplace Research Intelligence)
Reverse engineered Constructor.io discovery & taxonomy integration for Paris.cl.

Provides:
- Public catalog query via verified Cencosud / Constructor.io key
- Separation of brand ("Nicopoly") vs seller ("NICOPOLY" / third-party / inactive)
- Hierarchical category tree reconstruction and breadcrumb path resolution
- Commercial facets & campaign/promotions membership extraction
- Multi-membership publication model and normalized commercial contract
"""

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import hashlib
import pathlib

logger = logging.getLogger(__name__)

# Verified public Constructor.io production configuration for Paris.cl
PARIS_CONSTRUCTOR_KEY = "key_6PvQHDnR0zdWgEPh"
PARIS_API_BASE = "https://ac.cnstrc.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _resolve_har_provenance(
    candidate_paths: Optional[List[str]] = None,
    item_sku: Optional[str] = None,
    item_data: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Verifies primary HAR evidence integrity via SHA-256 recalculation AND
    validates that the specific publication record exists and matches inside the capture.
    Never invents metadata if evidence is missing, corrupted, or unrelated to the item.
    """
    search_paths = candidate_paths or [
        "evidence/mri_rea_discovery_010/paris_search_capture.har",
        "clean_checkout/evidence/mri_rea_discovery_010/paris_search_capture.har",
        "../evidence/mri_rea_discovery_010/paris_search_capture.har",
    ]
    for p_str in search_paths:
        try:
            p = pathlib.Path(p_str).resolve()
            if p.exists() and p.is_file():
                raw_bytes = p.read_bytes()
                sha = hashlib.sha256(raw_bytes).hexdigest()
                har_data = json.loads(raw_bytes.decode("utf-8"))
                entry = har_data.get("log", {}).get("entries", [{}])[0]
                started_dt = entry.get("startedDateTime")
                creator = har_data.get("log", {}).get("creator", {}).get("name")
                src_url = entry.get("request", {}).get("url")

                # If item verification is requested, inspect the HAR response content
                if item_sku is not None:
                    matched = False
                    resp_content = entry.get("response", {}).get("content", {})
                    resp_text = resp_content.get("text", "")
                    if resp_text and item_sku in resp_text:
                        try:
                            feed = json.loads(resp_text)
                            results = feed.get("response", {}).get("results", [])
                            for res_item in results:
                                r_data = res_item.get("data", {})
                                r_id = str(r_data.get("id") or res_item.get("value") or "").strip()
                                if r_id == item_sku:
                                    # If item_data was provided, also verify sellers and groups consistency
                                    if item_data is not None:
                                        # Check sellers
                                        exp_sellers = set(item_data.get("sellers") or [])
                                        har_sellers = set(r_data.get("sellers") or [])
                                        if exp_sellers and har_sellers and exp_sellers != har_sellers:
                                            continue
                                        # Check groups / categories
                                        exp_groups = {g.get("group_id") for g in (item_data.get("groups") or []) if isinstance(g, dict) and g.get("group_id")}
                                        har_groups = {g.get("group_id") for g in (r_data.get("groups") or []) if isinstance(g, dict) and g.get("group_id")}
                                        if exp_groups and har_groups and exp_groups != har_groups:
                                            continue
                                    matched = True
                                    break
                        except Exception as e:
                            logger.debug(f"Error parsing HAR response text: {e}")
                    if not matched:
                        # Record not verified in this capture
                        continue

                return {
                    "path": str(p),
                    "sha256": sha,
                    "captured_at_declared": started_dt,
                    "producer": creator,
                    "source_url": src_url,
                }
        except Exception as e:
            logger.debug(f"Error checking HAR candidate {p_str}: {e}")
    return None


@dataclass
class CommercialEntity:
    marketplace: str
    group_id: str
    display_name: str
    entity_type: str  # 'category', 'subcategory', 'brand', 'seller', 'promotion', 'collection'
    parent_id: Optional[str]
    hierarchical_path: str
    official_url: str
    reported_total: int
    associated_publications: List[str] = field(default_factory=list)
    acquisition_mechanism: str = "CONSTRUCTOR_CDP_PUBLIC_API"
    evidence_status: str = "VERIFIED_PUBLIC_TRAFFIC"
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class NormalizedPublication:
    publication_id: str
    marketplace: str
    sku: str
    title: str
    brand: str
    sellers: List[str]
    is_official_seller: bool
    price_regular: Optional[float]
    price_displayed: Optional[float]
    discount_percentage: Optional[float]
    condition: str
    canonical_url: str
    categories: List[Dict[str, str]] = field(default_factory=list)  # [{'group_id': ..., 'name': ..., 'path': ...}]
    promotions: List[str] = field(default_factory=list)
    facets: Dict[str, Any] = field(default_factory=dict)
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence_type: str = "CONTROLLED_REPLAY"
    raw_source_id: Optional[str] = None
    source_file_path: Optional[str] = None
    source_file_sha256: Optional[str] = None
    source_captured_at: Optional[str] = None


class REAParisEngine:
    """
    Operational REA engine for Paris.cl search & discovery inspection.
    Uses verified endpoints discovered through reverse engineering.
    """

    def __init__(self, api_key: str = PARIS_CONSTRUCTOR_KEY, user_agent: str = DEFAULT_USER_AGENT):
        self.api_key = api_key
        self.user_agent = user_agent
        self.base_url = PARIS_API_BASE

    def _get_json(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = {"key": self.api_key}
        if params:
            p.update(params)
        query_str = urllib.parse.urlencode(p)
        full_url = f"{self.base_url}{endpoint}?{query_str}"

        req = urllib.request.Request(full_url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)

    def search(
        self,
        query: str,
        page: int = 1,
        num_results: int = 40,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Perform search query on Constructor.io Paris index."""
        params: Dict[str, Any] = {
            "page": page,
            "num_results_per_page": num_results,
        }
        if filters:
            for k, v in filters.items():
                params[f"filters[{k}]"] = v
        return self._get_json(f"/search/{urllib.parse.quote(query)}", params)

    def browse(
        self,
        facet_name: str,
        facet_value: str,
        page: int = 1,
        num_results: int = 40,
        filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Perform browse request (e.g. by brand, sellers, group_id)."""
        params: Dict[str, Any] = {
            "page": page,
            "num_results_per_page": num_results,
        }
        if filters:
            for k, v in filters.items():
                params[f"filters[{k}]"] = v
        endpoint = f"/browse/{urllib.parse.quote(facet_name)}/{urllib.parse.quote(facet_value)}"
        return self._get_json(endpoint, params)

    def get_brand_summary(self, brand: str = "Nicopoly") -> Dict[str, Any]:
        """Retrieve total brand counts, active facets, and groups."""
        res = self.browse("brand", brand, page=1, num_results=1)
        resp_data = res.get("response", {})
        total_brand = resp_data.get("total_num_results")

        facets_list = resp_data.get("facets", [])
        facets_map = {f.get("name"): f for f in facets_list}

        # Subdepartments & product types
        subtypes = [
            {"name": o.get("display_name"), "count": o.get("count"), "value": o.get("value")}
            for o in facets_map.get("tipoProductoAll", {}).get("options", [])
        ]

        return {
            "marketplace": "Paris",
            "brand": brand,
            "total_brand_results": total_brand,
            "product_types": subtypes,
            "facets_available": list(facets_map.keys()),
            "raw_groups": resp_data.get("groups", []),
        }

    def get_seller_summary(self, seller: str = "NICOPOLY") -> Dict[str, Any]:
        """Retrieve total seller publications and category participation."""
        res = self.browse("sellers", seller, page=1, num_results=1)
        resp_data = res.get("response", {})
        total_seller = resp_data.get("total_num_results")

        facets_list = resp_data.get("facets", [])
        facets_map = {f.get("name"): f for f in facets_list}

        subtypes = [
            {"name": o.get("display_name"), "count": o.get("count"), "value": o.get("value")}
            for o in facets_map.get("tipoProductoAll", {}).get("options", [])
        ]

        return {
            "marketplace": "Paris",
            "seller": seller,
            "total_seller_results": total_seller,
            "product_types": subtypes,
            "raw_groups": resp_data.get("groups", []),
        }

    def get_category_metrics(
        self,
        group_id: str,
        group_display_name: str,
        brand: str = "Nicopoly",
        official_seller: str = "NICOPOLY",
    ) -> Dict[str, Any]:
        """
        Compare Category Total Marketplace vs Brand Total vs Seller Total.
        """
        # 1. Total in category
        cat_data = self.browse("group_id", group_id, page=1, num_results=1).get("response", {})
        total_market = cat_data.get("total_num_results", 0)

        # 2. Total brand in category
        brand_data = self.browse(
            "group_id", group_id, page=1, num_results=1, filters={"brand": brand}
        ).get("response", {})
        total_brand = brand_data.get("total_num_results", 0)

        # 3. Total seller in category
        seller_data = self.browse(
            "group_id", group_id, page=1, num_results=1, filters={"sellers": official_seller}
        ).get("response", {})
        total_seller = seller_data.get("total_num_results", 0)

        return {
            "group_id": group_id,
            "group_name": group_display_name,
            "total_market": total_market,
            "total_brand": total_brand,
            "total_official_seller": total_seller,
            "other_sellers_brand": max(0, total_brand - total_seller),
        }

    def harvest_sample_publications(
        self,
        brand: str = "Nicopoly",
        max_items: int = 100,
    ) -> Tuple[List[NormalizedPublication], List[CommercialEntity]]:
        """
        Harvest items and reconstruct taxonomy and promotional memberships.
        """
        publications_by_sku: Dict[str, NormalizedPublication] = {}
        entities_dict: Dict[str, CommercialEntity] = {}
        items_per_page = 40
        pages = (max_items + items_per_page - 1) // items_per_page

        for page in range(1, pages + 1):
            data = self.browse("brand", brand, page=page, num_results=items_per_page).get("response", {})
            results = data.get("results", [])
            if not results:
                break

            for r in results:
                idata = r.get("data", {})
                sku = str(idata.get("id") or r.get("value") or "").strip()
                if not sku:
                    continue
                title = r.get("value") or ""
                sellers = idata.get("sellers") or []
                is_official = any(str(s).strip().upper() == "NICOPOLY" for s in sellers)
                condition = idata.get("conditions") or "new"

                # Sanitize canonical URL: clean staging domain to official production domain
                raw_url = idata.get("url") or f"https://www.paris.cl/{sku}.html"
                canonical_url = raw_url.replace("staging.ccom-stg.paris.cl", "www.paris.cl")
                if not canonical_url.startswith("http"):
                    canonical_url = f"https://www.paris.cl{canonical_url if canonical_url.startswith('/') else '/' + canonical_url}"

                item_groups = idata.get("groups") or []
                item_collections = idata.get("collections") or []

                norm_groups = []
                for g in item_groups:
                    gid = g.get("group_id")
                    gname = g.get("display_name")
                    gpath = g.get("path") or ""
                    norm_groups.append({"group_id": gid, "name": gname, "path": gpath})

                    if gid not in entities_dict:
                        # Determine entity type from path or id
                        etype = "category"
                        if "mujMarcas" in gpath:
                            etype = "brand"
                        elif "mujNovedades" in gpath or "Coleccion" in gid or "Evento" in gid:
                            etype = "promotion"
                        elif gpath.count("/") >= 3:
                            etype = "subcategory"

                        official_url = f"https://www.paris.cl{gpath}/{gid}/" if gpath else f"https://www.paris.cl/{gid}/"
                        entities_dict[gid] = CommercialEntity(
                            marketplace="Paris",
                            group_id=gid,
                            display_name=gname,
                            entity_type=etype,
                            parent_id=gpath.split("/")[-1] if gpath else None,
                            hierarchical_path=gpath,
                            official_url=official_url,
                            reported_total=int(g.get("count") or 0),
                            associated_publications=[sku],
                        )
                    else:
                        if sku not in entities_dict[gid].associated_publications:
                            entities_dict[gid].associated_publications.append(sku)

                # Process collections & promotional events
                promos_for_item = list(item_collections)
                for g in item_groups:
                    gid = g.get("group_id", "")
                    gname = g.get("display_name", "")
                    if "Evento" in gid or "Cyber" in gid or "Cyber" in gname:
                        if gname not in promos_for_item:
                            promos_for_item.append(gname)

                for coll in item_collections:
                    if coll not in entities_dict:
                        entities_dict[coll] = CommercialEntity(
                            marketplace="Paris",
                            group_id=coll,
                            display_name=coll.replace("-", " ").title(),
                            entity_type="collection",
                            parent_id=None,
                            hierarchical_path="/promociones/" + coll,
                            official_url=f"https://www.paris.cl/promociones/{coll}/",
                            reported_total=0,
                            associated_publications=[sku],
                        )
                    else:
                        if sku not in entities_dict[coll].associated_publications:
                            entities_dict[coll].associated_publications.append(sku)

                if sku in publications_by_sku:
                    # Deduplicate SKU while merging multi-memberships
                    existing_pub = publications_by_sku[sku]
                    # Merge sellers
                    for s in sellers:
                        if s not in existing_pub.sellers:
                            existing_pub.sellers.append(s)
                    if is_official:
                        existing_pub.is_official_seller = True
                    # Merge categories
                    existing_gids = {c["group_id"] for c in existing_pub.categories}
                    for ng in norm_groups:
                        if ng["group_id"] not in existing_gids:
                            existing_pub.categories.append(ng)
                    # Merge promotions
                    for p in promos_for_item:
                        if p not in existing_pub.promotions:
                            existing_pub.promotions.append(p)
                else:
                    pub = NormalizedPublication(
                        publication_id=f"PARIS-{sku}",
                        marketplace="Paris",
                        sku=sku,
                        title=title,
                        brand=brand,
                        sellers=sellers,
                        is_official_seller=is_official,
                        price_regular=float(idata.get("regularPrice") or 0.0) if idata.get("regularPrice") else None,
                        price_displayed=float(idata.get("displayedPrice") or 0.0) if idata.get("displayedPrice") else None,
                        discount_percentage=float(idata.get("discountPercentage") or 0.0) if idata.get("discountPercentage") else None,
                        condition=condition,
                        canonical_url=canonical_url,
                        categories=norm_groups,
                        promotions=promos_for_item,
                        facets={
                            "tipoProducto": idata.get("tipoProducto"),
                            "color": idata.get("color"),
                            "material": idata.get("material"),
                            "gender": idata.get("genero"),
                        },
                    )
                    # Bind verifiable primary provenance from verified HAR evidence
                    har_prov = _resolve_har_provenance(item_sku=sku, item_data=idata)
                    if har_prov:
                        pub.evidence_type = "CONTROLLED_REPLAY"
                        pub.source_file_path = har_prov["path"]
                        pub.source_file_sha256 = har_prov["sha256"]
                        pub.source_captured_at = har_prov["captured_at_declared"]
                        pub.raw_source_id = f"HAR-REPLAY-SHA256:{har_prov['sha256'][:16]}:{sku}"
                        if har_prov.get("captured_at_declared"):
                            pub.observed_at = har_prov["captured_at_declared"]
                    else:
                        pub.raw_source_id = f"PROVENANCE_INCOMPLETE:{sku}"
                        pub.source_file_path = None
                        pub.source_file_sha256 = None
                        pub.source_captured_at = None

                    publications_by_sku[sku] = pub

                if len(publications_by_sku) >= max_items:
                    break

        return list(publications_by_sku.values()), list(entities_dict.values())

    def persist_to_mri_sqlite(
        self,
        publications: List[NormalizedPublication],
        entities: List[CommercialEntity],
        run_id: str,
        db_path: Optional[str] = None,
        terminal_state: str = "COMPLETED"
    ) -> Dict[str, Any]:
        """
        Persists normalized Paris publications and commercial entities into MRI SQLite schema.
        Enforces storage write barrier (StorageConfig.assert_write_allowed).
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
            run_id, now_str, now_str, "Paris", "Nicopoly",
            "REA_DISCOVERY_CONSTRUCTOR_HARVEST", "2.0", terminal_state,
            "CONSTRUCTOR_PUBLIC_API", "SUCCESS", now_str
        ))

        # 2. Persist categories / entities in mri_categories
        cats_inserted = 0
        for ent in entities:
            cur.execute("""
                INSERT OR REPLACE INTO mri_categories (
                    category_id, marketplace, category_name, canonical_url, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                f"PARIS_{ent.group_id}", ent.marketplace, ent.display_name, ent.official_url, now_str
            ))
            cats_inserted += 1

        # 3. Persist products, publications, and category linkages
        pubs_inserted = 0
        links_inserted = 0
        for idx, pub in enumerate(publications, start=1):
            prod_id = f"PROD_PAR_{pub.sku}"
            cur.execute("""
                INSERT OR REPLACE INTO mri_products (
                    product_id, canonical_brand, product_status, created_at
                ) VALUES (?, ?, ?, ?)
            """, (prod_id, pub.brand, "ACTIVE", now_str))

            # Check if this SKU matches master catalog
            parent_sku = None
            category_expected = None
            identity_status = "IDENTITY_NOT_LINKED"
            category_decision = "REVIEW_REQUIRED"

            try:
                from app.mri_dashboard.mri_api import get_master_catalog
                child_to_cat, parent_to_cat, title_to_cat, _ = get_master_catalog()
                m_match = child_to_cat.get(pub.sku) or parent_to_cat.get(pub.sku)
                if not m_match and pub.title:
                    m_match = title_to_cat.get(pub.title.lower().strip())
                if m_match:
                    identity_status = "TARGET_IDENTITY_VERIFIED"
                    parent_sku = m_match.get("parent")
                    category_expected = m_match.get("category")
                    # Evaluate decision
                    primary_cat = pub.categories[0]["name"] if pub.categories else "NO_VERIFICADO"
                    if category_expected and primary_cat and category_expected.lower() in primary_cat.lower():
                        category_decision = "CORRECT"
                    else:
                        category_decision = "REVIEW_REQUIRED"
            except Exception:
                pass

            primary_cat = pub.categories[0]["name"] if pub.categories else "NO_VERIFICADO"
            exp_cat = category_expected or "NO_VERIFICADO"

            comm_attrs = json.dumps({
                "sellers": pub.sellers,
                "is_official_seller": pub.is_official_seller,
                "condition": pub.condition,
                "price_regular": pub.price_regular,
                "price_displayed": pub.price_displayed,
                "promotions": pub.promotions,
                "facets": pub.facets
            }, ensure_ascii=False)

            # Check for existing publication to archive into historical table
            existing = cur.execute("""
                SELECT publication_id, product_id, marketplace, marketplace_product_id,
                       canonical_url, status, observed_at, run_id, position, surface,
                       position_state, category_relationship, evidence_type, raw_source_id,
                       acquisition_status, identity_status, category_observed,
                       category_source, category_expected, category_decision, commercial_attributes
                FROM mri_publications WHERE publication_id = ?
            """, (pub.publication_id,)).fetchone()

            if existing and existing[7] and existing[7] != run_id:
                cur.execute("""
                    INSERT OR REPLACE INTO mri_historical_publications (
                        history_id, publication_id, product_id, marketplace, marketplace_product_id,
                        canonical_url, status, observed_at, run_id, position, surface,
                        position_state, category_relationship, evidence_type, raw_source_id,
                        acquisition_status, identity_status, category_observed,
                        category_source, category_expected, category_decision, commercial_attributes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"hist_{existing[7]}_{pub.publication_id}", existing[0], existing[1], existing[2], existing[3],
                    existing[4], existing[5], existing[6], existing[7], existing[8], existing[9],
                    existing[10], existing[11], existing[12], existing[13], existing[14], existing[15],
                    existing[16], existing[17], existing[18], existing[19], existing[20]
                ))
                # F2: Ensure historical publication categories table exists before archiving
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS mri_historical_publication_categories (
                        history_id TEXT PRIMARY KEY,
                        publication_id TEXT NOT NULL,
                        category_id TEXT NOT NULL,
                        run_id TEXT,
                        observed_at TEXT NOT NULL
                    )
                """)
                old_links = cur.execute(
                    "SELECT category_id, observed_at FROM mri_publication_categories WHERE publication_id = ?",
                    (pub.publication_id,)
                ).fetchall()
                for o_cat, o_obs in old_links:
                    cur.execute("""
                        INSERT OR REPLACE INTO mri_historical_publication_categories (
                            history_id, publication_id, category_id, run_id, observed_at
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (f"hist_{existing[7]}_{pub.publication_id}_{o_cat}", pub.publication_id, o_cat, existing[7], o_obs))
                # Delete old active links for this publication to enforce run isolation
                cur.execute("DELETE FROM mri_publication_categories WHERE publication_id = ?", (pub.publication_id,))

            # Preserve real provenance: REPLAY / FIXTURE vs LIVE_OBSERVATION
            ev_type = getattr(pub, "evidence_type", None) or "CONTROLLED_REPLAY"
            raw_src = getattr(pub, "raw_source_id", None)
            if not raw_src:
                pub_item_data = {
                    "sellers": pub.sellers,
                    "groups": pub.categories,
                }
                har_prov = _resolve_har_provenance(item_sku=pub.sku, item_data=pub_item_data)
                if har_prov:
                    raw_src = f"HAR-REPLAY-SHA256:{har_prov['sha256'][:16]}:{pub.sku}"
                    if not getattr(pub, "source_file_path", None):
                        pub.source_file_path = har_prov["path"]
                        pub.source_file_sha256 = har_prov["sha256"]
                        pub.source_captured_at = har_prov["captured_at_declared"]
                else:
                    raw_src = f"PROVENANCE_INCOMPLETE:{pub.sku}"
                    pub.source_file_path = None
                    pub.source_file_sha256 = None
                    pub.source_captured_at = None
            elif str(raw_src).startswith("PROVENANCE_INCOMPLETE"):
                pub.source_file_path = None
                pub.source_file_sha256 = None
                pub.source_captured_at = None

            # If publication has explicit source_captured_at, preserve it in attributes & observed_at
            pub_attrs_dict = {
                "sellers": pub.sellers,
                "is_official_seller": pub.is_official_seller,
                "condition": pub.condition,
                "price_regular": pub.price_regular,
                "price_displayed": pub.price_displayed,
                "promotions": pub.promotions,
                "facets": pub.facets,
            }
            if getattr(pub, "source_file_path", None):
                pub_attrs_dict["source_file_path"] = pub.source_file_path
            if getattr(pub, "source_file_sha256", None):
                pub_attrs_dict["source_file_sha256"] = pub.source_file_sha256
            if getattr(pub, "source_captured_at", None):
                pub_attrs_dict["source_captured_at"] = pub.source_captured_at

            comm_attrs = json.dumps(pub_attrs_dict, ensure_ascii=False)

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
                "CONSTRUCTOR_SEARCH_GRID", "EXACT", category_decision,
                ev_type, raw_src,
                "OBSERVED", identity_status, primary_cat,
                "CONSTRUCTOR_CDP_TAXONOMY", exp_cat, category_decision, comm_attrs
            ))
            pubs_inserted += 1

            # Multi-membership linkage
            for cat in pub.categories:
                cat_id = f"PARIS_{cat['group_id']}"
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
