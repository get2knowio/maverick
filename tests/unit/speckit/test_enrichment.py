"""Tests for maverick.speckit.enrichment (prompt building, response parsing, apply)."""

from __future__ import annotations

from pathlib import Path

from maverick.speckit.build import build_ingestion_plan
from maverick.speckit.enrichment import (
    apply_enrichment,
    build_enrichment_prompt,
    parse_enrichment_response,
)
from maverick.speckit.models import SpeckitFeature
from maverick.speckit.parser import parse_spec_md, parse_tasks_md


def _feature(tmp_path: Path, tasks_md: str, spec_md: str) -> SpeckitFeature:
    feature_dir = tmp_path / "specs" / "048-enrich-sample"
    phases, story_deps = parse_tasks_md(tasks_md)
    return SpeckitFeature(
        feature_dir=feature_dir,
        feature_name=feature_dir.name,
        spec=parse_spec_md(spec_md),
        phases=phases,
        story_deps=story_deps,
    )


_TASKS_MD = """\
## Phase 1: Setup

- [ ] T001 Initialize project
- [ ] T002 [P] Create config file in src/config.py
"""
_SPEC_MD = "# Feature Specification: Enrich Sample\n"


class TestBuildEnrichmentPrompt:
    def test_prompt_covers_all_new_tasks_in_one_call(self, tmp_path: Path) -> None:
        feature = _feature(tmp_path, _TASKS_MD, _SPEC_MD)
        plan, _warnings = build_ingestion_plan(feature)

        prompt = build_enrichment_prompt(plan.new_tasks)

        assert "T001" in prompt
        assert "T002" in prompt
        assert prompt.count("## T001") == 1
        assert prompt.count("## T002") == 1


class TestParseEnrichmentResponse:
    def test_parses_commands_keyed_by_task_id(self) -> None:
        response = """\
### T001
- rg --files -g 'src/foo.py'
- cargo test test_foo

### T002
- make lint
"""
        parsed = parse_enrichment_response(response)
        assert parsed == {
            "T001": ["rg --files -g 'src/foo.py'", "cargo test test_foo"],
            "T002": ["make lint"],
        }

    def test_ignores_prose_outside_task_sections(self) -> None:
        response = "Some preamble.\n\n### T001\n- make test\n\nSome trailing notes.\n"
        parsed = parse_enrichment_response(response)
        assert parsed == {"T001": ["make test"]}

    def test_empty_response_yields_empty_dict(self) -> None:
        assert parse_enrichment_response("") == {}


class TestApplyEnrichment:
    def test_merges_commands_into_verification_only(self, tmp_path: Path) -> None:
        feature = _feature(tmp_path, _TASKS_MD, _SPEC_MD)
        plan, _warnings = build_ingestion_plan(feature)
        commands_by_task = {"T001": ["make test-t001"], "T002": ["make test-t002"]}

        enriched = apply_enrichment(plan, commands_by_task)

        by_id = {pb.task_id: pb for pb in enriched.new_tasks}
        assert "make test-t001" in by_id["T001"].definition.description
        assert "make test-t002" in by_id["T002"].definition.description

        # Every other section is untouched.
        original_by_id = {pb.task_id: pb for pb in plan.new_tasks}
        for task_id in ("T001", "T002"):
            original_sections = original_by_id[task_id].definition.description.split(
                "## Verification"
            )[0]
            enriched_sections = by_id[task_id].definition.description.split("## Verification")[0]
            assert original_sections == enriched_sections

    def test_task_set_and_edges_identical_to_unenriched_plan(self, tmp_path: Path) -> None:
        feature = _feature(tmp_path, _TASKS_MD, _SPEC_MD)
        plan, _warnings = build_ingestion_plan(feature)

        enriched = apply_enrichment(plan, {"T001": ["make test"]})

        assert enriched.edges == plan.edges
        assert [pb.task_id for pb in enriched.new_tasks] == [pb.task_id for pb in plan.new_tasks]
        assert enriched.skipped_completed == plan.skipped_completed
        assert enriched.skipped_existing == plan.skipped_existing

    def test_task_with_no_suggested_commands_is_unchanged(self, tmp_path: Path) -> None:
        feature = _feature(tmp_path, _TASKS_MD, _SPEC_MD)
        plan, _warnings = build_ingestion_plan(feature)

        enriched = apply_enrichment(plan, {"T001": ["make test"]})

        by_id = {pb.task_id: pb for pb in enriched.new_tasks}
        original_by_id = {pb.task_id: pb for pb in plan.new_tasks}
        assert (
            by_id["T002"].definition.description == original_by_id["T002"].definition.description
        )
