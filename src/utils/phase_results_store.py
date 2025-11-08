"""Utilities for persisting and loading PhaseResult to/from JSON files."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.phase_automation import (
    CiFailureDetail,
    PhaseResult,
    PullRequestAutomationResult,
)
from src.models.review_fix import (
    CodeReviewFindings,
    CodeReviewIssue,
    FixAttemptRecord,
    RetryMetadata,
    ReviewLoopOutcome,
    ValidationResult,
)


def serialize_phase_result(result: PhaseResult) -> dict[str, Any]:
    """Convert PhaseResult to JSON-serializable dictionary.

    Args:
        result: PhaseResult instance to serialize

    Returns:
        Dictionary with all fields converted to JSON-compatible types
    """
    return {
        "phase_id": result.phase_id,
        "status": result.status,
        "completed_task_ids": list(result.completed_task_ids),
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
        "duration_ms": result.duration_ms,
        "tasks_md_hash": result.tasks_md_hash,
        "stdout_path": result.stdout_path,
        "stderr_path": result.stderr_path,
        "artifact_paths": list(result.artifact_paths),
        "summary": list(result.summary),
        "error": result.error,
    }


def deserialize_phase_result(data: dict[str, Any]) -> PhaseResult:
    """Reconstruct PhaseResult from JSON dictionary.

    Args:
        data: Dictionary containing serialized PhaseResult fields

    Returns:
        PhaseResult instance

    Raises:
        ValueError: If data contains invalid timestamp format or missing required fields
        KeyError: If required fields are missing from data
    """
    try:
        started_at = datetime.fromisoformat(data["started_at"])
        finished_at = datetime.fromisoformat(data["finished_at"])
    except (ValueError, KeyError) as e:
        if isinstance(e, ValueError):
            raise ValueError(f"Invalid timestamp format: {e}") from e
        raise

    return PhaseResult(
        phase_id=data["phase_id"],
        status=data["status"],
        completed_task_ids=tuple(data["completed_task_ids"]),
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=data["duration_ms"],
        tasks_md_hash=data["tasks_md_hash"],
        stdout_path=data["stdout_path"],
        stderr_path=data["stderr_path"],
        artifact_paths=tuple(data["artifact_paths"]),
        summary=tuple(data["summary"]),
        error=data.get("error"),
    )


def save_phase_result(result: PhaseResult, output_path: Path) -> None:
    """Persist PhaseResult to JSON file.

    Creates parent directories if they don't exist. Overwrites existing file.

    Args:
        result: PhaseResult to save
        output_path: Target file path (will create parent directories)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    serialized = serialize_phase_result(result)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)


