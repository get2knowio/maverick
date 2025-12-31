# Data Model: Git Operations Module

**Feature**: 016-git-operations | **Date**: 2025-12-18

## Entity Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GitOperations                                     │
│  (Main class - wraps git CLI)                                              │
│                                                                             │
│  _cwd: Path                                                                │
│                                                                             │
│  Methods: current_branch(), status(), log(), create_branch(), checkout(),  │
│           commit(), push(), pull(), diff(), diff_stats(), stash(),         │
│           stash_pop()                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ returns
                                    ▼
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│    GitStatus      │  │    CommitInfo     │  │    DiffStats      │
│  (frozen)         │  │  (frozen)         │  │  (frozen)         │
│                   │  │                   │  │                   │
│  staged: tuple    │  │  hash: str        │  │  files_changed: int│
│  unstaged: tuple  │  │  short_hash: str  │  │  insertions: int  │
│  untracked: tuple │  │  message: str     │  │  deletions: int   │
│  branch: str      │  │  author: str      │  │  file_list: tuple │
│  ahead: int       │  │  date: str        │  │                   │
│  behind: int      │  │                   │  │                   │
└───────────────────┘  └───────────────────┘  └───────────────────┘

                           Exception Hierarchy
┌─────────────────────────────────────────────────────────────────────────────┐
│  MaverickError                                                              │
│      └── AgentError                                                         │
│              └── GitError (existing)                                        │
│                      ├── GitNotFoundError (new)                            │
│                      ├── NotARepositoryError (new)                         │
│                      ├── BranchExistsError (new)                           │
│                      ├── MergeConflictError (new)                          │
│                      └── PushRejectedError (new)                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Entity Definitions

### GitOperations

**Purpose**: Main class providing all git operations through a unified interface.

| Attribute | Type | Description |
|-----------|------|-------------|
| `_cwd` | `Path` | Working directory for all git commands (immutable) |

**Constructor**: `GitOperations(cwd: Path | str | None = None)`
- If `cwd` is None, uses current working directory
- Validates git is installed on first operation (lazy check)

**Thread Safety**: Yes - only immutable state (`_cwd`)

---

### GitStatus

**Purpose**: Represents repository status snapshot.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `staged` | `tuple[str, ...]` | Files staged for commit | May be empty |
| `unstaged` | `tuple[str, ...]` | Modified but unstaged files | May be empty |
| `untracked` | `tuple[str, ...]` | Untracked files | May be empty |
| `branch` | `str` | Current branch name | Non-empty string |
| `ahead` | `int` | Commits ahead of upstream | >= 0 |
| `behind` | `int` | Commits behind upstream | >= 0 |

**Decorators**: `@dataclass(frozen=True, slots=True)`

**Example**:
```python
GitStatus(
    staged=("src/main.py",),
    unstaged=("README.md",),
    untracked=("temp.txt",),
    branch="feature-x",
    ahead=2,
    behind=0,
)
```

---

### CommitInfo

**Purpose**: Represents a single commit's metadata.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `hash` | `str` | Full 40-character SHA | 40 hex chars |
| `short_hash` | `str` | Abbreviated SHA (7 chars) | 7 chars |
| `message` | `str` | First line of commit message | Non-empty |
| `author` | `str` | Author name | Non-empty |
| `date` | `str` | ISO 8601 date string | Valid ISO date |

**Decorators**: `@dataclass(frozen=True, slots=True)`

**Example**:
```python
CommitInfo(
    hash="abc1234567890def1234567890abc1234567890de",
    short_hash="abc1234",
    message="feat: add user authentication",
    author="Jane Developer",
    date="2025-12-18T10:30:00+00:00",
)
```

---

### DiffStats

**Purpose**: Represents statistics about code changes between refs.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `files_changed` | `int` | Number of files with changes | >= 0 |
| `insertions` | `int` | Total lines added | >= 0 |
| `deletions` | `int` | Total lines removed | >= 0 |
| `file_list` | `tuple[str, ...]` | Paths of changed files | May be empty |

**Decorators**: `@dataclass(frozen=True, slots=True)`

**Example**:
```python
DiffStats(
    files_changed=3,
    insertions=150,
    deletions=20,
    file_list=("src/main.py", "src/utils.py", "tests/test_main.py"),
)
```

---

## Exception Types

All exceptions extend the existing `GitError` class from `maverick.exceptions`.

### GitNotFoundError

**Purpose**: Raised when git CLI is not installed or not in PATH.

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Human-readable error (inherited) |
| `operation` | `str | None` | Always "git_check" |
| `recoverable` | `bool` | Always False |

**Raised By**: Any GitOperations method (lazy check on first command)

---

### NotARepositoryError

**Purpose**: Raised when operating outside a git repository.

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Human-readable error (inherited) |
| `operation` | `str | None` | The attempted operation |
| `recoverable` | `bool` | Always False |
| `path` | `Path` | Directory that is not a repo |

**Raised By**: Any GitOperations method

---

### BranchExistsError

**Purpose**: Raised when creating a branch that already exists.

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Human-readable error (inherited) |
| `operation` | `str | None` | Always "create_branch" |
| `recoverable` | `bool` | Always False |
| `branch_name` | `str` | Name of existing branch |

**Raised By**: `create_branch()`

---

### MergeConflictError

**Purpose**: Raised when pull results in merge conflicts.

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Human-readable error (inherited) |
| `operation` | `str | None` | Always "pull" |
| `recoverable` | `bool` | Always True |
| `conflicted_files` | `tuple[str, ...]` | Paths with conflicts |

**Raised By**: `pull()`

---

### PushRejectedError

**Purpose**: Raised when remote rejects a push.

| Attribute | Type | Description |
|-----------|------|-------------|
| `message` | `str` | Human-readable error (inherited) |
| `operation` | `str | None` | Always "push" |
| `recoverable` | `bool` | Always True |
| `reason` | `str` | Rejection reason from git |

**Raised By**: `push()`

---

## State Transitions

The `GitOperations` class is stateless; state lives in the git repository itself. However, certain operations affect repository state:

```
Repository State Machine (conceptual)
─────────────────────────────────────

                    checkout(branch)
   [On Branch A] ────────────────────► [On Branch B]
        │                                    │
        │ commit(msg, add_all=True)         │
        ▼                                    │
   [Clean + 1 commit]                       │
        │                                    │
        │ push()                            │
        ▼                                    │
   [Synced with remote]◄────────────────────┘

Stash Flow:
   [Dirty] ──stash()──► [Clean + stash@{0}] ──stash_pop()──► [Dirty]
```

---

## Relationships

```
GitOperations (1) ───uses───► GitError hierarchy (many)
      │
      │ returns
      ▼
    ┌─────────────────────────────────────┐
    │  Value Objects (all frozen)         │
    │  - GitStatus   (from status())      │
    │  - CommitInfo  (from log())         │
    │  - DiffStats   (from diff_stats())  │
    └─────────────────────────────────────┘
```

- GitOperations creates and returns value objects
- GitOperations raises specific exception types
- All value objects are immutable (frozen dataclasses)
- No circular dependencies; no inheritance among value objects
