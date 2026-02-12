"""Data models for maverick init command.

This module defines enums, dataclasses, and Pydantic models for project type
detection, preflight validation, and configuration generation.

All enums use str inheritance for JSON/YAML serialization compatibility.
Dataclasses are frozen and use slots for immutability and memory efficiency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml
from pydantic import BaseModel, Field

from maverick.constants import (
    CLAUDE_HAIKU_LATEST,
    CLAUDE_OPUS_LATEST,
    CLAUDE_SONNET_LATEST,
    DEFAULT_MODEL,
    MAX_OUTPUT_TOKENS,
)

__all__ = [
    # Enums
    "ProjectType",
    "DetectionConfidence",
    "PreflightStatus",
    # Constants
    "MARKER_FILE_MAP",
    "VALIDATION_DEFAULTS",
    "PYTHON_DEFAULTS",
    "MODEL_NAME_MAP",
    # Dataclasses
    "ProjectMarker",
    "ValidationCommands",
    "PrerequisiteCheck",
    "GitRemoteInfo",
    "ProjectDetectionResult",
    "InitPreflightResult",
    "InitResult",
    # Pydantic models
    "InitGitHubConfig",
    "InitValidationConfig",
    "InitModelConfig",
    "InitConfig",
    # Functions
    "resolve_model_id",
]


# =============================================================================
# Enums
# =============================================================================


class ProjectType(str, Enum):
    """Supported project types for maverick init detection.

    Each project type has associated marker files and default validation
    commands. The UNKNOWN type is used when detection fails or is ambiguous.

    Attributes:
        PYTHON: Python projects (pyproject.toml, setup.py, requirements.txt).
        NODEJS: Node.js projects (package.json).
        GO: Go projects (go.mod).
        RUST: Rust projects (Cargo.toml).
        ANSIBLE_COLLECTION: Ansible Galaxy collections (galaxy.yml).
        ANSIBLE_PLAYBOOK: Ansible playbook projects (ansible.cfg, requirements.yml).
        UNKNOWN: Fallback when project type cannot be determined.
    """

    PYTHON = "python"
    NODEJS = "nodejs"
    GO = "go"
    RUST = "rust"
    ANSIBLE_COLLECTION = "ansible_collection"
    ANSIBLE_PLAYBOOK = "ansible_playbook"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str) -> ProjectType:
        """Parse project type from string (case-insensitive).

        Normalizes the input by converting to lowercase and replacing
        hyphens and spaces with underscores.

        Args:
            value: String representation of project type.

        Returns:
            Matching ProjectType enum member, or UNKNOWN if not found.

        Examples:
            >>> ProjectType.from_string("python")
            <ProjectType.PYTHON: 'python'>
            >>> ProjectType.from_string("NODEJS")
            <ProjectType.NODEJS: 'nodejs'>
            >>> ProjectType.from_string("ansible-collection")
            <ProjectType.ANSIBLE_COLLECTION: 'ansible_collection'>
            >>> ProjectType.from_string("invalid")
            <ProjectType.UNKNOWN: 'unknown'>
        """
        normalized = value.lower().replace("-", "_").replace(" ", "_")
        try:
            return cls(normalized)
        except ValueError:
            return cls.UNKNOWN


class DetectionConfidence(str, Enum):
    """Confidence level of project type detection.

    Indicates how certain the detection algorithm is about the identified
    project type based on the available marker files and context.

    Attributes:
        HIGH: Single clear project type with strong markers (e.g., Cargo.toml
            for Rust). No ambiguity in detection.
        MEDIUM: Multiple types detected but one is clearly dominant, or
            primary markers are present but secondary markers suggest
            mixed usage.
        LOW: Ambiguous markers present, best-guess detection. User should
            verify the detected type.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PreflightStatus(str, Enum):
    """Status of a preflight validation check.

    Used to report the outcome of prerequisite checks during maverick init
    (e.g., git installed, in a git repository, Claude API key present).

    Attributes:
        PASS: Check completed successfully.
        FAIL: Check failed; init cannot proceed.
        SKIP: Check was skipped (e.g., optional validation or not applicable).
    """

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


