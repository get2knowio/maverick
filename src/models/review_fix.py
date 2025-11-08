"""Data models for automated review and fix loop.

This module defines the data structures for orchestrating CodeRabbit reviews
and OpenCode fix attempts within Temporal activities.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


# Type aliases for clarity
ReviewOutcomeStatus = Literal["clean", "fixed", "failed"]
IssueSeverity = Literal["blocker", "major", "minor"]


@dataclass
class RetryMetadata:
    """Records previous attempt context to support idempotent retries.

    Invariants:
        - previous_fingerprint must be exactly 64 hex characters
        - attempt_counter must be non-negative
        - last_status must be a valid outcome status
    """

    previous_fingerprint: str
    attempt_counter: int
    last_status: ReviewOutcomeStatus
    artifacts_path: str | None = None

    def __post_init__(self) -> None:
        """Validate retry metadata invariants."""
        if len(self.previous_fingerprint) != 64:
            raise ValueError(f"previous_fingerprint must be 64 hex chars, got {len(self.previous_fingerprint)}")
        if not all(c in "0123456789abcdef" for c in self.previous_fingerprint):
            raise ValueError("previous_fingerprint must contain only hex characters")
        if self.attempt_counter < 0:
            raise ValueError(f"attempt_counter must be >= 0, got {self.attempt_counter}")

    @classmethod
    def from_outcome(
        cls,
        outcome: "ReviewLoopOutcome",
        attempt_counter: int = 1,
    ) -> "RetryMetadata":
        """Create RetryMetadata from a previous ReviewLoopOutcome.

        Args:
            outcome: Previous outcome to create retry metadata from
            attempt_counter: Current attempt number (default: 1 for first retry)

        Returns:
            RetryMetadata instance for the next retry attempt
        """
        return cls(
            previous_fingerprint=outcome.fingerprint,
            attempt_counter=attempt_counter,
            last_status=outcome.status,
            artifacts_path=outcome.artifacts_path or None,
        )


@dataclass
class ReviewLoopInput:
    """Activity input describing the target branch run context.

    Invariants:
        - branch_ref must be non-empty
        - commit_range items must be valid commit SHAs (7-40 hex chars)
        - implementation_summary, if provided, must be <= 2000 characters
        - validation_command, if provided, must start with "uv"
    """

    branch_ref: str
    enable_fixes: bool
    commit_range: list[str] = field(default_factory=list)
    implementation_summary: str | None = None
    validation_command: list[str] | None = None
    retry_metadata: RetryMetadata | None = None

    def __post_init__(self) -> None:
        """Validate input invariants."""
        if not self.branch_ref or not self.branch_ref.strip():
            raise ValueError("branch_ref must be non-empty")

        for commit in self.commit_range:
            if not (7 <= len(commit) <= 40):
                raise ValueError(f"commit SHA must be 7-40 chars, got {len(commit)}: {commit}")
            if not all(c in "0123456789abcdef" for c in commit.lower()):
                raise ValueError(f"commit SHA must be hex chars: {commit}")

        if self.implementation_summary is not None and len(self.implementation_summary) > 2000:
            raise ValueError(f"implementation_summary must be <= 2000 chars, got {len(self.implementation_summary)}")

        if self.validation_command is not None:
            if not self.validation_command:
                raise ValueError("validation_command must be non-empty list if provided")
            if self.validation_command[0] != "uv":
                raise ValueError(f"validation_command must start with 'uv', got {self.validation_command[0]}")


@dataclass
class CodeReviewIssue:
    """A single issue identified by CodeRabbit.

    Invariants:
        - title must be non-empty
        - severity must be a valid severity level
        - details must be non-empty
    """

    title: str
    severity: IssueSeverity
    details: str
    anchor: str | None = None

    def __post_init__(self) -> None:
        """Validate issue invariants."""
        if not self.title or not self.title.strip():
            raise ValueError("title must be non-empty")
        if not self.details or not self.details.strip():
            raise ValueError("details must be non-empty")


@dataclass
class CodeReviewFindings:
    """Normalized result of running CodeRabbit CLI.

    Invariants:
        - issues list is sorted by severity (blocker > major > minor)
        - sanitized_prompt is derived from transcript
        - raw_hash is 64 hex characters (SHA-256)
    """

    issues: list[CodeReviewIssue]
    sanitized_prompt: str
    raw_hash: str
    generated_at: datetime
    transcript: str = ""
    summary: str = ""

    def __post_init__(self) -> None:
        """Validate findings invariants."""
        if len(self.raw_hash) != 64:
            raise ValueError(f"raw_hash must be 64 hex chars, got {len(self.raw_hash)}")
        if not all(c in "0123456789abcdef" for c in self.raw_hash):
            raise ValueError("raw_hash must contain only hex characters")

        # Verify severity ordering
        severity_order = {"blocker": 0, "major": 1, "minor": 2}
        for i in range(len(self.issues) - 1):
            current_severity = severity_order[self.issues[i].severity]
            next_severity = severity_order[self.issues[i + 1].severity]
            if current_severity > next_severity:
                raise ValueError(
                    f"issues must be sorted by severity: {self.issues[i].severity} "
                    f"should not come before {self.issues[i + 1].severity}"
                )


@dataclass
class FixAttemptRecord:
    """Metadata describing an OpenCode remediation attempt.

    Invariants:
        - request_id must be non-empty
        - sanitized_prompt must be non-empty
        - started_at must be before or equal to completed_at
    """

    request_id: str
    sanitized_prompt: str
    exit_code: int
    started_at: datetime
    completed_at: datetime
    applied_changes: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""

    def __post_init__(self) -> None:
        """Validate fix attempt invariants."""
        if not self.request_id or not self.request_id.strip():
            raise ValueError("request_id must be non-empty")
        if not self.sanitized_prompt or not self.sanitized_prompt.strip():
            raise ValueError("sanitized_prompt must be non-empty")
        if self.started_at > self.completed_at:
            raise ValueError(
                f"started_at ({self.started_at}) must be before or equal to completed_at ({self.completed_at})"
            )


@dataclass
class ValidationResult:
    """Outcome of validation command (default cargo test).

    Invariants:
        - command must be non-empty and start with "uv"
        - started_at must be before or equal to completed_at
    """

    command: list[str]
    exit_code: int
    started_at: datetime
    completed_at: datetime
    stdout: str = ""
    stderr: str = ""

    def __post_init__(self) -> None:
        """Validate validation result invariants."""
        if not self.command:
            raise ValueError("command must be non-empty")
        if self.command[0] != "uv":
            raise ValueError(f"command must start with 'uv', got {self.command[0]}")
        if self.started_at > self.completed_at:
            raise ValueError(
                f"started_at ({self.started_at}) must be before or equal to completed_at ({self.completed_at})"
            )


@dataclass
class ReviewLoopOutcome:
    """Activity result the workflow consumes.

    Invariants:
        - status="clean" requires fix_attempt=None and issues_fixed=0
        - status="fixed" requires both fix_attempt and validation_result
        - status="fixed" requires issues_fixed > 0
        - fingerprint must be 64 hex characters
        - code_review_findings should be present unless activity fails early
    """

    status: ReviewOutcomeStatus
    fingerprint: str
    completed_at: datetime
    issues_fixed: int = 0
    code_review_findings: CodeReviewFindings | None = None
    fix_attempt: FixAttemptRecord | None = None
    validation_result: ValidationResult | None = None
    artifacts_path: str = ""

    def __post_init__(self) -> None:
        """Validate outcome invariants."""
        if len(self.fingerprint) != 64:
            raise ValueError(f"fingerprint must be 64 hex chars, got {len(self.fingerprint)}")
        if not all(c in "0123456789abcdef" for c in self.fingerprint):
            raise ValueError("fingerprint must contain only hex characters")

        if self.issues_fixed < 0:
            raise ValueError(f"issues_fixed must be >= 0, got {self.issues_fixed}")

        # Validate clean status invariants
        if self.status == "clean":
            if self.fix_attempt is not None:
                raise ValueError("status=clean requires fix_attempt=None")
            if self.issues_fixed != 0:
                raise ValueError(f"status=clean requires issues_fixed=0, got {self.issues_fixed}")

        # Validate fixed status invariants
        if self.status == "fixed":
            if self.fix_attempt is None:
                raise ValueError("status=fixed requires fix_attempt")
            if self.validation_result is None:
                raise ValueError("status=fixed requires validation_result")
            if self.issues_fixed <= 0:
                raise ValueError(f"status=fixed requires issues_fixed > 0, got {self.issues_fixed}")
