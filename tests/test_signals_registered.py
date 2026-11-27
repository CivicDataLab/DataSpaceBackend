"""Every signal module in api/signals/ must be loaded when Django starts (#326).

Root cause: `api/signals/collaborative_signals.py` (removes an unpublished
collaborative from search and refreshes the search cache) was never imported in
`api/signals/__init__.py`, so it never ran on any server. The library's own
signals only index published collaboratives; they never remove one that goes
back to draft, so unpublished collaboratives stayed in the public listing.
Tests did not notice because `test_search_cache_invalidation.py` imports the
module directly, which connects its handler for the whole test run.

Fix: import it in `api/signals/__init__.py`. These checks start Django in a new
process, so imports made by other test files cannot hide a missing one.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

STARTUP_CHECK = """
import json
import sys

import django

django.setup()

from django.db.models.signals import pre_save

from api.models import Collaborative

sync_receivers, async_receivers = pre_save._live_receivers(Collaborative)

print(json.dumps({
    "loaded": sorted(m for m in sys.modules if m.startswith("api.signals.")),
    "collaborative_pre_save": [
        getattr(receiver, "__name__", "") for receiver in sync_receivers + async_receivers
    ],
}))
"""


@pytest.fixture(scope="module")
def startup() -> dict:
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "tests.test_settings"}
    result = subprocess.run(
        [sys.executable, "-c", STARTUP_CHECK],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_every_signal_module_is_loaded_at_startup(startup: dict) -> None:
    modules = sorted(
        f"api.signals.{path.stem}"
        for path in (REPO_ROOT / "api" / "signals").glob("*.py")
        if path.stem != "__init__"
    )
    missing = [module for module in modules if module not in startup["loaded"]]
    assert not missing, f"never imported in api/signals/__init__.py: {missing}"


def test_collaborative_unpublish_handler_is_connected(startup: dict) -> None:
    assert "handle_collaborative_publication" in startup["collaborative_pre_save"]
