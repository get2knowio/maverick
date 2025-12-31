# Quickstart: CodeReviewerAgent

**Branch**: `003-code-reviewer-agent` | **Date**: 2025-12-13

## Overview

The CodeReviewerAgent performs automated code reviews on git branches, analyzing diffs for correctness, security, style, and convention compliance. It returns structured findings categorized by severity.

---

## Prerequisites

1. **Python 3.10+** with virtual environment
2. **Claude Agent SDK** installed (`pip install claude-agent-sdk`)
3. **Git** installed and repository initialized
4. **CLAUDE.md** at repository root (optional, for convention checking)

---

## Installation

```bash
# From repository root
pip install -e .

# Or install dependencies directly
pip install claude-agent-sdk pydantic
```

---

## Basic Usage

### Simple Review

```python
import asyncio
from maverick.agents.code_reviewer import CodeReviewerAgent
from maverick.models.review import ReviewContext

async def main():
    # Create agent
    agent = CodeReviewerAgent()

    # Define review context
    context = ReviewContext(
        branch="feature/add-auth",
        base_branch="main"
    )

    # Execute review
    result = await agent.execute(context)

    # Process results
    print(f"Reviewed {result.files_reviewed} files")
    print(f"Found {len(result.findings)} issues")

    for finding in result.findings:
        print(f"[{finding.severity.value}] {finding.file}:{finding.line}")
        print(f"  {finding.message}")
        if finding.suggestion:
            print(f"  Fix: {finding.suggestion}")

asyncio.run(main())
```

### Review Specific Files

```python
context = ReviewContext(
    branch="feature/add-auth",
    base_branch="main",
    file_list=["src/api/auth.py", "src/api/handlers.py"]
)

result = await agent.execute(context)
```

### Check for Critical Issues

```python
result = await agent.execute(context)

if result.has_critical_findings:
    print("CRITICAL ISSUES FOUND - Review required before merge")
    for finding in result.findings_by_severity[ReviewSeverity.CRITICAL]:
        print(f"  - {finding.file}:{finding.line}: {finding.message}")
```

---

## Integration with Workflows

### In FlyWorkflow

```python
from maverick.agents.code_reviewer import CodeReviewerAgent
from maverick.models.review import ReviewContext

class FlyWorkflow:
    async def run_code_review(self, branch: str) -> ReviewResult:
        """Run code review as part of workflow."""
        agent = CodeReviewerAgent()
        context = ReviewContext(branch=branch, base_branch="origin/main")

        try:
            result = await agent.execute(context)

            if result.has_critical_findings:
                # Block merge for critical issues
                raise WorkflowError("Critical issues must be resolved")

            return result

        except AgentError as e:
            # Handle review failures gracefully
            self.log_error(f"Review failed: {e}")
            raise
```

### Parallel Review with Other Agents

```python
import asyncio

async def run_parallel_reviews(branch: str):
    """Run code review in parallel with other agents."""
    code_reviewer = CodeReviewerAgent()
    # architecture_reviewer = ArchitectureReviewerAgent()

    context = ReviewContext(branch=branch)

    # Execute reviews in parallel
    results = await asyncio.gather(
        code_reviewer.execute(context),
        # architecture_reviewer.execute(context),
        return_exceptions=True
    )

    # Process results
    code_result = results[0]
    if isinstance(code_result, Exception):
        print(f"Code review failed: {code_result}")
    else:
        print(f"Code review: {len(code_result.findings)} findings")
```

---

## Output Format

### ReviewResult Structure

```python
ReviewResult(
    success=True,
    findings=[
        ReviewFinding(
            severity=ReviewSeverity.MAJOR,
            file="src/api/auth.py",
            line=42,
            message="Missing error handling for failed authentication",
            suggestion="Wrap in try/except and return 401 response",
            convention_ref=None
        ),
        ReviewFinding(
            severity=ReviewSeverity.MINOR,
            file="src/utils/helpers.py",
            line=15,
            message="Function uses camelCase instead of snake_case",
            suggestion="Rename getData to get_data",
            convention_ref="Code Style > Naming"
        )
    ],
    files_reviewed=12,
    summary="Reviewed 12 files, found 2 issues (1 major, 1 minor)",
    truncated=False
)
```

### JSON Serialization

