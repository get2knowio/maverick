"""Tests for maverick.flight.serializer round-trip serialization.

Covers:
- serialize_flight_plan() produces valid YAML frontmatter + Markdown sections
- serialize_work_unit() produces valid YAML frontmatter + Markdown sections
- Round-trip fidelity for FlightPlan: load → serialize → reload → compare
- Round-trip fidelity for WorkUnit: same
- FlightPlanFile.save(plan, path) writes correct content to file
- FlightPlanFile.asave(plan, path) async variant
- WorkUnitFile.save(unit, path) writes correct content to file
- WorkUnitFile.asave(unit, path) async variant
"""

from __future__ import annotations

from pathlib import Path

import yaml

from maverick.flight.loader import FlightPlanFile, WorkUnitFile
from maverick.flight.models import FlightPlan, WorkUnit
from maverick.flight.serializer import serialize_flight_plan, serialize_work_unit
from tests.unit.flight.conftest import (
    SAMPLE_FLIGHT_PLAN_MD,
    SAMPLE_WORK_UNIT_MD,
    SAMPLE_WORK_UNIT_MD_WITH_PARALLEL,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_flight_plan_from_string(content: str, tmp_path: Path) -> FlightPlan:
    """Write content to a temp file and load via FlightPlanFile."""
    p = tmp_path / "flight-plan.md"
    p.write_text(content, encoding="utf-8")
    return FlightPlanFile.load(p)


def _load_work_unit_from_string(
    content: str, tmp_path: Path, name: str = "001-unit.md"
) -> WorkUnit:
    """Write content to a temp file and load via WorkUnitFile."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return WorkUnitFile.load(p)


# ---------------------------------------------------------------------------
# serialize_flight_plan() — output format tests
# ---------------------------------------------------------------------------


class TestSerializeFlightPlan:
    """Tests for serialize_flight_plan() output format."""

    def test_produces_string(self, tmp_path: Path) -> None:
        """serialize_flight_plan returns a string."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        assert isinstance(result, str)

    def test_starts_with_frontmatter_delimiter(self, tmp_path: Path) -> None:
        """Output must start with --- frontmatter opener."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        assert result.startswith("---\n")

    def test_frontmatter_contains_name(self, tmp_path: Path) -> None:
        """Frontmatter must contain the plan name."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        # Extract frontmatter block
        parts = result.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["name"] == "setup-authentication"

    def test_frontmatter_contains_version(self, tmp_path: Path) -> None:
        """Frontmatter must contain the version."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        parts = result.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        assert str(fm["version"]) == "1.0"

    def test_frontmatter_contains_created_date(self, tmp_path: Path) -> None:
        """Frontmatter must contain the created date as ISO string."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        parts = result.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        # YAML may parse it as date or string — either is acceptable
        assert str(fm["created"]) == "2026-02-27"

    def test_frontmatter_contains_tags(self, tmp_path: Path) -> None:
        """Frontmatter must contain the tags list."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        parts = result.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["tags"] == ["auth", "security"]

    def test_contains_objective_section(self, tmp_path: Path) -> None:
        """Output must contain ## Objective section."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        assert "## Objective" in result
        assert "Implement user authentication with JWT tokens." in result

    def test_contains_success_criteria_section(self, tmp_path: Path) -> None:
        """Output must contain ## Success Criteria section with checkbox items."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        assert "## Success Criteria" in result
        assert "- [x] Users can register with email and password" in result
        assert "- [ ] Users can log in and receive a JWT" in result
        assert "- [ ] Protected routes reject unauthenticated requests" in result

    def test_contains_scope_section(self, tmp_path: Path) -> None:
        """Output must contain ## Scope section with In/Out/Boundaries sub-sections."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        assert "## Scope" in result
        assert "### In" in result
        assert "### Out" in result
        assert "### Boundaries" in result
        assert "- Registration endpoint" in result
        assert "- OAuth providers" in result
        assert "- JWT tokens expire after 24 hours" in result

    def test_contains_context_section_when_non_empty(self, tmp_path: Path) -> None:
        """Output must contain ## Context section when plan.context is non-empty."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        assert "## Context" in result
        assert "Building on the existing Express.js API framework." in result

    def test_omits_context_section_when_empty(self, tmp_path: Path) -> None:
        """## Context section must be omitted when plan.context is empty."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        # Build plan without context
        plan_no_ctx = plan.model_copy(update={"context": "", "source_path": None})
        result = serialize_flight_plan(plan_no_ctx)
        assert "## Context" not in result

    def test_contains_constraints_when_non_empty(self, tmp_path: Path) -> None:
        """Output must contain ## Constraints section when constraints is non-empty."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        assert "## Constraints" in result
        assert "- Must use bcrypt for password hashing" in result

    def test_omits_constraints_when_empty(self, tmp_path: Path) -> None:
        """## Constraints section must be omitted when constraints is empty."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        plan_no_c = plan.model_copy(update={"constraints": (), "source_path": None})
        result = serialize_flight_plan(plan_no_c)
        assert "## Constraints" not in result

    def test_contains_notes_when_non_empty(self, tmp_path: Path) -> None:
        """Output must contain ## Notes section when notes is non-empty."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        assert "## Notes" in result
        assert "Consider adding refresh tokens in a follow-up." in result

    def test_omits_notes_when_empty(self, tmp_path: Path) -> None:
        """## Notes section must be omitted when notes is empty."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        plan_no_n = plan.model_copy(update={"notes": "", "source_path": None})
        result = serialize_flight_plan(plan_no_n)
        assert "## Notes" not in result

    def test_checked_criteria_format(self, tmp_path: Path) -> None:
        """Checked criteria use - [x] marker."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        assert "- [x] Users can register with email and password" in result

    def test_unchecked_criteria_format(self, tmp_path: Path) -> None:
        """Unchecked criteria use - [ ] marker."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        result = serialize_flight_plan(plan)
        assert "- [ ] Users can log in and receive a JWT" in result


# ---------------------------------------------------------------------------
# serialize_work_unit() — output format tests
# ---------------------------------------------------------------------------


class TestSerializeWorkUnit:
    """Tests for serialize_work_unit() output format."""

    def test_produces_string(self, tmp_path: Path) -> None:
        """serialize_work_unit returns a string."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        assert isinstance(result, str)

    def test_starts_with_frontmatter_delimiter(self, tmp_path: Path) -> None:
        """Output must start with --- frontmatter opener."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        assert result.startswith("---\n")

    def test_frontmatter_contains_work_unit_id(self, tmp_path: Path) -> None:
        """Frontmatter must contain work-unit id."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        parts = result.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["work-unit"] == "setup-database"

    def test_frontmatter_contains_flight_plan(self, tmp_path: Path) -> None:
        """Frontmatter must contain flight-plan."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        parts = result.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["flight-plan"] == "setup-authentication"

    def test_frontmatter_contains_sequence(self, tmp_path: Path) -> None:
        """Frontmatter must contain sequence number."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        parts = result.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["sequence"] == 1

    def test_frontmatter_contains_depends_on(self, tmp_path: Path) -> None:
        """Frontmatter must contain depends-on list."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        parts = result.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["depends-on"] == []

    def test_frontmatter_contains_parallel_group_when_set(self, tmp_path: Path) -> None:
        """Frontmatter must contain parallel-group when non-None."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD_WITH_PARALLEL, tmp_path)
        result = serialize_work_unit(unit)
        parts = result.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["parallel-group"] == "endpoints"

    def test_frontmatter_omits_parallel_group_when_none(self, tmp_path: Path) -> None:
        """Frontmatter must not contain parallel-group when None."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        parts = result.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        assert "parallel-group" not in fm

    def test_contains_task_section(self, tmp_path: Path) -> None:
        """Output must contain ## Task section."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        assert "## Task" in result
        assert "Create the users table and database connection module." in result

    def test_contains_acceptance_criteria_section(self, tmp_path: Path) -> None:
        """Output must contain ## Acceptance Criteria section."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        assert "## Acceptance Criteria" in result
        assert "- Database connection pool is configured [SC-001]" in result
        assert "- Users table has email, password_hash, created_at columns" in result

    def test_acceptance_criteria_with_trace_ref(self, tmp_path: Path) -> None:
        """Acceptance criteria with trace_ref include [SC-###] suffix."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        assert "[SC-001]" in result

    def test_acceptance_criteria_without_trace_ref(self, tmp_path: Path) -> None:
        """Acceptance criteria without trace_ref have no [SC-###] suffix."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        # Second criterion has no trace ref
        assert "- Users table has email, password_hash, created_at columns\n" in result

    def test_contains_file_scope_section(self, tmp_path: Path) -> None:
        """Output must contain ## File Scope section with sub-sections."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        assert "## File Scope" in result
        assert "### Create" in result
        assert "### Modify" in result
        assert "### Protect" in result
        assert "- src/db/connection.py" in result
        assert "- src/config.py" in result
        assert "- src/main.py" in result

    def test_contains_instructions_section(self, tmp_path: Path) -> None:
        """Output must contain ## Instructions section."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        assert "## Instructions" in result
        assert "Use SQLAlchemy with async support." in result

    def test_contains_verification_section(self, tmp_path: Path) -> None:
        """Output must contain ## Verification section."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        result = serialize_work_unit(unit)
        assert "## Verification" in result
        assert "- make test-fast" in result
        assert "- make lint" in result

    def test_omits_provider_hints_when_none(self, tmp_path: Path) -> None:
        """## Provider Hints section must be omitted when provider_hints is None."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        assert unit.provider_hints is None
        result = serialize_work_unit(unit)
        assert "## Provider Hints" not in result

    def test_contains_provider_hints_when_set(self, tmp_path: Path) -> None:
        """Provider Hints section must be present when provider_hints is non-empty."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        unit_with_hints = unit.model_copy(
            update={
                "provider_hints": "Prefer async SQLAlchemy patterns.",
                "source_path": None,
            }
        )
        result = serialize_work_unit(unit_with_hints)
        assert "## Provider Hints" in result
        assert "Prefer async SQLAlchemy patterns." in result

    def test_depends_on_with_values(self, tmp_path: Path) -> None:
        """Frontmatter depends-on must list dependency IDs."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD_WITH_PARALLEL, tmp_path)
        result = serialize_work_unit(unit)
        parts = result.split("---\n", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["depends-on"] == ["setup-database"]


# ---------------------------------------------------------------------------
# Round-trip fidelity — FlightPlan
# ---------------------------------------------------------------------------


class TestFlightPlanRoundTrip:
    """Round-trip fidelity: load → serialize → write → reload → compare."""

    @staticmethod
    def _round_trip(tmp_path: Path, markdown: str) -> tuple[FlightPlan, FlightPlan]:
        """Load a flight plan, serialize it, write to a new file, and reload.

        Args:
            tmp_path: Pytest temporary directory.
            markdown: Raw Markdown+frontmatter content.

        Returns:
            Tuple of (original, reloaded) FlightPlan models.
        """
        original_path = tmp_path / "original.md"
        original_path.write_text(markdown, encoding="utf-8")
        original = FlightPlanFile.load(original_path)

        content = serialize_flight_plan(original)
        serialized_path = tmp_path / "serialized.md"
        serialized_path.write_text(content, encoding="utf-8")
        reloaded = FlightPlanFile.load(serialized_path)

        return original, reloaded

    def test_round_trip_name(self, tmp_path: Path) -> None:
        """name must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_FLIGHT_PLAN_MD)
        assert reloaded.name == original.name

    def test_round_trip_version(self, tmp_path: Path) -> None:
        """version must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_FLIGHT_PLAN_MD)
        assert reloaded.version == original.version

    def test_round_trip_created(self, tmp_path: Path) -> None:
        """created date must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_FLIGHT_PLAN_MD)
        assert reloaded.created == original.created

    def test_round_trip_tags(self, tmp_path: Path) -> None:
        """tags must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_FLIGHT_PLAN_MD)
        assert reloaded.tags == original.tags

    def test_round_trip_objective(self, tmp_path: Path) -> None:
        """objective must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_FLIGHT_PLAN_MD)
        assert reloaded.objective == original.objective

    def test_round_trip_success_criteria_count(self, tmp_path: Path) -> None:
        """Number of success criteria must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_FLIGHT_PLAN_MD)
        assert len(reloaded.success_criteria) == len(original.success_criteria)

    def test_round_trip_success_criteria_text(self, tmp_path: Path) -> None:
        """Success criteria text must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_FLIGHT_PLAN_MD)
        for orig, rt in zip(
            original.success_criteria, reloaded.success_criteria, strict=True
        ):
            assert rt.text == orig.text
            assert rt.checked == orig.checked

    def test_round_trip_scope(self, tmp_path: Path) -> None:
        """Scope in/out/boundaries must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_FLIGHT_PLAN_MD)
        assert reloaded.scope.in_scope == original.scope.in_scope
        assert reloaded.scope.out_of_scope == original.scope.out_of_scope
        assert reloaded.scope.boundaries == original.scope.boundaries

    def test_round_trip_context(self, tmp_path: Path) -> None:
        """context must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_FLIGHT_PLAN_MD)
        assert reloaded.context == original.context

    def test_round_trip_constraints(self, tmp_path: Path) -> None:
        """constraints must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_FLIGHT_PLAN_MD)
        assert reloaded.constraints == original.constraints

    def test_round_trip_notes(self, tmp_path: Path) -> None:
        """notes must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_FLIGHT_PLAN_MD)
        assert reloaded.notes == original.notes


# ---------------------------------------------------------------------------
# Round-trip fidelity — WorkUnit
# ---------------------------------------------------------------------------


class TestWorkUnitRoundTrip:
    """Round-trip fidelity: load → serialize → write → reload → compare."""

    @staticmethod
    def _round_trip(
        tmp_path: Path,
        markdown: str,
        *,
        original_name: str = "001-setup-database.md",
        serialized_name: str = "001-serialized.md",
    ) -> tuple[WorkUnit, WorkUnit]:
        """Load a work unit, serialize it, write to a new file, and reload.

        Args:
            tmp_path: Pytest temporary directory.
            markdown: Raw Markdown+frontmatter content.
            original_name: Filename for the original file.
            serialized_name: Filename for the serialized file.

        Returns:
            Tuple of (original, reloaded) WorkUnit models.
        """
        original_path = tmp_path / original_name
        original_path.write_text(markdown, encoding="utf-8")
        original = WorkUnitFile.load(original_path)

        content = serialize_work_unit(original)
        serialized_path = tmp_path / serialized_name
        serialized_path.write_text(content, encoding="utf-8")
        reloaded = WorkUnitFile.load(serialized_path)

        return original, reloaded

    def test_round_trip_id(self, tmp_path: Path) -> None:
        """id must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_WORK_UNIT_MD)
        assert reloaded.id == original.id

    def test_round_trip_flight_plan(self, tmp_path: Path) -> None:
        """flight_plan must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_WORK_UNIT_MD)
        assert reloaded.flight_plan == original.flight_plan

    def test_round_trip_sequence(self, tmp_path: Path) -> None:
        """sequence must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_WORK_UNIT_MD)
        assert reloaded.sequence == original.sequence

    def test_round_trip_depends_on(self, tmp_path: Path) -> None:
        """depends_on must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_WORK_UNIT_MD)
        assert reloaded.depends_on == original.depends_on

    def test_round_trip_task(self, tmp_path: Path) -> None:
        """task must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_WORK_UNIT_MD)
        assert reloaded.task == original.task

    def test_round_trip_acceptance_criteria(self, tmp_path: Path) -> None:
        """acceptance_criteria must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_WORK_UNIT_MD)
        assert len(reloaded.acceptance_criteria) == len(original.acceptance_criteria)
        for orig, rt in zip(
            original.acceptance_criteria, reloaded.acceptance_criteria, strict=True
        ):
            assert rt.text == orig.text
            assert rt.trace_ref == orig.trace_ref

    def test_round_trip_file_scope(self, tmp_path: Path) -> None:
        """file_scope must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_WORK_UNIT_MD)
        assert reloaded.file_scope.create == original.file_scope.create
        assert reloaded.file_scope.modify == original.file_scope.modify
        assert reloaded.file_scope.protect == original.file_scope.protect

    def test_round_trip_instructions(self, tmp_path: Path) -> None:
        """instructions must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_WORK_UNIT_MD)
        assert reloaded.instructions == original.instructions

    def test_round_trip_verification(self, tmp_path: Path) -> None:
        """verification must survive round-trip."""
        original, reloaded = self._round_trip(tmp_path, SAMPLE_WORK_UNIT_MD)
        assert reloaded.verification == original.verification

    def test_round_trip_parallel_group(self, tmp_path: Path) -> None:
        """parallel_group must survive round-trip."""
        original, reloaded = self._round_trip(
            tmp_path,
            SAMPLE_WORK_UNIT_MD_WITH_PARALLEL,
            original_name="002-add-login-endpoint.md",
            serialized_name="002-serialized.md",
        )
        assert reloaded.parallel_group == original.parallel_group

    def test_round_trip_depends_on_with_values(self, tmp_path: Path) -> None:
        """depends_on with values must survive round-trip."""
        original, reloaded = self._round_trip(
            tmp_path,
            SAMPLE_WORK_UNIT_MD_WITH_PARALLEL,
            original_name="002-add-login-endpoint.md",
            serialized_name="002-serialized.md",
        )
        assert reloaded.depends_on == original.depends_on

    def test_round_trip_provider_hints(self, tmp_path: Path) -> None:
        """provider_hints must survive round-trip when set."""
        original_path = tmp_path / "001-setup-database.md"
        original_path.write_text(SAMPLE_WORK_UNIT_MD, encoding="utf-8")
        unit = WorkUnitFile.load(original_path)
        unit_with_hints = unit.model_copy(
            update={"provider_hints": "Use connection pooling.", "source_path": None}
        )

        content = serialize_work_unit(unit_with_hints)
        serialized_path = tmp_path / "001-serialized.md"
        serialized_path.write_text(content, encoding="utf-8")
        reloaded = WorkUnitFile.load(serialized_path)

        assert reloaded.provider_hints == unit_with_hints.provider_hints


# ---------------------------------------------------------------------------
# FlightPlanFile.save / asave
# ---------------------------------------------------------------------------


class TestFlightPlanFileSave:
    """Tests for FlightPlanFile.save() and FlightPlanFile.asave()."""

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """save() must create the file at the given path."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        out_path = tmp_path / "output.md"
        FlightPlanFile.save(plan, out_path)
        assert out_path.exists()

    def test_save_writes_correct_content(self, tmp_path: Path) -> None:
        """save() must write content that can be reloaded."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        out_path = tmp_path / "output.md"
        FlightPlanFile.save(plan, out_path)
        plan2 = FlightPlanFile.load(out_path)
        assert plan2.name == plan.name
        assert plan2.objective == plan.objective

    def test_save_utf8_encoding(self, tmp_path: Path) -> None:
        """save() must write in UTF-8 encoding."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        out_path = tmp_path / "output.md"
        FlightPlanFile.save(plan, out_path)
        # Read raw bytes to verify UTF-8
        content = out_path.read_bytes()
        # Should be valid UTF-8
        content.decode("utf-8")

    def test_save_overwrites_existing_file(self, tmp_path: Path) -> None:
        """save() must overwrite an existing file at the path."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        out_path = tmp_path / "output.md"
        out_path.write_text("old content", encoding="utf-8")
        FlightPlanFile.save(plan, out_path)
        content = out_path.read_text(encoding="utf-8")
        assert "old content" not in content
        assert "---" in content

    async def test_asave_creates_file(self, tmp_path: Path) -> None:
        """asave() must create the file at the given path."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        out_path = tmp_path / "async_output.md"
        await FlightPlanFile.asave(plan, out_path)
        assert out_path.exists()

    async def test_asave_writes_correct_content(self, tmp_path: Path) -> None:
        """asave() must write content that can be reloaded."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        out_path = tmp_path / "async_output.md"
        await FlightPlanFile.asave(plan, out_path)
        plan2 = FlightPlanFile.load(out_path)
        assert plan2.name == plan.name
        assert plan2.objective == plan.objective

    async def test_asave_matches_save_output(self, tmp_path: Path) -> None:
        """asave() must produce identical content to save()."""
        plan = _load_flight_plan_from_string(SAMPLE_FLIGHT_PLAN_MD, tmp_path)
        sync_path = tmp_path / "sync_output.md"
        async_path = tmp_path / "async_output.md"
        FlightPlanFile.save(plan, sync_path)
        await FlightPlanFile.asave(plan, async_path)
        sync_content = sync_path.read_text(encoding="utf-8")
        async_content = async_path.read_text(encoding="utf-8")
        assert sync_content == async_content


# ---------------------------------------------------------------------------
# WorkUnitFile.save / asave
# ---------------------------------------------------------------------------


class TestWorkUnitFileSave:
    """Tests for WorkUnitFile.save() and WorkUnitFile.asave()."""

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """save() must create the file at the given path."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        out_path = tmp_path / "output.md"
        WorkUnitFile.save(unit, out_path)
        assert out_path.exists()

    def test_save_writes_correct_content(self, tmp_path: Path) -> None:
        """save() must write content that can be reloaded."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        out_path = tmp_path / "001-output.md"
        WorkUnitFile.save(unit, out_path)
        unit2 = WorkUnitFile.load(out_path)
        assert unit2.id == unit.id
        assert unit2.task == unit.task

    def test_save_utf8_encoding(self, tmp_path: Path) -> None:
        """save() must write in UTF-8 encoding."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        out_path = tmp_path / "output.md"
        WorkUnitFile.save(unit, out_path)
        content = out_path.read_bytes()
        content.decode("utf-8")

    def test_save_overwrites_existing_file(self, tmp_path: Path) -> None:
        """save() must overwrite an existing file at the path."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        out_path = tmp_path / "output.md"
        out_path.write_text("old content", encoding="utf-8")
        WorkUnitFile.save(unit, out_path)
        content = out_path.read_text(encoding="utf-8")
        assert "old content" not in content
        assert "---" in content

    async def test_asave_creates_file(self, tmp_path: Path) -> None:
        """asave() must create the file at the given path."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        out_path = tmp_path / "async_output.md"
        await WorkUnitFile.asave(unit, out_path)
        assert out_path.exists()

    async def test_asave_writes_correct_content(self, tmp_path: Path) -> None:
        """asave() must write content that can be reloaded."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        out_path = tmp_path / "001-async-output.md"
        await WorkUnitFile.asave(unit, out_path)
        unit2 = WorkUnitFile.load(out_path)
        assert unit2.id == unit.id
        assert unit2.task == unit.task

    async def test_asave_matches_save_output(self, tmp_path: Path) -> None:
        """asave() must produce identical content to save()."""
        unit = _load_work_unit_from_string(SAMPLE_WORK_UNIT_MD, tmp_path)
        sync_path = tmp_path / "sync_output.md"
        async_path = tmp_path / "async_output.md"
        WorkUnitFile.save(unit, sync_path)
        await WorkUnitFile.asave(unit, async_path)
        sync_content = sync_path.read_text(encoding="utf-8")
        async_content = async_path.read_text(encoding="utf-8")
        assert sync_content == async_content
