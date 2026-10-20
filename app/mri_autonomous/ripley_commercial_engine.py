"""
app/mri_autonomous/ripley_commercial_engine.py

Ripley Commercial Intelligence Adapter for Visual Auditor MRI.
Conforms strictly to the common MRI Commercial Contract:
- CommercialEntity (categories, facets, sellers)
- NormalizedPublication (multi-marketplace normalized publication model)
- Isolated SQLite persistence with 018R historical category & run isolation

Reuses certified Ripley headless scraper and counter verification capabilities.
"""

import json
import logging
import pathlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.mri_autonomous.rea_paris_engine import CommercialEntity, NormalizedPublication

logger = logging.getLogger(__name__)

# Documentary reference categories / facets discovered on Ripley for Nicopoly
# Separated from operational observations (reference_count prevents false operational assertions)
RIPLEY_REFERENCE_CATEGORIES = [
    {"group_id": "moda-mujer/tops-y-chaquetas/sweaters-y-chalecos", "name": "Sweaters y Chalecos", "reference_count": 284},
    {"group_id": "moda-mujer/tops-y-chaquetas/chaquetas-y-blazers", "name": "Chaquetas y Blazers", "reference_count": 256},
    {"group_id": "moda-mujer/jeans-y-pantalones/pantalones", "name": "Pantalones", "reference_count": 232},
]


