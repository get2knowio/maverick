"""Parsing utilities for CodeReviewerAgent.

This module contains functions for parsing and normalizing Claude's response:
- JSON extraction from markdown-wrapped responses
- Finding validation and severity normalization
- Response structure parsing
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.models.review import ReviewFinding

logger = get_logger(__name__)


def extract_json(text: str) -> str | None:
    """Extract JSON from text that may be wrapped in markdown code blocks.

    Handles formats like:
    - Plain JSON
    - ```json ... ```
    - ``` ... ```

    Args:
        text: Raw text that may contain JSON.

    Returns:
        Extracted JSON string, or None if no JSON found.
    """
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

    Extracts ReviewFinding objects from the JSON response. Handles
    malformed responses gracefully by logging errors and returning
    partial results. Validates severity levels and defaults to SUGGESTION
    for invalid severities (T029).

    Args:
        response: Raw text response from Claude (expected to contain JSON).

    Returns:
        List of ReviewFinding objects extracted from response.

    Raises:
        No exceptions - gracefully degrades to empty list on errors.
    """
    # Import here to avoid circular dependency
    from maverick.models.review import ReviewFinding, ReviewSeverity

    # Extract JSON from response (may be wrapped in markdown code blocks)
    json_str = extract_json(response)

    if not json_str:
        logger.warning("No JSON found in response, returning empty findings list")
        return []

    # Parse JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return []

    # Extract findings array from the response
    findings_data = data.get("findings", [])
    if not isinstance(findings_data, list):
        logger.warning("'findings' field is not a list, returning empty")
        return []

    # Parse each finding with Pydantic validation
    findings: list[ReviewFinding] = []
    for idx, finding_dict in enumerate(findings_data):
        try:
            # Explicit severity validation before Pydantic validation (T029)
            if "severity" in finding_dict:
                severity_value = finding_dict["severity"]
                valid_severities = {s.value for s in ReviewSeverity}

                if severity_value not in valid_severities:
                    logger.warning(
                        f"Invalid severity '{severity_value}' at index {idx}, "
                        f"using SUGGESTION as default"
                    )
                    finding_dict["severity"] = ReviewSeverity.SUGGESTION.value

            finding = ReviewFinding.model_validate(finding_dict)

            # T035: Log if finding has empty or very short suggestion
            if not finding.suggestion or len(finding.suggestion.strip()) < 10:
                logger.debug(
                    f"Finding at index {idx} has empty or insufficient suggestion "
                    f"(file: {finding.file}, line: {finding.line})"
                )

            findings.append(finding)
        except Exception as e:
            logger.warning(
                f"Failed to validate finding at index {idx}: {e}. Data: {finding_dict}"
            )
            # Continue processing remaining findings (graceful degradation)
            continue

    # T035: Track findings with missing suggestions for potential enhancement
    findings_without_suggestions = sum(
        1 for f in findings if not f.suggestion or len(f.suggestion.strip()) < 10
    )
    if findings_without_suggestions > 0:
        logger.info(
            f"Review completed with {findings_without_suggestions} finding(s) "
            f"lacking detailed suggestions out of {len(findings)} total"
        )

    return findings
