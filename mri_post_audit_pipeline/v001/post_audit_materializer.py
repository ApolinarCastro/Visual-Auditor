import sqlite3
import hashlib
from datetime import datetime
import json
import logging
from contextlib import contextmanager

from mri_commercial_materialization_golden_slice.v001.materializer_engine import GenericCommercialMaterializer

logger = logging.getLogger(__name__)

class PostAuditMaterializer:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_status_table()

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_status_table(self):
        with self._db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mri_post_audit_status (
                    post_audit_run_id TEXT PRIMARY KEY,
                    audit_run_fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    source_count INTEGER,
                    admitted_count INTEGER,
                    rejected_count INTEGER,
                    quarantined_count INTEGER,
                    new_publications INTEGER,
                    reobserved_publications INTEGER,
                    unresolved_identity_count INTEGER,
                    rejected_commercial_count INTEGER,
                    non_nicopoly_confirmed_count INTEGER,
                    insufficient_evidence_count INTEGER,
                    grader_state TEXT,
                    certified_at TEXT,
                    last_error TEXT
                )
            """)
            conn.commit()

    def get_status(self, run_id: str):
        with self._db() as conn:
            r = conn.execute("SELECT * FROM mri_post_audit_status WHERE post_audit_run_id = ?", (run_id,)).fetchone()
            if r:
                return dict(r)
            return None

    def update_status(self, run_id: str, updates: dict):
        with self._db() as conn:
            # We must only update existing fields or insert if not exists
            if 'post_audit_run_id' not in updates:
                updates['post_audit_run_id'] = run_id
                
            fields = ", ".join(f"{k} = excluded.{k}" for k in updates.keys() if k != 'post_audit_run_id')
            cols = ", ".join(updates.keys())
            vals = ", ".join("?" for _ in updates)
            
            sql = f"""
                INSERT INTO mri_post_audit_status ({cols})
                VALUES ({vals})
                ON CONFLICT(post_audit_run_id) DO UPDATE SET {fields}
            """
            params = list(updates.values())
            conn.execute(sql, params)
            conn.commit()

    def run_materialization(self, manifest: dict, snapshot_ids: list):
        run_id = manifest["post_audit_run_id"]
        fingerprint = manifest["audit_run_fingerprint"]
        
        self.update_status(run_id, {
            "audit_run_fingerprint": fingerprint,
            "state": "PROCESSING",
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "certified_at": None,
            "last_error": None
        })

        try:
            with self._db() as conn:
                cursor = conn.cursor()
                
                # Fetch all snapshots
                placeholders = ",".join("?" for _ in snapshot_ids)
                cursor.execute(f"SELECT * FROM product_snapshots WHERE id IN ({placeholders})", snapshot_ids)
                snapshots = [dict(r) for r in cursor.fetchall()]
                
                # Group by marketplace
                mkt_snapshots = {}
                for snap in snapshots:
                    mkt = snap.get('marketplace', '').lower().replace(' ', '')
                    if mkt not in mkt_snapshots:
                        mkt_snapshots[mkt] = []
                    mkt_snapshots[mkt].append(snap)
                
                cursor.execute("SELECT publication_id FROM mri_publications")
                existing_pubs = {r['publication_id'] for r in cursor.fetchall()}

                materializer = GenericCommercialMaterializer(run_id)

                stats = {
                    "audit_run_fingerprint": fingerprint,
                    "source_count": len(snapshots),
                    "admitted_count": 0,
                    "rejected_count": 0,
                    "quarantined_count": 0,
                    "rejected_commercial_count": 0,
                    "non_nicopoly_confirmed_count": 0,
                    "insufficient_evidence_count": 0,
                    "new_publications": 0,
                    "reobserved_publications": 0,
                    "unresolved_identity_count": 0
                }

                # We will process each marketplace in its own transaction sub-boundary
                for mkt, snaps in mkt_snapshots.items():
                    mkt_stats = {"admitted": 0, "rejected": 0, "quarantined": 0, "new": 0, "reobs": 0, "unres": 0,
                                 "rejected_commercial": 0, "non_nicopoly": 0, "insufficient": 0}
                    
                    try:
                        cursor.execute("BEGIN TRANSACTION")
                        
                        for snap in snaps:
                            if not snap.get('marketplace_sku'):
                                if mkt == 'ripley':
                                    mkt_stats["rejected"] += 1
                                    mkt_stats["unres"] += 1
                                else:
                                    mkt_stats["quarantined"] += 1
                                continue
                                
                            res = materializer.process_record(snap)
                            
                            # Handle all result statuses - ALWAYS write evidence
                            if res['status'] == 'ACCEPTED':
                                mkt_stats["admitted"] += 1
                                
                                pub_id = res['identity']['publication_id']
                                is_new = False
                                if pub_id not in existing_pubs:
                                    mkt_stats["new"] += 1
                                    existing_pubs.add(pub_id)
                                    is_new = True
                                else:
                                    mkt_stats["reobs"] += 1
                                    
                                # Deterministic Observation IDs
                                ev_id = res['evidence']['evidence_id']
                                price_id = f"pr_{ev_id}"
                                cat_rel_id = f"cat_rel_{ev_id}"
                                
                                # Product UPSERT
                                prod_id = res['product']['product_id']
                                if prod_id and "unmapped" not in prod_id:
                                    cursor.execute("""
                                        INSERT INTO mri_products (product_id, canonical_brand, product_status, created_at)
                                        VALUES (?, ?, ?, ?)
                                        ON CONFLICT(product_id) DO UPDATE SET
                                            product_status = excluded.product_status
                                    """, (prod_id, res['normalized']['brand'] or "Nicopoly", "ACTIVE", res['normalized']['captured_at']))
                                
                                # Canonical Publication UPSERT
                                cursor.execute("""
                                    INSERT INTO mri_publications (
                                        publication_id, product_id, marketplace, marketplace_product_id, canonical_url,
                                        status, observed_at, run_id, position, surface, position_state, category_relationship,
                                        evidence_type, raw_source_id
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(publication_id) DO UPDATE SET
                                        observed_at = excluded.observed_at,
                                        run_id = excluded.run_id,
                                        position = excluded.position,
                                        surface = excluded.surface,
                                        position_state = excluded.position_state,
                                        evidence_type = excluded.evidence_type,
                                        raw_source_id = excluded.raw_source_id
                                """, (
                                    pub_id, prod_id, res['normalized']['marketplace'], 
                                    res['identity']['marketplace_product_id'], "",
                                    "OBSERVED", res['normalized']['captured_at'], run_id,
                                    res['position']['position'], res['position']['surface'],
                                    res['position']['position_state'], res['category']['relationship'],
                                    res['evidence']['provenance_classification'], res['normalized']['source_record_id']
                                ))

                                # Variant UPSERT
                                cursor.execute("""
                                    INSERT INTO mri_variants (
                                        variant_id, publication_id, variant_title, seller_sku, status, observed_at
                                    ) VALUES (?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(variant_id) DO UPDATE SET
                                        variant_title = excluded.variant_title,
                                        seller_sku = excluded.seller_sku,
                                        observed_at = excluded.observed_at
                                """, (
                                    f"var_{pub_id}", pub_id, res['normalized']['raw_title'],
                                    res['product']['master_sku'], "OBSERVED", res['normalized']['captured_at']
                                ))

                                # Evidence INSERT (Immutable Observation History)
                                cursor.execute("""
                                    INSERT INTO mri_evidence_ledger (
                                        evidence_id, run_id, marketplace, brand, claim_type, claim_value,
                                        source_surface, method, observed_at, confidence, status, raw_reference,
                                        content_hash, truth_model_version
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(evidence_id) DO NOTHING
                                """, (
                                    ev_id, run_id, res['evidence']['marketplace'], res['evidence']['brand'],
                                    'PRICE_AND_POSITION', 'OBSERVED', 'Category Browse', res['evidence']['method'],
                                    res['evidence']['timestamp'], 1.0, res['evidence']['status'], 
                                    res['evidence']['raw_reference'], res['evidence']['content_hash'], 'v1'
                                ))

                                # Price INSERT (Immutable Observation History)
                                cursor.execute("""
                                    INSERT INTO mri_prices (
                                        price_id, publication_id, variant_id, effective_price, currency, observed_at, evidence_id, status
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(price_id) DO NOTHING
                                """, (
                                    price_id, pub_id, f"var_{pub_id}", res['price']['effective_price'],
                                    res['price']['currency'], res['evidence']['timestamp'],
                                    ev_id, "OBSERVED_EFFECTIVE_PRICE"
                                ))
                                
                                # Categories Upsert and Relation observation
                                cat_name = res['category']['category_name']
                                if cat_name:
                                    cursor.execute("SELECT category_id FROM mri_categories WHERE category_name = ? AND marketplace = ?", 
                                                   (cat_name, res['normalized']['marketplace']))
                                    cat_row = cursor.fetchone()
                                    if cat_row:
                                        cat_id = cat_row['category_id']
                                    else:
                                        cat_id = f"cat_{hashlib.md5(cat_name.encode('utf-8')).hexdigest()[:8]}"
                                        cursor.execute("""
                                            INSERT INTO mri_categories (category_id, marketplace, category_name, canonical_url, created_at)
                                            VALUES (?, ?, ?, ?, ?)
                                            ON CONFLICT(category_id) DO NOTHING
                                        """, (cat_id, res['normalized']['marketplace'], cat_name, "", res['normalized']['captured_at']))
                                        
                                    cursor.execute("""
                                        INSERT INTO mri_publication_categories (publication_id, category_id, status, observed_at)
                                        VALUES (?, ?, ?, ?)
                                        ON CONFLICT(publication_id, category_id) DO UPDATE SET
                                            status = excluded.status,
                                            observed_at = excluded.observed_at
                                    """, (pub_id, cat_id, "OBSERVED", res['normalized']['captured_at']))

                            elif res['status'] == 'REJECTED_COMMERCIAL':
                                # REJECTED_COMMERCIAL: Write to evidence ledger only, NOT commercial tables
                                mkt_stats["rejected_commercial"] += 1
                                
                                membership = res.get('membership', {})
                                classification = membership.get('classification', 'UNKNOWN')
                                
                                if classification == 'NON_NICOPOLY_CONFIRMED':
                                    mkt_stats["non_nicopoly"] += 1
                                elif classification == 'INSUFFICIENT_EVIDENCE':
                                    mkt_stats["insufficient"] += 1
                                
                                # Still write evidence for traceability
                                ev_info = res['evidence']
                                ev_id = ev_info['evidence_id']
                                
                                cursor.execute("""
                                    INSERT INTO mri_evidence_ledger (
                                        evidence_id, run_id, marketplace, brand, claim_type, claim_value,
                                        source_surface, method, observed_at, confidence, status, raw_reference,
                                        content_hash, truth_model_version
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(evidence_id) DO NOTHING
                                """, (
                                    ev_id, run_id, ev_info['marketplace'], ev_info['brand'],
                                    'MEMBERSHIP_REJECTION', classification,
                                    'Category Browse', ev_info['method'],
                                    ev_info['timestamp'], 1.0, ev_info['status'], 
                                    ev_info['raw_reference'], ev_info['content_hash'], 'v1'
                                ))

                            else:
                                # Other rejection reasons (synthetic, identity unresolved, grader blocked)
                                reason = res.get('rejection_reason') or res.get('grader', {}).get('overall_status')
                                if 'synthetic' in str(reason).lower():
                                    mkt_stats["rejected"] += 1
                                elif 'identity' in str(reason).lower() or 'unresolved' in str(reason).lower():
                                    mkt_stats["unres"] += 1
                                else:
                                    mkt_stats["quarantined"] += 1
                                
                                # Still write evidence for traceability
                                if 'evidence' in res:
                                    ev_info = res['evidence']
                                    ev_id = ev_info['evidence_id']
                                    
                                    cursor.execute("""
                                        INSERT INTO mri_evidence_ledger (
                                            evidence_id, run_id, marketplace, brand, claim_type, claim_value,
                                            source_surface, method, observed_at, confidence, status, raw_reference,
                                            content_hash, truth_model_version
                                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                        ON CONFLICT(evidence_id) DO NOTHING
                                    """, (
                                        ev_id, run_id, ev_info['marketplace'], ev_info['brand'],
                                        'REJECTION', str(reason),
                                        'Category Browse', ev_info['method'],
                                        ev_info['timestamp'], 1.0, ev_info['status'], 
                                        ev_info['raw_reference'], ev_info['content_hash'], 'v1'
                                    ))

                        conn.commit()
                        
                        # Add marketplace stats to global stats
                        stats["admitted_count"] += mkt_stats["admitted"]
                        stats["rejected_count"] += mkt_stats["rejected"]
                        stats["quarantined_count"] += mkt_stats["quarantined"]
                        stats["rejected_commercial_count"] += mkt_stats["rejected_commercial"]
                        stats["non_nicopoly_confirmed_count"] += mkt_stats["non_nicopoly"]
                        stats["insufficient_evidence_count"] += mkt_stats["insufficient"]
                        stats["new_publications"] += mkt_stats["new"]
                        stats["reobserved_publications"] += mkt_stats["reobs"]
                        stats["unresolved_identity_count"] += mkt_stats["unres"]
                        
                    except Exception as mkt_e:
                        conn.rollback()
                        logger.error(f"Marketplace isolation failure for {mkt}: {mkt_e}")
                        # We do not fail the whole run immediately. This allows PARTIAL success.

                # Grader and Status Update (PROMOTION BOUNDARY)
                total_processed = stats["admitted_count"] + stats["rejected_count"] + stats["quarantined_count"] + stats["rejected_commercial_count"]
                
                historical_fingerprint = "f88d1c089fd62d6d6a31f521457423bc125b998eeb58b193ee4b8d84c9ae3242"
                is_fresh_production = (stats["source_count"] > 0) and (fingerprint != historical_fingerprint)
                
                grader_pass = (stats["source_count"] == total_processed) and is_fresh_production
                
                stats["grader_state"] = "PASS" if grader_pass else "FAIL"
                stats["state"] = "SUCCESS" if grader_pass else ("PARTIAL" if total_processed > 0 else "FAILED")
                stats["finished_at"] = datetime.now().isoformat()
                
                if grader_pass:
                    stats["certified_at"] = stats["finished_at"]
                
                self.update_status(run_id, stats)
                
                return stats
                
        except Exception as e:
            self.update_status(run_id, {
                "audit_run_fingerprint": fingerprint,
                "state": "FAILED",
                "last_error": str(e),
                "finished_at": datetime.now().isoformat()
            })
            raise e