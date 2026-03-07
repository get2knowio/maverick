"""Utility modules for Maverick workflows and agents.

This package contains shared utilities for:
- GitHub API interactions (github.py, github_client.py)
- Code validation (validation.py)
- Task file parsing (task_parser.py)
- Security utilities (security.py)

For git operations, use maverick.git.GitRepository (sync) or
maverick.git.AsyncGitRepository (async).
"""

from __future__ import annotations

__all__: list[str] = []

# GitHub utilities
try:
    from maverick.utils.github import (
        add_issue_comment,
        check_gh_auth,
        fetch_issue,
        list_issues,
    )

    __all__.extend(
        [
            "add_issue_comment",
            "check_gh_auth",
            "fetch_issue",
            "list_issues",
        ]
    )
except ImportError:
    pass

# Validation utilities
try:
    from maverick.utils.validation import (
        check_validation_passed,
        full_validate,
        quick_validate,
        run_validation_pipeline,
        run_validation_step,
    )

    __all__.extend(
        [
            "check_validation_passed",
            "full_validate",
            "quick_validate",
            "run_validation_pipeline",
            "run_validation_step",
        ]
    )
except ImportError:
    pass

# Task parser utilities
try:
    from maverick.utils.task_parser import (
        format_task_checkbox,
        get_completed_count,
        get_pending_count,
        parse_tasks_file,
        parse_tasks_md,
    )

    __all__.extend(
        [
            "format_task_checkbox",
            "get_completed_count",
            "get_pending_count",
            "parse_tasks_file",
            "parse_tasks_md",
        ]
    )
except ImportError:
    pass

# Context builder utilities
try:
    from maverick.utils.context import (
        build_fix_context,
        build_implementation_context,
        build_issue_context,
        build_review_context,
        detect_secrets,
        estimate_tokens,
        extract_file_paths,
        fit_to_budget,
        truncate_file,
        truncate_line,
    )

    __all__.extend(
        [
            "build_fix_context",
            "build_implementation_context",
            "build_issue_context",
            "build_review_context",
            "detect_secrets",
            "estimate_tokens",
            "extract_file_paths",
            "fit_to_budget",
            "truncate_file",
            "truncate_line",
        ]
    )
except ImportError:
    pass

# Security utilities
try:
    from maverick.utils.security import is_potentially_secret, scrub_secrets

    __all__.extend(
        [
            "is_potentially_secret",
            "scrub_secrets",
        ]
    )
except ImportError:
    pass

# GitHub client (PyGithub-based)
try:
    from maverick.utils.github_client import (
        GitHubClient,
        get_github_client,
        get_github_token,
    )

    __all__.extend(
        [
            "GitHubClient",
            "get_github_client",
            "get_github_token",
        ]
    )
except ImportError:
    pass

# Atomic file write utilities
try:
    from maverick.utils.atomic import (
        atomic_write_json,
        atomic_write_text,
    )

    __all__.extend(
        [
            "atomic_write_json",
            "atomic_write_text",
        ]
    )
except ImportError:
    pass

# Async utilities (anyio-based)
try:
    from maverick.utils.async_utils import (
        ParallelExecutionError,
        run_parallel,
        run_parallel_with_concurrency,
    )

    __all__.extend(
        [
            "ParallelExecutionError",
            "run_parallel",
            "run_parallel_with_concurrency",
        ]
    )
except ImportError:
    pass
