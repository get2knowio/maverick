# Data Model: Maverick Init

**Feature**: 028-maverick-init | **Date**: 2025-12-29

## Overview

This document defines the data models, entities, and their relationships for the unified `maverick init` command with Claude-powered project detection.

---

## Entities

### 1. ProjectType (Enum)

Enumeration of supported project types for detection and configuration generation.

```python
from enum import Enum

class ProjectType(str, Enum):
    """Supported project types for maverick init detection."""

    PYTHON = "python"
    NODEJS = "nodejs"
    GO = "go"
    RUST = "rust"
    ANSIBLE_COLLECTION = "ansible_collection"
    ANSIBLE_PLAYBOOK = "ansible_playbook"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str) -> "ProjectType":
        """Parse project type from string (case-insensitive)."""
        normalized = value.lower().replace("-", "_").replace(" ", "_")
        try:
            return cls(normalized)
        except ValueError:
            return cls.UNKNOWN
```

**Spec Reference**: FR-012 (`--type` flag values)

---

### 2. DetectionConfidence (Enum)

Confidence level for project type detection results.

```python
from enum import Enum

class DetectionConfidence(str, Enum):
    """Confidence level of project type detection."""

    HIGH = "high"      # Single clear project type, strong markers
    MEDIUM = "medium"  # Multiple types detected, one dominant
    LOW = "low"        # Ambiguous markers, best-guess detection
```

**Spec Reference**: Key Entity "ProjectDetectionResult"

---

### 3. PreflightStatus (Enum)

Status of individual preflight check results.

```python
from enum import Enum

class PreflightStatus(str, Enum):
    """Status of a preflight validation check."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"  # Check skipped (e.g., optional validation)
```

**Spec Reference**: Key Entity "PreflightResult"

---

### 4. ProjectMarker (Dataclass)

Represents a detected project marker file and its content.

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ProjectMarker:
    """A detected project marker file with optional content."""

    file_name: str          # e.g., "pyproject.toml"
    file_path: str          # Absolute path to the file
    project_type: ProjectType  # Associated project type
    content: str | None     # File content (truncated if large), None if unread
    priority: int           # Detection priority (lower = higher priority)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "file_path": self.file_path,
            "project_type": self.project_type.value,
            "content": self.content,
            "priority": self.priority,
        }
```

**Validation Rules**:
- `file_name` must be non-empty
- `file_path` must be an absolute path
- `content` truncated to 2000 characters for Claude context

---

### 5. ProjectDetectionResult (Dataclass)

Complete result of project type detection, including Claude's analysis.

```python
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class ProjectDetectionResult:
    """Result of project type detection analysis."""

    primary_type: ProjectType                    # Recommended primary type
    detected_types: tuple[ProjectType, ...]      # All detected types
    confidence: DetectionConfidence              # Detection confidence
    findings: tuple[str, ...]                    # Evidence strings
    markers: tuple[ProjectMarker, ...]           # Detected marker files
    validation_commands: ValidationCommands      # Recommended commands
    detection_method: str                        # "claude" or "markers"

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_type": self.primary_type.value,
            "detected_types": [t.value for t in self.detected_types],
            "confidence": self.confidence.value,
            "findings": list(self.findings),
            "markers": [m.to_dict() for m in self.markers],
            "validation_commands": self.validation_commands.to_dict(),
            "detection_method": self.detection_method,
        }
```

**Spec Reference**: Key Entity "ProjectDetectionResult", FR-007, FR-010

**Validation Rules**:
- `primary_type` must be in `detected_types` if detected_types is non-empty
- `findings` must be non-empty for HIGH confidence
- `detection_method` must be "claude" or "markers"

---

### 6. ValidationCommands (Dataclass)

Container for project validation commands.

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ValidationCommands:
    """Validation commands for a project type."""

    format_cmd: tuple[str, ...] | None     # e.g., ("ruff", "format", ".")
    lint_cmd: tuple[str, ...] | None       # e.g., ("ruff", "check", "--fix", ".")
    typecheck_cmd: tuple[str, ...] | None  # e.g., ("mypy", ".")
    test_cmd: tuple[str, ...] | None       # e.g., ("pytest", "-x", "--tb=short")

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_cmd": list(self.format_cmd) if self.format_cmd else None,
            "lint_cmd": list(self.lint_cmd) if self.lint_cmd else None,
            "typecheck_cmd": list(self.typecheck_cmd) if self.typecheck_cmd else None,
            "test_cmd": list(self.test_cmd) if self.test_cmd else None,
        }

    @classmethod
    def for_project_type(cls, project_type: ProjectType) -> "ValidationCommands":
        """Get default validation commands for a project type."""
        return VALIDATION_DEFAULTS.get(project_type, PYTHON_DEFAULTS)
```

