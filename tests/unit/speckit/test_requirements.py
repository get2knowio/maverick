"""Unit tests for the requirement-block grammar (speckit/requirements.py).

Each case here mirrors a measured corpus reality from
``specs/059-spec-delta-layer/contracts/requirement-block-grammar.md``
(research R1) — a synthetic, minimal reproduction of the shape that
matters, so a regression is traceable to the exact rule it violates
rather than requiring a 54-file diff to notice.
"""

from __future__ import annotations

import pytest

from maverick.speckit.errors import SpeckitParseError
from maverick.speckit.requirements import (
    PassthroughLines,
    RequirementBlock,
    parse_requirements,
    render_requirements,
)


def _round_trips(text: str) -> None:
    section = parse_requirements(text)
    assert render_requirements(section) == text


class TestLetterSuffixedIds:
    """34 ids across 13 specs carry a letter suffix (research R1)."""

    def test_letter_suffixed_id_parses(self) -> None:
        text = (
            "# Spec\n\n### Functional Requirements\n\n"
            "- **FR-019**: The base requirement.\n"
            "- **FR-019c**: A follow-on clarification.\n"
            "- **FR-020**: The next requirement.\n\n"
            "### Key Entities\n"
        )
        section = parse_requirements(text)
        ids = [b.req_id for b in section.blocks()]
        assert ids == ["FR-019", "FR-019c", "FR-020"]
        _round_trips(text)

    def test_bare_three_digit_id_required(self) -> None:
        # FR-1 (no zero-padding) must not match the block-start pattern —
        # it becomes passthrough content instead of a phantom requirement.
        text = (
            "### Functional Requirements\n\n- **FR-1**: Not a real id shape.\n\n### Key Entities\n"
        )
        section = parse_requirements(text)
        assert section.blocks() == ()
        _round_trips(text)


class TestNonTerminators:
    """Blank lines, ``####`` headings, and bold pseudo-headings must never
    terminate a block or the section (grammar contract's "Three things
    that MUST NOT terminate a block")."""

    def test_blank_line_does_not_terminate_block(self) -> None:
        # Spec 027 blank-separates every requirement and blank-separates
        # sub-bullets from their parent.
        text = (
            "### Functional Requirements\n\n"
            "- **FR-001**: The system MUST do a thing.\n\n"
            "  - A sub-bullet, blank-separated from its parent.\n\n"
            "- **FR-002**: A second requirement.\n\n"
            "### Key Entities\n"
        )
        section = parse_requirements(text)
        blocks = section.blocks()
        assert len(blocks) == 2
        assert blocks[0].sub_bullets == ("  - A sub-bullet, blank-separated from its parent.\n",)
        _round_trips(text)

    def test_hash4_heading_does_not_terminate_section(self) -> None:
        # 104 occurrences across 20 specs: an in-block *grouping* heading,
        # never a section terminator.
        text = (
            "### Functional Requirements\n\n"
            "#### Safety Hooks (PreToolUse)\n\n"
            "- **FR-001**: The system MUST do a thing.\n"
            "- **FR-002**: The system MUST do another thing.\n\n"
            "### Key Entities\n"
        )
        section = parse_requirements(text)
        assert [b.req_id for b in section.blocks()] == ["FR-001", "FR-002"]
        # The #### heading survives as passthrough, not swallowed.
        assert any(
            isinstance(el, PassthroughLines) and any("Safety Hooks" in line for line in el.lines)
            for el in section.elements
        )
        _round_trips(text)

    def test_bold_pseudo_heading_is_ordinary_block_content(self) -> None:
        # 29 occurrences across specs 010, 016, 052, 055 — indent-2
        # content inside a block, not a section-level element.
        text = (
            "### Functional Requirements\n\n"
            "- **FR-001**: The system MUST persist records.\n"
            "  **Data Structures**:\n"
            "  - A record has an id and a value.\n\n"
            "### Key Entities\n"
        )
        section = parse_requirements(text)
        block = section.blocks()[0]
        assert "  **Data Structures**:\n" in block.continuation
        _round_trips(text)


class TestBlockContents:
    def test_indent2_continuation_lines(self) -> None:
        # 371 occurrences across 6 specs — hard-wrapped prose.
        text = (
            "### Functional Requirements\n\n"
            "- **FR-001**: The system MUST do a thing that requires\n"
            "  a fair amount of explanation across more than one\n"
            "  physical line before it is fully specified.\n\n"
            "### Key Entities\n"
        )
        section = parse_requirements(text)
        block = section.blocks()[0]
        assert len(block.continuation) == 2
        assert block.sub_bullets == ()
        _round_trips(text)

    def test_indent2_sub_bullets_not_blank_separated(self) -> None:
        # Spec 007's style: sub-bullets directly under the header line.
        text = (
            "### Functional Requirements\n\n"
            "- **FR-001**: The system MUST support the following:\n"
            "  - First sub-requirement.\n"
            "  - Second sub-requirement.\n\n"
            "### Key Entities\n"
        )
        section = parse_requirements(text)
        block = section.blocks()[0]
        assert len(block.sub_bullets) == 2
        _round_trips(text)


class TestOrdering:
    def test_out_of_numeric_order_ids_are_preserved_in_file_order(self) -> None:
        # Specs 015 and 050 have complete id sets out of numeric order —
        # sorting would silently reorder them.
        text = (
            "### Functional Requirements\n\n"
            "- **FR-003**: Comes first in the file.\n"
            "- **FR-001**: Comes second in the file.\n"
            "- **FR-002**: Comes third in the file.\n\n"
            "### Key Entities\n"
        )
        section = parse_requirements(text)
        assert [b.req_id for b in section.blocks()] == ["FR-003", "FR-001", "FR-002"]
        _round_trips(text)


class TestSectionAnchor:
    def test_missing_section_raises(self) -> None:
        text = "# Spec\n\nNo requirements section anywhere in this file.\n"
        with pytest.raises(SpeckitParseError):
            parse_requirements(text)

    def test_split_headings_variant_round_trips(self) -> None:
        # Legacy spec 004's style: three "### Functional Requirements -
        # <suffix>" sub-headings instead of one bare heading. The whole
        # span must still round-trip, and each sub-heading survives as
        # passthrough rather than truncating the section.
        text = (
            "## Requirements\n\n"
            "### Functional Requirements - Alpha\n\n"
            "- **FR-001**: First agent's requirement.\n\n"
            "### Functional Requirements - Beta\n\n"
            "- **FR-002**: Second agent's requirement.\n\n"
            "### Key Entities\n\nSomething else entirely.\n"
        )
        section = parse_requirements(text)
        assert [b.req_id for b in section.blocks()] == ["FR-001", "FR-002"]
        _round_trips(text)

    def test_section_runs_to_eof_with_no_terminator(self) -> None:
        text = "### Functional Requirements\n\n- **FR-001**: The only requirement.\n"
        section = parse_requirements(text)
        assert [b.req_id for b in section.blocks()] == ["FR-001"]
        _round_trips(text)


class TestNormalizedLength:
    def test_normalized_length_collapses_whitespace(self) -> None:
        block = RequirementBlock(
            req_id="FR-001",
            header_line="- **FR-001**: A   thing.\n",
            body_lines=("  more   text\n",),
            line_number=1,
        )
        # "- **FR-001**: A thing. more text" (whitespace-collapsed)
        assert block.normalized_length == len("- **FR-001**: A thing. more text")
