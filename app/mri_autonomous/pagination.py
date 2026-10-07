"""Pagination discovery & traversal helpers (generic; no marketplace names).

Lesson transferred from MRI-AUTOCLAW-001 (failure layer: PAGINATION):
pagination links observed during discovery are EVIDENCE for traversal of the
same surface. They must never become taxonomy nodes, but they must not be
discarded either. This module converts observed page links + pager text into a
validated transition plan that the acquisition layer can follow.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

PAGER_RE = re.compile(r"p[aá]gina\s+(\d+)\s+de\s+(\d+)", re.IGNORECASE)
SORT_RE = re.compile(r"ordenar por\s*[\r\n:：]?\s*([^\r\n]{2,40})", re.IGNORECASE)
PAGE_PARAMS = ("page", "p", "offset")


def parse_pager_text(text: Optional[str]) -> Optional[Dict[str, int]]:
    """Parse 'Página X de Y' (accent-insensitive) from visible page text."""
    if not text:
        return None
    m = PAGER_RE.search(text)
    if not m:
        return None
    return {"current": int(m.group(1)), "total": int(m.group(2))}


def detect_sort_mode(text: Optional[str]) -> Optional[str]:
    """Extract the current sort mode label (e.g. 'Relevancia') from page text."""
    if not text:
        return None
    m = SORT_RE.search(text)
    if not m:
        return None
    val = m.group(1).strip().strip('"').strip()
    val = re.split(r"[|•·]", val)[0].strip()
    return val or None


def pagination_url(url: str, param: str, value: int) -> str:
    """Return url with the pagination param set to value (other params kept)."""
    p = urlparse(url)
    qs = parse_qs(p.query, keep_blank_values=True)
    qs[param] = [str(value)]
    q = urlencode({k: v[0] for k, v in qs.items()})
    return urlunparse((p.scheme, p.netloc, p.path, p.params, q, p.fragment))


def build_pagination_plan(hub_url: str, candidate_urls: List[str]) -> Optional[Dict]:
    """Build a transition plan from observed pagination candidates.

    Only candidates that share the hub's path are accepted (same surface
    different page). Returns None when no usable pagination signal exists.
    """
    if not hub_url or not candidate_urls:
        return None
    base_path = urlparse(hub_url).path
    pages: List[int] = []
    param: Optional[str] = None
    for u in candidate_urls:
        p = urlparse(u)
        if p.path != base_path:
            continue
        qs = parse_qs(p.query)
        for name in PAGE_PARAMS:
            if name in qs and qs[name][0].isdigit():
                if param is None:
                    param = name
                if name == param and int(qs[name][0]) >= 1:
                    pages.append(int(qs[name][0]))
    pages = sorted(set(pages))
    if not param or not pages:
        return None
    return {
        "param": param,
        "base_url": hub_url,
        "observed_pages": pages,
        "min_observed": min(pages),
        "max_observed": max(pages),
        "total_declared": None,
    }
