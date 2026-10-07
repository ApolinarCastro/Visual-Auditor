"""
Health Monitor — real-time system health tracking.
Tracks: scraper latency, DB write times, error rates per run.
Exposes /health endpoint data for dashboard and external monitoring.
"""
import aiosqlite
import logging
import time
from datetime import datetime, timedelta
from app.config.settings import DB_PATH

logger = logging.getLogger(__name__)


class HealthMonitor:
    async def _ensure_table(self, db: aiosqlite.Connection):
        await db.execute("""
            CREATE TABLE IF NOT EXISTS health_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                marketplace TEXT NOT NULL,
                category TEXT,
                event_type TEXT NOT NULL,
                duration_ms REAL,
                status TEXT NOT NULL,
                detail TEXT
            )
        """)
        await db.commit()

    async def record_event(
        self,
        marketplace: str,
        event_type: str,
        status: str,
        duration_ms: float | None = None,
        category: str | None = None,
        detail: str | None = None,
    ):
        async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
            await self._ensure_table(db)
            await db.execute("""
                INSERT INTO health_log
                (recorded_at, marketplace, category, event_type, duration_ms, status, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                datetime.now().isoformat(),
                marketplace, category, event_type,
                duration_ms, status, detail
            ])
            await db.commit()

    async def get_summary(self) -> dict:
        """Returns health summary for the last 24 hours."""
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
            await self._ensure_table(db)
            db.row_factory = aiosqlite.Row

            async with db.execute("""
                SELECT
                    COUNT(*) as total_events,
                    SUM(CASE WHEN status='OK' THEN 1 ELSE 0 END) as successes,
                    SUM(CASE WHEN status='ERROR' THEN 1 ELSE 0 END) as errors,
                    AVG(CASE WHEN duration_ms IS NOT NULL THEN duration_ms END) as avg_duration_ms,
                    MAX(recorded_at) as last_event
                FROM health_log
                WHERE recorded_at >= ?
            """, [cutoff]) as cur:
                row = await cur.fetchone()
                summary = dict(row) if row else {}

            async with db.execute("""
                SELECT marketplace,
                       SUM(CASE WHEN status='OK' THEN 1 ELSE 0 END) as ok,
                       SUM(CASE WHEN status='ERROR' THEN 1 ELSE 0 END) as errors
                FROM health_log
                WHERE recorded_at >= ?
                GROUP BY marketplace
            """, [cutoff]) as cur:
                mp_rows = await cur.fetchall()
                summary["by_marketplace"] = [dict(r) for r in mp_rows]

            # Last 10 errors
            async with db.execute("""
                SELECT * FROM health_log
                WHERE status = 'ERROR' AND recorded_at >= ?
                ORDER BY id DESC LIMIT 10
            """, [cutoff]) as cur:
                err_rows = await cur.fetchall()
                summary["recent_errors"] = [dict(r) for r in err_rows]

        total = summary.get("total_events") or 0
        errs = summary.get("errors") or 0
        summary["error_rate_pct"] = round((errs / total) * 100, 1) if total > 0 else 0.0
        summary["status"] = "HEALTHY" if summary["error_rate_pct"] < 20 else "DEGRADED"
        return summary

    async def get_latency_stats(self, marketplace: str | None = None) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
            await self._ensure_table(db)
            db.row_factory = aiosqlite.Row
            where = "AND LOWER(marketplace) = LOWER(?)" if marketplace else ""
            params = [cutoff, marketplace] if marketplace else [cutoff]
            async with db.execute(f"""
                SELECT
                    marketplace,
                    event_type,
                    AVG(duration_ms) as avg_ms,
                    MIN(duration_ms) as min_ms,
                    MAX(duration_ms) as max_ms,
                    COUNT(*) as count
                FROM health_log
                WHERE recorded_at >= ? {where}
                  AND duration_ms IS NOT NULL
                GROUP BY marketplace, event_type
                ORDER BY avg_ms DESC
            """, params) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]


# Singleton
_monitor = HealthMonitor()


class timed_event:
    """Context manager for timing scraper operations."""
    def __init__(self, marketplace: str, event_type: str, category: str | None = None):
        self.marketplace = marketplace
        self.event_type = event_type
        self.category = category
        self._start: float = 0.0

    async def __aenter__(self):
        self._start = time.monotonic()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.monotonic() - self._start) * 1000
        status = "ERROR" if exc_type else "OK"
        
        detail = None
        if exc_val:
            err_str = str(exc_val)
            if "TimeoutError" in err_str:
                detail = "Timeout"
            elif "403" in err_str or "Cloudflare" in err_str or "Just a moment" in err_str:
                detail = "Cloudflare/403 Block"
            elif "TargetClosedError" in err_str:
                detail = "Target Closed"
            elif "ERR_NAME_NOT_RESOLVED" in err_str or "ERR_CONNECTION" in err_str:
                detail = "Network Error"
            else:
                detail = exc_type.__name__ if exc_type else err_str[:50]
        await _monitor.record_event(
            marketplace=self.marketplace,
            event_type=self.event_type,
            status=status,
            duration_ms=round(duration_ms, 1),
            category=self.category,
            detail=detail,
        )
        return False  # Don't suppress exception


async def health_summary() -> dict:
    return await _monitor.get_summary()


async def latency_stats(marketplace: str | None = None) -> list[dict]:
    return await _monitor.get_latency_stats(marketplace)