def load_phase_result(input_path: Path) -> PhaseResult:
    """Load PhaseResult from JSON file.

    Args:
        input_path: Path to JSON file containing serialized PhaseResult

    Returns:
        Deserialized PhaseResult instance

    Raises:
        FileNotFoundError: If input_path does not exist
        ValueError: If file contains invalid JSON or cannot be deserialized
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Phase result file not found: {input_path}")

    try:
        with input_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from {input_path}: {e}") from e

    return deserialize_phase_result(data)


def serialize_review_outcome(outcome: ReviewLoopOutcome) -> dict[str, Any]:
    """Convert ReviewLoopOutcome to JSON-serializable dictionary.

    Args:
        outcome: ReviewLoopOutcome instance to serialize

    Returns:
        Dictionary with all fields converted to JSON-compatible types
    """
    result: dict[str, Any] = {
        "status": outcome.status,
        "fingerprint": outcome.fingerprint,
        "completed_at": outcome.completed_at.isoformat(),
        "issues_fixed": outcome.issues_fixed,
        "artifacts_path": outcome.artifacts_path,
    }

    # Serialize optional code_review_findings
    if outcome.code_review_findings is not None:
        findings = outcome.code_review_findings
        result["code_review_findings"] = {
            "issues": [
                {
                    "title": issue.title,
                    "severity": issue.severity,
                    "details": issue.details,
                    "anchor": issue.anchor,
                }
                for issue in findings.issues
            ],
            "transcript": findings.transcript,
            "sanitized_prompt": findings.sanitized_prompt,
            "summary": findings.summary,
            "raw_hash": findings.raw_hash,
            "generated_at": findings.generated_at.isoformat(),
        }

    # Serialize optional fix_attempt
    if outcome.fix_attempt is not None:
        attempt = outcome.fix_attempt
        result["fix_attempt"] = {
            "request_id": attempt.request_id,
            "sanitized_prompt": attempt.sanitized_prompt,
            "exit_code": attempt.exit_code,
            "started_at": attempt.started_at.isoformat(),
            "completed_at": attempt.completed_at.isoformat(),
            "applied_changes": list(attempt.applied_changes),
            "stdout": attempt.stdout,
            "stderr": attempt.stderr,
        }

    # Serialize optional validation_result
    if outcome.validation_result is not None:
        validation = outcome.validation_result
        result["validation_result"] = {
            "command": list(validation.command),
            "exit_code": validation.exit_code,
            "started_at": validation.started_at.isoformat(),
            "completed_at": validation.completed_at.isoformat(),
            "stdout": validation.stdout,
            "stderr": validation.stderr,
        }

    return result


def deserialize_review_outcome(data: dict[str, Any]) -> ReviewLoopOutcome:
    """Reconstruct ReviewLoopOutcome from JSON dictionary.

    Args:
        data: Dictionary containing serialized ReviewLoopOutcome fields

    Returns:
        ReviewLoopOutcome instance

    Raises:
        ValueError: If data contains invalid timestamp format or missing required fields
        KeyError: If required fields are missing from data
    """
    try:
        completed_at = datetime.fromisoformat(data["completed_at"])
    except (ValueError, KeyError) as e:
        if isinstance(e, ValueError):
            raise ValueError(f"Invalid timestamp format: {e}") from e
        raise

    # Deserialize optional code_review_findings
    code_review_findings = None
    if "code_review_findings" in data:
        findings_data = data["code_review_findings"]
        issues = [
            CodeReviewIssue(
                title=issue["title"],
                severity=issue["severity"],
                details=issue["details"],
                anchor=issue.get("anchor"),
            )
            for issue in findings_data["issues"]
        ]
        code_review_findings = CodeReviewFindings(
            issues=issues,
            transcript=findings_data.get("transcript", ""),
            sanitized_prompt=findings_data["sanitized_prompt"],
            summary=findings_data.get("summary", ""),
            raw_hash=findings_data["raw_hash"],
            generated_at=datetime.fromisoformat(findings_data["generated_at"]),
        )

    # Deserialize optional fix_attempt
    fix_attempt = None
    if "fix_attempt" in data:
        attempt_data = data["fix_attempt"]
        fix_attempt = FixAttemptRecord(
            request_id=attempt_data["request_id"],
            sanitized_prompt=attempt_data["sanitized_prompt"],
            exit_code=attempt_data["exit_code"],
            started_at=datetime.fromisoformat(attempt_data["started_at"]),
            completed_at=datetime.fromisoformat(attempt_data["completed_at"]),
            applied_changes=list(attempt_data.get("applied_changes", [])),
            stdout=attempt_data.get("stdout", ""),
            stderr=attempt_data.get("stderr", ""),
        )

    # Deserialize optional validation_result
    validation_result = None
    if "validation_result" in data:
        validation_data = data["validation_result"]
        validation_result = ValidationResult(
            command=list(validation_data["command"]),
            exit_code=validation_data["exit_code"],
            started_at=datetime.fromisoformat(validation_data["started_at"]),
            completed_at=datetime.fromisoformat(validation_data["completed_at"]),
            stdout=validation_data.get("stdout", ""),
            stderr=validation_data.get("stderr", ""),
        )

    return ReviewLoopOutcome(
        status=data["status"],
        fingerprint=data["fingerprint"],
        completed_at=completed_at,
        issues_fixed=data.get("issues_fixed", 0),
        code_review_findings=code_review_findings,
        fix_attempt=fix_attempt,
        validation_result=validation_result,
        artifacts_path=data.get("artifacts_path", ""),
    )


def save_review_outcome(outcome: ReviewLoopOutcome, output_path: Path) -> None:
    """Persist ReviewLoopOutcome to JSON file.

    Creates parent directories if they don't exist. Overwrites existing file.

    Args:
        outcome: ReviewLoopOutcome to save
        output_path: Target file path (will create parent directories)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    serialized = serialize_review_outcome(outcome)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)


