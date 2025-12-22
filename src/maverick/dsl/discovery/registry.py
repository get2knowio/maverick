"""Default workflow discovery implementation.

This module provides the default implementation of workflow discovery
that scans multiple locations (builtin, user, project) and applies
precedence rules.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.dsl.serialization.schema import WorkflowFile

from maverick.dsl.discovery.exceptions import (
    WorkflowConflictError,
    WorkflowDiscoveryError,
)
from maverick.dsl.discovery.models import (
    DiscoveredWorkflow,
    DiscoveryResult,
    SkippedWorkflow,
    WorkflowMetadata,
    WorkflowSource,
)

__all__ = [
    "WorkflowLocator",
    "WorkflowLoader",
    "DefaultWorkflowDiscovery",
    "create_discovery",
]


# =============================================================================
# Service Implementations
# =============================================================================


class WorkflowLocator:
    """Default implementation for finding workflow files.

    Scans a directory for YAML workflow files (*.yaml, *.yml).
    """

    def scan(self, directory: Path) -> list[Path]:
        """Find all workflow files in directory.

        Args:
            directory: Directory to scan.

        Returns:
            List of paths to workflow YAML files (sorted).
        """
        if not directory.exists() or not directory.is_dir():
            return []

        # Find all .yaml and .yml files recursively
        yaml_files = list(directory.glob("**/*.yaml"))
        yaml_files.extend(directory.glob("**/*.yml"))

        # Return sorted list of absolute paths
        return sorted(p.resolve() for p in yaml_files)


class WorkflowLoader:
    """Default implementation for parsing workflow files.

    Uses the existing parser from dsl.serialization.parser.
    """

    def load_metadata(self, path: Path) -> WorkflowMetadata:
        """Load workflow metadata without full validation.

        Args:
            path: Path to workflow file.

        Returns:
            Parsed metadata.

        Raises:
            WorkflowDiscoveryError: If file cannot be parsed.
        """
        from maverick.dsl.serialization.parser import parse_workflow

        try:
            # Parse the workflow with validate_only mode
            workflow = parse_workflow(path.read_text(), validate_only=True)

            # Determine source from path
            source = self._infer_source(path)

            # Extract metadata
            return WorkflowMetadata(
                name=workflow.name,
                version=workflow.version,
                description=workflow.description,
                input_names=tuple(workflow.inputs.keys()),
                step_count=len(workflow.steps),
                file_path=path.resolve(),
                source=source,
            )
        except Exception as e:
            msg = f"Failed to load metadata from {path}: {e}"
            raise WorkflowDiscoveryError(msg) from e

    def load_full(self, path: Path) -> WorkflowFile:
        """Load and fully validate workflow file.

        Args:
            path: Path to workflow file.

        Returns:
            Fully validated WorkflowFile.

        Raises:
            WorkflowDiscoveryError: If validation fails.
        """
        from maverick.dsl.serialization.parser import parse_workflow

        try:
            return parse_workflow(path.read_text(), validate_only=True)
        except Exception as e:
            msg = f"Failed to load workflow from {path}: {e}"
            raise WorkflowDiscoveryError(msg) from e

    def _infer_source(self, path: Path) -> str:
        """Infer workflow source from path.

        Args:
            path: Path to workflow file.

        Returns:
            WorkflowSource value (builtin/user/project).
        """
        path_str = str(path.resolve())

        # Check if it's in the maverick package (builtin)
        if "maverick/library" in path_str or "maverick.library" in path_str:
            return WorkflowSource.BUILTIN.value

        # Check if it's in user config directory
        user_config = Path.home() / ".config" / "maverick"
        if path.resolve().is_relative_to(user_config):
            return WorkflowSource.USER.value

        # Otherwise assume it's project-level
        return WorkflowSource.PROJECT.value


# =============================================================================
# Discovery Registry
# =============================================================================


class DefaultWorkflowDiscovery:
    """Default implementation of workflow discovery.

    Scans multiple locations (builtin, user, project) and applies
    precedence rules to resolve workflows and fragments.

    Precedence order: PROJECT > USER > BUILTIN (higher overrides lower)

    This applies to both workflows and fragments:
    - Workflows: .maverick/workflows/*.yaml > ~/.config/maverick/workflows/*.yaml
      > built-in
    - Fragments: .maverick/workflows/fragments/*.yaml
      > ~/.config/maverick/workflows/fragments/*.yaml > built-in

    Fragment Override Example:
        To customize the validate-and-fix fragment, create:
        .maverick/workflows/fragments/validate_and_fix.yaml

        This will override the built-in fragment for all workflows that
        reference it.
    """

    def __init__(
        self,
        locator: WorkflowLocator | None = None,
        loader: WorkflowLoader | None = None,
    ) -> None:
        """Initialize discovery service.

        Args:
            locator: Custom locator implementation (uses default if None).
            loader: Custom loader implementation (uses default if None).
        """
        self._locator = locator or WorkflowLocator()
        self._loader = loader or WorkflowLoader()

    def discover(
        self,
        project_dir: Path | None = None,
        user_dir: Path | None = None,
        include_builtin: bool = True,
    ) -> DiscoveryResult:
        """Discover workflows from all configured locations.

        Args:
            project_dir: Override project workflows directory.
            user_dir: Override user workflows directory.
            include_builtin: Whether to include built-in workflows.

        Returns:
            DiscoveryResult with all discovered workflows.

        Raises:
            WorkflowConflictError: If same-name conflict at same precedence.
        """
        start_time = time.perf_counter()

        # Determine locations to scan
        locations_to_scan: list[tuple[Path, str]] = []

        if include_builtin:
            builtin_path = self.get_builtin_path()
            locations_to_scan.append((builtin_path, WorkflowSource.BUILTIN.value))

        user_path = user_dir or self.get_user_path()
        if user_path.exists():
            locations_to_scan.append((user_path, WorkflowSource.USER.value))

        project_path = project_dir or self.get_project_path()
        if project_path.exists():
            locations_to_scan.append((project_path, WorkflowSource.PROJECT.value))

        # Scan each location
        all_workflows: dict[str, list[tuple[Path, str]]] = {}
        all_fragments: dict[str, list[tuple[Path, str]]] = {}
        skipped: list[SkippedWorkflow] = []
        locations_scanned: list[Path] = []

        for location, source in locations_to_scan:
            locations_scanned.append(location)

            # Scan for files
            files = self._locator.scan(location)

            for file_path in files:
                try:
                    # Load workflow
                    workflow = self._loader.load_full(file_path)

                    # Determine if it's a workflow or fragment based on path
                    is_fragment = self._is_fragment(file_path)

                    # Add to appropriate collection
                    if is_fragment:
                        if workflow.name not in all_fragments:
                            all_fragments[workflow.name] = []
                        all_fragments[workflow.name].append((file_path, source))
                    else:
                        if workflow.name not in all_workflows:
                            all_workflows[workflow.name] = []
                        all_workflows[workflow.name].append((file_path, source))

                except Exception as e:
                    # Skip invalid files
                    error_type = self._classify_error(e)
                    skipped.append(
                        SkippedWorkflow(
                            file_path=file_path,
                            error_message=str(e),
                            error_type=error_type,
                            line_number=None,
                        )
                    )

        # Apply precedence and detect conflicts
        workflows = self._apply_precedence(all_workflows)
        fragments = self._apply_precedence(all_fragments)

        # Calculate discovery time
        end_time = time.perf_counter()
        discovery_time_ms = (end_time - start_time) * 1000

        return DiscoveryResult(
            workflows=tuple(workflows),
            fragments=tuple(fragments),
            skipped=tuple(skipped),
            locations_scanned=tuple(locations_scanned),
            discovery_time_ms=discovery_time_ms,
        )

    def get_builtin_path(self) -> Path:
        """Get path to built-in workflows package resource.

        Returns:
            Path to built-in workflows directory.
        """
        from importlib.resources import files

        # Get the library package path
        library_path = files("maverick.library")

        # Convert to Path (importlib.resources returns Traversable)
        if hasattr(library_path, "__fspath__"):
            return Path(library_path.__fspath__())
        else:
            # Fallback for Python 3.10
            return Path(str(library_path))

    def get_user_path(self) -> Path:
        """Get path to user workflows directory.

        Returns:
            Path to ~/.config/maverick/workflows/
        """
        return Path.home() / ".config" / "maverick" / "workflows"

    def get_project_path(self, project_root: Path | None = None) -> Path:
        """Get path to project workflows directory.

        Args:
            project_root: Project root directory (defaults to cwd).

        Returns:
            Path to .maverick/workflows/
        """
        root = project_root or Path.cwd()
        return root / ".maverick" / "workflows"

    def get_project_fragments_path(self, project_root: Path | None = None) -> Path:
        """Get path to project fragments directory.

        Fragments override built-in fragments following precedence:
        project > user > built-in

        Args:
            project_root: Project root directory (defaults to cwd).

        Returns:
            Path to .maverick/workflows/fragments/
        """
        return self.get_project_path(project_root) / "fragments"

    def get_user_fragments_path(self) -> Path:
        """Get path to user fragments directory.

        Fragments override built-in fragments following precedence:
        project > user > built-in

        Returns:
            Path to ~/.config/maverick/workflows/fragments/
        """
        return self.get_user_path() / "fragments"

    def get_builtin_fragments_path(self) -> Path:
        """Get path to built-in fragments directory.

        Returns:
            Path to built-in fragments directory in package resources.
        """
        return self.get_builtin_path() / "fragments"

    def _is_fragment(self, file_path: Path) -> bool:
        """Determine if a workflow file is a fragment.

        Fragments are reusable sub-workflows that can be invoked by other workflows.
        They follow the same precedence rules as workflows:
        - PROJECT (.maverick/workflows/fragments/) overrides
        - USER (~/.config/maverick/workflows/fragments/) overrides
        - BUILTIN (maverick.library.fragments/)

        To override a built-in fragment, create a file with the same name in your
        project or user fragments directory.

        Args:
            file_path: Path to workflow file.

        Returns:
            True if the file is in a fragments/ directory.
        """
        return "fragments" in file_path.parts

    def _classify_error(self, error: Exception) -> str:
        """Classify an error into a category.

        Args:
            error: The exception that occurred.

        Returns:
            Error category (parse_error, schema_error, io_error).
        """
        error_name = type(error).__name__

        if "Parse" in error_name or "YAML" in error_name:
            return "parse_error"
        elif "Validation" in error_name or "Schema" in error_name:
            return "schema_error"
        elif "IO" in error_name or "File" in error_name or "Permission" in error_name:
            return "io_error"
        else:
            return "parse_error"  # Default

    def get_fragment_override_info(self, fragment_name: str) -> dict[str, Path | None]:
        """Get information about fragment override locations.

        This is useful for debugging and understanding which fragment will be used.

        Args:
            fragment_name: Fragment name to check (e.g., "validate-and-fix").

        Returns:
            Dict with keys: 'project', 'user', 'builtin', 'active'
            - project: Path to project fragment if it exists
            - user: Path to user fragment if it exists
            - builtin: Path to builtin fragment if it exists
            - active: Path to the fragment that will be used (highest precedence)
        """
        # Convert name to filename
        filename = f"{fragment_name.replace('-', '_')}.yaml"

        # Check each location
        project_path = self.get_project_fragments_path() / filename
        user_path = self.get_user_fragments_path() / filename
        builtin_path = self.get_builtin_fragments_path() / filename

        result: dict[str, Path | None] = {
            "project": project_path if project_path.exists() else None,
            "user": user_path if user_path.exists() else None,
            "builtin": builtin_path if builtin_path.exists() else None,
            "active": None,
        }

        # Determine active (highest precedence)
        if result["project"]:
            result["active"] = result["project"]
        elif result["user"]:
            result["active"] = result["user"]
        elif result["builtin"]:
            result["active"] = result["builtin"]

        return result

    def _apply_precedence(
        self,
        workflows_by_name: dict[str, list[tuple[Path, str]]],
    ) -> list[DiscoveredWorkflow]:
        """Apply precedence rules and detect conflicts.

        For both workflows and fragments, the same precedence applies:
        PROJECT > USER > BUILTIN

        When multiple definitions exist for the same name, the highest
        precedence one is selected, and lower precedence ones are recorded
        in the 'overrides' field of the DiscoveredWorkflow.

        Args:
            workflows_by_name: Map of workflow name to list of (path, source).

        Returns:
            List of DiscoveredWorkflow with precedence applied.

        Raises:
            WorkflowConflictError: If same-name conflict at same precedence.
        """
        from maverick.dsl.serialization.parser import parse_workflow

        # Define precedence order
        precedence_order = [
            WorkflowSource.PROJECT.value,
            WorkflowSource.USER.value,
            WorkflowSource.BUILTIN.value,
        ]

        result: list[DiscoveredWorkflow] = []

        for name, entries in workflows_by_name.items():
            # Group by source
            by_source: dict[str, list[Path]] = {}
            for path, source in entries:
                if source not in by_source:
                    by_source[source] = []
                by_source[source].append(path)

            # Check for conflicts at same precedence level
            for source, paths in by_source.items():
                if len(paths) > 1:
                    raise WorkflowConflictError(
                        name=name,
                        source=source,
                        conflicting_paths=tuple(paths),
                    )

            # Find highest precedence workflow
            selected_path: Path | None = None
            selected_source: str | None = None
            overridden_paths: list[Path] = []

            for source in precedence_order:
                if source in by_source:
                    if selected_path is None:
                        # This is the highest precedence
                        selected_path = by_source[source][0]
                        selected_source = source
                    else:
                        # This is overridden
                        overridden_paths.extend(by_source[source])

            # Load the selected workflow
            if selected_path and selected_source:
                workflow = parse_workflow(selected_path.read_text(), validate_only=True)
                result.append(
                    DiscoveredWorkflow(
                        workflow=workflow,
                        file_path=selected_path,
                        source=selected_source,
                        overrides=tuple(overridden_paths),
                    )
                )

        return result


# =============================================================================
# Factory Functions
# =============================================================================


def create_discovery(
    locator: WorkflowLocator | None = None,
    loader: WorkflowLoader | None = None,
) -> DefaultWorkflowDiscovery:
    """Create a workflow discovery service.

    Args:
        locator: Custom locator implementation (uses default if None).
        loader: Custom loader implementation (uses default if None).

    Returns:
        Configured DefaultWorkflowDiscovery instance.
    """
    return DefaultWorkflowDiscovery(locator=locator, loader=loader)