```python
# Serialize to JSON
json_str = result.model_dump_json(indent=2)

# Deserialize from JSON
result = ReviewResult.model_validate_json(json_str)
```

---

## Error Handling

### Common Errors

```python
from maverick.exceptions import AgentError

try:
    result = await agent.execute(context)
except AgentError as e:
    match e.error_code:
        case "INVALID_BRANCH":
            print(f"Branch '{context.branch}' not found")
        case "MERGE_CONFLICTS":
            print("Resolve merge conflicts before review")
        case "GIT_ERROR":
            print(f"Git operation failed: {e}")
        case "TIMEOUT":
            print("Review timed out - try reducing scope")
        case _:
            print(f"Review failed: {e}")
```

### Edge Cases

```python
# No changes to review
if result.files_reviewed == 0:
    print(result.summary)  # "No changes to review"

# Truncated large diff
if result.truncated:
    print(f"Warning: {result.summary}")  # Includes truncation notice

# Non-fatal errors during review
if result.errors:
    for error in result.errors:
        print(f"Warning: {error}")
```

---

## Configuration

### Default Values

```python
# In CodeReviewerAgent
MAX_DIFF_LINES = 2000      # Truncate diffs larger than this
MAX_DIFF_FILES = 50        # Truncate if more files than this
DEFAULT_BASE_BRANCH = "main"
```

### Custom Configuration (Future)

```python
# When MaverickConfig is implemented
config = MaverickConfig(
    max_diff_lines=3000,
    max_diff_files=100,
    timeout_seconds=180
)

agent = CodeReviewerAgent(config=config)
```

---

## Testing

### Unit Test Example

```python
import pytest
from unittest.mock import AsyncMock, patch

from maverick.agents.code_reviewer import CodeReviewerAgent
from maverick.models.review import ReviewContext, ReviewResult

@pytest.mark.asyncio
async def test_review_empty_diff():
    """Test review with no changes."""
    agent = CodeReviewerAgent()
    context = ReviewContext(branch="feature/empty")

    with patch.object(agent, '_get_diff', return_value=""):
        result = await agent.execute(context)

    assert result.success is True
    assert result.files_reviewed == 0
    assert result.summary == "No changes to review"

@pytest.mark.asyncio
async def test_review_returns_findings():
    """Test review returns structured findings."""
    agent = CodeReviewerAgent()
    context = ReviewContext(branch="feature/with-issues")

    result = await agent.execute(context)

    assert result.success is True
    assert all(isinstance(f, ReviewFinding) for f in result.findings)
```

### Integration Test Example

```python
import subprocess
import tempfile

@pytest.fixture
def git_repo_with_changes():
    """Create a temporary git repo with changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize repo
        subprocess.run(["git", "init"], cwd=tmpdir, check=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmpdir, check=True)

        # Create initial file
        (Path(tmpdir) / "test.py").write_text("def foo(): pass")
        subprocess.run(["git", "add", "."], cwd=tmpdir, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmpdir, check=True)

        # Create feature branch with changes
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=tmpdir, check=True)
        (Path(tmpdir) / "test.py").write_text("def foo():\n    print('hello')")
        subprocess.run(["git", "add", "."], cwd=tmpdir, check=True)
        subprocess.run(["git", "commit", "-m", "Add print"], cwd=tmpdir, check=True)

        yield tmpdir

@pytest.mark.asyncio
async def test_integration_review_real_repo(git_repo_with_changes):
    """Integration test with real git repo."""
    agent = CodeReviewerAgent()
    context = ReviewContext(
        branch="feature",
        base_branch="main",
        cwd=Path(git_repo_with_changes)
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.files_reviewed >= 1
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| "Branch not found" | Invalid branch name | Verify branch exists with `git branch -a` |
| "Merge conflicts" | Unresolved conflicts | Run `git status` and resolve conflicts |
| "Git command failed" | Git not installed or not in repo | Verify git is installed and cwd is a repo |
| Empty findings | No issues detected | This is expected for clean code |
| Truncated review | Large diff | Review in smaller batches or increase limits |

---

## Next Steps

1. See [data-model.md](data-model.md) for detailed model definitions
2. See [research.md](research.md) for implementation rationale
3. See [contracts/code_reviewer_api.py](contracts/code_reviewer_api.py) for interface contract
