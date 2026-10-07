import re
from app.loaders.multivende_loader import get_multivende_loader

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

def is_nicopoly(product: dict, marketplace: str = "") -> bool:
    title = str(product.get("title") or product.get("product_title") or product.get("name") or "").strip()
    title_lower = title.lower()
    vendor = str(product.get("vendor") or product.get("brand") or "").strip().lower()

    # 0. Anti-banner filter: short titles or blacklisted promotional phrases
    # FIX: Usar word-boundary matching para BANNER_BLACK_LIST en vez de substring
    # "ad" como substring rechazaba "bufanda", "rosado", etc.
    if any(re.search(rf"\b{re.escape(b)}\b", title_lower) for b in BANNER_BLACK_LIST) or (len(title) < 4 and not product.get("marketplace_sku")):
        return False

    # Block explicit competitor brands unless Nicopoly is explicitly in title or vendor
    if any(re.search(rf"\b{c}\b", f"{title_lower} {vendor}") for c in COMPETITOR_BRANDS):
        if not any(p in f"{title_lower} {vendor}" for p in ["nicopoly", "nicopolo", "nico poly"]):
            return False

    # FIX RIP-1: respetar la marca extraida por el scraper. Si el vendor/brand es
    # NO vacio y NO es un patron Nicopoly, el producto es de otra marca (ej. Ripley
    # "RAINDOOR ... N07097EXL", "GENÉRICO ... N07007AS"). El lookup por SKU/titulo
    # NO debe matchear un SKU Nicopoly embebido en el titulo de un producto ajeno.
    if vendor and not any(re.search(p, vendor) for p in NICOPOLY_PATTERNS):
        return False

    # 1. Deterministic lookup via Multivende Matrix if marketplace or SKU is present
    loader = get_multivende_loader()
    mkt = marketplace or product.get("marketplace", "")
    
    # Try by marketplace_sku or item ID if available
    mkt_sku = product.get("marketplace_sku") or product.get("sku", "")
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
            return True

    # Try by title lookup in Multivende matrix
    title = str(product.get("title") or product.get("product_title") or product.get("name") or "").strip()  # FIX: preservar fallback de campos
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
            return True

    # 2. Heuristic fallback by brand / title pattern
    vendor = product.get("vendor") or product.get("brand", "")
    search_text = f"{title} {vendor}".lower()
    
    for pattern in NICOPOLY_PATTERNS:
        if re.search(pattern, search_text):
            return True
            
    return False


