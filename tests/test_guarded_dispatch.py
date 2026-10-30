"""_guarded_run must forward kwargs and run_id to the runner."""
import asyncio
import app.mri_dashboard.mri_api as API


def test_guarded_run_forwards_kwargs_and_runner_run_id():
    seen = {}

    async def fn(run_id, marketplaces=None, max_pages=None, limit=None):
        seen.update(run_id=run_id, marketplaces=marketplaces,
                    max_pages=max_pages, limit=limit)

    asyncio.run(API._guarded_run(fn, "guard-run", "runner-run",
                                 marketplaces=None, max_pages=5, limit=None))
    assert seen == {"run_id": "runner-run", "marketplaces": None,
                    "max_pages": 5, "limit": None}
