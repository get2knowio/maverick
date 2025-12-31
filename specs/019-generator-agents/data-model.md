# Data Model: Generator Agents

**Branch**: `019-generator-agents` | **Date**: 2025-12-18

## Entity Definitions

### GeneratorAgent (Base Class)

Abstract base class for all text generation agents.

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `name` | `str` | Unique identifier for the generator | Non-empty, immutable |
| `system_prompt` | `str` | Prompt defining output format and behavior | Non-empty, immutable |
| `model` | `str` | Claude model ID | Default: `claude-sonnet-4-5-20250929` |
| `_options` | `ClaudeAgentOptions` | Cached SDK options | Private, built from fields |

**Methods**:
- `async generate(context: dict[str, Any]) -> str`: Abstract method for text generation
- `_build_prompt(context: dict[str, Any]) -> str`: Build user prompt from context
- `_truncate_input(content: str, max_size: int, name: str) -> str`: Truncate with warning

**Invariants**:
- `system_prompt` must define expected output format
- `allowed_tools` is always empty (no tools for generators)
- `max_turns` is always 1 (single-shot generation)

---

### CommitMessageGenerator

Generates conventional commit messages from git diffs.

**Input Context**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `diff` | `str` | Yes | Git diff output |
| `file_stats` | `dict[str, int]` | Yes | File statistics (insertions, deletions) |
| `scope_hint` | `str \| None` | No | Optional scope override |

**Output**: `str` - Conventional commit message (e.g., `feat(auth): add password reset`)

**Validation Rules**:
- `diff` must be non-empty or error returned
- `diff` truncated to 100KB if exceeded
- Output must match pattern: `^(type)(scope)?:\s.+$`

**System Prompt Guidelines**:
```
You generate conventional commit messages.
Format: type(scope): description
Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
- Use imperative mood ("add" not "added")
- Keep under 72 characters
- No period at end
```

---

### PRDescriptionGenerator

Generates markdown PR descriptions from commit history and validation results.

**Input Context**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `commits` | `list[dict[str, str]]` | Yes | Commit list with hash, message, author |
| `diff_stats` | `dict[str, int]` | Yes | Overall diff statistics |
| `task_summary` | `str` | Yes | Description of the feature/task |
| `validation_results` | `dict[str, Any]` | Yes | Test/lint/build results |
| `sections` | `list[str] \| None` | No | Custom sections (default: Summary, Changes, Testing) |

**Output**: `str` - Markdown PR description

**Validation Rules**:
- `commits` must be non-empty
- `task_summary` must be non-empty
- Output must contain all requested sections as markdown headers

**Default Sections**:
1. **Summary**: Brief overview incorporating task_summary
2. **Changes**: Bulleted list of modifications
3. **Testing**: Validation status (pass/fail with details)

---

### CodeAnalyzer

Generates code analysis based on requested type.

**Input Context**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | `str` | Yes | Code snippet to analyze |
| `analysis_type` | `Literal["explain", "review", "summarize"]` | Yes | Type of analysis |
| `language` | `str \| None` | No | Programming language hint |

**Output**: `str` - Analysis text appropriate to requested type

**Validation Rules**:
- `code` must be non-empty
- `code` truncated to 10KB if exceeded
- `analysis_type` must be one of: explain, review, summarize
- Invalid `analysis_type` defaults to "explain"

**Analysis Type Behaviors**:

| Type | Output Description |
|------|-------------------|
| `explain` | Plain-English explanation of what the code does |
| `review` | Potential issues, improvements, best practice observations |
| `summarize` | Brief summary of purpose, structure, key functions |

---

### ErrorExplainer

Generates human-readable error explanations with fix suggestions.

**Input Context**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `error_output` | `str` | Yes | Raw error message/traceback |
| `source_context` | `str \| None` | No | Relevant source code |
| `error_type` | `Literal["lint", "test", "build", "type"] \| None` | No | Error category hint |

**Output**: `str` - Plain-English explanation with fix suggestions

**Validation Rules**:
- `error_output` must be non-empty
- `source_context` truncated to 10KB if provided
- Output should include: what went wrong, why, how to fix

**Output Structure**:
```
**What happened**: {plain English description}

**Why this occurred**: {root cause explanation}

**How to fix**: {actionable steps}

**Code example** (if applicable):
{corrected code snippet}
```

---

## Supporting Types

### GeneratorError

Custom exception for generator failures.

| Field | Type | Description |
|-------|------|-------------|
| `message` | `str` | Human-readable error message |
| `generator_name` | `str \| None` | Name of failing generator |
| `input_context` | `dict[str, Any] \| None` | Context that caused failure |

**Inheritance**: `AgentError` → `MaverickError`

---

### InputTruncationWarning

Dataclass for tracking input truncation.

| Field | Type | Description |
|-------|------|-------------|
| `field` | `str` | Name of truncated field |
| `original_size` | `int` | Original size in bytes |
| `truncated_size` | `int` | Size after truncation |

---

## Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `MAX_DIFF_SIZE` | `102400` (100KB) | Maximum diff size before truncation |
| `MAX_SNIPPET_SIZE` | `10240` (10KB) | Maximum code snippet size before truncation |
| `DEFAULT_MODEL` | `claude-sonnet-4-5-20250929` | Default Claude model |
| `MAX_TURNS` | `1` | Fixed single-turn for generators |
| `DEFAULT_PR_SECTIONS` | `["Summary", "Changes", "Testing"]` | Default PR sections |

---

## Relationships

```
GeneratorAgent (ABC)
├── CommitMessageGenerator
├── PRDescriptionGenerator
├── CodeAnalyzer
└── ErrorExplainer

AgentError
└── GeneratorError

Context Builders (018) ──provides──> Generator Input Contexts
Generators ──output──> Workflow Consumers (fly, refuel)
```

## State Transitions

Generators are stateless - no state transitions. Each `generate()` call is independent.

## Type Definitions (Python)

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# Analysis type literal
AnalysisType = Literal["explain", "review", "summarize"]

# Error type literal
ErrorType = Literal["lint", "test", "build", "type"]

# Context type aliases
CommitMessageContext = dict[str, Any]  # diff, file_stats, scope_hint?
PRDescriptionContext = dict[str, Any]  # commits, diff_stats, task_summary, validation_results, sections?
CodeAnalysisContext = dict[str, Any]   # code, analysis_type, language?
ErrorExplainerContext = dict[str, Any] # error_output, source_context?, error_type?

@dataclass(frozen=True, slots=True)
class InputTruncationWarning:
    """Warning for truncated input."""
    field: str
    original_size: int
    truncated_size: int
```
