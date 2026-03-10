"""Unit tests for maverick.library.actions.decompose."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.library.actions.decompose import (
    CodebaseContext,
    FileContent,
    _extract_path_from_scope_item,
    build_decomposition_prompt,
    convert_specs_to_work_units,
    gather_codebase_context,
    validate_decomposition,
)
from maverick.workflows.refuel_maverick.models import (
    AcceptanceCriterionSpec,
    FileScopeSpec,
    WorkUnitSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_work_unit_spec(
    wu_id: str,
    sequence: int = 1,
    depends_on: list[str] | None = None,
    trace_refs: list[str | None] | None = None,
    parallel_group: str | None = None,
) -> WorkUnitSpec:
    criteria = []
    for ref in trace_refs or []:
        criteria.append(AcceptanceCriterionSpec(text=f"Criterion {ref}", trace_ref=ref))
    return WorkUnitSpec(
        id=wu_id,
        sequence=sequence,
        depends_on=depends_on or [],
        parallel_group=parallel_group,
        task=f"Task for {wu_id}",
        acceptance_criteria=criteria,
        file_scope=FileScopeSpec(create=[], modify=[], protect=["src/config.py"]),
        instructions="Do the thing",
        verification=["make test"],
    )


# ---------------------------------------------------------------------------
# _extract_path_from_scope_item tests
# ---------------------------------------------------------------------------


class TestExtractPathFromScopeItem:
    """Tests for _extract_path_from_scope_item()."""

    def test_bare_path_unchanged(self) -> None:
        assert _extract_path_from_scope_item("src/greet/cli.py") == "src/greet/cli.py"

    def test_backtick_path_with_description(self) -> None:
        raw = "`src/greet/languages.py` — Language dataclass and LANGUAGES list"
        assert _extract_path_from_scope_item(raw) == "src/greet/languages.py"

    def test_backtick_path_alone(self) -> None:
        assert _extract_path_from_scope_item("`src/main.py`") == "src/main.py"

    def test_path_like_with_dash_separator(self) -> None:
        raw = "src/greet/cli.py - CLI entry point"
        assert _extract_path_from_scope_item(raw) == "src/greet/cli.py"

    def test_directory_path(self) -> None:
        assert _extract_path_from_scope_item("src/greet/") == "src/greet/"

    def test_backtick_directory_with_description(self) -> None:
        raw = "`tests/` — All test files"
        assert _extract_path_from_scope_item(raw) == "tests/"

    def test_plain_text_returned_as_is(self) -> None:
        raw = "No changes to database layer"
        assert _extract_path_from_scope_item(raw) == "No changes to database layer"

    def test_whitespace_stripped(self) -> None:
        assert _extract_path_from_scope_item("  src/foo.py  ") == "src/foo.py"


# ---------------------------------------------------------------------------
# gather_codebase_context tests
# ---------------------------------------------------------------------------


class TestGatherCodebaseContext:
    """Tests for gather_codebase_context()."""

    async def test_reads_existing_files(self, tmp_path: Path) -> None:
        """Existing files are read and returned as FileContent entries."""
        (tmp_path / "foo.py").write_text("print('hello')", encoding="utf-8")
        (tmp_path / "bar.py").write_text("x = 1", encoding="utf-8")

        ctx = await gather_codebase_context(
            in_scope=("foo.py", "bar.py"),
            cwd=tmp_path,
        )

        assert len(ctx.files) == 2
        paths = {f.path for f in ctx.files}
        assert "foo.py" in paths
        assert "bar.py" in paths
        contents = {f.path: f.content for f in ctx.files}
        assert "print('hello')" in contents["foo.py"]

    async def test_missing_files_recorded_in_missing(self, tmp_path: Path) -> None:
        """Missing files are recorded in CodebaseContext.missing_files."""
        ctx = await gather_codebase_context(
            in_scope=("nonexistent.py",),
            cwd=tmp_path,
        )

        assert len(ctx.files) == 0
        assert "nonexistent.py" in ctx.missing_files

    async def test_directory_expanded_to_files(self, tmp_path: Path) -> None:
        """Directory paths in in_scope are expanded to contained files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "a.py").write_text("a = 1", encoding="utf-8")
        (src_dir / "b.py").write_text("b = 2", encoding="utf-8")

        ctx = await gather_codebase_context(
            in_scope=("src",),
            cwd=tmp_path,
        )

        assert len(ctx.files) == 2
        paths = {f.path for f in ctx.files}
        assert any("a.py" in p for p in paths)
        assert any("b.py" in p for p in paths)

    async def test_total_size_reflects_content_size(self, tmp_path: Path) -> None:
        """total_size reflects the total bytes of all file contents."""
        content = "x" * 100
        (tmp_path / "test.py").write_text(content, encoding="utf-8")

        ctx = await gather_codebase_context(
            in_scope=("test.py",),
            cwd=tmp_path,
        )

        assert ctx.total_size == len(content)

    async def test_empty_in_scope_returns_empty_context(self, tmp_path: Path) -> None:
        """Empty in_scope returns empty CodebaseContext."""
        ctx = await gather_codebase_context(in_scope=(), cwd=tmp_path)

        assert ctx.files == ()
        assert ctx.missing_files == ()
        assert ctx.total_size == 0

    async def test_unreadable_binary_file_handled_gracefully(
        self, tmp_path: Path
    ) -> None:
        """Unreadable files (binary with invalid UTF-8) handled without crash."""
        # Create a binary file (not valid UTF-8)
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\xff\xfe\x00\x01")

        # Should not raise
        ctx = await gather_codebase_context(
            in_scope=("binary.bin",),
            cwd=tmp_path,
        )

        # Binary file should appear in missing (unreadable as text)
        assert len(ctx.files) == 0
        assert len(ctx.missing_files) == 1
        assert "binary.bin" in ctx.missing_files[0]

    async def test_mixed_existing_and_missing(self, tmp_path: Path) -> None:
        """Mix of existing and missing files handled correctly."""
        (tmp_path / "exists.py").write_text("exists = True", encoding="utf-8")

        ctx = await gather_codebase_context(
            in_scope=("exists.py", "missing.py"),
            cwd=tmp_path,
        )

        assert len(ctx.files) == 1
        assert ctx.files[0].path == "exists.py"
        assert "missing.py" in ctx.missing_files

    async def test_total_size_zero_for_empty_files(self, tmp_path: Path) -> None:
        """total_size is zero when all files have empty content."""
        (tmp_path / "empty.py").write_text("", encoding="utf-8")

        ctx = await gather_codebase_context(
            in_scope=("empty.py",),
            cwd=tmp_path,
        )

        assert ctx.total_size == 0
        assert len(ctx.files) == 1

    async def test_multiple_files_total_size_is_sum(self, tmp_path: Path) -> None:
        """total_size is the sum of individual file content lengths."""
        (tmp_path / "a.py").write_text("aaa", encoding="utf-8")
        (tmp_path / "b.py").write_text("bbbbb", encoding="utf-8")

        ctx = await gather_codebase_context(
            in_scope=("a.py", "b.py"),
            cwd=tmp_path,
        )

        assert ctx.total_size == 8  # 3 + 5

    async def test_descriptive_scope_items_resolved(self, tmp_path: Path) -> None:
        """Scope items with backtick-wrapped paths and descriptions are resolved."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "cli.py").write_text("cli = True", encoding="utf-8")

        ctx = await gather_codebase_context(
            in_scope=("`src/cli.py` — CLI entry point with argument parsing",),
            cwd=tmp_path,
        )

        assert len(ctx.files) == 1
        assert ctx.files[0].content == "cli = True"

    async def test_nested_directory_expanded_recursively(self, tmp_path: Path) -> None:
        """Nested directories are expanded recursively."""
        outer = tmp_path / "pkg"
        inner = outer / "sub"
        inner.mkdir(parents=True)
        (outer / "top.py").write_text("top = 1", encoding="utf-8")
        (inner / "nested.py").write_text("nested = 2", encoding="utf-8")

        ctx = await gather_codebase_context(
            in_scope=("pkg",),
            cwd=tmp_path,
        )

        assert len(ctx.files) == 2
        paths = {f.path for f in ctx.files}
        assert any("top.py" in p for p in paths)
        assert any("nested.py" in p for p in paths)


# ---------------------------------------------------------------------------
# build_decomposition_prompt tests
# ---------------------------------------------------------------------------


class TestBuildDecompositionPrompt:
    """Tests for build_decomposition_prompt()."""

    def test_includes_flight_plan_content(self) -> None:
        """Prompt includes the flight plan content."""
        fp_content = "## Objective\nBuild something great."
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)

        prompt = build_decomposition_prompt(fp_content, ctx)

        assert fp_content in prompt

    def test_includes_file_contents_with_path_headers(self) -> None:
        """Prompt includes file contents with path headers."""
        ctx = CodebaseContext(
            files=(FileContent(path="src/auth.py", content="def login(): pass"),),
            missing_files=(),
            total_size=18,
        )

        prompt = build_decomposition_prompt("flight plan", ctx)

        assert "src/auth.py" in prompt
        assert "def login(): pass" in prompt

    def test_includes_missing_files_section(self) -> None:
        """Prompt includes missing files section when files are missing."""
        ctx = CodebaseContext(
            files=(),
            missing_files=("src/missing.py",),
            total_size=0,
        )

        prompt = build_decomposition_prompt("plan", ctx)

        assert "src/missing.py" in prompt

    def test_includes_instructions(self) -> None:
        """Prompt includes decomposition instructions."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)

        prompt = build_decomposition_prompt("plan", ctx)

        assert "work units" in prompt.lower()
        assert "kebab-case" in prompt.lower()

    def test_no_in_scope_files_shows_placeholder(self) -> None:
        """Prompt notes when no in-scope files are available."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)

        prompt = build_decomposition_prompt("plan", ctx)

        # The _format_codebase_context returns "No in-scope files specified."
        assert "No in-scope files specified." in prompt

    def test_returns_string(self) -> None:
        """build_decomposition_prompt always returns a string."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        result = build_decomposition_prompt("any plan", ctx)
        assert isinstance(result, str)

    def test_includes_multiple_files(self) -> None:
        """Prompt includes all provided files."""
        ctx = CodebaseContext(
            files=(
                FileContent(path="src/models.py", content="class Model: pass"),
                FileContent(path="src/views.py", content="class View: pass"),
            ),
            missing_files=(),
            total_size=36,
        )

        prompt = build_decomposition_prompt("plan", ctx)

        assert "src/models.py" in prompt
        assert "src/views.py" in prompt
        assert "class Model: pass" in prompt
        assert "class View: pass" in prompt

    def test_no_files_with_missing_shows_missing_message(self) -> None:
        """When no files read but some are missing, message reflects that."""
        ctx = CodebaseContext(
            files=(),
            missing_files=("gone.py",),
            total_size=0,
        )

        prompt = build_decomposition_prompt("plan", ctx)

        assert "gone.py" in prompt
        assert "No files could be read" in prompt


