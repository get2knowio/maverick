"""Subprocess execution module with async command runners.

For git operations, use maverick.git instead:
    - maverick.git.GitRepository (sync) or maverick.git.AsyncGitRepository (async)
    - maverick.git.DiffStats, maverick.git.CommitInfo, etc.
"""

from __future__ import annotations

from maverick.runners.coderabbit import CodeRabbitRunner
from maverick.runners.command import CommandRunner
from maverick.runners.github import GitHubCLIRunner
from maverick.runners.models import (
    CheckStatus,
    CodeRabbitFinding,
    CodeRabbitResult,
    CommandResult,
    GitHubIssue,
    ParsedError,
    PullRequest,
    StageResult,
    StreamLine,
    ValidationOutput,
    ValidationStage,
)
from maverick.runners.preflight import (
    CustomToolValidator,
    PreflightConfig,
    PreflightResult,
    PreflightValidator,
    ValidationResult,
)
from maverick.runners.protocols import ValidatableRunner
from maverick.runners.validation import ValidationRunner

__all__ = [
    # Models
    "CommandResult",
    "StreamLine",
    "ParsedError",
    "ValidationStage",
    "StageResult",
    "ValidationOutput",
    "GitHubIssue",
    "PullRequest",
    "CheckStatus",
    "CodeRabbitFinding",
    "CodeRabbitResult",
    # Preflight validation
    "ValidationResult",
    "PreflightResult",
    "PreflightConfig",
    "PreflightValidator",
    "CustomToolValidator",
    "ValidatableRunner",
    # Runners
    "CommandRunner",
    "GitHubCLIRunner",
    "CodeRabbitRunner",
    "ValidationRunner",
]

__version__ = "0.1.0"
