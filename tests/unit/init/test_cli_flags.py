"""Unit tests for init CLI flags (--type, --force, --verbose).

Tests for T041:
- T041: Test --type flag behavior

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


@pytest.fixture(autouse=True)
def _mock_bd_init():
    """Mock bd init — CI doesn't have bd installed."""
    with patch("maverick.init._init_beads", new_callable=AsyncMock, return_value=True):
        yield


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

    @pytest.mark.parametrize(
        ("type_name", "config_marker"),
        [
            ("python", "ruff"),
            ("nodejs", "npm"),
            ("go", "go"),
            ("rust", "cargo"),
            ("ansible_collection", "ansible"),
            ("ansible_playbook", "ansible"),
        ],
    )
    def test_type_flag_accepted(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
        type_name: str,
        config_marker: str,
    ) -> None:
        """Test --type <type_name> is accepted and produces expected config."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight_success,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", type_name])

        assert result.exit_code == 0, f"Failed: {result.output}"
        config = (git_repo / "maverick.yaml").read_text().lower()
        assert config_marker in config

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
        """Test --type, --force, --verbose all together."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        # Create existing config
        (git_repo / "maverick.yaml").write_text("# Old\n")

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight_success,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "rust", "--force", "-v"])

        assert result.exit_code == 0, f"Failed: {result.output}"

        # Verify Rust config was generated
        config = (git_repo / "maverick.yaml").read_text()
        assert "cargo" in config.lower()


# =============================================================================
# --skip-providers flag
# =============================================================================


class TestSkipProvidersFlag:
    """Tests for --skip-providers CLI flag."""

    def test_skip_providers_flag_omits_discovery(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--skip-providers prevents provider discovery from running."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_preflight_success,
            ),
            patch(
                "maverick.init._maybe_discover_providers",
                new_callable=AsyncMock,
            ) as mock_discover,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "python", "--skip-providers"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        mock_discover.assert_not_called()

    def test_provider_output_shown(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Provider discovery results are shown in CLI output."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        from maverick.init.provider_discovery import (
            ProviderDiscoveryResult,
            ProviderProbeResult,
        )

        discovery = ProviderDiscoveryResult(
            providers=(
                ProviderProbeResult("claude", "Claude", "claude-agent-acp", True),
                ProviderProbeResult("copilot", "GitHub Copilot", "copilot", False),
                ProviderProbeResult("gemini", "Gemini", "gemini", False),
            ),
            default_provider="claude",
        )

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_preflight_success,
            ),
            patch(
                "maverick.init._maybe_discover_providers",
                new_callable=AsyncMock,
                return_value=discovery,
            ),
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "python"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "ACP Providers" in result.output
        assert "Claude" in result.output
        assert "(default)" in result.output

    def test_init_suggests_seed_when_runway_and_providers(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Post-init tip suggests 'maverick runway seed' when conditions met."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        from maverick.init.provider_discovery import (
            ProviderDiscoveryResult,
            ProviderProbeResult,
        )

        discovery = ProviderDiscoveryResult(
            providers=(ProviderProbeResult("claude", "Claude", "claude-agent-acp", True),),
            default_provider="claude",
        )

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_preflight_success,
            ),
            patch(
                "maverick.init._maybe_discover_providers",
                new_callable=AsyncMock,
                return_value=discovery,
            ),
            patch(
                "maverick.init._maybe_init_runway",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "python"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "maverick runway seed" in result.output

    def test_init_no_seed_suggestion_without_providers(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No seed suggestion when no providers found."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_preflight_success,
            ),
            patch(
                "maverick.init._maybe_discover_providers",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "python"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "maverick runway seed" not in result.output

    def test_init_no_seed_suggestion_without_runway(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_preflight_success: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No seed suggestion when runway not initialized."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        from maverick.init.provider_discovery import (
            ProviderDiscoveryResult,
            ProviderProbeResult,
        )

        discovery = ProviderDiscoveryResult(
            providers=(ProviderProbeResult("claude", "Claude", "claude-agent-acp", True),),
            default_provider="claude",
        )

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_preflight_success,
            ),
            patch(
                "maverick.init._maybe_discover_providers",
                new_callable=AsyncMock,
                return_value=discovery,
            ),
            patch(
                "maverick.init._maybe_init_runway",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "python"])

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "maverick runway seed" not in result.output
