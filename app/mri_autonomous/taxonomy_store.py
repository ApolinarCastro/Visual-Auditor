"""MRI taxonomy foundation: versioned additive schema and idempotent persistence.

This module is deliberately additive. It does not alter mri_categories, the
legacy consumers, the Paris baseline, or any historical table. The production
database is only touched by an explicit caller after StorageGuard authorization.
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

TAXONOMY_SCHEMA_VERSION = 1
MIGRATIONS_TABLE = "mri_taxonomy_schema_migrations"
NODES_TABLE = "mri_taxonomy_nodes"
HISTORY_TABLE = "mri_taxonomy_node_history"
FRONTIER_TABLE = "mri_taxonomy_frontier_summary"
LEARNING_TABLE = "mri_taxonomy_learning"

TAXONOMY_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS {NODES_TABLE} (
    marketplace TEXT NOT NULL,
    category_id TEXT NOT NULL,
    category_name TEXT NOT NULL,
    parent_category_id TEXT,
    hierarchical_path TEXT,
    canonical_url TEXT,
    taxonomy_source TEXT NOT NULL,
    source_evidence TEXT,
    discovered_at TEXT NOT NULL,
    last_verified_at TEXT,
    discovery_status TEXT NOT NULL DEFAULT 'NOT_VERIFIED',
    run_id TEXT,
    PRIMARY KEY (marketplace, category_id),
    UNIQUE (category_id, marketplace),
    FOREIGN KEY (parent_category_id, marketplace)
        REFERENCES {NODES_TABLE}(category_id, marketplace)
);

CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    marketplace TEXT NOT NULL,
    category_id TEXT NOT NULL,
    category_name TEXT NOT NULL,
    parent_category_id TEXT,
    hierarchical_path TEXT,
    canonical_url TEXT,
    taxonomy_source TEXT NOT NULL,
    source_evidence TEXT,
    discovered_at TEXT NOT NULL,
    last_verified_at TEXT,
    discovery_status TEXT NOT NULL,
    run_id TEXT,
    recorded_at TEXT NOT NULL,
    UNIQUE (marketplace, category_id, run_id)
);

CREATE TABLE IF NOT EXISTS {FRONTIER_TABLE} (
    marketplace TEXT NOT NULL,
    run_id TEXT NOT NULL,
    roots_discovered INTEGER NOT NULL DEFAULT 0,
    nodes_discovered INTEGER NOT NULL DEFAULT 0,
    edges_verified INTEGER NOT NULL DEFAULT 0,
    leaves_discovered INTEGER NOT NULL DEFAULT 0,
    frontier_pending INTEGER NOT NULL DEFAULT 0,
    frontier_blocked INTEGER NOT NULL DEFAULT 0,
    frontier_exhausted INTEGER NOT NULL DEFAULT 0,
    source_completeness TEXT NOT NULL DEFAULT 'NOT_VERIFIED',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (marketplace, run_id)
);

CREATE TABLE IF NOT EXISTS {LEARNING_TABLE} (
    knowledge_id TEXT PRIMARY KEY,
    marketplace TEXT NOT NULL,
    knowledge_type TEXT NOT NULL,
    observation TEXT NOT NULL,
    source_evidence TEXT,
    first_seen TEXT,
    last_verified TEXT,
    confidence TEXT NOT NULL DEFAULT 'OBSERVED',
    validation_status TEXT NOT NULL DEFAULT 'NOT_VERIFIED',
    supersedes TEXT
);
"""

SCHEMA_SHA256 = hashlib.sha256(TAXONOMY_SCHEMA_SQL.encode("utf-8")).hexdigest()


class TaxonomyMigrationError(RuntimeError):
    """The taxonomy migration cannot be applied safely."""


