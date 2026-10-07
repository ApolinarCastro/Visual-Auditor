from pathlib import Path
import os

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Database
SQLITE_DIR = DATA_DIR / "sqlite"
DB_PATH = SQLITE_DIR / "visibility.db"

# Default fallback settings
TOP_LIMIT = 240
HEADLESS = os.getenv("HEADLESS", "True").lower() == "true"
BROWSER_TIMEOUT = 30000  # ms
MAX_RETRIES = 2
CIRCUIT_BREAKER_THRESHOLD = 3
CIRCUIT_BREAKER_RECOVERY_S = 120

# Load from .agents/config.toml if present
CONFIG_TOML_PATH = BASE_DIR / ".agents" / "config.toml"
config_data = {}
if CONFIG_TOML_PATH.exists():
    try:
        try:
            import tomllib  # Python 3.11+
            with open(CONFIG_TOML_PATH, "rb") as f:
                config_data = tomllib.load(f)
        except ImportError:
            try:
                import toml
                with open(CONFIG_TOML_PATH, "r", encoding="utf-8") as f:
                    config_data = toml.load(f)
            except ImportError:
                # Basic fallback manual parser for config.toml to prevent dependency errors
                with open(CONFIG_TOML_PATH, "r", encoding="utf-8") as f:
                    current_section = None
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.startswith("[") and line.endswith("]"):
                            current_section = line[1:-1].strip()
                            config_data[current_section] = {}
                        elif "=" in line and current_section:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            # Try converting type
                            if v.lower() == "true":
                                v = True
                            elif v.lower() == "false":
                                v = False
                            elif v.startswith("[") and v.endswith("]"):
                                v = [item.strip().strip('"').strip("'") for item in v[1:-1].split(",") if item.strip()]
                            else:
                                try:
                                    if "." in v:
                                        v = float(v)
                                    else:
                                        v = int(v)
                                except ValueError:
                                    pass
                            config_data[current_section][k] = v
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to parse config.toml: {e}")

# Apply values from TOML config
audit_conf = config_data.get("audit", {})
TOP_LIMIT = int(audit_conf.get("top_limit", TOP_LIMIT))
MAX_RETRIES = int(audit_conf.get("max_retries", MAX_RETRIES))
CIRCUIT_BREAKER_THRESHOLD = int(audit_conf.get("circuit_breaker_threshold", CIRCUIT_BREAKER_THRESHOLD))
CIRCUIT_BREAKER_RECOVERY_S = int(audit_conf.get("circuit_breaker_recovery_s", CIRCUIT_BREAKER_RECOVERY_S))
# FIX ML-3 (14-Ago): enfriamiento largo para ML - la IP quedo marcada por la rafaga headless del 13-Ago
CIRCUIT_BREAKER_RECOVERY_ML_S = int(audit_conf.get("circuit_breaker_recovery_ml_s", 1800))

# Source files
EXCEL_SOURCE = BASE_DIR / "SVMP.xlsx"
RULES_DIR = BASE_DIR / "Logica_Operacional"
MULTIVENDE_EXCEL_PATH = BASE_DIR / "Actualización masiva de productos.xlsx"

# Feature Flags (Evolution / Pricing Intelligence)
ENABLE_PRICE_COLLECTION = os.getenv("ENABLE_PRICE_COLLECTION", "True").lower() == "true"
ENABLE_PRODUCT_SNAPSHOTS = os.getenv("ENABLE_PRODUCT_SNAPSHOTS", "True").lower() == "true"
MRI_POST_AUDIT_AUTO_MATERIALIZE = os.getenv("MRI_POST_AUDIT_AUTO_MATERIALIZE", "False").lower() == "true"

# MRI Dashboard Cutover Settings
COMMERCIAL_READ_MODE = os.getenv("COMMERCIAL_READ_MODE", "MRI_PRIMARY").upper()
if COMMERCIAL_READ_MODE not in ("LEGACY", "MRI_SHADOW", "MRI_PRIMARY"):
    COMMERCIAL_READ_MODE = "LEGACY"

AUTHORITY_REGISTRY = {
    "COMMERCIAL_PUBLICATIONS": {
        "paris": "MRI_PRIMARY",
        "falabella": "MRI_PRIMARY",
        "mercadolibre": "MRI_PRIMARY",
        "ripley": "UNRESOLVED_IDENTITY"
    },
    "VISIBILITY_KPI": "LEGACY_VA",
    "AUDIT_EXECUTION": "LEGACY_VA",
    "RESEARCH_CENSUS": "MRI_RESEARCH",
    "EVIDENCE": "MRI_PRIMARY"
}
