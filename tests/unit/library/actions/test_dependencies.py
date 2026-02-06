"""Unit tests for dependency sync actions.

Tests the dependencies.py action module including:
- Explicit sync_cmd usage
- Auto-detection from various manifest files
- Graceful skip when no manifest is found
- Command failure handling
- Priority order of manifest detection
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.library.actions.dependencies import (
    _detect_sync_command,
    sync_dependencies,
)
from maverick.runners.models import CommandResult


def make_result(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    duration_ms: float = 10.0,
    timed_out: bool = False,
) -> CommandResult:
    """Create a CommandResult for test mocking."""
    return CommandResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


class TestDetectSyncCommand:
    """Tests for _detect_sync_command helper."""

    def test_detects_uv_lock(self, tmp_path: Path) -> None:
        """Test detects uv.lock and returns uv sync."""
        (tmp_path / "uv.lock").touch()
        result = _detect_sync_command(tmp_path)
        assert result == ["uv", "sync"]

    def test_detects_pyproject_toml(self, tmp_path: Path) -> None:
        """Test detects pyproject.toml (without uv.lock) and returns pip install."""
        (tmp_path / "pyproject.toml").touch()
        result = _detect_sync_command(tmp_path)
        assert result == ["pip", "install", "-e", ".[dev]"]

    def test_detects_package_lock_json(self, tmp_path: Path) -> None:
        """Test detects package-lock.json and returns npm install."""
        (tmp_path / "package-lock.json").touch()
        result = _detect_sync_command(tmp_path)
        assert result == ["npm", "install"]

    def test_detects_yarn_lock(self, tmp_path: Path) -> None:
        """Test detects yarn.lock and returns yarn install."""
        (tmp_path / "yarn.lock").touch()
        result = _detect_sync_command(tmp_path)
        assert result == ["yarn", "install"]

    def test_detects_pnpm_lock(self, tmp_path: Path) -> None:
        """Test detects pnpm-lock.yaml and returns pnpm install."""
        (tmp_path / "pnpm-lock.yaml").touch()
        result = _detect_sync_command(tmp_path)
        assert result == ["pnpm", "install"]

    def test_detects_cargo_toml(self, tmp_path: Path) -> None:
        """Test detects Cargo.toml and returns cargo build."""
        (tmp_path / "Cargo.toml").touch()
        result = _detect_sync_command(tmp_path)
        assert result == ["cargo", "build"]

    def test_detects_go_mod(self, tmp_path: Path) -> None:
        """Test detects go.mod and returns go mod download."""
        (tmp_path / "go.mod").touch()
        result = _detect_sync_command(tmp_path)
        assert result == ["go", "mod", "download"]

    def test_returns_none_when_no_manifest(self, tmp_path: Path) -> None:
        """Test returns None when no manifest file is found."""
        result = _detect_sync_command(tmp_path)
        assert result is None

    def test_uv_lock_takes_precedence_over_pyproject(self, tmp_path: Path) -> None:
        """Test uv.lock takes priority over pyproject.toml."""
        (tmp_path / "uv.lock").touch()
        (tmp_path / "pyproject.toml").touch()
        result = _detect_sync_command(tmp_path)
        assert result == ["uv", "sync"]


class TestSyncDependencies:
    """Tests for sync_dependencies action."""

    @pytest.mark.asyncio
    async def test_uses_explicit_sync_cmd(self, tmp_path: Path) -> None:
        """Test uses provided sync_cmd over auto-detection."""
        explicit_cmd = ["uv", "sync", "--frozen"]

        with patch("maverick.library.actions.dependencies._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout="Resolved 42 packages")
            )

            result = await sync_dependencies(
                cwd=str(tmp_path), sync_cmd=explicit_cmd
            )

            assert result.success is True
            assert result.skipped is False
            assert result.command == "uv sync --frozen"
            assert result.error is None
            mock_runner.run.assert_called_once_with(explicit_cmd, cwd=tmp_path)

    @pytest.mark.asyncio
    async def test_auto_detects_uv(self, tmp_path: Path) -> None:
        """Test auto-detects uv.lock and runs uv sync."""
        (tmp_path / "uv.lock").touch()

        with patch("maverick.library.actions.dependencies._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout="Resolved 10 packages")
            )

            result = await sync_dependencies(cwd=str(tmp_path))

            assert result.success is True
            assert result.skipped is False
            assert result.command == "uv sync"
            mock_runner.run.assert_called_once_with(
                ["uv", "sync"], cwd=tmp_path
            )

    @pytest.mark.asyncio
    async def test_auto_detects_pyproject(self, tmp_path: Path) -> None:
        """Test auto-detects pyproject.toml and runs pip install."""
        (tmp_path / "pyproject.toml").touch()

        with patch("maverick.library.actions.dependencies._runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=make_result())

            result = await sync_dependencies(cwd=str(tmp_path))

            assert result.success is True
            assert result.command == "pip install -e .[dev]"

    @pytest.mark.asyncio
    async def test_auto_detects_npm(self, tmp_path: Path) -> None:
        """Test auto-detects package-lock.json and runs npm install."""
        (tmp_path / "package-lock.json").touch()

        with patch("maverick.library.actions.dependencies._runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=make_result())

            result = await sync_dependencies(cwd=str(tmp_path))

            assert result.success is True
            assert result.command == "npm install"

    @pytest.mark.asyncio
    async def test_skips_when_no_manifest(self, tmp_path: Path) -> None:
        """Test returns skipped result when no manifest file detected."""
        result = await sync_dependencies(cwd=str(tmp_path))

        assert result.success is True
        assert result.skipped is True
        assert result.command is None
        assert "No package manifest" in (result.reason or "")
        assert result.error is None

    @pytest.mark.asyncio
    async def test_handles_command_failure(self, tmp_path: Path) -> None:
        """Test returns error result when sync command fails."""
        (tmp_path / "uv.lock").touch()

        with patch("maverick.library.actions.dependencies._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    returncode=1,
                    stderr="error: Network unreachable",
                )
            )

            result = await sync_dependencies(cwd=str(tmp_path))

            assert result.success is False
            assert result.skipped is False
            assert result.command == "uv sync"
            assert result.error == "error: Network unreachable"

    @pytest.mark.asyncio
    async def test_explicit_cmd_overrides_auto_detect(self, tmp_path: Path) -> None:
        """Test explicit sync_cmd takes priority even when manifest exists."""
        (tmp_path / "package-lock.json").touch()
        explicit_cmd = ["poetry", "install"]

        with patch("maverick.library.actions.dependencies._runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=make_result())

            result = await sync_dependencies(
                cwd=str(tmp_path), sync_cmd=explicit_cmd
            )

            assert result.command == "poetry install"
            mock_runner.run.assert_called_once_with(explicit_cmd, cwd=tmp_path)

    @pytest.mark.asyncio
    async def test_defaults_to_cwd_when_no_cwd_provided(self) -> None:
        """Test defaults to current working directory when cwd is None."""
        with patch("maverick.library.actions.dependencies._runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=make_result())

            with patch(
                "maverick.library.actions.dependencies._detect_sync_command",
                return_value=None,
            ):
                result = await sync_dependencies()

                assert result.success is True
                assert result.skipped is True

    @pytest.mark.asyncio
    async def test_captures_stdout_on_success(self, tmp_path: Path) -> None:
        """Test captures command stdout in result."""
        (tmp_path / "uv.lock").touch()
        expected_output = "Resolved 42 packages in 1.2s\nInstalled 3 packages"

        with patch("maverick.library.actions.dependencies._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=expected_output)
            )

            result = await sync_dependencies(cwd=str(tmp_path))

            assert result.output == expected_output

    @pytest.mark.asyncio
    async def test_result_to_dict(self, tmp_path: Path) -> None:
        """Test DependencySyncResult.to_dict() serialization."""
        result = await sync_dependencies(cwd=str(tmp_path))
        d = result.to_dict()

        assert isinstance(d, dict)
        assert "success" in d
        assert "command" in d
        assert "output" in d
        assert "skipped" in d
        assert "reason" in d
        assert "error" in d
