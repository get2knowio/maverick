# Data Model: Subprocess Execution Module

**Feature**: 017-subprocess-runners
**Date**: 2025-12-18

## Overview

This document defines all data entities for the subprocess execution module. All models use frozen dataclasses with `slots=True` for immutability and memory efficiency, following patterns established in `maverick.agents.result`.

> **Design Note**: Collection fields use `tuple[T, ...]` instead of `list[T]` to ensure immutability,
> which is required for frozen dataclasses. This prevents accidental mutation of model instances and
> provides better type safety guarantees.

---

## Core Result Models

### CommandResult

Represents the outcome of a single command execution.

```python
@dataclass(frozen=True, slots=True)
class CommandResult:
    """Result of executing a single command.

    Attributes:
        returncode: Process exit code (0 = success, non-zero = failure).
        stdout: Captured standard output as string.
        stderr: Captured standard error as string.
        duration_ms: Execution time in milliseconds.
        timed_out: True if command was terminated due to timeout.

    Invariants:
        - returncode is always an integer (use -1 for killed processes)
        - duration_ms >= 0
        - If timed_out is True, returncode should be -1
    """
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False

    @property
    def success(self) -> bool:
        """True if command completed successfully (returncode 0, no timeout)."""
        return self.returncode == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Combined stdout and stderr for convenience."""
        if self.stderr:
            return f"{self.stdout}\n{self.stderr}" if self.stdout else self.stderr
        return self.stdout
```

**Source**: FR-002 (capture returncode, stdout, stderr, duration_ms)

---

### StreamLine

Represents a single line from streaming output.

```python
@dataclass(frozen=True, slots=True)
class StreamLine:
    """A single line from streaming command output.

    Attributes:
        content: The line content (without trailing newline).
        stream: Which stream produced this line ('stdout' or 'stderr').
        timestamp_ms: Milliseconds since command start when line was received.
    """
    content: str
    stream: Literal["stdout", "stderr"]
    timestamp_ms: int
```

**Source**: FR-006 (async streaming of stdout lines)

---

## Validation Models

### ValidationStage

Defines a validation step configuration.

```python
@dataclass(frozen=True, slots=True)
class ValidationStage:
    """Configuration for a single validation stage.

    Attributes:
        name: Human-readable stage name (e.g., "format", "lint", "test").
        command: Command as tuple of strings (no shell interpretation).
        fixable: Whether this stage supports automatic fixing.
        fix_command: Command to run when fix is needed (None if not fixable).
        timeout_seconds: Maximum execution time for this stage.

    Invariants:
        - If fixable is True, fix_command should be provided
        - command must have at least one element
        - timeout_seconds > 0
    """
    name: str
    command: tuple[str, ...]
    fixable: bool = False
    fix_command: tuple[str, ...] | None = None
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not self.command:
            raise ValueError("Command list cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("Timeout must be positive")
```

**Source**: FR-008, FR-009 (validation stages, fixable stages)

---

### StageResult

Result of running a single validation stage.

```python
@dataclass(frozen=True, slots=True)
class StageResult:
    """Result of executing a single validation stage.

    Attributes:
        stage_name: Name of the stage that was executed.
        passed: True if stage succeeded (after fix attempts if applicable).
        output: Combined stdout/stderr from the stage command.
        duration_ms: Total time for this stage including fix attempts.
        fix_attempts: Number of fix attempts made (0 if not fixable or passed first try).
        errors: Parsed errors if output matches known format.
    """
    stage_name: str
    passed: bool
    output: str
    duration_ms: int
    fix_attempts: int = 0
    errors: tuple[ParsedError, ...] = field(default_factory=tuple)
```

**Source**: FR-008, FR-010 (stage results, fix attempts)

---

### ValidationOutput

Aggregated results from all validation stages.

