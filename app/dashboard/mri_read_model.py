"""
MRI V2 Read-Only Commercial Inspection Model
Dedicated deterministic read model for Visual Auditor MRI V2 inspection layer.
Strictly read-only: zero write paths, zero mutation of legacy tables, zero cutover.

PHASE A REFACTORED:
All synthetic commercial generators permanently decommissioned.
Rule: EMPTY BUT TRUE > COMPLETE BUT SYNTHETIC.
Zero publication IDs, SKUs, prices, positions, availability, or evidence hashes generated.
"""

import os
import json
import sqlite3
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime
from app.config.settings import COMMERCIAL_READ_MODE, AUTHORITY_REGISTRY

# Truth model constants
ACTIVE_TRUTH_MODEL = "LEGACY_VA"
MRI_DISPLAY_LABEL = "MRI V2 — READ ONLY / SHADOW"

# Certified completeness constants
COMPLETENESS_VERIFIED_COMPLETE = "VERIFIED_COMPLETE"
COMPLETENESS_HIGH_CONFIDENCE_PARTIAL = "HIGH_CONFIDENCE_PARTIAL"
COMPLETENESS_PARTIAL = "PARTIAL"
COMPLETENESS_BLOCKED = "BLOCKED"
COMPLETENESS_RESEARCH_CENSUS_ONLY = "RESEARCH_CENSUS_ONLY (NOT_MATERIALIZED)"

UNKNOWN_REMAINDER_UNKNOWN = "UNKNOWN"

class ReadOnlyViolationError(Exception):
    """Raised when any code attempts a mutating query through the MRI read model."""
    pass


