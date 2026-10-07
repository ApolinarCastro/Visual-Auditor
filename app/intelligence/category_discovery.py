"""
Category Discovery & Coverage Audit Module
- Compares brand-level global catalog listings against configured SVMP categories
- Detects unmonitored or out-of-scope categories where products are published
- Identifies orphan products outside the configured category scope
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path
from app.loaders.excel_loader import ExcelLoader
from app.loaders.rule_loader import RuleLoader
from app.storage.sqlite_manager import SQLiteManager

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class CategoryDiscoveryEngine:
    def __init__(self):
        self.excel_loader = ExcelLoader()
        self.rule_loader = RuleLoader()
        self.db = SQLiteManager()

    async def audit_marketplace_coverage(self, marketplace: str) -> Dict[str, Any]:
        """Audits category coverage for a specific marketplace by comparing global census vs category sum."""
        logger.info(f"[CategoryDiscovery] Starting category coverage audit for: {marketplace}")
        
        # Load configured categories from SVMP.xlsx
        configured_tasks = self.excel_loader.load_tasks()
        mkt_tasks = [t for t in configured_tasks if t.marketplace.lower() == marketplace.lower()]
        configured_categories = [t.category_marketplace for t in mkt_tasks]
        configured_categories_lower = {c.lower() for c in configured_categories}

        rules = self.rule_loader.get_rules_for_marketplace(marketplace)
        phase1_url = rules.get("phase_1_url", "") if rules else ""

        # Fetch latest audits for this marketplace from database
        all_latest = await self.db.get_latest_audits()
        latest_audits = [a for a in all_latest if a.get("marketplace", "").lower() == marketplace.lower()]
        
        # Get Global Census count (Phase 1) — FIX: usar el censo global REAL del dia.
        # Fuentes: 1) health_log (global_census persistido por audit_runner),
        #          2) logs/auditor.log de hoy, 3) proxy MAX (solo ultimo recurso).
        global_census_count = None
        census_source = "none"
        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            async with self.db._connect() as dbconn:
                row = await dbconn.execute_fetchall(
                    "SELECT detail FROM health_log WHERE marketplace=? AND event_type='global_census' "
                    "AND substr(recorded_at,1,10)=? ORDER BY recorded_at DESC LIMIT 1",
                    (marketplace, today_str),
                )
            if row and str(row[0][0]).strip().isdigit():
                global_census_count = int(str(row[0][0]).strip())
                census_source = "phase1_healthlog"
        except Exception as e:
            logger.debug(f"[CategoryDiscovery] health_log no disponible: {e}")

        if global_census_count is None:
            try:
                log_path = BASE_DIR / "logs" / "auditor.log"
                if log_path.exists():
                    with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                        best = None
                        for line in lf:
                            if line.startswith(today_str) and f"[{marketplace}] Global Nicopoly count:" in line:
                                m = re.search(r"Global Nicopoly count: (\d+)", line)
                                if m:
                                    best = int(m.group(1))
                        if best is not None:
                            global_census_count = best
                            census_source = "phase1_logfile"
            except Exception as e:
                logger.debug(f"[CategoryDiscovery] log no disponible: {e}")

        if global_census_count is None:
            global_census_count = max([a.get("total_nicopoly", 0) for a in latest_audits] + [0]) if latest_audits else 0
            census_source = "proxy_max"
        
        # Sum nicopoly products across all configured categories
        sum_category_nicopoly = sum([a.get("total_nicopoly", 0) for a in latest_audits if a.get("category", "").lower() in configured_categories_lower])
        
        # Determine orphan / hidden count
        orphan_count = max(0, global_census_count - sum_category_nicopoly) if global_census_count > 0 else 0
        
        coverage_pct = 100.0
        if global_census_count > 0:
            coverage_pct = round(min(100.0, (sum_category_nicopoly / global_census_count) * 100.0), 1)
            
        status = "EXCELLENT"
        if coverage_pct < 80.0:
            status = "CRITICAL"
        elif coverage_pct < 95.0:
            status = "DEGRADED"

        # INDICACION: deteccion de productos en categorias NO incluidas.
        # No se incorporan automaticamente (detencion): solo se registra una alerta
        # para que el operador decida si agregarlas a SVMP.xlsx / Logica_Operacional.
        if orphan_count > 0:
            try:
                from app.intelligence.trend_engine import record_custom_alert
                await record_custom_alert(
                    marketplace=marketplace,
                    category="Cobertura",
                    alert_type="Categorias no incluidas",
                    message=(
                        f"Se detectaron {orphan_count} productos Nicopoly fuera de las "
                        f"{len(configured_categories)} categorias configuradas "
                        f"(cobertura {coverage_pct}%). Posibles categorias nuevas no "
                        f"incluidas: revisar el marketplace y agregarlas manualmente si corresponde."
                    ),
                    prev_value=float(sum_category_nicopoly),
                    curr_value=float(global_census_count),
                )
                logger.warning(
                    f"[CategoryDiscovery] {marketplace}: {orphan_count} productos fuera de "
                    f"categorias configuradas (cobertura {coverage_pct}%) - alerta registrada"
                )
            except Exception as alert_err:
                logger.warning(f"[CategoryDiscovery] No se pudo registrar la alerta de cobertura: {alert_err}")

        return {
            "marketplace": marketplace,
            "configured_categories_count": len(configured_categories),
            "configured_categories": configured_categories,
            "global_census_count": global_census_count,
            "sum_category_nicopoly": sum_category_nicopoly,
            "orphan_products_count": orphan_count,
            "coverage_pct": coverage_pct,
            "status": status,
            "census_source": census_source,
            "brand_census_url": phase1_url,
            "unmonitored_categories_detected": []
        }

    async def run_global_coverage_report(self) -> List[Dict[str, Any]]:
        results = []
        for mkt in ["Paris", "Falabella", "Ripley", "Mercado Libre"]:
            res = await self.audit_marketplace_coverage(mkt)
            results.append(res)
        return results
