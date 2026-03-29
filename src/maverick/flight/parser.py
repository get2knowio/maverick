"""Markdown + YAML frontmatter parser for flight plan documents.

Provides low-level parsing primitives used by FlightPlanFile and WorkUnitFile
loaders. All functions are pure (no I/O) for easy testing.

Public API:
    parse_frontmatter(content) -> tuple[dict, str]
    parse_checkbox_list(content) -> list[tuple[bool, str]]
    parse_bullet_list(content) -> list[str]
    parse_flight_plan_sections(body) -> dict[str, Any]
    parse_work_unit_sections(body) -> dict[str, Any]
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from maverick.flight.errors import FlightPlanParseError
from maverick.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_CHECKBOX_RE = re.compile(r"^-\s+\[([xX ])\]\s+(.+)$")
_BULLET_RE = re.compile(r"^-\s+(.+)$")
# Match [SC-NNN] suffix OR SC-XXX: prefix (both formats used by generators)
_TRACE_REF_RE = re.compile(r"\[SC-(\d+)\]\s*$")
_TRACE_REF_PREFIX_RE = re.compile(r"^(SC-[\w-]+):\s+")


# ---------------------------------------------------------------------------
# Core primitives
# ---------------------------------------------------------------------------


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Split a Markdown document into YAML frontmatter and body.

    The document must begin with ``---\\n`` and contain a second ``---``
    delimiter to close the frontmatter block.

    Args:
        content: Raw Markdown string with YAML frontmatter.

    Returns:
        A two-element tuple of (frontmatter_dict, markdown_body).

    Raises:
        FlightPlanParseError: If the ``---`` delimiters are missing or the
            YAML inside the frontmatter block is invalid.
    """
    if not content.startswith("---"):
        raise FlightPlanParseError(
            "Document does not start with '---' frontmatter delimiter",
            field="frontmatter",
            error_kind="missing_opening_delimiter",
        )

    # Split off the opening "---"
    rest = content[3:]
    # Match closing delimiter: "\n---" followed by newline or end-of-string.
    # Using a regex avoids false positives from "---" inside YAML values.
    _closing_re = re.search(r"\n---(\n|$)", rest)
    if _closing_re is None:
        raise FlightPlanParseError(
            "Document is missing the closing '---' frontmatter delimiter",
            field="frontmatter",
            error_kind="missing_closing_delimiter",
        )

    # Find the closing delimiter
    close_idx = _closing_re.start()
    yaml_block = rest[:close_idx]
    # Body starts after the closing ---\n
    body_start = close_idx + len("\n---")
    # Skip the newline immediately after the closing ---
    if body_start < len(rest) and rest[body_start] == "\n":
        body_start += 1
    body = rest[body_start:]

    try:
        fm: dict[str, Any] = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError as exc:
        raise FlightPlanParseError(
            f"Invalid YAML in frontmatter block: {exc}",
            field="frontmatter",
            error_kind="invalid_yaml",
        ) from exc

    return fm, body


def parse_checkbox_list(content: str) -> list[tuple[bool, str]]:
    """Parse Markdown checkbox list items from *content*.

    Recognises lines of the form ``- [x] text``, ``- [X] text``, and
    ``- [ ] text``.  All other lines are ignored.

    Args:
        content: Block of Markdown text.

    Returns:
        List of ``(checked, text)`` tuples in document order.
    """
    results: list[tuple[bool, str]] = []
    for line in content.splitlines():
        m = _CHECKBOX_RE.match(line.rstrip())
        if m:
            marker, text = m.group(1), m.group(2).strip()
            checked = marker.lower() == "x"
            results.append((checked, text))
    return results


def parse_bullet_list(content: str) -> list[str]:
    """Parse Markdown bullet list items from *content*.

    Recognises lines of the form ``- text``.  All other lines are ignored.

    Args:
        content: Block of Markdown text.

    Returns:
        List of bullet text strings in document order.
    """
    results: list[str] = []
    for line in content.splitlines():
        m = _BULLET_RE.match(line.rstrip())
        if m:
            results.append(m.group(1).strip())
    return results


# ---------------------------------------------------------------------------
# Section splitting helpers
# ---------------------------------------------------------------------------