# =============================================================================
# Constants
# =============================================================================


MARKER_FILE_MAP: dict[str, tuple[ProjectType, int]] = {
    # Mapping of marker files to (project_type, priority).
    # Lower priority values indicate more definitive markers.
    #
    # Python markers (priority 1-5)
    "pyproject.toml": (ProjectType.PYTHON, 1),
    "setup.py": (ProjectType.PYTHON, 2),
    "setup.cfg": (ProjectType.PYTHON, 3),
    "requirements.txt": (ProjectType.PYTHON, 4),
    "Pipfile": (ProjectType.PYTHON, 5),
    # Node.js markers (priority 1)
    "package.json": (ProjectType.NODEJS, 1),
    # Go markers (priority 1)
    "go.mod": (ProjectType.GO, 1),
    # Rust markers (priority 1)
    "Cargo.toml": (ProjectType.RUST, 1),
    # Ansible markers (priority 1-3)
    "galaxy.yml": (ProjectType.ANSIBLE_COLLECTION, 1),
    "requirements.yml": (ProjectType.ANSIBLE_PLAYBOOK, 2),
    "ansible.cfg": (ProjectType.ANSIBLE_PLAYBOOK, 3),
}
"""Mapping of marker files to project types and detection priorities.

Each entry maps a filename to a tuple of (ProjectType, priority) where:
- ProjectType: The project type associated with this marker file.
- priority: Detection priority (lower = more important/definitive).

When multiple marker files are found, the one with the lowest priority
value takes precedence for determining the primary project type.

Example:
    If both pyproject.toml (priority 1) and requirements.txt (priority 4)
    are found, pyproject.toml is considered the primary marker.
"""


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(frozen=True, slots=True)
class ValidationCommands:
    """Validation commands for a project type.

    Container for the commands used during validation phases.
    All commands are represented as tuples for immutability.

    Attributes:
        sync_cmd: Command for dependency sync (e.g., ("uv", "sync")).
        format_cmd: Command for formatting (e.g., ("ruff", "format", ".")).
        lint_cmd: Command for linting (e.g., ("ruff", "check", "--fix", ".")).
        typecheck_cmd: Command for type checking (e.g., ("mypy", ".")).
        test_cmd: Command for testing (e.g., ("pytest", "-x", "--tb=short")).
    """

    sync_cmd: tuple[str, ...] | None = None
    format_cmd: tuple[str, ...] | None = None
    lint_cmd: tuple[str, ...] | None = None
    typecheck_cmd: tuple[str, ...] | None = None
    test_cmd: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary with command lists (None values preserved).
        """
        return {
            "sync_cmd": list(self.sync_cmd) if self.sync_cmd else None,
            "format_cmd": list(self.format_cmd) if self.format_cmd else None,
            "lint_cmd": list(self.lint_cmd) if self.lint_cmd else None,
            "typecheck_cmd": list(self.typecheck_cmd) if self.typecheck_cmd else None,
            "test_cmd": list(self.test_cmd) if self.test_cmd else None,
        }

    @classmethod
    def for_project_type(cls, project_type: ProjectType) -> ValidationCommands:
        """Get default validation commands for a project type.

        Args:
            project_type: The project type to get commands for.

        Returns:
            ValidationCommands with appropriate defaults.
        """
        return VALIDATION_DEFAULTS.get(project_type, PYTHON_DEFAULTS)


@dataclass(frozen=True, slots=True)
class ProjectMarker:
    """A detected project marker file with optional content.

    Represents a file that indicates project type (e.g., pyproject.toml).

    Attributes:
        file_name: Name of the marker file (e.g., "pyproject.toml").
        file_path: Absolute path to the file.
        project_type: Associated project type.
        content: File content (truncated if large), None if unread.
        priority: Detection priority (lower = higher priority).
    """

    file_name: str
    file_path: str
    project_type: ProjectType
    content: str | None = None
    priority: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of this marker.
        """
        return {
            "file_name": self.file_name,
            "file_path": self.file_path,
            "project_type": self.project_type.value,
            "content": self.content,
            "priority": self.priority,
        }


