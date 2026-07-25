"""The integration suite's directory-scoped defaults actually apply (#163).

``tests/integration/conftest.py`` previously used a module-level
``pytestmark``, which pytest ignores in a ``conftest.py`` — so the
``integration`` marker silently covered only the handful of files that
declared it themselves, and nothing supplied the longer timeout those
real-subprocess tests need. Both failures were invisible: the suite
still passed, just with the wrong marks and too little headroom.

These tests run pytest in-process against the real integration tree via
``--collect-only`` (no integration test is executed) and assert on the
marks that come out.

**Environment independence**: several integration modules call
``pytest.skip(..., allow_module_level=True)`` when ``bd``/``jj`` are
absent, which prevents collection entirely — CI installs ``jj`` but not
``bd``, so a different set of tests collects there than on a dev box.
Assertions below are therefore stated as invariants over *whatever*
collected, never over named tests, with targeted checks skipping
explicitly when their subject isn't present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.conftest import INTEGRATION_TIMEOUT_SECONDS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INTEGRATION_DIR = _REPO_ROOT / "tests" / "integration"


def _collect_marks(*targets: str) -> dict[str, dict[str, object]]:
    """Collect *targets* and return ``{nodeid: {"timeout": ..., "integration": ...}}``."""
    collected: dict[str, dict[str, object]] = {}

    class _Recorder:
        def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
            for item in items:
                timeout = item.get_closest_marker("timeout")
                collected[item.nodeid] = {
                    "timeout": timeout.args[0] if timeout else None,
                    "integration": item.get_closest_marker("integration") is not None,
                }

    pytest.main(
        ["--collect-only", "-q", "-p", "no:randomly", "--timeout=30", *targets],
        plugins=[_Recorder()],
    )
    return collected


@pytest.fixture(scope="module")
def integration_marks() -> dict[str, dict[str, object]]:
    """Marks for every integration test collectable in this environment."""
    marks = _collect_marks(str(_INTEGRATION_DIR))
    if not marks:  # pragma: no cover — would mean the whole suite is unreachable
        pytest.skip("no integration tests collected in this environment")
    return marks


class TestIntegrationMarker:
    def test_every_collected_integration_test_is_marked(
        self, integration_marks: dict[str, dict[str, object]]
    ) -> None:
        """`-m integration` must select the whole directory, not a subset.

        The original bug: only files carrying their own ``pytestmark``
        were marked, so `-m integration` under-collected everything else.
        """
        unmarked = [nodeid for nodeid, m in integration_marks.items() if not m["integration"]]

        assert not unmarked, (
            f"{len(unmarked)} integration tests missing the marker: {unmarked[:5]}"
        )

    def test_covers_files_that_do_not_declare_the_marker(
        self, integration_marks: dict[str, dict[str, object]]
    ) -> None:
        """Guards specifically against the old per-module-only behavior.

        ``cli/test_json_verbs_scenario.py`` has no ``pytestmark`` of its
        own and no tooling guard, so it collects everywhere — making it a
        reliable witness that the marker now comes from the conftest.
        """
        witness = [n for n in integration_marks if "test_json_verbs_scenario.py" in n]

        assert witness, "witness file was not collected — did it move?"
        assert all(integration_marks[n]["integration"] for n in witness)

    def test_unit_tests_are_not_swept_in(self) -> None:
        """The conftest hook sees every item in the session — it must filter."""
        marks = _collect_marks(str(_REPO_ROOT / "tests" / "unit" / "test_workflow_errors.py"))

        assert marks
        assert not any(m["integration"] for m in marks.values())


class TestIntegrationTimeoutDefault:
    def test_no_integration_test_falls_through_to_the_global_default(
        self, integration_marks: dict[str, dict[str, object]]
    ) -> None:
        """The invariant behind #163.

        Every integration test must carry an explicit budget; a ``None``
        here means it silently inherits the 30s global default sized for
        pure-Python unit tests.
        """
        unbudgeted = [nodeid for nodeid, m in integration_marks.items() if m["timeout"] is None]

        assert not unbudgeted, (
            f"{len(unbudgeted)} tests fall back to the 30s global: {unbudgeted[:5]}"
        )

    def test_default_is_actually_reachable(
        self, integration_marks: dict[str, dict[str, object]]
    ) -> None:
        """At least one test picks up the directory default (not all overridden)."""
        defaulted = [
            nodeid
            for nodeid, m in integration_marks.items()
            if m["timeout"] == INTEGRATION_TIMEOUT_SECONDS
        ]

        assert defaulted, "nothing received the conftest default — is the hook filtering wrongly?"

    def test_explicit_per_test_override_still_wins(self) -> None:
        """A test that asked for a longer budget keeps it.

        Subject lives in a module guarded on ``bd``, which CI does not
        install — skip rather than fail where it can't be collected.
        """
        marks = _collect_marks(str(_INTEGRATION_DIR / "test_assumption_ledger_flow.py"))
        if not marks:
            pytest.skip("test_assumption_ledger_flow.py not collectable (bd absent)")

        overridden = {
            "test_low_severity_blocks_frontier_until_bulk_waived": 150,
            "test_full_provenance_round_trip_report": 60,
        }
        for name, expected in overridden.items():
            matching = [m for nodeid, m in marks.items() if nodeid.endswith(f"::{name}")]
            assert matching, f"{name} was not collected"
            assert matching[0]["timeout"] == expected

    def test_unit_tests_keep_the_global_default(self) -> None:
        """The longer budget must not leak out of the integration tree."""
        marks = _collect_marks(str(_REPO_ROOT / "tests" / "unit" / "test_workflow_errors.py"))

        assert marks
        assert all(m["timeout"] is None for m in marks.values())

    def test_default_exceeds_the_slowest_measured_serial_runtime(self) -> None:
        """Guard the sizing rationale in the conftest docstring.

        The slowest offender measured ~20s serially; the default must
        leave room for several-fold contention slowdown, not a hair.
        """
        slowest_measured_serial = 20
        minimum_contention_headroom = slowest_measured_serial * 5
        assert minimum_contention_headroom <= INTEGRATION_TIMEOUT_SECONDS
