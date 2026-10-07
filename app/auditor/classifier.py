from app.config.thresholds import PRESENCE_THRESHOLDS, MARKETPLACE_THRESHOLDS, RISK_LEVELS

def classify_presence(pct30: float, marketplace: str = None) -> str:
    # Use custom thresholds if defined for this marketplace, otherwise fallback to defaults
    ths = PRESENCE_THRESHOLDS
    if marketplace and marketplace in MARKETPLACE_THRESHOLDS:
        ths = MARKETPLACE_THRESHOLDS[marketplace]

    if pct30 >= ths["EXCELENTE"]:
        return "EXCELENTE"
    if pct30 >= ths["BUENA"]:
        return "BUENA"
    if pct30 >= ths["MEDIA"]:
        return "MEDIA"
    return "CRITICA"

def classify_risk(presence_level: str) -> str:
    if presence_level == "EXCELENTE":
        return "BAJO"
    if presence_level == "BUENA":
        return "MEDIO"
    if presence_level == "MEDIA":
        return "ALTO"
    return "CRITICO"

def identify_opportunity(presence_level: str) -> str:
    if presence_level in ["MEDIA", "CRITICA"]:
        return "ALTA (Mejorar posicionamiento orgánico)"
    return "BAJA (Mantener liderazgo)"
