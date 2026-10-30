"""
Visibility Auditor — CLI Entry Point v2

Commands:
  audit-all                 Audit all 4 marketplaces sequentially
  audit --marketplace <X>   Audit one marketplace
  dashboard                 Start FastAPI dashboard on port 8000
  schedule                  Run on automatic schedule (daily 03:00 default)
  health                    Print system health report to console
"""
import asyncio
import sys
import argparse
import logging
import os
import subprocess
import atexit
from logging.handlers import RotatingFileHandler

os.makedirs("logs", exist_ok=True)

# ── Obscura Background Service ────────────────────────────────────────────────
OBSCURA_PROCESS = None

def cleanup_obscura():
    global OBSCURA_PROCESS
    if OBSCURA_PROCESS:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(OBSCURA_PROCESS.pid)], capture_output=True)
            else:
                OBSCURA_PROCESS.terminate()
                OBSCURA_PROCESS.kill()
        except:
            pass

atexit.register(cleanup_obscura)

def start_obscura_if_exists():
    global OBSCURA_PROCESS
    obscura_path = "obscura.exe" if os.name == "nt" else "./obscura"
    if os.path.exists(obscura_path):
        try:
            OBSCURA_PROCESS = subprocess.Popen(
                [obscura_path, "serve", "--port", "9222", "--stealth"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            pass

# ── Logging setup ──────────────────────────────────────────────────────────────
_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.INFO)
_console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s"))
try:
    _console.stream.reconfigure(encoding="utf-8")
except AttributeError:
    pass

_file = RotatingFileHandler(
    "logs/auditor.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file.setLevel(logging.DEBUG)
_file.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[_console, _file])
logger = logging.getLogger(__name__)


# ── Main ───────────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(
        description="Visibility Auditor Execution Engine v2",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "command",
        choices=["audit-all", "audit", "dashboard", "schedule", "health", "mri"],
        help=(
            "audit-all   — Audit all marketplaces\n"
            "audit       — Audit one marketplace (--marketplace required)\n"
            "dashboard   — Launch web dashboard\n"
            "schedule    — Run on automatic schedule\n"
            "health      — Print health report\n"
            "mri         — Launch MRI dashboard/API (loopback, authenticated)"
        ),
    )
    parser.add_argument("--marketplace", help="Marketplace name (for 'audit' command)")
    parser.add_argument("--port", type=int, default=None,
                        help="Port (dashboard default: 8000, mri default: 8055)")
    parser.add_argument("--host", default="127.0.0.1", help="MRI host (default: 127.0.0.1)")
    parser.add_argument("--db", default=None, help="MRI SQLite path override")
    parser.add_argument("--interval-hours", type=float, help="Scheduler interval in hours")
    parser.add_argument("--daily-at", default="03:00", help="Scheduler daily run time HH:MM")

    args = parser.parse_args()

    try:
        start_obscura_if_exists()
        
        if args.command == "audit-all":
            from app.auditor.audit_runner import AuditRunner
            logger.info("Starting full audit — all marketplaces")
            runner = AuditRunner()
            await runner.run_all()

        elif args.command == "audit":
            if not args.marketplace:
                print("Error: --marketplace is required for the 'audit' command.", file=sys.stderr)
                sys.exit(1)
            from app.auditor.audit_runner import AuditRunner
            logger.info(f"Starting audit for: {args.marketplace}")
            runner = AuditRunner()
            await runner.run_marketplace_audit(args.marketplace)

        elif args.command == "dashboard":
            from app.dashboard.api import start_dashboard
            dash_port = args.port or 8000
            logger.info(f"Starting dashboard on http://localhost:{dash_port}")
            await start_dashboard(port=dash_port)

        elif args.command == "mri":
            # B-03: the MRI server is a blocking uvicorn app. It must NOT be
            # started from inside this coroutine: uvicorn.run() calls
            # asyncio.run() internally, which fails with "cannot be called from
            # a running event loop". `__main__` dispatches `mri` synchronously
            # before asyncio.run(main()) for exactly this reason.
            raise RuntimeError(
                "mri must be dispatched synchronously from __main__, not from main()"
            )

        elif args.command == "schedule":
            from app.scheduler.audit_scheduler import AuditScheduler
            scheduler = AuditScheduler(
                interval_hours=args.interval_hours,
                daily_at=args.daily_at,
            )
            logger.info(
                f"Scheduler started — "
                + (f"every {args.interval_hours}h" if args.interval_hours else f"daily at {args.daily_at}")
            )
            await scheduler.start()

        elif args.command == "health":
            from app.intelligence.health_monitor import health_summary
            from app.utils.circuit_breaker import all_breaker_statuses
            summary = await health_summary()
            breakers = all_breaker_statuses()
            print("\n=== SYSTEM HEALTH ===")
            print(f"  Status       : {summary.get('status','?')}")
            print(f"  Events (24h) : {summary.get('total_events',0)}")
            print(f"  Errors       : {summary.get('errors',0)}")
            print(f"  Error rate   : {summary.get('error_rate_pct',0):.1f}%")
            print(f"  Last event   : {summary.get('last_event','—')}")
            print("\n  Per marketplace:")
            for mp in summary.get("by_marketplace", []):
                print(f"    {mp['marketplace']:<20} ok={mp['ok']} err={mp['errors']}")
            if breakers:
                print("\n  Circuit Breakers:")
                for b in breakers:
                    print(f"    {b['name']:<20} [{b['state']}] failures={b['failure_count']}")
            if summary.get("recent_errors"):
                print("\n  Recent Errors:")
                for e in summary["recent_errors"][:3]:
                    print(f"    [{e['marketplace']}] {e['event_type']} — {e['detail']}")
            print()
    except (KeyboardInterrupt, SystemExit) as exc:
        logger.info("Process interrupted. Cleaning up active tasks and closing browsers...")
        # Cancel all running tasks so their finally blocks run
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Graceful shutdown completed.")
        # B-03: do not swallow SystemExit — it carries the process exit code.
        # Without this, `run.py mri` returning a preflight/startup error (2..5)
        # was silently converted into a success (rc=0).
        if isinstance(exc, SystemExit):
            raise


if __name__ == "__main__":
    # B-03: `run.py mri` runs a blocking uvicorn server. Dispatch it before the
    # asyncio runner so uvicorn can own the event loop (nested asyncio.run()
    # raises "cannot be called from a running event loop").
    # Operational DB bootstrap: uses the OFFICIAL additive schema initializer.
    # Idempotent, never overwrites an existing database.
    if len(sys.argv) > 1 and sys.argv[1] == "init-db":
        from app.mri_dashboard.mri_entrypoint import ensure_operational_db
        target = None
        if "--db" in sys.argv:
            i = sys.argv.index("--db")
            if i + 1 < len(sys.argv):
                target = sys.argv[i + 1]
        raise SystemExit(0 if ensure_operational_db(target) else 1)

    if len(sys.argv) > 1 and sys.argv[1] == "mri":
        from app.mri_dashboard.mri_entrypoint import main as mri_main
        raise SystemExit(mri_main(sys.argv[2:]))
    asyncio.run(main())
