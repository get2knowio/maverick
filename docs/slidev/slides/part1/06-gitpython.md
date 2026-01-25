---
layout: section
class: text-center
---

# 6. GitPython - Git Operations

<div class="text-lg text-secondary mt-4">
Programmatic git for AI-powered workflows
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">9 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Type-Safe</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Async-Ready</span>
  </div>
</div>

<!--
Section 6 covers GitPython - the library that powers all git operations in Maverick.

We'll cover:
1. Why GitPython over subprocess
2. Opening repositories
3. Status and index operations
4. Commits and history
5. Branch management
6. Remotes and push/pull
7. Diffs and change analysis
8. Async wrappers for TUI responsiveness
9. Error handling patterns
-->

---

## layout: two-cols

# 6.1 Why GitPython?

<div class="pr-4">

**GitPython** provides a programmatic interface to git operations

<div v-click class="mt-4">

## The Problems with Subprocess

<div class="space-y-3 text-sm mt-3">

<div class="flex items-start gap-2">
  <span class="text-coral font-bold">✗</span>
  <div>
    <strong>String Parsing</strong>
    <div class="text-muted">Fragile parsing of git output text</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-coral font-bold">✗</span>
  <div>
    <strong>No Type Safety</strong>
    <div class="text-muted">No IDE autocompletion or type checking</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-coral font-bold">✗</span>
  <div>
    <strong>Error Handling</strong>
    <div class="text-muted">Exit codes don't tell the full story</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-coral font-bold">✗</span>
  <div>
    <strong>Shell Injection Risk</strong>
    <div class="text-muted">shell=True is a security hazard</div>
  </div>
</div>

</div>

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Subprocess Approach ❌

```python
import subprocess

result = subprocess.run(
    ["git", "status", "--porcelain"],
    capture_output=True,
    text=True
)
# Now parse the output manually...
for line in result.stdout.split("\n"):
    if line.startswith("M "):
        modified.append(line[3:])
    elif line.startswith("?? "):
        untracked.append(line[3:])
```

</div>

<div v-click class="mt-4">

## GitPython Approach ✅

```python
from git import Repo

repo = Repo("/path/to/repo")

# Pythonic, type-safe access
modified = repo.index.diff(None)
untracked = repo.untracked_files
branch = repo.active_branch.name
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Maverick Rule:</strong> Use <code>maverick.git</code> for all git operations. Never use <code>subprocess.run("git ...")</code>.
</div>

</div>

<!--
GitPython vs subprocess is not even close. Subprocess requires you to:

1. **Parse text output** - Git's porcelain output is meant for machines, but you still have to write fragile string parsing code.

2. **No type safety** - Your IDE can't help you. There's no autocomplete, no type checking, no refactoring support.

3. **Error handling is painful** - Exit code 1 could mean many things. You have to parse stderr to understand what went wrong.

4. **Security risks** - If you ever use shell=True with user input, you're vulnerable to injection attacks.

GitPython gives you a proper Python API with objects, methods, and attributes. The Maverick codebase has a strict rule: all git operations go through `maverick.git`.
-->

---

## layout: default

# 6.2 Opening a Repository

<div class="text-secondary text-sm mb-4">
Maverick's GitRepository class wraps GitPython's Repo
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Basic Usage

```python
from maverick.git import GitRepository

# Open existing repository
repo = GitRepository("/path/to/repo")

# Defaults to current working directory
repo = GitRepository()

# Access path
print(repo.path)  # Path object
```

</div>

<div v-click class="mt-4">

### Error Handling

```python
from maverick.git import GitRepository
from maverick.exceptions import (
    GitNotFoundError,
    NotARepositoryError,
)

try:
    repo = GitRepository("/some/path")
except GitNotFoundError:
    print("Git not installed!")
except NotARepositoryError as e:
    print(f"Not a repo: {e.path}")
```

</div>

</div>

<div>

<div v-click>

### Direct GitPython Access

```python
from git import Repo

# Raw GitPython (not recommended)
raw_repo = Repo("/path/to/repo")

# But you can access it via Maverick's wrapper
repo = GitRepository("/path/to/repo")
raw_repo = repo.repo  # Underlying Repo instance
```

</div>

<div v-click class="mt-4">

### Repository Detection

```python
from git import InvalidGitRepositoryError

def find_repo_root(path: Path) -> Path | None:
    """Walk up to find .git directory."""
    current = path
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-xs">
  <div class="font-mono text-brass">maverick.git.GitRepository</div>
  <div class="text-muted mt-1">Thread-safe wrapper with typed return values</div>
</div>

</div>

</div>

<!--
The GitRepository class is Maverick's standard interface to git. Key points:

