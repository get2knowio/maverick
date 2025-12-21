"""Data models for subprocess runners and validation workflows.

This module defines immutable, frozen dataclasses for representing:
- Command execution results (CommandResult, StreamLine)
- Validation stages and results (ValidationStage, StageResult, ValidationOutput)
- GitHub entities (GitHubIssue, PullRequest, CheckStatus)
- Code review results (CodeRabbitFinding, CodeRabbitResult)
- Parsed errors (ParsedError)

All models use frozen dataclasses with slots for memory efficiency and immutability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
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
]


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Result of executing a single command.

    Attributes:
        returncode: Exit code from the command (0 = success).
        stdout: Standard output captured from the command.
        stderr: Standard error captured from the command.
        duration_ms: Execution time in milliseconds.
        timed_out: True if the command exceeded its timeout limit.
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


@dataclass(frozen=True, slots=True)
class StreamLine:
    """A single line from streaming command output.

    Attributes:
        content: The line content without trailing newline.
        stream: Which output stream this line came from.
        timestamp_ms: Milliseconds since command start when line was received.
    """

    content: str
    stream: Literal["stdout", "stderr"]
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class ParsedError:
    """Structured error parsed from tool output.

    Attributes:
        file: Path to the file containing the error.
        line: Line number where the error occurred.
        message: Human-readable error message.
        column: Column number where the error occurred (if available).
        severity: Error severity level (e.g., "error", "warning").
        code: Error code or identifier (e.g., "E501" for linters).
    """

    file: str
    line: int
    message: str
    column: int | None = None
    severity: str | None = None
    code: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationStage:
    """Configuration for a single validation stage.

    Attributes:
        name: Human-readable name for this stage (e.g., "Ruff format check").
        command: Command and arguments to execute as a tuple.
        fixable: True if this stage can be auto-fixed.
        fix_command: Command to run for auto-fixing (if fixable is True).
        timeout_seconds: Maximum execution time before killing the process.

    Raises:
        ValueError: If command is empty or timeout is non-positive.

    Example:
        >>> stage = ValidationStage(
        ...     name="lint",
        ...     command=("ruff", "check", "."),
        ...     fixable=True,
        ...     fix_command=("ruff", "check", "--fix", "."),
        ... )
        >>> stage.name
        'lint'
    """

    name: str
    command: tuple[str, ...]
    fixable: bool = False
    fix_command: tuple[str, ...] | None = None
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.command:
            raise ValueError("Command tuple cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("Timeout must be positive")


@dataclass(frozen=True, slots=True)
class StageResult:
    """Result of executing a single validation stage.

    Attributes:
        stage_name: Name of the validation stage that was executed.
        passed: True if the stage completed successfully.
        output: Combined stdout/stderr from the stage execution.
        duration_ms: Execution time in milliseconds.
        fix_attempts: Number of auto-fix attempts made (0 if not fixable).
        errors: Structured errors parsed from the output.
    """

    stage_name: str
    passed: bool
    output: str
    duration_ms: int
    fix_attempts: int = 0
    errors: tuple[ParsedError, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationOutput:
    """Aggregated validation results across all stages.

    Attributes:
        success: True if all stages passed.
        stages: Results from each validation stage in execution order.
        total_duration_ms: Total execution time across all stages.

    Example:
        >>> result = StageResult(
        ...     stage_name="lint",
        ...     passed=True,
        ...     output="All checks passed!",
        ...     duration_ms=150
        ... )
        >>> output = ValidationOutput(
        ...     success=True,
        ...     stages=(result,),
        ...     total_duration_ms=150
        ... )
        >>> output.stages_passed
        1
    """

    success: bool
    stages: tuple[StageResult, ...]
    total_duration_ms: int

    @property
    def stages_run(self) -> int:
        """Total number of stages executed."""
        return len(self.stages)

    @property
    def stages_passed(self) -> int:
        """Number of stages that passed."""
        return sum(1 for s in self.stages if s.passed)

    @property
    def stages_failed(self) -> int:
        """Number of stages that failed."""
        return sum(1 for s in self.stages if not s.passed)


@dataclass(frozen=True, slots=True)
class GitHubIssue:
    """GitHub issue representation.

    Attributes:
        number: GitHub issue number (must be positive).
        title: Issue title.
        body: Issue description/body text.
        labels: Issue labels as a tuple.
        state: Issue state ("open" or "closed").
        assignees: GitHub usernames assigned to this issue.
        url: Full URL to the issue on GitHub.

    Raises:
        ValueError: If number is not positive or state is invalid.

    Example:
        >>> issue = GitHubIssue(
        ...     number=42,
        ...     title="Fix bugs",
        ...     body="Description...",
        ...     labels=("bug",),
        ...     state="open",
        ...     assignees=("octocat",),
        ...     url="https://github.com/org/repo/issues/42"
        ... )
        >>> issue.number
        42
    """

    number: int
    title: str
    body: str
    labels: tuple[str, ...]
    state: str
    assignees: tuple[str, ...]
    url: str

    def __post_init__(self) -> None:
        """Validate issue data after initialization."""
        if self.number < 1:
            raise ValueError("Issue number must be positive")
        normalized_state = self.state.lower()
        valid_states = {"open", "closed"}
        if normalized_state not in valid_states:
            raise ValueError(f"Invalid state: {self.state}")


@dataclass(frozen=True, slots=True)
class PullRequest:
    """GitHub pull request representation.

    Attributes:
        number: PR number (must be positive).
        title: PR title.
        body: PR description/body text.
        state: PR state (e.g., "open", "closed", "merged").
        url: Full URL to the PR on GitHub.
        head_branch: Source branch being merged from.
        base_branch: Target branch being merged into.
        mergeable: True if PR can be merged (None if unknown).
        draft: True if PR is marked as draft.

    Raises:
        ValueError: If number is not positive.
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
        """Validate PR data after initialization."""
        if self.number < 1:
            raise ValueError("PR number must be positive")


