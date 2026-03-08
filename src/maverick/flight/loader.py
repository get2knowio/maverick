"""File loaders for Flight Plan and Work Unit documents.

Provides synchronous and asynchronous loaders that read Markdown+YAML
files from disk, parse them, and construct frozen Pydantic models.

Public API:
    FlightPlanFile.load(path) -> FlightPlan
    FlightPlanFile.aload(path) -> Awaitable[FlightPlan]
    WorkUnitFile.load(path) -> WorkUnit
    WorkUnitFile.aload(path) -> Awaitable[WorkUnit]
    WorkUnitFile.load_directory(directory) -> list[WorkUnit]
    WorkUnitFile.aload_directory(directory) -> Awaitable[list[WorkUnit]]
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import ValidationError

from maverick.flight.errors import (
    FlightPlanNotFoundError,
    FlightPlanParseError,
    FlightPlanValidationError,
    WorkUnitNotFoundError,
    WorkUnitValidationError,
)
from maverick.flight.models import (
    AcceptanceCriterion,
    FileScope,
    FlightPlan,
    Scope,
    SuccessCriterion,
    WorkUnit,
)
from maverick.flight.parser import (
    parse_flight_plan_sections,
    parse_frontmatter,
    parse_work_unit_sections,
)
from maverick.logging import get_logger

logger = get_logger(__name__)

# Pattern for work unit files: ###-slug.md
_WORK_UNIT_GLOB = "[0-9][0-9][0-9]-*.md"


# ---------------------------------------------------------------------------
# FlightPlanFile
# ---------------------------------------------------------------------------


class FlightPlanFile:
    """Loader for Flight Plan Markdown+YAML files.

    All methods are class methods; no instance state is maintained.
    """

    @classmethod
    def load(cls, path: Path) -> FlightPlan:
        """Load a FlightPlan from a Markdown file.

        Args:
            path: Path to the ``.md`` file.

        Returns:
            Parsed and validated FlightPlan model with source_path set.

        Raises:
            FlightPlanNotFoundError: When the file does not exist.
            FlightPlanParseError: When the Markdown/YAML cannot be parsed,
                or when the file cannot be read due to OS errors.
            FlightPlanValidationError: When required fields are missing or
                invalid.
        """
        logger.debug("loading_flight_plan", path=str(path))
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FlightPlanNotFoundError(
                f"Flight plan file not found: {path}", path=path
            ) from exc
        except OSError as exc:
            raise FlightPlanParseError(
                f"Cannot read flight plan file {path}: {exc}",
                path=path,
            ) from exc

        # parse_frontmatter raises FlightPlanParseError on invalid input
        fm, body = parse_frontmatter(content)

        # Pre-validate required frontmatter fields for clear error messages
        required_keys = ("name", "version", "created")
        for key in required_keys:
            if key not in fm:
                raise FlightPlanValidationError(
                    f"Flight plan {path} is missing required frontmatter "
                    f"field: {key!r}",
                    path=path,
                    field=key,
                )

        sections = parse_flight_plan_sections(body)

        # Build nested model inputs
        success_criteria = tuple(
            SuccessCriterion(text=text, checked=checked)
            for checked, text in sections["success_criteria"]
        )
        scope_data = sections["scope"]
        scope = Scope(
            in_scope=tuple(scope_data["in_scope"]),
            out_of_scope=tuple(scope_data["out_of_scope"]),
            boundaries=tuple(scope_data["boundaries"]),
        )

        try:
            fp = FlightPlan(
                name=fm.get("name", ""),
                version=str(fm.get("version", "")),
                created=fm.get("created"),  # type: ignore[arg-type]
                tags=tuple(fm.get("tags") or []),
                depends_on_plans=tuple(fm.get("depends-on-plans") or []),
                objective=sections["objective"],
                success_criteria=success_criteria,
                scope=scope,
                context=sections["context"],
                constraints=tuple(sections["constraints"]),
                notes=sections["notes"],
                source_path=path,
            )
        except ValidationError as exc:
            raise FlightPlanValidationError(
                f"Flight plan validation failed for {path}: {exc}",
                path=path,
            ) from exc

        logger.debug("flight_plan_loaded", name=fp.name, path=str(path))
        return fp

    @classmethod
    async def aload(cls, path: Path) -> FlightPlan:
        """Asynchronously load a FlightPlan from a Markdown file.

        Delegates to :meth:`load` via ``asyncio.to_thread`` to avoid
        blocking the event loop.

        Args:
            path: Path to the ``.md`` file.

        Returns:
            Parsed and validated FlightPlan model.

        Raises:
            FlightPlanNotFoundError: When the file does not exist.
            FlightPlanParseError: When the Markdown/YAML cannot be parsed.
            FlightPlanValidationError: When required fields are missing or invalid.
        """
        return await asyncio.to_thread(cls.load, path)

    @classmethod
    def save(cls, plan: FlightPlan, path: Path) -> None:
        """Save a FlightPlan to a Markdown file (synchronous).

        Serializes the plan to YAML frontmatter + Markdown format and writes
        it to the given path in UTF-8 encoding.

        Args:
            plan: FlightPlan model instance to serialize.
            path: Destination file path. Will be created or overwritten.
        """
        from maverick.flight.serializer import serialize_flight_plan

        content = serialize_flight_plan(plan)
        path.write_text(content, encoding="utf-8")

    @classmethod
    async def asave(cls, plan: FlightPlan, path: Path) -> None:
        """Save a FlightPlan to a Markdown file (asynchronous).

        Delegates to :meth:`save` via ``asyncio.to_thread`` to avoid
        blocking the event loop.

        Args:
            plan: FlightPlan model instance to serialize.
            path: Destination file path. Will be created or overwritten.
        """
        await asyncio.to_thread(cls.save, plan, path)


# ---------------------------------------------------------------------------
# WorkUnitFile
# ---------------------------------------------------------------------------


class WorkUnitFile:
    """Loader for Work Unit Markdown+YAML files.

    All methods are class methods; no instance state is maintained.
    """

    @classmethod
    def load(cls, path: Path) -> WorkUnit:
        """Load a WorkUnit from a Markdown file.

        Args:
            path: Path to the ``.md`` file.

        Returns:
            Parsed and validated WorkUnit model with source_path set.

        Raises:
            WorkUnitNotFoundError: When the file does not exist.
            WorkUnitValidationError: When required fields are missing or
                invalid (including bad kebab-case ID), or when the file
                cannot be read due to OS errors.
        """
        logger.debug("loading_work_unit", path=str(path))
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise WorkUnitNotFoundError(
                f"Work unit file not found: {path}", path=path
            ) from exc
        except OSError as exc:
            raise WorkUnitValidationError(
                f"Cannot read work unit file {path}: {exc}",
                path=path,
            ) from exc

        # parse_frontmatter raises FlightPlanParseError on invalid input
        fm, body = parse_frontmatter(content)

        # Pre-validate required frontmatter fields for clear error messages
        required_keys = ("work-unit", "flight-plan", "sequence")
        for key in required_keys:
            if key not in fm:
                raise WorkUnitValidationError(
                    f"Work unit {path} is missing required frontmatter field: {key!r}",
                    path=path,
                    field=key,
                )

        sections = parse_work_unit_sections(body)

        # Build nested model inputs
        acceptance_criteria = tuple(
            AcceptanceCriterion(text=text, trace_ref=trace_ref)
            for text, trace_ref in sections["acceptance_criteria"]
        )

        fs_data = sections["file_scope"]
        file_scope = FileScope(
            create=tuple(fs_data["create"]),
            modify=tuple(fs_data["modify"]),
            protect=tuple(fs_data["protect"]),
        )

        # Normalise depends-on: YAML may give None, a list, or be absent
        raw_depends_on = fm.get("depends-on") or []
        depends_on = tuple(str(d) for d in raw_depends_on)

        try:
            wu = WorkUnit(
                id=fm.get("work-unit", ""),
                flight_plan=str(fm.get("flight-plan", "")),
                sequence=int(fm.get("sequence", 0)),
                parallel_group=fm.get("parallel-group"),
                depends_on=depends_on,
                task=sections["task"],
                acceptance_criteria=acceptance_criteria,
                file_scope=file_scope,
                instructions=sections["instructions"],
                verification=tuple(sections["verification"]),
                provider_hints=sections["provider_hints"],
                source_path=path,
            )
        except ValidationError as exc:
            raise WorkUnitValidationError(
                f"Work unit validation failed for {path}: {exc}",
                path=path,
            ) from exc

        logger.debug("work_unit_loaded", id=wu.id, path=str(path))
        return wu

    @classmethod
    async def aload(cls, path: Path) -> WorkUnit:
        """Asynchronously load a WorkUnit from a Markdown file.

        Args:
            path: Path to the ``.md`` file.

        Returns:
            Parsed and validated WorkUnit model.

        Raises:
            WorkUnitNotFoundError: When the file does not exist.
            WorkUnitValidationError: When required fields are invalid.
        """
        return await asyncio.to_thread(cls.load, path)

    @classmethod
    def load_directory(cls, directory: Path) -> list[WorkUnit]:
        """Load all Work Units from a directory.

        Discovers files matching the ``###-slug.md`` pattern (three leading
        digits followed by a hyphen and slug), loads each, and returns them
        sorted by sequence number.

        Args:
            directory: Path to the directory containing work unit files.

        Returns:
            List of WorkUnit models sorted by sequence number (ascending).

        Raises:
            WorkUnitNotFoundError: If an individual file is missing while
                being read (rare race condition).
            WorkUnitValidationError: If any file fails validation.
        """
        logger.debug("loading_work_units_from_directory", directory=str(directory))
        files = sorted(directory.glob(_WORK_UNIT_GLOB))
        units = [cls.load(f) for f in files]
        # Sort by sequence number (ascending)
        units.sort(key=lambda u: u.sequence)
        logger.debug(
            "work_units_loaded_from_directory",
            count=len(units),
            directory=str(directory),
        )
        return units

    @classmethod
    async def aload_directory(cls, directory: Path) -> list[WorkUnit]:
        """Asynchronously load all Work Units from a directory.

        Args:
            directory: Path to the directory containing work unit files.

        Returns:
            List of WorkUnit models sorted by sequence number (ascending).
        """
        return await asyncio.to_thread(cls.load_directory, directory)

    @classmethod
    def save(cls, unit: WorkUnit, path: Path) -> None:
        """Save a WorkUnit to a Markdown file (synchronous).

        Serializes the unit to YAML frontmatter + Markdown format and writes
        it to the given path in UTF-8 encoding.

        Args:
            unit: WorkUnit model instance to serialize.
            path: Destination file path. Will be created or overwritten.
        """
        from maverick.flight.serializer import serialize_work_unit

        content = serialize_work_unit(unit)
        path.write_text(content, encoding="utf-8")

    @classmethod
    async def asave(cls, unit: WorkUnit, path: Path) -> None:
        """Save a WorkUnit to a Markdown file (asynchronous).

        Delegates to :meth:`save` via ``asyncio.to_thread`` to avoid
        blocking the event loop.

        Args:
            unit: WorkUnit model instance to serialize.
            path: Destination file path. Will be created or overwritten.
        """
        await asyncio.to_thread(cls.save, unit, path)


__all__ = [
    "FlightPlanFile",
    "WorkUnitFile",
]