1. **Path handling** - Accepts str or Path, defaults to cwd if not specified.

2. **Typed exceptions** - Instead of generic errors, you get specific exception types: GitNotFoundError (git not installed), NotARepositoryError (not in a git repo).

3. **Thread safety** - The class only stores immutable configuration and the Repo instance. Multiple async tasks can safely use the same GitRepository.

4. **Raw access** - If you ever need the underlying GitPython Repo, it's available via the `.repo` property, but this should be rare.
-->

---

## layout: default

# 6.3 Status & Index

<div class="text-secondary text-sm mb-4">
Understanding your repository's current state
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### GitStatus Dataclass

```python
from maverick.git import GitRepository, GitStatus

repo = GitRepository()
status: GitStatus = repo.status()

# All fields are typed tuples
print(status.staged)     # Files ready to commit
print(status.unstaged)   # Modified but not staged
print(status.untracked)  # New files not tracked
print(status.branch)     # Current branch name
print(status.ahead)      # Commits ahead of upstream
print(status.behind)     # Commits behind upstream
```

</div>

<div v-click class="mt-4">

### Quick Dirty Check

```python
# Simple boolean check
if repo.is_dirty():
    print("You have uncommitted changes!")

# is_dirty() includes untracked files
is_dirty = repo.is_dirty()  # Equivalent to:
# repo._repo.is_dirty(untracked_files=True)
```

</div>

</div>

<div>

<div v-click>

### GitStatus Definition

```python
@dataclass(frozen=True, slots=True)
class GitStatus:
    """Repository status snapshot."""

    staged: tuple[str, ...]
    unstaged: tuple[str, ...]
    untracked: tuple[str, ...]
    branch: str
    ahead: int
    behind: int
```

</div>

<div v-click class="mt-4">

### Staging Files

```python
# Stage specific files
repo.add(["src/main.py", "README.md"])

# Stage all changes (like git add -A)
repo.add_all()

# Or inline with commit
repo.commit("feat: add feature", add_all=True)
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-xs">
  <strong class="text-teal">Frozen Dataclass:</strong> GitStatus is immutable and uses slots for memory efficiency. It's a snapshot, not a live view.
</div>

</div>

</div>

<!--
The status() method returns a GitStatus dataclass - a frozen, immutable snapshot of the repository state.

**Why frozen?** Because git state can change between when you call status() and when you use the result. A mutable object would give false confidence. This is a snapshot at a point in time.

**Why tuples?** Same reason - immutability. Lists could be accidentally modified.

**Ahead/behind** counts are useful for showing users if they need to push or pull. The TUI uses these to display sync status.

The `add_all=True` pattern in commit() is common - stage everything and commit in one operation. This is safer than separate calls in async code.
-->

---

## layout: two-cols

# 6.4 Commits

<div class="pr-4">

Creating and reading commit history

<div v-click class="mt-4">

### Creating Commits

```python
# Basic commit
sha = repo.commit("feat: add new feature")

# Stage and commit together
sha = repo.commit(
    "fix: resolve bug",
    add_all=True  # git add -A first
)

# Allow empty commits (rare)
sha = repo.commit(
    "chore: trigger CI",
    allow_empty=True
)
```

</div>

<div v-click class="mt-4">

### Commit Returns SHA

```python
sha = repo.commit("feat: add feature")
print(sha)  # Full 40-char SHA
# "a1b2c3d4e5f6..."

# Get short SHA for display
short = repo.get_head_sha(short=True)
print(short)  # "a1b2c3d"
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### CommitInfo Dataclass

```python
@dataclass(frozen=True, slots=True)
class CommitInfo:
    """Single commit metadata."""

    sha: str           # Full 40-char SHA
    short_sha: str     # 7-char abbreviated
    message: str       # First line only
    author: str        # Author name
    date: str          # ISO 8601 format
```

</div>

<div v-click class="mt-4">

### Reading History

```python
# Get last 10 commits
history = repo.log(n=10)

for commit in history:
    print(f"{commit.short_sha} {commit.message}")
    print(f"  by {commit.author} on {commit.date}")

# Get commit messages since a ref
messages = repo.commit_messages_since("main")
# Returns: ["fix: bug", "feat: feature", ...]
```

</div>

<div v-click class="mt-4 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">Exception:</strong> <code>NothingToCommitError</code> raised if no staged changes and <code>allow_empty=False</code>
</div>

</div>

<!--
Commits are the bread and butter of git, and Maverick's agents create a lot of them.

**commit() returns the SHA** - This is useful for referencing the commit later, creating tags, or verifying the operation succeeded.

