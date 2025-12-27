"""Integration tests for subprocess runners.

These tests require actual CLI tools to be installed and may interact
with external services. They are marked with pytest.mark.integration
and are not run by default in CI.

To run these tests locally:
    pytest tests/integration/runners/ -m integration -v
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

# Tool availability detection for conditional skipping
HAS_GH = shutil.which("gh") is not None
HAS_RUFF = shutil.which("ruff") is not None


def _gh_is_authenticated() -> bool:
    """Check if GitHub CLI is authenticated."""
    if not HAS_GH:
        return False
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


GH_AUTHENTICATED = _gh_is_authenticated()

pytestmark = pytest.mark.integration


class TestCommandRunnerIntegration:
    """Integration tests for CommandRunner with actual subprocess execution."""

    @pytest.mark.asyncio
    async def test_run_echo_command(self) -> None:
        """Test running a simple echo command."""
        from maverick.runners import CommandRunner

        runner = CommandRunner()
        result = await runner.run(["echo", "hello world"])

        assert result.success
        assert result.returncode == 0
        assert "hello world" in result.stdout

    @pytest.mark.asyncio
    async def test_run_command_with_error(self) -> None:
        """Test running a command that fails."""
        from maverick.runners import CommandRunner

        runner = CommandRunner()
        result = await runner.run(["ls", "/nonexistent/path/12345"])

        assert not result.success
        assert result.returncode != 0


class TestGitHubCLIRunnerIntegration:
    """Integration tests for GitHubCLIRunner.

    These tests require GitHub CLI to be installed and authenticated.
    """

    @pytest.mark.skipif(
        not GH_AUTHENTICATED, reason="Requires gh CLI installed and authenticated"
    )
    @pytest.mark.asyncio
    async def test_list_issues(self) -> None:
        """Test listing issues from the current repository."""
        from maverick.runners import GitHubCLIRunner

        runner = GitHubCLIRunner()
        issues = await runner.list_issues(state="open", limit=5)

        # Should return a list (may be empty)
        assert isinstance(issues, list)


class TestValidationRunnerIntegration:
    """Integration tests for ValidationRunner with actual validation tools."""

    @pytest.mark.skipif(not HAS_RUFF, reason="Requires ruff to be installed")
    @pytest.mark.asyncio
    async def test_validation_stages(self) -> None:
        """Test running validation stages with actual ruff."""
        from maverick.runners import ValidationRunner, ValidationStage

        stages = [
            ValidationStage(
                name="lint-check",
                command=("ruff", "check", "--select=E", "src/"),
            ),
        ]
        runner = ValidationRunner(stages=stages)
        output = await runner.run()

        # Should complete (pass or fail)
        assert output.stages_run == 1
