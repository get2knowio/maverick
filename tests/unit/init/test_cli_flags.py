"""Unit tests for init CLI flags (--type, --no-detect, --force, --verbose).

Tests for T041-T042:
- T041: Test --type flag behavior
- T042: Test --no-detect flag behavior

These tests focus on flag parsing and option validation at the CLI level.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from maverick.init import (
    DetectionConfidence,
    InitPreflightResult,
    PreflightStatus,
    PrerequisiteCheck,
    ProjectDetectionResult,
    ProjectType,
    ValidationCommands,
)
from maverick.main import cli

if TYPE_CHECKING:
    from click.testing import CliRunner


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def git_repo(temp_dir: Path) -> Path:
    """Create a minimal git repository for testing."""
    subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=temp_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=temp_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:org/repo.git"],
        cwd=temp_dir,
        capture_output=True,
    )
    (temp_dir / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Init"], cwd=temp_dir, capture_output=True)
    return temp_dir


@pytest.fixture
def mock_preflight_success() -> InitPreflightResult:
    """Successful preflight check result."""
    return InitPreflightResult(
        success=True,
        checks=(
            PrerequisiteCheck(
                name="git_installed",
                display_name="Git",
                status=PreflightStatus.PASS,
                message="Git installed",
            ),
        ),
        total_duration_ms=10,
    )


@pytest.fixture
def mock_detection_python() -> ProjectDetectionResult:
    """Python project detection result."""
    return ProjectDetectionResult(
        primary_type=ProjectType.PYTHON,
        detected_types=(ProjectType.PYTHON,),
        confidence=DetectionConfidence.HIGH,
        findings=("pyproject.toml found",),
        markers=(),
        validation_commands=ValidationCommands.for_project_type(ProjectType.PYTHON),
        detection_method="claude",
    )


# =============================================================================
# T041: Test --type flag behavior
# =============================================================================


class TestTypeFlag:
    """Tests for --type CLI flag."""

    def test_type_flag_accepts_python(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --type python is accepted."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight_success,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "python"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        config = (git_repo / "maverick.yaml").read_text()
        assert "ruff" in config  # Python uses ruff

    def test_type_flag_accepts_nodejs(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --type nodejs is accepted."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight_success,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "nodejs"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        config = (git_repo / "maverick.yaml").read_text()
        # Node.js uses npm/npx commands
        assert "npm" in config or "npx" in config

    def test_type_flag_accepts_go(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --type go is accepted."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight_success,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "go"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        config = (git_repo / "maverick.yaml").read_text()
        assert "go" in config.lower()

    def test_type_flag_accepts_rust(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --type rust is accepted."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight_success,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "rust"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        config = (git_repo / "maverick.yaml").read_text()
        assert "cargo" in config.lower()

    def test_type_flag_accepts_ansible_collection(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --type ansible_collection is accepted."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight_success,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "ansible_collection"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        config = (git_repo / "maverick.yaml").read_text()
        assert "ansible" in config.lower() or "molecule" in config.lower()

    def test_type_flag_accepts_ansible_playbook(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --type ansible_playbook is accepted."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight_success,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "ansible_playbook"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        config = (git_repo / "maverick.yaml").read_text()
        # Ansible playbook uses yamllint and ansible-lint
        assert "yaml" in config.lower() or "ansible" in config.lower()

    def test_type_flag_rejects_invalid_type(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --type with invalid value is rejected."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        result = cli_runner.invoke(cli, ["init", "--type", "invalid_type"])

        # Click should reject invalid choice
        assert result.exit_code != 0
        output_lower = result.output.lower()
        assert "invalid_type" in output_lower or "invalid" in output_lower

    def test_type_flag_case_insensitive(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --type is case insensitive."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight_success,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "PYTHON"])

        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_type_flag_skips_detection(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --type skips project detection entirely."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_preflight_success,
            ),
            patch(
                "maverick.init.detect_project_type",
                new_callable=AsyncMock,
            ) as mock_detect,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "python"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        # detect_project_type should NOT be called when --type is provided
        mock_detect.assert_not_called()


# =============================================================================
# T042: Test --no-detect flag behavior
# =============================================================================


class TestNoDetectFlag:
    """Tests for --no-detect CLI flag."""

    def test_no_detect_flag_uses_markers_only(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        mock_detection_python: ProjectDetectionResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --no-detect uses marker-based detection."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_preflight_success,
            ),
            patch(
                "maverick.init.detect_project_type",
                new_callable=AsyncMock,
                return_value=mock_detection_python,
            ) as mock_detect,
        ):
            result = cli_runner.invoke(cli, ["init", "--no-detect"])

        assert result.exit_code == 0, f"Failed: {result.output}"

        # Verify detection was called with use_claude=False
        mock_detect.assert_called_once()
        _, kwargs = mock_detect.call_args
        assert kwargs.get("use_claude") is False

    def test_no_detect_flag_skips_api_check(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_detection_python: ProjectDetectionResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --no-detect causes API check to be skipped."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        mock_preflight = InitPreflightResult(
            success=True,
            checks=(
                PrerequisiteCheck(
                    name="git_installed",
                    display_name="Git",
                    status=PreflightStatus.PASS,
                    message="Git installed",
                ),
                PrerequisiteCheck(
                    name="anthropic_api",
                    display_name="Anthropic API",
                    status=PreflightStatus.SKIP,  # Should be skipped
                    message="Skipped (--no-detect)",
                ),
            ),
            total_duration_ms=10,
        )

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_preflight,
            ) as mock_prereqs,
            patch(
                "maverick.init.detect_project_type",
                new_callable=AsyncMock,
                return_value=mock_detection_python,
            ),
        ):
            result = cli_runner.invoke(cli, ["init", "--no-detect"])

        assert result.exit_code == 0, f"Failed: {result.output}"

        # Verify prereqs was called with skip_api_check=True
        mock_prereqs.assert_called_once()
        _, kwargs = mock_prereqs.call_args
        assert kwargs.get("skip_api_check") is True

    def test_no_detect_with_type_uses_type(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --no-detect combined with --type uses type override."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_preflight_success,
            ),
            patch(
                "maverick.init.detect_project_type",
                new_callable=AsyncMock,
            ) as mock_detect,
        ):
            result = cli_runner.invoke(cli, ["init", "--no-detect", "--type", "go"])

        assert result.exit_code == 0, f"Failed: {result.output}"

        # With --type, detect_project_type should not be called at all
        mock_detect.assert_not_called()

        # Verify Go config was generated
        config = (git_repo / "maverick.yaml").read_text()
        assert "go" in config.lower()


# =============================================================================
# Combined Flag Tests
# =============================================================================


class TestCombinedFlags:
    """Tests for combinations of CLI flags."""

    def test_force_with_existing_config(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --force overwrites existing config."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        # Create existing config
        config_path = git_repo / "maverick.yaml"
        config_path.write_text("# Old config\n")

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight_success,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "python", "--force"])

        assert result.exit_code == 0, f"Failed: {result.output}"

        # Verify config was overwritten
        new_config = config_path.read_text()
        assert "# Old config" not in new_config
        assert "github:" in new_config

    def test_verbose_shows_extra_output(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        mock_detection_python: ProjectDetectionResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --verbose / -v shows additional output."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_preflight_success,
            ),
            patch(
                "maverick.init.detect_project_type",
                new_callable=AsyncMock,
                return_value=mock_detection_python,
            ),
        ):
            result = cli_runner.invoke(cli, ["init", "-v"])

        assert result.exit_code == 0, f"Failed: {result.output}"

        # Verbose should show additional sections
        assert "Generated Configuration" in result.output

    def test_all_flags_together(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test --type, --no-detect, --force, --verbose all together."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        # Create existing config
        (git_repo / "maverick.yaml").write_text("# Old\n")

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight_success,
        ):
            result = cli_runner.invoke(
                cli, ["init", "--type", "rust", "--no-detect", "--force", "-v"]
            )

        assert result.exit_code == 0, f"Failed: {result.output}"

        # Verify Rust config was generated
        config = (git_repo / "maverick.yaml").read_text()
        assert "cargo" in config.lower()
