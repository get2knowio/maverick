"""Parameters dataclass for workflow inputs."""

from __future__ import annotations

from dataclasses import dataclass

from src.models.compose import ComposeConfig


@dataclass
class Parameters:
    """Parameters passed to workflow at start.

    MVP requires github_repo_url; designed to scale to N+ parameters.

    Attributes:
        github_repo_url: GitHub repository URL to validate
        compose_config: Optional Docker Compose configuration for containerized validation
    """

    github_repo_url: str
    compose_config: ComposeConfig | None = None

    def __post_init__(self) -> None:
        """Validate required parameters."""
        if not self.github_repo_url or not isinstance(self.github_repo_url, str):
            raise ValueError("github_repo_url must be a non-empty string")

        self.github_repo_url = self.github_repo_url.strip()

        if not self.github_repo_url:
            raise ValueError("github_repo_url must be a non-empty string after stripping")
