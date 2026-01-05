"""Tests for reviewer output parsing and validation utilities.

This module tests the parse_findings() and validate_findings() functions
that extract and validate structured JSON findings from reviewer responses.
"""

from __future__ import annotations

import pytest

from maverick.agents.reviewers.utils import (
    REQUIRED_FIELDS,
    VALID_CATEGORIES,
    VALID_SEVERITIES,
    parse_findings,
    validate_findings,
)


class TestParseFindingsMarkdown:
    """Test _parse_findings() extracts JSON from markdown code blocks."""

    def test_extracts_json_from_markdown_block(self) -> None:
        """Should extract findings from ```json ... ``` block."""
        response = """
## Review Summary

Here is my analysis of the code.

```json
{
  "findings": [
    {
      "id": "RS001",
      "severity": "major",
      "category": "correctness",
      "title": "Missing null check",
      "description": "The function does not check for null input"
    }
  ],
  "summary": "Found 1 issue"
}
```
"""
        findings = parse_findings(response, "RS")
        assert len(findings) == 1
        assert findings[0]["id"] == "RS001"
        assert findings[0]["severity"] == "major"
        assert findings[0]["category"] == "correctness"

    def test_extracts_multiple_findings(self) -> None:
        """Should extract all findings from the JSON block."""
        response = """
```json
{
  "findings": [
    {
      "id": "RT001",
      "severity": "critical",
      "category": "security",
      "title": "SQL injection",
      "description": "User input not sanitized"
    },
    {
      "id": "RT002",
      "severity": "minor",
      "category": "style",
      "title": "Long line",
      "description": "Line exceeds 120 characters"
    }
  ],
  "summary": "Found 2 issues"
}
```
"""
        findings = parse_findings(response, "RT")
        assert len(findings) == 2
        assert findings[0]["id"] == "RT001"
        assert findings[1]["id"] == "RT002"

    def test_extracts_empty_findings_list(self) -> None:
        """Should handle empty findings array."""
        response = """
```json
{"findings": [], "summary": "No issues found"}
```
"""
        findings = parse_findings(response, "RS")
        assert findings == []


class TestParseFindingsRawJson:
    """Test _parse_findings() handles raw JSON without markdown."""

    def test_extracts_raw_json_object(self) -> None:
        """Should find JSON object in plain text response."""
        # Using a multi-line JSON for readability
        json_block = """{
  "findings": [{
    "id": "RS001",
    "severity": "major",
    "category": "spec_compliance",
    "title": "Missing feature",
    "description": "Feature X from spec not implemented"
  }],
  "summary": "1 issue"
}"""
        response = f"""
After reviewing the code, here are my findings:

{json_block}

Please address the above issues.
"""
        findings = parse_findings(response, "RS")
        assert len(findings) == 1
        assert findings[0]["id"] == "RS001"

    def test_handles_json_with_optional_fields(self) -> None:
        """Should parse findings with optional fields."""
        response = """{
  "findings": [{
    "id": "RT001",
    "severity": "critical",
    "category": "security",
    "title": "XSS vulnerability",
    "description": "Unescaped HTML output",
    "file_path": "src/views/user.py",
    "line_start": 42,
    "line_end": 45,
    "suggested_fix": "Use html.escape()"
  }],
  "summary": "Critical security issue"
}"""
        findings = parse_findings(response, "RT")
        assert len(findings) == 1
        assert findings[0]["file_path"] == "src/views/user.py"
        assert findings[0]["line_start"] == 42
        assert findings[0]["line_end"] == 45
        assert findings[0]["suggested_fix"] == "Use html.escape()"


