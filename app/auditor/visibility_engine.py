from app.auditor.nicopoly_matcher import is_nicopoly

class VisibilityEngine:
    def __init__(self, top_limits=[30, 60, 90, 120, 240]):
        self.top_limits = top_limits

    def calculate_cumulative_kpis(self, products: list[dict]) -> dict:
        results = {}
        
        # Mark products as nicopoly
        for p in products:
            p["is_nicopoly"] = is_nicopoly(p)
            
        # Calculate cumulative counts with title-based deduplication
        # to remove duplicate sponsored ads or identical listings
        for limit in self.top_limits:
            seen_titles = set()
            count = 0
            for p in products:
                if p["position_absolute"] > limit:
                    continue
                if p["is_nicopoly"]:
                    # Deduplicate by exact SKU if possible, fallback to normalized title
                    mkt_sku = str(p.get("marketplace_sku", "")).strip()
                    title_norm = " ".join(p.get("title", "").lower().split())
                    
                    dedup_key = mkt_sku if mkt_sku else title_norm
                    if dedup_key not in seen_titles:
                        seen_titles.add(dedup_key)
                        count += 1
            results[f"top_{limit}"] = count
            
        return results

    def calculate_percentages(self, kpis: dict, total_nicopoly: int) -> dict:
        percentages = {}
        if total_nicopoly == 0:
            return {f"pct_{k}": 0.0 for k in kpis.keys()}
            
        for key, value in kpis.items():
            denom = max(total_nicopoly, value)
            pct = (value / denom) * 100
            percentages[f"pct_{key.split('_')[1]}"] = min(round(pct, 2), 100.0)
            
        return percentages
