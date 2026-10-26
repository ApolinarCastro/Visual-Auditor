import json
import os
import asyncio

try:
    from app.mri_autonomous.storage_guard import StorageConfig
    DEFAULT_CAT_PATH = StorageConfig.get_categories_json_path()
except Exception:
    DEFAULT_CAT_PATH = "data/mri_categories.json"

class CategoryManager:
    def __init__(self, data_path=None):
        self._explicit_path = (data_path is not None)
        if data_path is not None:
            self.data_path = str(data_path)
        else:
            try:
                from app.mri_autonomous.storage_guard import StorageConfig
                self.data_path = str(StorageConfig.get_categories_json_path())
            except Exception:
                self.data_path = str(DEFAULT_CAT_PATH)
        self.categories = self._load()

    def _load(self):
        if os.path.exists(self.data_path):
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self):
        try:
            from app.mri_autonomous.storage_guard import StorageConfig
            StorageConfig.ensure_writable(
                self.data_path,
                reason="Category catalog persistence",
                explicit=getattr(self, "_explicit_path", False),
            )
            StorageConfig.assert_write_allowed(self.data_path)
        except ImportError:
            pass
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(self.categories, f, indent=2, ensure_ascii=False)

    def register_category(self, marketplace, category_id, name, url, parent_id=None, source="OBSERVED", status="NOT_TESTED"):
        if marketplace not in self.categories:
            self.categories[marketplace] = {}
            
        import datetime
        now = datetime.datetime.now(datetime.UTC).isoformat()
        
        if category_id not in self.categories[marketplace]:
            self.categories[marketplace][category_id] = {
                "name": name,
                "url": url,
                "parent_id": parent_id,
                "source": source,
                "status": status,
                "first_seen": now,
                "last_seen": now
            }
        else:
            cat = self.categories[marketplace][category_id]
            cat["last_seen"] = now
            if status != "NOT_TESTED" and cat.get("status") == "NOT_TESTED":
                cat["status"] = status
                
        self._save()

    def get_categories(self, marketplace):
        return self.categories.get(marketplace, {})

category_manager = CategoryManager()
