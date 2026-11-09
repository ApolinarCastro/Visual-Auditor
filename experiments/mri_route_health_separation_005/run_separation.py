"""MRI-005 isolated proof: a failing route must not block a healthy sibling route."""
import asyncio, json, os, sys

ROOT = r"C:\Users\ASUS Zenbook\Documents\Visibility Auditor"
SB = os.path.join(ROOT, "experiments", "mri_route_health_separation_005", "sandbox")
os.makedirs(SB, exist_ok=True)
sys.path.insert(0, os.path.join(ROOT, "_integration"))
os.environ["MRI_ENV"] = "TEST"
os.environ["MRI_AUX_DIR"] = SB
os.environ["MRI_ISOLATED_DB"] = os.path.join(SB, "visibility.db")

from app.mri_autonomous.storage_guard import StorageConfig
StorageConfig.set_test_mode(True, SB)
from app.mri_autonomous.experience_store import ExperienceStore
from app.mri_dashboard.verified_routes_audit import execute_verified_routes_audit

db = os.path.join(SB, "exp_route_health.db")
if os.path.exists(db):
    os.remove(db)
store = ExperienceStore(db_path=db)
BAD = "https://simple.ripley.cl/moda-mujer/tops-y-chaquetas/abrigos?brand=NICOPOLY"
GOOD = "https://simple.ripley.cl/moda-mujer/tops-y-chaquetas/blusas-y-poleras?brand=NICOPOLY"
for url in (BAD, GOOD):
    store.record_experience(marketplace="Ripley", brand="Nicopoly", knowledge_type="CATEGORY",
                            value=url, source_url=url, page_type="COMMERCIAL_FACET",
                            status="LAST_GOOD", is_success=True, evidence_reference="seed")

calls = {"bad": 0, "good": 0}

async def acquire(route):
    if "abrigos" in route["url"]:
        calls["bad"] += 1
        return {"state": "SOURCE_BLOCKED", "publications": [], "reason": "FAKE_BLOCK",
                "failure_class": "SOURCE_FAILURE", "scraper_started": True}
    calls["good"] += 1
    return {"state": "FOUND", "reason": "FAKE_OK", "scraper_started": True,
            "publications": [{"sku": "SKU-GOOD", "title": "Blusa", "url": route["url"],
                              "position_absolute": 1}]}

runs = []
for i in range(1, 5):
    r = asyncio.run(execute_verified_routes_audit(
        run_id=f"RUN_SEP_{i}", marketplace="Ripley", scope="TOP_N", limit=2,
        experience_store=store, acquisition_fn=acquire, persist_fn=lambda *a, **k: {}))
    routes = []
    for x in r["routes"]:
        routes.append({"url": x["url"], "state": x["state"],
                       "failure_class": x.get("failure_class"),
                       "scraper_started": x.get("scraper_started"),
                       "strategy": x.get("strategy_selected")})
    cap = store.get_experience_item("Ripley", "Nicopoly", "CAPABILITY", "ripley_headless_catalog_scraper")
    runs.append({"run": i, "routes_selected": r["routes_selected"], "routes": routes,
                 "capability_status": (cap or {}).get("status"),
                 "capability_successes": (cap or {}).get("success_count"),
                 "capability_failures": (cap or {}).get("failure_count"),
                 "bad_calls": calls["bad"], "good_calls": calls["good"]})

bad_state = store.get_experience_item("Ripley", "Nicopoly", "ROUTE_STATE", "exp_1")
out = {"runs": runs, "bad_route_state": bad_state, "acquisition_calls": calls}
print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
with open(os.path.join(ROOT, "experiments", "mri_route_health_separation_005",
                       "separation_result.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2, ensure_ascii=False, default=str)
