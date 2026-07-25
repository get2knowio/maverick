"""Directory-scoped defaults for the integration suite.

Two things every test under ``tests/integration/`` gets automatically:

1. **The ``integration`` marker.** This used to be a module-level
   ``pytestmark = pytest.mark.integration`` — which does nothing in a
   ``conftest.py``: pytest only honours ``pytestmark`` in test *modules*,
   so only the four files that happened to declare it themselves were ever
   marked, and ``-m integration`` silently missed the other thirteen.

2. **A generous default timeout.** These tests shell out to real ``jj``,
   ``bd``, and ``git``, so their wall-clock is dominated by subprocess
   scheduling. Under ``-n auto`` they compete with every other worker and
   routinely take several times their serial runtime — the global 30s
   default in ``pyproject.toml`` (right for pure-Python unit tests) left
   too little headroom and produced intermittent CI failures that passed
   on re-run and in isolation (issue #163).

Both are applied only where a test hasn't already said otherwise, so an
explicit ``@pytest.mark.timeout(...)`` still wins.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_INTEGRATION_DIR = Path(__file__).parent

#: Default per-test timeout (seconds) for the integration suite.
#:
#: Sized from measurement, not guesswork: the slowest offender in #163
#: (``test_scenario_2_rollback_on_gate_failure``) runs ~20s serially on an
#: idle 8-core box, so it needed only a ~1.5x contention slowdown to breach
#: a 30s budget. 120s absorbs a ~6x slowdown while still failing a
#: genuinely hung test in bounded time. Tests that legitimately need longer
#: keep their own explicit marker.
INTEGRATION_TIMEOUT_SECONDS = 120


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply the ``integration`` marker and default timeout to this suite.

    A ``conftest.py`` hook is invoked for the whole session, not just its
    own subtree, so items are filtered to this directory explicitly.
    """
    for item in items:
        item_path = getattr(item, "path", None)
        # Compare paths rather than substring-matching the nodeid, so a
        # checkout living under a directory named "integration" doesn't
        # sweep the unit suite in too.
        if item_path is None or not item_path.is_relative_to(_INTEGRATION_DIR):
            continue

        item.add_marker(pytest.mark.integration)

        # Explicit per-test timeouts win — several tests in this suite
        # already carry 60/90/150s overrides.
        if item.get_closest_marker("timeout") is None:
            item.add_marker(pytest.mark.timeout(INTEGRATION_TIMEOUT_SECONDS))
