"""Context builders for agent and generate steps.

Context builders are async functions that construct context dictionaries
for agents and generators. They gather necessary data (file reads, git
commands, etc.) and return a dict suitable for the target component.

Each context builder receives workflow inputs and prior step results,
and returns a dictionary containing all the information needed by the
target agent or generator.

Git operations use AsyncGitRepository from maverick.git (GitPython-based).
Non-git shell commands (e.g., `tree`) use CommandRunner from maverick.runners.command.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from maverick.dsl.config import DEFAULTS
from maverick.git import AsyncGitRepository
from maverick.logging import get_logger
from maverick.models.implementation import ImplementerContext
from maverick.models.review import ReviewContext
from maverick.runners.command import CommandRunner

if TYPE_CHECKING:
    from maverick.dsl.serialization.registry import ComponentRegistry

logger = get_logger(__name__)


# =============================================================================
# TypedDict Definitions for Inputs
# =============================================================================


class ImplementationInputs(TypedDict, total=False):
    """Inputs for implementation context builder."""

    task_file: str
    branch_name: str


class ReviewInputs(TypedDict, total=False):
    """Inputs for review context builder."""

    base_branch: str
    pr_number: int


class IssueFixInputs(TypedDict, total=False):
    """Inputs for issue fix context builder."""

    issue_number: int


class CommitMessageInputs(TypedDict, total=False):
    """Inputs for commit message context builder."""

    message: str


class PRBodyInputs(TypedDict, total=False):
    """Inputs for PR body context builder."""

    base_branch: str
    draft: bool
    title: str
    task_summary: str


class PRTitleInputs(TypedDict, total=False):
    """Inputs for PR title context builder."""

    title: str
    branch_name: str
    task_summary: str


class IssueAnalyzerInputs(TypedDict, total=False):
    """Inputs for issue analyzer context builder."""

    parallel: bool
    limit: int


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_project_structure(
    max_depth: int | None = None,
) -> str:
    """Get a directory tree structure for the project.

    Uses the `tree` command via CommandRunner with proper timeout handling.

    Args:
        max_depth: Maximum depth to traverse. If None, uses
            DEFAULTS.PROJECT_STRUCTURE_MAX_DEPTH.

    Returns:
        String representation of the directory tree.
    """
    if max_depth is None:
        max_depth = DEFAULTS.PROJECT_STRUCTURE_MAX_DEPTH
    cwd = Path.cwd()
    runner = CommandRunner(cwd=cwd, timeout=DEFAULTS.COMMAND_TIMEOUT)

    # Try using tree command if available
    ignore_pattern = (
        "__pycache__|*.pyc|.git|.venv|venv|node_modules|.pytest_cache|.ruff_cache"
    )
    result = await runner.run(
        [
            "tree",
            "-L",
            str(max_depth),
            "-I",
            ignore_pattern,
            "--dirsfirst",
        ]
    )

    if result.success:
        return result.stdout.strip()

    # Fallback: simple directory listing
    try:
        lines: list[str] = []
        lines.append(str(cwd.name) + "/")

        def add_tree(path: Path, prefix: str = "", depth: int = 0) -> None:
            if depth >= max_depth:
                return

            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            # Filter out common ignore patterns
            items = [
                item
                for item in items
                if item.name
                not in {
                    "__pycache__",
                    ".git",
                    ".venv",
                    "venv",
                    "node_modules",
                    ".pytest_cache",
                    ".ruff_cache",
                    ".mypy_cache",
                    "dist",
                    "build",
                    "*.egg-info",
                }
                and not item.name.endswith(".pyc")
            ]

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                current_prefix = "└── " if is_last else "├── "
                next_prefix = "    " if is_last else "│   "

                if item.is_dir():
                    lines.append(f"{prefix}{current_prefix}{item.name}/")
                    add_tree(item, prefix + next_prefix, depth + 1)
                else:
                    lines.append(f"{prefix}{current_prefix}{item.name}")

        add_tree(cwd)
        return "\n".join(lines)

    except Exception as e:
        logger.debug("Failed to generate project structure: %s", e)
        return ""


async def _get_spec_artifacts() -> dict[str, str]:
    """Read spec artifacts from the current directory or spec directory.

    Returns:
        Dict mapping artifact names to their content.
    """
    artifacts: dict[str, str] = {}
    cwd = Path.cwd()

    # Get current branch name using AsyncGitRepository
    repo = AsyncGitRepository(cwd)
    branch_name = await repo.current_branch()

    if branch_name and branch_name != "(detached)":
        # Try to find spec directory matching branch name
        spec_patterns = [
            cwd / ".specify" / branch_name,
            cwd / "specs" / branch_name,
        ]

        for spec_dir in spec_patterns:
            if spec_dir.exists() and spec_dir.is_dir():
                # Read common spec files
                for filename in ["spec.md", "plan.md", "tasks.md", "data-model.md"]:
                    spec_file = spec_dir / filename
                    if spec_file.exists():
                        try:
                            artifacts[filename] = spec_file.read_text()
                        except Exception as e:
                            logger.debug("Failed to read %s: %s", spec_file, e)

    return artifacts


async def _get_diff(ref: str = "HEAD", staged: bool = False) -> str:
    """Get git diff against a reference.

    Args:
        ref: Git reference to diff against.
        staged: If True, get staged changes only.

    Returns:
        Git diff output, or empty string on error.
    """
    repo = AsyncGitRepository(Path.cwd())
    return await repo.diff(base=ref, staged=staged)


async def _get_changed_files(ref: str = "HEAD") -> list[str]:
    """Get list of changed files against a reference.

    Args:
        ref: Git reference to diff against.

    Returns:
        List of changed file paths.
    """
    repo = AsyncGitRepository(Path.cwd())
    return await repo.get_changed_files(ref=ref)


async def _get_file_stats(ref: str = "HEAD") -> dict[str, dict[str, int]]:
    """Get file statistics (additions/deletions) against a reference.

    Args:
        ref: Git reference to diff against.

    Returns:
        Dict mapping file paths to stats with 'additions' and 'deletions' keys.
    """
    repo = AsyncGitRepository(Path.cwd())
    diff_stats = await repo.diff_stats(base=ref)

    # Convert DiffStats per_file format to the legacy dict format
    # DiffStats uses per_file: dict[str, tuple[int, int]] (added, removed)
    # Legacy format: dict[str, dict[str, int]] with 'additions' and 'deletions' keys
    result: dict[str, dict[str, int]] = {}
    for file_path, (added, removed) in diff_stats.per_file.items():
        result[file_path] = {"additions": added, "deletions": removed}
    return result


async def _get_recent_commits(limit: int | None = None) -> list[str]:
    """Get recent commit messages.

    Args:
        limit: Maximum number of commits to retrieve. If None, uses
            DEFAULTS.DEFAULT_RECENT_COMMIT_LIMIT.

    Returns:
        List of commit messages.
    """
    if limit is None:
        limit = DEFAULTS.DEFAULT_RECENT_COMMIT_LIMIT
    repo = AsyncGitRepository(Path.cwd())
    return await repo.commit_messages(limit=limit)


async def _get_commits_on_branch(base_branch: str = "main") -> list[str]:
    """Get all commit messages on the current branch since base.

    Args:
        base_branch: Base branch to compare against.

    Returns:
        List of commit messages.
    """
    repo = AsyncGitRepository(Path.cwd())
    return await repo.commit_messages_since(ref=base_branch)


async def _find_related_files(issue_body: str, issue_title: str) -> list[str]:
    """Find files potentially related to an issue.

    Args:
        issue_body: Issue description.
        issue_title: Issue title.

    Returns:
        List of potentially related file paths.
    """
    # Extract file paths mentioned in issue
    related_files = []
    cwd = Path.cwd()

    # Look for common file patterns in title and body
    text = f"{issue_title}\n{issue_body}".lower()

    # Search for file extensions mentioned
    extensions = [".py", ".yaml", ".yml", ".md", ".json", ".toml"]
    for ext in extensions:
        if ext in text:
            # Find files with this extension
            for path in cwd.rglob(f"*{ext}"):
                if path.is_file() and not any(
                    part.startswith(".") or part == "__pycache__" for part in path.parts
                ):
                    related_files.append(str(path.relative_to(cwd)))

    # Look for specific file names or module names mentioned
    words = text.split()
    for word in words:
        # Remove common punctuation
        word = word.strip(".,;:!?()[]{}\"'")
        if "/" in word or "\\" in word:
            # Looks like a path
            path = cwd / word
            if path.exists() and path.is_file():
                related_files.append(str(path.relative_to(cwd)))

    # Remove duplicates and limit
    return list(dict.fromkeys(related_files))[:20]


# =============================================================================
# Context Builder Functions
# =============================================================================


async def implementation_context(
    inputs: dict[str, Any],
    step_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build context for the implementer agent.

    Used by: fly.yaml (implement step)

    The context includes:
    - task_file: Path from inputs or auto-detected
    - task_content: Full content of tasks.md
    - project_structure: Directory tree
    - spec_artifacts: Spec files (spec.md, plan.md, etc.)
    - conventions: CLAUDE.md content

    Args:
        inputs: Workflow inputs (branch_name, task_file, etc.)
        step_results: Results from prior steps (init workspace result)

    Returns:
        ImplementationContext as dict
    """
    task_file = inputs.get("task_file")

    # Read task file content if path provided
    task_content = ""
    if task_file:
        task_path = Path(task_file)
        if task_path.exists():
            task_content = task_path.read_text()

    # Read CLAUDE.md if exists
    conventions = ""
    claude_md = Path("CLAUDE.md")
    if claude_md.exists():
        conventions = claude_md.read_text()

    # Get project structure
    project_structure = await _get_project_structure()

    # Get spec artifacts
    spec_artifacts = await _get_spec_artifacts()

    return {
        "task_file": str(task_file) if task_file else None,
        "task_content": task_content,
        "conventions": conventions,
        "project_structure": project_structure,
        "spec_artifacts": spec_artifacts,
    }