@dataclass(frozen=True, slots=True)
class CheckStatus:
    """CI check status for a pull request.

    Attributes:
        name: Name of the CI check (e.g., "test", "build").
        status: Current status ("queued", "in_progress", "completed").
        conclusion: Final result if completed ("success", "failure", etc.).
        url: URL to view check details (if available).
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


@dataclass(frozen=True, slots=True)
class CodeRabbitFinding:
    """Individual finding from CodeRabbit review.

    Attributes:
        file: Path to the file with the finding.
        line: Line number of the finding.
        severity: Severity level ("error", "warning", "info").
        message: Description of the finding.
        suggestion: Suggested fix or improvement (if available).
        category: Finding category (e.g., "security", "style").
    """

    file: str
    line: int
    severity: str
    message: str
    suggestion: str | None = None
    category: str | None = None


@dataclass(frozen=True, slots=True)
class CodeRabbitResult:
    """Results from a CodeRabbit review.

    Attributes:
        findings: All findings from the review as a tuple.
        summary: High-level summary of the review.
        raw_output: Complete raw output from CodeRabbit.
        warnings: Non-critical warnings encountered during review.

    Example:
        >>> finding = CodeRabbitFinding(
        ...     file="src/main.py",
        ...     line=10,
        ...     severity="error",
        ...     message="Syntax error"
        ... )
        >>> result = CodeRabbitResult(
        ...     findings=(finding,),
        ...     summary="Found 1 error"
        ... )
        >>> result.error_count
        1
    """

    findings: tuple[CodeRabbitFinding, ...]
    summary: str = ""
    raw_output: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def has_findings(self) -> bool:
        """True if the review produced any findings."""
        return len(self.findings) > 0

    @property
    def error_count(self) -> int:
        """Number of error-level findings."""
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warning_count(self) -> int:
        """Number of warning-level findings."""
        return sum(1 for f in self.findings if f.severity == "warning")