def load_review_outcome(input_path: Path) -> ReviewLoopOutcome:
    """Load ReviewLoopOutcome from JSON file.

    Args:
        input_path: Path to JSON file containing serialized ReviewLoopOutcome

    Returns:
        Deserialized ReviewLoopOutcome instance

    Raises:
        FileNotFoundError: If input_path does not exist
        ValueError: If file contains invalid JSON or cannot be deserialized
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Review outcome file not found: {input_path}")

    try:
        with input_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from {input_path}: {e}") from e

    return deserialize_review_outcome(data)


def save_sanitized_prompt(
    prompt: str,
    fingerprint: str,
    output_dir: Path,
) -> Path:
    """Save sanitized CodeRabbit prompt to file.

    Args:
        prompt: Sanitized prompt text
        fingerprint: Review fingerprint for filename
        output_dir: Directory to save prompt file

    Returns:
        Path to saved prompt file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = output_dir / f"prompt_{fingerprint}.txt"

    with prompt_file.open("w", encoding="utf-8") as f:
        f.write(prompt)

    return prompt_file


def save_fix_summary(
    summary: str,
    fingerprint: str,
    output_dir: Path,
) -> Path:
    """Save OpenCode fix summary to file.

    Args:
        summary: Fix summary text
        fingerprint: Review fingerprint for filename
        output_dir: Directory to save summary file

    Returns:
        Path to saved summary file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_file = output_dir / f"fix_summary_{fingerprint}.txt"

    with summary_file.open("w", encoding="utf-8") as f:
        f.write(summary)

    return summary_file


def serialize_retry_metadata(metadata: RetryMetadata) -> dict[str, Any]:
    """Convert RetryMetadata to JSON-serializable dictionary.

    Args:
        metadata: RetryMetadata instance to serialize

    Returns:
        Dictionary with all fields converted to JSON-compatible types
    """
    return {
        "previous_fingerprint": metadata.previous_fingerprint,
        "attempt_counter": metadata.attempt_counter,
        "last_status": metadata.last_status,
        "artifacts_path": metadata.artifacts_path,
    }


def deserialize_retry_metadata(data: dict[str, Any]) -> RetryMetadata:
    """Reconstruct RetryMetadata from JSON dictionary.

    Args:
        data: Dictionary containing serialized RetryMetadata fields

    Returns:
        RetryMetadata instance

    Raises:
        KeyError: If required fields are missing from data
    """
    return RetryMetadata(
        previous_fingerprint=data["previous_fingerprint"],
        attempt_counter=data["attempt_counter"],
        last_status=data["last_status"],
        artifacts_path=data.get("artifacts_path"),
    )


def save_retry_metadata(metadata: RetryMetadata, output_path: Path) -> None:
    """Persist RetryMetadata to JSON file.

    Creates parent directories if they don't exist. Overwrites existing file.

    Args:
        metadata: RetryMetadata to save
        output_path: Target file path (will create parent directories)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    serialized = serialize_retry_metadata(metadata)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)


