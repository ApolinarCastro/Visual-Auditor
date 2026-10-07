"""
Enhanced SQLite Manager v2
- Adds: historical trend queries, selector_stats, alerts, health_log tables
- Migration-safe: uses ALTER TABLE IF NOT EXISTS pattern
- Exposes: trend queries, audit history, category stats
"""
import aiosqlite
import logging
import re
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from app.config.settings import DB_PATH

logger = logging.getLogger(__name__)


def _make_key(s_item):
    """Normaliza un snapshot a una clave unica para dedup."""
    mkt_sku = str(s_item.get("marketplace_sku", "")).strip()
    if mkt_sku:
        return mkt_sku
    raw_title = str(s_item.get("product_title", s_item.get("title", ""))).strip().lower()
    clean = re.sub(r"\b(nicopoly|nicopolo|nico poly)\b", "", raw_title, flags=re.IGNORECASE).strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean


_AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_date TEXT,
    marketplace TEXT,
    category TEXT,
    category_url TEXT,
    total_marketplace INTEGER,
    total_nicopoly INTEGER,
    top_30 INTEGER,
    top_60 INTEGER,
    top_90 INTEGER,
    top_120 INTEGER,
    top_240 INTEGER,
    pct_30 REAL,
    pct_60 REAL,
    pct_90 REAL,
    pct_120 REAL,
    pct_240 REAL,
    presence_level TEXT,
    risk_level TEXT,
    opportunity TEXT,
    duration_seconds REAL
)
"""

_PRODUCT_SNAPSHOTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS product_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_date TEXT,
    marketplace TEXT,
    category TEXT,
    sku_master TEXT,
    marketplace_sku TEXT,
    product_title TEXT,
    brand TEXT,
    price REAL,
    price_multivende REAL,
    price_diff REAL,
    position_absolute INTEGER,
    is_nicopoly INTEGER,
    created_at TEXT
);
"""

_RECOVERY_EXPERIENCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS recovery_experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    marketplace TEXT,
    category TEXT,
    failure_type TEXT,
    quality_flag TEXT,
    strategy TEXT,
    attempt INTEGER,
    result TEXT,
    recovery_seconds REAL,
    previous_value TEXT,
    candidate_value TEXT,
    promoted INTEGER,
    evidence TEXT
);
"""

_SOURCE_HEALTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_health (
    marketplace TEXT PRIMARY KEY,
    status TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    last_success TEXT,
    last_failure TEXT,
    last_recovery TEXT,
    failure_type TEXT,
    updated_at TEXT
);
"""


class SQLiteManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    @asynccontextmanager
    async def _connect(self):
        async with aiosqlite.connect(self.db_path, timeout=30.0) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            yield db

    async def init_db(self):
        import os
        os.makedirs(self.db_path.parent, exist_ok=True)
        async with self._connect() as db:
            await db.execute(_AUDIT_SCHEMA)
            await db.execute(_PRODUCT_SNAPSHOTS_SCHEMA)
            await db.execute(_RECOVERY_EXPERIENCES_SCHEMA)
            await db.execute(_SOURCE_HEALTH_SCHEMA)
            # Add duration_seconds column if upgrading from v1
            try:
                await db.execute(
                    "ALTER TABLE audits ADD COLUMN duration_seconds REAL"
                )
            except Exception:
                pass  # Column already exists
            try:
                await db.execute("ALTER TABLE product_snapshots ADD COLUMN price_multivende REAL")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE product_snapshots ADD COLUMN price_diff REAL")
            except Exception:
                pass
                
            # Create indexes to speed up history, latest queries, and avoid locks
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_audits_lookup ON audits (marketplace, category, audit_date);"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_audits_date ON audits (audit_date);"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_lookup ON product_snapshots (marketplace, category, audit_date);"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_sku ON product_snapshots (sku_master);"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_date ON product_snapshots (audit_date);"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_recovery_lookup ON recovery_experiences (marketplace, category, timestamp);"
            )
            # Create a partial UNIQUE index to enforce schema-level uniqueness per day & SKU when marketplace_sku is present
            try:
                await db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_daily_sku ON product_snapshots (marketplace, category, substr(audit_date, 1, 10), marketplace_sku) WHERE marketplace_sku IS NOT NULL AND marketplace_sku != '';"
                )
            except Exception:
                pass
            await db.commit()
            logger.info("Database initialized (v2 with product_snapshots, recovery_experiences, source_health, concurrent WAL, partial UNIQUE daily SKU index and optimized lookup indexes).")

    async def save_audit(self, audit_data: dict):
        # Valid columns from the schema
        valid_cols = [
            "audit_date", "marketplace", "category", "category_url",
            "total_marketplace", "total_nicopoly",
            "top_30", "top_60", "top_90", "top_120", "top_240",
            "pct_30", "pct_60", "pct_90", "pct_120", "pct_240",
            "presence_level", "risk_level", "opportunity", "duration_seconds"
        ]
        
        # Filter input data to only include valid columns
        safe_data = {k: v for k, v in audit_data.items() if k in valid_cols}
        
        async with self._connect() as db:
            cols = ", ".join(safe_data.keys())
            placeholders = ", ".join(["?" for _ in safe_data])
            sql = f"INSERT INTO audits ({cols}) VALUES ({placeholders})"
            await db.execute(sql, list(safe_data.values()))
            await db.commit()
            logger.info(
                f"[DB] Saved: {safe_data.get('marketplace')} / "
                f"{safe_data.get('category')} â†’ "
                f"pct_30={safe_data.get('pct_30', 0):.1f}%"
            )

    async def get_latest_audits(self, limit: int = 200) -> list[dict]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            sql = """
                SELECT * FROM audits
                WHERE id IN (
                    SELECT MAX(id)
                    FROM audits
                    GROUP BY LOWER(marketplace), LOWER(category)
                )
                ORDER BY marketplace ASC, category ASC
            """
            async with db.execute(sql) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_audit_history(
        self,
        marketplace: str,
        category: str,
        days: int = 30,
    ) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM audits
                WHERE LOWER(marketplace) = LOWER(?)
                  AND LOWER(category) = LOWER(?)
                  AND audit_date >= ?
                ORDER BY audit_date ASC
            """, [marketplace, category, cutoff]) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_marketplace_history(
        self,
        marketplace: str,
        days: int = 7,
    ) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT date(audit_date) as dia, AVG(pct_30) as avg_pct_30
                FROM audits
                WHERE LOWER(marketplace) = LOWER(?)
                  AND audit_date >= ?
                GROUP BY dia
                ORDER BY dia ASC
            """, [marketplace, cutoff]) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_latest_for_category(
        self, marketplace: str, category: str
    ) -> dict | None:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM audits
                WHERE LOWER(marketplace) = LOWER(?)
                  AND LOWER(category) = LOWER(?)
                ORDER BY id DESC LIMIT 1
            """, [marketplace, category]) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def delete_today_record(
        self, marketplace: str, category: str, date_prefix: str
    ):
        async with self._connect() as db:
            await db.execute(
                """DELETE FROM audits
                   WHERE LOWER(marketplace) = LOWER(?)
                     AND LOWER(category) = LOWER(?)
                     AND audit_date LIKE ?""",
                [marketplace, category, f"{date_prefix}%"],
            )
            await db.commit()

    async def delete_today_snapshots(self, marketplace: str, category: str, date_prefix: str):
        """Purges all product_snapshots for a (marketplace, category) from today before re-insert.
        Prevents duplicate accumulation when a category is re-audited multiple times in one day."""
        async with self._connect() as db:
            await db.execute(
                """DELETE FROM product_snapshots
                   WHERE LOWER(marketplace) = LOWER(?)
                     AND LOWER(category) = LOWER(?)
                     AND audit_date LIKE ?""",
                [marketplace, category, f"{date_prefix}%"],
            )
            await db.commit()
            logger.info(f"[DB] Cleared today's snapshots for {marketplace}/{category}")

    async def get_summary_stats(self) -> dict:
        """Global stats for dashboard header cards."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT
                    COUNT(DISTINCT marketplace) as marketplace_count,
                    COUNT(DISTINCT category) as category_count,
                    COUNT(*) as total_audits,
                    MAX(audit_date) as last_audit,
                    AVG(pct_30) as avg_pct_30,
                    SUM(CASE WHEN presence_level='CRITICA' THEN 1 ELSE 0 END) as critical_count,
                    SUM(CASE WHEN presence_level='EXCELENTE' THEN 1 ELSE 0 END) as excellent_count
                FROM audits
                WHERE id IN (
                    SELECT MAX(id) FROM audits GROUP BY LOWER(marketplace), LOWER(category)
                )
            """) as cur:
                row = await cur.fetchone()
                return dict(row) if row else {}

    async def get_marketplace_summary(self) -> list[dict]:
        """Per-marketplace aggregated stats."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT
                    marketplace,
                    COUNT(*) as categories,
                    AVG(pct_30) as avg_pct_30,
                    AVG(pct_240) as avg_pct_240,
                    SUM(CASE WHEN presence_level='CRITICA' THEN 1 ELSE 0 END) as critical,
                    SUM(CASE WHEN presence_level='EXCELENTE' THEN 1 ELSE 0 END) as excellent,
                    MAX(audit_date) as last_audit
                FROM audits
                WHERE id IN (
                    SELECT MAX(id) FROM audits GROUP BY LOWER(marketplace), LOWER(category)
                )
                GROUP BY LOWER(marketplace)
                ORDER BY marketplace
            """) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_all_categories(self) -> list[dict]:
        """All unique marketplace+category pairs."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT DISTINCT marketplace, category
                FROM audits
                ORDER BY marketplace, category
            """) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def prune_and_optimize(self):
        """Prunes health_log (> 30 days) and alerts (> 15 days acknowledged), then runs VACUUM and optimize."""
        now = datetime.now()
        health_cutoff = (now - timedelta(days=30)).isoformat()
        alerts_cutoff = (now - timedelta(days=15)).isoformat()
        
        logger.info("[DB] Running telemetry pruning and auto-compaction...")
        async with self._connect() as db:
            # Prune health_log
            try:
                # In sqlite health_log table exists dynamically. We try executing, if it doesn't exist, we skip.
                async with db.execute(
                    "DELETE FROM health_log WHERE recorded_at < ?",
                    [health_cutoff]
                ) as cur:
                    logger.info(f"[DB] Pruned {cur.rowcount} stale records from health_log.")
            except Exception as e:
                logger.debug(f"[DB] Skipping health_log pruning: {e}")
                
            # Prune alerts
            try:
                async with db.execute(
                    "DELETE FROM alerts WHERE created_at < ? AND acknowledged = 1",
                    [alerts_cutoff]
                ) as cur:
                    logger.info(f"[DB] Pruned {cur.rowcount} acknowledged alerts from alerts table.")
            except Exception as e:
                logger.debug(f"[DB] Skipping alerts pruning: {e}")
                
            await db.commit()
            
            # Run SQLite compaction
            try:
                logger.info("[DB] Running database VACUUM...")
                await db.execute("VACUUM;")
                logger.info("[DB] Running database index optimization (PRAGMA optimize)...")
                await db.execute("PRAGMA optimize;")
                logger.info("[DB] Database auto-compaction completed successfully.")
            except Exception as e:
                logger.error(f"[DB] Failed to vacuum/optimize database: {e}")

    async def save_product_snapshots(self, snapshots: list[dict]):
        """Saves detailed per-product snapshots (pricing + SKU master) into secondary product_snapshots table.
        Deduplicates by marketplace_sku (or title as fallback) before inserting to prevent duplicates."""
        if not snapshots:
            return
        async with self._connect() as db:
            cols = [
                "audit_date", "marketplace", "category", "sku_master",
                "marketplace_sku", "product_title", "brand", "price",
                "price_multivende", "price_diff",
                "position_absolute", "is_nicopoly", "created_at",
                "price_multivende_offer", "stock_multivende"
            ]
            placeholders = ", ".join(["?" for _ in cols])
            sql = f"INSERT INTO product_snapshots ({', '.join(cols)}) VALUES ({placeholders})"

            # FIX: Dedup con reemplazo - si un producto ya existe con is_nicopoly=False
            # y llega uno nuevo con is_nicopoly=True para la misma key, REEMPLAZAR.
            # Esto corrige el bug donde productos Nicopoly rechazados en el primer flujo
            # (brand_products) no podian ser corregidos por el segundo flujo (products).
            seen_map: dict = {}  # key -> snapshot
            # First pass: Nicopoly-confirmed rows (is_nicopoly=True) take priority
            for s in snapshots:
                if not s.get("is_nicopoly"):
                    continue
                key = _make_key(s)
                if key and key not in seen_map:
                    seen_map[key] = s

            # Second pass: general (non-Nicopoly) rows - add if not seen
            for s in snapshots:
                if s.get("is_nicopoly"):
                    continue
                key = _make_key(s)
                if key and key not in seen_map:
                    seen_map[key] = s
            deduped_snapshots = list(seen_map.values())

            # Clear any existing rows for the exact same (marketplace, category, audit_date)
            # to prevent duplicate accumulation between different pagination batches.
            if deduped_snapshots:
                first = deduped_snapshots[0]
                mkt = first.get("marketplace", "")
                cat = first.get("category", "")
                a_date = first.get("audit_date", "")
                date_prefix = str(a_date)[:10] if a_date else ""
                if mkt and cat and date_prefix:
                    await db.execute("""
                        DELETE FROM product_snapshots
                        WHERE LOWER(marketplace) = LOWER(?)
                          AND LOWER(category) = LOWER(?)
                          AND substr(audit_date, 1, 10) = ?
                    """, [mkt, cat, date_prefix])

            rows = []
            now_iso = datetime.now().isoformat()
            for s in deduped_snapshots:
                p_pub = float(s.get("price", 0.0))
                p_mv = float(s.get("price_multivende", 0.0))
                p_mv_offer = float(s.get("price_multivende_offer", 0.0))
                
                # Para Paris u otros canales con ofertas activas, comparar contra el precio de oferta si existe
                mkt_lower = s.get("marketplace", "").lower()
                if p_mv_offer > 0 and (p_pub <= p_mv_offer or mkt_lower == "paris"):
                    ref_price = p_mv_offer
                else:
                    ref_price = p_mv
                    
                p_diff = round(p_pub - ref_price, 2) if (p_pub > 0 and ref_price > 0) else 0.0
                rows.append([
                    s.get("audit_date", now_iso),
                    s.get("marketplace", ""),
                    s.get("category", ""),
                    s.get("sku_master", ""),
                    s.get("marketplace_sku", ""),
                    s.get("product_title", s.get("title", "")),
                    s.get("brand", s.get("vendor", "")),
                    p_pub,
                    p_mv,
                    p_diff,
                    int(s.get("position_absolute", 0)),
                    1 if s.get("is_nicopoly") else 0,
                    now_iso,
                    float(s.get("price_multivende_offer", 0.0)),
                    int(s.get("stock_multivende", -1))
                ])
            if rows:
                await db.executemany(sql, rows)
                await db.commit()
            logger.info(f"[DB] Saved {len(rows)} product snapshots (from {len(snapshots)} raw, {len(snapshots)-len(rows)} deduped) in product_snapshots table.")

    async def get_price_history(self, sku_master: str, days: int = 30) -> list[dict]:
        """Retrieves price history for a given master SKU across marketplaces."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT audit_date, marketplace, category, product_title, price, position_absolute
                FROM product_snapshots
                WHERE LOWER(sku_master) = LOWER(?) AND audit_date >= ?
                ORDER BY audit_date ASC
            """, [sku_master, cutoff]) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_snapshots_for_category(self, marketplace: str, category: str, limit: int = 100, only_nicopoly: bool = False) -> list[dict]:
        """Retrieves latest product snapshots (prices, SKUs, positions) for a category, deduplicated by SKU/title."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            
            # Get latest audit timestamp for this category to ensure 100% freshness
            async with db.execute("""
                SELECT MAX(audit_date) FROM product_snapshots
                WHERE LOWER(marketplace) = LOWER(?) AND LOWER(category) = LOWER(?)
            """, [marketplace, category]) as cur:
                row = await cur.fetchone()
                latest_date = row[0] if row and row[0] else None

            if not latest_date:
                return []

            where_clause = "LOWER(marketplace) = LOWER(?) AND LOWER(category) = LOWER(?) AND audit_date = ?"
            params = [marketplace, category, latest_date]
            if only_nicopoly:
                where_clause += " AND is_nicopoly = 1"
            params.append(limit * 2)

            async with db.execute(f"""
                SELECT audit_date, marketplace, category, sku_master, marketplace_sku,
                       product_title, brand, price, price_multivende, price_diff, position_absolute, is_nicopoly,
                       price_multivende_offer, stock_multivende
                FROM product_snapshots
                WHERE {where_clause}
                ORDER BY position_absolute ASC
                LIMIT ?
            """, params) as cur:
                rows = await cur.fetchall()
                raw = [dict(r) for r in rows]
                
                from app.loaders.multivende_loader import get_multivende_loader
                mv_loader = get_multivende_loader()

                # Deduplicate entries by SKU and normalized title (aligned with write key)
                seen = set()
                deduped = []
                for item in raw:
                    key = _make_key(item)
                    if key and key not in seen:
                        seen.add(key)
                        
                        # Dynamic Multivende enrichment if sku_master or price_multivende is missing
                        if not item.get("sku_master") or item.get("sku_master") == "Sin match" or item.get("price_multivende", 0.0) <= 0:
                            lookup_val = item.get("marketplace_sku") or item.get("product_title", "")
                            match = mv_loader.lookup_sku(marketplace, lookup_val)
                            if match:
                                mkt_key = marketplace.lower().strip()
                                item["sku_master"] = match.get("sku_master", item.get("sku_master", ""))
                                item["price_multivende"] = match.get("prices", {}).get(mkt_key, 0.0)
                                item["price_multivende_offer"] = match.get("offers", {}).get(mkt_key, 0.0)
                                item["stock_multivende"] = match.get("stock", -1)
                                if item["price_multivende"] > 0 and item.get("price", 0.0) > 0:
                                    item["price_diff"] = item["price"] - item["price_multivende"]
                        deduped.append(item)
                        if len(deduped) >= limit:
                            break
                return deduped

    async def save_recovery_experience(self, exp_data: dict):
        """Saves a recovery experience record into recovery_experiences table."""
        sql = """
            INSERT INTO recovery_experiences (
                timestamp, marketplace, category, failure_type, quality_flag,
                strategy, attempt, result, recovery_seconds, previous_value,
                candidate_value, promoted, evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        async with self._connect() as db:
            await db.execute(sql, [
                exp_data.get("timestamp", datetime.now().isoformat()),
                exp_data.get("marketplace", ""),
                exp_data.get("category", ""),
                exp_data.get("failure_type", ""),
                exp_data.get("quality_flag", ""),
                exp_data.get("strategy", ""),
                int(exp_data.get("attempt", 1)),
                exp_data.get("result", ""),
                float(exp_data.get("recovery_seconds", 0.0)),
                str(exp_data.get("previous_value", "")),
                str(exp_data.get("candidate_value", "")),
                1 if exp_data.get("promoted") else 0,
                str(exp_data.get("evidence", ""))
            ])
            await db.commit()

    async def get_recovery_experiences(self, limit: int = 50) -> list[dict]:
        """Retrieves recent recovery experiences."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM recovery_experiences
                ORDER BY id DESC
                LIMIT ?
            """, [limit]) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def update_source_health(self, health_data: dict):
        """Upserts a source health status entry."""
        sql = """
            INSERT INTO source_health (
                marketplace, status, consecutive_failures, last_success,
                last_failure, last_recovery, failure_type, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(marketplace) DO UPDATE SET
                status = excluded.status,
                consecutive_failures = excluded.consecutive_failures,
                last_success = COALESCE(excluded.last_success, source_health.last_success),
                last_failure = COALESCE(excluded.last_failure, source_health.last_failure),
                last_recovery = COALESCE(excluded.last_recovery, source_health.last_recovery),
                failure_type = excluded.failure_type,
                updated_at = excluded.updated_at
        """
        async with self._connect() as db:
            await db.execute(sql, [
                health_data.get("marketplace"),
                health_data.get("status", "HEALTHY"),
                int(health_data.get("consecutive_failures", 0)),
                health_data.get("last_success"),
                health_data.get("last_failure"),
                health_data.get("last_recovery"),
                health_data.get("failure_type"),
                health_data.get("updated_at", datetime.now().isoformat())
            ])
            await db.commit()

    async def get_source_health(self, marketplace: str | None = None) -> list[dict]:
        """Retrieves source health status for all or a single marketplace."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            if marketplace:
                async with db.execute("SELECT * FROM source_health WHERE LOWER(marketplace) = LOWER(?)", [marketplace]) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute("SELECT * FROM source_health ORDER BY marketplace ASC") as cur:
                    rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_last_good_audit(self, marketplace: str, category: str) -> dict | None:
        """Retrieves the most recent valid (non-zero or historical best) audit for a category."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM audits
                WHERE LOWER(marketplace) = LOWER(?)
                  AND LOWER(category) = LOWER(?)
                  AND total_marketplace > 0
                ORDER BY id DESC LIMIT 1
            """, [marketplace, category]) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
