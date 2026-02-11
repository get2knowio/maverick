"""Unit tests for ``maverick briefing`` CLI command."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.beads.models import BeadSummary, ReadyBead
from maverick.main import cli

_PATCH_VERIFY = "maverick.cli.commands.briefing.BeadClient.verify_available"
_PATCH_READY = "maverick.cli.commands.briefing.BeadClient.ready"
_PATCH_CHILDREN = "maverick.cli.commands.briefing.BeadClient.children"


def _make_ready_bead(
    id: str = "bead-001",
    title: str = "Test bead",
    priority: int = 1,
    bead_type: str = "task",
) -> ReadyBead:
    return ReadyBead(id=id, title=title, priority=priority, bead_type=bead_type)


def _make_summary(
    id: str = "bead-001",
    title: str = "Test bead",
    priority: int = 1,
    bead_type: str = "task",
    status: str = "open",
) -> BeadSummary:
    return BeadSummary(
        id=id, title=title, priority=priority, bead_type=bead_type, status=status
    )


class TestBriefingRegistered:
    """Test that briefing command is registered."""

    def test_briefing_in_cli(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(cli, ["--help"])
        assert "briefing" in result.output

    def test_briefing_help(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        result = cli_runner.invoke(cli, ["briefing", "--help"])
        assert result.exit_code == 0
        assert "--epic" in result.output
        assert "--format" in result.output

    def test_briefing_help_shows_description(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        result = cli_runner.invoke(cli, ["briefing", "--help"])
        assert "Review queued beads" in result.output


class TestBriefingBdNotAvailable:
    """Test behavior when bd is not available."""

    @patch(_PATCH_VERIFY, new_callable=AsyncMock, return_value=False)
    def test_fails_when_bd_unavailable(
        self,
        mock_verify: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        result = cli_runner.invoke(cli, ["briefing"])
        assert result.exit_code != 0
        assert "bd is not available" in result.output


class TestBriefingReady:
    """Tests for briefing without --epic (ready beads)."""

    @patch(_PATCH_READY, new_callable=AsyncMock, return_value=[])
    @patch(_PATCH_VERIFY, new_callable=AsyncMock, return_value=True)
    def test_no_ready_beads(
        self,
        mock_verify: AsyncMock,
        mock_ready: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        result = cli_runner.invoke(cli, ["briefing"])
        assert "No beads ready" in result.output

    @patch(_PATCH_READY, new_callable=AsyncMock)
    @patch(_PATCH_VERIFY, new_callable=AsyncMock, return_value=True)
    def test_displays_ready_beads_table(
        self,
        mock_verify: AsyncMock,
        mock_ready: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        mock_ready.return_value = [
            _make_ready_bead("bead-001", "Setup project", 1),
            _make_ready_bead("bead-002", "Add tests", 2),
        ]
        result = cli_runner.invoke(cli, ["briefing"])
        assert result.exit_code == 0
        assert "2 beads ready" in result.output
        assert "bead-001" in result.output
        assert "Setup project" in result.output
        assert "bead-002" in result.output
        assert "maverick fly" in result.output

    @patch(_PATCH_READY, new_callable=AsyncMock)
    @patch(_PATCH_VERIFY, new_callable=AsyncMock, return_value=True)
    def test_single_bead_no_plural(
        self,
        mock_verify: AsyncMock,
        mock_ready: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        mock_ready.return_value = [_make_ready_bead()]
        result = cli_runner.invoke(cli, ["briefing"])
        assert "1 bead ready" in result.output
        assert "1 beads ready" not in result.output

    @patch(_PATCH_READY, new_callable=AsyncMock)
    @patch(_PATCH_VERIFY, new_callable=AsyncMock, return_value=True)
    def test_ready_calls_client_with_limit(
        self,
        mock_verify: AsyncMock,
        mock_ready: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        mock_ready.return_value = []
        cli_runner.invoke(cli, ["briefing"])
        mock_ready.assert_called_once_with(limit=100)

    @patch(_PATCH_READY, new_callable=AsyncMock)
    @patch(_PATCH_VERIFY, new_callable=AsyncMock, return_value=True)
    def test_json_format_ready(
        self,
        mock_verify: AsyncMock,
        mock_ready: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        mock_ready.return_value = [
            _make_ready_bead("bead-001", "Setup project", 1),
        ]
        result = cli_runner.invoke(cli, ["briefing", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "bead-001"
        assert data[0]["title"] == "Setup project"


class TestBriefingEpic:
    """Tests for briefing with --epic flag."""

    @patch(_PATCH_READY, new_callable=AsyncMock, return_value=[])
    @patch(_PATCH_CHILDREN, new_callable=AsyncMock, return_value=[])
    @patch(_PATCH_VERIFY, new_callable=AsyncMock, return_value=True)
    def test_epic_no_children(
        self,
        mock_verify: AsyncMock,
        mock_children: AsyncMock,
        mock_ready: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        result = cli_runner.invoke(cli, ["briefing", "--epic", "epic-001"])
        assert "has no children" in result.output

    @patch(_PATCH_READY, new_callable=AsyncMock)
    @patch(_PATCH_CHILDREN, new_callable=AsyncMock)
    @patch(_PATCH_VERIFY, new_callable=AsyncMock, return_value=True)
    def test_epic_shows_all_children_with_status(
        self,
        mock_verify: AsyncMock,
        mock_children: AsyncMock,
        mock_ready: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        mock_children.return_value = [
            _make_summary("bead-001", "Setup", 1, status="closed"),
            _make_summary("bead-002", "Implement", 2, status="open"),
            _make_summary("bead-003", "Test", 2, status="open"),
        ]
        mock_ready.return_value = [
            _make_ready_bead("bead-002", "Implement", 2),
            _make_ready_bead("bead-003", "Test", 2),
        ]
        result = cli_runner.invoke(cli, ["briefing", "--epic", "my-epic"])
        assert result.exit_code == 0
        assert "2 of 3" in result.output
        assert "my-epic" in result.output
        assert "bead-001" in result.output
        assert "closed" in result.output
        assert "ready" in result.output

    @patch(_PATCH_READY, new_callable=AsyncMock)
    @patch(_PATCH_CHILDREN, new_callable=AsyncMock)
    @patch(_PATCH_VERIFY, new_callable=AsyncMock, return_value=True)
    def test_epic_passes_parent_id_to_ready(
        self,
        mock_verify: AsyncMock,
        mock_children: AsyncMock,
        mock_ready: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        mock_children.return_value = []
        mock_ready.return_value = []
        cli_runner.invoke(cli, ["briefing", "--epic", "epic-123"])
        mock_children.assert_called_once_with("epic-123")
        mock_ready.assert_called_once_with(parent_id="epic-123", limit=100)

    @patch(_PATCH_READY, new_callable=AsyncMock)
    @patch(_PATCH_CHILDREN, new_callable=AsyncMock)
    @patch(_PATCH_VERIFY, new_callable=AsyncMock, return_value=True)
    def test_epic_json_format(
        self,
        mock_verify: AsyncMock,
        mock_children: AsyncMock,
        mock_ready: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        mock_children.return_value = [
            _make_summary("bead-001", "Setup", 1, status="closed"),
            _make_summary("bead-002", "Implement", 2, status="open"),
        ]
        mock_ready.return_value = [
            _make_ready_bead("bead-002", "Implement", 2),
        ]
        result = cli_runner.invoke(
            cli, ["briefing", "--epic", "epic-001", "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2
        # Closed bead keeps its status
        assert data[0]["status"] == "closed"
        # Open bead in ready set gets marked as ready
        assert data[1]["status"] == "ready"

    @patch(_PATCH_READY, new_callable=AsyncMock)
    @patch(_PATCH_CHILDREN, new_callable=AsyncMock)
    @patch(_PATCH_VERIFY, new_callable=AsyncMock, return_value=True)
    def test_epic_closed_bead_not_marked_ready(
        self,
        mock_verify: AsyncMock,
        mock_children: AsyncMock,
        mock_ready: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A closed bead should never be re-marked as ready even if in ready set."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        mock_children.return_value = [
            _make_summary("bead-001", "Done task", 1, status="closed"),
        ]
        # Hypothetically in ready set (shouldn't happen but test the guard)
        mock_ready.return_value = [
            _make_ready_bead("bead-001", "Done task", 1),
        ]
        result = cli_runner.invoke(
            cli, ["briefing", "--epic", "epic-001", "--format", "json"]
        )
        data = json.loads(result.output)
        assert data[0]["status"] == "closed"
