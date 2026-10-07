"""
Enhanced Audit Runner v2
- Circuit Breaker per marketplace
- Health monitoring (timed_event)
- Trend analysis + alerts after each category
- Structured duration tracking
- Cleaner per-category retry with proper logging
"""
import asyncio
import time
from datetime import datetime
from app.loaders.excel_loader import ExcelLoader
from app.loaders.rule_loader import RuleLoader
from app.scrapers.mercadolibre_scraper import MercadoLibreScraper
from app.scrapers.paris_scraper import ParisScraper
from app.scrapers.ripley_scraper import RipleyScraper
from app.scrapers.falabella_scraper import FalabellaScraper
from app.auditor.visibility_engine import VisibilityEngine
from app.auditor.classifier import classify_presence, classify_risk, identify_opportunity
from app.storage.sqlite_manager import SQLiteManager
from app.utils.circuit_breaker import get_breaker
from app.intelligence.trend_engine import run_trend_analysis
from app.intelligence.health_monitor import timed_event
from app.config.settings import MAX_RETRIES
import logging

logger = logging.getLogger(__name__)


def _log_task_exception(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[BackgroundTask] Background task failed with exception: {e}", exc_info=True)


_SCRAPER_MAP = {
    "mercado libre": lambda: MercadoLibreScraper(),
    "paris": lambda: ParisScraper(),
    "ripley": lambda: RipleyScraper(),
    "falabella": lambda: FalabellaScraper(),
}


_global_audit_lock = asyncio.Lock()


class AuditRunner:
    def __init__(self):
        self.excel_loader = ExcelLoader()
        self.rule_loader = RuleLoader()
        self.visibility_engine = VisibilityEngine()
        self.db = SQLiteManager()

    async def reaudit_category(self, marketplace: str, category: str) -> dict:
        """Performs an isolated selective reaudit on a single category using ProviderManager."""
        from app.intelligence.provider_manager import MarketplaceProviderManager
        pm = MarketplaceProviderManager(self.db)
        return await pm.execute_selective_reaudit(marketplace, category, caller="audit_runner")

    async def run_marketplace_audit(self, marketplace: str, generate_html: bool = True):
        breaker = get_breaker(marketplace)
        breaker.reset()
        logger.info(f"=== Starting audit: {marketplace} ===")
        # DB init moved to run_all or handled safely to prevent concurrent locks
        await self.db.init_db()

        tasks = self.excel_loader.load_tasks()
        tasks = [t for t in tasks if t.marketplace.lower() == marketplace.lower()]

        if not tasks:
            logger.warning(f"[{marketplace}] No tasks found in SVMP.xlsx")
            return

        rules = self.rule_loader.get_rules_for_marketplace(marketplace)
        if not rules:
            logger.error(f"[{marketplace}] No rules found — cannot audit")
            return

        factory = _SCRAPER_MAP.get(marketplace.lower())
        if not factory:
            logger.error(f"[{marketplace}] No scraper registered")
            return

        scraper = factory()
        await scraper.start()

        audit_start = time.monotonic()

        try:
            # Phase 1 — Global census
            phase_1_url = rules.get("phase_1_url")
            if not phase_1_url:
                logger.error(f"[{marketplace}] Missing phase_1_url in rules")
                return

            total_nicopoly = 0
            for attempt in range(1, MAX_RETRIES + 2):
                try:
                    async with timed_event(marketplace, "phase1_census"):
                        total_nicopoly = await breaker.call(
                            scraper.get_total_count, phase_1_url
                        )
                    break
                except Exception as e:
                    if attempt <= MAX_RETRIES:
                        wait = 15 * attempt
                        logger.warning(f"[{marketplace}] Phase 1 failed ({e}) — retrying in {wait}s")
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"[{marketplace}] Phase 1 permanently failed: {e}")
                        total_nicopoly = 0 # Continue with 0 to allow categories to attempt scraping
            logger.info(f"[{marketplace}] Global Nicopoly count: {total_nicopoly}")

            # INDICACION: persistir el censo global (Phase 1) del dia (telemetria).
            # Es el dato base para la deteccion de productos fuera de categorias incluidas.
            try:
                async with self.db._connect() as conn:
                    await conn.execute(
                        "INSERT INTO health_log (recorded_at, marketplace, category, event_type, duration_ms, status, detail) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (datetime.now().isoformat(), marketplace, "Phase1", "global_census",
                         0.0, "OK", str(total_nicopoly)),
                    )
                    await conn.commit()
            except Exception as persist_err:
                logger.warning(f"[{marketplace}] No se pudo persistir el censo global: {persist_err}")

            succeeded = 0
            failed = 0

            pending_tasks = tasks
            max_passes = 2

            for current_pass in range(1, max_passes + 1):
                if not pending_tasks:
                    break
                
                if current_pass > 1:
                    logger.info(f"[{marketplace}] === Pasada automática {current_pass} para {len(pending_tasks)} categorías fallidas o en cero ===")
                    await asyncio.sleep(2)
                
                next_pending = []

                for task in pending_tasks:
                    cat = task.category_marketplace

                    # Smart Resume (Option 1): Check if already successfully audited today
                    today_str = datetime.now().date().isoformat()
                    latest = await self.db.get_latest_for_category(marketplace, cat)
                    if latest and latest["audit_date"].startswith(today_str):
                        # A category record is complete only if both total_marketplace (Total Canal) and
                        # total_nicopoly (Total Nico) are greater than 0. If either is 0, the selective audit
                        # does NOT skip it, so it can run again to complete the missing zero values.
                        has_valid_data = (
                            latest.get("total_marketplace", 0) > 0 
                            and latest.get("total_nicopoly", 0) > 0
                        )
                        if has_valid_data:
                            logger.info(f"[{marketplace}/{cat}] Omitiendo: Ya auditado exitosamente hoy con datos completos (Total Canal y Total Nico > 0).")
                            continue

                    cat_census_url = task.url_nicopoly or (rules.get("category_urls", {}).get(f"{cat.upper()}_census") if rules else None)
                    cat_visibility_url = task.url_base or (rules.get("category_urls", {}).get(f"{cat.upper()}_visibility") if rules else None)

                    if not cat_visibility_url:
                        logger.warning(f"[{marketplace}] No visibility URL for '{cat}' — skipping")
                        continue

                    category_ok = False
                    zero_products = False

                    for attempt in range(1, MAX_RETRIES + 2):
                        try:
                            async with timed_event(marketplace, "category_scrape", category=cat):
                                # Phase 2 — Category census
                                total_cat_nicopoly = 0
                                if cat_census_url:
                                    total_cat_nicopoly = await asyncio.wait_for(breaker.call(
                                        scraper.get_total_count, cat_census_url
                                    ), timeout=180)

                                # Phase 3 — Visibility scrape
                                total_canal = await asyncio.wait_for(breaker.call(
                                    scraper.get_total_count, cat_visibility_url
                                ), timeout=180)
                                cat_t0 = time.monotonic()
                                products = await asyncio.wait_for(breaker.call(
                                    scraper.scrape_top_240, cat_visibility_url
                                ), timeout=300)
                                cat_duration = round(time.monotonic() - cat_t0, 1)

                            logger.info(
                                f"[{marketplace}/{cat}] "
                                f"products={len(products)} canal={total_canal} "
                                f"nico_cat={total_cat_nicopoly} ({cat_duration}s)"
                            )

                            # KPI Calculation
                            kpis = self.visibility_engine.calculate_cumulative_kpis(products)
                            nicopoly_denom = total_cat_nicopoly if total_cat_nicopoly > 0 else kpis.get("top_240", 0)

                            # Cap counts at nicopoly_denom to prevent mathematical anomalies (such as >100% visibility)
                            if nicopoly_denom > 0:
                                for key in kpis:
                                    kpis[key] = min(kpis[key], nicopoly_denom)

                            if nicopoly_denom == 0:
                                logger.warning(f"[{marketplace}/{cat}] Zero products — KPIs zeroed")
                                pcts = {k: 0.0 for k in ["pct_30", "pct_60", "pct_90", "pct_120", "pct_240"]}
                            else:
                                pcts = self.visibility_engine.calculate_percentages(kpis, nicopoly_denom)

                            presence = classify_presence(pcts.get("pct_30", 0), marketplace)
                            risk = classify_risk(presence)
                            opp = identify_opportunity(presence)

                            # Dedup: remove today's record before re-inserting
                            today_str = datetime.now().date().isoformat()
                            await self.db.delete_today_record(marketplace, cat, today_str)

                            audit_result = {
                                "audit_date": datetime.now().isoformat(),
                                "marketplace": marketplace,
                                "category": cat,
                                "category_url": cat_visibility_url,
                                "total_marketplace": total_canal,
                                "total_nicopoly": total_cat_nicopoly,
                                **kpis,
                                **pcts,
                                "presence_level": presence,
                                "risk_level": risk,
                                "opportunity": opp,
                                "duration_seconds": cat_duration,
                            }
                            await self.db.save_audit(audit_result)

                            # Save product snapshots if feature flag is enabled
                            from app.config.settings import ENABLE_PRODUCT_SNAPSHOTS
                            from app.auditor.nicopoly_matcher import is_nicopoly
                            if ENABLE_PRODUCT_SNAPSHOTS:
                                now_iso = datetime.now().isoformat()
                                today_str_snaps = datetime.now().date().isoformat()
                                snapshots = []

                                # Helper: resolve price_multivende via Multivende lookup if missing
                                from app.loaders.multivende_loader import get_multivende_loader
                                mv_loader = get_multivende_loader()

                                def _enrich_price_multivende(p: dict, mkt: str) -> None:
                                    """If price_multivende is still 0 after is_nicopoly(), try fuzzy title lookup."""
                                    if p.get("price_multivende", 0.0) > 0:
                                        return
                                    title = p.get("title", "")
                                    if title:
                                        match = mv_loader.lookup_sku(mkt, title)
                                        if match:
                                            mkt_key = mkt.lower().strip()
                                            p["price_multivende"] = match.get("prices", {}).get(mkt_key, 0.0)
                                            p["price_multivende_offer"] = match.get("offers", {}).get(mkt_key, 0.0)
                                            p["stock_multivende"] = match.get("stock", -1)
                                            if not p.get("sku_master"):
                                                p["sku_master"] = match.get("sku_master", "")

                                # 1. Capture 100% of brand products via brand-filtered census URL
                                if cat_census_url:
                                    try:
                                        # Clear today's snapshots for this category before re-inserting
                                        await self.db.delete_today_snapshots(marketplace, cat, today_str_snaps)
                                        brand_products = await asyncio.wait_for(breaker.call(
                                            scraper.scrape_top_240, cat_census_url
                                        ), timeout=300)
                                        for p in brand_products:
                                            is_nico = is_nicopoly(p, marketplace=marketplace)
                                            _enrich_price_multivende(p, marketplace)
                                            snapshots.append({
                                                "audit_date": now_iso,
                                                "marketplace": marketplace,
                                                "category": cat,
                                                "sku_master": p.get("sku_master", ""),
                                                "marketplace_sku": p.get("marketplace_sku", ""),
                                                "product_title": p.get("title", ""),
                                                "brand": p.get("vendor", "Nicopoly"),
                                                "price": p.get("price", 0.0),
                                                "price_multivende": p.get("price_multivende", 0.0),
                                                "price_multivende_offer": p.get("price_multivende_offer", 0.0),
                                                "stock_multivende": p.get("stock_multivende", -1),
                                                "position_absolute": p.get("position_absolute", 0),
                                                "is_nicopoly": is_nico
                                            })
                                    except Exception as ex:
                                        logger.warning(f"[{marketplace}/{cat}] Brand census scrape warning: {ex}")

                                # 2. Capture general category products for visibility ranking
                                if products:
                                    for p in products:
                                        is_nico = is_nicopoly(p, marketplace=marketplace)
                                        if is_nico:
                                            _enrich_price_multivende(p, marketplace)
                                        snapshots.append({
                                            "audit_date": now_iso,
                                            "marketplace": marketplace,
                                            "category": cat,
                                            "sku_master": p.get("sku_master", ""),
                                            "marketplace_sku": p.get("marketplace_sku", ""),
                                            "product_title": p.get("title", ""),
                                            "brand": p.get("vendor", ""),
                                            "price": p.get("price", 0.0),
                                            "price_multivende": p.get("price_multivende", 0.0),
                                            "position_absolute": p.get("position_absolute", 0),
                                            "is_nicopoly": True if is_nico else False
                                        })
                                if snapshots:
                                    await self.db.save_product_snapshots(snapshots)
                                    # FIX 4b: Recalcular total_nicopoly contando SKUs UNICOS.
                                    # El conteo anterior (sum de snapshots is_nicopoly) inflaba el total
                                    # porque la lista `snapshots` en memoria contiene el mismo producto
                                    # dos veces: una del flujo brand_products y otra del flujo products.
                                    # La dedup real ocurre dentro de save_product_snapshots() (seen_map).
                                    nico_snapshots = [s for s in snapshots if s.get("is_nicopoly")]
                                    seen_keys = set()
                                    for s in nico_snapshots:
                                        key = str(s.get("marketplace_sku", "")).strip() or str(s.get("product_title", "")).strip().lower()
                                        if key:
                                            seen_keys.add(key)
                                    # Only fallback to real_nicopoly_count if total_cat_nicopoly was 0 (census count failed)
                                    real_nicopoly_count = len(seen_keys)
                                    if total_cat_nicopoly == 0 and real_nicopoly_count > 0:
                                        total_cat_nicopoly = real_nicopoly_count
                                        nicopoly_denom = total_cat_nicopoly
                                        if nicopoly_denom > 0:
                                            for key in kpis:
                                                kpis[key] = min(kpis[key], nicopoly_denom)
                                            pcts = self.visibility_engine.calculate_percentages(kpis, nicopoly_denom)
                                        audit_result["total_nicopoly"] = total_cat_nicopoly
                                        audit_result.update(kpis)
                                        audit_result.update(pcts)
                                        await self.db.delete_today_record(marketplace, cat, today_str)
                                        await self.db.save_audit(audit_result)
                                        logger.info(f"[{marketplace}/{cat}] total_nicopoly fallback a snapshots reales: {real_nicopoly_count}")

                            # Run trend analysis + alert generation
                            task = asyncio.create_task(
                                run_trend_analysis(marketplace, cat)
                            )
                            task.add_done_callback(_log_task_exception)

                            logger.info(
                                f"[{marketplace}/{cat}] ✓ "
                                f"pct_30={pcts.get('pct_30', 0):.1f}% | "
                                f"{presence} | risk={risk}"
                            )
                            succeeded += 1
                            category_ok = True
                            # A category is considered incomplete / having "zero values" if:
                            # 1. Nicopoly top 240 visibility count is 0
                            # 2. Or total_canal (Total Canal) is 0
                            # 3. Or total_cat_nicopoly (Total Nico) is 0
                            # If so, we trigger a retry in the next automatic pass (Pass 2).
                            if (
                                kpis.get("top_240", 0) == 0 
                                or total_canal == 0 
                                or total_cat_nicopoly == 0
                            ):
                                zero_products = True
                            break  # success — exit retry loop

                        except Exception as cat_exc:
                            import traceback
                            tb_str = traceback.format_exc()
                            logger.error(f"[{marketplace}/{cat}] Exception trace:\n{tb_str}")
                            if attempt <= MAX_RETRIES:
                                wait = 15 * attempt
                                logger.warning(
                                    f"[{marketplace}/{cat}] Attempt {attempt}/{MAX_RETRIES+1} failed: "
                                    f"{cat_exc} — retrying in {wait}s"
                                )
                                await asyncio.sleep(wait)
                            else:
                                logger.error(
                                    f"[{marketplace}/{cat}] Permanently failed after "
                                    f"{MAX_RETRIES+1} attempts: {cat_exc}"
                                )
                                failed += 1
                                
                    # Auto-Retry (Option 2): Queue for the next automatic pass if failed or zero products
                    if not category_ok or zero_products:
                        next_pending.append(task)
            
            pending_tasks = next_pending

            total_duration = round(time.monotonic() - audit_start, 1)
            logger.info(
                f"=== Audit complete: {marketplace} | "
                f"✓{succeeded} ✗{failed} | {total_duration}s ==="
            )

        finally:
            await scraper.stop()
            try:
                await self.db.prune_and_optimize()
            except Exception as e:
                logger.error(f"[{marketplace}] Error during DB pruning/compaction: {e}")
            
            if generate_html:
                try:
                    from app.utils.report_generator import generate_report
                    generate_report()
                except Exception as e:
                    logger.error(f"[{marketplace}] Error compiling HTML report: {e}")

            # INDICACION: deteccion de categorias no incluidas al cierre de la auditoria.
            # Solo lectura + alerta; si falla, no afecta la auditoria.
            try:
                from app.intelligence.category_discovery import CategoryDiscoveryEngine
                await CategoryDiscoveryEngine().audit_marketplace_coverage(marketplace)
            except Exception as cov_err:
                logger.error(f"[{marketplace}] Error during category coverage detection: {cov_err}")

    async def run_all(self, marketplaces: list[str] | None = None):
        """Audit all registered marketplaces concurrently."""
        if marketplaces is not None and isinstance(marketplaces, str):
            raise TypeError("marketplaces argument must be a list of strings, not a string.")
            
        if _global_audit_lock.locked():
            logger.warning("[AuditRunner] Una auditoría ya está en curso. Ignorando esta petición para prevenir solapamiento.")
            return

        async with _global_audit_lock:
            logger.info(f"\n{'='*50}\nStarting parallel multi-agent audit\n{'='*50}")
            await self.db.init_db()
            if marketplaces is None:
                marketplaces = ["Mercado Libre", "Paris", "Ripley", "Falabella"]
            
            # Parallel execution design
            tasks = [self.run_marketplace_audit(mp, generate_html=False) for mp in marketplaces]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for mp, res in zip(marketplaces, results):
                if isinstance(res, Exception):
                    logger.error(f"[{mp}] Fatal error in parallel execution: {res}", exc_info=res)

            try:
                await self.db.prune_and_optimize()
            except Exception as e:
                logger.error(f"[DB] Error in global DB pruning/compaction: {e}")

            # Compile report after all marketplaces are completed
            try:
                from app.utils.report_generator import generate_report
                generate_report()
            except Exception as e:
                logger.error(f"[DB] Error compiling HTML report: {e}")

            # Run automated self-check test suite after audit completes
            try:
                import unittest
                from tests.test_regression_guardrails import TestRegressionGuardrails
                suite = unittest.TestLoader().loadTestsFromTestCase(TestRegressionGuardrails)
                runner = unittest.TextTestRunner(verbosity=0)
                test_res = runner.run(suite)
                if test_res.wasSuccessful():
                    logger.info("[AuditRunner] Post-audit self-check: All 7 regression guardrails PASSED ✓")
                else:
                    logger.warning(f"[AuditRunner] Post-audit self-check: {len(test_res.failures)} failures, {len(test_res.errors)} errors")
            except Exception as e:
                logger.warning(f"[AuditRunner] Could not run post-audit self-check: {e}")

        # Execute Post-Audit Automatic Materialization Pipeline OUTSIDE the global lock
        try:
            from app.config.settings import MRI_POST_AUDIT_AUTO_MATERIALIZE, DB_PATH
            if MRI_POST_AUDIT_AUTO_MATERIALIZE:
                logger.info("[AuditRunner] MRI_POST_AUDIT_AUTO_MATERIALIZE is True. Triggering materialization in background.")
                
                def _run_materializer_bg():
                    import traceback
                    try:
                        # Determine run identity from recent snapshots
                        import sqlite3
                        from datetime import datetime
                        conn = sqlite3.connect(DB_PATH)
                        conn.row_factory = sqlite3.Row
                        audit_start = getattr(self, '_audit_start_time', datetime.now().date().isoformat())
                        import os
                        os.environ["MRI_CURRENT_AUDIT_START"] = audit_start
                        
                        import sys
                        import os
                        from pathlib import Path
                        base_dir = Path(__file__).resolve().parent.parent.parent
                        sys.path.insert(0, str(base_dir)) # Ensure we can import the new module
                        from mri_post_audit_pipeline.v001.run_manifest_generator import get_run_manifest
                        from mri_post_audit_pipeline.v001.post_audit_materializer import PostAuditMaterializer
                        
                        manifest = get_run_manifest()
                        if not manifest:
                            logger.info("[PostAuditMaterializer] No snapshots found for today. Skipping materialization.")
                            return
                        
                        mat = PostAuditMaterializer(str(DB_PATH))
                        # Note: In production we would fetch the dynamic list of snapshot_ids.
                        # For now we'll just run on the range determined by the manifest.
                        import sqlite3
                        conn = sqlite3.connect(DB_PATH)
                        conn.row_factory = sqlite3.Row
                        c = conn.cursor()
                        c.execute("SELECT id FROM product_snapshots WHERE created_at >= ? AND created_at <= ?", (manifest["start_timestamp"], manifest["finish_timestamp"]))
                        snapshot_ids = [r['id'] for r in c.fetchall()]
                        conn.close()
                        
                        res = mat.run_materialization(manifest, snapshot_ids)
                        logger.info(f"[PostAuditMaterializer] Success: {res}")
                    except Exception as e:
                        logger.error(f"[PostAuditMaterializer] Failed: {e}\n{traceback.format_exc()}")

                # Trigger asynchronously
                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, _run_materializer_bg)
            else:
                logger.info("[AuditRunner] MRI_POST_AUDIT_AUTO_MATERIALIZE is False. Skipping automatic materialization.")
        except Exception as e:
            logger.error(f"[AuditRunner] Failed to invoke materialization trigger: {e}")

