"""Plan-file parsing helpers for the fly-beads workflow.

Work-unit markdown sections, file-scope extraction, and validation
command building. Pure functions — no ACP, no subprocesses.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.config import ValidationConfig

logger = get_logger(__name__)


def _build_validation_commands(
    vc: ValidationConfig,
) -> dict[str, tuple[str, ...]]:
    """Convert ValidationConfig to the dict for run_independent_gate."""
    commands: dict[str, tuple[str, ...]] = {}
    if vc.format_cmd:
        commands["format"] = tuple(vc.format_cmd)
    if vc.lint_cmd:
        commands["lint"] = tuple(vc.lint_cmd)
    if vc.typecheck_cmd:
        commands["typecheck"] = tuple(vc.typecheck_cmd)
    if vc.test_cmd:
        commands["test"] = tuple(vc.test_cmd)
    return commands


def _parse_work_unit_sections(
    description: str,
) -> dict[str, str]:
    """Parse a work-unit markdown description into named sections.

    Splits on ``## `` headings and returns a dict keyed by
    lower-cased heading (e.g. ``"task"``, ``"acceptance criteria"``,
    ``"file scope"``, ``"instructions"``, ``"verification"``).
    """
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in description.split("\n"):
        if line.startswith("## "):
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[3:].strip().lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def _parse_file_scope(
    file_scope_text: str,
) -> tuple[list[str], list[str], list[str]]:
    """Parse ``## File Scope`` into create, modify, protect lists."""
    create: list[str] = []
    modify: list[str] = []
    protect: list[str] = []

    current = None
    for line in file_scope_text.split("\n"):
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("### create"):
            current = create
        elif low.startswith("### modify"):
            current = modify
        elif low.startswith("### protect"):
            current = protect
        elif stripped.startswith("- ") and current is not None:
            current.append(stripped[2:].strip())

    return create, modify, protect


def _parse_verification_commands(
    verification_text: str,
) -> list[str]:
    """Extract shell commands from ``## Verification``."""
    commands: list[str] = []
    for line in verification_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        # Skip empty lines and prose (commands start with a tool name)
        if not stripped or stripped[0].isupper():
            continue
        commands.append(stripped)
    return commands


def load_work_unit_files(
    flight_plan_name: str | None,
    cwd: Path | None = None,
) -> dict[str, str]:
    """Load all work unit markdown files from the plan directory.

    Returns a dict mapping work-unit ID (from YAML frontmatter) to
    the full markdown body (after frontmatter). Used to enrich bead
    descriptions with structured sections (File Scope, Acceptance
    Criteria, etc.) that the bead database truncates.

    Args:
        flight_plan_name: Plan directory name under ``.maverick/plans/``.
        cwd: Repo root containing ``.maverick/plans/``. Defaults to
            process cwd; under Architecture A this should be the
            workspace path.
    """
    result: dict[str, str] = {}
    if not flight_plan_name:
        return result
    base = cwd or Path.cwd()
    plan_dir = base / ".maverick" / "plans" / flight_plan_name
    if not plan_dir.is_dir():
        return result

    skip = {"flight-plan.md", "briefing.md", "refuel-briefing.md"}
    for md_file in sorted(plan_dir.glob("*.md")):
        if md_file.name in skip:
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
            wu_id = ""
            for line in content.split("\n"):
                if line.startswith("work-unit:"):
                    wu_id = line.split(":", 1)[1].strip()
                    break
            if wu_id:
                parts = content.split("---", 2)
                body = parts[2].strip() if len(parts) >= 3 else content
                result[wu_id] = body
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("work_unit_file_unreadable", file=str(md_file), error=str(exc))
            continue

    return result


def match_bead_to_work_unit(
    bead_title: str,
    work_units: dict[str, str],
) -> str | None:
    """Match a bead title to a work unit markdown body.

    The bead title from the database often starts with the work unit's
    task description. We match by checking if the work-unit ID
    (kebab-case) appears in the bead title (with hyphens or spaces).
    """
    title_lower = bead_title.lower()
    for wu_id, body in work_units.items():
        if wu_id in title_lower:
            return body
        if wu_id.replace("-", " ") in title_lower:
            return body
        sections = _parse_work_unit_sections(body)
        task = sections.get("task", "")
        if task:
            task_prefix = task[:40].lower().strip()
            if task_prefix and task_prefix in title_lower:
                return body
    return None


def load_briefing_context(
    flight_plan_name: str | None,
    cwd: Path | None = None,
) -> str | None:
    """Read briefing markdown from plan directory.

    Args:
        flight_plan_name: Plan directory name under ``.maverick/plans/``.
        cwd: Repo root containing ``.maverick/plans/``. Defaults to
            process cwd.

    Returns:
        Briefing text or None if not found.
    """
    if not flight_plan_name:
        return None
    base = cwd or Path.cwd()
    plan_dir = base / ".maverick" / "plans" / flight_plan_name
    for candidate in ("refuel-briefing.md", "briefing.md"):
        briefing_path = plan_dir / candidate
        if briefing_path.is_file():
            try:
                return briefing_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("briefing_file_unreadable", file=str(briefing_path), error=str(exc))
    return None
