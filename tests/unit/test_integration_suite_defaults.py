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


class TestIntegrationMarker:
    def test_applied_to_files_that_do_not_declare_it(self) -> None:
        """The regression that made ``-m integration`` under-collect.

        ``test_json_verbs_scenario.py`` carries no ``pytestmark`` of its
        own, so under the old conftest it was collected without the
        marker.
        """
        target = str(_INTEGRATION_DIR / "cli" / "test_json_verbs_scenario.py")
        marks = _collect_marks(target)

        assert marks, "collected nothing — check the target path"
        assert all(m["integration"] for m in marks.values())

    def test_every_integration_test_is_marked(self) -> None:
        """`-m integration` must select the whole directory, not a subset."""
        all_marks = _collect_marks(str(_INTEGRATION_DIR))
        unmarked = [nodeid for nodeid, m in all_marks.items() if not m["integration"]]

        assert not unmarked, (
            f"{len(unmarked)} integration tests missing the marker: {unmarked[:5]}"
        )

    def test_unit_tests_are_not_swept_in(self) -> None:
        """The conftest hook sees every item in the session — it must filter."""
        target = str(_REPO_ROOT / "tests" / "unit" / "test_workflow_errors.py")
        marks = _collect_marks(target)

        assert marks
        assert not any(m["integration"] for m in marks.values())


class TestIntegrationTimeoutDefault:
    def test_default_applied_to_the_flaky_offenders(self) -> None:
        """The three tests from #163 get real headroom, not the global 30s."""
        marks = _collect_marks(
            str(_INTEGRATION_DIR / "workflows" / "test_reconcile_jj.py"),
            str(_INTEGRATION_DIR / "test_assumption_ledger_flow.py"),
        )
        offenders = [
            "test_scenario_2_rollback_on_gate_failure",
            "test_scenario_1_clean_retroactive_application",
            "test_record_commit_stamp_flow",
        ]

        for name in offenders:
            matching = [m for nodeid, m in marks.items() if nodeid.endswith(f"::{name}")]
            assert matching, f"{name} was not collected"
            assert matching[0]["timeout"] == INTEGRATION_TIMEOUT_SECONDS

    def test_explicit_per_test_override_still_wins(self) -> None:
        """A test that asked for a longer budget keeps it."""
        marks = _collect_marks(str(_INTEGRATION_DIR / "test_assumption_ledger_flow.py"))
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
        target = str(_REPO_ROOT / "tests" / "unit" / "test_workflow_errors.py")
        marks = _collect_marks(target)

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
