"""Subprocess execution module with async command runners."""

from __future__ import annotations

from maverick.runners.coderabbit import CodeRabbitRunner
from maverick.runners.command import CommandRunner
from maverick.runners.git import GitResult, GitRunner
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
    # Runners
    "CommandRunner",
    "GitRunner",
    "GitResult",
    "GitHubCLIRunner",
    "CodeRabbitRunner",
    "ValidationRunner",
]

__version__ = "0.1.0"
