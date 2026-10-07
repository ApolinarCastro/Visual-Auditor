# Operational Presence Thresholds (based on TOP 30 percentage)
PRESENCE_THRESHOLDS = {
    "EXCELENTE": 70,  # 70% or more
    "BUENA": 50,      # 50% to 69%
    "MEDIA": 25,      # 25% to 49%
    "CRITICA": 0       # less than 25%
}

# Retailer-specific thresholds due to retail brands monopoly bias
MARKETPLACE_THRESHOLDS = {
    "Ripley": {
        "EXCELENTE": 30.0,  # 30% is excellent since Ripley favors own brands like Marquis/Index
        "BUENA": 20.0,
        "MEDIA": 10.0,
        "CRITICA": 0.0
    },
    "Falabella": {
        "EXCELENTE": 30.0,  # Falabella favors Sybilla/Americanino/Basement
        "BUENA": 20.0,
        "MEDIA": 10.0,
        "CRITICA": 0.0
    },
    "Paris": {
        "EXCELENTE": 30.0,  # Paris favors Alaniz/Opposite
        "BUENA": 20.0,
        "MEDIA": 10.0,
        "CRITICA": 0.0
    }
}

# Risk Levels
RISK_LEVELS = {
    "BAJO": "Presencia robusta en primeras posiciones.",
    "MEDIO": "Visibilidad aceptable pero con margen de mejora.",
    "ALTO": "Baja visibilidad, alto riesgo de no venta.",
    "CRITICO": "Invisibilidad casi total en el marketplace."
}
