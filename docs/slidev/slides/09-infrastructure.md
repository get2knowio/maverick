---
layout: section
---

# Part 9: Infrastructure

Git Operations, Process Runners & Context Building

---
layout: default
---

# Git & Subprocess Operations

<div class="grid grid-cols-2 gap-4">

<div>

## GitOperations Module

Pure Python git wrapper (no dependencies)

```python
from maverick.utils.git import GitOperations

git = GitOperations(repo_path="/path/to/repo")

# Query operations
branch = git.current_branch()
status = git.status()
commits = git.log(n=5)
diff = git.diff(base="main")
stats = git.diff_stats(base="main")

# Mutation operations
git.create_branch("feature/new")
git.checkout("feature/new")
git.commit(message="Add feature", files=["*.py"])
git.push(remote="origin", branch="feature/new")

# Stash operations
git.stash(message="WIP changes")
git.stash_pop()
```

</div>

<div>

## Exception Hierarchy

```python
GitError (base)
├── GitNotFoundError
│   # Git executable not found
├── NotARepositoryError
│   # Not a valid git repository
├── BranchExistsError
│   # Branch already exists
├── MergeConflictError
│   # Merge conflict detected
├── PushRejectedError
│   # Push rejected by remote
└── NothingToCommitError
    # No changes to commit
```

<div class="mt-4" v-click>

## Async Runners

```python
# CommandRunner: Async subprocess with timeout
result = await CommandRunner.run(
    ["pytest", "tests/"],
    timeout=300,
    cwd="/path/to/repo"
)

# ValidationRunner: Sequential stages
results = await ValidationRunner.run_stages(
    stages=[format_stage, lint_stage, test_stage],
    auto_fix=True
)

# GitHubCLIRunner: gh CLI wrapper
pr_url = await GitHubCLIRunner.create_pr(
    title="Add feature",
    body="Description",
    base="main"
)

# CodeRabbitRunner: Optional enhanced review
review = await CodeRabbitRunner.review(
    pr_number=123,
    config=review_config
)
```

</div>

</div>

</div>

---
layout: default
---

# Context Builders

<div class="grid grid-cols-2 gap-4">

<div>

## Implementation Context

```python
context = build_implementation_context(
    task_file=Path(".specify/tasks.md"),
    git=git_ops
)
# => {tasks, conventions, branch, commits}
```

## Review Context

```python
context = build_review_context(
    git=git_ops, base_branch="main"
)
# => {diff, changed_files, conventions, stats}
```

## Fix Context

```python
context = build_fix_context(
    validation_output=result, files=changed
)
# => {errors, source_files, error_summary}
```

</div>

<div>

## Token Budget Management

```python
# Estimate tokens (chars / 4)
tokens = estimate_tokens(text)

# Fit sections to budget
fitted = fit_to_budget(sections, budget=32000)

# Preserve context around key lines
truncated = truncate_file(
    content=file_content,
    max_lines=100,
    preserve_lines=[42, 56]  # Error lines
)
```

<div class="mt-4 text-sm">

**Strategies**:
- Proportional truncation (largest first)
- Preserve error locations
- Minimum quotas for high-priority sections

</div>

</div>

</div>
