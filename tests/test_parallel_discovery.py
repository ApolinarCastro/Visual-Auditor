"""ALL_PARALLEL coordinates isolated children; sequential path remains intact."""
import asyncio
import app.mri_dashboard.mri_runner as MR


def test_parallel_discovery_isolates_run_ids_and_aggregates(monkeypatch):
    class FakeChild:
        def __init__(self):
            self.results = []
            self.state = {"status_message": "FOUND"}

        async def run_discovery(self, marketplace, max_pages=1, run_id=None,
                                limit=None, full_audit=True):
            self.results = [{"marketplace": marketplace, "observed_sku": run_id}]
            self.state["status_message"] = "FOUND"
            self.state["marketplace"] = marketplace

    parent = MR.MRIOrchestrator()
    monkeypatch.setattr(MR, "MRIOrchestrator", FakeChild)
    asyncio.run(parent.run_parallel_discovery(
        "run_parallel_test", ["Mercado Libre", "Paris"], max_pages=1))
    assert len(parent.results) == 2
    assert len(set(parent.state["child_run_ids"].values())) == 2
    assert parent.state["marketplace_states"] == {
        "Mercado Libre": "FOUND", "Paris": "FOUND"}
    assert parent.state["execution_strategy"] == "ALL_PARALLEL"
