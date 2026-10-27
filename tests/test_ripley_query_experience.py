"""Query-experience log: learns, does not preseed categories."""
import uuid
from pathlib import Path

from app.mri_dashboard.ripley_query_experience import (
    read_query_experience, record_query, successful_query_shapes)


def _aux():
    p = Path("evidence_local_validation/query_experience") / uuid.uuid4().hex[:8]
    p.mkdir(parents=True, exist_ok=True)
    return p


def test_records_success_and_failure_without_category_list():
    aux = _aux()
    record_query(aux, run_id="r1", marketplace="Ripley",
                 url="https://simple.ripley.cl/moda-mujer/tops-y-chaquetas/abrigos?brand=NICOPOLY",
                 category="Abrigos", products=49, state="FOUND",
                 stop_reason="EXHAUSTION")
    record_query(aux, run_id="r1", marketplace="Ripley",
                 url="https://simple.ripley.cl/x?page={page}",
                 category="Kimonos", products=0, state="FOUND",
                 stop_reason="EXHAUSTION")
    rows = read_query_experience(aux, "r1")
    assert len(rows) == 2
    assert rows[0]["products"] == 49
    shapes = successful_query_shapes(aux)
    assert "Abrigos" in shapes
    assert "Kimonos" not in shapes


def test_log_is_run_scoped_and_empty_safe():
    aux = _aux()
    assert read_query_experience(aux) == []
    record_query(aux, run_id="a", marketplace="Ripley", url="u",
                 category="c", products=1, state="FOUND")
    assert len(read_query_experience(aux, "a")) == 1
    assert read_query_experience(aux, "b") == []
