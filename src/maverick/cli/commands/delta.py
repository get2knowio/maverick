"""``maverick delta`` — deterministic delta-document layer for changing an
already-shipped Spec Kit feature.

See ``specs/059-spec-delta-layer/contracts/cli-delta.md`` (human output)
and ``contracts/cli-delta-json.md`` (JSON verbs) for the full contract.
Zero model calls on every path (FR-003, FR-019); writes no beads
(FR-011) — bead consequences arrive on the next explicit
``refuel --speckit``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from maverick.beads.client import BeadClient
from maverick.cli.common import BD_REASON_MESSAGES, bd_ready_reason, cli_error_handler
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.json_output import ErrorKind, JsonEnvelope, emit_json
from maverick.speckit.delta.apply import (
    ApplyOutcome,
    RequirementSummary,
    TaskSummary,
    _task_summary,  # noqa: SLF001 -- reuse, not reimplement (Guardrail 5)
    apply_delta,
)
from maverick.speckit.delta.archive import extract_applied_at, list_delta_files
from maverick.speckit.delta.errors import DeltaFormatError, StaleAcknowledgementError
from maverick.speckit.delta.models import Acknowledgement, DeltaDocument, DeltaOperation, Impact
from maverick.speckit.delta.parser import parse_delta_md
from maverick.speckit.delta.validate import DeltaValidationError, Problem, validate_delta
from maverick.speckit.detect import resolve_feature
from maverick.speckit.errors import SpeckitError
from maverick.speckit.models import SpeckitPhase
from maverick.speckit.parser import parse_tasks_md
from maverick.speckit.requirements import RequirementSection, parse_requirements

__all__ = ["delta"]


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _resolve_delta_path(delta_arg: str, *, cwd: Path) -> Path:
    """Resolve DELTA (``<feature>/<slug>`` or a path) to an existing document.

    Raises:
        SpeckitError: The argument does not resolve to any delta document.
    """
    direct = Path(delta_arg)
    if direct.is_file():
        return direct.resolve()

    feature_part, sep, delta_part = delta_arg.partition("/")
    if not sep:
        raise SpeckitError(
            f"{delta_arg!r} does not resolve to a delta document "
            "(expected '<feature>/<delta-slug>' or a file path)"
        )

    resolution = resolve_feature(feature_part, cwd=cwd)
    if resolution.speckit_dir is None:
        raise SpeckitError(f"{feature_part!r} does not resolve to a Spec Kit feature directory")

    deltas_dir = resolution.speckit_dir / "deltas"
    pending = deltas_dir / f"{delta_part}.md"
    if pending.is_file():
        return pending
    archived = deltas_dir / "archive" / f"{delta_part}.md"
    if archived.is_file():
        return archived
    raise SpeckitError(
        f"no delta document found for {delta_arg!r} (looked in {pending} and {archived})"
    )


def _feature_dir_for(document_path: Path) -> Path:
    deltas_dir = document_path.parent
    if deltas_dir.name == "archive":
        deltas_dir = deltas_dir.parent
    return deltas_dir.parent


def _delta_label(document_path: Path, feature_dir: Path) -> str:
    return f"{feature_dir.name}/{document_path.stem}"


def _resolve_and_parse(delta_arg: str, *, cwd: Path) -> tuple[DeltaDocument, str, Path, str]:
    """Resolve + read + parse in one step.

    Raises:
        SpeckitError: Resolution failure.
        DeltaFormatError: Grammar failure.
    """
    document_path = _resolve_delta_path(delta_arg, cwd=cwd)
    feature_dir = _feature_dir_for(document_path)
    label = _delta_label(document_path, feature_dir)
    document_text = document_path.read_text(encoding="utf-8")
    document = parse_delta_md(document_text, path=document_path)
    return document, document_text, feature_dir, label


def _load_target(feature_dir: Path) -> tuple[RequirementSection, tuple[SpeckitPhase, ...]]:
    spec_path = feature_dir / "spec.md"
    tasks_path = feature_dir / "tasks.md"
    section = parse_requirements(spec_path.read_text(encoding="utf-8"), file=str(spec_path))
    phases, _story_deps = parse_tasks_md(
        tasks_path.read_text(encoding="utf-8"), file=str(tasks_path)
    )
    return section, phases


def _all_feature_dirs_with_deltas(cwd: Path) -> list[Path]:
    specs_dir = cwd / "specs"
    if not specs_dir.is_dir():
        return []
    return sorted(
        (p.parent for p in specs_dir.glob("*/deltas") if p.is_dir()), key=lambda p: p.name
    )


# ---------------------------------------------------------------------------
# Projections (shared between human and JSON rendering)
# ---------------------------------------------------------------------------


def _document_requirements_dict(document: DeltaDocument) -> dict[str, Any]:
    return {
        "added": [
            e.req_id for e in document.requirement_entries if e.operation is DeltaOperation.ADDED
        ],
        "modified": [
            e.req_id
            for e in document.requirement_entries
            if e.operation is DeltaOperation.MODIFIED
        ],
        "removed": [
            e.req_id for e in document.requirement_entries if e.operation is DeltaOperation.REMOVED
        ],
        "renamed": [
            {"from": e.req_id, "to": e.new_req_id}
            for e in document.requirement_entries
            if e.operation is DeltaOperation.RENAMED
        ],
    }


def _document_tasks_dict(document: DeltaDocument) -> dict[str, Any]:
    """Same added/withdrawn bucketing ``apply.py``'s ``_task_summary``
    already computes for :class:`~maverick.speckit.delta.apply.ApplyOutcome`
    — reused here rather than re-implemented so the preview (list/validate)
    and outcome (apply/dry-run) paths can't drift on what counts as
    "added"/"withdrawn"."""
    return _tasks_dict(_task_summary(document.task_entries))


def _requirements_dict(summary: RequirementSummary) -> dict[str, Any]:
    return {
        "added": list(summary.added),
        "modified": list(summary.modified),
        "removed": list(summary.removed),
        "renamed": [{"from": f, "to": t} for f, t in summary.renamed],
    }


def _tasks_dict(summary: TaskSummary) -> dict[str, Any]:
    return {"added": list(summary.added), "withdrawn": list(summary.withdrawn)}


def _tasks_change_phrase(tasks: TaskSummary) -> str:
    """``+T042, +T043, -T017`` — shared by the dry-run and applied human
    renderers so the two can never format the same ``TaskSummary``
    differently (previously: the dry-run branch always printed a leading
    literal ``+`` even when nothing was added)."""
    added_part = f"+{', +'.join(tasks.added)}" if tasks.added else ""
    withdrawn_part = f"-{', -'.join(tasks.withdrawn)}" if tasks.withdrawn else ""
    return ", ".join(p for p in (added_part, withdrawn_part) if p)


def _problem_to_dict(problem: Problem) -> dict[str, Any]:
    return {
        "line": problem.line,
        "entry": problem.entry,
        "code": problem.code,
        "message": problem.message,
    }


def _impact_to_dict(impact: Impact) -> dict[str, Any]:
    return {
        "task_id": impact.task_id,
        "bead_id": impact.bead_id,
        "bead_status": impact.bead_status,
        "reason": impact.reason,
    }


def _ack_to_dict(ack: Acknowledgement) -> dict[str, Any]:
    return {
        "task_id": ack.task_id,
        "bead_id": ack.bead_id,
        "bead_status": ack.bead_status,
        "acknowledged_at": ack.acknowledged_at,
    }


def _requirements_phrase(d: dict[str, Any]) -> str:
    renamed = d["renamed"]
    parts = [
        f"{len(d['modified'])} modified",
        f"{len(d['removed'])} removed",
        f"{len(d['added'])} added",
        f"{len(renamed)} renamed",
    ]
    return ", ".join(parts)


def _tasks_phrase(d: dict[str, Any]) -> str:
    return f"{len(d['added'])} added, {len(d['withdrawn'])} withdrawn"


# ---------------------------------------------------------------------------
# bd preflight (only reached when a delta carries task entries — FR-007b)
# ---------------------------------------------------------------------------


async def _bd_preflight_error(cwd: Path, client: BeadClient) -> str | None:
    reason = bd_ready_reason(cwd)
    if reason is not None:
        return BD_REASON_MESSAGES.get(reason, f"bd is not ready ({reason}).")
    if not await client.verify_available():
        return "The `bd` CLI is on PATH but is not responding (`bd --version` failed)."
    return None


async def _resolve_client(
    document: DeltaDocument, *, cwd: Path
) -> tuple[BeadClient | None, str | None]:
    """``(client, error)`` — *client* is ``None`` when *document* has no
    task entries (FR-007b: never needs bd) or bd preflight failed."""
    if not document.task_entries:
        return None, None
    client = BeadClient(cwd=cwd)
    error = await _bd_preflight_error(cwd, client)
    if error is not None:
        return None, error
    return client, None


# ---------------------------------------------------------------------------
# delta list
# ---------------------------------------------------------------------------


def _list_entries(directory: Path) -> list[tuple[Path, DeltaDocument | None, str]]:
    """``(path, document_or_none, raw_text)`` for every ``*.md`` in *directory*."""
    entries: list[tuple[Path, DeltaDocument | None, str]] = []
    for path in list_delta_files(directory):
        text = path.read_text(encoding="utf-8")
        try:
            document = parse_delta_md(text, path=path)
        except DeltaFormatError:
            document = None
        entries.append((path, document, text))
    return entries


def _feature_list_dict(feature_dir: Path) -> dict[str, Any]:
    pending: list[dict[str, Any]] = []
    for path, document, _text in _list_entries(feature_dir / "deltas"):
        if document is None:
            continue
        pending.append(
            {
                "delta": path.stem,
                "requirements": _document_requirements_dict(document),
                "tasks": _document_tasks_dict(document),
            }
        )
    applied: list[dict[str, Any]] = []
    for path, document, text in _list_entries(feature_dir / "deltas" / "archive"):
        if document is None:
            continue
        applied.append(
            {
                "delta": path.stem,
                "applied_at": extract_applied_at(text),
                "requirements": _document_requirements_dict(document),
                "tasks": _document_tasks_dict(document),
            }
        )
    return {"feature": feature_dir.name, "pending": pending, "applied": applied}


async def _run_list_json(feature: str | None, *, cwd: Path) -> None:
    verb = "delta.list"
    if feature is None:
        feature_dirs = _all_feature_dirs_with_deltas(cwd)
    else:
        try:
            resolution = resolve_feature(feature, cwd=cwd)
        except SpeckitError as exc:
            emit_json(JsonEnvelope.failure(verb, ErrorKind.NOT_FOUND, str(exc)))
            raise SystemExit(ExitCode.FAILURE) from exc
        if resolution.speckit_dir is None:
            emit_json(
                JsonEnvelope.failure(
                    verb,
                    ErrorKind.NOT_FOUND,
                    f"{feature!r} does not resolve to a Spec Kit feature",
                )
            )
            raise SystemExit(ExitCode.FAILURE)
        feature_dirs = [resolution.speckit_dir]

    features = [_feature_list_dict(d) for d in feature_dirs]
    emit_json(JsonEnvelope.success(verb, {"schema_version": 1, "features": features}))
    raise SystemExit(ExitCode.SUCCESS)


def _render_feature_list_human(feature_dir: Path) -> None:
    console.print(feature_dir.name)
    console.print()
    pending = list_delta_files(feature_dir / "deltas")
    if pending:
        console.print("  Pending")
        for path in pending:
            text = path.read_text(encoding="utf-8")
            try:
                document = parse_delta_md(text, path=path)
            except DeltaFormatError:
                console.print(f"    {path.stem:<28}  [red](malformed)[/red]")
                continue
            req = _document_requirements_dict(document)
            tasks = _document_tasks_dict(document)
            console.print(f"    {path.stem:<28}  {_requirements_phrase(req)}")
            if document.task_entries:
                console.print(f"    {'':<28}  {_tasks_phrase(tasks)} task entries")
        console.print()
    applied = list_delta_files(feature_dir / "deltas" / "archive")
    if applied:
        console.print("  Applied")
        for path in applied:
            text = path.read_text(encoding="utf-8")
            applied_at = extract_applied_at(text) or "?"
            try:
                document = parse_delta_md(text, path=path)
                req = _document_requirements_dict(document)
                summary = _requirements_phrase(req)
            except DeltaFormatError:
                summary = "?"
            console.print(f"    {path.stem:<28}  {applied_at:<12}  {summary}")
        console.print()
    if not pending and not applied:
        console.print("  (no deltas)")
        console.print()


async def _run_list_human(feature: str | None, *, cwd: Path) -> None:
    if feature is None:
        feature_dirs = _all_feature_dirs_with_deltas(cwd)
        if not feature_dirs:
            console.print("No Spec Kit features have a deltas/ directory.")
            raise SystemExit(ExitCode.SUCCESS)
    else:
        resolution = resolve_feature(feature, cwd=cwd)
        if resolution.speckit_dir is None:
            err_console.print(
                f"[red]Error:[/red] {feature!r} does not resolve to a Spec Kit feature"
            )
            raise SystemExit(ExitCode.FAILURE)
        feature_dirs = [resolution.speckit_dir]

    for feature_dir in feature_dirs:
        _render_feature_list_human(feature_dir)
    raise SystemExit(ExitCode.SUCCESS)


# ---------------------------------------------------------------------------
# delta validate
# ---------------------------------------------------------------------------


async def _run_validate_json(delta_arg: str, *, cwd: Path) -> None:
    verb = "delta.validate"
    try:
        document, _text, feature_dir, label = _resolve_and_parse(delta_arg, cwd=cwd)
    except DeltaFormatError as exc:
        emit_json(
            JsonEnvelope.failure(
                verb,
                ErrorKind.VALIDATION,
                str(exc),
                {
                    "problems": [
                        _problem_to_dict(Problem(exc.line, "document", exc.code, str(exc)))
                    ]
                },
            )
        )
        raise SystemExit(ExitCode.FAILURE) from exc
    except SpeckitError as exc:
        emit_json(JsonEnvelope.failure(verb, ErrorKind.NOT_FOUND, str(exc)))
        raise SystemExit(ExitCode.FAILURE) from exc

    section, phases = _load_target(feature_dir)
    problems = validate_delta(document, spec_section=section, tasks_phases=phases)
    if problems:
        emit_json(
            JsonEnvelope.failure(
                verb,
                ErrorKind.VALIDATION,
                f"{len(problems)} problem(s) in {label}",
                {"problems": [_problem_to_dict(p) for p in problems]},
            )
        )
        raise SystemExit(ExitCode.FAILURE)

    result = {
        "schema_version": 1,
        "delta": label,
        "requirements": _document_requirements_dict(document),
        "tasks": _document_tasks_dict(document),
    }
    emit_json(JsonEnvelope.success(verb, result))
    raise SystemExit(ExitCode.SUCCESS)


async def _run_validate_human(delta_arg: str, *, cwd: Path) -> None:
    with cli_error_handler():
        document, _text, feature_dir, label = _resolve_and_parse(delta_arg, cwd=cwd)
        section, phases = _load_target(feature_dir)
        problems = validate_delta(document, spec_section=section, tasks_phases=phases)

    if problems:
        err_console.print(f"[red]✗[/red] {label}\n")
        for problem in problems:
            err_console.print(f"  line {problem.line}   {problem.entry}: {problem.message}")
        raise SystemExit(ExitCode.FAILURE)

    console.print(f"[green]✓[/] {label}")
    console.print()
    req = _document_requirements_dict(document)
    console.print(f"  Requirements  {_requirements_phrase(req)}")
    if document.task_entries:
        tasks = _document_tasks_dict(document)
        console.print(f"  Tasks         {_tasks_phrase(tasks)}")
    raise SystemExit(ExitCode.SUCCESS)


# ---------------------------------------------------------------------------
# delta apply
# ---------------------------------------------------------------------------


async def _do_apply(
    delta_arg: str, *, cwd: Path, dry_run: bool, ack: tuple[str, ...]
) -> tuple[str, DeltaDocument, ApplyOutcome]:
    """Shared resolve -> preflight -> apply_delta path for both renderers.

    Raises:
        SpeckitError / DeltaFormatError: resolution/parse failure.
        DeltaValidationError / StaleAcknowledgementError: from apply_delta.
        BeadUnavailable (as a plain RuntimeError with ``.bd_message``):
            surfaced so each renderer can map it to its own error shape.
    """
    document, document_text, feature_dir, label = _resolve_and_parse(delta_arg, cwd=cwd)

    if document.is_applied:
        return (
            label,
            document,
            ApplyOutcome(status="already_applied", applied_at=extract_applied_at(document_text)),
        )

    client, bd_error = await _resolve_client(document, cwd=cwd)
    if bd_error is not None:
        raise _BdUnavailableError(bd_error)

    outcome = await apply_delta(
        document,
        document_text=document_text,
        feature_dir=feature_dir,
        client=client,
        acknowledged_task_ids=frozenset(ack),
        dry_run=dry_run,
    )
    return label, document, outcome


class _BdUnavailableError(RuntimeError):
    def __init__(self, message: str) -> None:
        self.bd_message = message
        super().__init__(message)


async def _run_apply_json(
    delta_arg: str, *, cwd: Path, dry_run: bool, ack: tuple[str, ...]
) -> None:
    verb = "delta.dry-run" if dry_run else "delta.apply"
    try:
        label, _document, outcome = await _do_apply(delta_arg, cwd=cwd, dry_run=dry_run, ack=ack)
    except DeltaFormatError as exc:
        emit_json(
            JsonEnvelope.failure(
                verb,
                ErrorKind.VALIDATION,
                str(exc),
                {
                    "problems": [
                        _problem_to_dict(Problem(exc.line, "document", exc.code, str(exc)))
                    ]
                },
            )
        )
        raise SystemExit(ExitCode.FAILURE) from exc
    except _BdUnavailableError as exc:
        emit_json(JsonEnvelope.failure(verb, ErrorKind.BD_UNAVAILABLE, exc.bd_message))
        raise SystemExit(ExitCode.FAILURE) from exc
    except DeltaValidationError as exc:
        emit_json(
            JsonEnvelope.failure(
                verb,
                ErrorKind.VALIDATION,
                str(exc),
                {"problems": [_problem_to_dict(p) for p in exc.problems]},
            )
        )
        raise SystemExit(ExitCode.FAILURE) from exc
    except StaleAcknowledgementError as exc:
        emit_json(
            JsonEnvelope.failure(
                verb, ErrorKind.VALIDATION, str(exc), {"stale_acks": list(exc.stale_task_ids)}
            )
        )
        raise SystemExit(ExitCode.FAILURE) from exc
    except SpeckitError as exc:
        # Must stay last: DeltaFormatError/DeltaValidationError/
        # StaleAcknowledgementError all subclass SpeckitError, and the
        # first matching `except` wins — a generic clause earlier would
        # silently swallow every specific one above as NOT_FOUND.
        emit_json(JsonEnvelope.failure(verb, ErrorKind.NOT_FOUND, str(exc)))
        raise SystemExit(ExitCode.FAILURE) from exc

    if outcome.status == "already_applied":
        emit_json(
            JsonEnvelope.success(verb, {"already_applied": True, "applied_at": outcome.applied_at})
        )
        raise SystemExit(ExitCode.SUCCESS)

    if outcome.status == "blocked":
        acked = set(ack)
        outstanding = [i.task_id for i in outcome.impacts if i.task_id and i.task_id not in acked]
        emit_json(
            JsonEnvelope.failure(
                verb,
                ErrorKind.CONFIRMATION_REQUIRED,
                f"{len(outcome.impacts)} impact(s) must be acknowledged before applying",
                {
                    "impacts": [_impact_to_dict(i) for i in outcome.impacts],
                    "acknowledged": sorted(acked),
                    "outstanding": outstanding,
                },
            )
        )
        raise SystemExit(ExitCode.FAILURE)

    if outcome.status == "dry_run":
        result = {
            "schema_version": 1,
            "delta": label,
            "requirements": _requirements_dict(outcome.requirements),
            "tasks": _tasks_dict(outcome.tasks),
            "impacts": [_impact_to_dict(i) for i in outcome.impacts],
            "would_block": outcome.would_block,
            "wrote_nothing": True,
        }
        emit_json(JsonEnvelope.success(verb, result))
        raise SystemExit(ExitCode.SUCCESS)

    result = {
        "schema_version": 1,
        "delta": label,
        "applied_at": outcome.applied_at,
        "requirements": _requirements_dict(outcome.requirements),
        "tasks": _tasks_dict(outcome.tasks),
        "acknowledgements": [_ack_to_dict(a) for a in outcome.acknowledgements],
        "declared_reductions": list(outcome.declared_reductions),
        "archived_to": str(outcome.archived_to) if outcome.archived_to else None,
    }
    emit_json(JsonEnvelope.success(verb, result))
    raise SystemExit(ExitCode.SUCCESS)


async def _run_apply_human(
    delta_arg: str, *, cwd: Path, dry_run: bool, ack: tuple[str, ...]
) -> None:
    try:
        label, _document, outcome = await _do_apply(delta_arg, cwd=cwd, dry_run=dry_run, ack=ack)
    except _BdUnavailableError as exc:
        err_console.print(f"[red]Error:[/red] {exc.bd_message}")
        raise SystemExit(ExitCode.FAILURE) from exc
    except DeltaValidationError as exc:
        err_console.print(f"[red]✗[/red] {delta_arg}\n")
        for problem in exc.problems:
            err_console.print(f"  line {problem.line}   {problem.entry}: {problem.message}")
        raise SystemExit(ExitCode.FAILURE) from exc
    except StaleAcknowledgementError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(ExitCode.FAILURE) from exc
    except (SpeckitError, DeltaFormatError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(ExitCode.FAILURE) from exc

    if outcome.status == "already_applied":
        console.print(f"[green]✓[/] Already applied {outcome.applied_at} — nothing to do.")
        raise SystemExit(ExitCode.SUCCESS)

    if outcome.status == "blocked":
        acked = set(ack)
        console.print(f"Impacts ({len(outcome.impacts)}) — nothing has been written:\n")
        for impact in outcome.impacts:
            name = impact.task_id or "(unstamped bead)"
            console.print(f"  {name:<8} bead {impact.bead_id:<10} {impact.bead_status}")
        outstanding = [i.task_id for i in outcome.impacts if i.task_id and i.task_id not in acked]
        if outstanding:
            console.print("\nAcknowledge each impact you accept, then re-run:")
            ack_flags = " ".join(f"--ack {tid}" for tid in outstanding)
            console.print(f"  maverick delta apply {delta_arg} {ack_flags}")
        unstamped = [i for i in outcome.impacts if not i.task_id]
        if unstamped:
            console.print(
                "\n[yellow]Note:[/yellow] the unstamped bead(s) above carry no task id, so "
                "no --ack can clear them — resolve them directly in bd (stamp a "
                "speckit_task_id, or close the bead) before re-running."
            )
        raise SystemExit(ExitCode.FAILURE)

    if outcome.status == "dry_run":
        console.print("Would rewrite:")
        req = outcome.requirements
        if req.added or req.modified or req.removed or req.renamed:
            console.print(f"  spec.md    {_requirements_phrase(_requirements_dict(req))}")
        tasks = outcome.tasks
        if tasks.added or tasks.withdrawn:
            console.print(f"  tasks.md   {_tasks_change_phrase(tasks)}")
        if outcome.impacts:
            status = "would block" if outcome.would_block else "clear"
            console.print(f"\nImpacts ({len(outcome.impacts)}) — {status}:")
            for impact in outcome.impacts:
                name = impact.task_id or "(unstamped bead)"
                console.print(f"  {name:<8} bead {impact.bead_id:<10} {impact.bead_status}")
        raise SystemExit(ExitCode.SUCCESS)

    console.print(f"✓ spec.md    {_requirements_phrase(_requirements_dict(outcome.requirements))}")
    if outcome.tasks.added or outcome.tasks.withdrawn:
        console.print(f"  tasks.md   {_tasks_change_phrase(outcome.tasks)}")
    else:
        console.print("  tasks.md   unchanged")
    console.print(f"✓ archived to {outcome.archived_to}")
    if outcome.tasks.added or outcome.tasks.withdrawn:
        console.print()
        console.print(f"  Next: maverick refuel {label.split('/')[0]} --speckit")
        added_n, withdrawn_n = len(outcome.tasks.added), len(outcome.tasks.withdrawn)
        console.print(f"        (+{added_n} bead, -{withdrawn_n} bead closed)")
    raise SystemExit(ExitCode.SUCCESS)


# ---------------------------------------------------------------------------
# Click wiring
# ---------------------------------------------------------------------------


@click.group()
def delta() -> None:
    """Deterministic delta-document layer for changing an already-shipped spec.

    A delta document states requirement operations (ADDED / MODIFIED /
    REMOVED / RENAMED) and, where work changes, task entries.
    ``maverick refuel`` is unaffected by this command's existence — a
    delta reaches the beads only via an explicit ``delta apply``
    followed by an ordinary refuel run (FR-027). Zero model calls on
    every path.
    """


@delta.command("list")
@click.argument("feature", required=False)
@click.option(
    "--json", "json_output", is_flag=True, default=False, help="Emit JSON instead of Rich output."
)
@async_command
async def delta_list(feature: str | None, json_output: bool) -> None:
    """List pending and applied deltas.

    With no FEATURE, lists every feature that has a ``deltas/`` directory.
    """
    cwd = Path.cwd().resolve()
    if json_output:
        await _run_list_json(feature, cwd=cwd)
        return
    await _run_list_human(feature, cwd=cwd)


@delta.command("validate")
@click.argument("delta_arg", metavar="DELTA")
@click.option(
    "--json", "json_output", is_flag=True, default=False, help="Emit JSON instead of Rich output."
)
@async_command
async def delta_validate(delta_arg: str, json_output: bool) -> None:
    """Validate a delta document against its target spec. Writes nothing.

    DELTA is ``<feature>/<delta-slug>`` or a path to the document.
    """
    cwd = Path.cwd().resolve()
    if json_output:
        await _run_validate_json(delta_arg, cwd=cwd)
        return
    await _run_validate_human(delta_arg, cwd=cwd)


@delta.command("apply")
@click.argument("delta_arg", metavar="DELTA")
@click.option("--dry-run", is_flag=True, default=False, help="Report every change; write nothing.")
@click.option(
    "--ack",
    "ack",
    multiple=True,
    metavar="TASK_ID",
    help="Acknowledge a blocking impact by task id. Repeatable. Every impact must be named.",
)
@click.option(
    "--json", "json_output", is_flag=True, default=False, help="Emit JSON instead of Rich output."
)
@async_command
async def delta_apply(
    delta_arg: str, dry_run: bool, ack: tuple[str, ...], json_output: bool
) -> None:
    """Apply a delta: rewrite spec.md/tasks.md, archive it. Writes no beads.

    DELTA is ``<feature>/<delta-slug>`` or a path to the document.
    Refuses (writing nothing) when a named task's bead is already in
    flight or closed — acknowledge each with a repeated ``--ack``.
    """
    cwd = Path.cwd().resolve()
    if json_output:
        await _run_apply_json(delta_arg, cwd=cwd, dry_run=dry_run, ack=ack)
        return
    await _run_apply_human(delta_arg, cwd=cwd, dry_run=dry_run, ack=ack)
