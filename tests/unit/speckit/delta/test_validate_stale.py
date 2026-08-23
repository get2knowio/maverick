"""Unit tests for the ``stale-before`` check: a ``### Before`` block that
does not match the spec's current block is rejected — including the
whitespace-normalization boundary that must NOT falsely reject a
before-block that only differs in wrapping/whitespace."""

from __future__ import annotations

from pathlib import Path

from maverick.speckit.delta.parser import parse_delta_md
from maverick.speckit.delta.validate import validate_delta
from maverick.speckit.requirements import parse_requirements

_SPEC_MD = """\
# Feature Specification: Sample

### Functional Requirements

- **FR-002**: The gate MUST evaluate the frontier before curating.
- **FR-014**: The land gate MUST block on any open entry of medium or
  higher severity.

### Key Entities
"""

_PATH = Path("specs/052-conditional-landing/deltas/001-sample.md")


def _codes(delta_text: str) -> list[str]:
    doc = parse_delta_md(delta_text, path=_PATH)
    section = parse_requirements(_SPEC_MD)
    problems = validate_delta(doc, spec_section=section)
    return [p.code for p in problems]


def test_stale_before_rejected_on_mismatched_text() -> None:
    codes = _codes(
        "# Delta: stale\n\n**Target**: 052\n\n"
        "## MODIFIED FR-002\n\n"
        "### Before\n\n- **FR-002**: This is not what the spec currently says.\n\n"
        "### After\n\n- **FR-002**: Something new that is long enough to pass the guard.\n"
    )
    assert "stale-before" in codes


def test_stale_before_rejected_on_removed_operation_too() -> None:
    codes = _codes(
        "# Delta: stale removal\n\n**Target**: 052\n\n"
        "## REMOVED FR-002\n\n### Before\n\n- **FR-002**: Wrong text entirely.\n"
    )
    assert "stale-before" in codes


def test_reflowed_line_wrap_is_not_stale() -> None:
    # Same content, wrapped onto a different line boundary — the
    # whitespace-normalization boundary the check must not misfire on.
    codes = _codes(
        "# Delta: reflow\n\n**Target**: 052\n\n"
        "## MODIFIED FR-002\n\n"
        "### Before\n\n- **FR-002**: The gate MUST evaluate the frontier\n"
        "  before curating.\n\n"
        "### After\n\n- **FR-002**: The gate MUST evaluate the frontier before "
        "curating, with an audit log entry recorded for every decision.\n"
    )
    assert "stale-before" not in codes


def test_trailing_whitespace_difference_is_not_stale() -> None:
    codes = _codes(
        "# Delta: trailing ws\n\n**Target**: 052\n\n"
        "## MODIFIED FR-014\n\n"
        "### Before\n\n- **FR-014**: The land gate MUST block on any open entry of "
        "medium or   \n  higher severity.\n\n"
        "### After\n\n- **FR-014**: The land gate MUST block on any open entry of "
        "medium or higher severity, with a logged reason.\n"
    )
    assert "stale-before" not in codes


def test_exact_match_is_not_stale() -> None:
    codes = _codes(
        "# Delta: exact\n\n**Target**: 052\n\n"
        "## MODIFIED FR-002\n\n"
        "### Before\n\n- **FR-002**: The gate MUST evaluate the frontier before curating.\n\n"
        "### After\n\n- **FR-002**: The gate MUST evaluate the frontier before curating "
        "and log the decision.\n"
    )
    assert "stale-before" not in codes