**Spec Reference**: FR-008

---

### 7. PrerequisiteCheck (Dataclass)

Result of a single prerequisite validation check.

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class PrerequisiteCheck:
    """Result of a single prerequisite check."""

    name: str                          # e.g., "git_installed"
    display_name: str                  # e.g., "Git"
    status: PreflightStatus            # pass/fail/skip
    message: str                       # Human-readable result
    remediation: str | None            # Suggested fix if failed
    duration_ms: int                   # Time taken for check

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "status": self.status.value,
            "message": self.message,
            "remediation": self.remediation,
            "duration_ms": self.duration_ms,
        }
```

**Spec Reference**: Key Entity "PreflightResult", FR-001 to FR-005

---

### 8. InitPreflightResult (Dataclass)

Aggregate result of all prerequisite checks for init command.

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class InitPreflightResult:
    """Aggregate result of init prerequisite validation."""

    success: bool                              # All critical checks passed
    checks: tuple[PrerequisiteCheck, ...]      # Individual check results
    total_duration_ms: int                     # Total validation time
    failed_checks: tuple[str, ...]             # Names of failed checks
    warnings: tuple[str, ...]                  # Non-fatal warnings

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "checks": [c.to_dict() for c in self.checks],
            "total_duration_ms": self.total_duration_ms,
            "failed_checks": list(self.failed_checks),
            "warnings": list(self.warnings),
        }
```

**Spec Reference**: Key Entity "PreflightResult"

---

### 9. GitRemoteInfo (Dataclass)

Parsed git remote URL information.

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class GitRemoteInfo:
    """Parsed git remote information."""

    owner: str | None          # GitHub owner/organization
    repo: str | None           # Repository name
    remote_url: str | None     # Raw remote URL
    remote_name: str           # Remote name (default: "origin")

    @property
    def full_name(self) -> str | None:
        """Return owner/repo format if both available."""
        if self.owner and self.repo:
            return f"{self.owner}/{self.repo}"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "repo": self.repo,
            "remote_url": self.remote_url,
            "remote_name": self.remote_name,
            "full_name": self.full_name,
        }
```

**Spec Reference**: FR-006

---

### 10. InitConfig (Pydantic Model)

Generated configuration for maverick.yaml.

```python
from pydantic import BaseModel, Field

class InitGitHubConfig(BaseModel):
    """GitHub configuration section."""

    owner: str | None = None
    repo: str | None = None
    default_branch: str = "main"


class InitValidationConfig(BaseModel):
    """Validation configuration section."""

    format_cmd: list[str] | None = None
    lint_cmd: list[str] | None = None
    typecheck_cmd: list[str] | None = None
    test_cmd: list[str] | None = None
    timeout_seconds: int = 300
    max_errors: int = 50


class InitModelConfig(BaseModel):
    """Model configuration section."""

    model_id: str = "claude-sonnet-4-20250514"
    max_tokens: int = 8192
    temperature: float = 0.0


class InitConfig(BaseModel):
    """Complete configuration generated by maverick init."""

    github: InitGitHubConfig = Field(default_factory=InitGitHubConfig)
    validation: InitValidationConfig = Field(default_factory=InitValidationConfig)
    model: InitModelConfig = Field(default_factory=InitModelConfig)
    notifications: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    parallel: dict[str, int] = Field(default_factory=lambda: {"max_agents": 3, "max_tasks": 5})
    verbosity: str = "warning"

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        import yaml
        return yaml.dump(self.model_dump(exclude_none=True), default_flow_style=False)
```

**Spec Reference**: Key Entity "MaverickConfig", FR-009

---

### 11. InitResult (Dataclass)

Complete result of the init command execution.

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class InitResult:
    """Complete result of maverick init execution."""

    success: bool                           # Init completed successfully
    config_path: str                        # Path to generated maverick.yaml
    preflight: InitPreflightResult          # Prerequisite check results
    detection: ProjectDetectionResult | None  # Detection result (None if --no-detect)
    git_info: GitRemoteInfo                 # Git remote information
    config: InitConfig                      # Generated configuration
    findings_printed: bool                  # Whether findings were displayed

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "config_path": self.config_path,
            "preflight": self.preflight.to_dict(),
            "detection": self.detection.to_dict() if self.detection else None,
            "git_info": self.git_info.to_dict(),
            "config": self.config.model_dump(),
            "findings_printed": self.findings_printed,
        }
```

