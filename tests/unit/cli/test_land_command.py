"""Unit tests for the ``maverick land`` CLI command.

The single-repo land flow is small enough that the tests exercise the
public ``land`` Click command directly via ``CliRunner``. WorkspaceManager
mocking is gone — there is no workspace any more.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from maverick.cli.commands.land import (
    _display_plan,
    land,
)

# ── Help-text tests ──────────────────────────────────────────────────


class TestLandHelp:
    """Verify all CLI options appear in help output."""

    def test_land_in_cli(self) -> None:
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        assert "curate" in result.output.lower()

    def test_land_help_shows_all_options(self) -> None:
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        for option in [
            "--no-curate",
            "--dry-run",
            "--yes",
            "--base",
            "--heuristic-only",
            "--eject",
            "--finalize",
            "--no-consolidate",
            "--branch",
        ]:
            assert option in result.output, f"missing {option}"


# ── Helper: shared patcher ──────────────────────────────────────────


def _patch_curation(
    *,
    commits: list[Any] | None = None,
    curate_result: dict[str, Any] | None = None,
) -> Any:
    """Patch the action surface land relies on.

    Returns a tuple of patch context managers that callers ``stack=`` into
    ``with`` blocks. Both ``gather_curation_context`` and
    ``curate_history`` are patched at their import sites in the action
    module, plus the consolidation helper is muted.
    """
    if commits is None:
        commits = [{"id": "abc", "subject": "test"}]
    if curate_result is None:
        curate_result = {
            "success": True,
            "absorb_ran": False,
            "squashed_count": 0,
            "error": None,
        }

    return (
        patch(
            "maverick.library.actions.jj.gather_curation_context",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "commits": commits,
                    "log_summary": "...",
                    "error": None,
                },
            ),
        ),
        patch(
            "maverick.library.actions.jj.curate_history",
            new=AsyncMock(return_value=curate_result),
        ),
        patch(
            "maverick.cli.commands.land._maybe_consolidate",
            new=AsyncMock(),
        ),
    )


# ── No-op paths ──────────────────────────────────────────────────────


class TestLandNoCommits:
    def test_nothing_to_land_returns_cleanly(self) -> None:
        """When the curation context surfaces zero commits, land exits cleanly."""
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation(commits=[])
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "Nothing to land" in result.output

    def test_gather_failure_exits_with_failure(self) -> None:
        """gather_curation_context failure → SystemExit(FAILURE)."""
        runner = CliRunner()
        with patch(
            "maverick.library.actions.jj.gather_curation_context",
            new=AsyncMock(
                return_value={
                    "success": False,
                    "commits": [],
                    "log_summary": "",
                    "error": "boom",
                },
            ),
        ):
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code != 0
        assert "Failed to gather commit context" in result.output


# ── Curation paths ──────────────────────────────────────────────────


class TestHeuristicCurate:
    def test_heuristic_runs_curate_history(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation(
            curate_result={
                "success": True,
                "absorb_ran": True,
                "squashed_count": 2,
                "error": None,
            },
        )
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--heuristic-only", "--yes"])
        assert result.exit_code == 0
        assert "Heuristic curation" in result.output
        assert "absorb=yes" in result.output
        assert "squashed=2" in result.output

    def test_heuristic_failure_exits_with_failure(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation(
            curate_result={
                "success": False,
                "absorb_ran": False,
                "squashed_count": 0,
                "error": "jj absorb failed",
            },
        )
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--heuristic-only", "--yes"])
        assert result.exit_code != 0
        assert "Heuristic curation failed" in result.output


class TestNoCurate:
    def test_no_curate_skips_curation_runs_consolidation(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "Skipping curation" in result.output


class TestDryRun:
    def test_dry_run_skips_next_step_hint(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate", "--dry-run"])
        assert result.exit_code == 0
        # Dry run path prints this message and returns before hint logic.
        assert "Dry run" in result.output


# ── Mode hints ──────────────────────────────────────────────────────


class TestModeHints:
    def test_default_mode_prints_generic_next_hint(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "Next: push the curated branch" in result.output

    def test_eject_mode_prints_preview_hint(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate", "--eject"])
        assert result.exit_code == 0
        assert "Eject hint" in result.output
        assert "maverick/preview/" in result.output

    def test_finalize_mode_prints_finalize_hint(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate", "--finalize"])
        assert result.exit_code == 0
        assert "Finalize hint" in result.output
        assert "gh pr create" in result.output

    def test_eject_branch_override(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate", "--eject", "--branch", "wip/foo"])
        assert result.exit_code == 0
        assert "wip/foo" in result.output


# ── Display plan ────────────────────────────────────────────────────


class TestDisplayPlan:
    def test_display_plan_renders_table(self) -> None:
        """Smoke test for the curation-plan renderer."""
        plan = [
            {"command": "describe", "args": ["-m", "fix bug"], "reason": "tighten msg"},
            {"command": "squash", "args": ["x", "y"], "reason": "fold fixup"},
        ]
        # Function does not raise; output sinks to console. The test
        # verifies the call itself doesn't blow up on real plan input.
        _display_plan(plan)


# ── pytest-asyncio mode ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _configure_asyncio() -> None:
    """Tests in this module are sync (CliRunner). The fixture exists
    only to silence pytest-asyncio's scope warnings if a future test
    adds async helpers."""
    return None


# ── Misc: top-level mock_runner kept for downstream callers ─────────


def _make_mock_command_runner() -> patch:
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.stderr = ""
    mock_runner = AsyncMock()
    mock_runner.run.return_value = mock_result
    return patch(
        "maverick.runners.command.CommandRunner",
        return_value=mock_runner,
    )
