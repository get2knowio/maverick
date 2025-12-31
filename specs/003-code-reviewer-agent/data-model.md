# Data Model: CodeReviewerAgent

**Branch**: `003-code-reviewer-agent` | **Date**: 2025-12-13

## Overview

This document defines the data models for the CodeReviewerAgent feature. All models use Pydantic for validation and serialization, following constitution principle VI (Type Safety).

---

## Entity Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CodeReviewerAgent                            │
│  (Concrete agent extending MaverickAgent)                           │
├─────────────────────────────────────────────────────────────────────┤
│  + name: str = "code-reviewer"                                      │
│  + system_prompt: str                                               │
│  + allowed_tools: list[str] = ["Read", "Glob", "Grep", "Bash"]     │
│  + max_diff_lines: int = 2000                                       │
│  + max_diff_files: int = 50                                         │
├─────────────────────────────────────────────────────────────────────┤
│  + execute(context: ReviewContext) -> ReviewResult                  │
│  - _get_diff(context) -> str                                        │
│  - _read_conventions() -> str | None                                │
│  - _build_system_prompt(conventions: str | None) -> str             │
│  - _parse_findings(response: AssistantMessage) -> list[ReviewFinding]│
│  - _chunk_files(files: list[str], tokens: int) -> list[list[str]]   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ uses
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ReviewContext                               │
│  (Input context for code review execution)                          │
├─────────────────────────────────────────────────────────────────────┤
│  + branch: str              # Feature branch to review              │
│  + base_branch: str = "main" # Base branch for comparison           │
│  + file_list: list[str] | None = None  # Optional file filter       │
│  + cwd: Path = Path.cwd()   # Working directory                     │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ produces
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ReviewResult                                │
│  (Output from code review, extends AgentResult)                     │
├─────────────────────────────────────────────────────────────────────┤
│  + success: bool            # Whether review completed              │
│  + findings: list[ReviewFinding]  # List of issues found            │
│  + files_reviewed: int      # Count of files analyzed               │
│  + summary: str             # Human-readable summary                │
│  + truncated: bool = False  # Whether diff was truncated            │
│  + output: str = ""         # Raw output (from AgentResult)         │
│  + metadata: dict = {}      # Additional metadata                   │
│  + errors: list[str] = []   # Any non-fatal errors                  │
│  + usage: UsageStats | None # Token/cost tracking                   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ contains
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        ReviewFinding                                │
│  (Single issue identified during review)                            │
├─────────────────────────────────────────────────────────────────────┤
│  + severity: ReviewSeverity # CRITICAL, MAJOR, MINOR, SUGGESTION    │
│  + file: str                # File path relative to repo root       │
│  + line: int | None = None  # Line number (if applicable)           │
│  + message: str             # Description of the issue              │
│  + suggestion: str = ""     # Recommended fix with code example     │
│  + convention_ref: str | None = None  # CLAUDE.md section violated  │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ uses
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       ReviewSeverity                                │
│  (Enum for finding severity levels)                                 │
├─────────────────────────────────────────────────────────────────────┤
│  CRITICAL = "critical"  # Security vulnerabilities, data loss       │
│  MAJOR = "major"        # Logic errors, incorrect behavior          │
│  MINOR = "minor"        # Style issues, minor inconsistencies       │
│  SUGGESTION = "suggestion"  # Improvements, best practices          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Model Definitions

### ReviewSeverity (Enum)

**Purpose**: Categorize findings by severity level for prioritization.

**Reference**: FR-013

```python
from enum import Enum

class ReviewSeverity(str, Enum):
    """Severity levels for code review findings."""

    CRITICAL = "critical"
    """Security vulnerabilities, potential data loss, system crashes."""

    MAJOR = "major"
    """Logic errors, incorrect behavior, breaking changes."""

    MINOR = "minor"
    """Style inconsistencies, minor code smells, formatting."""

    SUGGESTION = "suggestion"
    """Potential improvements, best practices, optimizations."""
```

**Severity Guidelines**:

| Severity | Examples | Action Required |
|----------|----------|-----------------|
| CRITICAL | SQL injection, hardcoded secrets, auth bypass | Must fix before merge |
| MAJOR | Off-by-one errors, null pointer, incorrect return | Should fix before merge |
| MINOR | Naming conventions, missing docstring, import order | Fix if time permits |
| SUGGESTION | Performance optimization, alternative approach | Consider for future |

