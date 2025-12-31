"""Integration tests for review command text output.

Tests the review command --output text option.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from maverick.cli.context import ExitCode
from maverick.main import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def mock_config() -> dict[str, Any]:
    """Create a mock configuration."""
    return {
        "github": {
            "owner": "test-owner",
            "repo": "test-repo",
            "default_branch": "main",
        },
        "notifications": {
            "enabled": False,
        },
        "validation": {},
        "model": {
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 8192,
            "temperature": 0.0,
        },
        "parallel": {},
        "verbosity": "warning",
    }


def test_review_command_text_output(
    runner: CliRunner,
    tmp_path: Path,
    mock_config: dict[str, Any],
) -> None:
    """Test review command with text output."""
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Create maverick.yaml config
        import yaml

        config_file = Path("maverick.yaml")
        with open(config_file, "w") as f:
            yaml.dump(mock_config, f)

        # Mock gh pr view
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="git version 2.34.1"),
                MagicMock(returncode=0, stdout="gh version 2.0.0"),
                MagicMock(returncode=0, stdout="PR #123"),
                MagicMock(
                    returncode=0,
                    stdout='{"headRefName": "feature-test", "baseRefName": "main"}',
                ),
            ]

            # Mock CodeReviewerAgent
            with patch(
                "maverick.cli.commands.review.CodeReviewerAgent"
            ) as mock_agent_class:
                mock_agent = AsyncMock()
                mock_agent_class.return_value = mock_agent

                from maverick.models.review import (
                    ReviewFinding,
                    ReviewResult,
                    ReviewSeverity,
                )

                mock_result = ReviewResult(
                    summary="Review complete",
                    findings=[
                        ReviewFinding(
                            file="test.py",
                            line=10,
                            message="Fix this issue please",
                            severity=ReviewSeverity.MAJOR,
                        )
                    ],
                    files_reviewed=3,
                    success=True,
                )
                mock_agent.execute.return_value = mock_result

                # Run review command with text output
                result = runner.invoke(cli, ["review", "123", "--output", "text"])

                # Verify
                assert result.exit_code == ExitCode.SUCCESS
                assert "Review complete" in result.output
                assert "[MAJOR] test.py" in result.output
                assert "Line 10" in result.output
                assert "WARNING" not in result.output  # Because we used MAJOR
                assert "Fix this issue please" in result.output
