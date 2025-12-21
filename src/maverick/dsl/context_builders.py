"""Context builders for agent and generate steps.

Context builders are async functions that construct context dictionaries
for agents and generators. They gather necessary data (file reads, git
commands, etc.) and return a dict suitable for the target component.

Each context builder receives workflow inputs and prior step results,
and returns a dictionary containing all the information needed by the
target agent or generator.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from maverick.dsl.serialization.registry import ComponentRegistry

logger = logging.getLogger(__name__)


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


async def _run_git_command(*args: str) -> tuple[str, str, int]:
    """Run a git command and return stdout, stderr, returncode.

    Args:
        *args: Git command arguments (without 'git' prefix).

    Returns:
        Tuple of (stdout, stderr, returncode).
    """
    process = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await process.communicate()
    return (
        stdout_bytes.decode().strip(),
        stderr_bytes.decode().strip(),
        process.returncode or 0,
    )


async def _get_project_structure(max_depth: int = 3) -> str:
    """Get a directory tree structure for the project.

    Args:
        max_depth: Maximum depth to traverse.

    Returns:
        String representation of the directory tree.
    """
    cwd = Path.cwd()

    # Try using tree command if available
    ignore_pattern = (
        "__pycache__|*.pyc|.git|.venv|venv|node_modules|"
        ".pytest_cache|.ruff_cache"
    )
    process = await asyncio.create_subprocess_exec(
        "tree",
        "-L", str(max_depth),
        "-I", ignore_pattern,
        "--dirsfirst",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await process.communicate()

    if process.returncode == 0:
        return stdout_bytes.decode().strip()

    # Fallback: simple directory listing
    try:
        result = []
        result.append(str(cwd.name) + "/")

        def add_tree(path: Path, prefix: str = "", depth: int = 0) -> None:
            if depth >= max_depth:
                return

            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            # Filter out common ignore patterns
            items = [
                item for item in items
                if item.name not in {
                    "__pycache__", ".git", ".venv", "venv",
                    "node_modules", ".pytest_cache", ".ruff_cache",
                    ".mypy_cache", "dist", "build", "*.egg-info"
                } and not item.name.endswith(".pyc")
            ]

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                current_prefix = "└── " if is_last else "├── "
                next_prefix = "    " if is_last else "│   "

                if item.is_dir():
                    result.append(f"{prefix}{current_prefix}{item.name}/")
                    add_tree(item, prefix + next_prefix, depth + 1)
                else:
                    result.append(f"{prefix}{current_prefix}{item.name}")

        add_tree(cwd)
        return "\n".join(result)

    except Exception as e:
        logger.debug(f"Failed to generate project structure: {e}")
        return ""


async def _get_spec_artifacts() -> dict[str, str]:
    """Read spec artifacts from the current directory or spec directory.

    Returns:
        Dict mapping artifact names to their content.
    """
    artifacts: dict[str, str] = {}
    cwd = Path.cwd()

    # Look for spec directory based on branch name
    stdout, _, returncode = await _run_git_command(
        "rev-parse", "--abbrev-ref", "HEAD"
    )
    if returncode == 0:
        branch_name = stdout
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
                            logger.debug(f"Failed to read {spec_file}: {e}")

    return artifacts


async def _get_diff(ref: str = "HEAD", staged: bool = False) -> str:
    """Get git diff against a reference.

    Args:
        ref: Git reference to diff against.
        staged: If True, get staged changes only.

    Returns:
        Git diff output.
    """
    args = ["diff"]
    if staged:
        args.append("--staged")
    else:
        args.append(ref)

    stdout, _, returncode = await _run_git_command(*args)
    return stdout if returncode == 0 else ""


async def _get_changed_files(ref: str = "HEAD") -> list[str]:
    """Get list of changed files against a reference.

    Args:
        ref: Git reference to diff against.

    Returns:
        List of changed file paths.
    """
    stdout, _, returncode = await _run_git_command(
        "diff", "--name-only", ref
    )
    if returncode != 0 or not stdout:
        return []
    return [line.strip() for line in stdout.split("\n") if line.strip()]


async def _get_file_stats(ref: str = "HEAD") -> dict[str, dict[str, int]]:
    """Get file statistics (additions/deletions) against a reference.

    Args:
        ref: Git reference to diff against.

    Returns:
        Dict mapping file paths to stats with 'additions' and 'deletions' keys.
    """
    stdout, _, returncode = await _run_git_command(
        "diff", "--numstat", ref
    )
    if returncode != 0 or not stdout:
        return {}

    stats: dict[str, dict[str, int]] = {}
    for line in stdout.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            added = int(parts[0]) if parts[0] != "-" else 0
            removed = int(parts[1]) if parts[1] != "-" else 0
            file_path = parts[2]
            stats[file_path] = {"additions": added, "deletions": removed}

    return stats


async def _get_recent_commits(limit: int = 10) -> list[str]:
    """Get recent commit messages.

    Args:
        limit: Maximum number of commits to retrieve.

    Returns:
        List of commit messages.
    """
    stdout, _, returncode = await _run_git_command(
        "log", f"-{limit}", "--pretty=format:%s"
    )
    if returncode != 0 or not stdout:
        return []
    return [line.strip() for line in stdout.split("\n") if line.strip()]


async def _get_commits_on_branch(base_branch: str = "main") -> list[str]:
    """Get all commit messages on the current branch since base.

    Args:
        base_branch: Base branch to compare against.

    Returns:
        List of commit messages.
    """
    stdout, _, returncode = await _run_git_command(
        "log", f"{base_branch}..HEAD", "--pretty=format:%s"
    )
    if returncode != 0 or not stdout:
        return []
    return [line.strip() for line in stdout.split("\n") if line.strip()]


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
                    part.startswith(".") or part == "__pycache__"
                    for part in path.parts
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
    project_structure = await _get_project_structure(max_depth=3)

    # Get spec artifacts
    spec_artifacts = await _get_spec_artifacts()

    return {
        "task_file": str(task_file) if task_file else None,
        "task_content": task_content,
        "conventions": conventions,
        "project_structure": project_structure,
        "spec_artifacts": spec_artifacts,
    }


async def review_context(
    inputs: dict[str, Any],
    step_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build context for the code reviewer agent.

    Used by: fly.yaml (review step), review.yaml (agent_review step)

    The context includes:
    - diff: Git diff against base branch
    - changed_files: List of changed file paths
    - conventions: CLAUDE.md content
    - base_branch: Target branch
    - pr_metadata: PR info if available
    - coderabbit_findings: CodeRabbit results if available

    Args:
        inputs: Workflow inputs (base_branch, pr_number, etc.)
        step_results: Results from prior steps (gather_context, run_coderabbit)

    Returns:
        ReviewContext as dict
    """
    base_branch = inputs.get("base_branch", "main")

    # Read CLAUDE.md
    conventions = ""
    claude_md = Path("CLAUDE.md")
    if claude_md.exists():
        conventions = claude_md.read_text()

    # Get coderabbit findings from prior step if available
    coderabbit_result = step_results.get("run_coderabbit", {}).get("output", {})
    coderabbit_findings = coderabbit_result.get("findings", [])

    # Get PR metadata from prior step if available
    gather_result = step_results.get("gather_context", {}).get("output", {})
    pr_metadata = gather_result.get("pr_metadata")

    # Get diff and changed files against base branch
    diff = await _get_diff(base_branch)
    changed_files = await _get_changed_files(base_branch)

    return {
        "diff": diff,
        "changed_files": changed_files,
        "conventions": conventions,
        "base_branch": base_branch,
        "pr_metadata": pr_metadata,
        "coderabbit_findings": coderabbit_findings,
    }


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
    - diff: Git diff of staged changes
    - file_stats: Insertions/deletions per file
    - recent_commits: Recent commit messages for style reference

    Args:
        inputs: Workflow inputs (message if provided)
        step_results: Results from prior steps

    Returns:
        CommitMessageContext as dict
    """
    # Get diff of staged changes
    diff = await _get_diff(staged=True)

    # Get file statistics for staged changes
    file_stats = await _get_file_stats("HEAD")

    # Get recent commits for style reference
    recent_commits = await _get_recent_commits(limit=10)

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

    # Get current branch name
    stdout, _, returncode = await _run_git_command(
        "rev-parse", "--abbrev-ref", "HEAD"
    )
    branch_name = stdout if returncode == 0 else inputs.get("branch_name", "")

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
        "limit": inputs.get("limit", 5),
    }


def register_all_context_builders(registry: ComponentRegistry) -> None:
    """Register all built-in context builders with the component registry.

    Args:
        registry: Component registry to register context builders with.
    """
    registry.context_builders.register("implementation_context", implementation_context)
    registry.context_builders.register("review_context", review_context)
    registry.context_builders.register("issue_fix_context", issue_fix_context)
    registry.context_builders.register("commit_message_context", commit_message_context)
    registry.context_builders.register("pr_body_context", pr_body_context)
    registry.context_builders.register("pr_title_context", pr_title_context)
    registry.context_builders.register("issue_analyzer_context", issue_analyzer_context)
