import pandas as pd
import logging
import re
from pathlib import Path
from app.config.settings import MULTIVENDE_EXCEL_PATH

logger = logging.getLogger(__name__)

class MultivendeLoader:
    def __init__(self, excel_path=MULTIVENDE_EXCEL_PATH):
        self.excel_path = Path(excel_path)
        self._loaded = False
        self._marketplace_indexes = {
            "mercado libre": {},
            "paris": {},
            "falabella": {},
            "ripley": {}
        }
        self._sku_master_map = {}

    def load_catalog(self) -> bool:
        if self._loaded:
            return True

        if not self.excel_path.exists():
            logger.warning(f"[MultivendeLoader] File not found: {self.excel_path}")
            return False

        try:
            logger.info(f"[MultivendeLoader] Loading catalog matrix from {self.excel_path.name}...")
            df = pd.read_excel(self.excel_path)
            
            for _, row in df.iterrows():
                sku_hijo = str(row.get("SKU_HIJO", "")).strip() if pd.notna(row.get("SKU_HIJO")) else ""
                sku_padre = str(row.get("SKU_PADRE", "")).strip() if pd.notna(row.get("SKU_PADRE")) else ""
                nombre = str(row.get("NOMBRE_PRODUCTO", "")).strip() if pd.notna(row.get("NOMBRE_PRODUCTO")) else ""
                marca = str(row.get("MARCA", "")).strip() if pd.notna(row.get("MARCA")) else "Nicopoly"
                
                sku_master = sku_hijo if sku_hijo else sku_padre
                if not sku_master:
                    continue

                def parse_price_val(val):
                    if pd.isna(val):
                        return 0.0
                    try:
                        return float(val)
                    except Exception:
                        return 0.0

                item_info = {
                    "sku_master": sku_master,
                    "sku_hijo": sku_hijo,
                    "sku_padre": sku_padre,
                    "product_name": nombre,
                    "brand": marca,
                    "prices": {
                        "paris": parse_price_val(row.get("PARIS_FULL_PRECIO_VENTA_CLP")),
                        "mercado libre": parse_price_val(row.get("PRECIOS_MERCADO_LIBRE_PRECIO_VENTA_CLP")),
                        "ripley": parse_price_val(row.get("PRECIO_RIPLEY_PRECIO_VENTA_CLP")),
                        "falabella": parse_price_val(row.get("PRECIOS_FALABELLA_PRECIO_VENTA_CLP"))
                    },
                    "offers": {
                        "mercado libre": parse_price_val(row.get("PRECIOS_MERCADO_LIBRE_PRICING_PRICE_WITH_DISCOUNT_CLP")),
                        "ripley": parse_price_val(row.get("PRECIO_RIPLEY_PRICING_PRICE_WITH_DISCOUNT_CLP")),
                        "falabella": parse_price_val(row.get("PRECIOS_FALABELLA_PRICING_PRICE_WITH_DISCOUNT_CLP")),
                        "paris": parse_price_val(row.get("PARIS_FULL_PRICING_PRICE_WITH_DISCOUNT_CLP"))
                    },
                    "stock": int(row.get("CANTIDAD_BODEGA_ONLINE", -1)) if pd.notna(row.get("CANTIDAD_BODEGA_ONLINE")) else -1
                }
                
                def update_index(index_dict, key, new_item, allow_sku=False):
                    if not key:
                        return
                    # Ignore single generic words (e.g. "strapless", "top", "casual") unless it's an explicit SKU
                    if len(key.split()) < 2:
                        if not (allow_sku or re.match(r"^n\d+", key)):
                            return
                    existing = index_dict.get(key)
                    if existing:
                        # Prefer items with stock > 0 if there are duplicates
                        if new_item["stock"] > 0 and existing["stock"] <= 0:
                            index_dict[key] = new_item
                    else:
                        index_dict[key] = new_item

                update_index(self._sku_master_map, sku_master.lower(), item_info, allow_sku=True)

                # 1. Mercado Libre Index
                meli_familia = str(row.get("CODIGO_MERCADO_LIBRE_FAMILIA", "")).strip() if pd.notna(row.get("CODIGO_MERCADO_LIBRE_FAMILIA")) else ""
                meli_modelo = str(row.get("CODIGO_MERCADO_LIBRE_MODELO_MELI", "")).strip() if pd.notna(row.get("CODIGO_MERCADO_LIBRE_MODELO_MELI")) else ""
                update_index(self._marketplace_indexes["mercado libre"], self._normalize(meli_familia), item_info)
                update_index(self._marketplace_indexes["mercado libre"], self._normalize(meli_modelo), item_info)

                # 2. Paris Index
                paris_desc = str(row.get("CODIGO_PARIS_DESCRIPCION_CORTA", "")).strip() if pd.notna(row.get("CODIGO_PARIS_DESCRIPCION_CORTA")) else ""
                paris_titulo = str(row.get("CODIGO_PARIS_TITULO_DE_LA_PUBLICACION", "")).strip() if pd.notna(row.get("CODIGO_PARIS_TITULO_DE_LA_PUBLICACION")) else ""
                update_index(self._marketplace_indexes["paris"], self._normalize(paris_desc), item_info)
                update_index(self._marketplace_indexes["paris"], self._normalize(paris_titulo), item_info)

                # 3. Falabella Index
                fala_tipo = str(row.get("CODIGO_FALABELLA_PRODUCTO_TIPO_DE_PRENDA_PARRTE_SUPERIOR", "")).strip() if pd.notna(row.get("CODIGO_FALABELLA_PRODUCTO_TIPO_DE_PRENDA_PARRTE_SUPERIOR")) else ""
                fala_barras = str(row.get("CODIGO_FALABELLA_VERSIONES_CODIGO_DE_BARRAS_VERSION", "")).strip() if pd.notna(row.get("CODIGO_FALABELLA_VERSIONES_CODIGO_DE_BARRAS_VERSION")) else ""
                update_index(self._marketplace_indexes["falabella"], self._normalize(fala_barras), item_info)

                # 4. Ripley Index
                ripley_desc = str(row.get("CODIGO_RIPLEY_DESCRIPCION_RIPLEY", "")).strip() if pd.notna(row.get("CODIGO_RIPLEY_DESCRIPCION_RIPLEY")) else ""
                update_index(self._marketplace_indexes["ripley"], self._normalize(ripley_desc), item_info)

                # General SKU/Barcode & Name Index for fallback
                if nombre:
                    norm_nombre = self._normalize(nombre)
                    clean_nombre = self._clean_brand(norm_nombre)
                    for mkt in self._marketplace_indexes:
                        if norm_nombre not in self._marketplace_indexes[mkt]:
                            self._marketplace_indexes[mkt][norm_nombre] = item_info
                        if clean_nombre and clean_nombre not in self._marketplace_indexes[mkt]:
                            self._marketplace_indexes[mkt][clean_nombre] = item_info

                if sku_master:
                    norm_sku = self._normalize(sku_master)
                    for mkt in self._marketplace_indexes:
                        if norm_sku not in self._marketplace_indexes[mkt]:
                            self._marketplace_indexes[mkt][norm_sku] = item_info

            self._loaded = True
            logger.info(f"[MultivendeLoader] Successfully indexed {len(self._sku_master_map)} master SKUs.")
            return True
        except Exception as e:
            logger.error(f"[MultivendeLoader] Failed to load catalog matrix: {e}")
            return False

    def lookup_sku(self, marketplace: str, text_or_id: str) -> dict | None:
        if not self._loaded:
            self.load_catalog()

        if not text_or_id:
            return None

        mkt_key = marketplace.lower().strip()
        index = self._marketplace_indexes.get(mkt_key, {})
        norm = self._normalize(text_or_id)
        clean_norm = self._clean_brand(norm)

        # Direct Hash Match
        if norm in index:
            return index[norm]
        if clean_norm and clean_norm in index:
            return index[clean_norm]

        # Extract embedded SKU patterns (e.g. N05155BL, MLC1584753643, MK69BO6ZBP, MPM10002646321)
        sku_match = re.search(r"\b(N\d{4,6}[A-Z0-9\-]*)\b", text_or_id, re.IGNORECASE)
        if sku_match:
            sku_found = sku_match.group(1).lower()
            if sku_found in self._sku_master_map:
                return self._sku_master_map[sku_found]

            # Variant fallback: match base model SKU prefix (e.g. N06207BM -> N06207)
            base_prefix_match = re.match(r"(n\d{4,5})", sku_found)
            if base_prefix_match:
                prefix = base_prefix_match.group(1)
                for k, v in self._sku_master_map.items():
                    if k.startswith(prefix):
                        return v

        # Clean token-based title match (Bag of Words without brand noise)
        clean_norm_tokens = set(clean_norm.split()) if clean_norm else set()
        norm_tokens = set(norm.split())
        has_brand_token = any(b in norm_tokens for b in ["nicopoly", "nicopolo", "nico"])
        
        for key, item in index.items():
            key_tokens = set(key.split())
            clean_key_tokens = set(self._clean_brand(key).split())
            if (has_brand_token and len(key_tokens) >= 2 and key_tokens.issubset(norm_tokens)) or \
               (len(key_tokens) >= 3 and key_tokens.issubset(norm_tokens)) or \
               (len(clean_key_tokens) >= 2 and clean_key_tokens == clean_norm_tokens) or \
               (len(clean_key_tokens) >= 2 and clean_key_tokens.issubset(clean_norm_tokens)) or \
               (len(clean_norm_tokens) >= 2 and clean_norm_tokens.issubset(clean_key_tokens)):
                return item
                
        # Substring fallback
        for key, item in index.items():
            clean_key = self._clean_brand(key)
            if (has_brand_token and len(norm) >= 8 and (key in norm or norm in key)) or \
               (len(key) >= 8 and len(norm) >= 12 and key in norm) or \
               (len(clean_key) >= 8 and len(clean_norm) >= 8 and (clean_key in clean_norm or clean_norm in clean_key)):
                return item

        return None

    def _clean_brand(self, text: str) -> str:
        if not text:
            return ""
        clean = re.sub(r"\b(nicopoly|nicopolo|nico poly|nico)\b", "", text.lower())
        return " ".join(clean.split())

    def _normalize(self, text: str) -> str:
        if not text:
            return ""
        clean = re.sub(r"[^\w\s]", " ", str(text).lower())
        return " ".join(clean.split())


_loader_instance = MultivendeLoader()

def get_multivende_loader() -> MultivendeLoader:
    if not _loader_instance._loaded:
        _loader_instance.load_catalog()
    return _loader_instance
