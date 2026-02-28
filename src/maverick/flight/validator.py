"""Flight plan structural validator.

Validates a flight plan Markdown file against the defined rules V1–V9
using the existing parser primitives.

Public API:
    ValidationIssue — frozen dataclass describing a single structural problem.
    validate_flight_plan_file(path) -> list[ValidationIssue]
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from maverick.flight.errors import FlightPlanParseError
from maverick.flight.parser import parse_flight_plan_sections, parse_frontmatter
from maverick.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single structural issue found during flight plan validation.

    Attributes:
        location: Human-readable location reference (e.g. ``"frontmatter.name"``
            or ``"section.objective"``).
        message: Description of what is wrong.
    """

    location: str
    message: str


def validate_flight_plan_file(path: Path) -> list[ValidationIssue]:
    """Validate a flight plan file and return all structural issues found.

    Checks the following rules in order:

    **Frontmatter (blocking — V1–V3)**:
        V1: Document must start with ``---`` delimiter.
        V2: Must have closing ``---`` delimiter.
        V3: YAML must be parseable.

    If any of V1–V3 fail, the function returns immediately with those issues;
    section checks (V7–V9) are skipped.

    **Frontmatter fields (V4–V6)**:
        V4: ``name`` must be present and non-empty.
        V5: ``version`` must be present and non-empty.
        V6: ``created`` must be present.

    **Body sections (V7–V9)**:
        V7: ``## Objective`` section must exist and be non-empty.
        V8: ``## Success Criteria`` section must contain at least one checkbox item.
        V9: ``## Scope`` section must exist.

    Args:
        path: Path to the flight plan Markdown file.

    Returns:
        Empty list if valid; list of :class:`ValidationIssue` for each problem.

    Raises:
        FileNotFoundError: Re-raised as-is when *path* does not exist; the CLI
            layer is responsible for producing a user-friendly message.
    """
    logger.debug("validating_flight_plan", path=str(path))

    # Read file — let FileNotFoundError propagate to caller.
    content = path.read_text(encoding="utf-8")

    issues: list[ValidationIssue] = []

    # ------------------------------------------------------------------
    # V1–V3: Frontmatter (blocking)
    # ------------------------------------------------------------------
    try:
        frontmatter, body = parse_frontmatter(content)
    except FlightPlanParseError as exc:
        # Classify by structured error_kind set by the parser.
        error_kind = exc.error_kind
        if error_kind == "missing_opening_delimiter":
            # V1: no opening --- delimiter
            issues.append(
                ValidationIssue(
                    location="frontmatter",
                    message=(
                        "V1: Document must start with '---' frontmatter delimiter."
                    ),
                )
            )
        elif error_kind == "missing_closing_delimiter":
            # V2: no closing --- delimiter
            issues.append(
                ValidationIssue(
                    location="frontmatter",
                    message=(
                        "V2: Document is missing the closing"
                        " '---' frontmatter delimiter."
                    ),
                )
            )
        else:
            # V3: YAML parse error (or any other parse failure)
            issues.append(
                ValidationIssue(
                    location="frontmatter",
                    message=f"V3: YAML frontmatter is not parseable. ({exc})",
                )
            )
        # Frontmatter rules are blocking — skip section checks.
        return issues

    # ------------------------------------------------------------------
    # V4: frontmatter.name must be present and non-empty
    # ------------------------------------------------------------------
    name_val = frontmatter.get("name")
    if name_val is None or not str(name_val).strip():
        issues.append(
            ValidationIssue(
                location="frontmatter.name",
                message="V4: Frontmatter field 'name' must be present and non-empty.",
            )
        )

    # ------------------------------------------------------------------
    # V5: frontmatter.version must be present and non-empty
    # ------------------------------------------------------------------
    version_val = frontmatter.get("version")
    if version_val is None or not str(version_val).strip():
        issues.append(
            ValidationIssue(
                location="frontmatter.version",
                message=(
                    "V5: Frontmatter field 'version' must be present and non-empty."
                ),
            )
        )

    # ------------------------------------------------------------------
    # V6: frontmatter.created must be present
    # ------------------------------------------------------------------
    if "created" not in frontmatter:
        issues.append(
            ValidationIssue(
                location="frontmatter.created",
                message="V6: Frontmatter field 'created' must be present.",
            )
        )

    # ------------------------------------------------------------------
    # V7–V9: Body sections
    # ------------------------------------------------------------------
    sections = parse_flight_plan_sections(body)

    # V7: ## Objective must exist and be non-empty
    objective = sections.get("objective", "")
    if not objective or not str(objective).strip():
        issues.append(
            ValidationIssue(
                location="section.objective",
                message=("V7: '## Objective' section must be present and non-empty."),
            )
        )

    # V8: ## Success Criteria must contain at least one checkbox item
    success_criteria = sections.get("success_criteria", [])
    if not success_criteria:
        issues.append(
            ValidationIssue(
                location="section.success_criteria",
                message=(
                    "V8: '## Success Criteria' section must contain at least one "
                    "checkbox item (- [ ] or - [x])."
                ),
            )
        )

    # V9: ## Scope must exist
    # parse_flight_plan_sections always returns a scope dict with empty lists when
    # the section is absent; we detect the missing section by checking the body.
    if "## Scope" not in body:
        issues.append(
            ValidationIssue(
                location="section.scope",
                message="V9: '## Scope' section must be present.",
            )
        )

    return issues


__all__ = ["ValidationIssue", "validate_flight_plan_file"]
