"""Unit tests for remediation message content and formatting.

These tests verify that remediation messages provide clear, actionable
guidance for resolving prerequisite check failures.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_gh_not_authenticated_remediation_content():
    """Test that gh unauthenticated remediation includes auth steps and docs link."""
    from src.activities.gh_status import check_gh_status

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock unauthenticated gh auth status
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"",
            b"You are not logged into any GitHub hosts. Run gh auth login to authenticate.\n",
        )
        mock_process.returncode = 1
        mock_exec.return_value = mock_process

        result = await check_gh_status()

        # Verify remediation content
        assert result.status == "fail"
        assert result.remediation is not None

        remediation = result.remediation.lower()

        # Must contain authentication command
        assert "gh auth login" in remediation

        # Must contain link to documentation
        assert "https://cli.github.com" in remediation or "cli.github.com" in remediation

        # Should mention authentication/login
        assert "authenticate" in remediation or "login" in remediation


@pytest.mark.asyncio
async def test_gh_not_installed_remediation_content():
    """Test that gh not installed remediation includes install steps and docs link."""
    from src.activities.gh_status import check_gh_status

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock command not found
        mock_exec.side_effect = FileNotFoundError("gh command not found")

        result = await check_gh_status()

        # Verify remediation content
        assert result.status == "fail"
        assert result.remediation is not None

        remediation = result.remediation.lower()

        # Must contain installation instructions
        assert "install" in remediation

        # Should mention at least one installation method
        assert any(method in remediation for method in ["brew", "winget", "linux"])

        # Must contain link to documentation
        assert (
            "https://cli.github.com" in remediation
            or "cli.github.com" in remediation
            or "github.com/cli" in remediation
        )

        # Should mention authentication as next step
        assert "gh auth login" in remediation


@pytest.mark.asyncio
async def test_copilot_not_installed_remediation_content():
    """Test that copilot not installed remediation includes install steps and docs link."""
    from src.activities.copilot_help import check_copilot_help

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock command not found
        mock_exec.side_effect = FileNotFoundError("copilot command not found")

        result = await check_copilot_help()

        # Verify remediation content
        assert result.status == "fail"
        assert result.remediation is not None

        remediation = result.remediation.lower()

        # Must contain installation instructions
        assert "install" in remediation

        # Must mention the tool name
        assert "copilot" in remediation

        # Must contain link to documentation or installation source
        assert "github.com" in remediation or "docs.github.com" in remediation

        # Should mention it's a CLI tool or standalone binary
        assert any(term in remediation for term in ["cli", "binary", "command"])


@pytest.mark.asyncio
async def test_copilot_failed_remediation_content():
    """Test that copilot execution failure remediation includes troubleshooting steps."""
    from src.activities.copilot_help import check_copilot_help

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock command execution failure
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"error: command failed\n")
        mock_process.returncode = 1
        mock_exec.return_value = mock_process

        result = await check_copilot_help()

        # Verify remediation content
        assert result.status == "fail"
        assert result.remediation is not None

        remediation = result.remediation.lower()

        # Should contain troubleshooting guidance
        assert any(term in remediation for term in ["troubleshoot", "verify", "check", "try"])

        # Should mention copilot
        assert "copilot" in remediation


@pytest.mark.asyncio
async def test_remediation_message_formatting():
    """Test that remediation messages are well-formatted with clear steps."""
    from src.activities.gh_status import check_gh_status

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock unauthenticated
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"not logged in")
        mock_process.returncode = 1
        mock_exec.return_value = mock_process

        result = await check_gh_status()

        remediation = result.remediation
        assert remediation is not None

        # Should not be empty or too short
        assert len(remediation) >= 20

        # Should be properly capitalized (starts with capital letter)
        assert remediation[0].isupper()

        # Should contain proper punctuation (not just a fragment)
        assert any(char in remediation for char in [".", ":", "\n"])


@pytest.mark.asyncio
async def test_remediation_none_on_pass():
    """Test that remediation is None or empty when checks pass."""
    from src.activities.copilot_help import check_copilot_help
    from src.activities.gh_status import check_gh_status

    # Test gh passing
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"authenticated", b"")
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result = await check_gh_status()
        assert result.status == "pass"
        assert result.remediation is None or result.remediation == ""

    # Test copilot passing
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"help text", b"")
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result = await check_copilot_help()
        assert result.status == "pass"
        assert result.remediation is None or result.remediation == ""


@pytest.mark.asyncio
async def test_all_remediation_messages_are_actionable():
    """Test that all failure scenarios provide actionable remediation."""
    from src.activities.copilot_help import check_copilot_help
    from src.activities.gh_status import check_gh_status

    # Test gh not authenticated
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"not logged in")
        mock_process.returncode = 1
        mock_exec.return_value = mock_process

        result = await check_gh_status()

        assert result.status == "fail"
        assert result.remediation is not None
        assert len(result.remediation) > 0

        # Remediation should suggest an action (contains a verb)
        remediation_lower = result.remediation.lower()
        action_verbs = [
            "install",
            "run",
            "authenticate",
            "login",
            "check",
            "verify",
            "try",
            "execute",
            "download",
            "see",
        ]
        assert any(verb in remediation_lower for verb in action_verbs), (
            f"Remediation should contain an action verb: {result.remediation}"
        )

    # Test gh not installed
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = FileNotFoundError()

        result = await check_gh_status()

        assert result.status == "fail"
        assert result.remediation is not None
        assert len(result.remediation) > 0

    # Test copilot not installed
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = FileNotFoundError()

        result = await check_copilot_help()

        assert result.status == "fail"
        assert result.remediation is not None
        assert len(result.remediation) > 0

    # Test copilot failed
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"error")
        mock_process.returncode = 1
        mock_exec.return_value = mock_process

        result = await check_copilot_help()

        assert result.status == "fail"
        assert result.remediation is not None
        assert len(result.remediation) > 0