---

### ReviewFinding (Value Object)

**Purpose**: Represent a single issue identified during code review.

**Reference**: FR-011

```python
from pydantic import BaseModel, Field

class ReviewFinding(BaseModel):
    """A single finding from code review.

    Attributes:
        severity: Categorization of issue importance.
        file: File path relative to repository root.
        line: Line number where issue occurs (None if file-level).
        message: Human-readable description of the issue.
        suggestion: Recommended fix, ideally with code example.
        convention_ref: Reference to CLAUDE.md section if convention violation.
    """

    severity: ReviewSeverity = Field(
        description="Severity level: critical, major, minor, or suggestion"
    )
    file: str = Field(
        description="File path relative to repository root",
        examples=["src/maverick/agents/code_reviewer.py"]
    )
    line: int | None = Field(
        default=None,
        description="Line number (1-indexed) or None for file-level findings",
        ge=1
    )
    message: str = Field(
        description="Clear description of the issue found",
        min_length=10
    )
    suggestion: str = Field(
        default="",
        description="Actionable fix recommendation with code example if applicable"
    )
    convention_ref: str | None = Field(
        default=None,
        description="Reference to violated convention in CLAUDE.md",
        examples=["Code Style > Naming", "Core Principles > Async-First"]
    )

    class Config:
        frozen = True  # Immutable value object
        json_schema_extra = {
            "examples": [
                {
                    "severity": "critical",
                    "file": "src/api/auth.py",
                    "line": 42,
                    "message": "SQL query uses string interpolation, vulnerable to injection",
                    "suggestion": "Use parameterized queries: cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
                    "convention_ref": None
                },
                {
                    "severity": "minor",
                    "file": "src/utils/helpers.py",
                    "line": 15,
                    "message": "Function name 'getData' uses camelCase instead of snake_case",
                    "suggestion": "Rename to 'get_data' per Python conventions",
                    "convention_ref": "Code Style > Naming"
                }
            ]
        }
```

---

### ReviewResult (Value Object)

**Purpose**: Aggregate result from code review execution, extending AgentResult.

**Reference**: FR-012

```python
from pydantic import BaseModel, Field
from typing import Any

class ReviewResult(BaseModel):
    """Result of a code review execution.

    Extends AgentResult with review-specific fields for findings,
    file counts, and summary information.

    Attributes:
        success: Whether the review completed without errors.
        findings: List of issues identified during review.
        files_reviewed: Number of files analyzed.
        summary: Human-readable summary of review outcome.
        truncated: Whether the diff was truncated due to size limits.
        output: Raw output from the review (for debugging).
        metadata: Additional context (e.g., branch names, timestamps).
        errors: List of non-fatal errors encountered.
        usage: Token and cost statistics.
    """

    success: bool = Field(
        description="True if review completed, False if failed"
    )
    findings: list[ReviewFinding] = Field(
        default_factory=list,
        description="List of issues found during review"
    )
    files_reviewed: int = Field(
        ge=0,
        description="Number of files analyzed (excludes binary files)"
    )
    summary: str = Field(
        description="Human-readable summary of review outcome",
        examples=["Reviewed 15 files, found 3 issues (1 critical, 2 minor)"]
    )
    truncated: bool = Field(
        default=False,
        description="True if diff exceeded size limits and was truncated"
    )
    output: str = Field(
        default="",
        description="Raw agent output for debugging"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (branch, timestamp, etc.)"
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Non-fatal errors encountered during review"
    )
    usage: "UsageStats | None" = Field(
        default=None,
        description="Token usage and cost statistics"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "success": True,
                    "findings": [],
                    "files_reviewed": 0,
                    "summary": "No changes to review",
                    "truncated": False
                },
                {
                    "success": True,
                    "findings": [
                        {
                            "severity": "major",
                            "file": "src/api/handlers.py",
                            "line": 87,
                            "message": "Missing error handling for database connection failure",
                            "suggestion": "Wrap in try/except and return appropriate HTTP 500 response"
                        }
                    ],
                    "files_reviewed": 12,
                    "summary": "Reviewed 12 files, found 1 major issue",
                    "truncated": False
                }
            ]
        }

    @property
    def has_critical_findings(self) -> bool:
        """Check if any findings are critical severity."""
        return any(f.severity == ReviewSeverity.CRITICAL for f in self.findings)

    @property
    def findings_by_severity(self) -> dict[ReviewSeverity, list[ReviewFinding]]:
        """Group findings by severity level."""
        result: dict[ReviewSeverity, list[ReviewFinding]] = {
            s: [] for s in ReviewSeverity
        }
        for finding in self.findings:
            result[finding.severity].append(finding)
        return result

    @property
    def findings_by_file(self) -> dict[str, list[ReviewFinding]]:
        """Group findings by file path."""
        result: dict[str, list[ReviewFinding]] = {}
        for finding in self.findings:
            if finding.file not in result:
                result[finding.file] = []
            result[finding.file].append(finding)
        return result
```

