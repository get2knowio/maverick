"""Temporal activity for executing a single phase via speckit.implement.

Logging Events (structured logger):
    - phase_run_started: Activity begins phase execution
    - phase_run_skipped: Phase has no actionable tasks, skipped
    - phase_activity_invoking: About to invoke speckit.implement CLI
    - phase_activity_timeout: CLI execution exceeded timeout
    - phase_verification_failed: Could not verify phase in updated tasks.md
    - phase_activity_failed: Phase execution failed (non-zero exit or incomplete tasks)
    - phase_activity_succeeded: Phase completed successfully
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from temporalio import activity

from src.models.phase_automation import PhaseExecutionContext, PhaseResult
from src.utils.logging import get_structured_logger
from src.utils.tasks_markdown import compute_tasks_md_hash, parse_tasks_markdown


logger = get_structured_logger("activity.run_phase")


def _load_tasks_content(context: PhaseExecutionContext) -> str:
    if context.tasks_md_path is not None:
        path = Path(context.tasks_md_path)
        if not path.exists():
            raise FileNotFoundError(f"tasks.md path does not exist: {path}")
        return path.read_text(encoding="utf-8")
    if context.tasks_md_content is not None:
        return context.tasks_md_content
    raise ValueError("PhaseExecutionContext must provide tasks_md_path or tasks_md_content")


def _build_command(context: PhaseExecutionContext, open_task_ids: Iterable[str]) -> list[str]:
    cmd = ["speckit.implement"]

    if context.tasks_md_path is not None:
        cmd.extend(["--tasks-md-path", str(context.tasks_md_path)])
    cmd.extend(["--phase-id", context.phase.phase_id])
    cmd.extend(["--branch", context.branch])
    cmd.extend(["--repo-path", context.repo_path])

    task_arg = ",".join(open_task_ids)
    if task_arg:
        cmd.extend(["--task-ids", task_arg])

    if context.hints and context.hints.model:
        cmd.extend(["--model", context.hints.model])
    if context.hints and context.hints.agent_profile:
        cmd.extend(["--agent-profile", context.hints.agent_profile])

    return cmd


def _prepare_env(context: PhaseExecutionContext) -> dict[str, str]:
    env = os.environ.copy()
    if context.hints:
        env.update(context.hints.extra_env)
    return env


def _ensure_logs_dir(repo_path: Path, phase_id: str) -> Path:
    logs_dir = repo_path / "logs" / "phase-results" / phase_id
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def _write_log(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8", errors="replace")
    return path


def _summarize_output(stdout_text: str, stderr_text: str) -> list[str]:
    summary: list[str] = []
    if stdout_text:
        summary.append(stdout_text.splitlines()[0][:200])
    if stderr_text:
        summary.append(stderr_text.splitlines()[0][:200])
    if not summary:
        summary.append("speckit.implement produced no output")
    return summary


def _extract_phase_after(content: str, phase_id: str):
    phases = parse_tasks_markdown(content)
    for phase in phases:
        if phase.phase_id == phase_id:
            return phase
    raise ValueError(f"Phase {phase_id} missing from updated tasks.md")


@activity.defn(name="run_phase")
async def run_phase(context: PhaseExecutionContext) -> PhaseResult:
    """Execute speckit.implement for a single phase and capture structured results."""

    logger.info(
        "phase_run_started",
        phase_id=context.phase.phase_id,
        task_count=len(context.phase.tasks),
        repo_path=context.repo_path,
    )

    start_time = datetime.now(UTC)
    original_content = _load_tasks_content(context)

    open_tasks = [task for task in context.phase.tasks if not task.is_complete]

    if not context.phase.tasks or not open_tasks:
        finished_at = datetime.now(UTC)
        duration_ms = int((finished_at - start_time).total_seconds() * 1000)
        summary = ["Phase contains no actionable tasks; skipping execution."]
        result = PhaseResult(
            phase_id=context.phase.phase_id,
            status="skipped",
            completed_task_ids=[task.task_id for task in context.phase.tasks],
            started_at=start_time,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tasks_md_hash=compute_tasks_md_hash(original_content),
            stdout_path=None,
            stderr_path=None,
            artifact_paths=[],
            summary=summary,
        )
        logger.info("phase_run_skipped", phase_id=context.phase.phase_id)
        return result

    cmd = _build_command(context, (task.task_id for task in open_tasks))
    env = _prepare_env(context)

    logger.info(
        "phase_activity_invoking",
        command=cmd,
        hints=asdict(context.hints) if context.hints else None,
    )

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=context.repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    timeout_seconds = max(1, context.timeout_minutes * 60)

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        process.kill()
        stdout_bytes, stderr_bytes = await process.communicate()
        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        logs_dir = _ensure_logs_dir(Path(context.repo_path), context.phase.phase_id)
        timestamp = start_time.strftime("%Y%m%dT%H%M%S")
        stdout_path = _write_log(logs_dir / f"stdout-timeout-{timestamp}.log", stdout_text)
        stderr_path = _write_log(logs_dir / f"stderr-timeout-{timestamp}.log", stderr_text)
        finished_at = datetime.now(UTC)
        duration_ms = int((finished_at - start_time).total_seconds() * 1000)
        summary = ["speckit.implement timed out", *_summarize_output(stdout_text, stderr_text)]
        logger.error(
            "phase_activity_timeout",
            phase_id=context.phase.phase_id,
            timeout_seconds=timeout_seconds,
        )
        return PhaseResult(
            phase_id=context.phase.phase_id,
            status="failed",
            completed_task_ids=[],
            started_at=start_time,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tasks_md_hash=compute_tasks_md_hash(original_content),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            artifact_paths=[str(stdout_path), str(stderr_path)],
            summary=summary,
            error="speckit.implement timed out",
        )

    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace")

    logs_dir = _ensure_logs_dir(Path(context.repo_path), context.phase.phase_id)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    stdout_path = _write_log(logs_dir / f"stdout-{timestamp}.log", stdout_text)
    stderr_path = _write_log(logs_dir / f"stderr-{timestamp}.log", stderr_text)

    if context.tasks_md_path is None:
        updated_content = original_content
    else:
        updated_content = Path(context.tasks_md_path).read_text(encoding="utf-8")

    try:
        updated_phase = _extract_phase_after(updated_content, context.phase.phase_id)
    except ValueError as exc:
        finished_at = datetime.now(UTC)
        duration_ms = int((finished_at - start_time).total_seconds() * 1000)
        summary = ["Failed to locate phase in updated tasks.md", str(exc)]
        logger.error(
            "phase_verification_failed",
            phase_id=context.phase.phase_id,
            error=str(exc),
        )
        return PhaseResult(
            phase_id=context.phase.phase_id,
            status="failed",
            completed_task_ids=[],
            started_at=start_time,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tasks_md_hash=compute_tasks_md_hash(updated_content),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            artifact_paths=[str(stdout_path), str(stderr_path)],
            summary=summary,
            error=str(exc),
        )

    remaining_open = [task.task_id for task in updated_phase.tasks if not task.is_complete]
    completed_ids = [task.task_id for task in updated_phase.tasks if task.is_complete]

    finished_at = datetime.now(UTC)
    duration_ms = int((finished_at - start_time).total_seconds() * 1000)
    tasks_md_hash = compute_tasks_md_hash(updated_content)

    if process.returncode != 0 or remaining_open:
        error_reason = (
            f"speckit.implement exited with {process.returncode}"
            if process.returncode != 0
            else "Tasks remain unchecked"
        )
        if remaining_open:
            error_reason += f"; remaining tasks: {', '.join(remaining_open)}"
        summary = [error_reason, *_summarize_output(stdout_text, stderr_text)]
        logger.error(
            "phase_activity_failed",
            phase_id=context.phase.phase_id,
            return_code=process.returncode,
            remaining_tasks=remaining_open,
        )
        return PhaseResult(
            phase_id=context.phase.phase_id,
            status="failed",
            completed_task_ids=completed_ids,
            started_at=start_time,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tasks_md_hash=tasks_md_hash,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            artifact_paths=[str(stdout_path), str(stderr_path)],
            summary=summary,
            error=error_reason,
        )

    summary = ["speckit.implement completed successfully", *_summarize_output(stdout_text, stderr_text)]

    logger.info(
        "phase_activity_succeeded",
        phase_id=context.phase.phase_id,
        completed_tasks=completed_ids,
    )

    return PhaseResult(
        phase_id=context.phase.phase_id,
        status="success",
        completed_task_ids=completed_ids,
        started_at=start_time,
        finished_at=finished_at,
        duration_ms=duration_ms,
        tasks_md_hash=tasks_md_hash,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        artifact_paths=[str(stdout_path), str(stderr_path)],
        summary=summary,
    )


__all__ = ["run_phase"]