**CommitInfo is minimal** - Just the fields we need. The full commit object from GitPython has much more, but we extract what's useful for display and comparison.

**commit_messages_since()** is particularly useful for generating PR descriptions - we can list all the commits on a feature branch compared to main.

The NothingToCommitError exception lets calling code decide how to handle the case where the working tree is already clean.
-->

---

## layout: two-cols

# 6.5 Branches

<div class="pr-4">

Branch creation, switching, and management

<div v-click class="mt-4">

### Current Branch

```python
branch = repo.current_branch()
print(branch)  # "main" or "feature-x"

# Detached HEAD returns SHA
if repo._repo.head.is_detached:
    print(repo.current_branch())
    # Returns commit SHA instead
```

</div>

<div v-click class="mt-4">

### Creating Branches

```python
# Create and checkout
repo.create_branch("feature/new-agent")

# Create without checkout
repo.create_branch(
    "feature/backup",
    checkout=False
)

# Create from specific ref
repo.create_branch(
    "hotfix/urgent",
    from_ref="v1.0.0"
)
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### Smart Fallback Creation

```python
# If "feature-x" exists, creates
# "feature-x-20240115103045"
actual_name = repo.create_branch_with_fallback(
    "feature-x"
)
print(actual_name)
# May differ from requested name!
```

</div>

<div v-click class="mt-4">

### Switching Branches

```python
# Checkout existing branch
repo.checkout("main")

# Handles detached HEAD
repo.checkout("v1.0.0")  # Tag
repo.checkout("abc123")   # Commit SHA
```

</div>

<div v-click class="mt-4">

### Branch Validation

```python
# Invalid characters rejected
repo.create_branch("my branch")  # ValueError!
repo.create_branch("feature~x")  # ValueError!

# Validation pattern
_INVALID_BRANCH_CHARS = re.compile(
    r"[~^: ?*\[\]\\]"
)
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-xs">
  <strong class="text-brass">BranchExistsError:</strong> Raised if branch already exists (use <code>create_branch_with_fallback</code> to avoid)
</div>

</div>

<!--
Branch management is critical for Maverick's workflows - each feature implementation happens on its own branch.

**create_branch_with_fallback()** is particularly important for automated workflows. If an agent tries to create "feature-123" but it already exists (maybe from a previous failed run), the fallback adds a timestamp suffix instead of failing.

**Branch validation** happens before any git operation. Git has strict rules about branch names - no spaces, no special characters. We validate early to give clear error messages.

**CheckoutConflictError** is raised if checkout would overwrite uncommitted changes. The workflow can then decide to stash, commit, or abort.
-->

---

## layout: two-cols

# 6.6 Remotes & Push/Pull

<div class="pr-4">

Network operations with automatic retry

<div v-click class="mt-4">

### Push with Retry

```python
# Basic push
repo.push()

# Push with upstream tracking
repo.push(set_upstream=True)

# Force push (use carefully!)
repo.push(force=True)

# Push to specific remote/branch
repo.push(
    remote="upstream",
    branch="feature-x"
)
```

</div>

<div v-click class="mt-4">

### Pull and Fetch

```python
# Pull latest changes
repo.pull()

# Pull specific branch
repo.pull(remote="origin", branch="main")

# Fetch without merge
repo.fetch()
repo.fetch(remote="upstream")
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### Network Retry Decorator

```python
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