---

## Constants

### Marker File Mappings

```python
MARKER_FILE_MAP: dict[str, tuple[ProjectType, int]] = {
    # (project_type, priority) - lower priority = more important
    "pyproject.toml": (ProjectType.PYTHON, 1),
    "setup.py": (ProjectType.PYTHON, 2),
    "setup.cfg": (ProjectType.PYTHON, 3),
    "requirements.txt": (ProjectType.PYTHON, 4),
    "Pipfile": (ProjectType.PYTHON, 5),
    "package.json": (ProjectType.NODEJS, 1),
    "go.mod": (ProjectType.GO, 1),
    "Cargo.toml": (ProjectType.RUST, 1),
    "galaxy.yml": (ProjectType.ANSIBLE_COLLECTION, 1),
    "requirements.yml": (ProjectType.ANSIBLE_PLAYBOOK, 2),
    "ansible.cfg": (ProjectType.ANSIBLE_PLAYBOOK, 3),
}
```

### Validation Command Defaults

```python
VALIDATION_DEFAULTS: dict[ProjectType, ValidationCommands] = {
    ProjectType.PYTHON: ValidationCommands(
        format_cmd=("ruff", "format", "."),
        lint_cmd=("ruff", "check", "--fix", "."),
        typecheck_cmd=("mypy", "."),
        test_cmd=("pytest", "-x", "--tb=short"),
    ),
    ProjectType.NODEJS: ValidationCommands(
        format_cmd=("prettier", "--write", "."),
        lint_cmd=("eslint", "--fix", "."),
        typecheck_cmd=("tsc", "--noEmit"),
        test_cmd=("npm", "test"),
    ),
    ProjectType.GO: ValidationCommands(
        format_cmd=("gofmt", "-w", "."),
        lint_cmd=("golangci-lint", "run"),
        typecheck_cmd=None,  # Compiled language
        test_cmd=("go", "test", "./..."),
    ),
    ProjectType.RUST: ValidationCommands(
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
        format_cmd=("ruff", "format", "."),
        lint_cmd=("ruff", "check", "--fix", "."),
        typecheck_cmd=("mypy", "."),
        test_cmd=("pytest", "-x", "--tb=short"),
    ),
}

# Alias for convenience
PYTHON_DEFAULTS = VALIDATION_DEFAULTS[ProjectType.PYTHON]
```

---

## Relationships

```
InitResult
├── InitPreflightResult
│   └── PrerequisiteCheck[]
├── ProjectDetectionResult
│   ├── ProjectType (primary)
│   ├── ProjectType[] (detected)
│   ├── ProjectMarker[]
│   └── ValidationCommands
├── GitRemoteInfo
└── InitConfig
    ├── InitGitHubConfig
    ├── InitValidationConfig
    └── InitModelConfig
```

---

## State Transitions

### Init Command Flow

```
[Start]
    │
    ▼
┌─────────────────┐
│  Preflight      │  ──(any fail)──▶ [Error Exit]
│  Validation     │
└────────┬────────┘
         │ (all pass)
         ▼
┌─────────────────┐
│  Git Remote     │  ──(no remote)──▶ [Warning: owner/repo null]
│  Parsing        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Project Type   │  ──(--no-detect)──▶ [Use Python defaults]
│  Detection      │  ──(--type X)────▶ [Use type X defaults]
└────────┬────────┘
         │ (Claude detection)
         ▼
┌─────────────────┐
│  Print          │
│  Findings       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Generate       │  ──(exists + no --force)──▶ [Error Exit]
│  Config         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Write          │
│  maverick.yaml  │
└────────┬────────┘
         │
         ▼
    [Success]
```

---

## File Locations

| Entity | Module |
|--------|--------|
| ProjectType | `src/maverick/init/models.py` |
| DetectionConfidence | `src/maverick/init/models.py` |
| PreflightStatus | `src/maverick/init/models.py` |
| ProjectMarker | `src/maverick/init/models.py` |
| ProjectDetectionResult | `src/maverick/init/models.py` |
| ValidationCommands | `src/maverick/init/models.py` |
| PrerequisiteCheck | `src/maverick/init/models.py` |
| InitPreflightResult | `src/maverick/init/models.py` |
| GitRemoteInfo | `src/maverick/init/models.py` |
| InitConfig | `src/maverick/init/models.py` |
| InitResult | `src/maverick/init/models.py` |
| MARKER_FILE_MAP | `src/maverick/init/detector.py` |
| VALIDATION_DEFAULTS | `src/maverick/init/models.py` |