class TestParseFindingsErrors:
    """Test _parse_findings() error handling."""

    def test_raises_on_empty_response(self) -> None:
        """Should raise ValueError for empty response."""
        with pytest.raises(ValueError, match="Empty response"):
            parse_findings("", "RS")

    def test_raises_on_no_json_found(self) -> None:
        """Should raise ValueError when no JSON block exists."""
        response = """
## Review Summary

The code looks good. No issues found.

### Recommendations
- Consider adding more tests
"""
        with pytest.raises(ValueError, match="No valid findings JSON block found"):
            parse_findings(response, "RS")

    def test_raises_on_invalid_json(self) -> None:
        """Should raise ValueError for malformed JSON."""
        response = """
```json
{"findings": [{"id": "RS001", "severity": "major" missing comma}]}
```
"""
        with pytest.raises(ValueError, match="No valid findings JSON block"):
            parse_findings(response, "RS")

    def test_raises_when_findings_not_array(self) -> None:
        """Should raise ValueError when findings is not an array."""
        response = """
```json
{"findings": "not an array", "summary": "invalid"}
```
"""
        with pytest.raises(ValueError, match="No valid findings JSON block"):
            parse_findings(response, "RS")


class TestValidateFindingsAcceptsValid:
    """Test validate_findings() accepts valid findings."""

    def test_accepts_minimal_valid_finding(self) -> None:
        """Should accept finding with all required fields."""
        findings = [
            {
                "id": "RS001",
                "severity": "major",
                "category": "correctness",
                "title": "Missing null check",
                "description": "Function does not check for null input",
            }
        ]
        valid, errors = validate_findings(findings)
        assert len(valid) == 1
        assert errors == []

    def test_accepts_finding_with_all_optional_fields(self) -> None:
        """Should accept finding with all fields populated."""
        findings = [
            {
                "id": "RT001",
                "severity": "critical",
                "category": "security",
                "title": "SQL injection vulnerability",
                "description": "User input is not sanitized before query",
                "file_path": "src/db/queries.py",
                "line_start": 42,
                "line_end": 45,
                "suggested_fix": "Use parameterized queries",
            }
        ]
        valid, errors = validate_findings(findings)
        assert len(valid) == 1
        assert errors == []

    def test_accepts_multiple_valid_findings(self) -> None:
        """Should accept multiple valid findings."""
        findings = [
            {
                "id": "RS001",
                "severity": "major",
                "category": "spec_compliance",
                "title": "Missing feature",
                "description": "Feature X not implemented",
            },
            {
                "id": "RS002",
                "severity": "minor",
                "category": "style",
                "title": "Inconsistent naming",
                "description": "Variable names use mixed conventions",
            },
        ]
        valid, errors = validate_findings(findings)
        assert len(valid) == 2
        assert errors == []

    def test_accepts_all_valid_severities(self) -> None:
        """Should accept all valid severity values."""
        for severity in VALID_SEVERITIES:
            findings = [
                {
                    "id": "RS001",
                    "severity": severity,
                    "category": "correctness",
                    "title": "Test",
                    "description": "Test description",
                }
            ]
            valid, errors = validate_findings(findings)
            assert len(valid) == 1, f"Failed for severity: {severity}"
            assert errors == []

    def test_accepts_all_valid_categories(self) -> None:
        """Should accept all valid category values."""
        for category in VALID_CATEGORIES:
            findings = [
                {
                    "id": "RT001",
                    "severity": "major",
                    "category": category,
                    "title": "Test",
                    "description": "Test description",
                }
            ]
            valid, errors = validate_findings(findings)
            assert len(valid) == 1, f"Failed for category: {category}"
            assert errors == []


class TestValidateFindingsRejectsMissingFields:
    """Test validate_findings() rejects findings with missing required fields."""

    @pytest.mark.parametrize("missing_field", list(REQUIRED_FIELDS))
    def test_rejects_missing_required_field(self, missing_field: str) -> None:
        """Should reject finding missing a required field."""
        finding = {
            "id": "RS001",
            "severity": "major",
            "category": "correctness",
            "title": "Test issue",
            "description": "Test description",
        }
        del finding[missing_field]

        valid, errors = validate_findings([finding])
        assert len(valid) == 0
        assert len(errors) == 1
        assert f"missing required field '{missing_field}'" in errors[0]

    def test_rejects_empty_required_field(self) -> None:
        """Should reject finding with empty required field."""
        findings = [
            {
                "id": "RS001",
                "severity": "major",
                "category": "correctness",
                "title": "",  # Empty title
                "description": "Test description",
            }
        ]
        valid, errors = validate_findings(findings)
        assert len(valid) == 0
        assert len(errors) == 1
        assert "missing required field 'title'" in errors[0]


