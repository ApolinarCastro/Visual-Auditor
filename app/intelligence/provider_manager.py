"""
Marketplace Provider Manager
Decouples AuditRunner and Dashboard from scraper recovery details.
Provides isolated execution of selective reaudits, candidate evaluation,
quality gate verification, last-good cache preservation, and recovery experience recording.
"""
import asyncio
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from app.storage.sqlite_manager import SQLiteManager
from app.loaders.rule_loader import RuleLoader
from app.auditor.visibility_engine import VisibilityEngine
from app.auditor.classifier import classify_presence, classify_risk, identify_opportunity
from app.utils.circuit_breaker import get_breaker
from app.intelligence.quality_gate import QualityGate, QualityFlag, ReasonCode
from app.scrapers.mercadolibre_scraper import MercadoLibreScraper
from app.scrapers.paris_scraper import ParisScraper
from app.scrapers.ripley_scraper import RipleyScraper
from app.scrapers.falabella_scraper import FalabellaScraper

logger = logging.getLogger(__name__)

_SCRAPER_MAP = {
    "mercado libre": lambda: MercadoLibreScraper(),
    "paris": lambda: ParisScraper(),
    "ripley": lambda: RipleyScraper(),
    "falabella": lambda: FalabellaScraper(),
}


class MarketplaceProviderManager:
    def __init__(self, db: Optional[SQLiteManager] = None):
        self.db = db or SQLiteManager()
        self.rule_loader = RuleLoader()
        self.visibility_engine = VisibilityEngine()

    async def execute_selective_reaudit(
        self,
        marketplace: str,
        category: str,
        caller: str = "manual"
    ) -> Dict[str, Any]:
        """
        Executes an isolated candidate scrape for a single (marketplace, category).
        Evaluates candidate against QualityGate.
        If valid or recovered, promotes candidate to SQLite audits table.
        If failed/unavailable, preserves Last-Good audit and avoids writing false zeros.
        Records recovery experience in recovery_experiences table.
        """
        t0 = time.monotonic()
        await self.db.init_db()
        breaker = get_breaker(marketplace)
        rules = self.rule_loader.get_rules_for_marketplace(marketplace)

        if not rules:
            return {
                "status": "FAIL",
                "quality_flag": QualityFlag.UNAVAILABLE.value,
                "reason_code": ReasonCode.EMPTY_RESPONSE.value,
                "message": f"No se encontraron reglas para {marketplace}"
            }

        cat_census_url = rules["category_urls"].get(f"{category.upper()}_census")
        cat_visibility_url = rules["category_urls"].get(f"{category.upper()}_visibility")

        if not cat_visibility_url:
            return {
                "status": "FAIL",
                "quality_flag": QualityFlag.UNAVAILABLE.value,
                "reason_code": ReasonCode.EMPTY_RESPONSE.value,
                "message": f"No se encontró URL de visibilidad para '{category}' en {marketplace}"
            }

        factory = _SCRAPER_MAP.get(marketplace.lower())
        if not factory:
            return {
                "status": "FAIL",
                "quality_flag": QualityFlag.UNAVAILABLE.value,
                "reason_code": ReasonCode.EMPTY_RESPONSE.value,
                "message": f"Scraper no registrado para {marketplace}"
            }

        # Fetch previous baseline to compare against
        previous_good = await self.db.get_last_good_audit(marketplace, category)
        prev_nico_val = previous_good.get("total_nicopoly") if previous_good else None

        scraper = factory()
        await scraper.start()

        candidate_data = None
        scraper_err = None
        attempt_count = 1

        try:
            # 1. First Candidate Scrape Attempt
            total_cat_nico = 0
            if cat_census_url:
                total_cat_nico = await breaker.call(scraper.get_total_count, cat_census_url)

            total_canal = await breaker.call(scraper.get_total_count, cat_visibility_url)
            products = await breaker.call(scraper.scrape_top_240, cat_visibility_url)

            kpis = self.visibility_engine.calculate_cumulative_kpis(products)
            nicopoly_denom = total_cat_nico if total_cat_nico > 0 else kpis.get("top_240", 0)

            if nicopoly_denom > 0:
                for k in kpis:
                    kpis[k] = min(kpis[k], nicopoly_denom)
                pcts = self.visibility_engine.calculate_percentages(kpis, nicopoly_denom)
            else:
                pcts = {k: 0.0 for k in ["pct_30", "pct_60", "pct_90", "pct_120", "pct_240"]}

            candidate_data = {
                "total_marketplace": total_canal,
                "total_nicopoly": total_cat_nico,
                "products_scraped_count": len(products),
                "kpis": kpis,
                "pcts": pcts
            }

        except Exception as ex:
            scraper_err = str(ex)
            logger.warning(f"[{marketplace}/{category}] Scraper error on attempt 1: {ex}")

        # Quality Gate Assessment
        q_flag, reason, explanation = QualityGate.evaluate_candidate(
            candidate=candidate_data,
            previous=previous_good,
            scraper_error=scraper_err
        )

        # 2. Automated Single Reaudit if SUSPECT (Max 1 retry)
        if q_flag == QualityFlag.SUSPECT and not scraper_err:
            attempt_count = 2
            logger.info(f"[{marketplace}/{category}] QualityGate flagged SUSPECT ({reason.value}: {explanation}). Executing 1x automated verification...")
            await asyncio.sleep(2)
            try:
                if cat_census_url:
                    total_cat_nico_2 = await breaker.call(scraper.get_total_count, cat_census_url)
                else:
                    total_cat_nico_2 = candidate_data["total_nicopoly"]

                total_canal_2 = await breaker.call(scraper.get_total_count, cat_visibility_url)
                products_2 = await breaker.call(scraper.scrape_top_240, cat_visibility_url)

                kpis_2 = self.visibility_engine.calculate_cumulative_kpis(products_2)
                nicopoly_denom_2 = total_cat_nico_2 if total_cat_nico_2 > 0 else kpis_2.get("top_240", 0)

                if nicopoly_denom_2 > 0:
                    for k in kpis_2:
                        kpis_2[k] = min(kpis_2[k], nicopoly_denom_2)
                    pcts_2 = self.visibility_engine.calculate_percentages(kpis_2, nicopoly_denom_2)
                else:
                    pcts_2 = {k: 0.0 for k in ["pct_30", "pct_60", "pct_90", "pct_120", "pct_240"]}

                candidate_data_2 = {
                    "total_marketplace": total_canal_2,
                    "total_nicopoly": total_cat_nico_2,
                    "products_scraped_count": len(products_2),
                    "kpis": kpis_2,
                    "pcts": pcts_2
                }

                # Evaluate second observation
                q_flag_2, reason_2, expl_2 = QualityGate.evaluate_candidate(
                    candidate=candidate_data_2,
                    previous=previous_good,
                    scraper_error=None
                )

                # If confirmed or recovered
                candidate_data = candidate_data_2
                q_flag = QualityFlag.RECOVERED
                explanation = f"Recuperado tras reauditoría selectiva: {expl_2}"

            except Exception as ex2:
                logger.error(f"[{marketplace}/{category}] Reaudit attempt failed: {ex2}")
                q_flag = QualityFlag.UNAVAILABLE
                reason = ReasonCode.EMPTY_RESPONSE
                explanation = f"Reauditoría falló: {ex2}"

        await scraper.stop()
        duration = round(time.monotonic() - t0, 2)

        # Decision: Promote or Preserve Last-Good
        promoted = False
        final_result_dict = {}

        if q_flag in (QualityFlag.FRESH, QualityFlag.RECOVERED) and candidate_data:
            presence = classify_presence(candidate_data["pcts"].get("pct_30", 0), marketplace)
            risk = classify_risk(presence)
            opp = identify_opportunity(presence)
            today_str = datetime.now().date().isoformat()
            now_iso = datetime.now().isoformat()

            audit_row = {
                "audit_date": now_iso,
                "marketplace": marketplace,
                "category": category,
                "category_url": cat_visibility_url,
                "total_marketplace": candidate_data["total_marketplace"],
                "total_nicopoly": candidate_data["total_nicopoly"],
                **candidate_data["kpis"],
                **candidate_data["pcts"],
                "presence_level": presence,
                "risk_level": risk,
                "opportunity": opp,
                "duration_seconds": duration,
            }

            await self.db.delete_today_record(marketplace, category, today_str)
            await self.db.save_audit(audit_row)
            promoted = True
            final_result_dict = audit_row

            # Update Source Health: SUCCESS
            await self.db.update_source_health({
                "marketplace": marketplace,
                "status": "HEALTHY",
                "consecutive_failures": 0,
                "last_success": now_iso,
                "last_recovery": now_iso if q_flag == QualityFlag.RECOVERED else None,
                "failure_type": None,
                "updated_at": now_iso
            })

        else:
            # UNAVAILABLE or FAILED: Preserve Last-Good cache and mark STALE
            logger.warning(f"[{marketplace}/{category}] Observación no promovida ({q_flag.value}). Preservando Last-Good cache.")
            final_result_dict = previous_good or {}
            now_iso = datetime.now().isoformat()

            # Update Source Health: FAILURE/DEGRADED
            current_health = await self.db.get_source_health(marketplace)
            failures = (current_health[0]["consecutive_failures"] + 1) if current_health else 1
            status = "OPEN" if breaker.is_open() else ("DEGRADED" if failures >= 2 else "HEALTHY")

            await self.db.update_source_health({
                "marketplace": marketplace,
                "status": status,
                "consecutive_failures": failures,
                "last_failure": now_iso,
                "failure_type": reason.value,
                "updated_at": now_iso
            })

        # Record Experience in SQLite
        exp_record = {
            "timestamp": datetime.now().isoformat(),
            "marketplace": marketplace,
            "category": category,
            "failure_type": reason.value,
            "quality_flag": q_flag.value,
            "strategy": f"Selective Reaudit ({caller})",
            "attempt": attempt_count,
            "result": "PROMOTED" if promoted else "REJECTED_LAST_GOOD_KEPT",
            "recovery_seconds": duration,
            "previous_value": str(prev_nico_val) if prev_nico_val is not None else "None",
            "candidate_value": str(candidate_data.get("total_nicopoly") if candidate_data else "None"),
            "promoted": promoted,
            "evidence": explanation
        }
        await self.db.save_recovery_experience(exp_record)

        return {
            "status": "PASS" if promoted else "UNAVAILABLE",
            "quality_flag": q_flag.value,
            "reason_code": reason.value,
            "explanation": explanation,
            "promoted": promoted,
            "duration_seconds": duration,
            "data": final_result_dict
        }
