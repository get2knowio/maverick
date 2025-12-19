# Research: Git Operations Module

**Feature**: 016-git-operations | **Date**: 2025-12-18

## Research Summary

This document consolidates research findings for the Git Operations module implementation decisions.

---

## 1. Subprocess Best Practices for Git CLI Wrapping

**Decision**: Use `subprocess.run()` with explicit argument lists (no shell=True)

**Rationale**:
- Security: Prevents shell injection attacks by avoiding command string parsing
- Portability: Works consistently across Unix and Windows platforms
- Control: Direct argument passing gives predictable behavior with special characters
- Timeout: `subprocess.run()` supports native timeout parameter

**Alternatives Considered**:
- `os.system()` - Rejected: No stdout/stderr capture, uses shell
- `subprocess.Popen()` - Rejected: More complex; `run()` covers our use cases
- `shell=True` with shlex.quote() - Rejected: Still has edge cases; direct args are safer

**Implementation Pattern**:
```python
result = subprocess.run(
    ["git", "status", "--porcelain"],
    cwd=self._cwd,
    capture_output=True,
    text=True,
    timeout=30,
)
```

---

## 2. Exception Hierarchy for Git Errors

**Decision**: Extend existing `GitError` with specific subclasses

**Rationale**:
- Consistency: Aligns with existing Maverick exception hierarchy (MaverickError → AgentError → GitError)
- Specificity: Callers can catch broad (GitError) or specific (BranchExistsError) exceptions
- Actionable: Each exception type carries context for recovery decisions

**Alternatives Considered**:
- Return tuples (success, error) - Rejected: Pythonic style prefers exceptions; harder to ignore
- Single GitError with error codes - Rejected: Less type-safe; requires string matching
- New base class - Rejected: GitError already exists with appropriate attributes

**Exception Mapping**:
| Git Error Scenario | Exception Type |
|-------------------|----------------|
| git not installed | GitNotFoundError |
| Not in a repository | NotARepositoryError |
| Branch already exists | BranchExistsError |
| Merge conflicts | MergeConflictError |
| Remote rejects push | PushRejectedError |
| Other failures | GitError (base) |

---

## 3. Structured Return Types with Dataclasses

**Decision**: Use `@dataclass(frozen=True, slots=True)` for return types

**Rationale**:
- Immutability: frozen=True prevents accidental mutation of results
- Performance: slots=True reduces memory and improves attribute access
- Type Safety: Static type checkers understand dataclass fields
- Consistency: Matches Constitution VI (Type Safety) and existing Maverick patterns

**Alternatives Considered**:
- Named tuples - Rejected: Less flexible; can't add optional fields
- Pydantic models - Rejected: Overkill for simple data containers; adds dependency
- Plain dicts - Rejected: No type safety; violates Constitution VI

**Data Class Pattern**:
```python
@dataclass(frozen=True, slots=True)
class GitStatus:
    staged: tuple[str, ...]
    unstaged: tuple[str, ...]
    untracked: tuple[str, ...]
    branch: str
    ahead: int
    behind: int
```

---

## 4. Thread Safety Without Global State

**Decision**: Store only `_cwd: Path` as instance state; all operations are stateless

**Rationale**:
- Thread Safety: Multiple threads can share a GitOperations instance safely
- Simplicity: No locks, no mutable state, no race conditions
- Testability: Each method call is independent and reproducible

**Alternatives Considered**:
- Thread-local storage - Rejected: Unnecessary complexity; we have no mutable state
- Instance-level locks - Rejected: Git CLI handles its own locking
- Async-only design - Rejected: Spec requires synchronous operations (FR-003)

**Thread Safety Contract**:
- Only `_cwd: Path` is stored (immutable)
- All method arguments are passed explicitly
- No class-level or module-level mutable state

---

## 5. Git Output Parsing Patterns

**Decision**: Use machine-readable git flags where available; regex for structured output

**Rationale**:
- Reliability: `--porcelain`, `--format`, `--numstat` flags provide stable output
- Maintainability: Less fragile than parsing human-readable output
- Efficiency: Machine formats are often more compact

**Key Git Flags Used**:
| Operation | Flag | Output Format |
|-----------|------|---------------|
| status | `--porcelain` | Two-char status codes + path |
| log | `--format="%H\|%h\|%s\|%an\|%aI"` | Pipe-delimited fields |
| diff | `--numstat` | Additions/deletions per file |
| branch | `--show-current` | Just the branch name |
| rev-parse | `--abbrev-ref HEAD` | Branch name or "HEAD" |

**Alternatives Considered**:
- Parse default git output - Rejected: Locale-dependent; format may change
- Use gitpython library - Rejected: Adds external dependency; subprocess is sufficient
- Use dulwich (pure Python git) - Rejected: Heavy; we only need CLI wrapper

---

## 6. Error Detection from Git Exit Codes and Stderr

**Decision**: Check return code first, then parse stderr for specific error types

**Rationale**:
- Git uses exit codes consistently (0 = success, non-zero = failure)
- Specific errors have recognizable stderr patterns
- Combining both provides accurate exception mapping

**Error Detection Patterns**:
```python
# Return code check
if result.returncode != 0:
    stderr = result.stderr.lower()

    # Specific error mapping
    if "not a git repository" in stderr:
        raise NotARepositoryError(...)
    if "already exists" in stderr:
        raise BranchExistsError(...)
    if "conflict" in stderr:
        raise MergeConflictError(...)
    if "rejected" in stderr:
        raise PushRejectedError(...)

    # Default
    raise GitError(...)
```

---

## 7. Detached HEAD Handling

**Decision**: Return commit hash when in detached HEAD state

**Rationale**:
- Spec defines this behavior (Edge Cases section)
- Callers can distinguish branch vs detached by checking for 40-char hex string
- Consistent with git's own behavior (`git branch --show-current` returns empty)

**Implementation**:
```python
def current_branch(self) -> str:
    result = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
    if result.stdout.strip() == "HEAD":
        # Detached HEAD - return full SHA
        sha_result = self._run(["rev-parse", "HEAD"])
        return sha_result.stdout.strip()
    return result.stdout.strip()
```

---

## Resolved Unknowns

All Technical Context items were known. This research confirms best practices for:

1. Subprocess invocation patterns (safe, portable)
2. Exception hierarchy design (extends existing)
3. Dataclass usage (frozen, slots)
4. Thread safety approach (no mutable state)
5. Git output parsing (machine-readable flags)
6. Error detection patterns (returncode + stderr)
7. Detached HEAD handling (return SHA)

**Status**: All research complete. Ready for Phase 1 design.