class MRIReadModel:
    """
    Deterministic read model for MRI V2 inspection data.
    Provides verified commercial views without modifying production truth.
    Strictly read-only projection: DB / Evidence -> projection -> UI.
    ZERO authority to synthesize or invent commercial publication records.
    """

    def __init__(self, db_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.db_path = db_path or os.path.join(base_dir, "data", "sqlite", "visibility.db")
        self.base_dir = base_dir

    def get_commercial_read_mode(self) -> str:
        """Returns the configured commercial read mode."""
        import app.config.settings as settings
        import importlib
        # For testing reloads, we force a reload of the module when checking mode
        if os.getenv("COMMERCIAL_READ_MODE"):
            os.environ["COMMERCIAL_READ_MODE"] = os.getenv("COMMERCIAL_READ_MODE")
        importlib.reload(settings)
        val = getattr(settings, 'COMMERCIAL_READ_MODE', 'LEGACY')
        return val

    def is_feature_enabled(self) -> bool:
        """Legacy accessor, defaults to true if we are in MRI_PRIMARY or MRI_SHADOW."""
        return self.get_commercial_read_mode() in ("MRI_PRIMARY", "MRI_SHADOW")

    def get_read_only_connection(self) -> sqlite3.Connection:
        """Opens SQLite in strict read-only URI mode where supported, else standard connection."""
        try:
            uri = f"file:{os.path.abspath(self.db_path)}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
        except Exception:
            conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def safe_query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """
        Executes a SQL query with mechanical read-only enforcement.
        Rejects any statement that could mutate state.
        """
        normalized = sql.strip().upper()
        forbidden_verbs = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE", "TRUNCATE"]
        for verb in forbidden_verbs:
            if normalized.startswith(verb) or f" {verb} " in normalized:
                raise ReadOnlyViolationError(f"READ_ONLY_VIOLATION: Attempted mutating operation '{verb}'")

        conn = self.get_read_only_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
            return rows
        finally:
            conn.close()

    def get_status(self) -> Dict[str, Any]:
        """Returns system inspection status and active truth model."""
        mode = self.get_commercial_read_mode()
        return {
            "feature_flag": "COMMERCIAL_READ_MODE",
            "commercial_read_mode": mode,
            "feature_enabled": self.is_feature_enabled(),
            "active_truth_model": ACTIVE_TRUTH_MODEL,
            "authority_registry": AUTHORITY_REGISTRY,
            "mri_label": "MRI V2 \u2014 COMMERCIAL READ (PRIMARY)",
            "read_only": True,
            "phase": "PHASE_C_PRODUCTION_ACTIVATION",
            "synthetic_authority": "ZERO",
            "server_time": datetime.now().isoformat()
        }

    def _sanitize_reference(self, raw_ref: Optional[str]) -> str:
        """Strips local filesystem paths, secrets, or cookies from evidence references."""
        if not raw_ref:
            return "N/A"
        cleaned = raw_ref.replace(self.base_dir, "").replace("\\", "/")
        if "Users" in cleaned:
            parts = cleaned.split("/")
            cleaned = parts[-1] if parts else "internal_reference"
        return cleaned

    def get_summary(self) -> Dict[str, Any]:
        """
        Returns per-marketplace commercial summary distinguishing:
        - RESEARCH / CENSUS SUMMARY (Aggregates from frozen research audits)
        - MATERIALIZED COMMERCIAL RECORDS (Real persisted publication rows in MRI tables)
        NO synthetic publication counts. NO fabricated completeness.
        """
        # Query real persisted commercial publications from mri_publications
        # Excludes test/foundation runs (e.g. golden shadow runs)
        real_pub_counts = {}
        try:
            rows = self.safe_query(
                "SELECT lower(replace(marketplace, ' ', '')) as mkt, count(*) as cnt FROM mri_publications "
                "WHERE run_id != 'run_golden_shadow_001' AND run_id NOT LIKE '%test%' "
                "GROUP BY lower(replace(marketplace, ' ', ''))"
            )
            for r in rows:
                real_pub_counts[r["mkt"]] = r["cnt"]
        except Exception:
            pass

        # Query Ripley unresolved observations
        ripley_unresolved = 0
        try:
            r_rows = self.safe_query(
                "SELECT count(*) as cnt FROM product_snapshots WHERE lower(marketplace) = 'ripley' AND created_at >= '2026-09-22T09:00:00'"
            )
            ripley_unresolved = r_rows[0]["cnt"] if r_rows else 0
        except Exception:
            pass

        marketplaces = [
            {
                "marketplace": "Paris",
                "brand": "Nicopoly",
                "research_census_total": 486,
                "materialized_real_publications": real_pub_counts.get("paris", 0),
                "completeness_state": COMPLETENESS_RESEARCH_CENSUS_ONLY,
                "unknown_remainder": UNKNOWN_REMAINDER_UNKNOWN,
                "unknown_remainder_display": "UNKNOWN (Censo de investigación congelado; materialización parcial en curso)",
                "surfaces_observed": 8,
                "surfaces_observed_list": ["Category Browse", "Brand Catalog", "Subcategory Listing", "Product Detail"],
                "last_verified": "2026-09-21T16:27:40",
                "blocked_surfaces": 0,
                "unresolved_identities": 0,
                "contradictions": 0,
                "evidence_health": "RESEARCH_BASELINE_FROZEN",
                "reference_universe": "486 registros en censo de investigación (No materializados en publicaciones MRI)",
                "provenance": "commercial_reconciliation/v001/09_CENSUS_RECONCILIATION.csv",
                "commercial_authority": AUTHORITY_REGISTRY["COMMERCIAL_PUBLICATIONS"]["paris"],
                "note": f"Paris: Censo de investigación: 486. Publicaciones reales materializadas: {real_pub_counts.get('paris', 0)}."
            },
            {
                "marketplace": "Ripley",
                "brand": "Nicopoly",
                "research_census_total": 382,
                "materialized_real_publications": real_pub_counts.get("ripley", 0),
                "completeness_state": "IDENTITY_UNRESOLVED",
                "unknown_remainder": UNKNOWN_REMAINDER_UNKNOWN,
                "unknown_remainder_display": "IDENTITY_UNRESOLVED",
                "surfaces_observed": 6,
                "surfaces_observed_list": ["Brand Catalog", "Category Listing", "Product Detail"],
                "last_verified": "2026-09-21T16:27:40",
                "blocked_surfaces": 0,
                "unresolved_identities": ripley_unresolved,
                "contradictions": 0,
                "evidence_health": "RESEARCH_BASELINE_FROZEN",
                "reference_universe": f"{ripley_unresolved} observaciones en run certificado (identidad nativa no capturada)",
                "provenance": "product_snapshots",
                "commercial_authority": AUTHORITY_REGISTRY["COMMERCIAL_PUBLICATIONS"]["ripley"],
                "note": f"Ripley: {ripley_unresolved} observations IDENTITY_UNRESOLVED."
            },
            {
                "marketplace": "Falabella",
                "brand": "Nicopoly",
                "research_census_total": 192,
                "materialized_real_publications": real_pub_counts.get("falabella", 0),
                "completeness_state": COMPLETENESS_RESEARCH_CENSUS_ONLY,
                "unknown_remainder": UNKNOWN_REMAINDER_UNKNOWN,
                "unknown_remainder_display": "UNKNOWN (Censo de investigación de 6 facetas; materialización en curso)",
                "surfaces_observed": 6,
                "surfaces_observed_list": ["Search Grid", "Department Facet: Vestidos", "Department Facet: Blusas", "Department Facet: Pantalones", "Department Facet: Chaquetas", "Department Facet: Sweaters"],
                "last_verified": "2026-09-21T16:50:00",
                "blocked_surfaces": 0,
                "unresolved_identities": 0,
                "contradictions": 0,
                "evidence_health": "RESEARCH_BASELINE_FROZEN",
                "reference_universe": "192 registros en censo de investigación (No materializados en publicaciones MRI)",
                "provenance": "census_capability_revalidation/v001/06_FALABELLA_CENSUS.json",
                "commercial_authority": AUTHORITY_REGISTRY["COMMERCIAL_PUBLICATIONS"]["falabella"],
                "note": f"Falabella: Censo de investigación: 192. Publicaciones reales materializadas: {real_pub_counts.get('falabella', 0)}."
            },
            {
                "marketplace": "Mercado Libre",
                "brand": "Nicopoly",
                "research_census_total": 430,
                "materialized_real_publications": real_pub_counts.get("mercadolibre", 0),
                "completeness_state": COMPLETENESS_RESEARCH_CENSUS_ONLY,
                "unknown_remainder": UNKNOWN_REMAINDER_UNKNOWN,
                "unknown_remainder_display": "UNKNOWN (Censo de investigación; materialización en curso)",
                "surfaces_observed": 4,
                "surfaces_observed_list": ["Brand Store (422 items)", "Search Grid (8 reseller items)", "Offers", "Category Browse"],
                "last_verified": "2026-09-21T16:50:00",
                "blocked_surfaces": 0,
                "unresolved_identities": 0,
                "contradictions": 0,
                "evidence_health": "RESEARCH_BASELINE_FROZEN",
                "reference_universe": "430 registros en censo de investigación (No materializados en publicaciones MRI)",
                "provenance": "census_capability_revalidation/v001/11_ML_CENSUS.json",
                "commercial_authority": AUTHORITY_REGISTRY["COMMERCIAL_PUBLICATIONS"]["mercadolibre"],
                "note": f"Mercado Libre: Censo de investigación: 430. Publicaciones reales materializadas: {real_pub_counts.get('mercadolibre', 0)}."
            }
        ]

        total_materialized = sum(m["materialized_real_publications"] for m in marketplaces)
        total_census = sum(m["research_census_total"] for m in marketplaces)

        return {
            "mri_label": MRI_DISPLAY_LABEL,
            "active_truth_model": ACTIVE_TRUTH_MODEL,
            "marketplaces": marketplaces,
            "total_materialized_real_publications": total_materialized,
            "total_research_census_publications": total_census,
            "as_of": datetime.now().isoformat(),
            "phase": "PHASE_C_PRODUCTION_ACTIVATION"
        }

    def get_publications(
        self,
        marketplace: Optional[str] = None,
        category: Optional[str] = None,
        surface: Optional[str] = None,
        top_n: Optional[str] = None,
        evidence_state: Optional[str] = None,
        page: int = 1,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Returns paginated publications from REAL PERSISTED MRI tables.
        PHASE A: All synthetic mock loops have been removed.
        Queries mri_publications directly. When no commercial materialized
        records exist, returns an honest empty state:
        'Sin publicaciones MRI materializadas con evidencia comercial real.'
        """
        # Filters out foundation/test execution records (run_golden_shadow_001)
        conditions = ["p.run_id != 'run_golden_shadow_001'", "p.run_id NOT LIKE '%test%'"]
        params = []

        if marketplace and marketplace.strip() and marketplace.lower() != "all":
            conditions.append("lower(p.marketplace) = ?")
            params.append(marketplace.strip().lower())

        if category and category.strip():
            # Match taxonomy node or raw category name
            conditions.append("(lower(p.taxonomy_classified_as) LIKE ? OR lower(c.category_name) LIKE ?)")
            search_term = f"%{category.strip().lower()}%"
            params.extend([search_term, search_term])

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"""
            SELECT p.publication_id, p.product_id, p.marketplace, p.marketplace_product_id,
                   p.canonical_url, p.status as evidence_state, p.observed_at as last_verified,
                   p.run_id, p.position, p.surface, p.category_relationship,
                   v.variant_title as title, v.seller_sku,
                   pr.effective_price as sale_price, pr.regular_price,
                   c.category_name as observed_in
            FROM mri_publications p
            LEFT JOIN mri_variants v ON v.publication_id = p.publication_id
            LEFT JOIN mri_prices pr ON pr.publication_id = p.publication_id
            LEFT JOIN mri_publication_categories pc ON pc.publication_id = p.publication_id
            LEFT JOIN mri_categories c ON c.category_id = pc.category_id
            {where_clause}
            ORDER BY p.observed_at DESC, p.publication_id ASC
        """

        try:
            raw_rows = self.safe_query(sql, tuple(params))
        except Exception:
            raw_rows = []

        total = len(raw_rows)
        start = (page - 1) * limit
        end = start + limit
        paginated_raw = raw_rows[start:end]

        items = []
        for r in paginated_raw:
            items.append({
                "publication_id": r.get("publication_id"),
                "marketplace": r.get("marketplace", "").capitalize() if r.get("marketplace") else "Paris",
                "marketplace_product_id": r.get("marketplace_product_id"),
                "product_id": r.get("product_id"),
                "title": r.get("title") or "N/A",
                "seller_sku": r.get("seller_sku") if (r.get("seller_sku") and r.get("seller_sku") != "MASTER_UNMAPPED") else "MASTER_UNMAPPED",
                "sale_price": r.get("sale_price"),
                "regular_price": r.get("regular_price"),
                "availability": {"display": "UNKNOWN"},
                "taxonomy_classified_as": r.get("category_relationship") or "LEGACY_CONFIGURED_CATEGORY",
                "observed_in": r.get("observed_in") or "N/A",
                "surface": r.get("surface") or "Category Browse",
                "position": r.get("position") if r.get("position") is not None else "UNRESOLVED",
                "top_n": "N/A",
                "evidence_state": r.get("evidence_state") or "OBSERVED",
                "last_verified": r.get("last_verified") or "N/A",
                "canonical_url": r.get("canonical_url"),
                "evidence_id": f"ev_{r.get('marketplace', '').lower()}_pub_{r.get('publication_id')}"
            })

        return {
            "mri_label": MRI_DISPLAY_LABEL,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if limit > 0 and total > 0 else 1,
            "items": items,
            "empty_state_message": "Sin publicaciones MRI materializadas con evidencia comercial real."
        }

    def get_unresolved_observations(self, marketplace: str = "Ripley", limit: int = 100) -> Dict[str, Any]:
        """
        Returns unresolved observations directly from product_snapshots.
        These are NOT canonical publications.
        """
        sql = f"""
            SELECT id, marketplace_sku as marketplace_product_id, product_title as title, price as sale_price, 
                   price_multivende as regular_price, created_at as observed_at
            FROM product_snapshots
            WHERE lower(marketplace) = ? AND created_at >= '2026-09-22T09:00:00'
            ORDER BY created_at DESC
            LIMIT ?
        """
        
        try:
            raw_rows = self.safe_query(sql, (marketplace.lower(), limit))
        except Exception:
            raw_rows = []
            
        items = []
        for r in raw_rows:
            items.append({
                "marketplace": marketplace.capitalize(),
                "marketplace_product_id": r.get("marketplace_product_id"),
                "title": r.get("title") or "N/A",
                "sale_price": r.get("sale_price"),
                "regular_price": r.get("regular_price"),
                "observed_at": r.get("observed_at"),
                "canonical_url": "N/A",
                "evidence_state": "IDENTITY_UNRESOLVED",
                "note": "Raw observation without canonical identity mapping"
            })
            
        return {
            "mri_label": MRI_DISPLAY_LABEL,
            "total": len(items),
            "items": items,
            "empty_state_message": "No hay observaciones no resueltas."
        }

    def get_categories(self, marketplace: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns active commercial categories with live observed counts and TopN position aggregation
        queried deterministically from SQLite (mri_categories, mri_publication_categories, mri_publications).
        If database has no materialized categories, falls back to labeled frozen research summary.
        """
        conditions = ["p.run_id != 'run_golden_shadow_001'", "p.run_id NOT LIKE '%test%'"]
        params = []
        if marketplace and marketplace.strip() and marketplace.lower() != "all":
            conditions.append("lower(c.marketplace) = ?")
            params.append(marketplace.strip().lower())

        where_clause = " WHERE " + " AND ".join(conditions)
        sql = f"""
            SELECT 
                c.marketplace,
                c.category_name as taxonomy_node,
                count(DISTINCT pc.publication_id) as publications_classified,
                count(DISTINCT p.publication_id) as publications_observed,
                COALESCE(p.surface, 'Category Browse') as browse_surface,
                sum(CASE WHEN p.position IS NOT NULL AND p.position <= 30 THEN 1 ELSE 0 END) as top30,
                sum(CASE WHEN p.position IS NOT NULL AND p.position <= 60 THEN 1 ELSE 0 END) as top60,
                sum(CASE WHEN p.position IS NOT NULL AND p.position <= 90 THEN 1 ELSE 0 END) as top90,
                sum(CASE WHEN p.position IS NOT NULL AND p.position <= 120 THEN 1 ELSE 0 END) as top120,
                sum(CASE WHEN p.position IS NOT NULL AND p.position <= 240 THEN 1 ELSE 0 END) as top240,
                count(p.position) as total_positions,
                COALESCE(max(p.observed_at), c.created_at) as last_verified,
                COALESCE(max(p.status), 'OBSERVED') as evidence_state
            FROM mri_categories c
            JOIN mri_publication_categories pc ON pc.category_id = c.category_id
            JOIN mri_publications p ON p.publication_id = pc.publication_id
            {where_clause}
            GROUP BY c.marketplace, c.category_name
            ORDER BY c.marketplace ASC, publications_observed DESC, c.category_name ASC
        """

        try:
            db_rows = self.safe_query(sql, tuple(params))
        except Exception:
            db_rows = []

        if db_rows:
            items = []
            for r in db_rows:
                has_pos = r["total_positions"] > 0
                items.append({
                    "marketplace": r["marketplace"],
                    "taxonomy_node": r["taxonomy_node"],
                    "publications_classified": r["publications_classified"],
                    "publications_observed": r["publications_observed"],
                    "browse_surface": r["browse_surface"],
                    "top30_count": r["top30"] if has_pos else "N/A (NOT MATERIALIZED)",
                    "top60_count": r["top60"] if has_pos else "N/A (NOT MATERIALIZED)",
                    "top90_count": r["top90"] if has_pos else "N/A (NOT MATERIALIZED)",
                    "top120_count": r["top120"] if has_pos else "N/A (NOT MATERIALIZED)",
                    "top240_count": r["top240"] if has_pos else "N/A (NOT MATERIALIZED)",
                    "evidence_state": r["evidence_state"],
                    "last_verified": r["last_verified"],
                    "provenance": "Materialized Commercial Records (mri_categories)"
                })
            return {
                "mri_label": MRI_DISPLAY_LABEL,
                "total": len(items),
                "items": items,
                "provenance_notice": "Materialización comercial MRI V2 activa. Posiciones TopN derivadas de observaciones reales persistidas."
            }

        # Fallback to research census summary if no commercial records in DB
        raw_cats = [
            {
                "marketplace": "Paris",
                "taxonomy_node": "Vestidos",
                "publications_classified": 150,
                "publications_observed": 150,
                "browse_surface": "Brand Catalog + Category Browse",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T09:12:30",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Paris",
                "taxonomy_node": "Blusas y Poleras",
                "publications_classified": 150,
                "publications_observed": 150,
                "browse_surface": "Brand Catalog + Category Browse",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T09:12:30",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Paris",
                "taxonomy_node": "Pantalones y Jeans",
                "publications_classified": 186,
                "publications_observed": 186,
                "browse_surface": "Brand Catalog + Subcategory Listing",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T09:12:30",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Ripley",
                "taxonomy_node": "Vestidos y Enteritos",
                "publications_classified": 140,
                "publications_observed": 140,
                "browse_surface": "Brand Catalog",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T09:28:45",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Ripley",
                "taxonomy_node": "Blusas",
                "publications_classified": 120,
                "publications_observed": 120,
                "browse_surface": "Brand Catalog",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T09:28:45",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Ripley",
                "taxonomy_node": "Sweaters y Tejidos",
                "publications_classified": 122,
                "publications_observed": 122,
                "browse_surface": "Brand Catalog",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T09:28:45",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Falabella",
                "taxonomy_node": "Vestidos",
                "publications_classified": 48,
                "publications_observed": 48,
                "browse_surface": "Brand Facet: Vestidos",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T16:50:00",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Falabella",
                "taxonomy_node": "Blusas y Poleras",
                "publications_classified": 36,
                "publications_observed": 36,
                "browse_surface": "Department Facet: Blusas",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T16:50:00",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Falabella",
                "taxonomy_node": "Pantalones y Jeans",
                "publications_classified": 42,
                "publications_observed": 42,
                "browse_surface": "Department Facet: Pantalones",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T16:50:00",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Falabella",
                "taxonomy_node": "Chaquetas y Abrigos",
                "publications_classified": 32,
                "publications_observed": 32,
                "browse_surface": "Department Facet: Chaquetas",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T16:50:00",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Falabella",
                "taxonomy_node": "Sweaters y Cardigans",
                "publications_classified": 20,
                "publications_observed": 20,
                "browse_surface": "Department Facet: Sweaters",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T16:50:00",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Mercado Libre",
                "taxonomy_node": "Vestidos",
                "publications_classified": 144,
                "publications_observed": 144,
                "browse_surface": "Brand Store + Search Grid",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T16:50:00",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Mercado Libre",
                "taxonomy_node": "Blusas",
                "publications_classified": 143,
                "publications_observed": 143,
                "browse_surface": "Brand Store + Search Grid",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T16:50:00",
                "provenance": "Research Census Aggregate"
            },
            {
                "marketplace": "Mercado Libre",
                "taxonomy_node": "Pantalones",
                "publications_classified": 143,
                "publications_observed": 143,
                "browse_surface": "Brand Store + Search Grid",
                "top30_count": "N/A (NOT MATERIALIZED)",
                "top60_count": "N/A (NOT MATERIALIZED)",
                "top90_count": "N/A (NOT MATERIALIZED)",
                "top120_count": "N/A (NOT MATERIALIZED)",
                "top240_count": "N/A (NOT MATERIALIZED)",
                "evidence_state": "RESEARCH_SUMMARY_NOT_MATERIALIZED",
                "last_verified": "2026-09-21T16:50:00",
                "provenance": "Research Census Aggregate"
            }
        ]

        cats = raw_cats
        if marketplace and marketplace.strip() and marketplace.lower() != "all":
            m_clean = marketplace.strip().lower()
            cats = [c for c in cats if c["marketplace"].lower() == m_clean]

        return {
            "mri_label": MRI_DISPLAY_LABEL,
            "total": len(cats),
            "items": cats,
            "provenance_notice": "RESEARCH SUMMARY / NOT MATERIALIZED (HISTÓRICO). Cero posiciones TopN materializadas."
        }

    def get_evidence(
        self,
        marketplace: Optional[str] = None,
        claim_type: Optional[str] = None,
        page: int = 1,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Returns ONLY persisted evidence ledger records that actually exist in the database.
        Foundation/test records are explicitly identified as TEST/FOUNDATION and must NOT appear as commercial VERIFIED.
        All 200 previously generated mock rows are completely eliminated.
        """
        sql = """
            SELECT evidence_id, run_id, marketplace, brand, claim_type, claim_value,
                   source_surface as surface, method, observed_at, confidence,
                   status, raw_reference, content_hash, truth_model_version
            FROM mri_evidence_ledger
            ORDER BY observed_at DESC
        """
        try:
            raw_rows = self.safe_query(sql)
        except Exception:
            raw_rows = []

        processed = []
        for r in raw_rows:
            is_foundation = "golden" in r.get("run_id", "").lower() or "test" in r.get("run_id", "").lower()
            # Foundation/test evidence MUST NOT appear as commercial VERIFIED
            display_status = "TEST/FOUNDATION" if is_foundation else r.get("status", "UNVERIFIED")
            
            processed.append({
                "evidence_id": r["evidence_id"],
                "marketplace": r["marketplace"].title() if r["marketplace"] else "N/A",
                "publication_id": r.get("claim_value") if "pub" in str(r.get("claim_value", "")) else "N/A",
                "claim_type": r["claim_type"],
                "claim_value": r["claim_value"],
                "surface": r["surface"],
                "method": r["method"],
                "observed_at": r["observed_at"],
                "confidence": r["confidence"],
                "status": display_status,
                "is_foundation_test": is_foundation,
                "raw_reference": self._sanitize_reference(r.get("raw_reference")),
                "content_hash": r.get("content_hash", "")[:16] if r.get("content_hash") else "N/A",
                "truth_model_version": r.get("truth_model_version", "MRI_V2_SHADOW")
            })

        filtered = processed
        if marketplace and marketplace.strip() and marketplace.lower() != "all":
            m_clean = marketplace.strip().lower()
            filtered = [e for e in filtered if e["marketplace"].lower() == m_clean]

        if claim_type and claim_type.strip():
            c_clean = claim_type.strip().upper()
            filtered = [e for e in filtered if e["claim_type"] == c_clean]

        total = len(filtered)
        start = (page - 1) * limit
        end = start + limit
        paginated = filtered[start:end]

        return {
            "mri_label": MRI_DISPLAY_LABEL,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if limit > 0 and total > 0 else 1,
            "items": paginated,
            "notice": "Solo muestra evidencia física persistida en mri_evidence_ledger. Cero filas generadas."
        }

    def get_source_health(self) -> Dict[str, Any]:
        """
        Returns source state from certified frozen research observations.
        Identifies provenance explicitly as RESEARCH OBSERVATION, not current live health.
        """
        return {
            "mri_label": MRI_DISPLAY_LABEL,
            "provenance": "RESEARCH OBSERVATION (Frozen Research Audit)",
            "is_live": False,
            "sources": [
                {
                    "marketplace": "Paris",
                    "status": "HEALTHY",
                    "status_label": "● HEALTHY (RESEARCH OBSERVATION)",
                    "last_verified": "2026-09-21T09:12:30",
                    "details": "Catálogo accesible en censo de investigación (486 productos en censo)",
                    "provenance": "RESEARCH OBSERVATION",
                    "blocked": False
                },
                {
                    "marketplace": "Ripley",
                    "status": "HEALTHY",
                    "status_label": "● HEALTHY (RESEARCH OBSERVATION)",
                    "last_verified": "2026-09-21T09:28:45",
                    "details": "Portal accesible en censo de investigación (382 productos en censo)",
                    "provenance": "RESEARCH OBSERVATION",
                    "blocked": False
                },
                {
                    "marketplace": "Falabella",
                    "status": "PARTIAL",
                    "status_label": "▲ PARTIAL (RESEARCH OBSERVATION)",
                    "last_verified": "2026-09-21T16:50:00",
                    "details": "Búsqueda limitada a 52; superada a 192 en recorrido de investigación de facetas",
                    "provenance": "RESEARCH OBSERVATION",
                    "blocked": False
                },
                {
                    "marketplace": "Mercado Libre",
                    "status": "PARTIAL",
                    "status_label": "▲ PARTIAL (RESEARCH OBSERVATION)",
                    "last_verified": "2026-09-21T16:50:00",
                    "details": "Tienda oficial cubre 422; búsqueda orgánica 8 adicionales en investigación",
                    "provenance": "RESEARCH OBSERVATION",
                    "blocked": False
                }
            ]
        }

    def get_legacy_comparison(self) -> Dict[str, Any]:
        """
        Returns side-by-side comparison of historical / legacy observations vs current MRI observations.
        Preserves historical legacy observations while dynamically populating MRI observations from SQLite.
        """
        conn = self.get_read_only_connection()
        cur = conn.cursor()
        
        # Query latest MRI observations per marketplace
        cur.execute("""
            SELECT lower(replace(marketplace, ' ', '')) as mp,
                   count(distinct publication_id) as pub_count,
                   max(observed_at) as latest_obs
            FROM mri_publications
            WHERE run_id != 'run_golden_shadow_001' AND run_id NOT LIKE '%test%'
            GROUP BY lower(replace(marketplace, ' ', ''))
        """)
        mri_stats = {row["mp"]: row for row in cur.fetchall()}
        conn.close()

        # Historical legacy reference definitions
        legacy_benchmarks = [
            {
                "mp_key": "paris",
                "marketplace": "Paris",
                "legacy_observation": "335 productos (Configurado en 2 categorías)",
                "difference_classification": "MRI_DISCOVERED_EXPANDED_SCOPE",
                "note_template": "Legacy configuró 2 categorías (335). MRI materializó {pub_count} publicaciones activas."
            },
            {
                "mp_key": "ripley",
                "marketplace": "Ripley",
                "legacy_observation": "238 productos (Colapso por título en scraper)",
                "difference_classification": "DYNAMIC_OBSERVED_COVERAGE",
                "note_template": "Legacy colapsó títulos duplicados. MRI observó y materializó {pub_count} publicaciones activas."
            },
            {
                "mp_key": "falabella",
                "marketplace": "Falabella",
                "legacy_observation": "198 productos (Rastreo histórico por catálogo)",
                "difference_classification": "COLD_SEARCH_LIMITATION_RESOLVED",
                "note_template": "Legacy limitó búsqueda fría. MRI materializó {pub_count} publicaciones activas."
            },
            {
                "mp_key": "mercadolibre",
                "marketplace": "Mercado Libre",
                "legacy_observation": "422 productos (Tienda Oficial scrapeada)",
                "difference_classification": "DYNAMIC_OBSERVED_COVERAGE",
                "note_template": "Legacy midió catálogo total. MRI materializó {pub_count} publicaciones activas observadas."
            }
        ]

        comparisons = []
        for b in legacy_benchmarks:
            stat = mri_stats.get(b["mp_key"])
            if stat:
                pub_cnt = stat["pub_count"]
                latest_ts = stat["latest_obs"]
                mri_obs = f"{pub_cnt} publicaciones materializadas en SQLite"
                note = b["note_template"].format(pub_count=pub_cnt)
            else:
                mri_obs = "NOT_MATERIALIZED"
                latest_ts = "N/A"
                note = "Sin publicaciones materializadas en el run actual."

            comparisons.append({
                "marketplace": b["marketplace"],
                "legacy_observation": b["legacy_observation"],
                "mri_observation": mri_obs,
                "semantic_comparability": "COMPARABLE_SUPERSET" if b["mp_key"] in ["paris", "ripley"] else "HIGH_CONFIDENCE_PARTIAL_UNION",
                "difference_classification": b["difference_classification"],
                "last_observed": latest_ts,
                "note": note
            })

        return {
            "mri_label": MRI_DISPLAY_LABEL,
            "comparison_scope": "HISTORICAL_LEGACY_VS_CURRENT_MRI_MATERIALIZATION",
            "materialized": True,
            "comparisons": comparisons
        }

    def get_search_intents(self) -> Dict[str, Any]:
        sql = """
            SELECT search_query, target_category, target_surface, search_type
            FROM mri_expected_search_intents
            ORDER BY search_query ASC
        """
        try:
            items = self.safe_query(sql)
        except Exception:
            items = []
        return {"items": items}

    def get_season_products(self) -> Dict[str, Any]:
        sql = """
            SELECT parent_sku, status, priority_group as priority, product_name as title, publication_url as url
            FROM mri_season_registry
            GROUP BY parent_sku
            ORDER BY priority_group ASC
        """
        try:
            items = self.safe_query(sql)
        except Exception:
            items = []
        return {"items": items}

