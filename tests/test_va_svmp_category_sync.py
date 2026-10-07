import pytest
from pathlib import Path
from app.loaders.excel_loader import ExcelLoader
from app.auditor.audit_runner import AuditRunner

def test_excel_loader_loads_urls_and_new_categories():
    """Verify ExcelLoader loads tasks with both category names and valid URLs from SVMP.xlsx."""
    loader = ExcelLoader()
    tasks = loader.load_tasks()
    
    assert len(tasks) > 0, "No tasks loaded from Excel"
    
    # Check that new categories exist
    new_expected = {
        "Falabella": ["Poleras mujer", "Vestidos y enteritos", "Faldas", "Shorts"],
        "Paris": ["Fiesta"],
        "Ripley": ["Calzas", "Accesorios y complementos"]
    }
    
    tasks_by_mkt = {}
    for t in tasks:
        tasks_by_mkt.setdefault(t.marketplace, {})[t.category_marketplace] = t
        
    for mkt, cats in new_expected.items():
        assert mkt in tasks_by_mkt, f"Marketplace {mkt} missing in loaded tasks"
        for cat in cats:
            assert cat in tasks_by_mkt[mkt], f"New category '{cat}' missing in loaded tasks for {mkt}"
            task = tasks_by_mkt[mkt][cat]
            # Red requirement 1: task must have url_base loaded from Excel hyperlink
            assert task.url_base is not None, f"Task '{cat}' in {mkt} has url_base=None (hyperlink not loaded)"
            assert task.url_base.startswith("http"), f"Task '{cat}' in {mkt} has invalid url_base: {task.url_base}"
            # Red requirement 2: task must have url_nicopoly loaded from Excel hyperlink
            assert task.url_nicopoly is not None, f"Task '{cat}' in {mkt} has url_nicopoly=None"
            assert task.url_nicopoly.startswith("http"), f"Task '{cat}' in {mkt} has invalid url_nicopoly: {task.url_nicopoly}"

def test_audit_runner_resolves_all_category_visibility_urls():
    """Verify AuditRunner can resolve visibility and census URLs for all loaded tasks including new categories."""
    loader = ExcelLoader()
    tasks = loader.load_tasks()
    runner = AuditRunner()
    
    for t in tasks:
        mkt = t.marketplace
        cat = t.category_marketplace
        rules = runner.rule_loader.get_rules_for_marketplace(mkt)
        rule_urls = rules.get("category_urls", {}) if rules else {}
        
        # Current baseline logic only uses rules["category_urls"]
        cat_visibility_url = t.url_base or rule_urls.get(f"{cat.upper()}_visibility")
        cat_census_url = t.url_nicopoly or rule_urls.get(f"{cat.upper()}_census")
        
        # Red requirement 3: Every loaded valid task must resolve to a valid visibility URL for dispatch
        assert cat_visibility_url is not None and cat_visibility_url.startswith("http"), (
            f"AuditRunner cannot resolve visibility URL for category '{cat}' in {mkt} — would be skipped!"
        )
