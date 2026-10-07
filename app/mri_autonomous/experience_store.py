import os
import json
import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "mri_experience.db")

class ExperienceStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS experience (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marketplace TEXT NOT NULL,
                brand TEXT NOT NULL,
                knowledge_type TEXT NOT NULL,
                value TEXT NOT NULL,
                source_url TEXT,
                page_type TEXT,
                taxonomy_type TEXT,
                parent_identity TEXT,
                discovery_method TEXT,
                extractor_used TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_success_at TEXT,
                last_failure_at TEXT,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                consecutive_failures INTEGER DEFAULT 0,
                confidence REAL DEFAULT 1.0,
                status TEXT NOT NULL,
                evidence_reference TEXT,
                UNIQUE(marketplace, brand, knowledge_type, value)
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marketplace TEXT NOT NULL,
                brand TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                surface TEXT,
                hypothesis TEXT,
                attempt INTEGER,
                result TEXT,
                failure_type TEXT,
                evidence TEXT,
                timestamp TEXT NOT NULL,
                confidence REAL DEFAULT 0.0,
                last_validated_at TEXT,
                UNIQUE(marketplace, brand, strategy_id)
            )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_decision (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    marketplace TEXT NOT NULL,
                    brand TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    selected INTEGER NOT NULL,
                    reason TEXT,
                    alternative_strategy_id TEXT,
                    expected_outcome TEXT,
                    timestamp TEXT NOT NULL,
                    UNIQUE(marketplace, brand, strategy_id, timestamp)
                )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS taxonomy_graph (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marketplace TEXT NOT NULL,
                parent_value TEXT NOT NULL,
                child_value TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                last_verified TEXT NOT NULL,
                active_currently INTEGER DEFAULT 1,
                evidence TEXT,
                UNIQUE(marketplace, parent_value, child_value, relation_type)
            )
            """)
            conn.commit()

    def record_experience(
        self,
        marketplace: str,
        brand: str,
        knowledge_type: str,
        value: str,
        source_url: Optional[str] = None,
        page_type: Optional[str] = None,
        taxonomy_type: Optional[str] = None,
        parent_identity: Optional[str] = None,
        discovery_method: Optional[str] = None,
        extractor_used: Optional[str] = None,
        status: str = "CANDIDATE",
        is_success: bool = True,
        evidence_reference: Optional[str] = None
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM experience WHERE marketplace = ? AND brand = ? AND knowledge_type = ? AND value = ?",
                (marketplace, brand, knowledge_type, value)
            )
            row = cursor.fetchone()

            if row:
                row_dict = dict(row)
                s_count = row_dict["success_count"] + (1 if is_success else 0)
                f_count = row_dict["failure_count"] + (0 if is_success else 1)
                c_failures = 0 if is_success else (row_dict["consecutive_failures"] + 1)
                last_succ = now if is_success else row_dict["last_success_at"]
                last_fail = row_dict["last_failure_at"] if is_success else now

                # Simple score rule
                if c_failures >= 3:
                    new_status = "FAILED"
                elif is_success and status in ["VALIDATED", "LAST_GOOD"]:
                    new_status = status
                elif is_success:
                    new_status = "VALIDATED"
                else:
                    new_status = row_dict["status"]

                cursor.execute("""
                    UPDATE experience SET
                        source_url = COALESCE(?, source_url),
                        page_type = COALESCE(?, page_type),
                        taxonomy_type = COALESCE(?, taxonomy_type),
                        parent_identity = COALESCE(?, parent_identity),
                        discovery_method = COALESCE(?, discovery_method),
                        extractor_used = COALESCE(?, extractor_used),
                        last_seen_at = ?,
                        last_success_at = ?,
                        last_failure_at = ?,
                        success_count = ?,
                        failure_count = ?,
                        consecutive_failures = ?,
                        status = ?,
                        evidence_reference = COALESCE(?, evidence_reference)
                    WHERE marketplace = ? AND brand = ? AND knowledge_type = ? AND value = ?
                """, (
                    source_url, page_type, taxonomy_type, parent_identity, discovery_method, extractor_used,
                    now, last_succ, last_fail, s_count, f_count, c_failures, new_status, evidence_reference,
                    marketplace, brand, knowledge_type, value
                ))
            else:
                initial_status = "VALIDATED" if is_success else "CANDIDATE"
                if status in ["LAST_GOOD", "VALIDATED", "FAILED", "STALE", "RETIRED"]:
                    initial_status = status

                cursor.execute("""
                    INSERT INTO experience (
                        marketplace, brand, knowledge_type, value, source_url, page_type,
                        taxonomy_type, parent_identity, discovery_method, extractor_used,
                        first_seen_at, last_seen_at, last_success_at, last_failure_at,
                        success_count, failure_count, consecutive_failures, confidence,
                        status, evidence_reference
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    marketplace, brand, knowledge_type, value, source_url, page_type,
                    taxonomy_type, parent_identity, discovery_method, extractor_used,
                    now, now, (now if is_success else None), (None if is_success else now),
                    (1 if is_success else 0), (0 if is_success else 1), (0 if is_success else 1),
                    1.0, initial_status, evidence_reference
                ))
            conn.commit()

        return self.get_experience_item(marketplace, brand, knowledge_type, value)

    def get_experience_item(self, marketplace: str, brand: str, knowledge_type: str, value: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM experience WHERE marketplace = ? AND brand = ? AND knowledge_type = ? AND value = ?",
                (marketplace, brand, knowledge_type, value)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_experiences(self, marketplace: Optional[str] = None, brand: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM experience WHERE 1=1"
            params = []
            if marketplace:
                query += " AND marketplace = ?"
                params.append(marketplace)
            if brand:
                query += " AND brand = ?"
                params.append(brand)
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def set_last_good(self, marketplace: str, brand: str, knowledge_type: str, value: str):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE experience SET status = 'VALIDATED' 
                WHERE marketplace = ? AND brand = ? AND knowledge_type = ? AND status = 'LAST_GOOD'
            """, (marketplace, brand, knowledge_type))
            conn.execute("""
                UPDATE experience SET status = 'LAST_GOOD'
                WHERE marketplace = ? AND brand = ? AND knowledge_type = ? AND value = ?
            """, (marketplace, brand, knowledge_type, value))
            conn.commit()

    def record_taxonomy_relation(
        self,
        marketplace: str,
        parent_value: str,
        child_value: str,
        relation_type: str = "parent_child",
        evidence: Optional[str] = None
    ):
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO taxonomy_graph (
                    marketplace, parent_value, child_value, relation_type, first_seen, last_seen, last_verified, active_currently, evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(marketplace, parent_value, child_value, relation_type) DO UPDATE SET
                    last_seen = ?,
                    last_verified = ?,
                    active_currently = 1,
                    evidence = COALESCE(?, evidence)
            """, (
                marketplace, parent_value, child_value, relation_type, now, now, now, evidence,
                now, now, evidence
            ))
            conn.commit()

    def get_taxonomy_graph(self, marketplace: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM taxonomy_graph WHERE marketplace = ? AND active_currently = 1", (marketplace,))
            return [dict(r) for r in cursor.fetchall()]

    # Strategy Learning and Decision Making Capabilities

    def record_strategy(self,
                       marketplace: str,
                       brand: str,
                       strategy_id: str,
                       strategy_type: str,
                       surface: str,
                       hypothesis: str,
                       attempt: int,
                       result: str,
                       failure_type: Optional[str] = None,
                       evidence: str = "",
                       timestamp: Optional[str] = None,
                       confidence: float = 0.0,
                       last_validated_at: Optional[str] = None) -> Dict[str, Any]:
        """Record a strategy attempt with its outcome."""
        now = timestamp or datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Create strategy table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    marketplace TEXT NOT NULL,
                    brand TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    strategy_type TEXT NOT NULL,
                    surface TEXT,
                    hypothesis TEXT,
                    attempt INTEGER,
                    result TEXT,
                    failure_type TEXT,
                    evidence TEXT,
                    timestamp TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    last_validated_at TEXT,
                    UNIQUE(marketplace, brand, strategy_id)
                )
            """)
            
            cursor.execute("""
                INSERT OR REPLACE INTO strategy (
                    marketplace, brand, strategy_id, strategy_type, surface, hypothesis,
                    attempt, result, failure_type, evidence, timestamp, confidence, last_validated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                marketplace, brand, strategy_id, strategy_type, surface, hypothesis,
                attempt, result, failure_type, evidence, now, confidence, last_validated_at
            ))
            conn.commit()
            
            return {"strategy_id": strategy_id, "recorded": True}

    def get_strategies(self, marketplace: str, brand: str = "Nicopoly",
                       strategy_type: Optional[str] = None,
                       result: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve strategies with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM strategy WHERE marketplace = ? AND brand = ?"
            params = [marketplace, brand]
            
            if strategy_type:
                query += " AND strategy_type = ?"
                params.append(strategy_type)
            if result:
                query += " AND result = ?"
                params.append(result)
            
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def get_strategy(self, marketplace: str, brand: str, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific strategy by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM strategy WHERE marketplace = ? AND brand = ? AND strategy_id = ?",
                (marketplace, brand, strategy_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def select_strategy(self, marketplace: str, brand: str, strategy_type: str,
                       surface: str, hypothesis: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Select the best strategy based on experience."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Get successful strategies for this type/surface
            cursor.execute("""
                SELECT * FROM strategy 
                WHERE marketplace = ? AND brand = ? AND strategy_type = ? AND surface = ?
                AND result = 'SUCCESS'
                ORDER BY confidence DESC, last_validated_at DESC
                LIMIT 5
            """, (marketplace, brand, strategy_type, surface))
            
            strategies = [dict(r) for r in cursor.fetchall()]
            if not strategies:
                return None
            
            # Return the highest confidence strategy
            best = max(strategies, key=lambda s: s.get("confidence", 0))
            return best

    def record_strategy_decision(self,
                                marketplace: str,
                                brand: str,
                                strategy_id: str,
                                selected: bool,
                                reason: str,
                                alternative_strategy_id: Optional[str] = None,
                                expected_outcome: str = "",
                                timestamp: Optional[str] = None) -> Dict[str, Any]:
        """Record a strategy selection decision."""
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_decision (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    marketplace TEXT NOT NULL,
                    brand TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    selected INTEGER NOT NULL,
                    reason TEXT,
                    alternative_strategy_id TEXT,
                    expected_outcome TEXT,
                    timestamp TEXT NOT NULL,
                    UNIQUE(marketplace, brand, strategy_id, timestamp)
                )
            """)
            
            cursor.execute("""
                INSERT INTO strategy_decision (
                    marketplace, brand, strategy_id, selected, reason,
                    alternative_strategy_id, expected_outcome, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (marketplace, brand, strategy_id, 1 if selected else 0,
                  reason, alternative_strategy_id, expected_outcome, now))
            conn.commit()
            
            return {"decision_recorded": True}

    def get_strategy_decisions(self, marketplace: str, brand: str = "Nicopoly",
                              strategy_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get strategy decisions for analysis."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM strategy_decision WHERE marketplace = ? AND brand = ?"
            params = [marketplace, brand]
            
            if strategy_id:
                query += " AND strategy_id = ?"
                params.append(strategy_id)
            
            query += " ORDER BY timestamp DESC"
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def record_strategy_outcome(self,
                               marketplace: str,
                               brand: str,
                               strategy_id: str,
                               result: str,
                               confidence: float,
                               evidence: str = "",
                               timestamp: Optional[str] = None) -> Dict[str, Any]:
        """Update strategy with outcome and validate/revalidate."""
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Update strategy with outcome
            cursor.execute("""
                UPDATE strategy SET
                    result = ?,
                    confidence = ?,
                    evidence = COALESCE(?, evidence),
                    last_validated_at = ?
                WHERE marketplace = ? AND brand = ? AND strategy_id = ?
            """, (result, confidence, evidence, now, marketplace, brand, strategy_id))
            conn.commit()
            
            # Update experience record for this strategy
            if result == "SUCCESS":
                self.record_experience(
                    marketplace=marketplace, brand=brand,
                    knowledge_type="STRATEGY", value=strategy_id,
                    status="VALIDATED", is_success=True,
                    evidence_reference=f"Strategy {strategy_id} succeeded"
                )
            elif result == "FAILED":
                self.record_experience(
                    marketplace=marketplace, brand=brand,
                    knowledge_type="STRATEGY", value=strategy_id,
                    status="FAILED", is_success=False,
                    evidence_reference=f"Strategy {strategy_id} failed"
                )
            
            return {"outcome_recorded": True}

    def get_stale_strategies(self, marketplace: str, brand: str = "Nicopoly",
                            days_threshold: int = 30) -> List[Dict[str, Any]]:
        """Get strategies that haven't been validated recently."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cutoff = (datetime.utcnow() - __import__('datetime').timedelta(days=days_threshold)).isoformat()
            cursor.execute("""
                SELECT * FROM strategy 
                WHERE marketplace = ? AND brand = ? 
                AND (last_validated_at IS NULL OR last_validated_at < ?)
                AND result = 'SUCCESS'
            """, (marketplace, brand, cutoff))
            return [dict(r) for r in cursor.fetchall()]

    def get_failed_strategies(self, marketplace: str, brand: str = "Nicopoly",
                             min_failures: int = 3) -> List[Dict[str, Any]]:
        """Get strategies that have failed repeatedly."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM strategy 
                WHERE marketplace = ? AND brand = ? AND result = 'FAILED'
                ORDER BY attempt DESC
                LIMIT ?
            """, (marketplace, brand, min_failures))
            return [dict(r) for r in cursor.fetchall()]

    def revalidate_strategy(self, marketplace: str, brand: str, strategy_id: str,
                           new_confidence: float, new_evidence: str = "") -> Dict[str, Any]:
        """Revalidate a strategy with new evidence."""
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE strategy SET
                    confidence = ?,
                    evidence = COALESCE(?, evidence),
                    last_validated_at = ?,
                    attempt = attempt + 1
                WHERE marketplace = ? AND brand = ? AND strategy_id = ?
            """, (new_confidence, new_evidence, datetime.utcnow().isoformat(),
                  marketplace, brand, strategy_id))
            conn.commit()
            return {"revalidated": True, "strategy_id": strategy_id}