class TestValidateFindingsRejectsInvalidValues:
    """Test validate_findings() rejects invalid field values."""

    def test_rejects_invalid_severity(self) -> None:
        """Should reject unknown severity value."""
        findings = [
            {
                "id": "RS001",
                "severity": "extreme",  # Invalid
                "category": "correctness",
                "title": "Test",
                "description": "Test description",
            }
        ]
        valid, errors = validate_findings(findings)
        assert len(valid) == 0
        assert len(errors) == 1
        assert "invalid severity 'extreme'" in errors[0]

    def test_rejects_invalid_category(self) -> None:
        """Should reject unknown category value."""
        findings = [
            {
                "id": "RT001",
                "severity": "major",
                "category": "unknown_category",  # Invalid
                "title": "Test",
                "description": "Test description",
            }
        ]
        valid, errors = validate_findings(findings)
        assert len(valid) == 0
        assert len(errors) == 1
        assert "invalid category 'unknown_category'" in errors[0]

    def test_rejects_negative_line_start(self) -> None:
        """Should reject negative line_start."""
        findings = [
            {
                "id": "RS001",
                "severity": "major",
                "category": "correctness",
                "title": "Test",
                "description": "Test description",
                "line_start": -1,  # Invalid
            }
        ]
        valid, errors = validate_findings(findings)
        assert len(valid) == 0
        assert len(errors) == 1
        assert "invalid line_start '-1'" in errors[0]

    def test_rejects_zero_line_start(self) -> None:
        """Should reject zero line_start (1-indexed)."""
        findings = [
            {
                "id": "RS001",
                "severity": "major",
                "category": "correctness",
                "title": "Test",
                "description": "Test description",
                "line_start": 0,  # Invalid (1-indexed)
            }
        ]
        valid, errors = validate_findings(findings)
        assert len(valid) == 0
        assert len(errors) == 1
        assert "invalid line_start '0'" in errors[0]

    def test_rejects_non_integer_line_end(self) -> None:
        """Should reject non-integer line_end."""
        findings = [
            {
                "id": "RS001",
                "severity": "major",
                "category": "correctness",
                "title": "Test",
                "description": "Test description",
                "line_end": "42",  # String, not int
            }
        ]
        valid, errors = validate_findings(findings)
        assert len(valid) == 0
        assert len(errors) == 1
        assert "invalid line_end" in errors[0]


class TestValidateFindingsMixedResults:
    """Test validate_findings() with mix of valid and invalid findings."""

    def test_filters_invalid_keeps_valid(self) -> None:
        """Should return valid findings and list errors for invalid."""
        findings = [
            {
                "id": "RS001",
                "severity": "major",
                "category": "correctness",
                "title": "Valid finding",
                "description": "This is valid",
            },
            {
                "id": "RS002",
                "severity": "extreme",  # Invalid severity
                "category": "correctness",
                "title": "Invalid finding",
                "description": "This has bad severity",
            },
            {
                "id": "RS003",
                "severity": "minor",
                "category": "style",
                "title": "Another valid",
                "description": "Also valid",
            },
        ]
        valid, errors = validate_findings(findings)
        assert len(valid) == 2
        assert len(errors) == 1
        assert valid[0]["id"] == "RS001"
        assert valid[1]["id"] == "RS003"
        assert "RS002" in errors[0]

    def test_reports_multiple_errors_per_finding(self) -> None:
        """Should report all validation errors for a finding."""
        findings = [
            {
                "id": "RT001",
                "severity": "invalid_severity",
                "category": "invalid_category",
                "title": "Test",
                "description": "Test description",
            }
        ]
        valid, errors = validate_findings(findings)
        assert len(valid) == 0
        assert len(errors) == 1
        # Both errors should be in the same error message
        assert "invalid severity" in errors[0]
        assert "invalid category" in errors[0]
