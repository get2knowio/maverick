# Quickstart: ImplementerAgent and IssueFixerAgent

**Feature**: 004-implementer-issue-fixer-agents | **Date**: 2025-12-14

## Overview

This document provides quick verification scenarios for the ImplementerAgent and IssueFixerAgent implementations.

---

## Prerequisites

- Python 3.10+
- Git installed and configured
- GitHub CLI (`gh`) installed and authenticated (for IssueFixerAgent)
- Virtual environment with Maverick dependencies installed

```bash
# Verify prerequisites
python --version    # Python 3.10+
git --version       # Git 2.x+
gh --version        # GitHub CLI 2.x+
gh auth status      # Should show authenticated

# Install Maverick in development mode
pip install -e ".[dev]"
```

---

## Scenario 1: Execute Single Task (ImplementerAgent)

**Goal**: Verify ImplementerAgent can execute a direct task description.

### Setup

```python
# test_scenario_1.py
import asyncio
from pathlib import Path
from maverick.agents import ImplementerAgent
from maverick.models.implementation import ImplementerContext

async def test_single_task():
    agent = ImplementerAgent()

    context = ImplementerContext(
        task_description="Create a new file src/maverick/utils/hello.py with a function greet(name: str) -> str that returns 'Hello, {name}!'",
        branch="test/single-task",
        cwd=Path.cwd(),
        dry_run=True,  # Don't actually commit
    )

    result = await agent.execute(context)

    # Verify
    assert result.success, f"Task failed: {result.errors}"
    assert result.tasks_completed == 1
    assert any("hello.py" in fc.file_path for fc in result.files_changed)
    print(f"OK: Single task executed. Files: {[fc.file_path for fc in result.files_changed]}")

if __name__ == "__main__":
    asyncio.run(test_single_task())
```

### Expected Output

```
OK: Single task executed. Files: ['src/maverick/utils/hello.py']
```

---

## Scenario 2: Execute Task File (ImplementerAgent)

**Goal**: Verify ImplementerAgent can parse and execute a tasks.md file.

### Setup

Create a test task file:

```markdown
# test_tasks.md

## Phase 1: Setup

- [ ] T001 Create directory tests/quickstart/ if it doesn't exist
- [ ] T002 [P] Create tests/quickstart/__init__.py (empty file)
- [ ] T003 [P] Create tests/quickstart/test_hello.py with a test for greet()
```

```python
# test_scenario_2.py
import asyncio
from pathlib import Path
from maverick.agents import ImplementerAgent
from maverick.models.implementation import ImplementerContext

async def test_task_file():
    # Create test task file
    task_file = Path("test_tasks.md")
    task_file.write_text("""# Test Tasks

## Phase 1: Setup

- [ ] T001 Create directory tests/quickstart/ if it doesn't exist
- [ ] T002 [P] Create tests/quickstart/__init__.py (empty file)
- [ ] T003 [P] Create tests/quickstart/test_hello.py with a simple test
""")

    try:
        agent = ImplementerAgent()
        context = ImplementerContext(
            task_file=task_file,
            branch="test/task-file",
            cwd=Path.cwd(),
            dry_run=True,
        )

        result = await agent.execute(context)

        assert result.success, f"Task file execution failed: {result.errors}"
        assert result.tasks_completed == 3
        print(f"OK: {result.tasks_completed} tasks completed")
        for tr in result.task_results:
            print(f"  {tr.task_id}: {tr.status}")

    finally:
        task_file.unlink(missing_ok=True)

if __name__ == "__main__":
    asyncio.run(test_task_file())
```

### Expected Output

```
OK: 3 tasks completed
  T001: completed
  T002: completed
  T003: completed
```

---

## Scenario 3: Parallel Task Execution (ImplementerAgent)

**Goal**: Verify tasks marked `[P]` execute concurrently.

### Setup

```python
# test_scenario_3.py
import asyncio
import time
from pathlib import Path
from maverick.agents import ImplementerAgent
from maverick.models.implementation import ImplementerContext

async def test_parallel_tasks():
    task_file = Path("test_parallel.md")
    task_file.write_text("""# Parallel Test

## Phase 1

- [ ] T001 [P] Create file parallel_1.txt with content "File 1"
- [ ] T002 [P] Create file parallel_2.txt with content "File 2"
- [ ] T003 [P] Create file parallel_3.txt with content "File 3"
""")

    try:
        agent = ImplementerAgent()
        context = ImplementerContext(
            task_file=task_file,
            branch="test/parallel",
            cwd=Path.cwd(),
            dry_run=True,
        )

        start = time.time()
        result = await agent.execute(context)
        duration = time.time() - start

        assert result.success
        assert result.tasks_completed == 3
        # Parallel tasks should complete faster than sequential
        print(f"OK: 3 parallel tasks completed in {duration:.2f}s")

    finally:
        task_file.unlink(missing_ok=True)
        for i in range(1, 4):
            Path(f"parallel_{i}.txt").unlink(missing_ok=True)

if __name__ == "__main__":
    asyncio.run(test_parallel_tasks())
```

---

## Scenario 4: Fix GitHub Issue (IssueFixerAgent)

**Goal**: Verify IssueFixerAgent can fetch and process a GitHub issue.

### Setup

