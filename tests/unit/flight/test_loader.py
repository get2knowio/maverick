"""Tests for maverick.flight.loader module.

T008: FlightPlanFile loader tests.
T013: WorkUnitFile loader tests.

Tests written before implementation (TDD). All tests must fail until
loaders are implemented.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tests.unit.flight.conftest import (
    SAMPLE_FLIGHT_PLAN_MD,
    SAMPLE_WORK_UNIT_MD,
    SAMPLE_WORK_UNIT_MD_WITH_PARALLEL,
)

# ===========================================================================
# T008: FlightPlanFile loader tests
# ===========================================================================


class TestFlightPlanFileLoad:
    """Tests for FlightPlanFile.load()."""

    def test_load_valid_file_returns_flight_plan(self, tmp_path: Path) -> None:
        """load() from a valid file returns a FlightPlan with correct fields."""
        from maverick.flight.loader import FlightPlanFile
        from maverick.flight.models import FlightPlan

        fp_file = tmp_path / "flight-plan.md"
        fp_file.write_text(SAMPLE_FLIGHT_PLAN_MD)

        fp = FlightPlanFile.load(fp_file)

        assert isinstance(fp, FlightPlan)
        assert fp.name == "setup-authentication"
        assert fp.version == "1.0"
        assert fp.created == date(2026, 2, 27)
        assert "auth" in fp.tags
        assert "security" in fp.tags

    def test_load_sets_source_path(self, tmp_path: Path) -> None:
        """load() sets source_path on the returned FlightPlan."""
        from maverick.flight.loader import FlightPlanFile

        fp_file = tmp_path / "flight-plan.md"
        fp_file.write_text(SAMPLE_FLIGHT_PLAN_MD)

        fp = FlightPlanFile.load(fp_file)
        assert fp.source_path == fp_file

    def test_load_objective_field(self, tmp_path: Path) -> None:
        """load() correctly populates the objective field."""
        from maverick.flight.loader import FlightPlanFile

        fp_file = tmp_path / "plan.md"
        fp_file.write_text(SAMPLE_FLIGHT_PLAN_MD)

        fp = FlightPlanFile.load(fp_file)
        assert "JWT tokens" in fp.objective

    def test_load_success_criteria(self, tmp_path: Path) -> None:
        """load() populates success_criteria with correct checked states."""
        from maverick.flight.loader import FlightPlanFile

        fp_file = tmp_path / "plan.md"
        fp_file.write_text(SAMPLE_FLIGHT_PLAN_MD)

        fp = FlightPlanFile.load(fp_file)
        assert len(fp.success_criteria) == 3
        assert fp.success_criteria[0].checked is True
        assert fp.success_criteria[1].checked is False

    def test_load_scope_in_scope(self, tmp_path: Path) -> None:
        """load() populates scope.in_scope from the ### In subsection."""
        from maverick.flight.loader import FlightPlanFile

        fp_file = tmp_path / "plan.md"
        fp_file.write_text(SAMPLE_FLIGHT_PLAN_MD)

        fp = FlightPlanFile.load(fp_file)
        assert "Registration endpoint" in fp.scope.in_scope

    def test_load_optional_context(self, tmp_path: Path) -> None:
        """load() populates optional context field."""
        from maverick.flight.loader import FlightPlanFile

        fp_file = tmp_path / "plan.md"
        fp_file.write_text(SAMPLE_FLIGHT_PLAN_MD)

        fp = FlightPlanFile.load(fp_file)
        assert "Express.js" in fp.context

    def test_load_optional_constraints(self, tmp_path: Path) -> None:
        """load() populates optional constraints field."""
        from maverick.flight.loader import FlightPlanFile

        fp_file = tmp_path / "plan.md"
        fp_file.write_text(SAMPLE_FLIGHT_PLAN_MD)

        fp = FlightPlanFile.load(fp_file)
        assert len(fp.constraints) == 2

    def test_load_optional_notes(self, tmp_path: Path) -> None:
        """load() populates optional notes field."""
        from maverick.flight.loader import FlightPlanFile

        fp_file = tmp_path / "plan.md"
        fp_file.write_text(SAMPLE_FLIGHT_PLAN_MD)

        fp = FlightPlanFile.load(fp_file)
        assert "refresh tokens" in fp.notes

    def test_load_depends_on_plans_absent_defaults_empty(self, tmp_path: Path) -> None:
        """load() defaults depends_on_plans to () when absent."""
        from maverick.flight.loader import FlightPlanFile

        fp_file = tmp_path / "plan.md"
        fp_file.write_text(SAMPLE_FLIGHT_PLAN_MD)

        fp = FlightPlanFile.load(fp_file)
        assert fp.depends_on_plans == ()

    def test_load_depends_on_plans_present(self, tmp_path: Path) -> None:
        """load() reads depends-on-plans from YAML frontmatter."""
        from maverick.flight.loader import FlightPlanFile

        content = """\
---
name: add-payments
version: "1.0"
created: 2026-03-01
depends-on-plans:
  - add-auth
  - add-database
---

## Objective

Add payment processing.

## Success Criteria

- [ ] Payments work

## Scope

### In

- src/payments/
"""
        fp_file = tmp_path / "plan.md"
        fp_file.write_text(content)

        fp = FlightPlanFile.load(fp_file)
        assert fp.depends_on_plans == ("add-auth", "add-database")

    def test_load_missing_file_raises_not_found(self, tmp_path: Path) -> None:
        """load() on a missing file raises FlightPlanNotFoundError with path."""
        from maverick.flight.errors import FlightPlanNotFoundError
        from maverick.flight.loader import FlightPlanFile

        missing = tmp_path / "nonexistent.md"
        with pytest.raises(FlightPlanNotFoundError) as exc_info:
            FlightPlanFile.load(missing)
        assert exc_info.value.path == missing

    def test_load_oserror_raises_parse_error(self, tmp_path: Path) -> None:
        """load() wraps non-FileNotFoundError OSError in FlightPlanParseError."""
        from maverick.flight.errors import FlightPlanParseError
        from maverick.flight.loader import FlightPlanFile

        # Use a directory path — reading it as text raises IsADirectoryError
        dir_path = tmp_path / "a-directory"
        dir_path.mkdir()

        with pytest.raises(FlightPlanParseError) as exc_info:
            FlightPlanFile.load(dir_path)
        assert exc_info.value.path == dir_path

    def test_load_missing_frontmatter_name_raises_validation_error(self, tmp_path: Path) -> None:
        """load() raises FlightPlanValidationError when 'name' is absent."""
        from maverick.flight.errors import FlightPlanValidationError
        from maverick.flight.loader import FlightPlanFile

        content = (
            "---\n"
            "version: '1.0'\n"
            "created: 2026-01-01\n"
            "tags:\n  - test\n"
            "---\n\n## Objective\n\nDo something.\n\n"
            "## Success Criteria\n\n- [x] Done\n\n"
            "## Scope\n\n### In\n\n- item\n\n### Out\n\n### Boundaries\n"
        )
        fp_file = tmp_path / "no-name.md"
        fp_file.write_text(content)

        with pytest.raises(FlightPlanValidationError) as exc_info:
            FlightPlanFile.load(fp_file)
        assert exc_info.value.field == "name"
        assert exc_info.value.path == fp_file

    def test_load_missing_frontmatter_version_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """load() raises FlightPlanValidationError when 'version' is absent."""
        from maverick.flight.errors import FlightPlanValidationError
        from maverick.flight.loader import FlightPlanFile

        content = (
            "---\n"
            "name: my-plan\n"
            "created: 2026-01-01\n"
            "tags:\n  - test\n"
            "---\n\n## Objective\n\nDo something.\n\n"
            "## Success Criteria\n\n- [x] Done\n\n"
            "## Scope\n\n### In\n\n- item\n\n### Out\n\n### Boundaries\n"
        )
        fp_file = tmp_path / "no-version.md"
        fp_file.write_text(content)

        with pytest.raises(FlightPlanValidationError) as exc_info:
            FlightPlanFile.load(fp_file)
        assert exc_info.value.field == "version"
        assert exc_info.value.path == fp_file

    def test_load_missing_frontmatter_created_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """load() raises FlightPlanValidationError when 'created' is absent."""
        from maverick.flight.errors import FlightPlanValidationError
        from maverick.flight.loader import FlightPlanFile

        content = (
            "---\n"
            "name: my-plan\n"
            "version: '1.0'\n"
            "tags:\n  - test\n"
            "---\n\n## Objective\n\nDo something.\n\n"
            "## Success Criteria\n\n- [x] Done\n\n"
            "## Scope\n\n### In\n\n- item\n\n### Out\n\n### Boundaries\n"
        )
        fp_file = tmp_path / "no-created.md"
        fp_file.write_text(content)

        with pytest.raises(FlightPlanValidationError) as exc_info:
            FlightPlanFile.load(fp_file)
        assert exc_info.value.field == "created"
        assert exc_info.value.path == fp_file

    def test_load_malformed_frontmatter_raises_parse_error(self, tmp_path: Path) -> None:
        """load() on content without --- delimiters raises FlightPlanParseError."""
        from maverick.flight.errors import FlightPlanParseError
        from maverick.flight.loader import FlightPlanFile

        bad_file = tmp_path / "bad.md"
        bad_file.write_text("name: my-plan\nversion: 1.0\n\n## Objective\n\nSomething.")

        with pytest.raises(FlightPlanParseError):
            FlightPlanFile.load(bad_file)

    def test_load_missing_required_fields_raises_validation_error(self, tmp_path: Path) -> None:
        """load() on YAML missing required fields raises FlightPlanValidationError."""
        from maverick.flight.errors import FlightPlanValidationError
        from maverick.flight.loader import FlightPlanFile

        incomplete = tmp_path / "incomplete.md"
        # Valid YAML but missing 'name', 'version', etc.
        incomplete.write_text(
            "---\ntags:\n  - test\n---\n\n## Objective\n\nSomething.\n\n"
            "## Success Criteria\n\n## Scope\n\n### In\n\n### Out\n\n### Boundaries\n"
        )
        with pytest.raises(FlightPlanValidationError) as exc_info:
            FlightPlanFile.load(incomplete)
        assert exc_info.value.path == incomplete

    def test_load_extra_yaml_fields_ignored(self, tmp_path: Path) -> None:
        """load() ignores extra YAML frontmatter fields (forward compatibility)."""
        from maverick.flight.loader import FlightPlanFile

        extra_fields = SAMPLE_FLIGHT_PLAN_MD.replace(
            "---\n\n## Objective",
            "future-field: some-value\n---\n\n## Objective",
        )
        fp_file = tmp_path / "plan.md"
        fp_file.write_text(extra_fields)

        # Should not raise
        fp = FlightPlanFile.load(fp_file)
        assert fp.name == "setup-authentication"

    def test_load_optional_sections_absent_defaults(self, tmp_path: Path) -> None:
        """load() uses empty defaults when optional sections are absent."""
        from maverick.flight.loader import FlightPlanFile

        minimal = (
            "---\n"
            "name: minimal-plan\n"
            "version: '1.0'\n"
            "created: 2026-01-01\n"
            "tags:\n"
            "  - test\n"
            "---\n\n"
            "## Objective\n\nDo something.\n\n"
            "## Success Criteria\n\n- [x] Done\n\n"
            "## Scope\n\n### In\n\n- item\n\n### Out\n\n### Boundaries\n\n"
        )
        fp_file = tmp_path / "minimal.md"
        fp_file.write_text(minimal)

        fp = FlightPlanFile.load(fp_file)
        assert fp.context == ""
        assert fp.constraints == ()
        assert fp.notes == ""

    def test_load_absent_success_criteria_section(self, tmp_path: Path) -> None:
        """Absent Success Criteria gives empty tuple and None pct."""
        from maverick.flight.loader import FlightPlanFile

        no_sc = (
            "---\n"
            "name: no-sc-plan\n"
            "version: '1.0'\n"
            "created: 2026-01-01\n"
            "tags:\n"
            "  - test\n"
            "---\n\n"
            "## Objective\n\nDo something.\n\n"
            "## Scope\n\n### In\n\n- item\n\n### Out\n\n### Boundaries\n\n"
        )
        fp_file = tmp_path / "no-sc.md"
        fp_file.write_text(no_sc)

        fp = FlightPlanFile.load(fp_file)
        assert fp.success_criteria == ()
        assert fp.completion.percentage is None