```python
@dataclass(frozen=True, slots=True)
class ValidationOutput:
    """Aggregated validation results across all stages.

    Attributes:
        success: True only when ALL stages passed.
        stages: Individual results for each stage.
        total_duration_ms: Total time for all stages.
        stages_run: Number of stages that were executed.
        stages_passed: Number of stages that passed.
        stages_failed: Number of stages that failed.
    """
    success: bool
    stages: tuple[StageResult, ...]
    total_duration_ms: int

    @property
    def stages_run(self) -> int:
        return len(self.stages)

    @property
    def stages_passed(self) -> int:
        return sum(1 for s in self.stages if s.passed)

    @property
    def stages_failed(self) -> int:
        return sum(1 for s in self.stages if not s.passed)
```

**Source**: FR-014 (overall success only when all stages pass)

---

### ParsedError

Structured error extracted from command output.

```python
@dataclass(frozen=True, slots=True)
class ParsedError:
    """Structured error parsed from tool output.

    Attributes:
        file: Path to the file containing the error (relative to cwd).
        line: Line number where error occurs (1-indexed).
        column: Column number if available, None otherwise.
        message: Human-readable error message.
        severity: Error severity ('error', 'warning', 'note') if available.
        code: Tool-specific error code (e.g., 'E501', 'type-arg').
    """
    file: str
    line: int
    message: str
    column: int | None = None
    severity: str | None = None
    code: str | None = None
```

**Source**: FR-011, FR-012, FR-013 (parsed error data)

---

## GitHub Models

### GitHubIssue

Represents a GitHub issue.

```python
@dataclass(frozen=True, slots=True)
class GitHubIssue:
    """GitHub issue representation.

    Attributes:
        number: Issue number.
        title: Issue title.
        body: Issue body/description (may be empty).
        labels: Tuple of label names.
        state: Issue state ('open' or 'closed').
        assignees: Tuple of assignee usernames.
        url: Full URL to the issue.
    """
    number: int
    title: str
    body: str
    labels: tuple[str, ...]
    state: str
    assignees: tuple[str, ...]
    url: str

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError("Issue number must be positive")
        if self.state not in ("open", "closed"):
            raise ValueError(f"Invalid state: {self.state}")
```

**Source**: FR-015 (fetch individual issues with all metadata)

---

### PullRequest

Represents a GitHub pull request.

```python
@dataclass(frozen=True, slots=True)
class PullRequest:
    """GitHub pull request representation.

    Attributes:
        number: PR number.
        title: PR title.
        body: PR description.
        state: PR state ('open', 'closed', 'merged').
        url: Full URL to the PR.
        head_branch: Source branch name.
        base_branch: Target branch name.
        mergeable: True if PR can be merged, False if conflicts, None if unknown.
        draft: True if PR is in draft state.
    """
    number: int
    title: str
    body: str
    state: str
    url: str
    head_branch: str
    base_branch: str
    mergeable: bool | None
    draft: bool = False

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError("PR number must be positive")
```

**Source**: FR-017, FR-018 (create/fetch PRs with metadata)

---

### CheckStatus

CI check result for a pull request.

```python
@dataclass(frozen=True, slots=True)
class CheckStatus:
    """CI check status for a pull request.

    Attributes:
        name: Check name (e.g., 'tests', 'lint', 'build').
        status: Current status ('queued', 'in_progress', 'completed').
        conclusion: Final result if completed ('success', 'failure', 'skipped', etc.).
        url: URL to check details (may be None).
    """
    name: str
    status: str
    conclusion: str | None = None
    url: str | None = None

    @property
    def passed(self) -> bool:
        """True if check completed successfully."""
        return self.status == "completed" and self.conclusion == "success"

    @property
    def pending(self) -> bool:
        """True if check is still running."""
        return self.status in ("queued", "in_progress")
```

**Source**: FR-019 (fetch PR check statuses)

---

## CodeRabbit Models

### CodeRabbitFinding

Individual finding from CodeRabbit review.

