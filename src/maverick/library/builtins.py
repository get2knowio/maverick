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

BUILTIN_WORKFLOWS = frozenset(
    {
        "fly-beads",  # Bead-driven development workflow
        "refuel-speckit",  # Generate beads from SpecKit spec
    }
)

# Reusable fragments (FR-009)
BUILTIN_FRAGMENTS = frozenset(
    {
        "validate-and-fix",  # FR-010: Validation-with-retry loop
        "commit-and-push",  # FR-011: Generate commit, commit, push
        "create-pr-with-summary",  # FR-012: Generate PR body, create PR
    }
)


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
# Built-in Workflow Specifications
# =============================================================================


FLY_BEADS_WORKFLOW_INFO = BuiltinWorkflowInfo(
    name="fly-beads",
    description="Bead-driven development workflow",
    inputs=(
        ("epic_id", "string", False, "Epic bead ID (empty to pick any ready bead)"),
        ("max_beads", "integer", False, "Maximum beads to process (default: 30)"),
        ("dry_run", "boolean", False, "Preview mode"),
        ("skip_review", "boolean", False, "Skip code review step"),
    ),
    step_summary=(
        "preflight → bead_loop(select → implement → validate → "
        "review → commit → close) → final_push"
    ),
)

REFUEL_SPECKIT_WORKFLOW_INFO = BuiltinWorkflowInfo(
    name="refuel-speckit",
    description="Generate beads from a SpecKit specification",
    inputs=(
        ("spec_dir", "string", True, "Path to spec directory with tasks.md"),
        ("dry_run", "boolean", False, "Preview mode"),
    ),
    step_summary="preflight → parse_speckit → create_beads → wire_dependencies",
)


# =============================================================================
# Built-in Fragment Specifications (FR-010 to FR-012)
# =============================================================================


VALIDATE_AND_FIX_FRAGMENT_INFO = BuiltinFragmentInfo(
    name="validate-and-fix",
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
    used_by=("fly-beads",),
)

COMMIT_AND_PUSH_FRAGMENT_INFO = BuiltinFragmentInfo(
    name="commit-and-push",
    description="Generate commit message, commit changes, and push",
    inputs=(
        ("message", "string", False, "Commit message (auto-generate if omitted)"),
        ("push", "boolean", False, "Push after commit (default: true)"),
    ),
    used_by=("fly-beads",),
)

CREATE_PR_WITH_SUMMARY_FRAGMENT_INFO = BuiltinFragmentInfo(
    name="create-pr-with-summary",
    description="Generate PR body and create pull request",
    inputs=(
        ("base_branch", "string", False, "PR base branch (default: main)"),
        ("draft", "boolean", False, "Create as draft PR (default: false)"),
        ("title", "string", False, "PR title (auto-generate if omitted)"),
    ),
    used_by=(),
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
            name: Workflow name (e.g., "fly-beads", "refuel-speckit").

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
            name: Fragment name (e.g., "validate-and-fix", "commit-and-push").

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
        "fly-beads": FLY_BEADS_WORKFLOW_INFO,
        "refuel-speckit": REFUEL_SPECKIT_WORKFLOW_INFO,
    }

    # Mapping of fragment names to info objects
    _FRAGMENT_INFO_MAP = {
        "validate-and-fix": VALIDATE_AND_FIX_FRAGMENT_INFO,
        "commit-and-push": COMMIT_AND_PUSH_FRAGMENT_INFO,
        "create-pr-with-summary": CREATE_PR_WITH_SUMMARY_FRAGMENT_INFO,
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
            name: Workflow name (e.g., "fly-beads", "refuel-speckit").

        Returns:
            Parsed WorkflowFile.

        Raises:
            KeyError: If workflow name is not a built-in.
        """
        if name not in BUILTIN_WORKFLOWS:
            raise KeyError(f"Unknown built-in workflow: {name}")

        from importlib.resources import files

        from maverick.dsl.serialization.parser import parse_workflow

        # Convert name to filename (e.g., "fly-beads" -> "fly-beads.yaml")
        filename = f"{name}.yaml"
        yaml_path = files("maverick.library.workflows").joinpath(filename)
        yaml_content = yaml_path.read_text(encoding="utf-8")

        return parse_workflow(yaml_content)

    def get_fragment(self, name: str) -> WorkflowFile:
        """Load a built-in fragment by name.

        Args:
            name: Fragment name (e.g., "validate-and-fix", "commit-and-push").

        Returns:
            Parsed WorkflowFile.

        Raises:
            KeyError: If fragment name is not a built-in.
        """
        if name not in BUILTIN_FRAGMENTS:
            raise KeyError(f"Unknown built-in fragment: {name}")

        from importlib.resources import files

        from maverick.dsl.serialization.parser import parse_workflow

        # Convert name to filename (e.g., "validate-and-fix" -> "validate_and_fix.yaml")
        # Note: Python constants use hyphens (kebab-case), filenames use underscores
        filename = f"{name.replace('-', '_')}.yaml"
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

        # Convert name to filename (e.g., "validate-and-fix" -> "validate_and_fix.yaml")
        filename = f"{name.replace('-', '_')}.yaml"
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
