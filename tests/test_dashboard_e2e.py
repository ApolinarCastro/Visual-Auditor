# -*- coding: utf-8 -*-
"""
E2E Dashboard Test Script
Uses Playwright to systematically verify dashboard endpoints and HTML rendering.
Supports continuous integration and prevents dashboard regressions.
"""
import asyncio
import logging
import sys
import io
import uvicorn
from playwright.async_api import async_playwright

# Force UTF-8 on Windows terminal output
# sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

async def run_e2e_tests():
    logger.info("=== Starting E2E Dashboard Regression Test ===")
    
    # Import the FastAPI application
    from app.dashboard.api import app
    from app.storage.sqlite_manager import SQLiteManager
    
    # Initialize DB schema and indexes first
    db = SQLiteManager()
    await db.init_db()
    
    # Configure and start Uvicorn server on a local test port
    port = 8888
    config = uvicorn.Config(
        app, 
        host="127.0.0.1", 
        port=port, 
        loop="asyncio", 
        log_level="warning"
    )
    server = uvicorn.Server(config)
    
    # Start the server as an asynchronous task
    server_task = asyncio.create_task(server.serve())
    
    # Allow uvicorn a moment to bind and launch
    await asyncio.sleep(2)
    
    try:
        # Launch Playwright to perform visual and functional tests
        async with async_playwright() as p:
            logger.info("Launching headless Chromium to test dashboard UI...")
            import os
            user = os.getenv("DASHBOARD_USER", "admin")
            password = os.getenv("DASHBOARD_PASS", "")
            if not password:
                logger.warning("[SKIP] DASHBOARD_PASS not configured; skipping live E2E.")
                return
            if not password:
                logger.warning("[SKIP] DASHBOARD_PASS not configured; skipping live E2E.")
                return
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                http_credentials={"username": user, "password": password}
            )
            page = await context.new_page()
            
            # Test 1: Load main dashboard page
            url = f"http://127.0.0.1:{port}/"
            logger.info(f"Navigating to {url}...")
            await page.goto(url)
            await page.wait_for_timeout(1000)
            
            title = await page.title()
            logger.info(f"[OK] Rendered title: '{title}'")
            assert "Visibility Auditor" in title, f"Unexpected title: {title}"
            
            # Test 2: Verify dashboard has key layout headers or containers
            content = await page.content()
            assert "container" in content.lower() or "dashboard" in content.lower(), "Dashboard UI container is missing"
            logger.info("[OK] Visual UI container verified successfully")
            
            # Test 3: Test API Health endpoint response
            logger.info("Verifying JSON API health endpoint...")
            await page.goto(f"http://127.0.0.1:{port}/api/health")
            health_json = await page.inner_text("body")
            logger.info(f"[OK] Health Response: {health_json[:200]}")
            assert "health" in health_json.lower(), "Health key missing from health endpoint"
            
            # Test 4: Test API SelectorStats endpoint
            logger.info("Verifying JSON API selectors endpoint...")
            await page.goto(f"http://127.0.0.1:{port}/api/selectors")
            selectors_json = await page.inner_text("body")
            assert "selectors" in selectors_json.lower(), "Selectors key missing from selectors endpoint"
            logger.info("[OK] Selectors API verified successfully")

            # Test 5: Verify GET /api/sessions
            logger.info("Verifying GET /api/sessions endpoint...")
            await page.goto(f"http://127.0.0.1:{port}/api/sessions")
            sessions_json = await page.inner_text("body")
            logger.info(f"[OK] Sessions Response: {sessions_json[:200]}")
            assert "ripley" in sessions_json.lower() and "mercadolibre" in sessions_json.lower(), "Ripley/ML session keys missing from sessions endpoint"

            # Test 6: Verify POST /api/sessions/upload validation safety (Expected 400)
            logger.info("Verifying POST /api/sessions/upload validation safety...")
            upload_bad = await page.evaluate(f"""async () => {{
                const r = await fetch('http://127.0.0.1:{port}/api/sessions/upload', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{marketplace: 'ripley', cookies: 'not-a-list'}})
                }});
                return {{status: r.status, data: await r.json()}};
            }}""")
            logger.info(f"[OK] Bad Upload Response: {upload_bad}")
            assert upload_bad["status"] == 400, f"Expected 400 for bad cookies payload, got {upload_bad['status']}"

            # Test 7: Verify POST /api/sessions/upload successful write (Expected 200)
            logger.info("Verifying POST /api/sessions/upload successful write...")
            upload_good = await page.evaluate(f"""async () => {{
                const r = await fetch('http://127.0.0.1:{port}/api/sessions/upload', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        marketplace: 'ripley',
                        cookies: [{{name: 'e2e_test_cookie', value: 'e2e_value', domain: '.ripley.cl'}}]
                    }})
                }});
                return {{status: r.status, data: await r.json()}};
            }}""")
            logger.info(f"[OK] Good Upload Response: {upload_good}")
            assert upload_good["status"] == 200, f"Expected 200 for good cookies payload, got {upload_good['status']}"
            assert upload_good["data"]["status"] == "success", f"Expected success status, got {upload_good['data']['status']}"

            # Clean up E2E cookie file changes by copying back the backup file
            import shutil
            import os
            from app.config.settings import BASE_DIR
            rip_path = BASE_DIR / "data" / "ripley_session.json"
            rip_bak = BASE_DIR / "data" / "ripley_session.json.bak"
            if os.path.exists(rip_bak):
                logger.info("Restoring original Ripley session file from backup to clean up E2E data...")
                shutil.copy2(rip_bak, rip_path)
                os.remove(rip_bak)

            await browser.close()

            
        logger.info("=== E2E Dashboard Testing Passed Successfully (Zero Regressions)! ===")
        
    except AssertionError as ae:
        logger.error(f"[FAIL] Assertion error during E2E verification: {ae}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"[FAIL] Unexpected error during E2E testing: {e}")
        sys.exit(1)
    finally:
        # Stop uvicorn server task cleanly
        logger.info("Stopping Uvicorn server task...")
        server.should_exit = True
        await server_task
        logger.info("Server stopped cleanly.")

if __name__ == "__main__":
    asyncio.run(run_e2e_tests())
