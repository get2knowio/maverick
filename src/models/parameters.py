"""Parameters dataclass for workflow inputs."""

from dataclasses import dataclass


@dataclass
class Parameters:
    """Parameters passed to workflow at start.

    MVP requires github_repo_url; designed to scale to N+ parameters.
    """

    github_repo_url: str

    def __post_init__(self) -> None:
        """Validate required parameters."""
        if not self.github_repo_url or not isinstance(self.github_repo_url, str):
            raise ValueError("github_repo_url must be a non-empty string")

        self.github_repo_url = self.github_repo_url.strip()

        if not self.github_repo_url:
            raise ValueError("github_repo_url must be a non-empty string after stripping")
