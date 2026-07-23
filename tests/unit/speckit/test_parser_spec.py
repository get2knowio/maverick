"""Tests for spec.md extraction (maverick.speckit.parser.parse_spec_md)."""

from __future__ import annotations

import pytest

from maverick.speckit.errors import SpeckitParseError
from maverick.speckit.parser import parse_spec_md


class TestTitleExtraction:
    def test_title_from_feature_specification_heading(self, full_spec_md: str) -> None:
        parsed = parse_spec_md(full_spec_md)
        assert parsed.title == "Sample Feature"

    def test_title_falls_back_to_first_h1(self) -> None:
        content = "# Just A Heading\n\nSome content.\n"
        parsed = parse_spec_md(content)
        assert parsed.title == "Just A Heading"

    def test_title_empty_when_no_heading_but_has_success_criteria(self) -> None:
        content = "## Success Criteria\n\n### Measurable Outcomes\n\n- **SC-001**: fast\n"
        parsed = parse_spec_md(content)
        assert parsed.title == ""
        assert parsed.success_criteria == ("**SC-001**: fast",)


class TestSuccessCriteria:
    def test_sc_bullets_extracted(self, full_spec_md: str) -> None:
        parsed = parse_spec_md(full_spec_md)
        assert len(parsed.success_criteria) == 2
        assert all(sc.startswith("**SC-") for sc in parsed.success_criteria)

    def test_missing_success_criteria_section_yields_empty_tuple(self) -> None:
        content = "# Feature Specification: X\n\nNo success criteria here.\n"
        parsed = parse_spec_md(content)
        assert parsed.success_criteria == ()


class TestStoryScenarios:
    def test_scenarios_keyed_by_story_id(self, full_spec_md: str) -> None:
        parsed = parse_spec_md(full_spec_md)
        assert "US1" in parsed.story_scenarios
        assert "US2" in parsed.story_scenarios
        assert len(parsed.story_scenarios["US1"]) == 2
        assert len(parsed.story_scenarios["US2"]) == 1

    def test_story_without_scenarios_maps_to_empty_tuple(self) -> None:
        content = """\
# Feature Specification: X

### User Story 1 - No Scenarios (Priority: P1)

Narrative only, no Acceptance Scenarios subsection.
"""
        parsed = parse_spec_md(content)
        assert parsed.story_scenarios["US1"] == ()


class TestEmptySpec:
    def test_empty_spec_raises_parse_error(self) -> None:
        with pytest.raises(SpeckitParseError) as exc_info:
            parse_spec_md("Just some prose with no structure at all.\n", file="spec.md")
        err = exc_info.value
        assert err.file == "spec.md"
        assert err.expected
        assert err.suggestion