class TestFlightPlanFileAload:
    """Tests for FlightPlanFile.aload()."""

    async def test_aload_valid_file(self, tmp_path: Path) -> None:
        """aload() returns FlightPlan asynchronously."""
        from maverick.flight.loader import FlightPlanFile
        from maverick.flight.models import FlightPlan

        fp_file = tmp_path / "plan.md"
        fp_file.write_text(SAMPLE_FLIGHT_PLAN_MD)

        fp = await FlightPlanFile.aload(fp_file)
        assert isinstance(fp, FlightPlan)
        assert fp.name == "setup-authentication"

    async def test_aload_missing_file_raises(self, tmp_path: Path) -> None:
        """aload() on missing file raises FlightPlanNotFoundError with path."""
        from maverick.flight.errors import FlightPlanNotFoundError
        from maverick.flight.loader import FlightPlanFile

        missing = tmp_path / "nonexistent.md"
        with pytest.raises(FlightPlanNotFoundError) as exc_info:
            await FlightPlanFile.aload(missing)
        assert exc_info.value.path == missing


# ===========================================================================
# T013: WorkUnitFile loader tests
# ===========================================================================


class TestWorkUnitFileLoad:
    """Tests for WorkUnitFile.load()."""

    def test_load_valid_file_returns_work_unit(self, tmp_path: Path) -> None:
        """load() from a valid file returns a WorkUnit with correct fields."""
        from maverick.flight.loader import WorkUnitFile
        from maverick.flight.models import WorkUnit

        wu_file = tmp_path / "001-setup-database.md"
        wu_file.write_text(SAMPLE_WORK_UNIT_MD)

        wu = WorkUnitFile.load(wu_file)

        assert isinstance(wu, WorkUnit)
        assert wu.id == "setup-database"
        assert wu.flight_plan == "setup-authentication"
        assert wu.sequence == 1

    def test_load_sets_source_path(self, tmp_path: Path) -> None:
        """load() sets source_path on the returned WorkUnit."""
        from maverick.flight.loader import WorkUnitFile

        wu_file = tmp_path / "001-setup-database.md"
        wu_file.write_text(SAMPLE_WORK_UNIT_MD)

        wu = WorkUnitFile.load(wu_file)
        assert wu.source_path == wu_file

    def test_load_acceptance_criteria(self, tmp_path: Path) -> None:
        """load() populates acceptance_criteria with trace refs."""
        from maverick.flight.loader import WorkUnitFile

        wu_file = tmp_path / "001-setup-database.md"
        wu_file.write_text(SAMPLE_WORK_UNIT_MD)

        wu = WorkUnitFile.load(wu_file)
        assert len(wu.acceptance_criteria) == 2
        assert wu.acceptance_criteria[0].trace_ref == "SC-001"
        assert wu.acceptance_criteria[1].trace_ref is None

    def test_load_file_scope(self, tmp_path: Path) -> None:
        """load() populates file_scope sections."""
        from maverick.flight.loader import WorkUnitFile

        wu_file = tmp_path / "001-setup-database.md"
        wu_file.write_text(SAMPLE_WORK_UNIT_MD)

        wu = WorkUnitFile.load(wu_file)
        assert "src/db/connection.py" in wu.file_scope.create
        assert "src/config.py" in wu.file_scope.modify
        assert "src/main.py" in wu.file_scope.protect

    def test_load_verification_commands(self, tmp_path: Path) -> None:
        """load() populates verification command list."""
        from maverick.flight.loader import WorkUnitFile

        wu_file = tmp_path / "001-setup-database.md"
        wu_file.write_text(SAMPLE_WORK_UNIT_MD)

        wu = WorkUnitFile.load(wu_file)
        assert "make test-fast" in wu.verification

    def test_load_depends_on_empty_list(self, tmp_path: Path) -> None:
        """load() populates depends_on as empty tuple when YAML has []."""
        from maverick.flight.loader import WorkUnitFile

        wu_file = tmp_path / "001-setup-database.md"
        wu_file.write_text(SAMPLE_WORK_UNIT_MD)

        wu = WorkUnitFile.load(wu_file)
        assert wu.depends_on == ()

    def test_load_with_parallel_group_and_depends_on(self, tmp_path: Path) -> None:
        """load() correctly handles parallel-group and depends-on fields."""
        from maverick.flight.loader import WorkUnitFile

        wu_file = tmp_path / "002-add-login-endpoint.md"
        wu_file.write_text(SAMPLE_WORK_UNIT_MD_WITH_PARALLEL)

        wu = WorkUnitFile.load(wu_file)
        assert wu.parallel_group == "endpoints"
        assert "setup-database" in wu.depends_on

    def test_load_missing_file_raises_not_found(self, tmp_path: Path) -> None:
        """load() on missing file raises WorkUnitNotFoundError with path."""
        from maverick.flight.errors import WorkUnitNotFoundError
        from maverick.flight.loader import WorkUnitFile

        missing = tmp_path / "nonexistent.md"
        with pytest.raises(WorkUnitNotFoundError) as exc_info:
            WorkUnitFile.load(missing)
        assert exc_info.value.path == missing

    def test_load_oserror_raises_validation_error(self, tmp_path: Path) -> None:
        """load() wraps non-FileNotFoundError OSError in WorkUnitValidationError."""
        from maverick.flight.errors import WorkUnitValidationError
        from maverick.flight.loader import WorkUnitFile

        dir_path = tmp_path / "a-directory"
        dir_path.mkdir()

        with pytest.raises(WorkUnitValidationError) as exc_info:
            WorkUnitFile.load(dir_path)
        assert exc_info.value.path == dir_path

    def test_load_missing_frontmatter_work_unit_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """load() raises WorkUnitValidationError when 'work-unit' is absent."""
        from maverick.flight.errors import WorkUnitValidationError
        from maverick.flight.loader import WorkUnitFile

        content = (
            "---\n"
            "flight-plan: my-plan\n"
            "sequence: 1\n"
            "depends-on: []\n"
            "---\n\n## Task\n\nDo something.\n\n"
            "## Acceptance Criteria\n\n- Something done\n\n"
            "## File Scope\n\n### Create\n\n### Modify\n\n### Protect\n\n"
            "## Instructions\n\nDo it.\n\n## Verification\n\n- make test\n"
        )
        wu_file = tmp_path / "001-no-id.md"
        wu_file.write_text(content)

        with pytest.raises(WorkUnitValidationError) as exc_info:
            WorkUnitFile.load(wu_file)
        assert exc_info.value.field == "work-unit"
        assert exc_info.value.path == wu_file

    def test_load_missing_frontmatter_flight_plan_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """load() raises WorkUnitValidationError when 'flight-plan' is absent."""
        from maverick.flight.errors import WorkUnitValidationError
        from maverick.flight.loader import WorkUnitFile

        content = (
            "---\n"
            "work-unit: my-unit\n"
            "sequence: 1\n"
            "depends-on: []\n"
            "---\n\n## Task\n\nDo something.\n\n"
            "## Acceptance Criteria\n\n- Something done\n\n"
            "## File Scope\n\n### Create\n\n### Modify\n\n### Protect\n\n"
            "## Instructions\n\nDo it.\n\n## Verification\n\n- make test\n"
        )
        wu_file = tmp_path / "001-no-plan.md"
        wu_file.write_text(content)

        with pytest.raises(WorkUnitValidationError) as exc_info:
            WorkUnitFile.load(wu_file)
        assert exc_info.value.field == "flight-plan"
        assert exc_info.value.path == wu_file

    def test_load_missing_frontmatter_sequence_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """load() raises WorkUnitValidationError when 'sequence' is absent."""
        from maverick.flight.errors import WorkUnitValidationError
        from maverick.flight.loader import WorkUnitFile

        content = (
            "---\n"
            "work-unit: my-unit\n"
            "flight-plan: my-plan\n"
            "depends-on: []\n"
            "---\n\n## Task\n\nDo something.\n\n"
            "## Acceptance Criteria\n\n- Something done\n\n"
            "## File Scope\n\n### Create\n\n### Modify\n\n### Protect\n\n"
            "## Instructions\n\nDo it.\n\n## Verification\n\n- make test\n"
        )
        wu_file = tmp_path / "001-no-seq.md"
        wu_file.write_text(content)

        with pytest.raises(WorkUnitValidationError) as exc_info:
            WorkUnitFile.load(wu_file)
        assert exc_info.value.field == "sequence"
        assert exc_info.value.path == wu_file

    def test_load_invalid_id_raises_validation_error(self, tmp_path: Path) -> None:
        """Invalid kebab-case ID raises WorkUnitValidationError."""
        from maverick.flight.errors import WorkUnitValidationError
        from maverick.flight.loader import WorkUnitFile

        bad_content = SAMPLE_WORK_UNIT_MD.replace(
            "work-unit: setup-database", "work-unit: SetupDatabase"
        )
        wu_file = tmp_path / "001-bad-id.md"
        wu_file.write_text(bad_content)

        with pytest.raises(WorkUnitValidationError) as exc_info:
            WorkUnitFile.load(wu_file)
        assert exc_info.value.path == wu_file

    def test_load_provider_hints_absent_is_none(self, tmp_path: Path) -> None:
        """load() sets provider_hints to None when section is absent."""
        from maverick.flight.loader import WorkUnitFile

        wu_file = tmp_path / "001-setup-database.md"
        wu_file.write_text(SAMPLE_WORK_UNIT_MD)

        wu = WorkUnitFile.load(wu_file)
        assert wu.provider_hints is None

    def test_load_provider_hints_present(self, tmp_path: Path) -> None:
        """load() populates provider_hints when section is present."""
        from maverick.flight.loader import WorkUnitFile

        content_with_hints = SAMPLE_WORK_UNIT_MD + "\n## Provider Hints\n\nUse the fast path.\n"
        wu_file = tmp_path / "001-hints.md"
        wu_file.write_text(content_with_hints)

        wu = WorkUnitFile.load(wu_file)
        assert wu.provider_hints is not None
        assert "fast path" in wu.provider_hints


