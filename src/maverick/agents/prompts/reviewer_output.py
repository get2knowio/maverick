"""Structured output schema for code reviewers.

This module defines the JSON schema that reviewers must use when outputting
their findings, enabling machine-parseable tracking through the fix loop.
"""

from __future__ import annotations

# ruff: noqa: E501
# Line length is intentionally ignored in this prompt string
REVIEWER_OUTPUT_SCHEMA = """
## Output Format

You MUST output your findings in the following JSON format at the END of your response:

```json
{
  "findings": [
    {
      "id": "RS001",
      "severity": "critical|major|minor",
      "category": "security|correctness|performance|maintainability|spec_compliance|style|other",
      "title": "Short title (max 80 chars)",
      "description": "Detailed description of the issue",
      "file_path": "path/to/file.py",
      "line_start": 42,
      "line_end": 45,
      "suggested_fix": "How to fix this issue"
    }
  ],
  "summary": "Brief summary of all findings"
}
```

### Field Requirements:
- **id**: Unique identifier. Use "RS" prefix for spec issues, "RT" for technical issues, followed by 3-digit number
- **severity**:
  - "critical": Security vulnerabilities, data corruption, crashes
  - "major": Bugs, spec violations, significant problems
  - "minor": Style issues, suggestions, minor improvements
- **category**: One of the predefined categories
- **title**: Concise description (required)
- **description**: Detailed explanation (required)
- **file_path**: Relative path from repo root (required if file-specific)
- **line_start**: Starting line number, 1-indexed (required if file-specific)
- **line_end**: Ending line number, can be null for single-line issues
- **suggested_fix**: Recommended fix with code if applicable (optional but recommended)

### Important:
- Output the JSON block AFTER your analysis
- Use valid JSON (no trailing commas, proper quoting)
- If no issues found, return empty findings array: {"findings": [], "summary": "No issues found"}
"""

SPEC_REVIEWER_ID_PREFIX = "RS"
TECH_REVIEWER_ID_PREFIX = "RT"