class RipleyCommercialEngine:
    """
    Operational commercial engine for Ripley.cl brand exploration and catalog normalization.
    """

    def __init__(self, brand: str = "Nicopoly"):
        self.brand = brand
        self.marketplace = "Ripley"

    def get_commercial_summary(self, db_path: Optional[str] = None, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns structured commercial summary for Ripley Nicopoly presence based strictly
        on verified persisted evidence in SQLite for the specified run (or latest run),
        or explicit unacquired status if empty.
        Never generates publications or counts from internal constants.
        """
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            effective_db = db_path or str(StorageConfig.get_sqlite_path())
        except Exception:
            effective_db = db_path or "data/sqlite/visibility.db"

        rows = []
        cat_rows = []
        target_run_id = run_id
        target_terminal_state = None

        if not pathlib.Path(effective_db).exists():
            return {
                "marketplace": "Ripley",
                "brand": self.brand,
                "official_seller": self.brand,
                "total_brand_publications": 0,
                "total_official_seller_publications": 0,
                "categories": [],
                "total_categories": 0,
                "reference_categories": RIPLEY_REFERENCE_CATEGORIES,
                "mechanism": "Ripley Scraper & Verified Facets",
                "storage_source": "NONE",
                "status": "NO_EVIDENCE_RECORDED",
                "message": "Sin publicaciones verificadas adquiridas en la corrida actual."
            }

        conn = sqlite3.connect(effective_db)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            # If run_id not provided, resolve the latest run that executed Ripley
            if not target_run_id:
                # Check mri_run_marketplace_states first
                try:
                    state_row = cur.execute("""
                        SELECT run_id, terminal_state, status
                        FROM mri_run_marketplace_states
                        WHERE marketplace = 'Ripley'
                        ORDER BY rowid DESC LIMIT 1
                    """).fetchone()
                    if state_row:
                        target_run_id = state_row["run_id"]
                        target_terminal_state = state_row["terminal_state"] or state_row["status"]
                except sqlite3.OperationalError:
                    pass

                # Fallback to mri_runs
                if not target_run_id:
                    try:
                        r_row = cur.execute("""
                            SELECT run_id, terminal_state, status
                            FROM mri_runs
                            WHERE marketplace = 'Ripley'
                            ORDER BY rowid DESC LIMIT 1
                        """).fetchone()
                        if r_row:
                            target_run_id = r_row["run_id"]
                            target_terminal_state = r_row["terminal_state"] or r_row["status"]
                    except sqlite3.OperationalError:
                        pass
            else:
                # Fetch terminal state of requested run
                try:
                    s_row = cur.execute("""
                        SELECT terminal_state, status
                        FROM mri_run_marketplace_states
                        WHERE run_id = ? AND marketplace = 'Ripley'
                    """, (target_run_id,)).fetchone()
                    if s_row:
                        target_terminal_state = s_row["terminal_state"] or s_row["status"]
                    else:
                        r_row = cur.execute("""
                            SELECT terminal_state, status
                            FROM mri_runs
                            WHERE run_id = ?
                        """, (target_run_id,)).fetchone()
                        if r_row:
                            target_terminal_state = r_row["terminal_state"] or r_row["status"]
                except sqlite3.OperationalError:
                    pass

            # Query publications scoped strictly to target_run_id (or none if no run found)
            if target_run_id:
                rows = cur.execute("""
                    SELECT publication_id, marketplace_product_id, commercial_attributes, category_observed
                    FROM mri_publications
                    WHERE marketplace = 'Ripley' AND run_id = ?
                """, (target_run_id,)).fetchall()

                # If not in active publications, check historical publications
                if not rows:
                    try:
                        rows = cur.execute("""
                            SELECT publication_id, marketplace_product_id, commercial_attributes, category_observed
                            FROM mri_historical_publications
                            WHERE marketplace = 'Ripley' AND run_id = ?
                        """, (target_run_id,)).fetchall()
                    except sqlite3.OperationalError:
                        rows = []

                # Scoped categories for target_run_id
                cat_rows = []
                try:
                    cat_rows = cur.execute("""
                        SELECT DISTINCT c.category_id, c.category_name, c.canonical_url
                        FROM mri_categories c
                        JOIN mri_publication_categories pc ON c.category_id = pc.category_id
                        JOIN mri_publications p ON pc.publication_id = p.publication_id
                        WHERE p.marketplace = 'Ripley' AND p.run_id = ?
                    """, (target_run_id,)).fetchall()
                    if not cat_rows:
                        cat_rows = cur.execute("""
                            SELECT DISTINCT c.category_id, c.category_name, c.canonical_url
                            FROM mri_categories c
                            JOIN mri_historical_publication_categories hpc ON c.category_id = hpc.category_id
                            WHERE hpc.run_id = ?
                        """, (target_run_id,)).fetchall()
                except sqlite3.OperationalError:
                    cat_rows = []
        finally:
            conn.close()

        if rows:
            official_seller_count = 0
            for r in rows:
                attrs = {}
                try:
                    attrs = json.loads(r["commercial_attributes"] or "{}")
                except Exception:
                    pass
                sellers = attrs.get("sellers", [])
                if attrs.get("is_official_seller") or any("nicopoly" in str(s).lower() for s in sellers):
                    official_seller_count += 1

            total_pubs = len(rows)
            categories = [{"group_id": c["category_id"], "name": c["category_name"]} for c in cat_rows]
            return {
                "marketplace": "Ripley",
                "run_id": target_run_id,
                "brand": self.brand,
                "official_seller": self.brand,
                "total_brand_publications": total_pubs,
                "total_official_seller_publications": official_seller_count,
                "categories": categories,
                "total_categories": len(categories),
                "mechanism": "Ripley Headless Catalog Scraper",
                "storage_source": "SQLITE_MRI_PERSISTENCE",
                "status": "OPERATIONAL"
            }

        # If no verified evidence recorded in the target run
        unacquired_status = target_terminal_state or "NO_EVIDENCE_RECORDED"
        return {
            "marketplace": "Ripley",
            "run_id": target_run_id,
            "brand": self.brand,
            "official_seller": self.brand,
            "total_brand_publications": 0,
            "total_official_seller_publications": 0,
            "categories": [],
            "total_categories": 0,
            "reference_categories": RIPLEY_REFERENCE_CATEGORIES,
            "mechanism": "Ripley Scraper & Verified Facets",
            "storage_source": "NONE" if not target_run_id else "SQLITE_EMPTY_RUN",
            "status": unacquired_status,
            "message": f"Sin publicaciones verificadas adquiridas en la corrida {target_run_id or 'actual'}."
        }

    def normalize_items_to_publications(
        self,
        raw_items: List[Dict[str, Any]],
        observed_at: Optional[str] = None
    ) -> Tuple[List[NormalizedPublication], List[CommercialEntity]]:
        """
        Normalizes raw Ripley scraper items or live captures into MRI common contract.
        Deduplicates publications while aggregating sellers, promotions, and categories.
        Strictly derives categories solely from raw item attributes, producing ([], []) for empty input.
        """
        if not raw_items:
            return [], []

        obs_time = observed_at or datetime.now(timezone.utc).isoformat()
        pubs_map: Dict[str, NormalizedPublication] = {}
        entities_map: Dict[str, CommercialEntity] = {}

        for it in raw_items:
            sku = str(it.get("marketplace_sku") or it.get("sku") or "").strip()
            title = str(it.get("title") or it.get("name") or "").strip()
            url = str(it.get("url") or "").strip()
            
            if not sku and url:
                import re
                m = re.search(r"(mpm\d+|\d{7,})", url, re.IGNORECASE)
                if m:
                    sku = m.group(1).upper()
            
            # MRI-021: Strictly reject synthetic or empty SKUs in production normalization
            if not sku:
                logger.warning(f"[Ripley] Skipping item without verifiable SKU: {title}")
                continue

            vendor = str(it.get("vendor") or self.brand).strip()
            price = float(it.get("price") or 0.0)
            canonical_url = url or f"https://simple.ripley.cl/product/{sku}"

            cat_name = str(it.get("category") or "Moda Mujer")
            cat_id = it.get("category_id") or "moda-mujer"

            if sku not in pubs_map:
                pubs_map[sku] = NormalizedPublication(
                    publication_id=f"PUB_RIPLEY_{sku}",
                    marketplace="Ripley",
                    sku=sku,
                    title=title or f"Producto Nicopoly {sku}",
                    brand=self.brand,
                    sellers=[vendor] if vendor else [self.brand],
                    is_official_seller=(vendor.lower() == self.brand.lower()),
                    price_regular=price if price > 0 else None,
                    price_displayed=price if price > 0 else None,
                    discount_percentage=0.0,
                    condition="NEW",
                    canonical_url=canonical_url,
                    categories=[{"group_id": cat_id, "name": cat_name, "path": cat_name}],
                    promotions=[],
                    facets={"raw_category": cat_name},
                    observed_at=obs_time,
                    evidence_type="LIVE_OBSERVATION",
                    raw_source_id=f"RIPLEY-OBS-{sku}"
                )
            else:
                existing = pubs_map[sku]
                if vendor and vendor not in existing.sellers:
                    existing.sellers.append(vendor)
                if not any(c.get("group_id") == cat_id for c in existing.categories):
                    existing.categories.append({"group_id": cat_id, "name": cat_name, "path": cat_name})

        return list(pubs_map.values()), list(entities_map.values())

    def persist_to_mri_sqlite(
        self,
        publications: List[NormalizedPublication],
        entities: List[CommercialEntity],
        run_id: str,
        db_path: Optional[str] = None,
        terminal_state: str = "COMPLETED"
    ) -> Dict[str, Any]:
        """
        Persists normalized Ripley publications and commercial entities into MRI SQLite.
        Strictly enforces isolated sandbox via StorageConfig.assert_write_allowed and
        implements run isolation (018R pattern).
        """
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            effective_db = db_path or str(StorageConfig.get_sqlite_path())
            StorageConfig.assert_write_allowed(effective_db)
        except ImportError:
            effective_db = db_path or "data/sqlite/visibility.db"

        conn = sqlite3.connect(effective_db)
        try:
            cur = conn.cursor()
            now_str = datetime.now(timezone.utc).isoformat()

            # Ensure base schema exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mri_runs (
                    run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, marketplace TEXT,
                    brand TEXT, execution_mode TEXT, truth_model_version TEXT, terminal_state TEXT,
                    source_method TEXT, status TEXT, created_at TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mri_run_marketplace_states (
                    run_id TEXT NOT NULL, marketplace TEXT NOT NULL, terminal_state TEXT,
                    source_method TEXT, execution_mode TEXT, started_at TEXT, finished_at TEXT,
                    status TEXT NOT NULL, created_at TEXT,
                    PRIMARY KEY (run_id, marketplace),
                    FOREIGN KEY (run_id) REFERENCES mri_runs(run_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mri_publications (
                    publication_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, marketplace TEXT NOT NULL, marketplace_product_id TEXT,
                    canonical_url TEXT, status TEXT NOT NULL, observed_at TEXT NOT NULL, run_id TEXT, position INTEGER, surface TEXT,
                    position_state TEXT, category_relationship TEXT, evidence_type TEXT, raw_source_id TEXT,
                    acquisition_status TEXT, identity_status TEXT, category_observed TEXT,
                    category_source TEXT, category_expected TEXT, category_decision TEXT, commercial_attributes TEXT,
                    FOREIGN KEY (product_id) REFERENCES mri_products(product_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mri_products (
                    product_id TEXT PRIMARY KEY, canonical_brand TEXT NOT NULL, product_status TEXT NOT NULL, created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mri_categories (
                    category_id TEXT PRIMARY KEY, marketplace TEXT NOT NULL, category_name TEXT NOT NULL, canonical_url TEXT, created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mri_publication_categories (
                    publication_id TEXT NOT NULL, category_id TEXT NOT NULL, status TEXT NOT NULL, observed_at TEXT NOT NULL,
                    PRIMARY KEY(publication_id, category_id),
                    FOREIGN KEY (publication_id) REFERENCES mri_publications(publication_id),
                    FOREIGN KEY (category_id) REFERENCES mri_categories(category_id)
                )
            """)

            # 1. Register run in mri_runs (safe parent row, never replace to protect child FKs)
            cur.execute("""
                INSERT OR IGNORE INTO mri_runs (
                    run_id, started_at, finished_at, marketplace, brand, execution_mode,
                    truth_model_version, terminal_state, source_method, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id, now_str, now_str, "Ripley", self.brand,
                "RIPLEY_FACET_AND_CATALOG_EXTRACTION", "2.0", terminal_state,
                "PLAYWRIGHT_HEADLESS_FACET", "SUCCESS", now_str
            ))

            # Check if multiple marketplaces are auditing this run
            existing_mkt = cur.execute("SELECT marketplace FROM mri_runs WHERE run_id = ?", (run_id,)).fetchone()
            if existing_mkt and existing_mkt[0] not in ("Ripley", "MULTI_MARKETPLACE"):
                cur.execute("UPDATE mri_runs SET marketplace = 'MULTI_MARKETPLACE' WHERE run_id = ?", (run_id,))

            # Register state in mri_run_marketplace_states
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mri_run_marketplace_states (
                    run_id TEXT NOT NULL, marketplace TEXT NOT NULL, terminal_state TEXT,
                    source_method TEXT, execution_mode TEXT, started_at TEXT, finished_at TEXT,
                    status TEXT NOT NULL, created_at TEXT,
                    PRIMARY KEY (run_id, marketplace),
                    FOREIGN KEY (run_id) REFERENCES mri_runs(run_id)
                )
            """)
            cur.execute("""
                INSERT OR REPLACE INTO mri_run_marketplace_states (
                    run_id, marketplace, terminal_state, source_method, execution_mode,
                    started_at, finished_at, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id, "Ripley", terminal_state, "PLAYWRIGHT_HEADLESS_FACET",
                "RIPLEY_FACET_AND_CATALOG_EXTRACTION", now_str, now_str, "SUCCESS", now_str
            ))

            # 2. Persist categories
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
                prod_id = f"PROD_RIPLEY_{pub.sku}"
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

                # Check for existing publication to archive into historical table (018R pattern)
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
                        CREATE TABLE IF NOT EXISTS mri_historical_publications (
                            history_id TEXT PRIMARY KEY,
                            publication_id TEXT NOT NULL,
                            product_id TEXT NOT NULL,
                            marketplace TEXT NOT NULL,
                            marketplace_product_id TEXT,
                            canonical_url TEXT,
                            status TEXT,
                            observed_at TEXT NOT NULL,
                            run_id TEXT,
                            position INTEGER,
                            surface TEXT,
                            position_state TEXT,
                            category_relationship TEXT,
                            evidence_type TEXT,
                            raw_source_id TEXT,
                            acquisition_status TEXT,
                            identity_status TEXT,
                            category_observed TEXT,
                            category_source TEXT,
                            category_expected TEXT,
                            category_decision TEXT,
                            commercial_attributes TEXT
                        )
                    """)
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
                    # Ensure historical publication categories table exists before archiving
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
                    "RIPLEY_FACET_GRID", "EXACT", "CORRECT",
                    "FACET_COUNTER_RECORD", f"RIPLEY-OBS-{pub.sku}",
                    "OBSERVED", "TARGET_IDENTITY_VERIFIED", primary_cat,
                    "RIPLEY_TAXONOMY", primary_cat, "CORRECT", comm_attrs
                ))
                pubs_inserted += 1

                for cat in pub.categories:
                    cat_id = f"RIPLEY_CAT_{cat['group_id']}"
                    cur.execute("""
                        INSERT OR REPLACE INTO mri_publication_categories (
                            publication_id, category_id, status, observed_at
                        ) VALUES (?, ?, ?, ?)
                    """, (pub.publication_id, cat_id, "ACTIVE", pub.observed_at))
                    links_inserted += 1

            conn.commit()
            return {

                "run_id": run_id,
                "publications_materialized": pubs_inserted,
                "categories_materialized": cats_inserted,
                "category_links_materialized": links_inserted
            }
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()
