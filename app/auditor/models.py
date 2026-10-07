from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class AuditTask:
    marketplace: str
    category_marketplace: str
    category_nicopoly: str
    url_base: Optional[str] = None
    url_nicopoly: Optional[str] = None
    phase_1_total_nicopoly: Optional[int] = None
    phase_2_total_nicopoly_category: Optional[int] = None
    phase_3_results: List[dict] = field(default_factory=list)
    
    def __post_init__(self):
        # Normalize strings
        self.marketplace = self.marketplace.strip()
        self.category_marketplace = self.category_marketplace.strip()
        self.category_nicopoly = self.category_nicopoly.strip()
