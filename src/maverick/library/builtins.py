"""Built-in workflow and fragment metadata.

This module provides constants and data structures describing all built-in
workflows and fragments shipped with Maverick.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.dsl.serialization.schema import WorkflowFile

# =============================================================================
# Built-in Workflow Names (Constants)
# =============================================================================

# Core workflows (FR-001)
BUILTIN_WORKFLOWS = frozenset({
    "fly",       # FR-004: Full spec-based development
    "refuel",    # FR-005: Tech-debt resolution
    "review",    # FR-006: Code review orchestration
    "validate",  # FR-007: Validation with optional fixes
    "quick_fix", # FR-008: Quick issue fix
})

# Reusable fragments (FR-009)
BUILTIN_FRAGMENTS = frozenset({
    "validate_and_fix",       # FR-010: Validation-with-retry loop
    "commit_and_push",        # FR-011: Generate commit, commit, push
    "create_pr_with_summary", # FR-012: Generate PR body, create PR
})


# =============================================================================
# Data Transfer Objects
# =============================================================================


@dataclass(frozen=True, slots=True)
class BuiltinWorkflowInfo:
    """Information about a built-in workflow.

    Attributes:
        name: Workflow name.
        description: Human-readable description.
        inputs: Tuple of (name, type, required, description) for each input.
        step_summary: Brief description of workflow stages.
    """

    name: str
    description: str
    inputs: tuple[tuple[str, str, bool, str], ...]  # (name, type, required, desc)
    step_summary: str


@dataclass(frozen=True, slots=True)
class BuiltinFragmentInfo:
    """Information about a built-in fragment.

    Attributes:
        name: Fragment name.
        description: Human-readable description.
        inputs: Tuple of (name, type, required, description) for each input.
        used_by: Names of workflows that use this fragment.
    """

    name: str
    description: str
    inputs: tuple[tuple[str, str, bool, str], ...]
    used_by: tuple[str, ...]


# =============================================================================
# Built-in Workflow Specifications (FR-004 to FR-008)
# =============================================================================


FLY_WORKFLOW_INFO = BuiltinWorkflowInfo(
    name="fly",
    description="Full spec-based development workflow",
    inputs=(
        ("branch_name", "string", True, "Feature branch name"),
        ("task_file", "string", False, "Path to tasks.md (auto-detect if omitted)"),
        ("skip_review", "boolean", False, "Skip code review stage"),
    ),
    step_summary="init → implement → validate/fix loop → commit → review → create_pr",
)

REFUEL_WORKFLOW_INFO = BuiltinWorkflowInfo(
    name="refuel",
    description="Tech-debt resolution workflow",
    inputs=(
        ("label", "string", False, "Issue label to filter (default: tech-debt)"),
        ("limit", "integer", False, "Maximum issues to process (default: 5)"),
        ("parallel", "boolean", False, "Process issues in parallel (default: true)"),
    ),
    step_summary="fetch_issues → for each: branch → fix → validate → commit → pr",
)

REVIEW_WORKFLOW_INFO = BuiltinWorkflowInfo(
    name="review",
    description="Code review orchestration workflow",
    inputs=(
        ("pr_number", "integer", False, "PR number (auto-detect if omitted)"),
        ("base_branch", "string", False, "Base branch for comparison (default: main)"),
    ),
    step_summary="gather_context → run_coderabbit → agent_review → combine_results",
)

VALIDATE_WORKFLOW_INFO = BuiltinWorkflowInfo(
    name="validate",
    description="Validation with optional fixes workflow",
    inputs=(
        ("fix", "boolean", False, "Attempt automatic fixes (default: true)"),
        ("max_attempts", "integer", False, "Maximum fix attempts (default: 3)"),
    ),
    step_summary="run_validation → fix loop (when enabled) → report",
)

QUICK_FIX_WORKFLOW_INFO = BuiltinWorkflowInfo(
    name="quick_fix",
    description="Quick issue fix workflow",
    inputs=(
        ("issue_number", "integer", True, "GitHub issue number"),
    ),
    step_summary="fetch_issue → branch → fix → validate → commit → pr",
)


# =============================================================================
# Built-in Fragment Specifications (FR-010 to FR-012)
# =============================================================================


VALIDATE_AND_FIX_FRAGMENT_INFO = BuiltinFragmentInfo(
    name="validate_and_fix",
    description="Validation-with-retry loop",
    inputs=(
        (
            "stages",
            "array",
            False,
            "Validation stages (default: format, lint, typecheck, test)",
        ),
        ("max_attempts", "integer", False, "Maximum retry attempts (default: 3)"),
        ("fixer_agent", "string", False, "Agent for fixes (default: validation_fixer)"),
    ),
    used_by=("fly", "refuel", "validate"),
)

COMMIT_AND_PUSH_FRAGMENT_INFO = BuiltinFragmentInfo(
    name="commit_and_push",
    description="Generate commit message, commit changes, and push",
    inputs=(
        ("message", "string", False, "Commit message (auto-generate if omitted)"),
        ("push", "boolean", False, "Push after commit (default: true)"),
    ),
    used_by=("fly", "refuel", "quick_fix"),
)

CREATE_PR_WITH_SUMMARY_FRAGMENT_INFO = BuiltinFragmentInfo(
    name="create_pr_with_summary",
    description="Generate PR body and create pull request",
    inputs=(
        ("base_branch", "string", False, "PR base branch (default: main)"),
        ("draft", "boolean", False, "Create as draft PR (default: false)"),
        ("title", "string", False, "PR title (auto-generate if omitted)"),
    ),
    used_by=("fly", "refuel", "quick_fix"),
)


# =============================================================================
# Service Protocol
# =============================================================================


class BuiltinLibrary(ABC):
    """Abstract base for built-in workflow library service.

    Provides access to workflows and fragments packaged with Maverick.
    """

    @abstractmethod
    def list_workflows(self) -> list[BuiltinWorkflowInfo]:
        """List all built-in workflows.

        Returns:
            List of workflow information objects.
        """
        ...

    @abstractmethod
    def list_fragments(self) -> list[BuiltinFragmentInfo]:
        """List all built-in fragments.

        Returns:
            List of fragment information objects.
        """
        ...

    @abstractmethod
    def get_workflow(self, name: str) -> WorkflowFile:
        """Load a built-in workflow by name.

        Args:
            name: Workflow name (e.g., "fly", "refuel").

        Returns:
            Parsed WorkflowFile.

        Raises:
            KeyError: If workflow name is not a built-in.
        """
        ...

    @abstractmethod
    def get_fragment(self, name: str) -> WorkflowFile:
        """Load a built-in fragment by name.

        Args:
            name: Fragment name (e.g., "validate_and_fix").

        Returns:
            Parsed WorkflowFile.

        Raises:
            KeyError: If fragment name is not a built-in.
        """
        ...

    @abstractmethod
    def get_workflow_path(self, name: str) -> Path:
        """Get path to a built-in workflow file.

        Args:
            name: Workflow name.

        Returns:
            Path to YAML file (for copying/inspection).

        Raises:
            KeyError: If workflow name is not a built-in.
        """
        ...

    @abstractmethod
    def get_fragment_path(self, name: str) -> Path:
        """Get path to a built-in fragment file.

        Args:
            name: Fragment name.

        Returns:
            Path to YAML file (for copying/inspection).

        Raises:
            KeyError: If fragment name is not a built-in.
        """
        ...

    @abstractmethod
    def has_workflow(self, name: str) -> bool:
        """Check if a workflow name is a built-in.

        Args:
            name: Workflow name to check.

        Returns:
            True if name is a built-in workflow.
        """
        ...

    @abstractmethod
    def has_fragment(self, name: str) -> bool:
        """Check if a fragment name is a built-in.

        Args:
            name: Fragment name to check.

        Returns:
            True if name is a built-in fragment.
        """
        ...


# =============================================================================
# Default Implementation
# =============================================================================


class DefaultBuiltinLibrary(BuiltinLibrary):
    """Default implementation using importlib.resources.

    Loads workflows and fragments from package resources:
    - maverick.library.workflows/*.yaml
    - maverick.library.fragments/*.yaml
    """

    # Mapping of workflow names to info objects
    _WORKFLOW_INFO_MAP = {
        "fly": FLY_WORKFLOW_INFO,
        "refuel": REFUEL_WORKFLOW_INFO,
        "review": REVIEW_WORKFLOW_INFO,
        "validate": VALIDATE_WORKFLOW_INFO,
        "quick_fix": QUICK_FIX_WORKFLOW_INFO,
    }

    # Mapping of fragment names to info objects
    _FRAGMENT_INFO_MAP = {
        "validate_and_fix": VALIDATE_AND_FIX_FRAGMENT_INFO,
        "commit_and_push": COMMIT_AND_PUSH_FRAGMENT_INFO,
        "create_pr_with_summary": CREATE_PR_WITH_SUMMARY_FRAGMENT_INFO,
    }

    def list_workflows(self) -> list[BuiltinWorkflowInfo]:
        """List all built-in workflows.

        Returns:
            List of workflow information objects.
        """
        return list(self._WORKFLOW_INFO_MAP.values())

    def list_fragments(self) -> list[BuiltinFragmentInfo]:
        """List all built-in fragments.

        Returns:
            List of fragment information objects.
        """
        return list(self._FRAGMENT_INFO_MAP.values())

    def get_workflow(self, name: str) -> WorkflowFile:
        """Load a built-in workflow by name.

        Args:
            name: Workflow name (e.g., "fly", "refuel", "quick_fix").
                  Can use underscores (Python-style) which will be converted
                  to hyphens for YAML name lookup.

        Returns:
            Parsed WorkflowFile.

        Raises:
            KeyError: If workflow name is not a built-in.
        """
        if name not in BUILTIN_WORKFLOWS:
            raise KeyError(f"Unknown built-in workflow: {name}")

        from importlib.resources import files

        from maverick.dsl.serialization.parser import parse_workflow

        # Convert name to filename (e.g., "quick_fix" -> "quick_fix.yaml")
        # Note: filenames use underscores, YAML names use hyphens
        filename = f"{name}.yaml"
        yaml_path = files("maverick.library.workflows").joinpath(filename)
        yaml_content = yaml_path.read_text(encoding="utf-8")

        return parse_workflow(yaml_content)

    def get_fragment(self, name: str) -> WorkflowFile:
        """Load a built-in fragment by name.

        Args:
            name: Fragment name (e.g., "validate_and_fix", "commit_and_push").
                  Can use underscores (Python-style) which will be converted
                  to hyphens for YAML name lookup.

        Returns:
            Parsed WorkflowFile.

        Raises:
            KeyError: If fragment name is not a built-in.
        """
        if name not in BUILTIN_FRAGMENTS:
            raise KeyError(f"Unknown built-in fragment: {name}")

        from importlib.resources import files

        from maverick.dsl.serialization.parser import parse_workflow

        # Convert name to filename (e.g., "validate_and_fix" -> "validate_and_fix.yaml")
        # Note: filenames use underscores, YAML names use hyphens
        filename = f"{name}.yaml"
        yaml_path = files("maverick.library.fragments").joinpath(filename)
        yaml_content = yaml_path.read_text(encoding="utf-8")

        return parse_workflow(yaml_content)

    def get_workflow_path(self, name: str) -> Path:
        """Get path to a built-in workflow file.

        Args:
            name: Workflow name.

        Returns:
            Path to YAML file (for copying/inspection).

        Raises:
            KeyError: If workflow name is not a built-in.
        """
        if name not in BUILTIN_WORKFLOWS:
            raise KeyError(f"Unknown built-in workflow: {name}")

        from importlib.resources import files

        filename = f"{name}.yaml"
        yaml_path = files("maverick.library.workflows").joinpath(filename)

        # Convert to Path object (importlib.resources returns a Traversable)
        return Path(str(yaml_path))

    def get_fragment_path(self, name: str) -> Path:
        """Get path to a built-in fragment file.

        Args:
            name: Fragment name.

        Returns:
            Path to YAML file (for copying/inspection).

        Raises:
            KeyError: If fragment name is not a built-in.
        """
        if name not in BUILTIN_FRAGMENTS:
            raise KeyError(f"Unknown built-in fragment: {name}")

        from importlib.resources import files

        filename = f"{name}.yaml"
        yaml_path = files("maverick.library.fragments").joinpath(filename)

        # Convert to Path object (importlib.resources returns a Traversable)
        return Path(str(yaml_path))

    def has_workflow(self, name: str) -> bool:
        """Check if a workflow name is a built-in.

        Args:
            name: Workflow name to check.

        Returns:
            True if name is a built-in workflow.
        """
        return name in BUILTIN_WORKFLOWS

    def has_fragment(self, name: str) -> bool:
        """Check if a fragment name is a built-in.

        Args:
            name: Fragment name to check.

        Returns:
            True if name is a built-in fragment.
        """
        return name in BUILTIN_FRAGMENTS


# =============================================================================
# Factory Function
# =============================================================================


def create_builtin_library() -> BuiltinLibrary:
    """Create a built-in library service instance.

    Returns:
        Configured BuiltinLibrary instance.
    """
    return DefaultBuiltinLibrary()