async def implementer_context(
    inputs: dict[str, Any],
    step_results: dict[str, dict[str, Any]],
) -> ImplementerContext:
    """Build ImplementerContext model for the implementer agent.

    Used by: feature.yaml (implement_phase, implement_no_phases steps)

    Converts inline context dict to ImplementerContext Pydantic model.

    Args:
        inputs: Workflow inputs containing:
            - task_file: Path to tasks.md (optional, from inline context)
            - branch_name: Git branch name (from workflow inputs)
            - phase_name: Phase name for phase-mode execution (optional,
              from inline context)
        step_results: Results from prior steps (unused)

    Returns:
        ImplementerContext model instance
    """
    task_file_str = inputs.get("task_file")
    task_file = Path(task_file_str) if task_file_str else None

    branch_name = inputs.get("branch") or inputs.get("branch_name", "")
    phase_name = inputs.get("phase_name")
    cwd_str = inputs.get("cwd")
    cwd = Path(cwd_str) if cwd_str else Path.cwd()

    return ImplementerContext(
        task_file=task_file,
        phase_name=phase_name,
        branch=branch_name,
        cwd=cwd,
        skip_validation=inputs.get("skip_validation", False),
        dry_run=inputs.get("dry_run", False),
    )


async def review_context(
    inputs: dict[str, Any],
    step_results: dict[str, dict[str, Any]],
) -> ReviewContext:
    """Build context for the code reviewer agent.

    Used by: fly.yaml (review step), review.yaml (agent_review step)

    The CodeReviewerAgent expects a ReviewContext model with branch information.
    The agent internally computes diff, changed files, and reads conventions.

    Args:
        inputs: Workflow inputs (branch_name, base_branch, etc.)
        step_results: Results from prior steps (not used currently)

    Returns:
        ReviewContext model instance
    """
    branch_name = inputs.get("branch_name", "")
    base_branch = inputs.get("base_branch", "main")

    # Get current working directory from inputs if provided
    cwd_str = inputs.get("cwd")
    cwd = Path(cwd_str) if cwd_str else Path.cwd()

    # Create ReviewContext model that the agent expects
    return ReviewContext(
        branch=branch_name,
        base_branch=base_branch,
        cwd=cwd,
        file_list=None,  # Review all changed files
    )


