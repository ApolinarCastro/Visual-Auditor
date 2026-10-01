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
