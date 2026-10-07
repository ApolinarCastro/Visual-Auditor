"""
Quality Gate and Anomaly Evaluation Engine for Visibility Auditor
Enforces strict multi-factor evaluation of candidate observations:
- Distinguishes FRESH, SUSPECT, STALE, RECOVERED, UNAVAILABLE
- Handles reason codes without arbitrarily rejecting true catalog fluctuations
- Protects against False Zeros
"""
from enum import Enum
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class QualityFlag(str, Enum):
    FRESH = "FRESH"
    SUSPECT = "SUSPECT"
    STALE = "STALE"
    RECOVERED = "RECOVERED"
    UNAVAILABLE = "UNAVAILABLE"


class ReasonCode(str, Enum):
    NONE = "NONE"
    CAPTCHA = "CAPTCHA"
    WAF_BLOCK = "WAF_BLOCK"
    SESSION = "SESSION"
    TIMEOUT = "TIMEOUT"
    DOM_CHANGE = "DOM_CHANGE"
    SELECTOR = "SELECTOR"
    EMPTY_RESPONSE = "EMPTY_RESPONSE"
    PARTIAL_RESPONSE = "PARTIAL_RESPONSE"
    ZERO_ANOMALY = "ZERO_ANOMALY"
    VOLUME_DROP = "VOLUME_DROP"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    INCONSISTENT_TOTAL = "INCONSISTENT_TOTAL"


class QualityGate:
    """
    Evaluates candidate scrape observations before promotion to SQLite.
    Never marks a statistical fluctuation as outright INVALID; marks it as SUSPECT
    to trigger a single controlled selective reaudit.
    """

    @staticmethod
    def evaluate_candidate(
        candidate: Dict[str, Any],
        previous: Optional[Dict[str, Any]] = None,
        scraper_error: Optional[str] = None
    ) -> tuple[QualityFlag, ReasonCode, str]:
        """
        Returns (QualityFlag, ReasonCode, explanation).
        """
        # 1. Scraper / Network / Block failures
        if scraper_error:
            err_lower = scraper_error.lower()
            if "captcha" in err_lower:
                return QualityFlag.UNAVAILABLE, ReasonCode.CAPTCHA, f"Bloqueo por CAPTCHA detectado: {scraper_error}"
            if "waf" in err_lower or "403" in err_lower or "forbidden" in err_lower or "cloudflare" in err_lower or "shield" in err_lower:
                return QualityFlag.UNAVAILABLE, ReasonCode.WAF_BLOCK, f"Bloqueo por WAF/Bot Shield detectado: {scraper_error}"
            if "timeout" in err_lower or "timed out" in err_lower:
                return QualityFlag.UNAVAILABLE, ReasonCode.TIMEOUT, f"Timeout en navegación: {scraper_error}"
            if "session" in err_lower or "auth" in err_lower or "login" in err_lower:
                return QualityFlag.UNAVAILABLE, ReasonCode.SESSION, f"Fallo o expiración de sesión: {scraper_error}"
            return QualityFlag.UNAVAILABLE, ReasonCode.EMPTY_RESPONSE, f"Fallo de scraper: {scraper_error}"

        if not candidate:
            return QualityFlag.UNAVAILABLE, ReasonCode.EMPTY_RESPONSE, "Candidato vacío o no disponible"

        total_canal = int(candidate.get("total_marketplace", 0) or 0)
        total_nico = int(candidate.get("total_nicopoly", 0) or 0)
        top_240 = int(candidate.get("top_240", 0) or 0)
        products_scraped = int(candidate.get("products_scraped_count", len(candidate.get("products", []))))

        # 2. False-Zero Protection / Channel Empty State
        if total_canal == 0:
            return QualityFlag.UNAVAILABLE, ReasonCode.EMPTY_RESPONSE, "Total Canal = 0 sin productos cargados en DOM"

        # If Nico is 0 but canal had products, check if it's an anomaly compared to previous
        if total_nico == 0:
            if previous and int(previous.get("total_nicopoly", 0) or 0) > 5:
                # Dropped from >5 to 0 -> SUSPECT
                return QualityFlag.SUSPECT, ReasonCode.ZERO_ANOMALY, f"Total Nico cayó de {previous.get('total_nicopoly')} a 0 (posible filtro o selector no cargado)"
            # Legitimate 0 (e.g. category where brand has no inventory) -> FRESH

        # 3. Inconsistent totals / Mathematical anomalies
        if total_nico > total_canal and total_canal > 0:
            return QualityFlag.SUSPECT, ReasonCode.INCONSISTENT_TOTAL, f"Total Nico ({total_nico}) mayor que Total Canal ({total_canal})"

        if top_240 > total_nico and total_nico > 0:
            return QualityFlag.SUSPECT, ReasonCode.INCONSISTENT_TOTAL, f"TOP 240 ({top_240}) mayor que Total Nico ({total_nico})"

        # 4. Multi-factor statistical comparison with previous baseline
        if previous:
            prev_nico = int(previous.get("total_nicopoly", 0) or 0)
            if prev_nico > 0 and total_nico > 0:
                diff_ratio = (total_nico - prev_nico) / prev_nico
                # Significant drop > 30% when baseline is large
                if diff_ratio < -0.30 and prev_nico >= 20:
                    return QualityFlag.SUSPECT, ReasonCode.VOLUME_DROP, f"Caída notable en Total Nico ({prev_nico} -> {total_nico}, {diff_ratio:.1%})"
                # Significant spike > 60%
                if diff_ratio > 0.60 and prev_nico >= 20:
                    return QualityFlag.SUSPECT, ReasonCode.VOLUME_SPIKE, f"Aumento inusual en Total Nico ({prev_nico} -> {total_nico}, +{diff_ratio:.1%})"

        # 5. Normal verified observation
        return QualityFlag.FRESH, ReasonCode.NONE, "Observación válida y consistente"
