"""GitHub URL normalization utilities."""

import re
from dataclasses import dataclass


@dataclass
class NormalizedRepo:
    """Normalized repository information.

    Attributes:
        host: GitHub host (e.g., github.com or GHES host)
        repo_slug: Repository in owner/repo format
    """

    host: str
    repo_slug: str


class URLNormalizationError(ValueError):
    """Raised when URL cannot be normalized."""

    pass


def _validate_repo_slug(repo_slug: str) -> None:
    """Validate that repo_slug matches GitHub's allowed pattern.

    GitHub allows alphanumeric characters, hyphens, underscores, and dots
    in both owner and repository names.

    Args:
        repo_slug: Repository slug in owner/repo format

    Raises:
        URLNormalizationError: If repo_slug contains invalid characters
    """
    # GitHub pattern: owner and repo can contain A-Z, a-z, 0-9, -, _, .
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo_slug):
        raise URLNormalizationError(
            f"Invalid repository slug: {repo_slug}. "
            "Owner and repository names must contain only alphanumeric characters, hyphens, underscores, and dots."
        )


def normalize_github_url(url: str) -> NormalizedRepo:
    """Normalize GitHub URL to host and owner/repo slug.

    Accepts HTTPS and SSH formats:
    - HTTPS: https://github.com/owner/repo
    - HTTPS: https://github.com/owner/repo.git
    - SSH: git@github.com:owner/repo
    - SSH: git@github.com:owner/repo.git

    Also supports GitHub Enterprise Server hosts.

    Args:
        url: GitHub repository URL

    Returns:
        NormalizedRepo with host and repo_slug

    Raises:
        URLNormalizationError: If URL format is invalid or unsupported
    """
    url = url.strip()

    if not url:
        raise URLNormalizationError("URL cannot be empty")

    # Try HTTPS format: https://host/owner/repo[.git]
    https_match = re.match(r"^https?://([^/]+)/([^/]+)/([^/]+?)(?:\.git)?/?$", url, re.IGNORECASE)

    if https_match:
        host = https_match.group(1).lower()
        validate_github_host(host)
        owner = https_match.group(2)
        repo = https_match.group(3)
        repo_slug = f"{owner}/{repo}"
        _validate_repo_slug(repo_slug)
        return NormalizedRepo(host=host, repo_slug=repo_slug)

    # Try SSH format: git@host:owner/repo[.git]
    ssh_match = re.match(r"^git@([^:]+):([^/]+)/([^/]+?)(?:\.git)?/?$", url, re.IGNORECASE)

    if ssh_match:
        host = ssh_match.group(1).lower()
        validate_github_host(host)
        owner = ssh_match.group(2)
        repo = ssh_match.group(3)
        repo_slug = f"{owner}/{repo}"
        _validate_repo_slug(repo_slug)
        return NormalizedRepo(host=host, repo_slug=repo_slug)

    # Unrecognized format
    raise URLNormalizationError(
        f"Unsupported URL format: {url}. Expected HTTPS (https://host/owner/repo) or SSH (git@host:owner/repo)"
    )


def validate_github_host(host: str) -> None:
    """Validate that host is a recognized GitHub host.

    Accepts github.com and GitHub Enterprise Server hosts.
    Basic validation: host should be a valid domain format.

    Args:
        host: GitHub host to validate

    Raises:
        URLNormalizationError: If host format is invalid
    """
    if not host:
        raise URLNormalizationError("Host cannot be empty")

    # Basic domain validation: alphanumeric, dots, hyphens
    if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$", host, re.IGNORECASE):
        raise URLNormalizationError(f"Invalid host format: {host}")