def load_retry_metadata(input_path: Path) -> RetryMetadata:
    """Load RetryMetadata from JSON file.

    Args:
        input_path: Path to JSON file containing serialized RetryMetadata

    Returns:
        Deserialized RetryMetadata instance

    Raises:
        FileNotFoundError: If input_path does not exist
        ValueError: If file contains invalid JSON or cannot be deserialized
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Retry metadata file not found: {input_path}")

    try:
        with input_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from {input_path}: {e}") from e

    return deserialize_retry_metadata(data)


def serialize_pr_automation_result(result: PullRequestAutomationResult) -> dict[str, Any]:
    """Convert PullRequestAutomationResult to JSON-serializable dictionary.

    Args:
        result: PullRequestAutomationResult instance to serialize

    Returns:
        Dictionary with all fields converted to JSON-compatible types
    """
    data: dict[str, Any] = {
        "status": result.status,
        "polling_duration_seconds": result.polling_duration_seconds,
        "pull_request_number": result.pull_request_number,
        "pull_request_url": result.pull_request_url,
        "merge_commit_sha": result.merge_commit_sha,
        "retry_advice": result.retry_advice,
        "error_detail": result.error_detail,
    }

    # Serialize ci_failures
    if result.ci_failures:
        data["ci_failures"] = [
            {
                "job_name": failure.job_name,
                "attempt": failure.attempt,
                "status": failure.status,
                "summary": failure.summary,
                "log_url": failure.log_url,
                "completed_at": failure.completed_at.isoformat() if failure.completed_at else None,
            }
            for failure in result.ci_failures
        ]
    else:
        data["ci_failures"] = []

    return data


def deserialize_pr_automation_result(data: dict[str, Any]) -> PullRequestAutomationResult:
    """Reconstruct PullRequestAutomationResult from JSON dictionary.

    Args:
        data: Dictionary containing serialized PullRequestAutomationResult fields

    Returns:
        PullRequestAutomationResult instance

    Raises:
        ValueError: If data contains invalid timestamp format or missing required fields
        KeyError: If required fields are missing from data
    """
    # Deserialize ci_failures
    ci_failures = []
    if "ci_failures" in data and data["ci_failures"]:
        for failure_data in data["ci_failures"]:
            completed_at = None
            if failure_data.get("completed_at"):
                try:
                    completed_at = datetime.fromisoformat(failure_data["completed_at"])
                except ValueError as e:
                    raise ValueError(f"Invalid timestamp format in ci_failure: {e}") from e

            ci_failures.append(
                CiFailureDetail(
                    job_name=failure_data["job_name"],
                    attempt=failure_data["attempt"],
                    status=failure_data["status"],
                    summary=failure_data.get("summary"),
                    log_url=failure_data.get("log_url"),
                    completed_at=completed_at,
                )
            )

    return PullRequestAutomationResult(
        status=data["status"],
        polling_duration_seconds=data["polling_duration_seconds"],
        pull_request_number=data.get("pull_request_number"),
        pull_request_url=data.get("pull_request_url"),
        merge_commit_sha=data.get("merge_commit_sha"),
        ci_failures=ci_failures,
        retry_advice=data.get("retry_advice"),
        error_detail=data.get("error_detail"),
    )


def save_pr_automation_result(result: PullRequestAutomationResult, output_path: Path) -> None:
    """Persist PullRequestAutomationResult to JSON file.

    Creates parent directories if they don't exist. Overwrites existing file.

    Args:
        result: PullRequestAutomationResult to save
        output_path: Target file path (will create parent directories)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    serialized = serialize_pr_automation_result(result)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)


def load_pr_automation_result(input_path: Path) -> PullRequestAutomationResult:
    """Load PullRequestAutomationResult from JSON file.

    Args:
        input_path: Path to JSON file containing serialized PullRequestAutomationResult

    Returns:
        Deserialized PullRequestAutomationResult instance

    Raises:
        FileNotFoundError: If input_path does not exist
        ValueError: If file contains invalid JSON or cannot be deserialized
    """
    if not input_path.exists():
        raise FileNotFoundError(f"PR automation result file not found: {input_path}")

    try:
        with input_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from {input_path}: {e}") from e

    return deserialize_pr_automation_result(data)


__all__ = [
    "deserialize_phase_result",
    "deserialize_pr_automation_result",
    "deserialize_retry_metadata",
    "deserialize_review_outcome",
    "load_phase_result",
    "load_pr_automation_result",
    "load_retry_metadata",
    "load_review_outcome",
    "save_fix_summary",
    "save_phase_result",
    "save_pr_automation_result",
    "save_retry_metadata",
    "save_review_outcome",
    "save_sanitized_prompt",
    "serialize_phase_result",
    "serialize_pr_automation_result",
    "serialize_retry_metadata",
    "serialize_review_outcome",
]
