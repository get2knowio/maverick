"""Maverick exception hierarchy.

This package organizes all Maverick exceptions into domain-specific modules
while maintaining backward compatibility with the original flat structure.

All exceptions can be imported from this package:
    from maverick.exceptions import AgentError, GitError, WorkflowError
"""

from __future__ import annotations

# Agent-related exceptions
from maverick.exceptions.agent import (
    AgentError,
    AgentNotFoundError,
    CircuitBreakerError,
    CLINotFoundError,
    DuplicateAgentError,
    GeneratorError,
    InvalidToolError,
    MalformedResponseError,
    MaverickTimeoutError,
    NetworkError,
    ProcessError,
    StreamingError,
    TaskParseError,
)

# Base exception
from maverick.exceptions.base import MaverickError

# Bead-related exceptions
from maverick.exceptions.beads import (
    BeadCreationError,
    BeadDependencyError,
    BeadError,
    SpecKitParseError,
)

# Configuration exceptions
from maverick.exceptions.config import ConfigError

# Git-related exceptions
from maverick.exceptions.git import (
    BranchExistsError,
    CheckoutConflictError,
    GitError,
    GitNotFoundError,
    GitToolsError,
    MergeConflictError,
    NoStashError,
    NotARepositoryError,
    NothingToCommitError,
    PushRejectedError,
)

# GitHub-related exceptions
from maverick.exceptions.github import (
    GitHubAuthError,
    GitHubCLINotFoundError,
    GitHubError,
    GitHubToolsError,
)

# Hook-related exceptions
from maverick.exceptions.hooks import HookConfigError, HookError, SafetyHookError

# Init-related exceptions
from maverick.exceptions.init import (
    AnthropicAPIError,
    ConfigExistsError,
    ConfigWriteError,
    DetectionError,
    InitError,
    PrerequisiteError,
)

# Preflight validation exceptions
from maverick.exceptions.preflight import PreflightValidationError

# Runner-related exceptions
from maverick.exceptions.runner import (
    CommandNotFoundError,
    CommandTimeoutError,
    RunnerError,
    WorkingDirectoryError,
)

# Validation-related exceptions
from maverick.exceptions.validation import (
    MaverickValidationError,
    NotificationToolsError,
    ValidationToolsError,
)

# Workflow-related exceptions
from maverick.exceptions.workflow import (
    DuplicateStepNameError,
    StagesNotFoundError,
    WorkflowError,
)

__all__ = [
    # Base
    "MaverickError",
    # Beads
    "BeadCreationError",
    "BeadDependencyError",
    "BeadError",
    "SpecKitParseError",
    # Agent
    "AgentError",
    "AgentNotFoundError",
    "CircuitBreakerError",
    "CLINotFoundError",
    "DuplicateAgentError",
    "GeneratorError",
    "InvalidToolError",
    "MalformedResponseError",
    "MaverickTimeoutError",
    "NetworkError",
    "ProcessError",
    "StreamingError",
    "TaskParseError",
    # Config
    "ConfigError",
    # Git
    "BranchExistsError",
    "CheckoutConflictError",
    "GitError",
    "GitNotFoundError",
    "GitToolsError",
    "MergeConflictError",
    "NoStashError",
    "NothingToCommitError",
    "NotARepositoryError",
    "PushRejectedError",
    # GitHub
    "GitHubAuthError",
    "GitHubCLINotFoundError",
    "GitHubError",
    "GitHubToolsError",
    # Hooks
    "HookConfigError",
    "HookError",
    "SafetyHookError",
    # Init
    "AnthropicAPIError",
    "ConfigExistsError",
    "ConfigWriteError",
    "DetectionError",
    "InitError",
    "PrerequisiteError",
    # Preflight
    "PreflightValidationError",
    # Runner
    "CommandNotFoundError",
    "CommandTimeoutError",
    "RunnerError",
    "WorkingDirectoryError",
    # Validation
    "MaverickValidationError",
    "NotificationToolsError",
    "ValidationToolsError",
    # Workflow
    "DuplicateStepNameError",
    "StagesNotFoundError",
    "WorkflowError",
]
