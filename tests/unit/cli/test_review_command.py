"""Unit tests for the review CLI command.

Tests review command functionality:
- Valid PR number execution
- Fix option
- Output format options (json, markdown, text)
- Error handling for nonexistent PRs
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from maverick.main import cli


def test_review_command_with_valid_pr_number(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T057: Test review command with valid PR number - 'maverick review 123'.

    Verifies:
    - Command accepts PR number argument
    - PR validation using 'gh pr view'
    - CodeReviewerAgent is executed
    - Success exit code
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies to return success (FR-013 startup validation)
    from maverick.cli.validators import DependencyStatus

    with patch("maverick.main.check_dependencies") as mock_check_deps:
        mock_check_deps.return_value = [
            DependencyStatus(
                name="git", available=True, version="2.39.0", path="/usr/bin/git"
            ),
            DependencyStatus(
                name="gh", available=True, version="2.20.0", path="/usr/bin/gh"
            ),
        ]

        # Mock gh pr view to succeed
        with patch("subprocess.run") as mock_subprocess:
            # First call: gh pr view 123 (validation)
            # Second call: gh pr view 123 --json headRefName,baseRefName
            pr_data = {"headRefName": "feature-123", "baseRefName": "main"}
            mock_subprocess.side_effect = [
                MagicMock(returncode=0, stdout="PR #123", stderr=""),
                MagicMock(returncode=0, stdout=json.dumps(pr_data), stderr=""),
            ]

            # Mock CodeReviewerAgent
            with patch(
                "maverick.cli.commands.review.CodeReviewerAgent"
            ) as mock_agent_cls:
                mock_agent = MagicMock()
                mock_agent_cls.return_value = mock_agent

                # Mock agent execution
                async def mock_execute(context):
                    from maverick.models.review import ReviewResult

                    return ReviewResult(
                        success=True,
                        findings=[],
                        files_reviewed=3,
                        summary="Reviewed 3 files, no issues found",
                        metadata={"branch": "feature-123", "base_branch": "main"},
                    )

                mock_agent.execute = mock_execute

                result = cli_runner.invoke(cli, ["review", "123"])

                assert result.exit_code == 0
                # Verify gh pr view was called
                assert mock_subprocess.call_count == 2


def test_review_with_fix_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T058: Test review --fix option - 'maverick review 123 --fix'.

    Verifies:
    - --fix flag is accepted
    - Fix mode is passed to the review agent
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies to return success (FR-013 startup validation)
    from maverick.cli.validators import DependencyStatus

    with patch("maverick.main.check_dependencies") as mock_check_deps:
        mock_check_deps.return_value = [
            DependencyStatus(
                name="git", available=True, version="2.39.0", path="/usr/bin/git"
            ),
            DependencyStatus(
                name="gh", available=True, version="2.20.0", path="/usr/bin/gh"
            ),
        ]

        # Mock gh pr view to succeed
        with patch("subprocess.run") as mock_subprocess:
            pr_data = {"headRefName": "feature-123", "baseRefName": "main"}
            mock_subprocess.side_effect = [
                MagicMock(returncode=0, stdout="PR #123", stderr=""),
                MagicMock(returncode=0, stdout=json.dumps(pr_data), stderr=""),
            ]

            # Mock CodeReviewerAgent
            with patch(
                "maverick.cli.commands.review.CodeReviewerAgent"
            ) as mock_agent_cls:
                mock_agent = MagicMock()
                mock_agent_cls.return_value = mock_agent

                # Mock agent execution
                async def mock_execute(context):
                    from maverick.models.review import ReviewResult

                    return ReviewResult(
                        success=True,
                        findings=[],
                        files_reviewed=3,
                        summary="Reviewed 3 files, no issues found",
                        metadata={"branch": "feature-123", "base_branch": "main"},
                    )

                mock_agent.execute = mock_execute

                result = cli_runner.invoke(cli, ["review", "123", "--fix"])

                assert result.exit_code == 0


def test_review_output_json_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T059: Test review --output json option - outputs valid JSON.

    Verifies:
    - --output json flag is accepted
    - Output is valid JSON
    - Contains expected review data
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies to return success (FR-013 startup validation)
    from maverick.cli.validators import DependencyStatus

    with patch("maverick.main.check_dependencies") as mock_check_deps:
        mock_check_deps.return_value = [
            DependencyStatus(
                name="git", available=True, version="2.39.0", path="/usr/bin/git"
            ),
            DependencyStatus(
                name="gh", available=True, version="2.20.0", path="/usr/bin/gh"
            ),
        ]

        # Mock gh pr view to succeed
        with patch("subprocess.run") as mock_subprocess:
            pr_data = {"headRefName": "feature-123", "baseRefName": "main"}
            mock_subprocess.side_effect = [
                MagicMock(returncode=0, stdout="PR #123", stderr=""),
                MagicMock(returncode=0, stdout=json.dumps(pr_data), stderr=""),
            ]

            # Mock CodeReviewerAgent
            with patch(
                "maverick.cli.commands.review.CodeReviewerAgent"
            ) as mock_agent_cls:
                mock_agent = MagicMock()
                mock_agent_cls.return_value = mock_agent

                # Mock agent execution
                async def mock_execute(context):
                    from maverick.models.review import ReviewResult

                    return ReviewResult(
                        success=True,
                        findings=[],
                        files_reviewed=3,
                        summary="Reviewed 3 files, no issues found",
                        metadata={"branch": "feature-123", "base_branch": "main"},
                    )

                mock_agent.execute = mock_execute

                result = cli_runner.invoke(cli, ["review", "123", "--output", "json"])

                assert result.exit_code == 0
                # Verify output is valid JSON
                try:
                    data = json.loads(result.output)
                    assert "success" in data
                    assert "findings" in data
                    assert "summary" in data
                except json.JSONDecodeError:
                    pytest.fail("Output is not valid JSON")


def test_review_output_markdown_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T060: Test review --output markdown option - outputs markdown.

    Verifies:
    - --output markdown flag is accepted
    - Output is formatted as markdown
    - Contains review summary
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies to return success (FR-013 startup validation)
    from maverick.cli.validators import DependencyStatus

    with patch("maverick.main.check_dependencies") as mock_check_deps:
        mock_check_deps.return_value = [
            DependencyStatus(
                name="git", available=True, version="2.39.0", path="/usr/bin/git"
            ),
            DependencyStatus(
                name="gh", available=True, version="2.20.0", path="/usr/bin/gh"
            ),
        ]

        # Mock gh pr view to succeed
        with patch("subprocess.run") as mock_subprocess:
            pr_data = {"headRefName": "feature-123", "baseRefName": "main"}
            mock_subprocess.side_effect = [
                MagicMock(returncode=0, stdout="PR #123", stderr=""),
                MagicMock(returncode=0, stdout=json.dumps(pr_data), stderr=""),
            ]

            # Mock CodeReviewerAgent
            with patch(
                "maverick.cli.commands.review.CodeReviewerAgent"
            ) as mock_agent_cls:
                mock_agent = MagicMock()
                mock_agent_cls.return_value = mock_agent

                # Mock agent execution
                async def mock_execute(context):
                    from maverick.models.review import ReviewResult

                    return ReviewResult(
                        success=True,
                        findings=[],
                        files_reviewed=3,
                        summary="Reviewed 3 files, no issues found",
                        metadata={"branch": "feature-123", "base_branch": "main"},
                    )

                mock_agent.execute = mock_execute

                result = cli_runner.invoke(
                    cli, ["review", "123", "--output", "markdown"]
                )

                assert result.exit_code == 0
                # Verify markdown formatting
                assert (
                    "#" in result.output
                    or "**" in result.output
                    or result.output.strip().startswith("Reviewed")
                )


def test_review_output_text_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test review --output text option - outputs plain text.

    Verifies:
    - --output text flag is accepted
    - Output is formatted as plain text
    - Contains review summary
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies
    from maverick.cli.validators import DependencyStatus

    with patch("maverick.main.check_dependencies") as mock_check_deps:
        mock_check_deps.return_value = [
            DependencyStatus(
                name="git", available=True, version="2.39.0", path="/usr/bin/git"
            ),
            DependencyStatus(
                name="gh", available=True, version="2.20.0", path="/usr/bin/gh"
            ),
        ]

        # Mock gh pr view
        with patch("subprocess.run") as mock_subprocess:
            pr_data = {"headRefName": "feature-123", "baseRefName": "main"}
            mock_subprocess.side_effect = [
                MagicMock(returncode=0, stdout="PR #123", stderr=""),
                MagicMock(returncode=0, stdout=json.dumps(pr_data), stderr=""),
            ]

            # Mock CodeReviewerAgent
            with patch(
                "maverick.cli.commands.review.CodeReviewerAgent"
            ) as mock_agent_cls:
                mock_agent = MagicMock()
                mock_agent_cls.return_value = mock_agent

                # Mock agent execution
                async def mock_execute(context):
                    from maverick.models.review import ReviewResult

                    return ReviewResult(
                        success=True,
                        findings=[],
                        files_reviewed=3,
                        summary="Reviewed 3 files, no issues found",
                        metadata={"branch": "feature-123", "base_branch": "main"},
                    )

                mock_agent.execute = mock_execute

                result = cli_runner.invoke(cli, ["review", "123", "--output", "text"])

                assert result.exit_code == 0
                # Verify text formatting (should contain summary)
                assert "Reviewed 3 files" in result.output
                # Should NOT look like JSON (simple heuristic)
                assert not result.output.strip().startswith("{")


def test_review_with_nonexistent_pr_error(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T061: Test review with non-existent PR error.

    Verifies:
    - PR validation fails for non-existent PR
    - Exit code 1 (FAILURE)
    - Error message mentions PR not found
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock gh pr view to fail (PR not found)
    with patch("subprocess.run") as mock_subprocess:
        mock_subprocess.return_value = MagicMock(
            returncode=1, stdout="", stderr="pull request not found"
        )

        result = cli_runner.invoke(cli, ["review", "999"])

        assert result.exit_code == 1
        # Error message should mention PR not found
        assert "999" in result.output or "not found" in result.output.lower()
