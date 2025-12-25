"""Subprocess execution module with async command runners.

Note: maverick.runners.git is deprecated. For new code, use maverick.git instead:
    - GitRunner -> maverick.git.GitRepository or maverick.git.AsyncGitRepository
    - DiffStats -> maverick.git.DiffStats
    - CommitInfo -> maverick.git.CommitInfo
"""

from __future__ import annotations

import warnings

from maverick.runners.coderabbit import CodeRabbitRunner
from maverick.runners.command import CommandRunner

# Import git module with deprecation warning suppressed for backward compat
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from maverick.runners.git import CommitInfo, DiffStats, GitResult, GitRunner

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
    "DiffStats",
    "CommitInfo",
    # Preflight validation
    "ValidationResult",
    "PreflightResult",
    "PreflightConfig",
    "PreflightValidator",
    "CustomToolValidator",
    "ValidatableRunner",
    # Runners
    "CommandRunner",
    "GitRunner",
    "GitResult",
    "GitHubCLIRunner",
    "CodeRabbitRunner",
    "ValidationRunner",
]

__version__ = "0.1.0"
