import re
from app.loaders.multivende_loader import get_multivende_loader
from app.mri_autonomous.experience_store import ExperienceStore

NICOPOLY_PATTERNS = [
    r"nicopoly",
    r"nicopolo", # Common typo
    r"nico poly"
]

BANNER_BLACK_LIST = [
    "oferta imperdible", "mÃ¡s vendido", "mas vendido", "disponible en",
    "promocionado", "publicidad", "sin match", "ad"
]

COMPETITOR_BRANDS = [
    "zara", "topshop", "wild lama", "mango", "sybilla", "h&m", "hm",
    "marquis", "foster", "bubba", "lippi", "maui", "rip curl", "daite",
    "intime", "flores", "monarch", "kayser", "palmers", "caffarena",
    "sicurezza", "lady genny", "bambino", "op", "tribal", "triumph"
]

def _get_store():
    try:
        return ExperienceStore()
    except Exception:
        return None

def is_nicopoly(product: dict, marketplace: str = "") -> bool:
    title = str(product.get("title") or product.get("product_title") or product.get("name") or "").strip()
    title_lower = title.lower()
    vendor = str(product.get("vendor") or product.get("brand") or "").strip().lower()
    mkt = marketplace or product.get("marketplace", "")
    mkt_sku = product.get("marketplace_sku") or product.get("sku", "")

    # 0. Anti-banner filter
    if any(re.search(rf"\b{re.escape(b)}\b", title_lower) for b in BANNER_BLACK_LIST) or (len(title) < 4 and not mkt_sku):
        return False

    if any(re.search(rf"\b{c}\b", f"{title_lower} {vendor}") for c in COMPETITOR_BRANDS):
        if not any(p in f"{title_lower} {vendor}" for p in ["nicopoly", "nicopolo", "nico poly"]):
            return False

    if vendor and not any(re.search(p, vendor) for p in NICOPOLY_PATTERNS):
        return False

    store = _get_store()
    
    # Check Memory First
    if store and mkt and mkt_sku:
        mem = store.get_experience_item(mkt, "Nicopoly", "IDENTITY", mkt_sku)
        if mem and mem.get("status") in ["VALIDATED", "LAST_GOOD"]:
            # Known identity!
            product["sku_master"] = mem.get("parent_identity", "")
            return True

    # 1. Deterministic lookup via Multivende Matrix
    loader = None
    try:
        loader = get_multivende_loader()
    except Exception:
        pass
        
    if loader:
        if mkt_sku:
            match = loader.lookup_sku(mkt, mkt_sku)
            if match:
                product["sku_master"] = match.get("sku_master", "")
                mkt_prices = match.get("prices", {})
                mkt_offers = match.get("offers", {})
                mkt_key = mkt.lower().strip()
                product["price_multivende"] = mkt_prices.get(mkt_key, 0.0)
                product["price_multivende_offer"] = mkt_offers.get(mkt_key, 0.0)
                product["stock_multivende"] = match.get("stock", -1)
                
                # Save to Memory
                if store and mkt_sku:
                    store.record_experience(
                        marketplace=mkt,
                        brand="Nicopoly",
                        knowledge_type="IDENTITY",
                        value=mkt_sku,
                        parent_identity=product["sku_master"],
                        discovery_method="multivende_sku_match",
                        status="VALIDATED"
                    )
                return True

        if title:
            match = loader.lookup_sku(mkt, title)
            if match:
                product["sku_master"] = match.get("sku_master", "")
                mkt_prices = match.get("prices", {})
                mkt_offers = match.get("offers", {})
                mkt_key = mkt.lower().strip()
                product["price_multivende"] = mkt_prices.get(mkt_key, 0.0)
                product["price_multivende_offer"] = mkt_offers.get(mkt_key, 0.0)
                product["stock_multivende"] = match.get("stock", -1)
                
                # Save to Memory
                if store and mkt_sku:
                    store.record_experience(
                        marketplace=mkt,
                        brand="Nicopoly",
                        knowledge_type="IDENTITY",
                        value=mkt_sku,
                        parent_identity=product["sku_master"],
                        discovery_method="multivende_title_match",
                        status="VALIDATED"
                    )
                return True

    # 2. Heuristic fallback
    search_text = f"{title} {vendor}".lower()
    
    for pattern in NICOPOLY_PATTERNS:
        if re.search(pattern, search_text):
            # Save heuristic match to memory
            if store and mkt and mkt_sku:
                store.record_experience(
                    marketplace=mkt,
                    brand="Nicopoly",
                    knowledge_type="IDENTITY",
                    value=mkt_sku,
                    discovery_method="heuristic_regex",
                    status="VALIDATED"
                )
            return True
            
    return False