network_retry = retry(
    retry=retry_if_exception_type(GitCommandError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(
        multiplier=1, min=1, max=10
    ),
    reraise=True,
)

@network_retry
def push(self, ...):
    # Automatically retries on network errors
```

</div>

<div v-click class="mt-4">

### Remote Information

```python
# Get remote URL
url = repo.get_remote_url()
# "https://github.com/user/repo.git"

url = repo.get_remote_url("upstream")
# Returns None if remote doesn't exist
```

</div>

<div v-click class="mt-4 p-3 bg-coral/10 border border-coral/30 rounded-lg text-xs">
  <strong class="text-coral">Exceptions:</strong><br/>
  • <code>PushRejectedError</code> - Remote rejected push<br/>
  • <code>MergeConflictError</code> - Pull has conflicts
</div>

</div>

<!--
Network operations are where things can go wrong - timeouts, connection issues, authentication problems. Maverick uses tenacity for automatic retry.

**Why retry on push/pull/fetch?** Network hiccups happen. A brief DNS failure or SSL renegotiation shouldn't fail an entire workflow. The decorator retries up to 3 times with exponential backoff (1s, 2s, 4s).

**set_upstream=True** is used when pushing a new branch for the first time. It's equivalent to `git push -u origin branch`.

**PushRejectedError** is recoverable - usually means you need to pull first. The workflow can catch this, pull, and retry.

**MergeConflictError** requires human intervention - the workflow captures this and reports which files conflict.
-->

---

## layout: default

# 6.7 Diffs

<div class="text-secondary text-sm mb-4">
Understanding what changed between refs
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Raw Diff Output

```python
# Diff working tree vs HEAD
diff_text = repo.diff()

# Diff between two refs
diff_text = repo.diff(
    base="main",
    head="feature-x"
)

# Staged changes only
diff_text = repo.diff(staged=True)
```

</div>

<div v-click class="mt-4">

### Changed Files List

```python
# Just the filenames
files = repo.get_changed_files()
# ["src/main.py", "README.md"]

files = repo.get_changed_files(ref="main")
# Files changed since main
```

</div>

</div>

<div>

<div v-click>

### DiffStats Dataclass

```python
@dataclass(frozen=True, slots=True)
class DiffStats:
    """Diff statistics between refs."""

    files_changed: int
    insertions: int
    deletions: int
    file_list: tuple[str, ...]
    per_file: Mapping[str, tuple[int, int]]
```

</div>

<div v-click class="mt-4">

### Using DiffStats

```python
stats = repo.diff_stats(base="main")

print(f"{stats.files_changed} files changed")
print(f"+{stats.insertions} -{stats.deletions}")

# Per-file breakdown
for path, (added, removed) in stats.per_file.items():
    print(f"  {path}: +{added} -{removed}")
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-xs">
  <strong class="text-teal">Use Case:</strong> Code review agents use diff_stats() to understand change scope before reviewing
</div>

</div>

</div>

<!--
Diffs are essential for code review workflows. Maverick's review agents need to understand what changed.

**diff()** returns raw unified diff text - useful for passing to Claude for analysis or displaying in a terminal.

**get_changed_files()** returns just filenames - useful for deciding which files to read in full for review.

**DiffStats** gives numeric summaries without the full diff content. This is used for:
- Estimating review complexity (small change vs large refactor)
- Displaying change summaries in the TUI
- Validating that changes were actually made

The per_file mapping lets you identify the hotspots - which files had the most churn.
-->

---

## layout: two-cols

# 6.8 Async Git in Maverick

<div class="pr-4">

Keeping the TUI responsive during git operations

<div v-click class="mt-4">

### The Problem

```python
# Git operations are blocking!
# This freezes the TUI:
repo = GitRepository()
status = repo.status()  # Blocks event loop
repo.push()             # Network I/O blocks

# Textual's event loop can't update
# the UI while git runs
```

</div>

<div v-click class="mt-4">

### AsyncGitRepository

```python
from maverick.git import AsyncGitRepository

# Same interface, async methods
repo = AsyncGitRepository("/path/to/repo")

# All operations are async
status = await repo.status()
await repo.commit("feat: add", add_all=True)
await repo.push()
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### How It Works

```python
class AsyncGitRepository:
    """Async wrapper for GitRepository."""

    def __init__(self, path: Path | str | None = None):
        # Wraps sync implementation
        self._sync = GitRepository(path)

    async def status(self) -> GitStatus:
        # Runs sync code in thread pool
        return await asyncio.to_thread(
            self._sync.status
        )

    async def push(self, ...):
        return await asyncio.to_thread(
            self._sync.push, remote, branch, ...
        )
```

</div>

<div v-click class="mt-4">

### asyncio.to_thread()

```python
import asyncio

# Offloads blocking call to thread pool
result = await asyncio.to_thread(
    blocking_function,
    arg1, arg2
)

# Event loop stays free for UI updates!
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-xs">
  <strong class="text-brass">Best Practice:</strong> Use AsyncGitRepository in workflows and TUI code. Use GitRepository only in sync contexts or tests.
</div>

</div>

<!--
This is a critical pattern for Maverick's TUI. Git operations can take seconds (especially network operations), and we can't freeze the terminal UI.

**asyncio.to_thread()** is the key. It runs the blocking GitPython code in a thread pool while the asyncio event loop continues processing UI events.

**Why not make GitPython async?** GitPython is inherently synchronous - it wraps the git CLI. Making a truly async git library would require reimplementing git in Python. The thread pool approach is pragmatic.

**Consistency** - AsyncGitRepository has the exact same method signatures as GitRepository, just with `async` and `await`. This makes it easy to convert sync code to async.

In workflows, always use AsyncGitRepository. The only exception is tests or scripts that don't have an event loop.
-->

---

## layout: default

# 6.9 Error Handling

<div class="text-secondary text-sm mb-4">
Specific exceptions for specific failures
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Exception Hierarchy

```python
# Base exception
class GitError(AgentError):
    operation: str | None
    recoverable: bool

# Specific exceptions
class GitNotFoundError(GitError): ...
class NotARepositoryError(GitError): ...
class BranchExistsError(GitError): ...
class MergeConflictError(GitError): ...
class PushRejectedError(GitError): ...
class NothingToCommitError(GitError): ...
class NoStashError(GitError): ...
class CheckoutConflictError(GitError): ...
```

</div>

<div v-click class="mt-4">

### Recoverable Flag

```python
# Some errors are recoverable
if isinstance(e, PushRejectedError):
    print(e.recoverable)  # True
    # Can pull and retry

if isinstance(e, BranchExistsError):
    print(e.recoverable)  # False
    # Need different branch name
```

</div>

</div>

<div>

<div v-click>

### Handling in Workflows

```python
from maverick.git import AsyncGitRepository
from maverick.exceptions import (
    PushRejectedError,
    MergeConflictError,
    NothingToCommitError,
)

async def safe_push(repo: AsyncGitRepository):
    try:
        await repo.push()
    except PushRejectedError:
        # Pull and retry
        await repo.pull()
        await repo.push()
    except NothingToCommitError:
        # No changes - that's okay
        pass
```

</div>

<div v-click class="mt-4">

### Error Conversion

```python
def _convert_git_error(
    exc: GitCommandError,
    operation: str
) -> GitError:
    """Convert GitPython exception."""
    stderr = str(exc.stderr or "").lower()

    if "already exists" in stderr:
        return BranchExistsError(...)
    if "conflict" in stderr:
        return MergeConflictError(...)
    if "rejected" in stderr:
        return PushRejectedError(...)

    return GitError(str(exc), operation=operation)
```

</div>

</div>

</div>

<!--
Maverick's exception hierarchy lets workflows handle errors intelligently.

**Specific exceptions** - Instead of catching generic GitCommandError and parsing stderr, you catch typed exceptions. Your IDE can help you handle each case.

**Recoverable flag** - Some errors can be retried with different strategies:
- PushRejectedError → pull then push
- CheckoutConflictError → stash then checkout
- MergeConflictError → requires human intervention

**NothingToCommitError** is often not an error at all - if an agent makes no changes, that's valid. The workflow decides whether to treat it as a problem.

**Error conversion** happens inside GitRepository. Raw GitPython exceptions are caught and converted to Maverick exceptions, so callers never see GitCommandError.
-->

---

layout: center
class: text-center

---

# GitPython Summary

<div class="grid grid-cols-3 gap-6 mt-8 text-sm">

<div v-click class="p-4 bg-raised rounded-lg border border-border">
  <div class="text-2xl mb-2">🐍</div>
  <div class="font-semibold text-brass">Pythonic API</div>
  <div class="text-muted mt-2">
    Objects, methods, attributes<br/>
    No string parsing
  </div>
</div>

<div v-click class="p-4 bg-raised rounded-lg border border-border">
  <div class="text-2xl mb-2">⚡</div>
  <div class="font-semibold text-teal">Async Ready</div>
  <div class="text-muted mt-2">
    AsyncGitRepository wraps<br/>
    sync ops via to_thread()
  </div>
</div>

<div v-click class="p-4 bg-raised rounded-lg border border-border">
  <div class="text-2xl mb-2">🔄</div>
  <div class="font-semibold text-coral">Retry Built-In</div>
  <div class="text-muted mt-2">
    Network ops retry with<br/>
    exponential backoff
  </div>
</div>

</div>

<div class="mt-8 text-sm text-muted">
  Key Files: <code>src/maverick/git/repository.py</code> • <code>src/maverick/git/__init__.py</code>
</div>

<div v-click class="mt-6 p-4 bg-brass/10 border border-brass/30 rounded-lg max-w-md mx-auto">

**Remember**: All git operations in Maverick go through `maverick.git`.  
Never use `subprocess.run("git ...")` directly.

</div>

<!--
Let's recap the key takeaways from GitPython in Maverick:

1. **Pythonic API** - GitPython gives us proper Python objects. No more parsing git output text. Type hints everywhere, IDE autocompletion, refactoring support.

2. **Async Ready** - The AsyncGitRepository wrapper runs blocking git operations in a thread pool. The TUI stays responsive even during slow network operations.

3. **Retry Built-In** - Network operations (push, pull, fetch) automatically retry with exponential backoff. Transient failures don't crash workflows.

The pattern here - wrapping a sync library with async via to_thread() - is common in Maverick. You'll see it again with PyGithub.

Next up: PyGithub for GitHub API integration!
-->