@dataclass(frozen=True, slots=True)
class PrerequisiteCheck:
    """Result of a single prerequisite check.

    Captures the outcome of validation checks like git installed,
    gh authenticated, API key set, etc.

    Attributes:
        name: Identifier for the check (e.g., "git_installed").
        display_name: Human-readable name (e.g., "Git").
        status: Pass/fail/skip status.
        message: Human-readable result message.
        remediation: Suggested fix if failed (None if passed).
        duration_ms: Time taken for this check in milliseconds.
    """

    name: str
    display_name: str
    status: PreflightStatus
    message: str
    remediation: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of this check.
        """
        return {
            "name": self.name,
            "display_name": self.display_name,
            "status": self.status.value,
            "message": self.message,
            "remediation": self.remediation,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class GitRemoteInfo:
    """Parsed git remote information.

    Contains owner and repo extracted from git remote URL.

    Attributes:
        owner: GitHub owner/organization (None if not parseable).
        repo: Repository name (None if not parseable).
        remote_url: Raw remote URL (None if no remote).
        remote_name: Remote name (default: "origin").
    """

    owner: str | None = None
    repo: str | None = None
    remote_url: str | None = None
    remote_name: str = "origin"

    @property
    def full_name(self) -> str | None:
        """Return owner/repo format if both available.

        Returns:
            "owner/repo" string or None if incomplete.
        """
        if self.owner and self.repo:
            return f"{self.owner}/{self.repo}"
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation including full_name property.
        """
        return {
            "owner": self.owner,
            "repo": self.repo,
            "remote_url": self.remote_url,
            "remote_name": self.remote_name,
            "full_name": self.full_name,
        }


@dataclass(frozen=True, slots=True)
class ProjectDetectionResult:
    """Result of project type detection analysis.

    Contains complete detection results including primary type,
    all detected types, confidence level, and evidence.

    Attributes:
        primary_type: Recommended primary project type.
        detected_types: All detected project types.
        confidence: Detection confidence level.
        findings: Evidence strings explaining detection.
        markers: Detected marker files.
        validation_commands: Recommended validation commands.
        detection_method: "claude" or "markers".
    """

    primary_type: ProjectType
    detected_types: tuple[ProjectType, ...] = field(default_factory=tuple)
    confidence: DetectionConfidence = DetectionConfidence.LOW
    findings: tuple[str, ...] = field(default_factory=tuple)
    markers: tuple[ProjectMarker, ...] = field(default_factory=tuple)
    validation_commands: ValidationCommands = field(default_factory=ValidationCommands)
    detection_method: str = "markers"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of detection result.
        """
        return {
            "primary_type": self.primary_type.value,
            "detected_types": [t.value for t in self.detected_types],
            "confidence": self.confidence.value,
            "findings": list(self.findings),
            "markers": [m.to_dict() for m in self.markers],
            "validation_commands": self.validation_commands.to_dict(),
            "detection_method": self.detection_method,
        }


@dataclass(frozen=True, slots=True)
class InitPreflightResult:
    """Aggregate result of init prerequisite validation.

    Contains all prerequisite check results and summary information.

    Attributes:
        success: True if all critical checks passed.
        checks: Individual check results.
        total_duration_ms: Total validation time.
        failed_checks: Names of failed checks.
        warnings: Non-fatal warning messages.
    """

    success: bool
    checks: tuple[PrerequisiteCheck, ...] = field(default_factory=tuple)
    total_duration_ms: int = 0
    failed_checks: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of preflight result.
        """
        return {
            "success": self.success,
            "checks": [c.to_dict() for c in self.checks],
            "total_duration_ms": self.total_duration_ms,
            "failed_checks": list(self.failed_checks),
            "warnings": list(self.warnings),
        }


# =============================================================================
# Pydantic Models
# =============================================================================


class InitGitHubConfig(BaseModel):
    """GitHub configuration section for generated maverick.yaml.

    Attributes:
        owner: GitHub owner/organization name.
        repo: Repository name.
        default_branch: Default branch name (usually "main").
    """

    owner: str | None = None
    repo: str | None = None
    default_branch: str = "main"


