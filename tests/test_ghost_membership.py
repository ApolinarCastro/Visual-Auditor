"""Ghost CATEGORY_UNKNOWN memberships must not survive next to a real edge."""
import sqlite3
from app.mri_autonomous.recovery_runner import cleanup_ghost_unknown_memberships


def _db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE mri_categories (category_id TEXT PRIMARY KEY, category_name TEXT)")
    conn.execute("CREATE TABLE mri_publication_categories (publication_id TEXT, category_id TEXT)")
    return conn


def test_ghost_unknown_removed_only_when_real_category_exists():
    conn = _db()
    conn.execute("INSERT INTO mri_categories VALUES ('u','CATEGORY_UNKNOWN')")
    conn.execute("INSERT INTO mri_categories VALUES ('r','Blusas y poleras')")
    conn.execute("INSERT INTO mri_publication_categories VALUES ('p1','u')")
    conn.execute("INSERT INTO mri_publication_categories VALUES ('p1','r')")
    conn.execute("INSERT INTO mri_publication_categories VALUES ('p2','u')")
    removed = cleanup_ghost_unknown_memberships(conn)
    rows = set(conn.execute("SELECT publication_id, category_id FROM mri_publication_categories"))
    assert removed == 1
    assert ("p1", "u") not in rows and ("p1", "r") in rows
    assert ("p2", "u") in rows


def test_anchor_script_accepts_data_href():
    from app.mri_autonomous.ripley_discovery import _anchor_script
    js = _anchor_script()
    assert "data-href" in js and "data-url" in js and "button[onclick]" in js