class TestWorkUnitFileAload:
    """Tests for WorkUnitFile.aload()."""

    async def test_aload_valid_file(self, tmp_path: Path) -> None:
        """aload() returns WorkUnit asynchronously."""
        from maverick.flight.loader import WorkUnitFile
        from maverick.flight.models import WorkUnit

        wu_file = tmp_path / "001-setup-database.md"
        wu_file.write_text(SAMPLE_WORK_UNIT_MD)

        wu = await WorkUnitFile.aload(wu_file)
        assert isinstance(wu, WorkUnit)
        assert wu.id == "setup-database"

    async def test_aload_missing_file_raises(self, tmp_path: Path) -> None:
        """aload() on missing file raises WorkUnitNotFoundError with path."""
        from maverick.flight.errors import WorkUnitNotFoundError
        from maverick.flight.loader import WorkUnitFile

        missing = tmp_path / "nonexistent.md"
        with pytest.raises(WorkUnitNotFoundError) as exc_info:
            await WorkUnitFile.aload(missing)
        assert exc_info.value.path == missing


class TestWorkUnitFileLoadDirectory:
    """Tests for WorkUnitFile.load_directory()."""

    def test_load_directory_discovers_files(self, tmp_path: Path) -> None:
        """load_directory() discovers ###-slug.md files and returns WorkUnits."""
        from maverick.flight.loader import WorkUnitFile

        (tmp_path / "001-setup-database.md").write_text(SAMPLE_WORK_UNIT_MD)
        (tmp_path / "002-add-login-endpoint.md").write_text(SAMPLE_WORK_UNIT_MD_WITH_PARALLEL)

        units = WorkUnitFile.load_directory(tmp_path)
        assert len(units) == 2

    def test_load_directory_sorted_by_sequence(self, tmp_path: Path) -> None:
        """load_directory() returns units sorted by sequence number."""
        from maverick.flight.loader import WorkUnitFile

        # Write in reverse order on disk
        (tmp_path / "002-add-login-endpoint.md").write_text(SAMPLE_WORK_UNIT_MD_WITH_PARALLEL)
        (tmp_path / "001-setup-database.md").write_text(SAMPLE_WORK_UNIT_MD)

        units = WorkUnitFile.load_directory(tmp_path)
        assert units[0].sequence == 1
        assert units[1].sequence == 2

    def test_load_directory_empty_returns_empty_list(self, tmp_path: Path) -> None:
        """load_directory() on an empty directory returns empty list."""
        from maverick.flight.loader import WorkUnitFile

        units = WorkUnitFile.load_directory(tmp_path)
        assert units == []

    def test_load_directory_ignores_non_matching_files(self, tmp_path: Path) -> None:
        """load_directory() ignores files not matching ###-slug.md pattern."""
        from maverick.flight.loader import WorkUnitFile

        (tmp_path / "001-setup-database.md").write_text(SAMPLE_WORK_UNIT_MD)
        (tmp_path / "README.md").write_text("# This should be ignored\n")
        (tmp_path / "notes.txt").write_text("ignored\n")

        units = WorkUnitFile.load_directory(tmp_path)
        assert len(units) == 1

    def test_load_directory_returns_list_of_work_units(self, tmp_path: Path) -> None:
        """load_directory() returns a list of WorkUnit instances."""
        from maverick.flight.loader import WorkUnitFile
        from maverick.flight.models import WorkUnit

        (tmp_path / "001-setup-database.md").write_text(SAMPLE_WORK_UNIT_MD)

        units = WorkUnitFile.load_directory(tmp_path)
        assert all(isinstance(u, WorkUnit) for u in units)


class TestWorkUnitFileAloadDirectory:
    """Tests for WorkUnitFile.aload_directory()."""

    async def test_aload_directory_valid(self, tmp_path: Path) -> None:
        """aload_directory() returns list of WorkUnits asynchronously."""
        from maverick.flight.loader import WorkUnitFile

        (tmp_path / "001-setup-database.md").write_text(SAMPLE_WORK_UNIT_MD)

        units = await WorkUnitFile.aload_directory(tmp_path)
        assert len(units) == 1
        assert units[0].id == "setup-database"

    async def test_aload_directory_empty_returns_empty_list(self, tmp_path: Path) -> None:
        """aload_directory() on empty directory returns empty list."""
        from maverick.flight.loader import WorkUnitFile

        units = await WorkUnitFile.aload_directory(tmp_path)
        assert units == []
