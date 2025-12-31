# Quickstart: Git Operations Module

**Feature**: 016-git-operations | **Date**: 2025-12-18

## Installation

No additional dependencies required - uses Python stdlib only.

## Basic Usage

```python
from pathlib import Path
from maverick.utils.git_operations import GitOperations

# Initialize with repository path
git = GitOperations(cwd="/path/to/repo")
# Or use current directory
git = GitOperations()
```

## Common Operations

### Check Repository State

```python
# Get current branch
branch = git.current_branch()
print(f"On branch: {branch}")

# Get full status
status = git.status()
print(f"Staged files: {status.staged}")
print(f"Unstaged files: {status.unstaged}")
print(f"Untracked files: {status.untracked}")
print(f"Ahead/behind: {status.ahead}/{status.behind}")

# Get commit history
commits = git.log(n=5)
for commit in commits:
    print(f"{commit.short_hash} - {commit.message} ({commit.author})")
```

### Branch Operations

```python
# Create and switch to new branch
git.create_branch("feature-x", checkout=True)

# Create branch without switching
git.create_branch("feature-y", checkout=False)

# Switch to existing branch
git.checkout("main")
```

### Commit and Push

```python
# Stage all and commit
commit_sha = git.commit("feat: add new feature", add_all=True)
print(f"Created commit: {commit_sha}")

# Push with upstream tracking
git.push(set_upstream=True)

# Regular push
git.push()
```

### Diff Analysis

```python
# Get diff against HEAD
diff_output = git.diff()

# Get diff between branches
diff_output = git.diff(base="main", head="feature-x")

# Get statistics
stats = git.diff_stats(base="main")
print(f"Files changed: {stats.files_changed}")
print(f"Insertions: {stats.insertions}")
print(f"Deletions: {stats.deletions}")
```

### Stash Management

```python
# Stash changes with message
git.stash(message="WIP: feature work")

# Stash without message
git.stash()

# Restore most recent stash
git.stash_pop()
```

## Error Handling

```python
from maverick.exceptions import (
    GitError,
    GitNotFoundError,
    NotARepositoryError,
    BranchExistsError,
    MergeConflictError,
    PushRejectedError,
)

try:
    git.create_branch("feature-x")
except BranchExistsError as e:
    print(f"Branch already exists: {e.branch_name}")
except GitError as e:
    print(f"Git operation failed: {e.message}")

try:
    git.pull()
except MergeConflictError as e:
    print(f"Conflicts in: {e.conflicted_files}")
    # Handle conflicts...

try:
    git.push()
except PushRejectedError as e:
    print(f"Push rejected: {e.reason}")
    print("Run git.pull() first")
```

## Integration with Async Workflows

The module is synchronous by design. Use `asyncio.to_thread()` for async context:

```python
import asyncio
from maverick.utils.git_operations import GitOperations

async def get_status_async():
    git = GitOperations()
    status = await asyncio.to_thread(git.status)
    return status
```

## Thread Safety

`GitOperations` is thread-safe - multiple threads can share the same instance:

```python
import threading

git = GitOperations()

def worker():
    status = git.status()  # Safe from any thread
    print(f"Thread {threading.current_thread().name}: {status.branch}")

threads = [threading.Thread(target=worker) for _ in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

## Testing Tips

Use a temporary git repository for tests:

```python
import pytest
import tempfile
import subprocess
from pathlib import Path
from maverick.utils.git_operations import GitOperations

@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
        yield path

def test_status(temp_repo):
    git = GitOperations(cwd=temp_repo)
    status = git.status()
    assert status.branch in ("main", "master")
```

## Type Checking

Full type hints are provided. Use with mypy:

```bash
mypy src/maverick/utils/git_operations.py
```

## Environment Requirements

- Python 3.10+
- Git CLI 2.0+ installed and in PATH
- Unix-like system or Windows with git
