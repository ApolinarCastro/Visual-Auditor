"""
Audit Scheduler
Runs automatic audits on a configurable schedule using asyncio.
Supports: daily, custom interval (hours), or manual trigger.
"""
import asyncio
import logging
from datetime import datetime, time as dtime

from app.auditor.audit_runner import AuditRunner, _global_audit_lock

logger = logging.getLogger(__name__)


class AuditScheduler:
    """
    Schedules audit runs. Two modes:
    - interval_hours: run every N hours
    - daily_at: run once per day at a fixed time (HH:MM string)
    """

    def __init__(
        self,
        interval_hours: float | None = None,
        daily_at: str | None = "03:00",
        marketplaces: list[str] | None = None,
    ):
        self.interval_hours = interval_hours
        self.daily_at = daily_at
        self.marketplaces = marketplaces or ["Mercado Libre", "Paris", "Ripley", "Falabella"]
        self._running = False
        self._runner = AuditRunner()

    async def _run_cycle(self):
        logger.info(f"[Scheduler] Starting audit cycle at {datetime.now().isoformat()}")
        if _global_audit_lock.locked():
            logger.warning("[Scheduler] Audit cycle skipped because an audit is already running manually.")
            return
            
        try:
            await self._runner.run_all(self.marketplaces)
        except Exception as exc:
            logger.error(f"[Scheduler] Error running parallel audit cycle: {exc}")
        logger.info(f"[Scheduler] Cycle complete at {datetime.now().isoformat()}")

    async def _seconds_until_daily(self) -> float:
        """Seconds until next daily_at trigger."""
        now = datetime.now()
        h, m = map(int, (self.daily_at or "03:00").split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            # Next day
            from datetime import timedelta
            target += timedelta(days=1)
        return (target - now).total_seconds()

    async def start(self):
        self._running = True
        logger.info(
            f"[Scheduler] Started. marketplaces={self.marketplaces} | "
            f"interval_hours={self.interval_hours} | daily_at={self.daily_at}"
        )

        while self._running:
            if self.interval_hours:
                sleep_secs = self.interval_hours * 3600
            else:
                sleep_secs = await self._seconds_until_daily()

            next_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(
                f"[Scheduler] Next run in {sleep_secs/3600:.2f}h "
                f"(~{datetime.fromtimestamp(__import__('time').time() + sleep_secs).strftime('%Y-%m-%d %H:%M')})"
            )
            await asyncio.sleep(sleep_secs)

            if self._running:
                await self._run_cycle()

    def stop(self):
        self._running = False
        logger.info("[Scheduler] Stopped.")