async def issue_fix_context(
    inputs: dict[str, Any],
    step_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build context for the issue fixer agent.

    Used by: quick_fix.yaml (fix_issue step)

    The context includes:
    - issue_number: GitHub issue number
    - issue_title: Issue title
    - issue_body: Issue description
    - branch_name: Current branch
    - related_files: Files potentially related to the issue
    - conventions: CLAUDE.md content

    Args:
        inputs: Workflow inputs (issue_number)
        step_results: Results from prior steps (fetch_issue, create_branch)

    Returns:
        IssueFixContext as dict
    """
    # Get issue from fetch_issue step result
    fetch_result = step_results.get("fetch_issue", {}).get("output", {})
    issue = fetch_result.get("issue", {})

    # Read CLAUDE.md
    conventions = ""
    claude_md = Path("CLAUDE.md")
    if claude_md.exists():
        conventions = claude_md.read_text()

    # Get branch from create_branch step result
    branch_result = step_results.get("create_branch", {}).get("output", {})

    # Find related files based on issue content
    issue_title = issue.get("title", "")
    issue_body = issue.get("body", "")
    related_files = await _find_related_files(issue_body, issue_title)

    return {
        "issue_number": issue.get("number") or inputs.get("issue_number"),
        "issue_title": issue_title,
        "issue_body": issue_body,
        "branch_name": branch_result.get("branch_name", ""),
        "related_files": related_files,
        "conventions": conventions,
    }


async def commit_message_context(
    inputs: dict[str, Any],
    step_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build context for the commit message generator.

    Used by: commit_and_push.yaml (generate_message step)

    The context includes:
    - diff: Git diff of all changes (staged + unstaged)
    - file_stats: Insertions/deletions per file
    - recent_commits: Recent commit messages for style reference

    Args:
        inputs: Workflow inputs (message if provided)
        step_results: Results from prior steps

    Returns:
        CommitMessageContext as dict
    """
    # Get diff of all changes (staged + unstaged)
    # We include unstaged changes because git_commit uses add_all=True
    # which stages everything before committing
    staged_diff = await _get_diff(staged=True)
    unstaged_diff = await _get_diff(staged=False)

    # Combine staged and unstaged diffs
    if staged_diff and unstaged_diff:
        diff = f"{staged_diff}\n{unstaged_diff}"
    else:
        diff = staged_diff or unstaged_diff

    # Get file statistics for working tree changes
    file_stats = await _get_file_stats("HEAD")

    # Get recent commits for style reference
    recent_commits = await _get_recent_commits()

    return {
        "diff": diff,
        "file_stats": file_stats,
        "recent_commits": recent_commits,
        "message": inputs.get("message"),  # User-provided message if any
    }


async def pr_body_context(
    inputs: dict[str, Any],
    step_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build context for the PR body generator.

    Used by: create_pr_with_summary.yaml (generate_body step)

    The context includes:
    - commits: All commits on the branch
    - diff_stats: File change statistics
    - task_summary: Summary from task file (if available)
    - validation_results: Validation/test results

    Args:
        inputs: Workflow inputs (base_branch, draft, title)
        step_results: Results from prior steps

    Returns:
        PRBodyContext as dict
    """
    base_branch = inputs.get("base_branch", "main")

    # Get all commits on this branch
    commits = await _get_commits_on_branch(base_branch)

    # Get diff statistics
    diff_stats = await _get_file_stats(base_branch)

    return {
        "commits": commits,
        "diff_stats": diff_stats,
        "task_summary": inputs.get("task_summary"),
        "validation_results": step_results.get("validate_and_fix", {}).get("output"),
    }


async def pr_title_context(
    inputs: dict[str, Any],
    step_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build context for the PR title generator.

    Used by: create_pr_with_summary.yaml (generate_title step)

    The context includes:
    - commits: Commit messages from the branch
    - branch_name: Current branch name
    - task_summary: Summary from task file (if available)
    - diff_overview: Brief overview of changes

    Args:
        inputs: Workflow inputs (title if provided)
        step_results: Results from prior steps

    Returns:
        Dict with title generation context
    """
    base_branch = inputs.get("base_branch", "main")

    # Get commits on this branch
    commits = await _get_commits_on_branch(base_branch)

    # Get current branch name using AsyncGitRepository
    repo = AsyncGitRepository(Path.cwd())
    branch_name = await repo.current_branch()
    if branch_name == "(detached)":
        branch_name = inputs.get("branch_name", "")

    # Get brief diff overview (just file names and stats)
    diff_stats = await _get_file_stats(base_branch)
    if diff_stats:
        total_additions = sum(stats["additions"] for stats in diff_stats.values())
        total_deletions = sum(stats["deletions"] for stats in diff_stats.values())
        file_count = len(diff_stats)
        diff_overview = (
            f"{file_count} files changed, "
            f"+{total_additions} additions, -{total_deletions} deletions"
        )
    else:
        diff_overview = "No changes"

    return {
        "commits": commits,
        "branch_name": branch_name,
        "task_summary": inputs.get("task_summary"),
        "diff_overview": diff_overview,
    }


async def issue_analyzer_context(
    inputs: dict[str, Any],
    step_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build context for the issue analyzer agent.

    Used by: refuel.yaml (analyze_issues step)

    The context includes:
    - issues: List of fetched issues
    - max_parallel: Whether parallel processing is requested

    Args:
        inputs: Workflow inputs (parallel, limit)
        step_results: Results from prior steps (fetch_issues)

    Returns:
        Dict with issues and analysis parameters
    """
    fetch_result = step_results.get("fetch_issues", {}).get("output", {})

    return {
        "issues": fetch_result.get("issues", []),
        "parallel": inputs.get("parallel", True),
        "limit": inputs.get("limit", DEFAULTS.DEFAULT_ISSUE_LIMIT),
    }


def register_all_context_builders(registry: ComponentRegistry) -> None:
    """Register all built-in context builders with the component registry.

    Args:
        registry: Component registry to register context builders with.
    """
    registry.context_builders.register("implementation_context", implementation_context)
    registry.context_builders.register("implementer_context", implementer_context)
    registry.context_builders.register("review_context", review_context)
    registry.context_builders.register("issue_fix_context", issue_fix_context)
    registry.context_builders.register("commit_message_context", commit_message_context)
    registry.context_builders.register("pr_body_context", pr_body_context)
    registry.context_builders.register("pr_title_context", pr_title_context)
    registry.context_builders.register("issue_analyzer_context", issue_analyzer_context)
