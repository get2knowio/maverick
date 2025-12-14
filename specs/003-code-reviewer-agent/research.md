# Research: CodeReviewerAgent

**Branch**: `003-code-reviewer-agent` | **Date**: 2025-12-13

## Overview

This document captures research findings for implementing the CodeReviewerAgent, resolving technical unknowns and documenting best practices for key implementation areas.

---

## 1. Claude Agent SDK Integration Patterns

### Decision: Use ClaudeSDKClient for Stateful Multi-Turn Interactions

**Rationale**: The CodeReviewerAgent may need multiple turns to review large diffs or follow up on specific concerns. ClaudeSDKClient provides session state management and proper async streaming.

**Alternatives Considered**:
- `query()` one-shot function: Rejected because reviews may require context accumulation across turns (e.g., chunked reviews).
- Direct HTTP API calls: Rejected because it bypasses SDK conveniences and violates dependency injection principle.

### System Prompt Structure

The system prompt should include:
1. **Role Definition**: Expert code reviewer specializing in Python
2. **Review Dimensions**: Correctness, security, style/conventions, performance, testability
3. **Output Format**: Explicit JSON schema instruction
4. **Convention Reference**: Instructions to check CLAUDE.md compliance
5. **Severity Guidelines**: Definitions for critical/major/minor/suggestion

```python
system_prompt = """You are an expert code reviewer specializing in Python development.

When reviewing code, evaluate:
1. **Correctness**: Logic errors, edge cases, proper error handling
2. **Security**: Injection vulnerabilities, secrets exposure, unsafe patterns
3. **Style & Conventions**: Adherence to CLAUDE.md conventions
4. **Performance**: Inefficient algorithms, resource leaks
5. **Testability**: Test coverage implications

For each finding, categorize severity:
- CRITICAL: Security vulnerabilities, data loss risks
- MAJOR: Logic errors, incorrect behavior
- MINOR: Style issues, minor inconsistencies
- SUGGESTION: Improvements, best practices

Return structured JSON matching the ReviewResult schema."""
```

### Tool Configuration

Per principle of least privilege (FR-006):
```python
allowed_tools = ["Read", "Glob", "Grep", "Bash"]  # Read-only only
disallowed_tools = ["Write", "Edit"]  # Explicitly deny modifications
```

**Read-only Bash operations** (per spec assumption): `git diff`, `git log`, `git show`, `cat`, `head`, `tail`, `wc`

---

## 2. Structured JSON Output

### Decision: Use Pydantic Models with JSON Schema Output Format

**Rationale**: Pydantic provides validation, serialization, and automatic JSON schema generation. The Agent SDK supports `output_format` with JSON schema for structured responses.

**Alternatives Considered**:
- Manual JSON parsing: Rejected due to validation complexity and error-prone string handling.
- Dataclasses with manual schema: Rejected because Pydantic's `.model_json_schema()` is more robust.

### Implementation Pattern

```python
from pydantic import BaseModel
from enum import Enum

class ReviewSeverity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"

class ReviewFinding(BaseModel):
    severity: ReviewSeverity
    file: str
    line: int | None = None
    message: str
    suggestion: str = ""

class ReviewResult(BaseModel):
    success: bool
    findings: list[ReviewFinding]
    files_reviewed: int
    summary: str
    truncated: bool = False

# Usage with Agent SDK
options = ClaudeAgentOptions(
    output_format={
        "type": "json_schema",
        "schema": ReviewResult.model_json_schema()
    }
)
```

---

## 3. Git Diff Analysis

### Decision: Two-Phase Diff Strategy

**Rationale**: GitHub's engineering team demonstrated 3x performance improvement by separating metadata retrieval from full patch generation.

**Alternatives Considered**:
- Single `git diff` call: Rejected for large diffs due to performance issues.
- GitPython library: Rejected to avoid additional dependency; CLI is sufficient.

### Phase 1: Metadata (Fast)

```bash
git diff origin/main...HEAD --numstat
```

