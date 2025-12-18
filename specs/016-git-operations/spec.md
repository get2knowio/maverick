# Feature Specification: Git Operations Module

**Feature Branch**: `016-git-operations`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create a spec for a pure Python git operations module in Maverick that handles all deterministic git actions."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Query Repository State (Priority: P1)

A Maverick workflow needs to understand the current state of a git repository before making any changes. This includes knowing the current branch, uncommitted changes, and recent commit history.

**Why this priority**: All other git operations depend on knowing the repository state first. Without state awareness, workflows cannot make safe decisions about branching, committing, or pushing.

**Independent Test**: Can be fully tested by initializing a git repository, making changes, and verifying the module correctly reports branch name, file status, and commit history.

**Acceptance Scenarios**:

1. **Given** a valid git repository, **When** requesting the current branch, **Then** return the exact branch name as a string
2. **Given** a repository with staged, unstaged, and untracked files, **When** requesting status, **Then** return structured data categorizing each file correctly
3. **Given** a repository with commits, **When** requesting log with n=5, **Then** return the 5 most recent commits with hash, message, author, and date
4. **Given** a directory that is not a git repository, **When** any operation is attempted, **Then** raise NotARepositoryError with a descriptive message

---

### User Story 2 - Create and Manage Branches (Priority: P1)

A workflow needs to create feature branches, switch between branches, and manage branch state without risk of data loss.

**Why this priority**: Branch management is fundamental to the Maverick workflow pattern of creating isolated feature branches for each task.

**Independent Test**: Can be tested by creating branches, switching between them, and verifying the correct branch is active.

**Acceptance Scenarios**:

1. **Given** a repository on branch "main", **When** creating a branch "feature-x" with checkout=True, **Then** create the branch and switch to it
2. **Given** a repository on branch "main", **When** creating a branch "feature-x" with checkout=False, **Then** create the branch but remain on "main"
3. **Given** a branch "feature-x" already exists, **When** attempting to create "feature-x" again, **Then** raise BranchExistsError
4. **Given** uncommitted changes exist, **When** checking out another branch, **Then** complete the checkout if no conflicts exist, or raise an appropriate error if conflicts would occur

---

### User Story 3 - Commit and Push Changes (Priority: P1)

A workflow needs to commit completed work with descriptive messages and push changes to a remote repository.

**Why this priority**: Committing and pushing are the primary ways Maverick preserves work and enables collaboration via pull requests.

**Independent Test**: Can be tested by making file changes, committing them, and verifying the commit exists with the correct message and that push succeeds to a remote.

**Acceptance Scenarios**:

1. **Given** staged or unstaged changes, **When** committing with add_all=True, **Then** stage all changes and create a commit, returning the commit hash
2. **Given** only staged changes, **When** committing with add_all=False, **Then** commit only staged changes
3. **Given** a new branch not on remote, **When** pushing with set_upstream=True, **Then** push and set the upstream tracking branch
4. **Given** a branch that is behind remote, **When** pushing, **Then** raise PushRejectedError with guidance to pull first
5. **Given** no changes to commit, **When** committing, **Then** raise an appropriate error indicating nothing to commit

---

### User Story 4 - Analyze Code Changes (Priority: P2)

A workflow needs to understand what code has changed between branches or commits to generate meaningful PR descriptions and conduct reviews.

**Why this priority**: Diff analysis enables intelligent PR body generation and helps workflows understand the scope of changes.

**Independent Test**: Can be tested by making changes on a feature branch and requesting diffs against main branch.

**Acceptance Scenarios**:

1. **Given** changes between HEAD and a base branch, **When** requesting diff, **Then** return the full diff output as a string
2. **Given** changes between branches, **When** requesting diff_stats, **Then** return structured data with files changed count, total insertions, total deletions, and list of affected files
3. **Given** no changes between branches, **When** requesting diff or diff_stats, **Then** return empty diff string or DiffStats with zero values

---

### User Story 5 - Sync with Remote (Priority: P2)

A workflow needs to pull the latest changes from a remote branch to keep local work synchronized.

**Why this priority**: Keeping synchronized with remote prevents divergent work and merge conflicts later in the workflow.

**Independent Test**: Can be tested by setting up a remote with newer commits and verifying pull retrieves them.

**Acceptance Scenarios**:

1. **Given** remote has new commits, **When** pulling, **Then** fast-forward local branch to include remote changes
2. **Given** local and remote have diverged, **When** pulling results in conflicts, **Then** raise MergeConflictError with affected files
3. **Given** specified remote branch does not exist, **When** pulling, **Then** raise an appropriate error

---

### User Story 6 - Stash Work in Progress (Priority: P3)

A workflow may need to temporarily set aside uncommitted changes to perform other operations, then restore them.

**Why this priority**: Stashing is useful but less common; most workflows commit or discard changes rather than stashing.

**Independent Test**: Can be tested by making changes, stashing them, verifying working directory is clean, then restoring the stash.

**Acceptance Scenarios**:

1. **Given** uncommitted changes, **When** stashing with a message, **Then** save changes to stash with the provided message and clean the working directory
2. **Given** uncommitted changes, **When** stashing without a message, **Then** save changes to stash with a default message
3. **Given** a stash exists, **When** calling stash_pop, **Then** restore the most recent stash and remove it from the stash list
4. **Given** no stash exists, **When** calling stash_pop, **Then** raise an appropriate error

---

