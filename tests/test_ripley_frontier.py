import pytest
from app.mri_autonomous.category_discoverer import build_navigation_candidates

def test_red_1_marca_competidora():
    """RED-1: Una superficie como marcas-destacadas/bubba no debe expandirse como frontier para Nicopoly."""
    nodes = [
        {"href": "https://simple.ripley.cl/marcas-destacadas/bubba", "label": "Bubba", "container": "dom"},
        {"href": "https://simple.ripley.cl/marcas-destacadas/nicopoly", "label": "Nicopoly", "container": "dom"},
        {"href": "/marcas-destacadas/bubba", "label": "Bubba", "container": "menu_dialog"},
    ]
    hub_url = "https://simple.ripley.cl/search/nicopoly"
    brand = "Nicopoly"
    
    candidates = build_navigation_candidates(nodes, hub_url, brand)
    urls = [c["url"] for c in candidates]
    
    # Bubba should NOT be in candidates, because it's a competitor brand (not Nicopoly)
    # Nicopoly is also correctly pruned because classify_surface labels it as BRAND_SURFACE.
    assert "https://simple.ripley.cl/marcas-destacadas/bubba" not in urls, "Competitor brand was not pruned!"

def test_red_2_categoria_irrelevante():
    """RED-2: Superficies como sartenes, accesorios de baño, fútbol no deben expandir el frontier."""
    nodes = [
        {"href": "/hogar/sartenes", "label": "Sartenes", "container": "dom"},
        {"href": "/deportes/futbol", "label": "Fútbol", "container": "dom"},
        {"href": "/bano/accesorios", "label": "Accesorios de Baño", "container": "dom"},
        {"href": "/zapatos-y-zapatillas", "label": "Zapatos", "container": "dom"},
    ]
    hub_url = "https://simple.ripley.cl/search/nicopoly"
    brand = "Nicopoly"
    
    candidates = build_navigation_candidates(nodes, hub_url, brand)
    urls = [c["url"] for c in candidates]
    
    # Currently these might be classified as CATEGORY and returned.
    # The fix should prune irrelevant categories based on semantic signals.
    assert "https://simple.ripley.cl/hogar/sartenes" not in urls
    assert "https://simple.ripley.cl/deportes/futbol" not in urls

def test_red_4_bounded_fallback():
    """RED-4: Fallback no puede convertirse en FULL MARKETPLACE TRAVERSAL."""
    # This tests that if container=dom (fallback), we don't blindly accept everything.
    # We should only accept if there's evidence (e.g. brand in url or other evidence).
    nodes = [
        {"href": "/moda-mujer/jeans", "label": "Jeans", "container": "dom"},
        {"href": "/belleza/perfumeria", "label": "Perfumería", "container": "dom"},
    ]
    hub_url = "https://simple.ripley.cl/search/nicopoly"
    brand = "Nicopoly"
    
    candidates = build_navigation_candidates(nodes, hub_url, brand)
    urls = [c["url"] for c in candidates]
    
    # If container is "dom" and it's a generic category with no brand signal, it shouldn't be added to frontier.
    # Wait, how does it find the frontier if it doesn't add it? It relies on menu_dialog or brand signals.
    assert "https://simple.ripley.cl/belleza/perfumeria" not in urls

