"""Where a bead's ``## Verification`` commands run, and why it differs
under isolation.

research.md R6 places `ac_check` in the bead's workspace on the grounds
that it "needs no toolchain". That holds for its `rg`/`grep` commands but
not for `cargo`/`make`: `.venv/`, `target/` and friends are gitignored, so
they never travel into a `jj workspace add` workspace. Running them there
fails for reasons that have nothing to do with the bead's code — which
costs a fix round on an agent asked to repair working code, then abandons
the bead.

So under isolation the workspace-side check runs the artifact-level subset
only, and `gate` picks the environment-level commands back up in the
checkout after fold-back, where the toolchain actually exists.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from burr.core import State

from maverick.workflows.fly_beads._plan_parsing import (
    ARTIFACT_LEVEL_VERIFICATION,
    ENVIRONMENT_LEVEL_VERIFICATION,
    SUPPORTED_VERIFICATION,
    verification_tool,
)
from maverick.workflows.fly_beads.actions import (
    _ac_check_impl,
    _gate_impl_isolated,
    _run_environment_verification,
)

_DESCRIPTION = """## Verification

- rg "fn handle" src/
- cargo test --lib
- make lint
- grep -q TODO src/lib.rs
"""


def _state(**overrides: Any) -> State:
    base: dict[str, Any] = {
        "current_bead": {"id": "bd-1", "description": _DESCRIPTION},
        "current_bead_id": "bd-1",
        "implementer_escalation_level": 0,
        "pending_assumptions": (),
        "isolated": False,
    }
    base.update(overrides)
    return State(base)


class _RecordingRunner:
    """Captures every command a check actually executes."""

    def __init__(self, *, returncode: int = 0) -> None:
        self.commands: list[str] = []
        self._returncode = returncode

    def __call__(self, *_args: Any, **_kwargs: Any) -> _RecordingRunner:
        return self

    async def run(self, argv: list[str]) -> Any:
        self.commands.append(argv[-1])

        class _Result:
            returncode = self._returncode

        return _Result()


class TestCommandClassification:
    def test_the_two_tiers_partition_the_supported_set(self) -> None:
        assert set(ARTIFACT_LEVEL_VERIFICATION).isdisjoint(ENVIRONMENT_LEVEL_VERIFICATION)
        assert set(SUPPORTED_VERIFICATION) == set(ARTIFACT_LEVEL_VERIFICATION) | set(
            ENVIRONMENT_LEVEL_VERIFICATION
        )

    def test_toolchain_commands_are_environment_level(self) -> None:
        assert verification_tool("cargo test --lib") in ENVIRONMENT_LEVEL_VERIFICATION
        assert verification_tool("make lint") in ENVIRONMENT_LEVEL_VERIFICATION

    def test_reading_commands_are_artifact_level(self) -> None:
        assert verification_tool('rg "fn handle" src/') in ARTIFACT_LEVEL_VERIFICATION
        assert verification_tool("grep -q TODO src/lib.rs") in ARTIFACT_LEVEL_VERIFICATION

    def test_blank_command_yields_no_tool(self) -> None:
        assert verification_tool("   ") == ""


class TestIsolatedAcCheckSkipsTheToolchain:
    @pytest.mark.asyncio
    async def test_isolated_runs_only_artifact_level_commands(self) -> None:
        runner = _RecordingRunner()
        with patch("maverick.runners.command.CommandRunner", runner):
            await _ac_check_impl(
                _state(isolated=True),
                squadron=AsyncMock(),
                events=AsyncMock(),
                cwd="/ws/bd-1",
                tools=ARTIFACT_LEVEL_VERIFICATION,
            )

        assert runner.commands == ['rg "fn handle" src/', "grep -q TODO src/lib.rs"]

    @pytest.mark.asyncio
    async def test_non_isolated_still_runs_every_supported_command(self) -> None:
        """FR-035: the default path is byte-identical to before 057."""
        runner = _RecordingRunner()
        with patch("maverick.runners.command.CommandRunner", runner):
            await _ac_check_impl(
                _state(),
                squadron=AsyncMock(),
                events=AsyncMock(),
                cwd="/checkout",
            )

        assert runner.commands == [
            'rg "fn handle" src/',
            "cargo test --lib",
            "make lint",
            "grep -q TODO src/lib.rs",
        ]

    @pytest.mark.asyncio
    async def test_a_failing_toolchain_command_cannot_fail_an_isolated_bead(self) -> None:
        """The regression this split exists to prevent: `make lint` exiting
        non-zero purely because the workspace has no `.venv` must not mark
        the bead's AC check failed."""
        runner = _RecordingRunner(returncode=1)
        with patch("maverick.runners.command.CommandRunner", runner):
            result, state = await _ac_check_impl(
                _state(
                    isolated=True,
                    current_bead={"id": "bd-1", "description": "## Verification\n\n- make lint\n"},
                ),
                squadron=AsyncMock(),
                events=AsyncMock(),
                cwd="/ws/bd-1",
                tools=ARTIFACT_LEVEL_VERIFICATION,
            )

        assert runner.commands == []  # never executed in the workspace at all
        assert result == {"passed": True}
        assert state["ac_passed"] is True