# ---------------------------------------------------------------------------
# validate_decomposition tests
# ---------------------------------------------------------------------------


class TestValidateDecomposition:
    """Tests for validate_decomposition()."""

    def test_valid_acyclic_graph_passes(self) -> None:
        """Valid acyclic dependency graph passes without raising."""
        specs = [
            make_work_unit_spec("unit-a", sequence=1, trace_refs=["SC-001"]),
            make_work_unit_spec(
                "unit-b", sequence=2, depends_on=["unit-a"], trace_refs=["SC-002"]
            ),
        ]

        warnings = validate_decomposition(specs, success_criteria_count=2)

        # Both SC-001 and SC-002 are covered
        assert warnings == []

    def test_coverage_gaps_raise_sc_coverage_error(self) -> None:
        """Uncovered SC criteria raise SCCoverageError with gap details."""
        from maverick.library.actions.decompose import SCCoverageError

        specs = [
            make_work_unit_spec("unit-a", sequence=1, trace_refs=["SC-001"]),
        ]

        # 3 criteria but only SC-001 covered
        with pytest.raises(SCCoverageError) as exc_info:
            validate_decomposition(specs, success_criteria_count=3)

        assert len(exc_info.value.gaps) == 2
        assert "SC-002" in exc_info.value.gaps[0]
        assert "SC-003" in exc_info.value.gaps[1]

    def test_circular_dependency_raises(self) -> None:
        """Circular dependency raises ValueError."""
        specs = [
            make_work_unit_spec("unit-a", sequence=1, depends_on=["unit-b"]),
            make_work_unit_spec("unit-b", sequence=2, depends_on=["unit-a"]),
        ]

        with pytest.raises(ValueError, match="[Cc]ircular"):
            validate_decomposition(specs, success_criteria_count=0)

    def test_dangling_depends_on_raises(self) -> None:
        """Dangling depends_on reference raises ValueError."""
        specs = [
            make_work_unit_spec("unit-a", sequence=1, depends_on=["nonexistent-unit"]),
        ]

        with pytest.raises(ValueError):
            validate_decomposition(specs, success_criteria_count=0)

    def test_zero_sc_count_no_warnings(self) -> None:
        """Zero success criteria count produces no coverage warnings."""
        specs = [make_work_unit_spec("unit-a", sequence=1)]

        warnings = validate_decomposition(specs, success_criteria_count=0)

        assert warnings == []

    def test_uncovered_sc_raises_error(self) -> None:
        """Uncovered SC raises SCCoverageError (blocking for retry)."""
        from maverick.library.actions.decompose import SCCoverageError

        specs = [make_work_unit_spec("unit-a", sequence=1)]

        with pytest.raises(SCCoverageError) as exc_info:
            validate_decomposition(specs, success_criteria_count=3)

        assert len(exc_info.value.gaps) == 3  # SC-001, SC-002, SC-003 all uncovered

    def test_empty_specs_with_zero_sc_passes(self) -> None:
        """Empty specs with zero sc count produces empty warnings."""
        warnings = validate_decomposition([], success_criteria_count=0)
        assert warnings == []

    def test_sc_coverage_error_text_mentions_ref(self) -> None:
        """SCCoverageError gap text contains the SC reference."""
        from maverick.library.actions.decompose import SCCoverageError

        specs = [make_work_unit_spec("unit-a", sequence=1)]

        with pytest.raises(SCCoverageError) as exc_info:
            validate_decomposition(specs, success_criteria_count=1)

        assert len(exc_info.value.gaps) == 1
        assert "SC-001" in exc_info.value.gaps[0]

    def test_all_sc_covered_no_warnings(self) -> None:
        """When all SCs are covered, no coverage warnings produced."""
        specs = [
            make_work_unit_spec("unit-a", sequence=1, trace_refs=["SC-001", "SC-002"]),
            make_work_unit_spec("unit-b", sequence=2, trace_refs=["SC-003"]),
        ]

        warnings = validate_decomposition(specs, success_criteria_count=3)

        assert warnings == []

    def test_none_trace_refs_do_not_count_as_covered(self) -> None:
        """Criteria with trace_ref=None do not count toward SC coverage."""
        from maverick.library.actions.decompose import SCCoverageError

        specs = [
            make_work_unit_spec("unit-a", sequence=1, trace_refs=[None]),
        ]

        with pytest.raises(SCCoverageError) as exc_info:
            validate_decomposition(specs, success_criteria_count=1)

        # SC-001 is not covered because trace_ref=None
        assert len(exc_info.value.gaps) == 1
        assert "SC-001" in exc_info.value.gaps[0]

    def test_three_way_circular_dependency_raises(self) -> None:
        """Three-unit circular dependency raises ValueError."""
        specs = [
            make_work_unit_spec("unit-a", sequence=1, depends_on=["unit-c"]),
            make_work_unit_spec("unit-b", sequence=2, depends_on=["unit-a"]),
            make_work_unit_spec("unit-c", sequence=3, depends_on=["unit-b"]),
        ]

        with pytest.raises(ValueError):
            validate_decomposition(specs, success_criteria_count=0)


