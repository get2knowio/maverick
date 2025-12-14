"""Agent context dataclass.

This module defines the AgentContext dataclass for passing runtime context
to agent execution.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maverick.config import MaverickConfig


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Runtime context for agent execution (FR-009).

    This is an immutable value object that provides execution context to agents.
    It includes the working directory, git branch, application configuration,
    and any additional context needed by specific agents.

    Attributes:
        cwd: Working directory for agent execution.
        branch: Current git branch name.
        config: Application configuration (MaverickConfig).
        extra: Additional context for specific agents.

    Example:
        ```python
        context = AgentContext(
            cwd=Path("/workspace/project"),
            branch="feature-branch",
            config=MaverickConfig(),
            extra={"file_path": "src/main.py"},
        )

        # Or create from current working directory
        context = AgentContext.from_cwd(Path.cwd())
        ```
    """

    cwd: Path
    branch: str
    config: MaverickConfig
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate field values after initialization."""
        if not self.branch:
            raise ValueError("branch must be a non-empty string")

    @classmethod
    def from_cwd(
        cls,
        cwd: Path,
        config: MaverickConfig | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AgentContext:
        """Create context from working directory, auto-detecting git branch.

        Args:
            cwd: Working directory path.
            config: Optional configuration (creates default if not provided).
            extra: Optional additional context.

        Returns:
            AgentContext with detected branch name.

        Raises:
            ValueError: If cwd is not a valid directory or not in a git repo.
        """
        if not cwd.is_dir():
            raise ValueError(f"cwd must be an existing directory: {cwd}")

        # Detect git branch
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            )
            branch = result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Not a git repository: {cwd}") from e

        # Import here to avoid circular imports
        if config is None:
            from maverick.config import MaverickConfig

            config = MaverickConfig()

        return cls(
            cwd=cwd,
            branch=branch,
            config=config,
            extra=extra or {},
        )
