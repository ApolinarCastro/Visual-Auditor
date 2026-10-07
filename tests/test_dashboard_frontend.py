import pytest
import subprocess
import time
import os
import requests
from playwright.sync_api import sync_playwright


def _basic_auth():
    return (os.environ.get("DASHBOARD_USER", "admin"), os.environ.get("DASHBOARD_PASS", ""))


def _http_credentials():
    return {"username": os.environ.get("DASHBOARD_USER", "admin"), "password": os.environ.get("DASHBOARD_PASS", "")}


LIVE_GATE = os.environ.get("VA_LIVE_DASHBOARD_TESTS") == "1"

@pytest.fixture(scope="module")
def test_server():
    if not LIVE_GATE:
        pytest.skip("live dashboard E2E disabled; set VA_LIVE_DASHBOARD_TESTS=1 and DASHBOARD_USER/DASHBOARD_PASS to run")
    # Start the server as a background process
    proc = subprocess.Popen(["python", "run.py", "dashboard"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for the server to be healthy
    url = "http://127.0.0.1:8000"
    started = False
    for _ in range(15):
        try:
            res = requests.get(f"{url}/api/health", auth=_basic_auth())
            if res.status_code == 200:
                started = True
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
        
    if not started:
        proc.terminate()
        pytest.fail("Server did not start in time")
        
    yield url
    
    proc.terminate()
    proc.wait()

def test_dashboard_search_filter(test_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(http_credentials=_http_credentials())
        page = context.new_page()
        
        page.goto(test_server)
        page.wait_for_timeout(500)
        page.evaluate("switchGlobalTab('visibilidad')")
        page.wait_for_selector("#audit-tbody tr")
        
        initial_rows = page.locator("#audit-tbody tr").count()
        assert initial_rows > 0, "No data loaded initially"
        
        page.fill("#search", "nonexistentcategory123")
        page.wait_for_timeout(500)
        
        filtered_rows = page.locator("#audit-tbody tr").count()
        text = page.locator("#audit-tbody").inner_text()
        assert filtered_rows == 0 or (filtered_rows == 1 and "Sin datos" in text), f"Filter did not hide rows, still found {filtered_rows}"
        
        browser.close()

def test_dashboard_top30_sorting(test_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(http_credentials=_http_credentials())
        page = context.new_page()
        
        page.goto(test_server)
        page.wait_for_timeout(500)
        page.evaluate("switchGlobalTab('visibilidad')")
        page.wait_for_selector("#audit-tbody tr")
        
        header = page.locator("th:has-text('TOP30')").first
        
        # Click header to sort
        header.click()
        page.wait_for_timeout(500)
        
        # Extract values
        rows = page.locator("#audit-tbody tr").all()
        top30_values = []
        for row in rows:
            text = row.locator("td:nth-child(5)").inner_text()
            try:
                top30_values.append(int(text))
            except ValueError:
                pass
                
        # Click again to reverse
        header.click()
        page.wait_for_timeout(500)
        
        rows_rev = page.locator("#audit-tbody tr").all()
        top30_values_rev = []
        for row in rows_rev:
            text = row.locator("td:nth-child(5)").inner_text()
            try:
                top30_values_rev.append(int(text))
            except ValueError:
                pass
                
        assert top30_values != top30_values_rev, "Sorting did not change row order"
        
        browser.close()
