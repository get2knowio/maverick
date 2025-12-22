"""Utility modules for Maverick workflows and agents.

This package contains shared utilities for:
- Git operations (git.py)
- GitHub API interactions (github.py)
- Code validation (validation.py)
- Task file parsing (task_parser.py)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__: list[str] = []

# Git utilities
try:
    from maverick.utils.git import (
        create_commit,
        get_current_branch,
        get_diff_stats,
        get_head_sha,
        has_uncommitted_changes,
        stash_changes,
        unstash_changes,
    )

    __all__.extend(
        [
            "create_commit",
            "get_current_branch",
            "get_diff_stats",
            "get_head_sha",
            "has_uncommitted_changes",
            "stash_changes",
            "unstash_changes",
        ]
    )
except ImportError:
    logger.debug("Git utilities not yet available")

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
    logger.debug("GitHub utilities not yet available")

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
    logger.debug("Validation utilities not yet available")

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
    logger.debug("Task parser utilities not yet available")

# Git operations (synchronous wrapper)
try:
    from maverick.utils.git_operations import (
        CommitInfo,
        DiffStats,
        GitOperations,
        GitStatus,
    )

    __all__.extend(
        [
            "CommitInfo",
            "DiffStats",
            "GitOperations",
            "GitStatus",
        ]
    )
except ImportError:
    logger.debug("Git operations utilities not yet available")

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
    logger.debug("Context builder utilities not yet available")

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
    logger.debug("Security utilities not yet available")