Returns: `added_lines deleted_lines filename` (binary files show as `- -`)

### Phase 2: Selective Content

```bash
git diff origin/main...HEAD --patch -- file1.py file2.py
```

Load full patches only for files to review.

### Python Implementation

```python
import subprocess
from typing import List, Tuple

def get_diff_stats(base: str, feature: str) -> dict:
    """Get diff statistics without full content."""
    result = subprocess.run(
        ["git", "diff", f"{base}...{feature}", "--numstat"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30
    )

    lines = 0
    files = []
    binary_files = []

    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) >= 3:
            added, deleted, filename = parts[0], parts[1], parts[2]
            if added == '-' and deleted == '-':
                binary_files.append(filename)  # Binary file
            else:
                files.append(filename)
                lines += int(added) + int(deleted)

    return {
        "files": files,
        "binary_files": binary_files,
        "total_lines": lines
    }
```

---

## 4. Large Diff Handling (FR-017)

### Decision: Truncate at 2000 Lines or 50 Files

**Rationale**: Spec requirement (FR-017) defines these thresholds. Truncation with notice in summary balances thoroughness with practical limits.

**Alternatives Considered**:
- No truncation: Rejected due to token limits and review quality degradation.
- Automatic chunking only: Rejected because truncation is simpler for the first pass; chunking handles token limits separately.

### Implementation

```python
MAX_DIFF_LINES = 2000
MAX_DIFF_FILES = 50

def should_truncate(stats: dict) -> bool:
    return (len(stats['files']) > MAX_DIFF_FILES or
            stats['total_lines'] > MAX_DIFF_LINES)

def truncate_files(files: List[str], stats: dict) -> Tuple[List[str], str]:
    """Truncate file list and return notice.

    Files are kept in git diff order (alphabetical by path) for deterministic,
    reproducible results.
    """
    if len(files) > MAX_DIFF_FILES:
        truncated = files[:MAX_DIFF_FILES]
        skipped = len(files) - MAX_DIFF_FILES
        notice = f"Truncated: reviewing {MAX_DIFF_FILES} of {len(files)} files ({skipped} skipped)"
        return truncated, notice
    return files, ""
```

---

## 5. Binary File Handling (FR-020)

### Decision: Detect via `--numstat` and Silently Exclude

**Rationale**: Binary files show as `- -` in numstat output. Silent exclusion per spec (no mention in findings).

**Alternatives Considered**:
- File extension detection: Rejected as unreliable (e.g., `.bin` could be text).
- Null byte detection: Rejected as requires file read; numstat is sufficient.

### Detection Pattern

```python
def is_binary_in_numstat(line: str) -> bool:
    """Check if numstat line indicates binary file."""
    parts = line.split('\t')
    if len(parts) >= 3:
        return parts[0] == '-' and parts[1] == '-'
    return False
```

---

## 6. Merge Conflict Detection (FR-018)

### Decision: Pre-Check with `--diff-filter=U`

**Rationale**: Detect unmerged paths before attempting review. Raise AgentError with diagnostic details.

**Alternatives Considered**:
- Simulated merge: Rejected as too invasive; modifies working directory state.
- Parse conflict markers: Rejected as requires full diff read; filter is faster.

### Implementation

```python
def has_merge_conflicts() -> bool:
    """Check for unmerged files in working directory."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        capture_output=True,
        text=True,
        timeout=10
    )
    return bool(result.stdout.strip())
```

**Error Response**:
```python
if has_merge_conflicts():
    raise AgentError(
        "Cannot review: merge conflicts exist. Resolve conflicts before review.",
        error_code="MERGE_CONFLICTS"
    )
```

---

## 7. Token Limit Handling (FR-021)

### Decision: Automatic Chunking with Merged Results

**Rationale**: When reviews approach token limits, split remaining files into chunks, review each separately, and merge findings.

**Alternatives Considered**:
- Fail on token limit: Rejected as violates fail-gracefully principle.
- Truncate and skip: Rejected as loses review coverage.

### Chunking Strategy

