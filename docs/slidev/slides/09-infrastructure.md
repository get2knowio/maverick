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
from maverick.utils.context import (
    build_implementation_context
)

# For ImplementerAgent
context = build_implementation_context(
    task_file=Path(".specify/tasks.md"),
    git=git_ops
)

# Returns:
{
    "tasks": "Parsed task list...",
    "conventions": "# CLAUDE.md\n...",
    "branch": "feature/xyz",
    "recent_commits": [
        "abc123: Initial implementation",
        "def456: Add tests"
    ]
}
```

<div v-click>

## Review Context

```python
# For CodeReviewerAgent
context = build_review_context(
    git=git_ops,
    base_branch="main"
)

# Returns:
{
    "diff": "diff --git a/src/...",
    "changed_files": [
        "src/maverick/agents/base.py",
        "tests/test_agents.py"
    ],
    "conventions": "# CLAUDE.md\n...",
    "stats": {
        "files_changed": 2,
        "insertions": 150,
        "deletions": 30
    }
}
```

</div>

</div>

<div>

## Fix Context

```python
# For IssueFixerAgent
context = build_fix_context(
    validation_output=validation_result,
    files=changed_files
)

# Returns:
{
    "errors": [
        {
            "file": "src/maverick/main.py",
            "line": 42,
            "code": "E501",
            "message": "line too long (88 > 79)"
        }
    ],
    "source_files": {
        "src/maverick/main.py": "def main():\n..."
    },
    "error_summary": "3 E501 violations, 1 F401 unused import"
}
```

<div v-click>

## Token Budget Management

```python
from maverick.utils.context import (
    estimate_tokens,
    fit_to_budget,
    truncate_file
)

# Estimate token count (chars ÷ 4)
tokens = estimate_tokens(text)
# => 1250

# Fit sections to budget with proportional truncation
sections = {
    "diff": large_diff,
    "conventions": claude_md,
    "tasks": task_list
}
fitted = fit_to_budget(sections, budget=32000)
# => Truncates largest sections first

# Preserve context around key lines
truncated = truncate_file(
    content=file_content,
    max_lines=100,
    preserve_lines=[42, 56]  # Error locations
)
# => Keeps context around errors
```

</div>

</div>

</div>

<style>
.grid {
  font-size: 0.85em;
}

code {
  font-size: 0.9em;
}

h2 {
  margin-bottom: 0.5rem !important;
  font-size: 1.2em;
}
</style>
