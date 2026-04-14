"""Open bead analysis for cross-flight-plan dependency detection.

Queries open epics and their work beads, loads file scope data from
persisted work unit files, and identifies overlap with a new flight
plan's in-scope files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class OpenEpicInfo:
    """Summary of an open epic."""

    epic_id: str
    title: str
    flight_plan_name: str
    status: str
    open_bead_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "epic_id": self.epic_id,
            "title": self.title,
            "flight_plan_name": self.flight_plan_name,
            "status": self.status,
            "open_bead_count": self.open_bead_count,
        }


@dataclass(frozen=True, slots=True)
class FileOverlap:
    """A file path that overlaps between an open epic and the new plan."""

    file_path: str
    epic_flight_plan_name: str
    epic_id: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "file_path": self.file_path,
            "epic_flight_plan_name": self.epic_flight_plan_name,
            "epic_id": self.epic_id,
        }


@dataclass(frozen=True, slots=True)
class OpenBeadAnalysisResult:
    """Result of analyzing open beads for file scope overlap."""

    open_epics: tuple[OpenEpicInfo, ...] = ()
    file_overlaps: tuple[FileOverlap, ...] = ()
    total_open_beads: int = 0
    overlap_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "open_epics": [e.to_dict() for e in self.open_epics],
            "file_overlaps": [o.to_dict() for o in self.file_overlaps],
            "total_open_beads": self.total_open_beads,
            "overlap_count": self.overlap_count,
        }

    def format_for_prompt(self) -> str:
        """Format as a prompt section for briefing agents.

        Returns:
            Markdown string describing open epics and file overlaps,
            or empty string if no open epics.
        """
        if not self.open_epics:
            return ""

        lines: list[str] = [
            "## Open Work Beads (Cross-Plan Context)",
            "",
            "The following open epics from other flight plans are in progress:",
            "",
        ]

        for epic in self.open_epics:
            lines.append(
                f"- **{epic.flight_plan_name}** "
                f"({epic.open_bead_count} open beads, status: {epic.status})"
            )
        lines.append("")

        if self.file_overlaps:
            lines.append("### File Scope Overlaps")
            lines.append("")
            lines.append("These files are in-scope for both this plan and an open epic:")
            lines.append("")
            # Group by epic
            by_epic: dict[str, list[str]] = {}
            for overlap in self.file_overlaps:
                by_epic.setdefault(overlap.epic_flight_plan_name, []).append(overlap.file_path)
            for plan_name, files in by_epic.items():
                lines.append(f"**{plan_name}**:")
                for f in files:
                    lines.append(f"  - `{f}`")
            lines.append("")
            lines.append(
                "Consider whether this plan should depend on any of these "
                "flight plans to avoid merge conflicts or integration issues."
            )
        else:
            lines.append("No file scope overlaps detected with open epics.")

        return "\n".join(lines)


def _normalize_scope_path(path: str) -> str:
    """Strip backtick fences and inline annotations from scope paths.

    Flight plan in-scope items may look like:
        `src/foo.py` — CLI entry point

    This returns just ``src/foo.py``.
    """
    path = path.strip()
    # Remove backtick wrapping
    if path.startswith("`") and "`" in path[1:]:
        path = path[1 : path.index("`", 1)]
    # Remove trailing annotations like " — description"
    for sep in (" — ", " - ", " -- "):
        if sep in path:
            path = path[: path.index(sep)]
    return path.strip()


async def analyze_open_beads(
    new_plan_in_scope: tuple[str, ...],
    cwd: Path | None = None,
) -> OpenBeadAnalysisResult:
    """Analyze open beads for file scope overlap with a new flight plan.

    Steps:
    1. Query all epics via BeadClient.query("type=epic")
    2. For each non-closed epic, get details (flight_plan_name from state)
    3. Load work unit files from ``.maverick/plans/<flight_plan_name>/``
    4. Compare file scopes against new_plan_in_scope
    5. Return overlapping files grouped by epic

    Args:
        new_plan_in_scope: In-scope file paths from the new flight plan.
        cwd: Working directory for bd commands and file lookups.

    Returns:
        OpenBeadAnalysisResult with overlap information.
    """
    from maverick.beads.client import BeadClient
    from maverick.flight.loader import WorkUnitFile

    effective_cwd = cwd or Path.cwd()
    client = BeadClient(cwd=effective_cwd)

    # Normalize new plan's in-scope paths for comparison
    new_scope_set: set[str] = {_normalize_scope_path(p) for p in new_plan_in_scope}

    try:
        epics = await client.query("type=epic")
    except Exception as exc:
        logger.debug("analyze_open_beads_query_failed", error=str(exc))
        return OpenBeadAnalysisResult()

    open_epics: list[OpenEpicInfo] = []
    file_overlaps: list[FileOverlap] = []
    total_open = 0

    for epic_summary in epics:
        if epic_summary.status == "closed":
            continue

        # Get details for flight_plan_name
        try:
            details = await client.show(epic_summary.id)
        except Exception:
            continue

        fp_name = details.state.get("flight_plan_name", "")
        if not fp_name:
            continue

        # Count open children
        try:
            children = await client.children(epic_summary.id)
            open_children = [c for c in children if c.status != "closed"]
            open_count = len(open_children)
        except Exception:
            open_count = 0

        total_open += open_count

        open_epics.append(
            OpenEpicInfo(
                epic_id=epic_summary.id,
                title=epic_summary.title,
                flight_plan_name=fp_name,
                status=epic_summary.status,
                open_bead_count=open_count,
            )
        )

        # Load work unit files to get file scopes
        plan_dir = effective_cwd / ".maverick" / "plans" / fp_name
        if not plan_dir.is_dir():
            continue

        try:
            work_units = WorkUnitFile.load_directory(plan_dir)
        except Exception as exc:
            logger.debug("load_work_units_failed", plan=fp_name, error=str(exc))
            continue

        # Collect all file paths from work unit file scopes
        epic_files: set[str] = set()
        for wu in work_units:
            epic_files.update(wu.file_scope.create)
            epic_files.update(wu.file_scope.modify)

        # Check overlap with new plan
        overlap = new_scope_set & epic_files
        for file_path in sorted(overlap):
            file_overlaps.append(
                FileOverlap(
                    file_path=file_path,
                    epic_flight_plan_name=fp_name,
                    epic_id=epic_summary.id,
                )
            )

    return OpenBeadAnalysisResult(
        open_epics=tuple(open_epics),
        file_overlaps=tuple(file_overlaps),
        total_open_beads=total_open,
        overlap_count=len(file_overlaps),
    )