```python
MAX_TOKENS_PER_CHUNK = 50_000  # Conservative estimate

def chunk_files_for_review(files: List[str], diff_content: str) -> List[List[str]]:
    """Split files into chunks respecting token budget."""
    chunks = []
    current_chunk = []
    current_tokens = 0

    for file in files:
        # Estimate tokens (rough: 1 token ~ 4 chars)
        file_content = extract_file_diff(diff_content, file)
        file_tokens = len(file_content) // 4

        if current_tokens + file_tokens > MAX_TOKENS_PER_CHUNK:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = [file]
            current_tokens = file_tokens
        else:
            current_chunk.append(file)
            current_tokens += file_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
```

### Merging Results

```python
async def review_with_chunking(self, context: ReviewContext) -> ReviewResult:
    """Review with automatic chunking for large diffs."""
    all_findings = []
    total_files = 0

    for chunk in chunks:
        chunk_result = await self._review_chunk(chunk, context)
        all_findings.extend(chunk_result.findings)
        total_files += chunk_result.files_reviewed

    return ReviewResult(
        success=True,
        findings=all_findings,
        files_reviewed=total_files,
        summary=f"Reviewed {total_files} files across {len(chunks)} chunks"
    )
```

---

## 8. Error Handling Patterns

### Decision: Wrap All Errors in AgentError with Diagnostics

**Rationale**: Per constitution principle IV (Fail Gracefully), errors must be captured with context and returned in structured format.

### Error Categories

| Error Type | AgentError Code | Handling |
|------------|-----------------|----------|
| Invalid branch | `INVALID_BRANCH` | Include branch name in message |
| Git command failure | `GIT_ERROR` | Include stderr output |
| Merge conflicts | `MERGE_CONFLICTS` | List conflicted files |
| Timeout | `TIMEOUT` | Include timeout value |
| No changes | N/A (not an error) | Return empty ReviewResult |

### Implementation

```python
try:
    result = subprocess.run(
        ["git", "diff", f"{base}...{feature}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30
    )
except subprocess.CalledProcessError as e:
    raise AgentError(
        f"Git diff failed: {e.stderr or e.stdout}",
        error_code="GIT_ERROR"
    )
except subprocess.TimeoutExpired:
    raise AgentError(
        f"Git operation timed out after 30s",
        error_code="TIMEOUT"
    )
```

---

## 9. Async Execution Pattern

### Decision: Use asyncio.gather for Parallel Setup

**Rationale**: Per constitution principle I (Async-First), all I/O must be async. Parallel setup for diff and conventions improves performance.

### Implementation

```python
async def execute(self, context: ReviewContext) -> ReviewResult:
    """Execute review with async patterns."""

    # Parallel setup
    diff_task = asyncio.create_task(self._get_diff(context))
    conventions_task = asyncio.create_task(self._read_conventions())

    diff, conventions = await asyncio.gather(diff_task, conventions_task)

    # Handle empty diff (FR-019)
    if not diff.strip():
        return ReviewResult(
            success=True,
            findings=[],
            files_reviewed=0,
            summary="No changes to review"
        )

    # Perform review
    return await self._perform_review(diff, conventions, context)
```

---

## Summary

All technical unknowns have been resolved:

| Area | Decision | Spec Reference |
|------|----------|----------------|
| SDK Integration | ClaudeSDKClient for stateful sessions | FR-001, FR-007 |
| Structured Output | Pydantic with JSON schema | FR-010, FR-011, FR-016 |
| Git Diff | Two-phase (metadata + selective content) | FR-008 |
| Large Diffs | Truncate at 2000 lines / 50 files | FR-017 |
| Binary Files | Detect via numstat, silently exclude | FR-020 |
| Merge Conflicts | Pre-check with diff-filter=U | FR-018 |
| Token Limits | Automatic chunking with merged results | FR-021 |
| Error Handling | AgentError with diagnostic codes | FR-018 |
| Async Pattern | asyncio.gather for parallel setup | Constitution I |
