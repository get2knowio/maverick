# Quickstart: Context Builder Utilities

**Feature Branch**: `018-context-builder`
**Module Location**: `src/maverick/utils/context.py`

## Installation

No additional dependencies required - uses Python stdlib and existing Maverick modules.

## Basic Usage

### 1. Build Implementation Context

Prepare context for an implementation agent with task definitions and project conventions:

```python
from pathlib import Path
from maverick.utils.git_operations import GitOperations
from maverick.utils.context import build_implementation_context

# Initialize git operations
git = GitOperations()

# Build context for implementation
context = build_implementation_context(
    task_file=Path("specs/018-context-builder/tasks.md"),
    git=git,
)

# Access context components
print(context['tasks'])         # Raw task file content
print(context['branch'])        # Current branch name
print(context['conventions'])   # CLAUDE.md content
print(context['recent_commits'])  # Last 10 commits

# Check for truncation
if context['_metadata']['truncated']:
    print(f"Truncated sections: {context['_metadata']['sections_affected']}")
```

### 2. Build Review Context

Prepare context for code review with diffs and changed file contents:

```python
from maverick.utils.context import build_review_context

# Get diff against main branch
context = build_review_context(
    git=git,
    base_branch="main",
)

print(context['diff'])            # Full diff output
print(context['stats'])           # {'files_changed': 5, 'insertions': 100, ...}
print(context['changed_files'])   # {path: content} for each changed file
```

### 3. Build Fix Context

Prepare context for fix agents with error locations and surrounding code:

```python
from maverick.utils.context import build_fix_context
from maverick.runners.models import ValidationOutput

# After running validation
validation_result: ValidationOutput = ...

# Build fix context with 10 lines around errors
context = build_fix_context(
    validation_output=validation_result,
    files=[Path("src/maverick/utils/context.py")],
    context_lines=10,
)

print(context['error_summary'])   # "3 errors in 2 files"
print(context['errors'])          # Structured error list
print(context['source_files'])    # Truncated source with context
```

### 4. Build Issue Context

Prepare context for issue-related work with related files:

```python
from maverick.utils.context import build_issue_context
from maverick.runners.models import GitHubIssue

issue = GitHubIssue(
    number=42,
    title="Fix token estimation",
    body="The file src/utils/context.py has incorrect token counting...",
    labels=("bug",),
    state="open",
    assignees=(),
    url="https://github.com/owner/repo/issues/42",
)

context = build_issue_context(
    issue=issue,
    git=git,
)

print(context['issue'])           # Issue details as dict
print(context['related_files'])   # Files referenced in issue body
print(context['recent_changes'])  # Last 5 commits
```

### 5. Token Budget Management

Fit context to a token budget for prompt optimization:

```python
from maverick.utils.context import fit_to_budget, estimate_tokens

# Estimate tokens for some text
tokens = estimate_tokens(context['diff'])
print(f"Diff is approximately {tokens} tokens")

# Fit multiple sections to a budget
sections = {
    'system': "You are a code reviewer...",
    'diff': context['diff'],
    'conventions': context['conventions'],
}

fitted = fit_to_budget(sections, budget=16000)

# Check what was truncated
if '_metadata' in fitted:
    print(f"Truncated: {fitted['_metadata']['sections_affected']}")
```

### 6. File Truncation Utilities

Truncate files while preserving context around specific lines:

```python
from maverick.utils.context import truncate_file

content = Path("large_file.py").read_text()

# Truncate to 100 lines, preserving context around lines 50 and 150
truncated = truncate_file(
    content,
    max_lines=100,
    around_lines=[50, 150],
    context_lines=10,
)

# Result includes "..." markers where content was removed
```

## Integration with Agents

The context builders integrate with Maverick agents via the `extra` field in `AgentContext`:

```python
from maverick.agents.context import AgentContext
from maverick.utils.context import build_implementation_context

# Build context
impl_context = build_implementation_context(task_file, git)

# Create agent context with implementation context in extra
agent_context = AgentContext.from_cwd(
    cwd=Path.cwd(),
    extra={'implementation': impl_context},
)

# Agent can access via context.extra['implementation']['tasks']
```

## Error Handling

All context builders handle errors gracefully:

```python
# Missing task file - returns empty content with metadata
context = build_implementation_context(
    task_file=Path("nonexistent.md"),
    git=git,
)
# context['tasks'] == ""
# context['_metadata']['truncated'] == False

# Binary files in changed_files are skipped
context = build_review_context(git=git, base_branch="main")
# Binary files noted in _metadata but not included in changed_files
```

## Secret Detection

The module logs warnings for potential secrets but includes content as-is:

```python
import logging

# Enable warning logs
logging.basicConfig(level=logging.WARNING)

# Secrets trigger warnings but are included
context = build_implementation_context(task_file, git)
# Log: WARNING - Potential secret detected in CLAUDE.md at line 42: api_key pattern
# Content is still included for agent accuracy
```

## Performance Notes

- All functions are synchronous (file I/O only)
- Memory usage stays under 100MB per operation
- Large files (>50,000 lines) are automatically truncated
- Token estimation uses fast character count / 4 approximation
