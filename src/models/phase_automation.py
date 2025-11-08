"""Dataclasses supporting phase automation workflows."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from temporalio.common import RetryPolicy


PhaseResultStatus = Literal["success", "failed", "skipped"]
PrAutomationStatus = Literal["merged", "ci_failed", "timeout", "error"]
CiJobStatus = Literal["queued", "in_progress", "failure", "cancelled", "timed_out"]

_TASK_ID_PATTERN = re.compile(r"^T\d{3,}$")
_PHASE_ID_TEMPLATE = "phase-{ordinal}"


def _ensure_timezone(dt: datetime, field_name: str) -> None:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class TaskItem:
    """Represents an individual checklist entry."""

    task_id: str
    description: str
    is_complete: bool
    tags: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        normalized_description = self.description.strip()
        if not normalized_description:
            raise ValueError("description must be non-empty")
        if not _TASK_ID_PATTERN.fullmatch(self.task_id):
            raise ValueError("task_id must match pattern ^T\\d{3,}$")
        sanitized_tags: tuple[str, ...] = tuple(tag.strip().lstrip("#") for tag in self.tags if tag.strip())
        object.__setattr__(self, "description", normalized_description)
        object.__setattr__(self, "tags", sanitized_tags)


@dataclass(frozen=True)
class PhaseExecutionHints:
    """Optional overrides parsed from phase metadata."""

    model: str | None = None
    agent_profile: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        cleaned_env: dict[str, str] = {}
        for key, value in self.extra_env.items():
            if key.upper() != key or not key.isascii():
                raise ValueError("extra_env keys must be uppercase ASCII")
            cleaned_env[key] = str(value)
        object.__setattr__(self, "extra_env", cleaned_env)


@dataclass(frozen=True)
class PhaseDefinition:
    """Parsed representation of a `tasks.md` phase."""

    phase_id: str
    ordinal: int
    title: str
    tasks: Sequence[TaskItem]
    execution_hints: PhaseExecutionHints | None
    raw_markdown: str

    def __post_init__(self) -> None:
        if self.ordinal < 1:
            raise ValueError("ordinal must be >= 1")
        expected_phase_id = _PHASE_ID_TEMPLATE.format(ordinal=self.ordinal)
        if self.phase_id != expected_phase_id:
            raise ValueError("phase_id must match ordinal")
        normalized_title = self.title.strip()
        if not normalized_title:
            raise ValueError("title must be non-empty")
        for task in self.tasks:
            if not isinstance(task, TaskItem):
                raise ValueError("tasks must contain TaskItem instances")
        object.__setattr__(self, "title", normalized_title)
        object.__setattr__(self, "tasks", tuple(self.tasks))


@dataclass(frozen=True)
class PhaseResult:
    """Activity output summarizing phase execution."""

    phase_id: str
    status: PhaseResultStatus
    completed_task_ids: Sequence[str]
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    tasks_md_hash: str
    stdout_path: str | None
    stderr_path: str | None
    artifact_paths: Sequence[str]
    summary: Sequence[str]
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in ("success", "failed", "skipped"):
            raise ValueError("status must be one of 'success', 'failed', or 'skipped'")
        _ensure_timezone(self.started_at, "started_at")
        _ensure_timezone(self.finished_at, "finished_at")
        if self.finished_at <= self.started_at:
            raise ValueError("finished_at must be after started_at")
        expected_duration = int((self.finished_at - self.started_at).total_seconds() * 1000)
        if self.duration_ms != expected_duration:
            raise ValueError("duration_ms must equal elapsed time in milliseconds")
        if self.status == "failed" and not self.error:
            raise ValueError("error must be provided when status='failed'")
        if self.status != "failed" and self.error:
            raise ValueError("error must be None when status is not 'failed'")
        if not self.tasks_md_hash:
            raise ValueError("tasks_md_hash must be non-empty")
        parsed_stdout = str(self.stdout_path) if self.stdout_path is not None else None
        parsed_stderr = str(self.stderr_path) if self.stderr_path is not None else None
        artifact_strings = tuple(str(path) for path in self.artifact_paths)
        object.__setattr__(self, "stdout_path", parsed_stdout)
        object.__setattr__(self, "stderr_path", parsed_stderr)
        object.__setattr__(self, "completed_task_ids", tuple(self.completed_task_ids))
        object.__setattr__(self, "artifact_paths", artifact_strings)
        object.__setattr__(self, "summary", tuple(self.summary))


@dataclass(frozen=True)
class WorkflowCheckpoint:
    """Persisted workflow state enabling resume behaviour."""

    last_completed_phase_index: int
    results: Sequence[PhaseResult]
    tasks_md_hash: str
    updated_at: datetime

    def __post_init__(self) -> None:
        _ensure_timezone(self.updated_at, "updated_at")
        results_tuple = tuple(self.results)
        object.__setattr__(self, "results", results_tuple)
        if results_tuple:
            expected_index = len(results_tuple) - 1
            if self.last_completed_phase_index != expected_index:
                raise ValueError("last_completed_phase_index must align with results length")
            latest_hash = results_tuple[-1].tasks_md_hash
            if self.tasks_md_hash != latest_hash:
                raise ValueError("tasks_md_hash must match latest result")
        else:
            if self.last_completed_phase_index != -1:
                raise ValueError("last_completed_phase_index must be -1 when no results exist")
        if not self.tasks_md_hash:
            raise ValueError("tasks_md_hash must be non-empty")


@dataclass(frozen=True)
class PhaseExecutionContext:
    """Activity input describing execution parameters."""

    repo_path: str
    branch: str
    tasks_md_path: str | None
    tasks_md_content: str | None
    phase: PhaseDefinition
    checkpoint: WorkflowCheckpoint | None
    timeout_minutes: int
    hints: PhaseExecutionHints | None

    def __post_init__(self) -> None:
        normalized_repo = Path(self.repo_path)
        if not normalized_repo.is_absolute():
            raise ValueError("repo_path must be absolute")
        object.__setattr__(self, "repo_path", str(normalized_repo))

        if not self.branch.strip():
            raise ValueError("branch must be non-empty")
        has_path = self.tasks_md_path is not None
        has_content = self.tasks_md_content is not None
        if has_path == has_content:
            raise ValueError("Provide exactly one of tasks_md_path or tasks_md_content")
        if has_path:
            assert self.tasks_md_path is not None
            normalized_tasks_path = Path(self.tasks_md_path)
            if not normalized_tasks_path.is_absolute():
                raise ValueError("tasks_md_path must be absolute")
            object.__setattr__(self, "tasks_md_path", str(normalized_tasks_path))
        if self.timeout_minutes < 30:
            raise ValueError("timeout_minutes must be >= 30")


@dataclass(frozen=True)
class ResumeState:
    """Helper struct summarizing resume decisions."""

    starting_phase_index: int
    phases_to_run: Sequence[PhaseDefinition]
    skipped_phase_ids: Sequence[str]
    checkpoint: WorkflowCheckpoint | None

    def __post_init__(self) -> None:
        phases_tuple = tuple(self.phases_to_run)
        skipped_tuple = tuple(self.skipped_phase_ids)
        object.__setattr__(self, "phases_to_run", phases_tuple)
        object.__setattr__(self, "skipped_phase_ids", skipped_tuple)
        if phases_tuple:
            if not (0 <= self.starting_phase_index < len(phases_tuple)):
                raise ValueError("starting_phase_index must align with phases_to_run length")
        else:
            if self.starting_phase_index not in (-1, 0):
                raise ValueError("starting_phase_index must be -1 or 0 when no phases_to_run")


def _timedelta_to_seconds(value: timedelta | None) -> float | None:
    if value is None:
        return None
    return value.total_seconds()


def _seconds_to_timedelta(value: float | None) -> timedelta | None:
    if value is None:
        return None
    return timedelta(seconds=value)


@dataclass(frozen=True)
class RetryPolicySettings:
    """JSON-serializable representation of a Temporal retry policy."""

    maximum_attempts: int | None = None
    initial_interval_seconds: float | None = None
    maximum_interval_seconds: float | None = None
    non_retryable_error_types: tuple[str, ...] = field(default_factory=tuple)

    def to_retry_policy(self) -> RetryPolicy:
        kwargs: dict[str, Any] = {}
        if self.maximum_attempts is not None:
            kwargs["maximum_attempts"] = self.maximum_attempts
        if self.initial_interval_seconds is not None:
            kwargs["initial_interval"] = _seconds_to_timedelta(self.initial_interval_seconds)
        if self.maximum_interval_seconds is not None:
            kwargs["maximum_interval"] = _seconds_to_timedelta(self.maximum_interval_seconds)
        if self.non_retryable_error_types:
            kwargs["non_retryable_error_types"] = list(self.non_retryable_error_types)
        return RetryPolicy(**kwargs)


@dataclass(frozen=True)
class AutomatePhaseTasksParams:
    """Workflow input parameters for automated phase execution."""

    repo_path: str
    branch: str
    tasks_md_path: str | None
    tasks_md_content: str | None
    default_model: str | None = None
    default_agent_profile: str | None = None
    timeout_minutes: int = 30
    retry_policy: RetryPolicy | RetryPolicySettings | None = None

    def __post_init__(self) -> None:
        repo_path = Path(self.repo_path)
        if not repo_path.exists() or not repo_path.is_dir():
            raise ValueError("repo_path must exist and be a directory")
        object.__setattr__(self, "repo_path", str(repo_path.resolve()))

        normalized_branch = self.branch.strip()
        if not normalized_branch:
            raise ValueError("branch must be non-empty")
        object.__setattr__(self, "branch", normalized_branch)

        has_path = self.tasks_md_path is not None
        has_content = self.tasks_md_content is not None
        if has_path == has_content:
            raise ValueError("Provide exactly one of tasks_md_path or tasks_md_content")
        if has_path:
            path = Path(self.tasks_md_path or "")
            if not path.is_absolute():
                raise ValueError("tasks_md_path must be absolute")
            object.__setattr__(self, "tasks_md_path", str(path))

        if self.timeout_minutes < 30:
            raise ValueError("timeout_minutes must be >= 30")

        raw_policy = self.retry_policy
        if raw_policy is None:
            settings = RetryPolicySettings(maximum_attempts=1)
        elif isinstance(raw_policy, RetryPolicy):
            settings = RetryPolicySettings(
                maximum_attempts=raw_policy.maximum_attempts,
                initial_interval_seconds=_timedelta_to_seconds(raw_policy.initial_interval),
                maximum_interval_seconds=_timedelta_to_seconds(raw_policy.maximum_interval),
                non_retryable_error_types=tuple(raw_policy.non_retryable_error_types or []),
            )
        else:
            settings = raw_policy

        object.__setattr__(self, "retry_policy", settings)


@dataclass(frozen=True)
class PhaseAutomationSummary:
    """Aggregated workflow result for a phase automation run."""

    results: Sequence[PhaseResult]
    skipped_phase_ids: Sequence[str]
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    tasks_md_hash: str

    def __post_init__(self) -> None:
        _ensure_timezone(self.started_at, "started_at")
        _ensure_timezone(self.finished_at, "finished_at")
        if self.finished_at <= self.started_at:
            raise ValueError("finished_at must be after started_at")
        expected_duration = int((self.finished_at - self.started_at).total_seconds() * 1000)
        if self.duration_ms != expected_duration:
            raise ValueError("duration_ms must equal elapsed time in milliseconds")
        if not self.tasks_md_hash:
            raise ValueError("tasks_md_hash must be non-empty")
        object.__setattr__(self, "results", tuple(self.results))
        object.__setattr__(self, "skipped_phase_ids", tuple(self.skipped_phase_ids))


@dataclass(frozen=True)
class PollingConfiguration:
    """Configuration for CI polling behavior."""

    interval_seconds: int = 30
    timeout_minutes: int = 45
    max_retries: int = 5
    backoff_coefficient: float = 2.0

    def __post_init__(self) -> None:
        if self.interval_seconds < 1:
            raise ValueError("interval_seconds must be >= 1")
        if self.timeout_minutes < 1:
            raise ValueError("timeout_minutes must be >= 1")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.backoff_coefficient < 1.0:
            raise ValueError("backoff_coefficient must be >= 1.0")


@dataclass(frozen=True)
class CiFailureDetail:
    """Per-job failure record for CI failures."""

    job_name: str
    attempt: int
    status: CiJobStatus
    summary: str | None = None
    log_url: str | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.job_name.strip():
            raise ValueError("job_name must be non-empty")
        if self.attempt < 1:
            raise ValueError("attempt must be >= 1")
        if self.completed_at is not None:
            _ensure_timezone(self.completed_at, "completed_at")


@dataclass(frozen=True)
class PullRequestAutomationRequest:
    """Input payload for PR CI automation activity."""

    source_branch: str
    summary: str
    workflow_attempt_id: str
    target_branch: str = "main"
    polling: PollingConfiguration | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_branch.strip():
            raise ValueError("source_branch must be non-empty")
        if not self.summary.strip():
            raise ValueError("summary must be non-empty")
        if not self.workflow_attempt_id.strip():
            raise ValueError("workflow_attempt_id must be non-empty")
        if not self.target_branch.strip():
            raise ValueError("target_branch must be non-empty")

        # Normalize strings
        object.__setattr__(self, "source_branch", self.source_branch.strip())
        object.__setattr__(self, "summary", self.summary.strip())
        object.__setattr__(self, "workflow_attempt_id", self.workflow_attempt_id.strip())
        object.__setattr__(self, "target_branch", self.target_branch.strip())

        # Ensure metadata is immutable
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class PullRequestAutomationResult:
    """Deterministic activity response for PR CI automation."""

    status: PrAutomationStatus
    polling_duration_seconds: int
    pull_request_number: int | None = None
    pull_request_url: str | None = None
    merge_commit_sha: str | None = None
    ci_failures: Sequence[CiFailureDetail] = field(default_factory=tuple)
    retry_advice: str | None = None
    error_detail: str | None = None

    def __post_init__(self) -> None:
        if self.polling_duration_seconds < 0:
            raise ValueError("polling_duration_seconds must be >= 0")

        # Validate status-specific invariants
        if self.status == "merged" and (self.merge_commit_sha is None or not self.merge_commit_sha.strip()):
            raise ValueError("merge_commit_sha must be provided when status='merged'")

        if self.status == "ci_failed" and not self.ci_failures:
            raise ValueError("ci_failures must be non-empty when status='ci_failed'")

        if self.status == "error" and not self.error_detail:
            raise ValueError("error_detail must be provided when status='error'")

        # Ensure ci_failures is immutable tuple
        object.__setattr__(self, "ci_failures", tuple(self.ci_failures))


__all__ = [
    "AutomatePhaseTasksParams",
    "CiFailureDetail",
    "CiJobStatus",
    "PhaseDefinition",
    "PhaseExecutionContext",
    "PhaseExecutionHints",
    "PhaseResult",
    "PhaseResultStatus",
    "PhaseAutomationSummary",
    "PollingConfiguration",
    "PrAutomationStatus",
    "PullRequestAutomationRequest",
    "PullRequestAutomationResult",
    "ResumeState",
    "RetryPolicySettings",
    "TaskItem",
    "WorkflowCheckpoint",
]