class TestIsolatedGatePicksThemBackUp:
    @pytest.mark.asyncio
    async def test_environment_commands_run_in_the_checkout(self) -> None:
        runner = _RecordingRunner()
        with patch("maverick.runners.command.CommandRunner", runner):
            summary = await _run_environment_verification(_state(), cwd="/checkout")

        assert runner.commands == ["cargo test --lib", "make lint"]
        assert summary == ""

    @pytest.mark.asyncio
    async def test_failure_joins_the_gate_summary_and_fails_the_gate(self) -> None:
        runner = _RecordingRunner(returncode=1)
        with (
            patch("maverick.runners.command.CommandRunner", runner),
            patch(
                "maverick.library.actions.validation.run_independent_gate",
                AsyncMock(return_value={"passed": True}),
            ),
        ):
            result, state = await _gate_impl_isolated(_state(isolated=True), cwd="/checkout")

        assert result == {"passed": False}
        assert state["gate_passed"] is False
        # Routes through the existing undo -> gate_fix -> fold_back loop.
        assert "cargo test --lib" in state["gate_failure_summary"]
        assert "make lint" in state["gate_failure_summary"]

    @pytest.mark.asyncio
    async def test_a_failing_gate_short_circuits_before_verification(self) -> None:
        """No point shelling out to the toolchain when format/lint/test
        already failed — and the summary must stay the gate's own."""
        runner = _RecordingRunner()
        with (
            patch("maverick.runners.command.CommandRunner", runner),
            patch(
                "maverick.library.actions.validation.run_independent_gate",
                AsyncMock(return_value={"passed": False, "summary": "lint failed"}),
            ),
        ):
            result, state = await _gate_impl_isolated(_state(isolated=True), cwd="/checkout")

        assert result == {"passed": False}
        assert state["gate_failure_summary"] == "lint failed"
        assert runner.commands == []

    @pytest.mark.asyncio
    async def test_all_green_clears_unverified_in_checkout(self) -> None:
        runner = _RecordingRunner()
        with (
            patch("maverick.runners.command.CommandRunner", runner),
            patch(
                "maverick.library.actions.validation.run_independent_gate",
                AsyncMock(return_value={"passed": True}),
            ),
        ):
            result, state = await _gate_impl_isolated(_state(isolated=True), cwd="/checkout")

        assert result == {"passed": True}
        assert state["gate_passed"] is True
        assert state["unverified_in_checkout"] is False

    @pytest.mark.asyncio
    async def test_a_bead_with_no_verification_section_runs_nothing(self) -> None:
        runner = _RecordingRunner()
        with patch("maverick.runners.command.CommandRunner", runner):
            summary = await _run_environment_verification(
                _state(current_bead={"id": "bd-1", "description": "no sections here"}),
                cwd="/checkout",
            )

        assert summary == ""
        assert runner.commands == []