class InitValidationConfig(BaseModel):
    """Validation configuration section for generated maverick.yaml.

    Attributes:
        sync_cmd: Dependency sync command as list of strings.
        format_cmd: Formatting command as list of strings.
        lint_cmd: Linting command as list of strings.
        typecheck_cmd: Type checking command as list of strings.
        test_cmd: Test command as list of strings.
        timeout_seconds: Maximum time per validation command.
        max_errors: Maximum errors to return.
    """

    sync_cmd: list[str] | None = None
    format_cmd: list[str] | None = None
    lint_cmd: list[str] | None = None
    typecheck_cmd: list[str] | None = None
    test_cmd: list[str] | None = None
    timeout_seconds: int = 300
    max_errors: int = 50


# =============================================================================
# Model ID Resolution
# =============================================================================

# Map simple model names to full Claude model IDs
MODEL_NAME_MAP: dict[str, str] = {
    "opus": CLAUDE_OPUS_LATEST,
    "sonnet": CLAUDE_SONNET_LATEST,
    "haiku": CLAUDE_HAIKU_LATEST,
}


def resolve_model_id(model_name: str) -> str:
    """Resolve a simple model name to a full Claude model ID.

    Accepts simple names like "opus", "sonnet", or "haiku" and returns
    the corresponding full model identifier. If the input is already a
    full model ID (starts with "claude-"), it's returned as-is.

    Args:
        model_name: Simple model name (opus/sonnet/haiku) or full model ID.

    Returns:
        Full Claude model identifier.

    Raises:
        ValueError: If model_name is not recognized.

    Examples:
        >>> resolve_model_id("opus")
        'claude-opus-4-5-20251101'

        >>> resolve_model_id("sonnet")
        'claude-sonnet-4-5-20250929'

        >>> resolve_model_id("claude-opus-4-5-20251101")
        'claude-opus-4-5-20251101'

        >>> resolve_model_id("invalid")
        Traceback (most recent call last):
        ...
        ValueError: Unknown model name 'invalid'. ...
    """
    # Normalize input
    normalized = model_name.lower().strip()

    # If it's already a full model ID, return as-is
    if normalized.startswith("claude-"):
        return model_name

    # Look up simple name
    if normalized in MODEL_NAME_MAP:
        return MODEL_NAME_MAP[normalized]

    # Not found
    valid_names = ", ".join(sorted(MODEL_NAME_MAP.keys()))
    raise ValueError(
        f"Unknown model name '{model_name}'. "
        f"Valid names: {valid_names} or full model IDs starting with 'claude-'"
    )


# =============================================================================
# Pydantic Models
# =============================================================================


class InitModelConfig(BaseModel):
    """Model configuration section for generated maverick.yaml.

    Attributes:
        model_id: Claude model identifier.
        max_tokens: Maximum OUTPUT tokens per response (not context window).
            Claude 4.5 models support up to 64K output tokens.
            Context window (input) is 200K tokens (fixed by model).
        temperature: Temperature for generation (0.0 = deterministic).
    """

    model_id: str = DEFAULT_MODEL
    max_tokens: int = MAX_OUTPUT_TOKENS
    temperature: float = 0.0


class InitConfig(BaseModel):
    """Complete configuration generated by maverick init.

    This model represents the full maverick.yaml file structure.

    Attributes:
        project_type: Detected project type (python, rust, ansible_playbook, etc.)
        github: GitHub repository configuration.
        validation: Validation command configuration.
        model: Claude model configuration.
        notifications: Notification settings.
        parallel: Parallel execution limits.
        verbosity: Logging verbosity level.
    """

    project_type: str = Field(
        default="unknown",
        description="Detected project type for skill selection",
    )
    github: InitGitHubConfig = Field(default_factory=InitGitHubConfig)
    validation: InitValidationConfig = Field(default_factory=InitValidationConfig)
    model: InitModelConfig = Field(default_factory=InitModelConfig)
    notifications: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    parallel: dict[str, int] = Field(
        default_factory=lambda: {"max_agents": 3, "max_tasks": 5}
    )
    verbosity: str = "warning"

    def to_yaml(self) -> str:
        """Serialize configuration to YAML string.

        Returns:
            YAML-formatted configuration string.
        """
        return yaml.dump(
            self.model_dump(exclude_none=True),
            default_flow_style=False,
            sort_keys=False,
        )


