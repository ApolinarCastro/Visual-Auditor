"""
MRI V2 Additive Integration Foundation for Visual Auditor
Slice: ADDITIVE EVIDENCE + IDENTITY FOUNDATION

This module establishes:
1. Additive SQLite schema (versioned, append-only evidence, identity hierarchy, shadow snapshots)
2. Truth model versioning (LEGACY_VA, MRI_V2_SHADOW)
3. Shadow execution mode plumbing (DISABLED by default)
4. Mechanical Shadow Isolation (prevents shadow writes to legacy truth tables)
5. Additive identity relationships (Product -> Publications -> Variants, many-to-many categories)
6. Negative Knowledge enforcement (rejects forced %, max_insist=1, automatic SUSPECT->RECOVERED)
"""

import sqlite3
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

# Feature Flags
MRI_SHADOW_ENABLED: bool = False
SEARCH_INTENT_ENABLED: bool = False
SEASON_TRACKER_ENABLED: bool = False

# Truth Model Versions (Section 6: LEGACY_VA, MRI_V2_SHADOW)
TRUTH_MODEL_LEGACY_VA: str = "LEGACY_VA"
TRUTH_MODEL_MRI_SHADOW: str = "MRI_V2_SHADOW"
DEFAULT_TRUTH_MODEL: str = TRUTH_MODEL_LEGACY_VA

# Execution Modes (Section 7)
EXECUTION_MODE_LEGACY: str = "LEGACY"
EXECUTION_MODE_MRI_SHADOW: str = "MRI_SHADOW"

# Commercial State Statuses (Section 20)
STATUS_VERIFIED: str = "VERIFIED"
STATUS_OBSERVED: str = "OBSERVED"
STATUS_INFERRED: str = "INFERRED"
STATUS_PARTIAL: str = "PARTIAL"
STATUS_BLOCKED: str = "BLOCKED"
STATUS_STALE: str = "STALE"
STATUS_CONFLICT: str = "CONFLICT"
STATUS_UNVERIFIED: str = "UNVERIFIED"
STATUS_NOT_PUBLISHED: str = "NOT_PUBLISHED"
STATUS_NOT_FOUND: str = "NOT_FOUND"
STATUS_COMPLETE: str = "COMPLETE"
STATUS_LEGACY_OBSERVATION: str = "LEGACY_OBSERVATION"
STATUS_LEGACY_UNVERIFIED: str = "LEGACY_UNVERIFIED"

# Legacy Truth Tables that must NEVER be mutated by Shadow Mode
LEGACY_TABLES = {
    "audits",
    "alerts",
    "health_log",
    "selector_stats",
    "product_snapshots",
    "recovery_experiences",
    "source_health",
}

