"""
Self-Learning Selector Registry
Tracks success rates of CSS/XPath selectors per marketplace.
Automatically promotes high-performing selectors and demotes failing ones.
Data is persisted to SQLite so learnings survive restarts.
"""
import aiosqlite
import logging
import json
from datetime import datetime
from app.config.settings import DB_PATH

logger = logging.getLogger(__name__)


class SelectorRegistry:
    """
    Learns which selectors work best per marketplace/purpose.
    On each audit cycle it reorders selectors by success rate,
    so the fastest working selector is always tried first.
    """

    async def _ensure_table(self, db: aiosqlite.Connection):
        await db.execute("""
            CREATE TABLE IF NOT EXISTS selector_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marketplace TEXT NOT NULL,
                purpose TEXT NOT NULL,
                selector TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                successes INTEGER DEFAULT 0,
                last_success TEXT,
                last_attempt TEXT,
                UNIQUE(marketplace, purpose, selector)
            )
        """)
        await db.commit()

    async def record_attempt(
        self,
        marketplace: str,
        purpose: str,
        selector: str,
        success: bool,
    ):
        """Called by scrapers after each selector attempt."""
        now = datetime.now().isoformat()
        async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
            await self._ensure_table(db)
            await db.execute("""
                INSERT INTO selector_stats (marketplace, purpose, selector, attempts, successes, last_attempt)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(marketplace, purpose, selector) DO UPDATE SET
                    attempts = CASE WHEN attempts > 100 THEN attempts * 0.9 ELSE attempts END + 1,
                    successes = CASE WHEN attempts > 100 THEN successes * 0.9 ELSE successes END + ?,
                    last_attempt = ?,
                    last_success = CASE WHEN ? THEN ? ELSE last_success END
            """, [
                marketplace, purpose, selector,
                1 if success else 0, now,
                1 if success else 0, now,
                success, now
            ])
            
            # Garbage collection: remove dead selectors
            await db.execute("""
                DELETE FROM selector_stats 
                WHERE attempts > 10 AND (CAST(successes AS REAL) / attempts) < 0.05
            """)
            
            await db.commit()

    async def get_ranked_selectors(
        self,
        marketplace: str,
        purpose: str,
        default_selectors: list[str],
    ) -> list[str]:
        """
        Returns selectors sorted by success rate (desc).
        Falls back to original order if no data yet.
        """
        async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
            await self._ensure_table(db)
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT selector,
                       CAST(successes AS REAL) / MAX(attempts, 1) AS rate
                FROM selector_stats
                WHERE LOWER(marketplace) = LOWER(?)
                  AND purpose = ?
                  AND attempts >= 3
                ORDER BY rate DESC
            """, [marketplace, purpose]) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return default_selectors

        # Build ranked list: known selectors first (by rate), then any new ones appended
        ranked = [r["selector"] for r in rows]
        for s in default_selectors:
            if s not in ranked:
                ranked.append(s)
        return ranked

    async def get_stats(self, marketplace: str | None = None) -> list[dict]:
        """Return selector performance stats for dashboard."""
        async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
            await self._ensure_table(db)
            db.row_factory = aiosqlite.Row
            if marketplace:
                sql = """
                    SELECT *, CAST(successes AS REAL) / MAX(attempts, 1) AS rate
                    FROM selector_stats WHERE LOWER(marketplace) = LOWER(?)
                    ORDER BY marketplace, purpose, rate DESC
                """
                params = [marketplace]
            else:
                sql = """
                    SELECT *, CAST(successes AS REAL) / MAX(attempts, 1) AS rate
                    FROM selector_stats
                    ORDER BY marketplace, purpose, rate DESC
                """
                params = []
            async with db.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]


# Singleton
_registry = SelectorRegistry()


async def record_selector(marketplace: str, purpose: str, selector: str, success: bool):
    await _registry.record_attempt(marketplace, purpose, selector, success)


async def ranked_selectors(
    marketplace: str, purpose: str, defaults: list[str]
) -> list[str]:
    return await _registry.get_ranked_selectors(marketplace, purpose, defaults)


async def selector_stats(marketplace: str | None = None) -> list[dict]:
    return await _registry.get_stats(marketplace)
