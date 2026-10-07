"""
Trend Engine — detects anomalies, drops and recoveries in visibility data.
Runs after each audit cycle and writes alerts to SQLite.
Self-learning: adapts baseline from rolling 7-day average.
"""
import aiosqlite
import logging
from datetime import datetime, timedelta
from app.config.settings import DB_PATH

logger = logging.getLogger(__name__)

ALERT_TYPES = {
    "DROP": "📉 Caída de visibilidad",
    "RECOVERY": "📈 Recuperación de visibilidad",
    "CRITICAL": "🚨 Nivel crítico detectado",
    "PEAK": "🏆 Nuevo máximo histórico",
    "STALE": "⚠️ Sin datos recientes",
}

DROP_THRESHOLD_PCT = 15.0   # ≥15% drop triggers alert
RECOVERY_THRESHOLD_PCT = 10.0
CRITICAL_PCT30 = 10.0        # pct_30 below this = critical alert


class TrendEngine:
    async def _ensure_alerts_table(self, db: aiosqlite.Connection):
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                marketplace TEXT NOT NULL,
                category TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                message TEXT NOT NULL,
                prev_value REAL,
                curr_value REAL,
                acknowledged INTEGER DEFAULT 0
            )
        """)
        await db.commit()

    async def analyze_and_alert(self, marketplace: str, category: str):
        """
        Compare latest audit vs rolling 7-day average.
        Generates alerts if significant changes detected.
        """
        async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
            await self._ensure_alerts_table(db)
            db.row_factory = aiosqlite.Row

            # Latest record
            async with db.execute("""
                SELECT pct_30, pct_240, presence_level, audit_date
                FROM audits
                WHERE LOWER(marketplace) = LOWER(?)
                  AND LOWER(category) = LOWER(?)
                ORDER BY id DESC LIMIT 1
            """, [marketplace, category]) as cur:
                latest = await cur.fetchone()

            if not latest:
                return

            # 7-day rolling average (excluding today's latest)
            cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            async with db.execute("""
                SELECT AVG(pct_30) as avg_30, AVG(pct_240) as avg_240, COUNT(*) as n
                FROM audits
                WHERE LOWER(marketplace) = LOWER(?)
                  AND LOWER(category) = LOWER(?)
                  AND audit_date < ?
                  AND audit_date >= ?
            """, [
                marketplace, category,
                latest["audit_date"],
                (datetime.now() - timedelta(days=14)).isoformat()
            ]) as cur:
                baseline = await cur.fetchone()

            curr_30 = latest["pct_30"] or 0.0
            avg_30 = baseline["avg_30"] if baseline and baseline["avg_30"] is not None else None

            alerts_to_save = []
            now_dt = datetime.now()
            now = now_dt.isoformat()
            
            # Prevent spam: fetch the latest alert in the baseline window (24 hours)
            time_window = (now_dt - timedelta(days=1)).isoformat()
            async with db.execute("""
                SELECT alert_type, curr_value FROM alerts 
                WHERE LOWER(marketplace) = LOWER(?) AND LOWER(category) = LOWER(?)
                AND created_at >= ?
                ORDER BY id DESC LIMIT 1
            """, [marketplace, category, time_window]) as cur:
                last_alert_row = await cur.fetchone()
                
            last_alert = last_alert_row["alert_type"] if last_alert_row else None
            last_val = last_alert_row["curr_value"] if last_alert_row else None

            # --- Drop detection ---
            if avg_30 is not None and avg_30 > 0:
                delta = avg_30 - curr_30
                pct_change = (delta / avg_30) * 100

                # Trigger DROP if no recent DROP, OR if it dropped significantly further (>= 10% lower than last drop)
                is_new_drop = (last_alert != "DROP") or (last_val is not None and (last_val - curr_30) >= 10.0)
                
                if pct_change >= DROP_THRESHOLD_PCT and is_new_drop:
                    alerts_to_save.append({
                        "created_at": now,
                        "marketplace": marketplace,
                        "category": category,
                        "alert_type": "DROP",
                        "message": (
                            f"Caída de {pct_change:.1f}% en visibilidad TOP30. "
                            f"Anterior: {avg_30:.1f}% → Actual: {curr_30:.1f}%"
                        ),
                        "prev_value": avg_30,
                        "curr_value": curr_30,
                    })
                
                # Trigger RECOVERY if no recent RECOVERY
                elif pct_change <= -RECOVERY_THRESHOLD_PCT and last_alert != "RECOVERY":
                    alerts_to_save.append({
                        "created_at": now,
                        "marketplace": marketplace,
                        "category": category,
                        "alert_type": "RECOVERY",
                        "message": (
                            f"Recuperación de {abs(pct_change):.1f}% en visibilidad TOP30. "
                            f"Anterior: {avg_30:.1f}% → Actual: {curr_30:.1f}%"
                        ),
                        "prev_value": avg_30,
                        "curr_value": curr_30,
                    })

            # --- Critical floor detection ---
            if curr_30 < CRITICAL_PCT30 and latest["presence_level"] == "CRITICA" and last_alert != "CRITICAL":
                alerts_to_save.append({
                    "created_at": now,
                    "marketplace": marketplace,
                    "category": category,
                    "alert_type": "CRITICAL",
                    "message": (
                        f"Nivel CRÍTICO: {curr_30:.1f}% en TOP30. "
                        f"Riesgo de invisibilidad total en {marketplace} / {category}."
                    ),
                    "prev_value": avg_30,
                    "curr_value": curr_30,
                })

            # --- Peak detection: new historical maximum ---
            async with db.execute("""
                SELECT MAX(pct_30) as max_30 FROM audits
                WHERE LOWER(marketplace) = LOWER(?)
                  AND LOWER(category) = LOWER(?)
                  AND id < (SELECT MAX(id) FROM audits WHERE LOWER(marketplace)=LOWER(?) AND LOWER(category)=LOWER(?))
            """, [marketplace, category, marketplace, category]) as cur:
                hist = await cur.fetchone()

            if hist and hist["max_30"] and curr_30 > hist["max_30"]:
                alerts_to_save.append({
                    "created_at": now,
                    "marketplace": marketplace,
                    "category": category,
                    "alert_type": "PEAK",
                    "message": (
                        f"🏆 Nuevo máximo histórico: {curr_30:.1f}% TOP30 "
                        f"(anterior máx: {hist['max_30']:.1f}%)"
                    ),
                    "prev_value": hist["max_30"],
                    "curr_value": curr_30,
                })

            for alert in alerts_to_save:
                await db.execute("""
                    INSERT INTO alerts
                    (created_at, marketplace, category, alert_type, message, prev_value, curr_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, [
                    alert["created_at"], alert["marketplace"], alert["category"],
                    alert["alert_type"], alert["message"],
                    alert.get("prev_value"), alert.get("curr_value")
                ])
                logger.info(f"[ALERT] {alert['alert_type']} — {alert['message']}")

            if alerts_to_save:
                await db.commit()

    async def get_recent_alerts(self, limit: int = 50, unack_only: bool = False) -> list[dict]:
        async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
            await self._ensure_alerts_table(db)
            db.row_factory = aiosqlite.Row
            where = "WHERE acknowledged = 0" if unack_only else ""
            async with db.execute(f"""
                SELECT * FROM alerts {where}
                ORDER BY id DESC LIMIT ?
            """, [limit]) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def acknowledge_alert(self, alert_id: int):
        async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
            await self._ensure_alerts_table(db)
            await db.execute(
                "UPDATE alerts SET acknowledged = 1 WHERE id = ?", [alert_id]
            )
            await db.commit()

    async def get_trend_data(self, marketplace: str, category: str, days: int = 30) -> list[dict]:
        """Returns daily pct_30 time series for charting."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT
                    DATE(audit_date) as date,
                    AVG(pct_30)  as pct_30,
                    AVG(pct_60)  as pct_60,
                    AVG(pct_240) as pct_240,
                    AVG(top_30)  as top_30,
                    MAX(presence_level) as presence_level
                FROM audits
                WHERE LOWER(marketplace) = LOWER(?)
                  AND LOWER(category) = LOWER(?)
                  AND audit_date >= ?
                GROUP BY DATE(audit_date)
                ORDER BY date ASC
            """, [marketplace, category, cutoff]) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def record_alert(
        self,
        marketplace: str,
        category: str,
        alert_type: str,
        message: str,
        prev_value: float | None = None,
        curr_value: float | None = None,
    ):
        async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
            await self._ensure_alerts_table(db)
            await db.execute("""
                INSERT INTO alerts
                (created_at, marketplace, category, alert_type, message, prev_value, curr_value)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                datetime.now().isoformat(),
                marketplace,
                category,
                alert_type,
                message,
                prev_value,
                curr_value
            ])
            await db.commit()


# Singleton
_engine = TrendEngine()

async def run_trend_analysis(marketplace: str, category: str):
    await _engine.analyze_and_alert(marketplace, category)

async def get_alerts(limit: int = 50, unack_only: bool = False) -> list[dict]:
    return await _engine.get_recent_alerts(limit, unack_only)

async def ack_alert(alert_id: int):
    await _engine.acknowledge_alert(alert_id)

async def get_trend(marketplace: str, category: str, days: int = 30) -> list[dict]:
    return await _engine.get_trend_data(marketplace, category, days)

async def record_custom_alert(
    marketplace: str,
    category: str,
    alert_type: str,
    message: str,
    prev_value: float | None = None,
    curr_value: float | None = None,
):
    await _engine.record_alert(marketplace, category, alert_type, message, prev_value, curr_value)
