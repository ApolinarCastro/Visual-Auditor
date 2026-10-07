# -*- coding: utf-8 -*-
"""
Test Ripley scraper with session harvesting (non-headless).
A visible browser window WILL open -- that is intentional.
"""
import asyncio
import sys
import logging
import io

# Fix Windows encoding
# sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    stream=sys.stdout
)

from app.scrapers.ripley_scraper import RipleyScraper

async def main():
    print("=== Testing Ripley Session Harvesting ===")
    print("A browser window WILL open -- this is expected.")

    scraper = RipleyScraper()
    await scraper.start()

    try:
        test_url = (
            "https://simple.ripley.cl/search/Nicopoly"
            "?facet%3DTipo%20de%20Prenda=Jeans&sort=relevance_desc&page=1"
        )

        print(f"\nTesting get_total_count for Jeans...")
        count = await scraper.get_total_count(test_url)
        print(f"[OK] Total count: {count}")

        if count > 0:
            print(f"\nTesting scrape_top_240 for Jeans...")
            products = await scraper.scrape_top_240(test_url)
            print(f"[OK] Scraped {len(products)} products")

            nicopoly = [p for p in products if "nicopoly" in p.get("vendor", "").lower()]
            print(f"[OK] Nicopoly products: {len(nicopoly)}")

            for p in products[:5]:
                print(f"  [{p['position_absolute']}] {p['vendor']} -- {p['title'][:50]}")
        else:
            print("[WARN] Count returned 0. Check debug_screenshots/ripley_count_debug.png")
            print("       Also dumping visible page text:")
            try:
                text = await scraper.page.inner_text("body")
                print(text[:1000])
            except:
                pass

    finally:
        await scraper.stop()
        print("\n=== Test complete ===")

if __name__ == '__main__':
    asyncio.run(main())