---

### ReviewContext (Value Object)

**Purpose**: Input context for code review execution.

**Reference**: FR-007, FR-014

```python
from pathlib import Path
from pydantic import BaseModel, Field

class ReviewContext(BaseModel):
    """Context for code review execution.

    Provides all inputs needed for the CodeReviewerAgent to perform
    a review, including branch information and optional file filters.

    Attributes:
        branch: Feature branch name to review.
        base_branch: Base branch for comparison (default: main).
        file_list: Optional list of specific files to review.
        cwd: Working directory for git operations.
    """

    branch: str = Field(
        description="Feature branch name to review",
        examples=["feature/add-auth", "bugfix/fix-login"]
    )
    base_branch: str = Field(
        default="main",
        description="Base branch for diff comparison",
        examples=["main", "develop", "origin/main"]
    )
    file_list: list[str] | None = Field(
        default=None,
        description="Optional list of specific files to review (None = all changed files)",
        examples=[["src/api/auth.py", "tests/test_auth.py"]]
    )
    cwd: Path = Field(
        default_factory=Path.cwd,
        description="Working directory for git operations"
    )

    class Config:
        arbitrary_types_allowed = True  # For Path
```

---

### UsageStats (Value Object)

**Purpose**: Track token usage and cost for monitoring.

**Reference**: FR-012 (from base AgentResult)

```python
from pydantic import BaseModel, Field

class UsageStats(BaseModel):
    """Usage statistics for agent execution.

    Attributes:
        input_tokens: Number of tokens in input/prompt.
        output_tokens: Number of tokens in response.
        total_cost: Estimated cost in USD (if available).
        duration_ms: Execution time in milliseconds.
    """

    input_tokens: int = Field(ge=0, description="Tokens in prompt")
    output_tokens: int = Field(ge=0, description="Tokens in response")
    total_cost: float | None = Field(
        default=None,
        ge=0,
        description="Estimated cost in USD"
    )
    duration_ms: int = Field(ge=0, description="Execution time in milliseconds")

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.input_tokens + self.output_tokens
```

---

## Validation Rules

### ReviewFinding

| Field | Rule | Error |
|-------|------|-------|
| severity | Must be valid ReviewSeverity | Invalid severity value |
| file | Non-empty string | File path required |
| line | >= 1 if provided | Line number must be positive |
| message | >= 10 characters | Message too short |

### ReviewResult

| Field | Rule | Error |
|-------|------|-------|
| files_reviewed | >= 0 | Cannot be negative |
| findings | All valid ReviewFinding | Invalid finding in list |

### ReviewContext

| Field | Rule | Error |
|-------|------|-------|
| branch | Non-empty string | Branch name required |
| base_branch | Non-empty string | Base branch required |
| cwd | Valid directory path | Invalid working directory |

---

## State Transitions

The CodeReviewerAgent has no persistent state. Each `execute()` call is stateless:

```
ReviewContext ──► execute() ──► ReviewResult
```

**Internal States During Execution**:

1. **Initializing**: Validating context, checking prerequisites
2. **Fetching Diff**: Running git diff command
3. **Reading Conventions**: Loading CLAUDE.md (optional)
4. **Reviewing**: Claude analyzing diff with conventions
5. **Parsing**: Extracting findings from response
6. **Completed**: Returning ReviewResult

---

## Serialization

All models serialize to JSON via Pydantic:

```python
# Serialize to JSON
result_json = review_result.model_dump_json()

# Deserialize from JSON
result = ReviewResult.model_validate_json(result_json)

# Get JSON Schema for Agent SDK
schema = ReviewResult.model_json_schema()
```

---

## File Location

```
src/maverick/models/
├── __init__.py          # Exports all models
└── review.py            # ReviewSeverity, ReviewFinding, ReviewResult, ReviewContext, UsageStats
```
