from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """Status of a required CLI dependency.

    Attributes:
        name: Dependency name (e.g., "git", "gh").
        available: Whether the dependency is installed and accessible.
        version: Version string if available.
        path: Path to executable if found.
        error: Error message if not available.
        install_url: URL for installation instructions.
    """

    name: str
    available: bool
    version: str | None = None
    path: str | None = None
    error: str | None = None
    install_url: str | None = None


def check_dependencies(required: list[str] | None = None) -> list[DependencyStatus]:
    """Check for required CLI tools and return their status.

    Validates that required CLI tools are installed and accessible in the system
    PATH. For each tool, attempts to determine the version by running the tool's
    version command.

    Args:
        required: List of tool names to check. Defaults to ["git", "gh"].

    Returns:
        List of DependencyStatus objects, one per required tool. Each status includes
        availability, version, path, and installation URL if not available.

    Example:
        >>> statuses = check_dependencies()
        >>> for status in statuses:
        ...     if not status.available:
        ...         print(f"{status.name} not found: {status.install_url}")
        git not found: https://git-scm.com/downloads

        >>> statuses = check_dependencies(["git", "gh", "docker"])
        >>> git_status = statuses[0]
        >>> print(f"{git_status.name} v{git_status.version} at {git_status.path}")
        git v2.39.0 at /usr/bin/git
    """
    if required is None:
        required = ["git", "gh"]

    # Map tool names to installation URLs
    install_urls = {
        "git": "https://git-scm.com/downloads",
        "gh": "https://cli.github.com/",
    }

    statuses: list[DependencyStatus] = []

    for tool_name in required:
        # Check if tool is in PATH
        tool_path = shutil.which(tool_name)

        if tool_path is None:
            # Tool not found
            statuses.append(
                DependencyStatus(
                    name=tool_name,
                    available=False,
                    error=f"{tool_name} is not installed or not in PATH",
                    install_url=install_urls.get(tool_name),
                )
            )
            continue

        # Tool found, try to get version
        version: str | None = None
        error: str | None = None

        try:
            result = subprocess.run(
                [tool_name, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                # Extract version from output (first line, strip whitespace)
                version = result.stdout.strip().split("\n")[0]
            else:
                error = f"Failed to get version: {result.stderr.strip()}"

        except subprocess.TimeoutExpired:
            error = "Version check timed out"
        except Exception as e:
            error = f"Error checking version: {e!s}"

        statuses.append(
            DependencyStatus(
                name=tool_name,
                available=True,
                version=version,
                path=tool_path,
                error=error,
                install_url=install_urls.get(tool_name),
            )
        )

    return statuses


def check_git_auth() -> DependencyStatus:
    """Check GitHub CLI authentication status.

    Runs 'gh auth status' to verify that the user is authenticated with GitHub.
    This is required for GitHub operations like creating PRs and issues.

    Returns:
        DependencyStatus with name="gh-auth". If authenticated, available=True
        with version info. If not authenticated, available=False with error message
        and suggestion to run 'gh auth login'.

    Example:
        >>> auth_status = check_git_auth()
        >>> if not auth_status.available:
        ...     print(f"Error: {auth_status.error}")
        Error: Not authenticated. Run 'gh auth login'

        >>> if auth_status.available:
        ...     print(f"Authenticated: {auth_status.version}")
        Authenticated: Logged in to github.com as username
    """
    # First check if gh is available
    gh_path = shutil.which("gh")

    if gh_path is None:
        return DependencyStatus(
            name="gh-auth",
            available=False,
            error="GitHub CLI (gh) is not installed",
            install_url="https://cli.github.com/",
        )

    # Check auth status
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            # Authenticated - extract account info from stdout
            # Format is typically: "✓ Logged in to github.com as username (...)"
            auth_info = result.stdout.strip().split("\n")[0] if result.stdout else None

            return DependencyStatus(
                name="gh-auth",
                available=True,
                version=auth_info,
                path=gh_path,
            )
        else:
            # Not authenticated
            error_msg = (
                result.stderr.strip()
                if result.stderr
                else "Authentication check failed"
            )

            return DependencyStatus(
                name="gh-auth",
                available=False,
                error=f"{error_msg}. Run 'gh auth login' to authenticate",
                install_url="https://cli.github.com/",
            )

    except subprocess.TimeoutExpired:
        return DependencyStatus(
            name="gh-auth",
            available=False,
            error="Authentication check timed out. Run 'gh auth login' to authenticate",
            install_url="https://cli.github.com/",
        )
    except Exception as e:
        return DependencyStatus(
            name="gh-auth",
            available=False,
            error=(
                f"Error checking authentication: {e!s}. "
                "Run 'gh auth login' to authenticate"
            ),
            install_url="https://cli.github.com/",
        )