```python
@dataclass(frozen=True, slots=True)
class CodeRabbitFinding:
    """Individual finding from CodeRabbit review.

    Attributes:
        file: Path to the file with the finding.
        line: Line number (1-indexed).
        severity: Finding severity ('error', 'warning', 'info', 'suggestion').
        message: Description of the issue.
        suggestion: Suggested fix if available.
        category: Finding category (e.g., 'security', 'performance', 'style').
    """
    file: str
    line: int
    severity: str
    message: str
    suggestion: str | None = None
    category: str | None = None
```

**Source**: FR-022 (structured findings)

---

### CodeRabbitResult

Aggregated CodeRabbit review results.

```python
@dataclass(frozen=True, slots=True)
class CodeRabbitResult:
    """Results from a CodeRabbit review.

    Attributes:
        findings: Tuple of individual findings.
        summary: Human-readable summary of the review.
        raw_output: Original CLI output for debugging.
        warnings: Any warnings (e.g., 'CodeRabbit not installed').
    """
    findings: tuple[CodeRabbitFinding, ...]
    summary: str = ""
    raw_output: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_findings(self) -> bool:
        return len(self.findings) > 0

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")
```

**Source**: FR-022, FR-025 (review results with raw output)

---

## Exception Classes

New exceptions to add to `maverick.exceptions`:

```python
class RunnerError(MaverickError):
    """Base exception for runner failures."""
    pass

class WorkingDirectoryError(RunnerError):
    """Working directory does not exist or is not accessible.

    Attributes:
        path: The path that was not found.
    """
    def __init__(self, message: str, path: Path | None = None) -> None:
        self.path = path
        super().__init__(message)

class CommandTimeoutError(RunnerError):
    """Command execution exceeded timeout.

    Attributes:
        timeout_seconds: The timeout that was exceeded.
        command: The command that timed out.
    """
    def __init__(
        self,
        message: str,
        timeout_seconds: float,
        command: tuple[str, ...] | None = None
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.command = command
        super().__init__(message)

class CommandNotFoundError(RunnerError):
    """Executable not found in PATH.

    Attributes:
        executable: The command that was not found.
    """
    def __init__(self, message: str, executable: str | None = None) -> None:
        self.executable = executable
        super().__init__(message)

class GitHubCLINotFoundError(RunnerError):
    """GitHub CLI (gh) is not installed.

    Provides installation instructions in the message.
    """
    def __init__(self) -> None:
        super().__init__(
            "GitHub CLI (gh) not installed. Install from: https://cli.github.com/"
        )

class GitHubAuthError(RunnerError):
    """GitHub CLI is not authenticated.

    Provides authentication instructions in the message.
    """
    def __init__(self) -> None:
        super().__init__(
            "GitHub CLI not authenticated. Run: gh auth login"
        )
```

**Source**: FR-005, FR-020, FR-021 (error handling requirements)

---

## Entity Relationships

```
CommandRunner
    └── produces → CommandResult
    └── streams → StreamLine*

ValidationRunner
    └── uses → ValidationStage*
    └── produces → ValidationOutput
        └── contains → StageResult*
            └── contains → ParsedError*

GitHubCLIRunner
    └── produces → GitHubIssue | PullRequest | CheckStatus

CodeRabbitRunner
    └── produces → CodeRabbitResult
        └── contains → CodeRabbitFinding*
```

---

## State Transitions

### ValidationStage Execution

```
PENDING → RUNNING → PASSED
                  └→ FAILED → FIXING → RUNNING → PASSED
                                               └→ FAILED (exhausted attempts)
```

### CommandResult States

```
Command started
    └→ Completed (returncode captured)
    └→ Timed out (SIGTERM → SIGKILL)
    └→ Not found (FileNotFoundError)
```

---

## Validation Rules Summary

| Entity | Field | Rule |
|--------|-------|------|
| CommandResult | duration_ms | >= 0 |
| ValidationStage | command | Non-empty tuple |
| ValidationStage | timeout_seconds | > 0 |
| GitHubIssue | number | > 0 |
| GitHubIssue | state | 'open' or 'closed' |
| PullRequest | number | > 0 |
| ParsedError | line | > 0 |
