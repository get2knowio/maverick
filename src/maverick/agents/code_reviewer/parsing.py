"""Parsing utilities for CodeReviewerAgent.

This module contains functions for parsing and normalizing Claude's response:
- JSON extraction from markdown-wrapped responses
- Finding validation and severity normalization via validate_output
- Response structure parsing
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, model_validator

from maverick.agents.contracts import validate_output
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.models.review import ReviewFinding

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal wrapper model for validate_output integration
# ---------------------------------------------------------------------------


class _FindingsWrapper(BaseModel):
    """Internal wrapper that validates a findings array via validate_output.

    Uses a model_validator(mode='before') to normalize invalid severity values
    to SUGGESTION before Pydantic field validation runs. This preserves the
    existing T029 behavior (graceful severity defaulting) while using the
    contracts module for JSON extraction.
    """

    # list[Any] is intentional (not list[ReviewFinding]): enables per-finding
    # graceful degradation — one invalid finding won't reject the entire
    # response.  Individual findings are validated separately in parse_findings().
    findings: list[Any] = []

    # Populated once at first use to avoid circular import at module level
    _valid_severities: ClassVar[set[str] | None] = None
    _default_severity: ClassVar[str | None] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_severities(cls, data: Any) -> Any:
        """Normalize invalid severity values before field validation (T029)."""
        if not isinstance(data, dict):
            return data

        # Lazy-load severity constants to avoid circular import
        if cls._valid_severities is None:
            from maverick.models.review import ReviewSeverity

            cls._valid_severities = {s.value for s in ReviewSeverity}
            cls._default_severity = ReviewSeverity.SUGGESTION.value

        findings_data = data.get("findings")
        if not isinstance(findings_data, list):
            return data

        for idx, finding in enumerate(findings_data):
            if not isinstance(finding, dict):
                continue
            severity_value = finding.get("severity")
            if (
                severity_value is not None
                and severity_value not in cls._valid_severities
            ):
                logger.warning(
                    "invalid_severity_defaulting",
                    severity_value=severity_value,
                    index=idx,
                    default=cls._default_severity,
                )
                finding["severity"] = cls._default_severity

        return data


def extract_json(text: str) -> str | None:
    """Extract JSON from text that may be wrapped in markdown code blocks.

    Retained for backward compatibility. New code should prefer
    ``validate_output()`` from ``maverick.agents.contracts``.

    .. deprecated::
        Use ``validate_output()`` from ``maverick.agents.contracts`` instead.

    Handles formats like:
    - Plain JSON
    - ```json ... ```
    - ``` ... ```

    Args:
        text: Raw text that may contain JSON.

    Returns:
        Extracted JSON string, or None if no JSON found.
    """
    import warnings

    warnings.warn(
        "extract_json() is deprecated. "
        "Use validate_output() from maverick.agents.contracts instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Try to extract from markdown code block first
    # Pattern: ```json ... ``` or ``` ... ```
    code_block_pattern = r"```(?:json)?\s*\n(.*?)\n```"
    match = re.search(code_block_pattern, text, re.DOTALL)

    if match:
        return match.group(1).strip()

    # Try to find JSON object or array in the text
    # Look for opening { or [ and try to parse from there
    json_start = text.find("{")
    if json_start == -1:
        json_start = text.find("[")

    if json_start != -1:
        # Try to parse from this position to the end
        potential_json = text[json_start:].strip()
        try:
            # Validate it's parseable JSON
            json.loads(potential_json)
            return potential_json
        except json.JSONDecodeError:
            # Try to find the closing bracket
            # This is a simple heuristic - may not work for all cases
            pass

    # No JSON found
    return None


def parse_findings(response: str) -> list[ReviewFinding]:
    """Parse structured findings from Claude response (FR-011, FR-016).

    Uses ``validate_output()`` from ``maverick.agents.contracts`` to extract
    JSON from markdown code blocks and validate against a ``_FindingsWrapper``
    model. The wrapper normalizes invalid severity values to SUGGESTION before
    Pydantic validation (T029).

    Individual findings that fail Pydantic validation are logged and skipped
    (graceful degradation).

    Args:
        response: Raw text response from Claude (expected to contain JSON).

    Returns:
        List of ReviewFinding objects extracted from response.

    Raises:
        No exceptions - gracefully degrades to empty list on errors.
    """
    from maverick.models.review import ReviewFinding

    # Use validate_output with strict=False for graceful fallback
    wrapper = validate_output(response, _FindingsWrapper, strict=False)

    if wrapper is None:
        logger.warning(
            "validate_output_returned_none",
            context="findings_extraction",
        )
        return []

    # wrapper.findings contains raw dicts (Any) after severity normalization.
    # Validate each individually so one bad finding doesn't discard the rest.
    findings: list[ReviewFinding] = []
    for idx, finding_data in enumerate(wrapper.findings):
        try:
            if isinstance(finding_data, dict):
                finding = ReviewFinding.model_validate(finding_data)
            elif isinstance(finding_data, ReviewFinding):
                finding = finding_data
            else:
                logger.warning(
                    "unexpected_finding_type",
                    index=idx,
                    finding_type=type(finding_data).__name__,
                )
                continue

            # T035: Log if finding has empty or very short suggestion
            if not finding.suggestion or len(finding.suggestion.strip()) < 10:
                logger.debug(
                    "finding_insufficient_suggestion",
                    index=idx,
                    file=finding.file,
                    line=finding.line,
                )

            findings.append(finding)
        except Exception as e:
            logger.warning(
                "finding_validation_failed",
                index=idx,
                error=str(e),
                data=finding_data,
            )
            # Continue processing remaining findings (graceful degradation)
            continue

    # T035: Track findings with missing suggestions for potential enhancement
    findings_without_suggestions = sum(
        1 for f in findings if not f.suggestion or len(f.suggestion.strip()) < 10
    )
    if findings_without_suggestions > 0:
        logger.info(
            "findings_lacking_suggestions",
            without_suggestions=findings_without_suggestions,
            total=len(findings),
        )

    return findings
