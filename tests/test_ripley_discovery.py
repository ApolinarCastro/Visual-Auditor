"""Live Ripley category discovery — the 14 daily-review categories are a
validation target, not a production hardcoded answer."""
import asyncio

from app.mri_autonomous.ripley_discovery import (
    category_urls_from_anchors, discover_live_categories)

PATHS = [
    "/moda-mujer/jeans-y-pantalones/jeans",
    "/moda-mujer/jeans-y-pantalones/pantalones",
    "/moda-mujer/jeans-y-pantalones/shorts",
    "/moda-mujer/tops-y-chaquetas/chaquetas-y-blazers",
    "/moda-mujer/tops-y-chaquetas/abrigos",
    "/moda-mujer/tops-y-chaquetas/blusas-y-poleras",
    "/moda-mujer/tops-y-chaquetas/kimonos",
    "/moda-mujer/tops-y-chaquetas/parkas",
    "/moda-mujer/tops-y-chaquetas/sweaters-y-chalecos",
    "/moda-mujer/vestidos-y-enteritos/enteritos",
    "/moda-mujer/vestidos-y-enteritos/faldas",
    "/moda-mujer/vestidos-y-enteritos/vestidos",
    "/moda-mujer/calzas",
    "/accesorios-y-complementos",
]


class _Page:
    def __init__(self, anchors):
        self.anchors = anchors

    async def evaluate(self, script):
        return self.anchors

    async def goto(self, *a, **k):
        return None

    async def wait_for_timeout(self, *a, **k):
        return None


def test_discovers_all_14_live_category_paths():
    anchors = [{"href": "https://simple.ripley.cl" + p, "text": p}
               for p in PATHS]
    urls = category_urls_from_anchors(anchors)
    assert len(urls) == 14
    for u in urls:
        assert "brand=NICOPOLY" in u
        assert "page={page}" in u
        assert u.format(page=2).endswith("page=2")


def test_product_and_non_category_links_are_excluded():
    anchors = [
        {"href": "https://simple.ripley.cl/producto-x-mpm10003569411", "text": "p"},
        {"href": "https://simple.ripley.cl/moda-mujer/calzas", "text": "Calzas"},
        {"href": "https://simple.ripley.cl/carrito", "text": "Carrito"},
    ]
    urls = category_urls_from_anchors(anchors)
    assert len(urls) == 1
    assert "calzas" in urls[0]


def test_async_discovery_from_live_page():
    anchors = [{"href": "https://simple.ripley.cl" + p, "text": p}
               for p in PATHS]
    urls = asyncio.run(discover_live_categories(_Page(anchors), "https://simple.ripley.cl/search/nicopoly"))
    assert len(urls) == 14


def test_discovery_restarts_browser_after_closed_context():
    class _Scraper:
        def __init__(self, page):
            self.page = page
            self.stops = 0
            self.starts = 0
            self.navs = 0

        async def _navigate_ripley(self, url):
            self.navs += 1
            return self.navs > 1  # first navigation fails (closed context)

        async def stop(self):
            self.stops += 1

        async def start(self):
            self.starts += 1

    class _P(_Page):
        pass

    page = _P([{"href": "https://simple.ripley.cl" + p, "text": p}
               for p in PATHS])
    scraper = _Scraper(page)
    urls = asyncio.run(discover_live_categories(
        page, "https://simple.ripley.cl/search/nicopoly",
        scraper=scraper, diagnostics=[]))
    assert scraper.stops == 1 and scraper.starts == 1
    assert len(urls) == 14