```python
# test_scenario_4.py
import asyncio
from pathlib import Path
from maverick.agents import IssueFixerAgent
from maverick.models.issue_fix import IssueFixerContext

async def test_issue_fix_with_data():
    """Test with pre-fetched issue data (no GitHub API needed)."""
    agent = IssueFixerAgent()

    # Simulate pre-fetched issue data
    context = IssueFixerContext(
        issue_data={
            "number": 999,
            "title": "Test Issue: Add missing docstring",
            "body": """The function `greet()` in `src/maverick/utils/hello.py` is missing a docstring.

Steps to reproduce:
1. Open src/maverick/utils/hello.py
2. Notice greet() has no docstring

Expected: Function should have a Google-style docstring.""",
            "url": "https://github.com/test/repo/issues/999",
            "labels": [{"name": "documentation"}],
        },
        cwd=Path.cwd(),
        dry_run=True,
    )

    result = await agent.execute(context)

    assert result.issue_number == 999
    if result.success:
        print(f"OK: Issue #{result.issue_number} fixed")
        print(f"  Root cause: {result.root_cause}")
        print(f"  Files changed: {[fc.file_path for fc in result.files_changed]}")
    else:
        print(f"Fix attempted but failed: {result.errors}")
        # This is OK for a test scenario where the file doesn't exist

if __name__ == "__main__":
    asyncio.run(test_issue_fix_with_data())
```

### With Real GitHub Issue

```python
# test_scenario_4_real.py
import asyncio
from pathlib import Path
from maverick.agents import IssueFixerAgent
from maverick.models.issue_fix import IssueFixerContext

async def test_real_issue():
    """Test with a real GitHub issue number."""
    agent = IssueFixerAgent()

    context = IssueFixerContext(
        issue_number=1,  # Replace with actual issue number
        cwd=Path.cwd(),
        dry_run=True,
    )

    try:
        result = await agent.execute(context)
        print(f"Issue #{result.issue_number}: {result.issue_title}")
        print(f"Success: {result.success}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_real_issue())
```

---

## Scenario 5: Validation Pipeline

**Goal**: Verify both agents run validation after changes.

### Setup

```python
# test_scenario_5.py
import asyncio
from pathlib import Path
from maverick.agents import ImplementerAgent
from maverick.models.implementation import ImplementerContext

async def test_validation():
    agent = ImplementerAgent()

    # Create a task that will require validation
    context = ImplementerContext(
        task_description="Create src/maverick/utils/validated.py with a function that has a type annotation error (return int but returning str)",
        branch="test/validation",
        cwd=Path.cwd(),
        dry_run=True,
        skip_validation=False,  # Ensure validation runs
    )

    result = await agent.execute(context)

    # Check validation was attempted
    for tr in result.task_results:
        if tr.validation:
            print(f"Task {tr.task_id} validation results:")
            for vr in tr.validation:
                status = "PASS" if vr.success else "FAIL"
                print(f"  {vr.step}: {status}")

if __name__ == "__main__":
    asyncio.run(test_validation())
```

---

## Scenario 6: Error Recovery (Git)

**Goal**: Verify git error recovery per FR-024a.

### Setup

```python
# test_scenario_6.py
import asyncio
import subprocess
from pathlib import Path
from maverick.agents import ImplementerAgent
from maverick.models.implementation import ImplementerContext

async def test_git_recovery():
    """Test that agent handles dirty index gracefully."""
    # Create uncommitted changes
    test_file = Path("dirty_index_test.txt")
    test_file.write_text("uncommitted changes")

    try:
        agent = ImplementerAgent()
        context = ImplementerContext(
            task_description="Create a new file clean_file.txt with content 'clean'",
            branch="test/git-recovery",
            cwd=Path.cwd(),
            dry_run=False,  # Actually test commit behavior
        )

        result = await agent.execute(context)

        # Agent should have handled the dirty index
        print(f"Task completed: {result.success}")
        if result.commits:
            print(f"Commits created: {result.commits}")

    finally:
        test_file.unlink(missing_ok=True)
        Path("clean_file.txt").unlink(missing_ok=True)

if __name__ == "__main__":
    asyncio.run(test_git_recovery())
```

---

## Scenario 7: Structured Output (JSON Serialization)

**Goal**: Verify results can be serialized to JSON (FR-025).

### Setup

```python
# test_scenario_7.py
import asyncio
import json
from pathlib import Path
from maverick.agents import ImplementerAgent
from maverick.models.implementation import ImplementerContext, ImplementationResult

async def test_json_output():
    agent = ImplementerAgent()
    context = ImplementerContext(
        task_description="Create a simple test file",
        branch="test/json",
        cwd=Path.cwd(),
        dry_run=True,
    )

    result = await agent.execute(context)

    # Serialize to JSON
    json_str = result.model_dump_json(indent=2)
    print("JSON Output:")
    print(json_str)

    # Verify roundtrip
    restored = ImplementationResult.model_validate_json(json_str)
    assert restored.success == result.success
    assert restored.tasks_completed == result.tasks_completed
    print("OK: JSON roundtrip successful")

if __name__ == "__main__":
    asyncio.run(test_json_output())
```

---

## Acceptance Criteria Verification

| Scenario | Acceptance Criteria | Status |
|----------|---------------------|--------|
| 1 | SC-001: Execute complete task file via single method call | To verify |
| 2 | SC-002: Implementation passes validation checks | To verify |
| 3 | SC-004: Commits follow conventional commit format | To verify |
| 4 | SC-009: IssueFixerAgent fetches and parses issue details | To verify |
| 5 | SC-007: Validation failures auto-corrected 80%+ of time | To verify |
| 7 | SC-008: Results serialize to JSON without data loss | To verify |

---

## Running All Scenarios

```bash
# Run all quickstart scenarios
python -m pytest tests/quickstart/ -v

# Or run individually
python test_scenario_1.py
python test_scenario_2.py
# ... etc
```

---

## Troubleshooting

### "GitHub CLI not authenticated"

```bash
gh auth login
gh auth status
```

### "Git repository not found"

```bash
git init
git config user.email "test@example.com"
git config user.name "Test User"
```

### "Module not found: maverick"

```bash
pip install -e ".[dev]"
```

### "Claude CLI not found"

```bash
npm install -g @anthropic-ai/claude-code
```
