"""Session challenge detection and recovery are evidence-driven."""
import asyncio
from app.mri_dashboard.session_supervisor import detect_challenge


class FakePage:
    def __init__(self, url, body):
        self.url = url
        self._body = body
    async def inner_text(self, selector, timeout=None):
        return self._body


def test_detects_human_challenge():
    page = FakePage("https://simple.ripley.cl/x",
                    "Verifica que eres un ser humano. Cloudflare Turnstile")
    assert asyncio.run(detect_challenge(page)) is not None


def test_normal_page_has_no_challenge():
    page = FakePage("https://simple.ripley.cl/moda", "Chaqueta mujer NICOPOLY")
    assert asyncio.run(detect_challenge(page)) is None
