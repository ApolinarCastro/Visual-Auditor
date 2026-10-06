import unittest
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.dashboard.api import app

class TestSecretNotRenderedInUI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.auth = (os.getenv("DASHBOARD_USER", "admin"), os.getenv("DASHBOARD_PASS"))
        if not self.auth[1]:
            self.skipTest("DASHBOARD_PASS not available in test environment")

    def test_api_sessions_does_not_expose_raw_cookies(self):
        """Verifies /api/sessions does NOT return raw cookie secrets or arrays."""
        resp = self.client.get("/api/sessions", auth=self.auth)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        
        # Check Ripley session response
        self.assertIn("ripley", data)
        rip = data["ripley"]
        self.assertNotIn("raw_cookies", rip, "CRITICAL: /api/sessions exposes raw_cookies in Ripley response")
        # Ensure no secret strings or cookie values leaked
        rip_str = json.dumps(rip)
        self.assertNotIn("cf_clearance", rip_str)

        # Check Mercado Libre session response
        self.assertIn("mercadolibre", data)
        ml = data["mercadolibre"]
        self.assertNotIn("raw_cookies", ml, "CRITICAL: /api/sessions exposes raw_cookies in Mercado Libre response")
        ml_str = json.dumps(ml)
        self.assertNotIn("ssid", ml_str)

if __name__ == "__main__":
    unittest.main()
