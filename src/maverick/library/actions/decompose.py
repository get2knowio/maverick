"""Decomposition actions for RefuelMaverickWorkflow.

Actions for gathering codebase context and building decomposition prompts.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.briefing.models import BriefingDocument
    from maverick.flight.models import WorkUnit
    from maverick.workflows.refuel_maverick.models import WorkUnitSpec

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FileContent:
    """Content of a single file for codebase context.

    Attributes:
        path: Relative file path.
        content: File text content.
    """

    path: str
    content: str


@dataclass(frozen=True, slots=True)
class CodebaseContext:
    """Context gathered from in-scope files for the decomposition agent.

    Attributes:
        files: Tuple of file contents.
        missing_files: Files that couldn't be read.
        total_size: Total bytes of content.
    """

    files: tuple[FileContent, ...]
    missing_files: tuple[str, ...]
    total_size: int


def _read_file_sync(file_path: Path) -> tuple[str, str | None]:
    """Read a file synchronously. Returns (content, error_msg)."""
    try:
        content = file_path.read_text(encoding="utf-8")
        return content, None
    except FileNotFoundError:
        return "", f"File not found: {file_path}"
    except PermissionError:
        return "", f"Permission denied: {file_path}"
    except IsADirectoryError:
        return "", f"Is a directory: {file_path}"
    except UnicodeDecodeError:
        return "", f"Binary file (not readable as text): {file_path}"
    except OSError as e:
        return "", f"Cannot read {file_path}: {e}"


_BACKTICK_PATH_RE = re.compile(r"^`([^`]+)`")
_PATH_LIKE_RE = re.compile(r"^(\S+\.\w+|\S+/)")


def _extract_path_from_scope_item(raw: str) -> str:
    """Extract a bare file/directory path from a possibly descriptive scope item.

    AI agents sometimes produce scope items like:
        ``\u0060src/greet/cli.py\u0060 — CLI entry point with argument parsing``
    instead of bare paths. This function extracts the path portion.

    Extraction rules (first match wins):
    1. Leading backtick-wrapped segment: ``\u0060path\u0060 ...`` → ``path``
    2. Leading path-like token (contains ``/`` or ``.ext``): ``path — desc`` → ``path``
    3. Fallback: return the original string stripped.

    Args:
        raw: Raw scope item string from the flight plan.

    Returns:
        Extracted path string.
    """
    stripped = raw.strip()

    # Rule 1: backtick-wrapped leading path
    m = _BACKTICK_PATH_RE.match(stripped)
    if m:
        return m.group(1).strip()

    # Rule 2: leading path-like token before a separator
    m = _PATH_LIKE_RE.match(stripped)
    if m:
        return m.group(1).strip()

    return stripped


def _expand_path(path_str: str, cwd: Path) -> list[Path]:
    """Expand a path string to a list of file paths.

    If path_str refers to a directory, expands to all contained files.
    If path_str refers to a file, returns just that file.
    Returns empty list if path doesn't exist.

    Args:
        path_str: File or directory path string.
        cwd: Working directory for resolving relative paths.

    Returns:
        List of resolved file paths.
    """
    # Extract bare path from descriptive scope items (e.g. "`src/foo.py` — description")
    cleaned = _extract_path_from_scope_item(path_str)
    if cleaned != path_str:
        logger.debug("scope_item_path_extracted", raw=path_str, extracted=cleaned)
    p = (cwd / cleaned) if not Path(cleaned).is_absolute() else Path(cleaned)

    if p.is_dir():
        # Expand directory to all files recursively
        return [f for f in p.rglob("*") if f.is_file()]
    elif p.exists():
        return [p]
    else:
        return []


async def gather_codebase_context(
    in_scope: tuple[str, ...],
    cwd: Path | None = None,
) -> CodebaseContext:
    """Gather file contents for in-scope paths.

    Reads each file listed in in_scope. Directories are expanded to all
    contained files. Missing files and unreadable files are noted as warnings.

    Args:
        in_scope: Tuple of file/directory paths from FlightPlan.scope.in_scope.
        cwd: Working directory for resolving relative paths. Defaults to cwd.

    Returns:
        CodebaseContext with files read, missing files noted.
    """
    resolved_cwd = cwd if cwd is not None else Path.cwd()

    # Expand all paths to individual files
    all_paths: list[tuple[str, Path]] = []
    missing: list[str] = []

    for path_str in in_scope:
        expanded = await asyncio.to_thread(_expand_path, path_str, resolved_cwd)
        if expanded:
            for file_path in expanded:
                # Use original path_str prefix for display in dirs, else path_str
                try:
                    rel = file_path.relative_to(resolved_cwd)
                    all_paths.append((str(rel), file_path))
                except ValueError:
                    all_paths.append((str(file_path), file_path))
        else:
            missing.append(path_str)
            logger.debug("in_scope_path_not_found", path=path_str)

    if not all_paths:
        logger.info("no_in_scope_files", in_scope_count=len(in_scope))
        return CodebaseContext(files=(), missing_files=tuple(missing), total_size=0)

    logger.info("gathering_codebase_context", file_count=len(all_paths))

    # Read all files concurrently using asyncio.to_thread
    async def _read(display_path: str, file_path: Path) -> FileContent | str:
        content, error = await asyncio.to_thread(_read_file_sync, file_path)
        if error:
            return error  # str indicates missing/unreadable
        return FileContent(path=display_path, content=content)

    results = await asyncio.gather(*[_read(dp, fp) for dp, fp in all_paths])

    files: list[FileContent] = []
    for i, result in enumerate(results):
        if isinstance(result, str):
            # Error message
            display_path = all_paths[i][0]
            missing.append(display_path)
            logger.warning("file_read_failed", path=display_path, error=result)
        else:
            files.append(result)

    total_size = sum(len(f.content) for f in files)
    logger.info(
        "codebase_context_gathered",
        file_count=len(files),
        missing_count=len(missing),
        total_size=total_size,
    )

    return CodebaseContext(
        files=tuple(files),
        missing_files=tuple(missing),
        total_size=total_size,
    )


def _format_codebase_context(context: CodebaseContext) -> str:
    """Format CodebaseContext as a string for the agent prompt.

    Args:
        context: Gathered codebase context.

    Returns:
        Formatted string representation of the context.
    """
    if not context.files:
        if context.missing_files:
            return (
                f"No files could be read. Missing: {', '.join(context.missing_files)}"
            )
        return "No in-scope files specified."

    parts: list[str] = []
    for fc in context.files:
        parts.append(f"### File: {fc.path}\n\n```\n{fc.content}\n```")

    result = "\n\n".join(parts)
    if context.missing_files:
        result += "\n\n### Missing Files\n\n" + "\n".join(
            f"- {p}" for p in context.missing_files
        )

    return result


def _format_briefing_section(briefing: BriefingDocument) -> str:
    """Format a BriefingDocument as a prompt section.

    Args:
        briefing: Synthesized briefing document.

    Returns:
        Markdown-formatted briefing analysis section.
    """
    parts: list[str] = []
    parts.append("## Briefing Room Analysis")
    parts.append("")

    if briefing.key_decisions:
        parts.append("### Key Architecture Decisions")
        parts.append("")
        for decision in briefing.key_decisions:
            parts.append(f"- {decision}")
        parts.append("")

    if briefing.structuralist.entities:
        parts.append("### Data Model")
        parts.append("")
        for entity in briefing.structuralist.entities:
            fields_str = ", ".join(entity.fields) if entity.fields else "none"
            parts.append(f"- **{entity.name}** (`{entity.module_path}`): {fields_str}")
        parts.append("")

    if briefing.key_risks:
        parts.append("### Key Risks")
        parts.append("")
        for risk in briefing.key_risks:
            parts.append(f"- {risk}")
        parts.append("")

    if briefing.open_questions:
        parts.append("### Open Questions")
        parts.append("")
        for question in briefing.open_questions:
            parts.append(f"- {question}")
        parts.append("")

    return "\n".join(parts)


def build_decomposition_prompt(
    flight_plan_content: str,
    context: CodebaseContext,
    briefing: BriefingDocument | None = None,
) -> str:
    """Build the decomposition agent prompt.

    Args:
        flight_plan_content: Raw flight plan markdown content.
        context: Gathered codebase context.
        briefing: Optional synthesized briefing document from the briefing room.

    Returns:
        Formatted prompt string for the decomposition agent.
    """
    codebase_section = _format_codebase_context(context)

    instructions = "\n".join(
        [
            "- Produce 3-15 work units (exceed only with justification)",
            "- Each work unit = one logical change",
            "- File scopes must include ALL protect boundaries from the flight"  # noqa: E501
            " plan's scope.boundaries in every work unit's file_scope.protect",
            "- Every acceptance criterion should trace to a flight plan success"  # noqa: E501
            " criterion (SC-### where ### is the 1-based index of the criterion)",
            "- Verification commands must be concrete and runnable",
            "- Use depends_on to express ordering constraints"
            " (list of work unit IDs that must complete first)",
            "- Assign parallel_group labels to work units that can execute"
            " concurrently within the same dependency tier",
            "- IDs must be kebab-case (lowercase letters, digits, and hyphens only)",
            "- Sequence numbers must be sequential starting from 1",
            "- instructions field should contain detailed implementation guidance",
            "",
            "## CRITICAL: Output Format",
            "You MUST output your result as a single JSON object in a ```json"
            " fenced code block. Do NOT write any files. The JSON must match"
            " this schema exactly:",
            '{"work_units": [{"id": "kebab-id", "sequence": 1,'
            ' "parallel_group": null, "depends_on": [],'
            ' "task": "description", "acceptance_criteria":'
            ' [{"text": "criterion", "trace_ref": "SC-001"}],'
            ' "file_scope": {"create": [], "modify": [], "protect": []},'
            ' "instructions": "...", "verification": ["cmd1"]}],'
            ' "rationale": "explanation"}',
        ]
    )

    prompt = (
        "You are a software decomposition expert. Given a flight plan and"
        " codebase context, produce an ordered set of small, focused work units."
        f"\n\n## Flight Plan\n\n{flight_plan_content}"
        f"\n\n## Codebase Context\n\n{codebase_section}"
    )

    if briefing is not None:
        prompt += f"\n\n{_format_briefing_section(briefing)}"

    prompt += f"\n\n## Instructions\n{instructions}"

    return prompt


def convert_specs_to_work_units(
    specs: list[WorkUnitSpec],
    flight_plan_name: str,
    source_path: Path | None = None,
) -> list[WorkUnit]:
    """Convert WorkUnitSpec list to full WorkUnit models.

    Sets flight_plan and source_path fields that the agent doesn't produce.

    Args:
        specs: WorkUnitSpec list from decomposition agent.
        flight_plan_name: Name of the parent flight plan.
        source_path: Optional source path for each work unit.

    Returns:
        List of WorkUnit models with all fields populated.
    """
    from maverick.flight.models import AcceptanceCriterion, FileScope, WorkUnit

    units = []
    for spec in specs:
        unit = WorkUnit(
            id=spec.id,
            flight_plan=flight_plan_name,
            sequence=spec.sequence,
            parallel_group=spec.parallel_group,
            depends_on=tuple(spec.depends_on),
            task=spec.task,
            acceptance_criteria=tuple(
                AcceptanceCriterion(text=ac.text, trace_ref=ac.trace_ref)
                for ac in spec.acceptance_criteria
            ),
            file_scope=FileScope(
                create=tuple(spec.file_scope.create),
                modify=tuple(spec.file_scope.modify),
                protect=tuple(spec.file_scope.protect),
            ),
            instructions=spec.instructions,
            verification=tuple(spec.verification),
            source_path=source_path,
        )
        units.append(unit)
    return units


def validate_decomposition(
    specs: list[WorkUnitSpec],
    success_criteria_count: int,
) -> list[str]:
    """Validate the decomposed work units.

    Checks:
    - Acyclic dependency graph via resolve_execution_order (cycle detection)
    - Unique work unit IDs
    - Dangling depends_on references
    - SC coverage (warnings only, non-blocking)

    Args:
        specs: List of WorkUnitSpec from decomposition agent.
        success_criteria_count: Number of success criteria in flight plan.

    Returns:
        List of coverage warning strings (non-blocking).

    Raises:
        ValueError: If circular dependency or dangling depends_on detected.
    """
    from maverick.flight.errors import WorkUnitDependencyError
    from maverick.flight.resolver import resolve_execution_order

    # Convert specs to WorkUnit models for dependency validation
    work_units = convert_specs_to_work_units(specs, flight_plan_name="validation")

    # Use resolve_execution_order for cycle detection and dangling reference detection
    try:
        resolve_execution_order(work_units)
    except WorkUnitDependencyError as e:
        raise ValueError(str(e)) from e

    # Check SC coverage (warning-level)
    warnings: list[str] = []
    if success_criteria_count > 0:
        covered_refs: set[str] = set()
        for spec in specs:
            for ac in spec.acceptance_criteria:
                if ac.trace_ref:
                    covered_refs.add(ac.trace_ref)

        for i in range(1, success_criteria_count + 1):
            ref = f"SC-{i:03d}"
            if ref not in covered_refs:
                warning = f"SC-{i:03d} not explicitly covered by any work unit"
                warnings.append(warning)
                logger.warning("sc_not_covered", ref=ref)

    return warnings