# New Additive Schema SQL Definitions
ADDITIVE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mri_truth_versions (
    version_key TEXT PRIMARY KEY,
    is_active INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mri_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    marketplace TEXT NOT NULL,
    brand TEXT NOT NULL,
    execution_mode TEXT NOT NULL,
    truth_model_version TEXT NOT NULL,
    terminal_state TEXT,
    source_method TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mri_evidence_ledger (
    evidence_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    brand TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    claim_value TEXT NOT NULL,
    source_surface TEXT NOT NULL,
    method TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    raw_reference TEXT,
    content_hash TEXT NOT NULL,
    truth_model_version TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES mri_runs(run_id)
);

CREATE TABLE IF NOT EXISTS mri_products (
    product_id TEXT PRIMARY KEY,
    canonical_brand TEXT NOT NULL,
    product_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mri_publications (
    publication_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    marketplace_product_id TEXT,
    canonical_url TEXT,
    status TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    run_id TEXT,
    position INTEGER,
    surface TEXT,
    FOREIGN KEY (product_id) REFERENCES mri_products(product_id)
);

CREATE TABLE IF NOT EXISTS mri_variants (
    variant_id TEXT PRIMARY KEY,
    publication_id TEXT NOT NULL,
    seller_sku TEXT,
    variant_title TEXT,
    status TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    FOREIGN KEY (publication_id) REFERENCES mri_publications(publication_id)
);

CREATE TABLE IF NOT EXISTS mri_categories (
    category_id TEXT PRIMARY KEY,
    marketplace TEXT NOT NULL,
    category_name TEXT NOT NULL,
    canonical_url TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mri_publication_categories (
    publication_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    status TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (publication_id, category_id),
    FOREIGN KEY (publication_id) REFERENCES mri_publications(publication_id),
    FOREIGN KEY (category_id) REFERENCES mri_categories(category_id)
);

CREATE TABLE IF NOT EXISTS mri_prices (
    price_id TEXT PRIMARY KEY,
    publication_id TEXT NOT NULL,
    variant_id TEXT,
    regular_price REAL,
    sale_price REAL,
    effective_price REAL,
    currency TEXT NOT NULL DEFAULT 'CLP',
    observed_at TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (publication_id) REFERENCES mri_publications(publication_id),
    FOREIGN KEY (evidence_id) REFERENCES mri_evidence_ledger(evidence_id)
);

CREATE TABLE IF NOT EXISTS mri_shadow_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    publication_id TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    brand TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES mri_runs(run_id),
    FOREIGN KEY (publication_id) REFERENCES mri_publications(publication_id),
    FOREIGN KEY (evidence_id) REFERENCES mri_evidence_ledger(evidence_id)
    FOREIGN KEY (evidence_id) REFERENCES mri_evidence_ledger(evidence_id)
);

CREATE TABLE IF NOT EXISTS mri_historical_publications (
    history_id TEXT PRIMARY KEY,
    publication_id TEXT NOT NULL,
    run_id TEXT,
    canonical_url TEXT,
    position INTEGER,
    surface TEXT,
    observed_at TEXT NOT NULL,
    FOREIGN KEY (publication_id) REFERENCES mri_publications(publication_id)
);

CREATE TABLE IF NOT EXISTS mri_historical_categories (
    history_id TEXT PRIMARY KEY,
    category_id TEXT NOT NULL,
    run_id TEXT,
    canonical_url TEXT,
    observed_at TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES mri_categories(category_id)
);

CREATE TABLE IF NOT EXISTS mri_historical_publication_categories (
    history_id TEXT PRIMARY KEY,
    publication_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    run_id TEXT,
    observed_at TEXT NOT NULL,
    FOREIGN KEY (publication_id) REFERENCES mri_publications(publication_id),
    FOREIGN KEY (category_id) REFERENCES mri_categories(category_id)
);

CREATE TABLE IF NOT EXISTS mri_expected_search_intents (
    intent_id TEXT PRIMARY KEY,
    search_set_version TEXT NOT NULL,
    product_type TEXT NOT NULL,
    intent TEXT NOT NULL,
    priority TEXT NOT NULL,
    level TEXT NOT NULL,
    compatible_products INTEGER NOT NULL DEFAULT 0,
    marketplace TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mri_season_registry (
    season_entry_id TEXT PRIMARY KEY,
    season_code TEXT NOT NULL,
    group_id TEXT NOT NULL,
    sku_parent TEXT NOT NULL,
    sku_child TEXT NOT NULL,
    product_name TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    expected_listing_id TEXT,
    expected_url TEXT,
    launch_status TEXT NOT NULL DEFAULT 'EXPECTED',
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (sku_parent) REFERENCES mri_products(product_id)
);
"""


class ShadowIsolationViolationError(PermissionError):
    """Raised when Shadow Mode attempts to write to legacy truth tables."""
    pass


class NegativeKnowledgeViolationError(ValueError):
    """Raised when an operation violates the Negative Knowledge Registry."""
    pass


def assert_mechanical_shadow_isolation(target_table: str, execution_mode: str) -> None:
    """
    Enforces mechanical isolation: MRI_SHADOW cannot write to legacy tables.
    """
    if execution_mode in (EXECUTION_MODE_MRI_SHADOW, TRUTH_MODEL_MRI_SHADOW):
        if target_table.lower() in LEGACY_TABLES:
            raise ShadowIsolationViolationError(
                f"Mechanical Isolation Violation: Execution mode '{execution_mode}' "
                f"is strictly forbidden from writing to legacy table '{target_table}'."
            )


def validate_negative_knowledge(claim: Dict[str, Any]) -> None:
    """
    Validates claims against Negative Knowledge constraints:
    1. No forced visibility percentage without DOM proof.
    2. No max_insist=1 completeness assertion.
    3. No automatic SUSPECT -> RECOVERED transition without fresh multi-surface verification.
    """
    if "forced_visibility_pct" in claim:
        raise NegativeKnowledgeViolationError(
            "Negative Knowledge Violation: Forced visibility percentage is prohibited."
        )
    if claim.get("completeness_assertion") and claim.get("max_insist", 0) <= 1:
        raise NegativeKnowledgeViolationError(
            "Negative Knowledge Violation: max_insist=1 completeness assertion is prohibited."
        )
    if claim.get("previous_state") == "SUSPECT" and claim.get("target_state") == "RECOVERED":
        if not claim.get("multi_surface_verified", False):
            raise NegativeKnowledgeViolationError(
                "Negative Knowledge Violation: Automatic SUSPECT->RECOVERED transition without multi-surface proof."
            )


def init_additive_schema(conn: sqlite3.Connection) -> None:
    """
    Initializes the additive schema idempotently without modifying any legacy table.
    """
    cursor = conn.cursor()
    cursor.executescript(ADDITIVE_SCHEMA_SQL)
    
    # Initialize version rows if not present
    cursor.execute(
        "INSERT OR IGNORE INTO mri_truth_versions (version_key, is_active, description, created_at) "
        "VALUES (?, ?, ?, ?)",
        (TRUTH_MODEL_LEGACY_VA, 1, "Visual Auditor Legacy Truth Model (Active Default)", datetime.now().isoformat())
    )
    cursor.execute(
        "INSERT OR IGNORE INTO mri_truth_versions (version_key, is_active, description, created_at) "
        "VALUES (?, ?, ?, ?)",
        (TRUTH_MODEL_MRI_SHADOW, 0, "MRI V2 Shadow Truth Model (Zero Commercial Cutover)", datetime.now().isoformat())
    )
    conn.commit()


def append_evidence(
    conn: sqlite3.Connection,
    run_id: str,
    marketplace: str,
    brand: str,
    claim_type: str,
    claim_value: str,
    source_surface: str,
    method: str,
    confidence: float,
    status: str,
    raw_reference: Optional[str] = None,
    observed_at: Optional[str] = None,
    truth_model_version: str = TRUTH_MODEL_MRI_SHADOW,
) -> str:
    """
    Appends an immutable record to the evidence ledger.
    """
    if observed_at is None:
        observed_at = datetime.now().isoformat()
    
    content_raw = f"{run_id}|{marketplace}|{brand}|{claim_type}|{claim_value}|{source_surface}|{method}|{observed_at}"
    content_hash = hashlib.sha256(content_raw.encode("utf-8")).hexdigest()
    evidence_id = f"ev_{content_hash[:16]}"

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO mri_evidence_ledger (
            evidence_id, run_id, marketplace, brand, claim_type, claim_value,
            source_surface, method, observed_at, confidence, status, raw_reference,
            content_hash, truth_model_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence_id, run_id, marketplace, brand, claim_type, claim_value,
            source_surface, method, observed_at, confidence, status, raw_reference,
            content_hash, truth_model_version
        )
    )
    conn.commit()
    return evidence_id


def persist_identity(
    conn: sqlite3.Connection,
    product_id: str,
    brand: str,
    publication_id: str,
    marketplace: str,
    marketplace_product_id: str,
    canonical_url: str,
    variants: List[Dict[str, Any]],
    status: str = STATUS_OBSERVED,
    observed_at: Optional[str] = None,
    run_id: Optional[str] = None,
    position: Optional[int] = None,
    surface: Optional[str] = None,
) -> None:
    """
    Persists identity hierarchy: 1 Product -> 1..N Publications -> 1..N Variants.
    """
    if observed_at is None:
        observed_at = datetime.now().isoformat()
    
    cursor = conn.cursor()
    
    # 1. Product level
    cursor.execute(
        """
        INSERT OR IGNORE INTO mri_products (product_id, canonical_brand, product_status, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (product_id, brand, status, observed_at)
    )
    
    # 2. Publication level
    cursor.execute(
        """
        INSERT OR REPLACE INTO mri_publications (
            publication_id, product_id, marketplace, marketplace_product_id, canonical_url, status, observed_at, run_id, position, surface
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (publication_id, product_id, marketplace, marketplace_product_id, canonical_url, status, observed_at, run_id, position, surface)
    )
    
    # 2.5 Historical Publication
    import uuid
    history_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO mri_historical_publications (
            history_id, publication_id, run_id, canonical_url, position, surface, observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (history_id, publication_id, run_id, canonical_url, position, surface, observed_at)
    )
    
    # 3. Variants level
    for var in variants:
        variant_id = var.get("variant_id")
        seller_sku = var.get("seller_sku")
        variant_title = var.get("variant_title")
        v_status = var.get("status", status)
        cursor.execute(
            """
            INSERT OR REPLACE INTO mri_variants (
                variant_id, publication_id, seller_sku, variant_title, status, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (variant_id, publication_id, seller_sku, variant_title, v_status, observed_at)
        )
    
    conn.commit()


def assign_categories(
    conn: sqlite3.Connection,
    publication_id: str,
    categories: List[Dict[str, str]],
    observed_at: Optional[str] = None,
) -> None:
    """
    Associates a publication with multiple categories (many-to-many).
    """
    if observed_at is None:
        observed_at = datetime.now().isoformat()
        
    cursor = conn.cursor()
    for cat in categories:
        cat_id = cat["category_id"]
        cat_name = cat["category_name"]
        marketplace = cat["marketplace"]
        canon_url = cat.get("canonical_url", "")
        status = cat.get("status", STATUS_OBSERVED)
        
        cursor.execute(
            """
            INSERT OR IGNORE INTO mri_categories (category_id, marketplace, category_name, canonical_url, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cat_id, marketplace, cat_name, canon_url, observed_at)
        )
        
        # We also need to update mri_categories if canonical_url changed but we don't want to break history.
        # So we just update the canonical_url in the main table to be the latest
        cursor.execute(
            """
            UPDATE mri_categories SET canonical_url = ?, created_at = ? WHERE category_id = ?
            """,
            (canon_url, observed_at, cat_id)
        )

        run_id = cat.get("run_id")
        import uuid
        history_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO mri_historical_categories (
                history_id, category_id, run_id, canonical_url, observed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (history_id, cat_id, run_id, canon_url, observed_at)
        )
        
        cursor.execute(
            """
            INSERT OR REPLACE INTO mri_publication_categories (publication_id, category_id, status, observed_at)
            VALUES (?, ?, ?, ?)
            """,
            (publication_id, cat_id, status, observed_at)
        )
        
        # Preserve historical junction
        j_history_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO mri_historical_publication_categories (
                history_id, publication_id, category_id, run_id, observed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (j_history_id, publication_id, cat_id, run_id, observed_at)
        )
    conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Search Intent & Season Tracker Additive Functions
# ──────────────────────────────────────────────────────────────────────────────

def import_expected_search_intents(
    conn: sqlite3.Connection,
    csv_path: str,
    search_set_version: str = "SS2026_V1",
) -> Dict[str, Any]:
    """
    Imports search intents from validated CSV into mri_expected_search_intents.
    No scraping, no new crawlers, no AI-generated keywords.
    """
    import csv
    cursor = conn.cursor()
    imported_count = 0
    unique_intents = set()
    principal_count = 0
    secondary_count = 0
    
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            busqueda = row["BUSQUEDA"].strip()
            prioridad = row["PRIORIDAD"].strip()
            tipo = row["TIPO"].strip()
            nivel = row["NIVEL"].strip()
            compat = int(row.get("PRODUCTOS_COMPATIBLES", 0))
            
            raw_key = f"{search_set_version}|{tipo}|{busqueda}"
            intent_id = f"intent_{hashlib.sha256(raw_key.encode('utf-8')).hexdigest()[:16]}"
            
            cursor.execute(
                """
                INSERT OR REPLACE INTO mri_expected_search_intents (
                    intent_id, search_set_version, product_type, intent,
                    priority, level, compatible_products, marketplace,
                    active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent_id, search_set_version, tipo, busqueda,
                    prioridad, nivel, compat, None, 1, datetime.now().isoformat()
                )
            )
            imported_count += 1
            unique_intents.add(busqueda)
            if nivel == "PRINCIPAL":
                principal_count += 1
            elif nivel == "SECUNDARIA":
                secondary_count += 1
                
    conn.commit()
    return {
        "search_set_version": search_set_version,
        "imported": imported_count,
        "unique": len(unique_intents),
        "principal": principal_count,
        "secondary": secondary_count,
    }


def import_pilot_season_products(
    conn: sqlite3.Connection,
    pilot_csv_path: str,
    season_code: str = "2026_SS",
) -> Dict[str, Any]:
    """
    Imports pilot products from validated pilot_20_products.csv into mri_season_registry.
    Preserves SKU parent -> SKU child hierarchy, listing IDs, and URLs without acquisition.
    """
    import csv
    cursor = conn.cursor()
    parents_by_group: Dict[str, set] = {"GRUPO 1": set(), "GRUPO 2": set(), "GRUPO 3": set(), "GRUPO 4": set()}
    total_children = 0
    created_at = datetime.now().isoformat()
    
    with open(pilot_csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            group = row["group"].strip()
            if group not in parents_by_group:
                # Exclude any group not in 1-4
                continue
                
            sku_parent = row["sku_parent"].strip()
            product_name = row["product_name"].strip()
            parents_by_group[group].add(sku_parent)
            
            # Ensure product exists in mri_products to satisfy foreign key
            cursor.execute(
                """
                INSERT OR IGNORE INTO mri_products (product_id, canonical_brand, product_status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (sku_parent, "Nicopoly", "PUBLISHED", created_at)
            )
            
            children = [c.strip() for c in row["variants_sku_children"].split(";") if c.strip()]
            marketplaces = [
                ("Ripley", row.get("ripley_id", ""), row.get("ripley_link", "")),
                ("Paris", row.get("paris_id", ""), row.get("paris_link", "")),
                ("Mercado Libre", row.get("meli_id", ""), row.get("meli_link", "")),
                ("Falabella", row.get("falabella_id", ""), row.get("falabella_link", "")),
                ("Nicopoly", row.get("sitio_propio_sku", ""), row.get("sitio_propio_link", "")),
            ]
            
            for child in children:
                total_children += 1
                for mp_name, exp_id, exp_url in marketplaces:
                    if not exp_id and not exp_url:
                        continue
                    entry_raw = f"{season_code}|{group}|{sku_parent}|{child}|{mp_name}"
                    season_entry_id = f"sea_{hashlib.sha256(entry_raw.encode('utf-8')).hexdigest()[:16]}"
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO mri_season_registry (
                            season_entry_id, season_code, group_id, sku_parent,
                            sku_child, product_name, marketplace, expected_listing_id,
                            expected_url, launch_status, active, notes, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            season_entry_id, season_code, group, sku_parent,
                            child, product_name, mp_name, exp_id, exp_url,
                            "PUBLISHED", 1, None, created_at
                        )
                    )
                    
    conn.commit()
    return {
        "season_code": season_code,
        "pilot_parents": sum(len(p) for p in parents_by_group.values()),
        "pilot_children": total_children,
        "group_1_parents": len(parents_by_group["GRUPO 1"]),
        "group_2_parents": len(parents_by_group["GRUPO 2"]),
        "group_3_parents": len(parents_by_group["GRUPO 3"]),
        "group_4_parents": len(parents_by_group["GRUPO 4"]),
        "group_5_processed": 0,
        "group_6_processed": 0,
    }


def get_season_product_observations(
    conn: sqlite3.Connection,
    sku_parent: str,
) -> List[Dict[str, Any]]:
    """
    Retrieves latest observations for a season product using verified joins.
    Explicitly preserves publication_id != evidence_id relationship.
    If no observation exists, marks status as NO_OBSERVATION without converting to NOT_FOUND.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            sr.season_code,
            sr.group_id,
            sr.sku_parent,
            sr.sku_child,
            sr.product_name,
            sr.marketplace,
            sr.expected_listing_id,
            sr.expected_url,
            pub.publication_id,
            pub.marketplace_product_id,
            pub.canonical_url,
            hist.position,
            hist.surface,
            hist.run_id,
            hist.observed_at,
            el.evidence_id,
            el.confidence,
            el.status AS evidence_status
        FROM mri_season_registry sr
        LEFT JOIN mri_publications pub 
            ON sr.sku_parent = pub.product_id AND sr.marketplace = pub.marketplace
        LEFT JOIN mri_historical_publications hist 
            ON pub.publication_id = hist.publication_id
        LEFT JOIN mri_shadow_snapshots ss 
            ON pub.publication_id = ss.publication_id AND hist.run_id = ss.run_id
        LEFT JOIN mri_evidence_ledger el 
            ON ss.evidence_id = el.evidence_id
        WHERE sr.sku_parent = ?
        ORDER BY hist.observed_at DESC
        """,
        (sku_parent,)
    )
    
    rows = cursor.fetchall()
    results = []
    for r in rows:
        results.append({
            "season_code": r[0],
            "group_id": r[1],
            "sku_parent": r[2],
            "sku_child": r[3],
            "product_name": r[4],
            "marketplace": r[5],
            "expected_listing_id": r[6],
            "expected_url": r[7],
            "publication_id": r[8],
            "marketplace_product_id": r[9],
            "canonical_url": r[10],
            "position": r[11],
            "surface": r[12],
            "run_id": r[13],
            "observed_at": r[14],
            "evidence_id": r[15],
            "confidence": r[16],
            "evidence_status": r[17] if r[17] is not None else "NO_OBSERVATION"
        })
    return results