def _split_h2_sections(body: str) -> dict[str, str]:
    """Split a Markdown body on ``## `` headings.

    Args:
        body: Markdown body text (without frontmatter).

    Returns:
        Dict mapping heading text (case-preserved) to section content (not
        including the heading line itself).
    """
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in body.splitlines():
        if line.startswith("## "):
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def _split_h3_sections(content: str) -> dict[str, str]:
    """Split section content on ``### `` sub-headings.

    Args:
        content: Text content of an ``## `` section.

    Returns:
        Dict mapping sub-heading text (case-preserved) to sub-section content.
    """
    subsections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in content.splitlines():
        if line.startswith("### "):
            if current_key is not None:
                subsections[current_key] = "\n".join(current_lines).strip()
            current_key = line[4:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_key is not None:
        subsections[current_key] = "\n".join(current_lines).strip()

    return subsections


# ---------------------------------------------------------------------------
# Flight Plan section parser
# ---------------------------------------------------------------------------


def parse_flight_plan_sections(body: str) -> dict[str, Any]:
    """Extract structured sections from a Flight Plan Markdown body.

    Expected sections (case-sensitive heading names):
    - ``## Objective`` — plain text
    - ``## Success Criteria`` — checkbox list
    - ``## Scope`` — has ``### In``, ``### Out``, ``### Boundaries`` sub-sections
    - ``## Context`` — plain text (optional)
    - ``## Constraints`` — bullet list (optional)
    - ``## Notes`` — plain text (optional)

    Args:
        body: Markdown body text after frontmatter has been stripped.

    Returns:
        Dict with keys: ``objective``, ``success_criteria``, ``scope``,
        ``context``, ``constraints``, ``notes``.  The ``scope`` value is
        itself a dict with keys ``in_scope``, ``out_of_scope``,
        ``boundaries``.
    """
    h2 = _split_h2_sections(body)

    objective = h2.get("Objective", "").strip()
    success_criteria = parse_checkbox_list(h2.get("Success Criteria", ""))

    scope_content = h2.get("Scope", "")
    h3_scope = _split_h3_sections(scope_content)
    scope: dict[str, list[str]] = {
        "in_scope": parse_bullet_list(h3_scope.get("In", "")),
        "out_of_scope": parse_bullet_list(h3_scope.get("Out", "")),
        "boundaries": parse_bullet_list(h3_scope.get("Boundaries", "")),
    }

    context = h2.get("Context", "").strip()
    constraints = parse_bullet_list(h2.get("Constraints", ""))
    notes = h2.get("Notes", "").strip()

    return {
        "objective": objective,
        "success_criteria": success_criteria,
        "scope": scope,
        "context": context,
        "constraints": constraints,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Work Unit section parser
# ---------------------------------------------------------------------------


def _parse_acceptance_criteria_line(line: str) -> tuple[str, str | None] | None:
    """Parse a single acceptance criterion bullet line.

    Args:
        line: A single line from the Acceptance Criteria section.

    Returns:
        ``(text, trace_ref)`` tuple, or ``None`` if line is not a bullet.
        ``trace_ref`` is ``None`` when no ``[SC-###]`` suffix is present.
    """
    m = _BULLET_RE.match(line.rstrip())
    if not m:
        return None
    raw_text = m.group(1).strip()
    # Try [SC-NNN] suffix first (e.g., "Some criterion [SC-001]")
    trace_m = _TRACE_REF_RE.search(raw_text)
    if trace_m:
        trace_ref: str | None = f"SC-{trace_m.group(1)}"
        text = raw_text[: trace_m.start()].strip()
    else:
        # Try SC-XXX: prefix (e.g., "SC-B1-default: Some criterion")
        prefix_m = _TRACE_REF_PREFIX_RE.match(raw_text)
        if prefix_m:
            trace_ref = prefix_m.group(1)
            text = raw_text[prefix_m.end():].strip()
        else:
            trace_ref = None
            text = raw_text
    return text, trace_ref


def parse_work_unit_sections(body: str) -> dict[str, Any]:
    """Extract structured sections from a Work Unit Markdown body.

    Expected sections:
    - ``## Task`` — plain text
    - ``## Acceptance Criteria`` — bullet list with optional ``[SC-###]`` refs
    - ``## File Scope`` — has ``### Create``, ``### Modify``, ``### Protect``
    - ``## Instructions`` — plain text
    - ``## Verification`` — bullet list (command strings)
    - ``## Provider Hints`` — plain text (optional)

    Args:
        body: Markdown body text after frontmatter has been stripped.

    Returns:
        Dict with keys: ``task``, ``acceptance_criteria``, ``file_scope``,
        ``instructions``, ``verification``, ``provider_hints``.
        ``acceptance_criteria`` is a list of ``(text, trace_ref | None)``.
        ``file_scope`` is a dict with ``create``, ``modify``, ``protect``.
    """
    h2 = _split_h2_sections(body)

    task = h2.get("Task", "").strip()

    ac_content = h2.get("Acceptance Criteria", "")
    acceptance_criteria: list[tuple[str, str | None]] = []
    for line in ac_content.splitlines():
        parsed = _parse_acceptance_criteria_line(line)
        if parsed is not None:
            acceptance_criteria.append(parsed)

    file_scope_content = h2.get("File Scope", "")
    h3_scope = _split_h3_sections(file_scope_content)
    file_scope: dict[str, list[str]] = {
        "create": parse_bullet_list(h3_scope.get("Create", "")),
        "modify": parse_bullet_list(h3_scope.get("Modify", "")),
        "protect": parse_bullet_list(h3_scope.get("Protect", "")),
    }

    instructions = h2.get("Instructions", "").strip()
    verification = parse_bullet_list(h2.get("Verification", ""))

    test_specification = h2.get("Test Specification", "").strip()

    raw_hints = h2.get("Provider Hints", None)
    provider_hints: str | None = raw_hints.strip() if raw_hints is not None else None
    # Treat empty-string hints as None (section absent)
    if provider_hints == "":
        provider_hints = None

    return {
        "task": task,
        "acceptance_criteria": acceptance_criteria,
        "file_scope": file_scope,
        "instructions": instructions,
        "test_specification": test_specification,
        "verification": verification,
        "provider_hints": provider_hints,
    }


__all__ = [
    "parse_frontmatter",
    "parse_checkbox_list",
    "parse_bullet_list",
    "parse_flight_plan_sections",
    "parse_work_unit_sections",
]
