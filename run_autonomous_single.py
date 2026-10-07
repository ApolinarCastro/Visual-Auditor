import asyncio, json
from datetime import datetime
from pathlib import Path
from app.mri_autonomous.autonomous_pipeline import autonomous_discover_marketplace, materialize_discovered_products

async def main():
    mkt="Paris"
    brand="Nicopoly"
    print(f"Testing {mkt}")
    res = await autonomous_discover_marketplace(mkt, brand, max_categories=2, headless=True)
    print(json.dumps({k: v for k,v in res.items() if k not in ["products_by_category","products"]}, indent=2, ensure_ascii=False))
    print(f"products: {len(res['products'])}")
    for p in res['products'][:3]:
        print(p)
    mat = materialize_discovered_products(res, f"run_test_{datetime.now().strftime('%H%M%S')}")
    print(f"mat unique {mat['unique_publications']} edges {len(mat['edges'])}")

if __name__=="__main__":
    asyncio.run(main())
