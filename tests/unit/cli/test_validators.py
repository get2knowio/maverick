"""Unit tests for CLI validators module."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from maverick.cli.validators import DependencyStatus, check_dependencies, check_git_auth


class TestDependencyStatus:
    """Tests for DependencyStatus dataclass."""

    def test_creation_with_required_fields_only(self) -> None:
        """Test creating DependencyStatus with only required fields."""
        status = DependencyStatus(name="git", available=True)

        assert status.name == "git"
        assert status.available is True
        assert status.version is None
        assert status.path is None
        assert status.error is None
        assert status.install_url is None

    def test_creation_with_all_fields(self) -> None:
        """Test creating DependencyStatus with all fields populated."""
        status = DependencyStatus(
            name="gh",
            available=True,
            version="gh version 2.40.0",
            path="/usr/bin/gh",
            error=None,
            install_url="https://cli.github.com/",
        )

        assert status.name == "gh"
        assert status.available is True
        assert status.version == "gh version 2.40.0"
        assert status.path == "/usr/bin/gh"
        assert status.error is None
        assert status.install_url == "https://cli.github.com/"

    def test_creation_with_error(self) -> None:
        """Test creating DependencyStatus for missing dependency with error."""
        status = DependencyStatus(
            name="docker",
            available=False,
            error="docker is not installed or not in PATH",
            install_url="https://docker.com",
        )

        assert status.name == "docker"
        assert status.available is False
        assert status.version is None
        assert status.path is None
        assert status.error == "docker is not installed or not in PATH"
        assert status.install_url == "https://docker.com"

    def test_dataclass_is_frozen(self) -> None:
        """Test that DependencyStatus dataclass is frozen (immutable)."""
        status = DependencyStatus(name="git", available=True)

        # Should not be able to modify frozen dataclass
        with pytest.raises((AttributeError, Exception)):
            status.available = False  # type: ignore

    def test_dataclass_uses_slots(self) -> None:
        """Test that DependencyStatus uses slots for memory efficiency."""
        status = DependencyStatus(name="git", available=True)

        # Frozen dataclass with slots prevents dynamic attribute assignment
        # The exception type may vary, but it should raise an error
        with pytest.raises((AttributeError, TypeError)):
            status.new_attribute = "value"  # type: ignore


class TestCheckDependencies:
    """Tests for check_dependencies function."""

    def test_with_default_dependencies(self) -> None:
        """Test check_dependencies with default dependencies (git, gh)."""
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "git version 2.39.0\n"
        mock_run.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/git"),
            patch("subprocess.run", return_value=mock_run),
        ):
            statuses = check_dependencies()

        assert len(statuses) == 2
        assert statuses[0].name == "git"
        assert statuses[1].name == "gh"

    def test_with_custom_list_of_dependencies(self) -> None:
        """Test check_dependencies with custom list of dependencies."""
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "version 1.0.0\n"
        mock_run.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/tool"),
            patch("subprocess.run", return_value=mock_run),
        ):
            statuses = check_dependencies(["git", "gh", "docker"])

        assert len(statuses) == 3
        assert statuses[0].name == "git"
        assert statuses[1].name == "gh"
        assert statuses[2].name == "docker"

    def test_with_missing_dependency(self) -> None:
        """Test check_dependencies with missing dependency (not in PATH)."""
        with patch("shutil.which", return_value=None):
            statuses = check_dependencies(["git"])

        assert len(statuses) == 1
        assert statuses[0].name == "git"
        assert statuses[0].available is False
        assert statuses[0].version is None
        assert statuses[0].path is None
        assert "not installed or not in PATH" in statuses[0].error

    def test_version_extraction_works(self) -> None:
        """Test that version extraction works correctly."""
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "git version 2.39.0\n"
        mock_run.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/git"),
            patch("subprocess.run", return_value=mock_run),
        ):
            statuses = check_dependencies(["git"])

        assert len(statuses) == 1
        assert statuses[0].available is True
        assert statuses[0].version == "git version 2.39.0"
        assert statuses[0].path == "/usr/bin/git"
        assert statuses[0].error is None

    def test_version_extraction_multiline_output(self) -> None:
        """Test version extraction with multi-line output (uses first line)."""
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = (
            "gh version 2.40.0 (2024-01-01)\nCopyright info\nOther details\n"
        )
        mock_run.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_run),
        ):
            statuses = check_dependencies(["gh"])

        assert len(statuses) == 1
        assert statuses[0].version == "gh version 2.40.0 (2024-01-01)"

    def test_install_url_included_for_git(self) -> None:
        """Test that install_url is included for git."""
        with patch("shutil.which", return_value=None):
            statuses = check_dependencies(["git"])

        assert len(statuses) == 1
        assert statuses[0].install_url == "https://git-scm.com/downloads"

    def test_install_url_included_for_gh(self) -> None:
        """Test that install_url is included for gh."""
        with patch("shutil.which", return_value=None):
            statuses = check_dependencies(["gh"])

        assert len(statuses) == 1
        assert statuses[0].install_url == "https://cli.github.com/"

    def test_install_url_none_for_unknown_tool(self) -> None:
        """Test that install_url is None for unknown tools."""
        with patch("shutil.which", return_value=None):
            statuses = check_dependencies(["unknown-tool"])

        assert len(statuses) == 1
        assert statuses[0].install_url is None

    def test_version_check_failure(self) -> None:
        """Test when version check command fails."""
        mock_run = MagicMock()
        mock_run.returncode = 1
        mock_run.stdout = ""
        mock_run.stderr = "Error: command not recognized\n"

        with (
            patch("shutil.which", return_value="/usr/bin/tool"),
            patch("subprocess.run", return_value=mock_run),
        ):
            statuses = check_dependencies(["tool"])

        assert len(statuses) == 1
        assert statuses[0].available is True
        assert statuses[0].path == "/usr/bin/tool"
        assert statuses[0].version is None
        assert "Failed to get version" in statuses[0].error
        assert "Error: command not recognized" in statuses[0].error

    def test_version_check_timeout(self) -> None:
        """Test when version check times out."""
        with (
            patch("shutil.which", return_value="/usr/bin/tool"),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("tool --version", 5),
            ),
        ):
            statuses = check_dependencies(["tool"])

        assert len(statuses) == 1
        assert statuses[0].available is True
        assert statuses[0].path == "/usr/bin/tool"
        assert statuses[0].version is None
        assert "Version check timed out" in statuses[0].error

    def test_version_check_exception(self) -> None:
        """Test when version check raises unexpected exception."""
        with (
            patch("shutil.which", return_value="/usr/bin/tool"),
            patch("subprocess.run", side_effect=Exception("Unexpected error")),
        ):
            statuses = check_dependencies(["tool"])

        assert len(statuses) == 1
        assert statuses[0].available is True
        assert statuses[0].path == "/usr/bin/tool"
        assert statuses[0].version is None
        assert "Error checking version" in statuses[0].error
        assert "Unexpected error" in statuses[0].error

    def test_subprocess_run_called_with_correct_args(self) -> None:
        """Test that subprocess.run is called with correct arguments."""
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "version\n"
        mock_run.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/git"),
            patch("subprocess.run", return_value=mock_run) as mock_subprocess,
        ):
            check_dependencies(["git"])

        # Verify subprocess.run was called with correct args
        mock_subprocess.assert_called_once_with(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_multiple_dependencies_mixed_availability(self) -> None:
        """Test multiple dependencies with some available and some missing."""

        def mock_which(tool_name: str) -> str | None:
            if tool_name == "git":
                return "/usr/bin/git"
            elif tool_name == "gh":
                return "/usr/bin/gh"
            else:
                return None

        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "version 1.0.0\n"
        mock_run.stderr = ""

        with (
            patch("shutil.which", side_effect=mock_which),
            patch("subprocess.run", return_value=mock_run),
        ):
            statuses = check_dependencies(["git", "docker", "gh"])

        assert len(statuses) == 3

        # git is available
        assert statuses[0].name == "git"
        assert statuses[0].available is True
        assert statuses[0].path == "/usr/bin/git"

        # docker is not available
        assert statuses[1].name == "docker"
        assert statuses[1].available is False
        assert statuses[1].path is None

        # gh is available
        assert statuses[2].name == "gh"
        assert statuses[2].available is True
        assert statuses[2].path == "/usr/bin/gh"


class TestCheckGitAuth:
    """Tests for check_git_auth function."""

    def test_successful_authentication(self) -> None:
        """Test successful GitHub CLI authentication check."""
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "✓ Logged in to github.com as testuser (keyring)\n"
        mock_run.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_run),
        ):
            status = check_git_auth()

        assert status.name == "gh-auth"
        assert status.available is True
        assert status.version == "✓ Logged in to github.com as testuser (keyring)"
        assert status.path == "/usr/bin/gh"
        assert status.error is None

    def test_failed_authentication(self) -> None:
        """Test failed GitHub CLI authentication check."""
        mock_run = MagicMock()
        mock_run.returncode = 1
        mock_run.stdout = ""
        mock_run.stderr = "Not logged in to any GitHub hosts"

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_run),
        ):
            status = check_git_auth()

        assert status.name == "gh-auth"
        assert status.available is False
        assert status.version is None
        assert status.error is not None
        assert "Not logged in to any GitHub hosts" in status.error
        assert "gh auth login" in status.error

    def test_gh_not_installed(self) -> None:
        """Test when GitHub CLI (gh) is not installed."""
        with patch("shutil.which", return_value=None):
            status = check_git_auth()

        assert status.name == "gh-auth"
        assert status.available is False
        assert status.version is None
        assert "GitHub CLI (gh) is not installed" in status.error
        assert status.install_url == "https://cli.github.com/"

    def test_error_message_includes_suggestion(self) -> None:
        """Test that error message includes 'gh auth login' suggestion."""
        mock_run = MagicMock()
        mock_run.returncode = 1
        mock_run.stdout = ""
        mock_run.stderr = "Authentication failed"

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_run),
        ):
            status = check_git_auth()

        assert status.available is False
        assert "Run 'gh auth login'" in status.error

    def test_auth_check_timeout(self) -> None:
        """Test when auth check times out."""
        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("gh auth status", 10),
            ),
        ):
            status = check_git_auth()

        assert status.name == "gh-auth"
        assert status.available is False
        assert status.version is None
        assert "timed out" in status.error
        assert "gh auth login" in status.error

    def test_auth_check_exception(self) -> None:
        """Test when auth check raises unexpected exception."""
        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", side_effect=Exception("Network error")),
        ):
            status = check_git_auth()

        assert status.name == "gh-auth"
        assert status.available is False
        assert status.version is None
        assert "Error checking authentication" in status.error
        assert "Network error" in status.error
        assert "gh auth login" in status.error

    def test_subprocess_run_called_with_correct_args(self) -> None:
        """Test that subprocess.run is called with correct arguments."""
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "✓ Logged in\n"
        mock_run.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_run) as mock_subprocess,
        ):
            check_git_auth()

        # Verify subprocess.run was called with correct args
        mock_subprocess.assert_called_once_with(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_authenticated_with_multiline_output(self) -> None:
        """Test authentication with multi-line output (uses first line)."""
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = (
            "✓ Logged in to github.com as testuser (keyring)\n"
            "✓ Git operations for github.com configured to use ssh protocol.\n"
            "✓ Token: gho_************************************\n"
        )
        mock_run.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_run),
        ):
            status = check_git_auth()

        assert status.available is True
        assert status.version == "✓ Logged in to github.com as testuser (keyring)"

    def test_authenticated_with_empty_stdout(self) -> None:
        """Test authenticated but with empty stdout."""
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = ""
        mock_run.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_run),
        ):
            status = check_git_auth()

        assert status.available is True
        assert status.version is None

    def test_failed_with_empty_stderr(self) -> None:
        """Test failed authentication with empty stderr."""
        mock_run = MagicMock()
        mock_run.returncode = 1
        mock_run.stdout = ""
        mock_run.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_run),
        ):
            status = check_git_auth()

        assert status.available is False
        assert "Authentication check failed" in status.error
        assert "gh auth login" in status.error

    def test_install_url_always_included(self) -> None:
        """Test that install_url is always included for gh-auth."""
        # Test when gh not installed
        with patch("shutil.which", return_value=None):
            status = check_git_auth()
            assert status.install_url == "https://cli.github.com/"

        # Test when auth fails
        mock_run = MagicMock()
        mock_run.returncode = 1
        mock_run.stdout = ""
        mock_run.stderr = "Not authenticated"

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_run),
        ):
            status = check_git_auth()
            assert status.install_url == "https://cli.github.com/"
