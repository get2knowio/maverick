"""Utility functions for reviewer agents.

This module provides helper functions for parsing and validating
structured findings from reviewer responses.
"""

from __future__ import annotations

import json
import re
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)

# Valid values for severity and category fields
VALID_SEVERITIES = {"critical", "major", "minor"}
VALID_CATEGORIES = {
    "security",
    "correctness",
    "performance",
    "maintainability",
    "spec_compliance",
    "style",
    "other",
}

# Required fields for a valid finding
REQUIRED_FIELDS = {"id", "severity", "category", "title", "description"}


def parse_findings(response: str, id_prefix: str) -> list[dict[str, Any]]:
    """Extract JSON findings from reviewer response.

    Looks for a JSON block in the response containing a "findings" array.
    Tries multiple extraction strategies:
    1. Look for ```json ... ``` markdown code block
    2. Look for raw JSON object { "findings": ... }

    Args:
        response: Full reviewer response text.
        id_prefix: Expected prefix for finding IDs (RS or RT).
            Currently unused but reserved for future validation.

    Returns:
        List of finding dictionaries.

    Raises:
        ValueError: If JSON cannot be parsed or no findings block found.
    """
    if not response:
        raise ValueError("Empty response")

    # Strategy 1: Look for ```json ... ``` markdown code block
    json_block_pattern = r"```json\s*([\s\S]*?)\s*```"
    matches = re.findall(json_block_pattern, response)

    for match in matches:
        try:
            data = json.loads(match)
            if isinstance(data, dict) and "findings" in data:
                findings = data["findings"]
                if isinstance(findings, list):
                    logger.debug(
                        "parsed_findings_from_markdown",
                        count=len(findings),
                        id_prefix=id_prefix,
                    )
                    return findings
        except json.JSONDecodeError:
            continue

    # Strategy 2: Look for raw JSON object with "findings" key
    # Find potential JSON objects in the response
    json_object_pattern = (
        r'\{\s*"findings"\s*:\s*\[[\s\S]*?\]\s*'
        r'(?:,\s*"summary"\s*:\s*"[^"]*")?\s*\}'
    )
    matches = re.findall(json_object_pattern, response)

    for match in matches:
        try:
            data = json.loads(match)
            if isinstance(data, dict) and "findings" in data:
                findings = data["findings"]
                if isinstance(findings, list):
                    logger.debug(
                        "parsed_findings_from_raw_json",
                        count=len(findings),
                        id_prefix=id_prefix,
                    )
                    return findings
        except json.JSONDecodeError:
            continue

    # Strategy 3: Try to find any JSON object and check for findings
    # More lenient pattern for edge cases
    brace_positions = []
    depth = 0
    start = None
    for i, char in enumerate(response):
        if char == "{":
            if depth == 0:
                start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                brace_positions.append((start, i + 1))
                start = None

    for start_pos, end_pos in brace_positions:
        try:
            candidate = response[start_pos:end_pos]
            data = json.loads(candidate)
            if isinstance(data, dict) and "findings" in data:
                findings = data["findings"]
                if isinstance(findings, list):
                    logger.debug(
                        "parsed_findings_from_brute_force",
                        count=len(findings),
                        id_prefix=id_prefix,
                    )
                    return findings
        except json.JSONDecodeError:
            continue

    raise ValueError("No valid findings JSON block found in response")


def validate_findings(
    findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate findings have required fields and valid values.

    Checks each finding for:
    - Required fields: id, severity, category, title, description
    - Valid severity values: critical, major, minor
    - Valid category values: security, correctness, performance, etc.
    - Optional field validation: line_start/line_end are positive integers

    Args:
        findings: Raw parsed findings list.

    Returns:
        Tuple of (valid_findings, validation_errors).
        validation_errors contains human-readable error messages.
    """
    valid_findings: list[dict[str, Any]] = []
    errors: list[str] = []

    for i, finding in enumerate(findings):
        finding_id = finding.get("id", f"finding_{i}")
        finding_errors: list[str] = []

        # Check required fields
        for field in REQUIRED_FIELDS:
            if field not in finding or not finding[field]:
                finding_errors.append(f"missing required field '{field}'")

        # Validate severity
        severity = finding.get("severity")
        if severity and severity not in VALID_SEVERITIES:
            valid_opts = ", ".join(sorted(VALID_SEVERITIES))
            finding_errors.append(
                f"invalid severity '{severity}', must be one of: {valid_opts}"
            )

        # Validate category
        category = finding.get("category")
        if category and category not in VALID_CATEGORIES:
            valid_opts = ", ".join(sorted(VALID_CATEGORIES))
            finding_errors.append(
                f"invalid category '{category}', must be one of: {valid_opts}"
            )

        # Validate optional line numbers
        line_start = finding.get("line_start")
        if line_start is not None and (
            not isinstance(line_start, int) or line_start < 1
        ):
            finding_errors.append(
                f"invalid line_start '{line_start}', must be a positive integer"
            )

        line_end = finding.get("line_end")
        if line_end is not None and (not isinstance(line_end, int) or line_end < 1):
            finding_errors.append(
                f"invalid line_end '{line_end}', must be a positive integer"
            )

        if finding_errors:
            errors.append(f"Finding {finding_id}: {'; '.join(finding_errors)}")
        else:
            valid_findings.append(finding)

    return valid_findings, errors