@dataclass(frozen=True, slots=True)
class InitResult:
    """Complete result of maverick init execution.

    Contains all information about an init command execution.

    Attributes:
        success: True if init completed successfully.
        config_path: Path to generated maverick.yaml.
        preflight: Prerequisite check results.
        detection: Detection result (None if --no-detect).
        git_info: Git remote information.
        config: Generated configuration.
        findings_printed: Whether findings were displayed.
    """

    success: bool
    config_path: str
    preflight: InitPreflightResult
    git_info: GitRemoteInfo
    config: InitConfig
    detection: ProjectDetectionResult | None = None
    findings_printed: bool = False
    jj_initialized: bool = False
    beads_initialized: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of init result.
        """
        return {
            "success": self.success,
            "config_path": self.config_path,
            "preflight": self.preflight.to_dict(),
            "detection": self.detection.to_dict() if self.detection else None,
            "git_info": self.git_info.to_dict(),
            "config": self.config.model_dump(),
            "findings_printed": self.findings_printed,
            "jj_initialized": self.jj_initialized,
            "beads_initialized": self.beads_initialized,
        }


# =============================================================================
# Validation Command Defaults
# =============================================================================


VALIDATION_DEFAULTS: dict[ProjectType, ValidationCommands] = {
    ProjectType.PYTHON: ValidationCommands(
        sync_cmd=("uv", "sync"),
        format_cmd=("ruff", "format", "."),
        lint_cmd=("ruff", "check", "--fix", "."),
        typecheck_cmd=("mypy", "."),
        test_cmd=("pytest", "-x", "--tb=short"),
    ),
    ProjectType.NODEJS: ValidationCommands(
        sync_cmd=("npm", "install"),
        format_cmd=("prettier", "--write", "."),
        lint_cmd=("eslint", "--fix", "."),
        typecheck_cmd=("tsc", "--noEmit"),
        test_cmd=("npm", "test"),
    ),
    ProjectType.GO: ValidationCommands(
        sync_cmd=("go", "mod", "download"),
        format_cmd=("gofmt", "-w", "."),
        lint_cmd=("golangci-lint", "run"),
        typecheck_cmd=None,  # Compiled language
        test_cmd=("go", "test", "./..."),
    ),
    ProjectType.RUST: ValidationCommands(
        sync_cmd=("cargo", "build"),
        format_cmd=("cargo", "fmt"),
        lint_cmd=("cargo", "clippy", "--fix", "--allow-dirty"),
        typecheck_cmd=None,  # Compiled language
        test_cmd=("cargo", "test"),
    ),
    ProjectType.ANSIBLE_COLLECTION: ValidationCommands(
        format_cmd=("yamllint", "."),
        lint_cmd=("ansible-lint",),
        typecheck_cmd=None,
        test_cmd=("molecule", "test"),
    ),
    ProjectType.ANSIBLE_PLAYBOOK: ValidationCommands(
        format_cmd=("yamllint", "."),
        lint_cmd=("ansible-lint",),
        typecheck_cmd=None,
        test_cmd=("ansible-playbook", "--syntax-check", "site.yml"),
    ),
    ProjectType.UNKNOWN: ValidationCommands(
        sync_cmd=("uv", "sync"),
        format_cmd=("ruff", "format", "."),
        lint_cmd=("ruff", "check", "--fix", "."),
        typecheck_cmd=("mypy", "."),
        test_cmd=("pytest", "-x", "--tb=short"),
    ),
}
"""Default validation commands for each project type.

Maps project types to their recommended validation commands.
UNKNOWN type falls back to Python defaults as Maverick is a Python project.
"""

# Convenience alias for Python defaults
PYTHON_DEFAULTS = VALIDATION_DEFAULTS[ProjectType.PYTHON]