### Edge Cases

- What happens when git is not installed on the system? → Raise GitNotFoundError on first operation
- What happens when the working directory is deleted during operations? → Raise NotARepositoryError
- What happens with very large diffs (megabytes)? → Return full diff; caller is responsible for handling size
- What happens with branches containing special characters? → Pass through to git; git handles validation
- What happens when network is unavailable during push/pull? → Raise appropriate error wrapping git's network error
- What happens with detached HEAD state? → current_branch() returns the commit hash instead of branch name

## Requirements *(mandatory)*

### Functional Requirements

**Core Operations**:
- **FR-001**: System MUST provide a GitOperations class that wraps git CLI commands
- **FR-002**: System MUST support specifying a working directory in the constructor (defaults to current working directory)
- **FR-003**: All methods MUST be synchronous (blocking) operations
- **FR-004**: All methods MUST raise typed exceptions rather than returning success/failure booleans
- **FR-005**: System MUST NOT use shell=True in any subprocess calls for security

**Repository State**:
- **FR-006**: System MUST provide current_branch() returning the active branch name as a string
- **FR-007**: System MUST provide status() returning a GitStatus dataclass with staged, unstaged, untracked files, branch name, ahead/behind counts
- **FR-008**: System MUST provide log(n) returning a list of CommitInfo dataclasses for the n most recent commits

**Branch Management**:
- **FR-009**: System MUST provide create_branch(name, checkout) to create new branches with optional checkout
- **FR-010**: System MUST provide checkout(branch) to switch to an existing branch

**Committing and Pushing**:
- **FR-011**: System MUST provide commit(message, add_all) that creates a commit and returns the commit hash
- **FR-012**: System MUST provide push(remote, set_upstream) to push current branch to remote
- **FR-013**: System MUST provide pull(remote, branch) to fetch and merge remote changes

**Diff Analysis**:
- **FR-014**: System MUST provide diff(base, head) returning the full diff as a string
- **FR-015**: System MUST provide diff_stats(base) returning a DiffStats dataclass with files changed, insertions, deletions, and file list

**Stashing**:
- **FR-016**: System MUST provide stash(message) to save and clear uncommitted changes
- **FR-017**: System MUST provide stash_pop() to restore the most recent stash

**Exception Handling**:
- **FR-018**: System MUST raise GitError as the base exception for all git-related errors
- **FR-019**: System MUST raise GitNotFoundError when git CLI is not installed
- **FR-020**: System MUST raise NotARepositoryError when operating outside a git repository
- **FR-021**: System MUST raise BranchExistsError when creating a branch that already exists
- **FR-022**: System MUST raise MergeConflictError when pull results in conflicts
- **FR-023**: System MUST raise PushRejectedError when remote rejects a push
- **FR-024**: System MUST raise NothingToCommitError when commit is attempted with no changes
- **FR-025**: System MUST raise NoStashError when stash_pop is called with no stash entries
- **FR-026**: System MUST raise CheckoutConflictError when checkout would overwrite uncommitted changes

**Thread Safety**:
- **FR-027**: System MUST be thread-safe by maintaining no mutable instance state beyond the working directory path

**Scope Boundary**:
- **FR-028**: System MUST NOT invoke any AI/Claude operations; this is pure Python git automation

### Key Entities

- **GitOperations**: The main class providing all git operations. Configured with an optional working directory path.
- **DiffStats**: Represents diff statistics with files_changed (int), insertions (int), deletions (int), and file_list (tuple of file paths)
- **GitStatus**: Represents repository status with staged (tuple), unstaged (tuple), untracked (tuple), branch (str), ahead (int), behind (int)
- **CommitInfo**: Represents a commit with hash (str), short_hash (str), message (str), author (str), date (str, ISO 8601 format)
- **GitError**: Base exception for all git-related errors
- **GitNotFoundError**: Raised when git CLI is not available
- **NotARepositoryError**: Raised when not in a git repository
- **BranchExistsError**: Raised when branch already exists
- **MergeConflictError**: Raised when merge conflicts occur
- **PushRejectedError**: Raised when remote rejects push
- **NothingToCommitError**: Raised when commit attempted with no staged or unstaged changes
- **NoStashError**: Raised when stash_pop called with empty stash list
- **CheckoutConflictError**: Raised when checkout would overwrite uncommitted local changes

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 12 specified git operations execute successfully on valid repositories without errors
- **SC-002**: 100% of error conditions raise the appropriate typed exception (not generic exceptions or boolean returns)
- **SC-003**: All operations complete within 5 seconds wall-clock time for typical repository sizes (under 10,000 files), measured from method call to return excluding test setup
- **SC-004**: Module correctly handles all edge cases identified in the specification
- **SC-005**: All structured return types (DiffStats, GitStatus, CommitInfo) contain accurate, parsed data matching git output
- **SC-006**: Thread safety is verified by concurrent operations on the same repository not causing data corruption
- **SC-007**: No subprocess call uses shell=True (verified by code inspection)
- **SC-008**: 100% test coverage for all public methods and exception paths

## Assumptions

- Git CLI (version 2.0+) is installed and available in the system PATH
- Operations are performed on local repositories; remote operations require network access
- The module targets Unix-like systems and Windows with git installed
- Large repositories may have longer operation times; no explicit timeout is enforced
- Git hooks may be triggered during operations; the module does not suppress them
- The default remote is named "origin" as per git conventions