class TaxonomyHierarchyError(ValueError):
    """Hierarchy is cyclic, cross-market, or references an unknown parent."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_taxonomy_migration(conn: sqlite3.Connection) -> int:
    """Apply the additive taxonomy schema transactionally and idempotently.

    Existing tables and rows are never dropped or rewritten. The migration is
    recorded by version and checksum; re-running it is a no-op.
    """
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        # executescript() implicitly commits, which would break rollback and
        # idempotent migration semantics. Execute each DDL statement explicitly
        # inside the same transaction.
        for statement in (part.strip() for part in TAXONOMY_SCHEMA_SQL.split(";")):
            if statement:
                conn.execute(statement)
        row = conn.execute(
            f"SELECT checksum FROM {MIGRATIONS_TABLE} WHERE version = ?",
            (TAXONOMY_SCHEMA_VERSION,),
        ).fetchone()
        if row is not None and row[0] != SCHEMA_SHA256:
            raise TaxonomyMigrationError(
                "taxonomy schema checksum mismatch for version "
                f"{TAXONOMY_SCHEMA_VERSION}: existing={row[0]} current={SCHEMA_SHA256}"
            )
        conn.execute(
            f"INSERT OR IGNORE INTO {MIGRATIONS_TABLE} (version, applied_at, checksum) "
            "VALUES (?, ?, ?)",
            (TAXONOMY_SCHEMA_VERSION, _now(), SCHEMA_SHA256),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return TAXONOMY_SCHEMA_VERSION


def migrate_database(db_path: str | Path) -> int:
    """Migrate a caller-authorized database path, preserving existing data."""
    from app.mri_autonomous.storage_guard import StorageConfig

    path = Path(db_path)
    StorageConfig.assert_write_allowed(path)
    conn = sqlite3.connect(str(path))
    try:
        return apply_taxonomy_migration(conn)
    finally:
        conn.close()


@dataclass(frozen=True)
class TaxonomyNode:
    marketplace: str
    category_id: str
    category_name: str
    parent_category_id: Optional[str] = None
    hierarchical_path: Optional[str] = None
    canonical_url: Optional[str] = None
    taxonomy_source: str = "DISCOVERY"
    source_evidence: Optional[str] = None
    discovered_at: Optional[str] = None
    last_verified_at: Optional[str] = None
    discovery_status: str = "NOT_VERIFIED"
    run_id: Optional[str] = None


def _validate_nodes(nodes: Sequence[TaxonomyNode]) -> None:
    by_key = {(n.marketplace, n.category_id): n for n in nodes}
    for n in nodes:
        if not n.marketplace or not n.category_id:
            raise TaxonomyHierarchyError("marketplace and category_id are required")
        if n.parent_category_id:
            if n.parent_category_id == n.category_id:
                raise TaxonomyHierarchyError(f"self-parent category: {n.category_id}")
            if (n.marketplace, n.parent_category_id) not in by_key:
                raise TaxonomyHierarchyError(
                    f"parent {n.parent_category_id} not present in marketplace "
                    f"{n.marketplace}; persist parents before children or mark NOT_VERIFIED"
                )
    # Cycle detection over the submitted snapshot.
    state: dict[tuple[str, str], int] = {}
    def visit(key: tuple[str, str]) -> None:
        mark = state.get(key, 0)
        if mark == 1:
            raise TaxonomyHierarchyError(f"cycle detected at {key[0]}:{key[1]}")
        if mark == 2:
            return
        state[key] = 1
        node = by_key[key]
        if node.parent_category_id:
            visit((node.marketplace, node.parent_category_id))
        state[key] = 2
    for key in by_key:
        visit(key)


def _node_values(n: TaxonomyNode) -> tuple:
    discovered = n.discovered_at or _now()
    return (
        n.marketplace, n.category_id, n.category_name, n.parent_category_id,
        n.hierarchical_path, n.canonical_url, n.taxonomy_source,
        n.source_evidence, discovered, n.last_verified_at or discovered,
        n.discovery_status, n.run_id,
    )


def persist_taxonomy_snapshot(
    conn: sqlite3.Connection,
    marketplace: str,
    run_id: str,
    categories: Iterable[dict[str, Any] | TaxonomyNode],
    *,
    taxonomy_source: str = "DISCOVERY",
    source_evidence: Optional[str] = None,
    discovered_at: Optional[str] = None,
    statuses: Optional[dict[str, str]] = None,
) -> dict[str, int]:
    """Upsert a taxonomy snapshot without deleting prior knowledge.

    Parents must be part of the snapshot. Unknown/hypothesis parents must be
    passed as None with discovery_status=NOT_VERIFIED; no parent is invented
    from slugs.
    """
    apply_taxonomy_migration(conn)
    statuses = statuses or {}
    nodes: list[TaxonomyNode] = []
    for item in categories:
        if isinstance(item, TaxonomyNode):
            n = item
        else:
            cid = item.get("category_id") or item.get("id")
            if not cid:
                continue
            n = TaxonomyNode(
                marketplace=marketplace,
                category_id=str(cid),
                category_name=str(item.get("name") or item.get("category_name") or cid),
                parent_category_id=(str(item["parent_id"]) if item.get("parent_id") else None),
                hierarchical_path=item.get("hierarchical_path") or item.get("path"),
                canonical_url=item.get("url") or item.get("canonical_url"),
                taxonomy_source=str(item.get("source") or taxonomy_source),
                source_evidence=str(item.get("evidence") or source_evidence or ""),
                discovered_at=item.get("discovered_at") or discovered_at,
                last_verified_at=item.get("last_verified_at") or discovered_at,
                discovery_status=str(statuses.get(str(cid)) or item.get("discovery_status") or "NOT_VERIFIED"),
                run_id=run_id,
            )
        if n.marketplace != marketplace:
            raise TaxonomyHierarchyError("all nodes in a snapshot must share marketplace")
        nodes.append(n)
    _validate_nodes(nodes)
    now = _now()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for n in nodes:
            vals = _node_values(n)
            conn.execute(
                f"""INSERT INTO {NODES_TABLE}
                (marketplace, category_id, category_name, parent_category_id,
                 hierarchical_path, canonical_url, taxonomy_source, source_evidence,
                 discovered_at, last_verified_at, discovery_status, run_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(marketplace, category_id) DO UPDATE SET
                    category_name=excluded.category_name,
                    parent_category_id=excluded.parent_category_id,
                    hierarchical_path=excluded.hierarchical_path,
                    canonical_url=excluded.canonical_url,
                    taxonomy_source=excluded.taxonomy_source,
                    source_evidence=excluded.source_evidence,
                    last_verified_at=excluded.last_verified_at,
                    discovery_status=excluded.discovery_status,
                    run_id=excluded.run_id""",
                vals,
            )
            conn.execute(
                f"""INSERT OR IGNORE INTO {HISTORY_TABLE}
                (marketplace, category_id, category_name, parent_category_id,
                 hierarchical_path, canonical_url, taxonomy_source, source_evidence,
                 discovered_at, last_verified_at, discovery_status, run_id, recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                vals + (now,),
            )
        # Frontier summary derived only from the submitted snapshot.
        ids = {(n.marketplace, n.category_id) for n in nodes}
        parents = {n.parent_category_id for n in nodes if n.parent_category_id}
        roots = sum(1 for n in nodes if not n.parent_category_id)
        edges = sum(1 for n in nodes if n.parent_category_id)
        leaves = sum(1 for n in nodes if n.category_id not in parents)
        status_counts = {"COMPLETE": 0, "BLOCKED": 0, "PENDING": 0, "NOT_VERIFIED": 0}
        for n in nodes:
            s = str(n.discovery_status).upper()
            if s in status_counts:
                status_counts[s] += 1
        conn.execute(
            f"""INSERT INTO {FRONTIER_TABLE}
            (marketplace, run_id, roots_discovered, nodes_discovered, edges_verified,
             leaves_discovered, frontier_pending, frontier_blocked, frontier_exhausted,
             source_completeness, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(marketplace, run_id) DO UPDATE SET
                roots_discovered=excluded.roots_discovered,
                nodes_discovered=excluded.nodes_discovered,
                edges_verified=excluded.edges_verified,
                leaves_discovered=excluded.leaves_discovered,
                frontier_pending=excluded.frontier_pending,
                frontier_blocked=excluded.frontier_blocked,
                frontier_exhausted=excluded.frontier_exhausted,
                source_completeness=excluded.source_completeness,
                updated_at=excluded.updated_at""",
            (marketplace, run_id, roots, len(nodes), edges, leaves,
             status_counts["PENDING"] + status_counts["NOT_VERIFIED"],
             status_counts["BLOCKED"], status_counts["COMPLETE"],
             "NOT_VERIFIED", now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"nodes": len(nodes), "roots": roots, "edges": edges, "leaves": leaves,
            "blocked": status_counts["BLOCKED"], "complete": status_counts["COMPLETE"]}


def record_taxonomy_learning(
    conn: sqlite3.Connection,
    *,
    knowledge_id: str,
    marketplace: str,
    knowledge_type: str,
    observation: str,
    source_evidence: str,
    first_seen: Optional[str] = None,
    last_verified: Optional[str] = None,
    confidence: str = "OBSERVED",
    validation_status: str = "NOT_VERIFIED",
    supersedes: Optional[str] = None,
) -> None:
    """Store reusable knowledge without promoting observations to rules."""
    apply_taxonomy_migration(conn)
    conn.execute(
        f"""INSERT INTO {LEARNING_TABLE}
        (knowledge_id, marketplace, knowledge_type, observation, source_evidence,
         first_seen, last_verified, confidence, validation_status, supersedes)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(knowledge_id) DO UPDATE SET
            observation=excluded.observation,
            source_evidence=excluded.source_evidence,
            last_verified=excluded.last_verified,
            confidence=excluded.confidence,
            validation_status=excluded.validation_status,
            supersedes=excluded.supersedes""",
        (knowledge_id, marketplace, knowledge_type, observation, source_evidence,
         first_seen or _now(), last_verified or _now(), confidence,
         validation_status, supersedes),
    )
    conn.commit()


def persist_taxonomy_result(
    db_path: str | Path,
    marketplace: str,
    result: dict[str, Any],
    *,
    run_id: str,
) -> dict[str, int]:
    """Persist one taxonomy result after explicit StorageGuard authorization."""
    from app.mri_autonomous.storage_guard import StorageConfig

    path = Path(db_path)
    StorageConfig.assert_write_allowed(path)
    categories = result.get("categories") or []
    statuses = {str(c.get("category_id")): str(c.get("discovery_status") or "NOT_VERIFIED")
                for c in categories if isinstance(c, dict)}
    conn = sqlite3.connect(str(path))
    try:
        return persist_taxonomy_snapshot(
            conn, marketplace, run_id, categories,
            taxonomy_source=str(result.get("source") or "DISCOVERY"),
            source_evidence=str(result.get("source") or ""),
            statuses=statuses,
        )
    finally:
        conn.close()


__all__ = [
    "TAXONOMY_SCHEMA_VERSION", "TAXONOMY_SCHEMA_SQL", "SCHEMA_SHA256",
    "TaxonomyMigrationError", "TaxonomyHierarchyError", "TaxonomyNode",
    "apply_taxonomy_migration", "migrate_database", "persist_taxonomy_snapshot",
    "persist_taxonomy_result", "record_taxonomy_learning",
]
