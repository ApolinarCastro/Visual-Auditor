import os
import re
from pathlib import Path
from app.config.settings import RULES_DIR
import logging

logger = logging.getLogger(__name__)

class RuleLoader:
    def __init__(self, rules_dir=RULES_DIR):
        self.rules_dir = Path(rules_dir)

    def get_rules_for_marketplace(self, marketplace_name: str):
        # Find the file that matches the marketplace (more flexible order)
        pattern1 = f"*OPERACIONAL*{marketplace_name.upper()}*.txt"
        pattern2 = f"*{marketplace_name.upper()}*OPERACIONAL*.txt"
        files = list(self.rules_dir.glob(pattern1)) + list(self.rules_dir.glob(pattern2))
        
        if not files:
            logger.error(f"No rules file found for marketplace: {marketplace_name} using patterns {pattern1} or {pattern2}")
            return None
        
        file_path = files[0]
        logger.info(f"Using rules file: {file_path}")
        content = file_path.read_text(encoding='utf-8')
        
        rules = {
            "phase_1_url": self._extract_phase_1_url(content),
            "category_urls": self._extract_category_urls(content)
        }
        return rules

    def _extract_phase_1_url(self, content):
        # Allow multiple formats: "URL: http", "URL OFICIAL: http", etc.
        match = re.search(r"FASE 1.*?(?:URL|URL OFICIAL)[:\s]+[=\- \n]*\s*(https?://\S+)", content, re.DOTALL | re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_category_urls(self, content):
        urls = {}
        # Strategy: Find "FASE 2" and "FASE 3" sections
        p2_match = re.search(r"FASE 2(.*?)FASE 3", content, re.DOTALL | re.IGNORECASE)
        p3_match = re.search(r"FASE 3(.*?)CÁLCULO|FASE 3(.*?)FIN DOCUMENTO", content, re.DOTALL | re.IGNORECASE)
        
        if p2_match:
            p2_content = p2_match.group(1)
            # Match "2.x CATEGORY_NAME" followed by a URL
            blocks = re.split(r"(\d+\.\d+)", p2_content)
            for i in range(1, len(blocks), 2):
                header = blocks[i] + blocks[i+1]
                # Match the number, then the name (stopping at colon or http), then the URL
                name_match = re.search(r"(\d+\.\d+)\s+([^: \n]+(?: [^: \n]+)*)", header)
                url_match = re.search(r"(https?://\S+)", header)
                if name_match and url_match:
                    name = name_match.group(2).strip().upper()
                    urls[f"{name}_census"] = url_match.group(1)

        if p3_match:
            p3_content = p3_match.group(1) or p3_match.group(2)
            blocks = re.split(r"(\d+\.\d+)", p3_content)
            for i in range(1, len(blocks), 2):
                header = blocks[i] + blocks[i+1]
                name_match = re.search(r"(\d+\.\d+)\s+([^: \n]+(?: [^: \n]+)*)", header)
                url_match = re.search(r"(https?://\S+)", header)
                if name_match and url_match:
                    name = name_match.group(2).strip().upper()
                    urls[f"{name}_visibility"] = url_match.group(1)
                    
        return urls
