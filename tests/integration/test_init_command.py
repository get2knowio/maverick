"""Integration tests for maverick init command.

Tests end-to-end initialization flow including:
- CLI invocation with CliRunner
- Prerequisite validation
- Project type detection (mocked Claude)
- Configuration generation and writing
- Performance assertions (<30s per SC-001)

These tests use mocking for external dependencies (git, gh, Anthropic API)
but exercise the full integration of all init modules.
"""

from __future__ import annotations

import os
import subprocess
import time
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


class TestInitCommandIntegration:
    """Integration tests for maverick init CLI command."""

    @pytest.fixture(autouse=True)
    def _mock_bd(self):
        """Mock bd init — CI doesn't have bd installed."""
        with patch("maverick.init._init_beads", new_callable=AsyncMock, return_value=True):
            yield

    @pytest.fixture
    def git_repo(self, temp_dir: Path) -> Path:
        """Create a temporary git repository with Python project markers."""
        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=temp_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=temp_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=temp_dir,
            capture_output=True,
            check=True,
        )

        # Add a remote
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:testorg/testrepo.git"],
            cwd=temp_dir,
            capture_output=True,
            check=True,
        )

        # Create Python project markers
        pyproject = temp_dir / "pyproject.toml"
        pyproject.write_text("""
[project]
name = "test-project"
version = "0.1.0"

[tool.ruff]
line-length = 88

[tool.mypy]
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
""")

        # Create initial commit
        subprocess.run(
            ["git", "add", "."],
            cwd=temp_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_dir,
            capture_output=True,
            check=True,
        )

        return temp_dir

    @pytest.fixture
    def mock_prerequisites(self) -> InitPreflightResult:
        """Create mock prerequisites result for successful init."""
        checks = (
            PrerequisiteCheck(
                name="git_installed",
                display_name="Git",
                status=PreflightStatus.PASS,
                message="Git installed (2.43.0)",
            ),
            PrerequisiteCheck(
                name="git_repo",
                display_name="Git Repository",
                status=PreflightStatus.PASS,
                message="Git repository detected",
            ),
            PrerequisiteCheck(
                name="gh_installed",
                display_name="GitHub CLI",
                status=PreflightStatus.PASS,
                message="GitHub CLI installed (2.40.0)",
            ),
            PrerequisiteCheck(
                name="gh_authenticated",
                display_name="GitHub Auth",
                status=PreflightStatus.PASS,
                message="GitHub CLI authenticated (user: @testuser)",
            ),
        )
        return InitPreflightResult(
            success=True,
            checks=checks,
            total_duration_ms=150,
        )

    @pytest.fixture
    def mock_detection(self) -> ProjectDetectionResult:
        """Mock detection result for Python project."""
        return ProjectDetectionResult(
            primary_type=ProjectType.PYTHON,
            detected_types=(ProjectType.PYTHON,),
            confidence=DetectionConfidence.HIGH,
            findings=(
                "pyproject.toml found at project root",
                "pytest configured as test runner",
                "ruff configured for linting",
                "mypy configured for type checking",
            ),
            markers=(),
            validation_commands=ValidationCommands.for_project_type(ProjectType.PYTHON),
            detection_method="claude",
        )

    def test_init_full_flow_success(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_prerequisites: InitPreflightResult,
        mock_detection: ProjectDetectionResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test complete init flow with all prerequisites passing.

        This is the primary happy path integration test that:
        1. Invokes `maverick init` via CLI
        2. Mocks prerequisites to pass
        3. Mocks Claude detection
        4. Verifies config file is written
        5. Asserts completion time < 30s (SC-001)
        """
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_prerequisites,
            ),
            patch(
                "maverick.init.detect_project_type",
                new_callable=AsyncMock,
                return_value=mock_detection,
            ),
        ):
            start_time = time.monotonic()
            result = cli_runner.invoke(cli, ["init", "--verbose"])
            elapsed = time.monotonic() - start_time

        # Performance assertion per SC-001
        assert elapsed < 30.0, f"Init took {elapsed:.2f}s, expected < 30s"

        # Verify success
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"

        # Verify output contains expected sections
        assert "Maverick Init" in result.output
        assert "Prerequisites" in result.output
        assert "Project Detection" in result.output
        assert "✓" in result.output
        assert "Configuration written to" in result.output

        # Verify config file was created
        config_path = git_repo / "maverick.yaml"
        assert config_path.exists(), "maverick.yaml should be created"

        # Verify config content
        config_content = config_path.read_text()
        assert "github:" in config_content
        assert "owner: testorg" in config_content
        assert "repo: testrepo" in config_content
        assert "validation:" in config_content
        assert "ruff" in config_content
        assert "pytest" in config_content

    def test_init_with_type_override(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_prerequisites: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test init with --type flag to override detection."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_prerequisites,
        ):
            result = cli_runner.invoke(cli, ["init", "--type", "nodejs"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"

        # Verify config file was created with Node.js commands
        config_path = git_repo / "maverick.yaml"
        assert config_path.exists()

        config_content = config_path.read_text()
        assert "npm" in config_content or "npx" in config_content

    def test_init_is_idempotent_when_config_exists(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_prerequisites: InitPreflightResult,
        mock_detection: ProjectDetectionResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Re-running ``maverick init`` on a project with an existing
        ``maverick.yaml`` succeeds without overwriting the config — only
        the idempotent steps (prereqs, beads, runway) are re-checked.
        ``--force`` remains the way to regenerate from scratch.
        FUTURE.md §4.3.
        """
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        # Existing config with a unique sentinel — assert it survives.
        config_path = git_repo / "maverick.yaml"
        original_content = "# Existing config — must NOT be overwritten\n"
        config_path.write_text(original_content)

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_prerequisites,
            ) as mock_prereq,
            patch(
                "maverick.init.detect_project_type",
                new_callable=AsyncMock,
                return_value=mock_detection,
            ) as mock_detect,
        ):
            result = cli_runner.invoke(cli, ["init"])

        # Idempotent re-init: exit success, config untouched.
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert config_path.read_text() == original_content
        assert "Already initialized" in result.output
        assert "--force" in result.output

        # Prereqs still ran (sanity check), but detection was skipped —
        # we don't re-detect a project we already have a config for.
        mock_prereq.assert_called_once()
        mock_detect.assert_not_called()

    def test_init_force_overwrites_config(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_prerequisites: InitPreflightResult,
        mock_detection: ProjectDetectionResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test init with --force overwrites existing config."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        # Create existing config with known content
        config_path = git_repo / "maverick.yaml"
        config_path.write_text("# Old config that should be overwritten\n")

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_prerequisites,
            ),
            patch(
                "maverick.init.detect_project_type",
                new_callable=AsyncMock,
                return_value=mock_detection,
            ),
        ):
            result = cli_runner.invoke(cli, ["init", "--force"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"

        # Verify config was overwritten
        config_content = config_path.read_text()
        assert "Old config" not in config_content
        assert "github:" in config_content

    def test_init_prerequisite_failure(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test init fails gracefully when prerequisites fail."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        failed_check = PrerequisiteCheck(
            name="gh_installed",
            display_name="GitHub CLI",
            status=PreflightStatus.FAIL,
            message="GitHub CLI not installed",
            remediation="Install from https://cli.github.com/",
        )

        mock_preflight = InitPreflightResult(
            success=False,
            checks=(
                PrerequisiteCheck(
                    name="git_installed",
                    display_name="Git",
                    status=PreflightStatus.PASS,
                    message="Git installed",
                ),
                PrerequisiteCheck(
                    name="git_repo",
                    display_name="Git Repository",
                    status=PreflightStatus.PASS,
                    message="Git repository detected",
                ),
                failed_check,
            ),
            total_duration_ms=50,
        )

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_preflight,
        ):
            result = cli_runner.invoke(cli, ["init"])

        # Should exit with code 1 (FAILURE)
        assert result.exit_code == 1
        assert "GitHub CLI" in result.output
        assert "Error" in result.output

    def test_init_no_git_remote_warning(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        mock_prerequisites: InitPreflightResult,
        mock_detection: ProjectDetectionResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test init shows warning when no git remote is configured."""
        # Initialize git repo without remote
        subprocess.run(
            ["git", "init"],
            cwd=temp_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=temp_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=temp_dir,
            capture_output=True,
            check=True,
        )

        # Create a file and commit
        (temp_dir / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=temp_dir,
            capture_output=True,
        )

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_prerequisites,
            ),
            patch(
                "maverick.init.detect_project_type",
                new_callable=AsyncMock,
                return_value=mock_detection,
            ),
        ):
            result = cli_runner.invoke(cli, ["init"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"

        # Should show warning about no remote
        assert "Warning" in result.output or "warning" in result.output.lower()
        assert "remote" in result.output.lower()

        # Config should still be created
        # When owner/repo is None, the YAML may not include them or include null
        config_path = temp_dir / "maverick.yaml"
        assert config_path.exists()
        config_content = config_path.read_text()
        # Verify github section exists (owner/repo may be omitted or null)
        assert "github:" in config_content

    def test_init_verbose_output(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_prerequisites: InitPreflightResult,
        mock_detection: ProjectDetectionResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test init with --verbose shows additional details."""
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_prerequisites,
            ),
            patch(
                "maverick.init.detect_project_type",
                new_callable=AsyncMock,
                return_value=mock_detection,
            ),
        ):
            result = cli_runner.invoke(cli, ["init", "-v"])

        assert result.exit_code == 0

        # Verbose mode should show additional details
        assert "Findings" in result.output
        assert "Git Remote" in result.output
        assert "Generated Configuration" in result.output

    def test_init_performance_under_30_seconds(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        mock_prerequisites: InitPreflightResult,
        mock_detection: ProjectDetectionResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Explicit test for SC-001: Init must complete in <30 seconds.

        This test is a specific assertion for the performance success criterion
        defined in the CLI interface contract.
        """
        os.chdir(git_repo)
        monkeypatch.setattr(Path, "home", lambda: git_repo)

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_prerequisites,
            ),
            patch(
                "maverick.init.detect_project_type",
                new_callable=AsyncMock,
                return_value=mock_detection,
            ),
        ):
            start = time.monotonic()
            result = cli_runner.invoke(cli, ["init"])
            elapsed = time.monotonic() - start

        assert result.exit_code == 0
        assert elapsed < 30.0, (
            f"SC-001 VIOLATED: maverick init took {elapsed:.2f}s, must complete in <30 seconds"
        )


class TestInitCommandEdgeCases:
    """Edge case tests for init command."""

    @pytest.fixture(autouse=True)
    def _mock_bd(self):
        """Mock bd init — CI doesn't have bd installed."""
        with patch("maverick.init._init_beads", new_callable=AsyncMock, return_value=True):
            yield

    @pytest.fixture
    def mock_success_preflight(self) -> InitPreflightResult:
        """Minimal successful preflight result."""
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

    def test_init_all_project_types(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        mock_success_preflight: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test init --type works for all supported project types."""
        # Initialize git repo
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
        subprocess.run(
            ["git", "commit", "-m", "Init"],
            cwd=temp_dir,
            capture_output=True,
        )

        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        project_types = ["python", "nodejs", "go", "rust", "ansible_collection"]

        for ptype in project_types:
            os.chdir(temp_dir)

            # Remove any existing config
            config_path = temp_dir / "maverick.yaml"
            if config_path.exists():
                config_path.unlink()

            with patch(
                "maverick.init.verify_prerequisites",
                new_callable=AsyncMock,
                return_value=mock_success_preflight,
            ):
                result = cli_runner.invoke(cli, ["init", "--type", ptype])

            assert result.exit_code == 0, f"Failed for --type {ptype}: {result.output}"
            assert config_path.exists(), f"Config not created for --type {ptype}"

    def test_init_combined_flags(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        mock_success_preflight: InitPreflightResult,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test init with multiple flags combined."""
        # Initialize git repo
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
        subprocess.run(
            ["git", "commit", "-m", "Init"],
            cwd=temp_dir,
            capture_output=True,
        )

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Create existing config to test --force
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text("# Old\n")

        with patch(
            "maverick.init.verify_prerequisites",
            new_callable=AsyncMock,
            return_value=mock_success_preflight,
        ):
            # Combine: --type, --force, --verbose
            result = cli_runner.invoke(
                cli,
                ["init", "--type", "go", "--force", "--verbose"],
            )

        assert result.exit_code == 0, f"Combined flags failed: {result.output}"

        # Verify Go-specific commands in config
        config_content = config_path.read_text()
        assert "go" in config_content.lower()


class TestInitBeadsLifecycle:
    """Integration tests for ``_init_beads`` lifecycle dispatch.

    These tests opt out of the ``_mock_bd`` autouse fixture used elsewhere
    in this module so they exercise the real ``BeadClient.init_or_bootstrap``
    state machine. The bd subprocess itself is mocked at
    :class:`CommandRunner.run` so the tests run without bd installed.

    The team-onboarding scenario — a fresh clone of a repo whose remote
    already carries Dolt history — is the path that previously surfaced
    bd's remote-divergence guard as a hard error in ``maverick init``.
    """

    @pytest.fixture
    def fresh_repo(self, temp_dir: Path) -> Path:
        """Git repo with origin set; nothing in ``.beads/``."""
        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:team/proj.git"],
            cwd=temp_dir,
            capture_output=True,
            check=True,
        )
        return temp_dir

    @pytest.mark.asyncio
    async def test_remote_with_dolt_history_routes_to_bootstrap(
        self,
        fresh_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A second developer cloning a project whose remote already has
        Dolt refs MUST get ``bd bootstrap`` (non-destructive adopt), NOT
        ``bd init --force`` (which bd's safety guard rejects)."""
        from maverick.init import _init_beads
        from maverick.runners.command import CommandRunner
        from maverick.runners.models import CommandResult

        # Pretend bd is on PATH — _init_beads guards on shutil.which.
        monkeypatch.setattr("maverick.init.shutil.which", lambda _: "/usr/bin/bd")

        calls: list[list[str]] = []

        async def fake_run(_self, command, **_kwargs):
            calls.append(list(command))
            # ls-remote → return a Dolt-data ref hash so the dispatch
            # picks the bootstrap branch.
            if command[:2] == ["git", "ls-remote"]:
                return CommandResult(
                    returncode=0,
                    stdout="abcdef\trefs/dolt/data\n",
                    stderr="",
                    duration_ms=5,
                    timed_out=False,
                )
            # Any bd subcommand → succeed.
            return CommandResult(
                returncode=0, stdout="", stderr="", duration_ms=5, timed_out=False
            )

        monkeypatch.setattr(CommandRunner, "run", fake_run)

        result = await _init_beads(fresh_repo, verbose=True)
        assert result is True

        # The cardinal assertion: bd bootstrap ran, bd init did NOT.
        bd_subcommands = [c[1] for c in calls if c[0] == "bd"]
        assert "bootstrap" in bd_subcommands, (
            f"Expected 'bd bootstrap' to be invoked when remote has Dolt "
            f"history; got bd calls: {bd_subcommands}"
        )
        assert "init" not in bd_subcommands, (
            f"'bd init' must NOT run when remote has Dolt history "
            f"(bd's safety guard would reject it); got bd calls: "
            f"{bd_subcommands}"
        )

    @pytest.mark.asyncio
    async def test_jsonl_only_clone_routes_to_bootstrap(
        self,
        fresh_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A clone where ``.beads/issues.jsonl`` is git-tracked but the
        Dolt store hasn't been materialized locally must also bootstrap."""
        from maverick.init import _init_beads
        from maverick.runners.command import CommandRunner
        from maverick.runners.models import CommandResult

        monkeypatch.setattr("maverick.init.shutil.which", lambda _: "/usr/bin/bd")

        # Simulate the second-developer state: tracked JSONL, no local DB.
        beads = fresh_repo / ".beads"
        beads.mkdir()
        (beads / "issues.jsonl").write_text("")

        calls: list[list[str]] = []

        async def fake_run(_self, command, **_kwargs):
            calls.append(list(command))
            # ls-remote returns nothing → JSONL alone must drive bootstrap.
            return CommandResult(
                returncode=0, stdout="", stderr="", duration_ms=5, timed_out=False
            )

        monkeypatch.setattr(CommandRunner, "run", fake_run)

        await _init_beads(fresh_repo, verbose=False)

        bd_subcommands = [c[1] for c in calls if c[0] == "bd"]
        assert "bootstrap" in bd_subcommands
        assert "init" not in bd_subcommands

    @pytest.mark.asyncio
    async def test_truly_fresh_repo_routes_to_init(
        self,
        fresh_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A genuinely fresh repo — no `.beads/`, no remote dolt refs —
        gets ``bd init`` with the sanitized prefix."""
        from maverick.init import _init_beads
        from maverick.runners.command import CommandRunner
        from maverick.runners.models import CommandResult

        monkeypatch.setattr("maverick.init.shutil.which", lambda _: "/usr/bin/bd")

        calls: list[list[str]] = []

        async def fake_run(_self, command, **_kwargs):
            calls.append(list(command))
            return CommandResult(
                returncode=0, stdout="", stderr="", duration_ms=5, timed_out=False
            )

        monkeypatch.setattr(CommandRunner, "run", fake_run)

        await _init_beads(fresh_repo, verbose=False)

        bd_calls = [c for c in calls if c[0] == "bd"]
        assert len(bd_calls) == 1
        assert bd_calls[0][1] == "init"
        assert "--non-interactive" in bd_calls[0]
        # Prefix is the (sanitized) project directory name.
        assert "--prefix" in bd_calls[0]

    @pytest.mark.asyncio
    async def test_already_initialized_skips_lifecycle_call(
        self,
        fresh_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Re-running on a repo with a materialized local DB performs no
        bd lifecycle subprocess at all (idempotent)."""
        from maverick.init import _init_beads
        from maverick.runners.command import CommandRunner
        from maverick.runners.models import CommandResult

        monkeypatch.setattr("maverick.init.shutil.which", lambda _: "/usr/bin/bd")

        # Pre-existing local Dolt store — the SKIP branch. Must include
        # both the embedded directory AND a valid metadata.json with
        # ``issue_prefix`` (the strict is_initialized contract).
        import json as _json

        beads = fresh_repo / ".beads"
        (beads / "embeddeddolt").mkdir(parents=True)
        (beads / "metadata.json").write_text(
            _json.dumps({"issue_prefix": "earlybird", "dolt_database": "earlybird"})
        )

        calls: list[list[str]] = []

        async def fake_run(_self, command, **_kwargs):
            calls.append(list(command))
            return CommandResult(
                returncode=0, stdout="", stderr="", duration_ms=5, timed_out=False
            )

        monkeypatch.setattr(CommandRunner, "run", fake_run)

        await _init_beads(fresh_repo, verbose=False)

        # Skipped — neither bd init nor bd bootstrap ran. ls-remote is also
        # skipped because is_initialized() returns True before probing.
        bd_calls = [c for c in calls if c[0] == "bd"]
        assert bd_calls == []
