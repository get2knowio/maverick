# Research: Context Builder Utilities

**Feature Branch**: `018-context-builder`
**Research Date**: 2025-12-18
**Status**: Complete

## Research Tasks

Based on the Technical Context unknowns, the following areas were researched:

### 1. Token Estimation Approach

**Decision**: Use character count divided by 4 (`len(text) // 4`) as the token estimation method.

**Rationale**:
- Spec FR-006 explicitly requires "characters divided by 4" approach
- SC-003 requires accuracy within 20% of actual token count for source code
- No external dependencies required (keeping with constitution principle VII - Simplicity)
- Consistent with industry approximations for code content

**Alternatives Considered**:
- **tiktoken library**: Provides exact token counts but adds external dependency and slows processing
- **Word-based estimation**: Less accurate for code which has unusual tokenization patterns
- **Hybrid approach**: Could improve accuracy but violates simplicity principle

**Validation**: The 4-character approximation works well for code because:
- Average token length in code is ~4 characters (keywords, operators, identifiers)
- Whitespace and punctuation are typically single tokens
- Accuracy within 20% is acceptable for budget management purposes

---

### 2. Secret Detection Patterns

**Decision**: Use regex-based detection with common secret patterns, logging warnings only.

**Rationale**:
- Spec FR-015 requires logging warnings for suspected secrets but including content as-is
- No blocking or redaction needed - this is informational only
- Patterns should have high precision (few false positives) over high recall

**Patterns to Implement**:
```python
SECRET_PATTERNS = [
    # API keys with common prefixes
    r'(?:api[_-]?key|apikey)\s*[:=]\s*[\'"]?[\w-]{20,}',
    # Bearer/Auth tokens
    r'(?:bearer|authorization)\s*[:=]\s*[\'"]?[\w.-]+',
    # AWS-style keys
    r'(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}',
    # Generic secret/password patterns
    r'(?:secret|password|passwd|pwd)\s*[:=]\s*[\'"]?[^\s\'"]{8,}',
    # Private keys
    r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----',
]
```

**Alternatives Considered**:
- **detect-secrets library**: Full-featured but heavyweight dependency
- **Entropy-based detection**: High false positive rate for code content
- **gitleaks/trufflehog**: External tools, not embeddable

---

### 3. File Truncation with Context Preservation

**Decision**: Implement sliding window approach with configurable context lines.

**Rationale**:
- Spec FR-005 requires `truncate_file(content, max_lines, around_lines)`
- FR-013 specifies 10 lines of context around error line numbers
- Memory efficiency is critical (SC-007: <100MB per operation)

**Algorithm**:
```
1. If file fits within max_lines, return unchanged
2. For around_lines (target line numbers):
   - Mark windows of ±context_lines around each target
   - Merge overlapping windows
3. Extract marked regions with "..." separators
4. Return truncated content with truncation metadata
```

**Line Length Handling** (from edge cases):
- Lines > 2000 chars are truncated to 2000 chars + "..."
- Applied before line counting to avoid memory issues

**Alternatives Considered**:
- **mmap-based processing**: Overkill for typical file sizes
- **Streaming approach**: Unnecessary complexity for synchronous use case
- **Fixed head/tail only**: Loses context around specific line numbers

---

### 4. Proportional Budget Allocation

**Decision**: Allocate tokens proportionally based on section size, with minimum guarantees.

**Rationale**:
- Spec FR-007 requires proportional truncation to fit budget
- SC-002 requires staying within 5% of specified budget
- Larger sections should get proportionally more space

**Algorithm**:
```
1. Estimate tokens for each section
2. If total <= budget, return unchanged
3. Calculate proportional allocation: section_budget = budget * (section_tokens / total_tokens)
4. Ensure minimum allocation (e.g., 100 tokens) for each section
5. Truncate sections to their budgets
6. Record truncation in _metadata
```

**Alternatives Considered**:
- **Priority-based allocation**: Requires explicit priority ranking
- **Fixed allocation per section**: Unfair to smaller sections
- **Iterative reduction**: More complex, marginal benefit

---

### 5. Memory Management for Large Files

**Decision**: Process files line-by-line, avoid loading full content for very large files.

**Rationale**:
- SC-007 requires <100MB memory per operation
- Typical file content fits in memory; only need streaming for edge cases
- 50,000 lines × 200 chars/line = ~10MB, well under limit

**Implementation**:
```python
def read_file_safely(path: Path, max_lines: int = 50000) -> tuple[str, bool]:
    """Read file with line limit.

    Returns:
        Tuple of (content, was_truncated)
    """
    lines = []
    with path.open() as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                return '\n'.join(lines), True
            lines.append(line.rstrip('\n'))
    return '\n'.join(lines), False
```

**Alternatives Considered**:
- **mmap**: Adds complexity, not needed for typical sizes
- **Full file read with size check**: Simple but risks OOM for edge cases

---

### 6. Integration with Existing Types

**Decision**: Accept existing types directly, return plain dicts as specified.

**Rationale**:
- FR-008/FR-009 require synchronous functions returning plain dicts
- Existing types are well-defined in codebase:
  - `GitOperations` from `maverick.utils.git_operations`
  - `ValidationOutput` from `maverick.runners.models`
  - `GitHubIssue` from `maverick.runners.models`

**Type Hints**:
```python
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maverick.utils.git_operations import GitOperations
    from maverick.runners.models import ValidationOutput, GitHubIssue

ContextDict = dict[str, Any]  # Plain dict with _metadata key
```

---

## Dependencies Summary

| Dependency | Type | Purpose |
|------------|------|---------|
| pathlib | stdlib | Path handling |
| logging | stdlib | Warning log for secrets |
| re | stdlib | Secret pattern matching |
| GitOperations | internal | Git branch, commits, diffs |
| ValidationOutput | internal | Error information |
| GitHubIssue | internal | Issue context |

No new external dependencies required.

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Token estimation inaccuracy | 20% tolerance allowed by SC-003 |
| False positive secrets | Warning only, content not blocked |
| Large file memory pressure | Line limits with early exit |
| Missing file handling | Return empty content + metadata |

---

## Open Questions Resolved

All NEEDS CLARIFICATION items from spec have been addressed:

1. **Q: Token estimation method?** → Character count / 4 (FR-006)
2. **Q: Secret handling?** → Log warning, include as-is (FR-015)
3. **Q: Memory budget?** → 100MB max per operation (SC-007)
4. **Q: Default token budget?** → 32,000 tokens (FR-007)
5. **Q: Recent commits count?** → 10 commits (FR-001)
