# Data Model: Typed Agent Output Contracts

**Feature Branch**: `030-typed-output-contracts`
**Date**: 2026-02-21

## Entity Overview

```
┌─────────────────────────────────────────────────────┐
│              maverick.agents.contracts               │
│  (centralized re-export + validate_output utility)   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─── Review Domain ───────────────────────────┐    │
│  │ ReviewFinding        (Pydantic, existing)   │    │
│  │ ReviewResult         (Pydantic, existing)   │    │
│  │ Finding              (Pydantic, converted)  │    │
│  │ FindingGroup         (Pydantic, converted)  │    │
│  │ GroupedReviewResult  (Pydantic, converted)  │    │
│  │ FixOutcome           (Pydantic, converted)  │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─── Fixer Domain ───────────────────────────┐    │
│  │ FixerResult          (Pydantic, NEW)        │    │
│  │ FixResult            (Pydantic, tightened)  │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─── Implementation Domain ──────────────────┐    │
│  │ ImplementationResult (Pydantic, existing)   │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─── Utility ────────────────────────────────┐    │
│  │ validate_output(raw, model) -> model        │    │
│  │ OutputValidationError                       │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─── Deprecated ─────────────────────────────┐    │
│  │ AgentResult          (frozen dc, unchanged) │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

## New Entities

### FixerResult (NEW)

**Location**: `src/maverick/models/fixer.py`
**Used by**: `FixerAgent` (replaces `AgentResult` return)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `bool` | Yes | Whether the fix attempt succeeded |
| `summary` | `str` | Yes | Human-readable description of what was done |
| `files_mentioned` | `list[str]` | Yes | Best-effort list of files the agent mentioned modifying. Not authoritative — workflows use `git diff` for ground truth. |
| `error_details` | `str \| None` | No | Error description if `success=False` |

**Validation Rules**:
- `files_mentioned` defaults to `[]` (empty list)
- `error_details` must be non-empty when `success=False` (validated via `model_validator`)

### OutputValidationError (NEW)

**Location**: `src/maverick/agents/contracts.py`
**Inherits**: `MaverickError`

| Field | Type | Description |
|-------|------|-------------|
| `expected_model` | `str` | Name of the expected Pydantic model class |
| `raw_output` | `str` | The raw text that failed validation (truncated to 500 chars) |
| `parse_error` | `str` | Description of what went wrong |
| `stage` | `Literal["extraction", "json_parse", "validation"]` | Where in the pipeline parsing failed |

## Converted Entities (frozen dataclass -> Pydantic)

### Finding

**Current**: `src/maverick/models/review_models.py:31` (frozen dataclass)
**After**: Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True)`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `str` | Yes | Unique finding identifier (e.g., "F001") |
| `file` | `str` | Yes | File path where issue was found |
| `line` | `str` | Yes | Line number or range |
| `issue` | `str` | Yes | Description of the issue |
| `severity` | `Literal["critical", "major", "minor"]` | Yes | Severity level |
| `category` | `str` | Yes | Finding category |
| `fix_hint` | `str \| None` | No | Suggested fix |

**Migration**: Add `to_dict()` -> `model_dump()` alias. Add `from_dict()` -> `model_validate()` classmethod alias.

### FindingGroup

**Current**: `src/maverick/models/review_models.py:81` (frozen dataclass)
**After**: Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True)`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | `str` | Yes | Group description |
| `findings` | `list[Finding]` | Yes | Findings in this group |

**Note**: `tuple[Finding, ...]` becomes `list[Finding]` for Pydantic/JSON compatibility.

### GroupedReviewResult (renamed from ReviewResult)

**Current**: `src/maverick/models/review_models.py:112` (frozen dataclass named `ReviewResult`)
**After**: Pydantic `BaseModel` named `GroupedReviewResult` with `model_config = ConfigDict(frozen=True)`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `groups` | `list[FindingGroup]` | Yes | Grouped findings |

**Properties preserved**: `all_findings`, `total_count`

### FixOutcome

**Current**: `src/maverick/models/review_models.py:149` (frozen dataclass)
**After**: Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True)`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `str` | Yes | Finding ID this outcome refers to |
| `outcome` | `Literal["fixed", "blocked", "deferred"]` | Yes | Fix outcome |
| `explanation` | `str` | Yes | Why this outcome was chosen |

## Tightened Entities

### FixResult (IssueFixerAgent)

**Location**: `src/maverick/models/issue_fix.py:46`
**Changes**: Mark `output: str` as deprecated via docstring

| Field | Change | Rationale |
|-------|--------|-----------|
| `output` | Add deprecation note in Field description | Callers should use `fix_description` + `files_changed` instead |

## Unchanged Entities (re-exported only)

### ReviewFinding
**Location**: `src/maverick/models/review.py:97` — Already Pydantic. Re-export from contracts.

### ReviewResult
**Location**: `src/maverick/models/review.py:169` — Already Pydantic. Re-export from contracts.

### ImplementationResult
**Location**: `src/maverick/models/implementation.py:539` — Already Pydantic. Re-export from contracts.

### AgentResult
**Location**: `src/maverick/agents/result.py:63` — Frozen dataclass. Stays as-is. Re-export from contracts with deprecation note.

## Utility: validate_output()

**Location**: `src/maverick/agents/contracts.py`

```python
def validate_output(
    raw: str,
    model: type[T],
    *,
    strict: bool = True,
) -> T:
    """Extract and validate JSON from agent output text.

    Pipeline:
    1. Search for ```json ... ``` code block
    2. Extract JSON string from code block
    3. Parse JSON string -> dict
    4. Validate dict against Pydantic model

    Args:
        raw: Raw text output from agent (may contain markdown).
        model: Pydantic BaseModel subclass to validate against.
        strict: If True, raise on failure. If False, return None.

    Returns:
        Validated model instance.

    Raises:
        OutputValidationError: If extraction, parsing, or validation fails
            (only when strict=True).
    """
```

**Extraction Rules** (per spec FR-005):
- Only extract from `` ```json ... ``` `` code blocks
- No raw-text fallback (no regex for JSON embedded in prose)
- No bare JSON detection (no `text.find("{")` heuristic)
- If no code block found -> `OutputValidationError(stage="extraction")`
- If JSON parse fails -> `OutputValidationError(stage="json_parse")`
- If Pydantic validation fails -> `OutputValidationError(stage="validation")`

## State Transitions

```
Agent.execute() produces text output
    │
    ├── [SDK structured output available]
    │   └── ResultMessage.structured_output -> model_validate() -> typed result
    │
    └── [Fallback / legacy path]
        └── validate_output(raw_text, Model)
            ├── extract code block
            ├── json.loads()
            ├── Model.model_validate()
            └── return typed result OR raise OutputValidationError
```

## Relationships

```
FixerAgent ──returns──> FixerResult (NEW)
IssueFixerAgent ──returns──> FixResult (tightened)
ImplementerAgent ──returns──> ImplementationResult (unchanged)
CodeReviewerAgent ──returns──> ReviewResult (unchanged)
UnifiedReviewerAgent ──returns──> GroupedReviewResult (renamed + converted)
SimpleFixerAgent ──returns──> list[FixOutcome] (converted)

contracts module ──re-exports──> all above types
contracts module ──provides──> validate_output() + OutputValidationError
```