# ---------------------------------------------------------------------------
# convert_specs_to_work_units tests
# ---------------------------------------------------------------------------


class TestConvertSpecsToWorkUnits:
    """Tests for convert_specs_to_work_units()."""

    def test_maps_all_fields_correctly(self) -> None:
        """All fields from WorkUnitSpec are mapped to WorkUnit correctly."""
        spec = WorkUnitSpec(
            id="add-models",
            sequence=1,
            parallel_group="group-a",
            depends_on=[],
            task="Add models",
            acceptance_criteria=[
                AcceptanceCriterionSpec(text="Models created", trace_ref="SC-001")
            ],
            file_scope=FileScopeSpec(
                create=["src/models.py"],
                modify=["src/admin.py"],
                protect=["src/config.py"],
            ),
            instructions="Implement models",
            verification=["pytest tests/"],
        )

        units = convert_specs_to_work_units([spec], flight_plan_name="my-plan")

        assert len(units) == 1
        wu = units[0]
        assert wu.id == "add-models"
        assert wu.flight_plan == "my-plan"
        assert wu.sequence == 1
        assert wu.parallel_group == "group-a"
        assert wu.depends_on == ()
        assert wu.task == "Add models"
        assert len(wu.acceptance_criteria) == 1
        assert wu.acceptance_criteria[0].text == "Models created"
        assert wu.acceptance_criteria[0].trace_ref == "SC-001"
        assert wu.file_scope.create == ("src/models.py",)
        assert wu.file_scope.modify == ("src/admin.py",)
        assert wu.file_scope.protect == ("src/config.py",)
        assert wu.instructions == "Implement models"
        assert wu.verification == ("pytest tests/",)
        assert wu.source_path is None

    def test_sets_flight_plan_name(self) -> None:
        """flight_plan field is set from flight_plan_name argument."""
        spec = make_work_unit_spec("unit-x", sequence=1)
        units = convert_specs_to_work_units([spec], flight_plan_name="test-flight-plan")

        assert units[0].flight_plan == "test-flight-plan"

    def test_empty_specs_returns_empty_list(self) -> None:
        """Empty specs list returns empty units list."""
        units = convert_specs_to_work_units([], flight_plan_name="plan")
        assert units == []

    def test_source_path_propagated(self, tmp_path: Path) -> None:
        """source_path argument is propagated to all work units."""
        spec = make_work_unit_spec("unit-a", sequence=1)
        path = tmp_path / "flight-plan.md"

        units = convert_specs_to_work_units(
            [spec], flight_plan_name="plan", source_path=path
        )

        assert units[0].source_path == path

    def test_source_path_none_by_default(self) -> None:
        """source_path defaults to None when not provided."""
        spec = make_work_unit_spec("unit-a", sequence=1)

        units = convert_specs_to_work_units([spec], flight_plan_name="plan")

        assert units[0].source_path is None

    def test_multiple_specs_all_converted(self) -> None:
        """Multiple specs are all converted to work units."""
        specs = [
            make_work_unit_spec("unit-a", sequence=1),
            make_work_unit_spec("unit-b", sequence=2),
            make_work_unit_spec("unit-c", sequence=3),
        ]

        units = convert_specs_to_work_units(specs, flight_plan_name="plan")

        assert len(units) == 3
        ids = [u.id for u in units]
        assert "unit-a" in ids
        assert "unit-b" in ids
        assert "unit-c" in ids

    def test_depends_on_tuple_conversion(self) -> None:
        """depends_on list from spec is converted to tuple in WorkUnit."""
        spec = make_work_unit_spec("unit-b", sequence=2, depends_on=["unit-a"])

        units = convert_specs_to_work_units([spec], flight_plan_name="plan")

        assert units[0].depends_on == ("unit-a",)

    def test_verification_tuple_conversion(self) -> None:
        """verification list from spec is converted to tuple in WorkUnit."""
        spec = WorkUnitSpec(
            id="unit-a",
            sequence=1,
            task="Do task",
            verification=["make test", "make lint"],
            file_scope=FileScopeSpec(),
            instructions="Instructions",
        )

        units = convert_specs_to_work_units([spec], flight_plan_name="plan")

        assert units[0].verification == ("make test", "make lint")

    def test_source_path_same_for_all_units(self, tmp_path: Path) -> None:
        """source_path is applied to all work units when multiple specs provided."""
        specs = [
            make_work_unit_spec("unit-a", sequence=1),
            make_work_unit_spec("unit-b", sequence=2),
        ]
        path = tmp_path / "fp.md"

        units = convert_specs_to_work_units(
            specs, flight_plan_name="plan", source_path=path
        )

        assert all(u.source_path == path for u in units)

    def test_parallel_group_preserved(self) -> None:
        """parallel_group from spec is preserved in work unit."""
        spec = make_work_unit_spec("unit-a", sequence=1, parallel_group="tier-1")

        units = convert_specs_to_work_units([spec], flight_plan_name="plan")

        assert units[0].parallel_group == "tier-1"

    def test_no_parallel_group_is_none(self) -> None:
        """parallel_group is None when not specified in spec."""
        spec = make_work_unit_spec("unit-a", sequence=1, parallel_group=None)

        units = convert_specs_to_work_units([spec], flight_plan_name="plan")

        assert units[0].parallel_group is None

    def test_acceptance_criteria_none_trace_ref_preserved(self) -> None:
        """AcceptanceCriterion with trace_ref=None is preserved correctly."""
        spec = WorkUnitSpec(
            id="unit-a",
            sequence=1,
            task="Do task",
            acceptance_criteria=[
                AcceptanceCriterionSpec(text="Some criterion", trace_ref=None),
            ],
            file_scope=FileScopeSpec(),
            instructions="Instructions",
        )

        units = convert_specs_to_work_units([spec], flight_plan_name="plan")

        assert len(units[0].acceptance_criteria) == 1
        assert units[0].acceptance_criteria[0].trace_ref is None
