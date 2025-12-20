"""Workflow file loading and parsing for discovery.

This module implements the WorkflowLoader protocol for parsing workflow files.
It provides both lightweight metadata extraction and full validation.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml  # type: ignore[import-untyped]

from maverick.dsl.discovery.exceptions import WorkflowDiscoveryError
from maverick.dsl.discovery.models import WorkflowMetadata, WorkflowSource
from maverick.dsl.serialization.parser import parse_workflow

if TYPE_CHECKING:
    from maverick.dsl.serialization.schema import WorkflowFile

__all__ = ["WorkflowLoader"]


class WorkflowLoader:
    """Loader for parsing workflow files with metadata extraction.

    Implements the WorkflowLoader protocol from the discovery contract.
    Provides both lightweight metadata extraction and full validation.

    Examples:
        >>> loader = WorkflowLoader()
        >>> metadata = loader.load_metadata(
        ...     Path("workflow.yaml"),
        ...     source=WorkflowSource.BUILTIN
        ... )
        >>> print(metadata.name)
        'fly'
        >>> workflow = loader.load_full(Path("workflow.yaml"))
        >>> print(workflow.version)
        '1.0'
    """

    def load_metadata(
        self, path: Path, source: WorkflowSource | str
    ) -> WorkflowMetadata:
        """Load workflow metadata without full validation.

        Reads just the workflow file header to extract lightweight metadata
        for listing and display operations. This is faster than full
        validation and allows discovery to continue even if some workflows
        have validation errors.

        Args:
            path: Path to workflow file.
            source: Origin location (WorkflowSource enum value or string).

        Returns:
            Parsed metadata.

        Raises:
            WorkflowDiscoveryError: If file cannot be read or parsed.

        Examples:
            >>> loader = WorkflowLoader()
            >>> metadata = loader.load_metadata(
            ...     Path("workflow.yaml"),
            ...     source=WorkflowSource.BUILTIN
            ... )
            >>> metadata.name
            'fly'
            >>> metadata.step_count
            5
        """
        # Convert source to string if it's an enum
        source_str = source.value if isinstance(source, WorkflowSource) else source

        try:
            # Read file contents
            yaml_content = path.read_text(encoding="utf-8")
        except FileNotFoundError as e:
            raise WorkflowDiscoveryError(
                f"Workflow file not found: {path}"
            ) from e
        except PermissionError as e:
            raise WorkflowDiscoveryError(
                f"Permission denied reading workflow file: {path}"
            ) from e
        except OSError as e:
            raise WorkflowDiscoveryError(
                f"Error reading workflow file {path}: {e}"
            ) from e

        try:
            # Parse YAML to dict
            data: dict[str, Any] = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            # Extract line number if available
            line_number = None
            if hasattr(e, "problem_mark"):
                line_number = e.problem_mark.line + 1

            error_msg = f"YAML parse error in {path}: {e}"
            if line_number:
                error_msg += f" (line {line_number})"
            raise WorkflowDiscoveryError(error_msg) from e

        # Ensure we have a dict
        if not isinstance(data, dict):
            raise WorkflowDiscoveryError(
                f"Workflow file {path} must be an object (dict), "
                f"got {type(data).__name__}"
            )

        # Extract required fields with validation
        try:
            name = data.get("name")
            if not name or not isinstance(name, str):
                raise WorkflowDiscoveryError(
                    f"Workflow file {path} missing or invalid 'name' field"
                )

            version = data.get("version")
            if not version or not isinstance(version, str):
                raise WorkflowDiscoveryError(
                    f"Workflow file {path} missing or invalid 'version' field"
                )

            description = data.get("description", "")
            if not isinstance(description, str):
                description = ""

            # Extract input names
            inputs = data.get("inputs", {})
            input_names = tuple(inputs.keys()) if isinstance(inputs, dict) else ()

            # Count top-level steps
            steps = data.get("steps", [])
            step_count = len(steps) if isinstance(steps, list) else 0

        except Exception as e:
            raise WorkflowDiscoveryError(
                f"Error extracting metadata from {path}: {e}"
            ) from e

        # Create and return metadata
        return WorkflowMetadata(
            name=name,
            version=version,
            description=description,
            input_names=input_names,
            step_count=step_count,
            file_path=path.resolve(),
            source=source_str,
        )

    def load_full(self, path: Path) -> WorkflowFile:
        """Load and fully validate workflow file.

        Uses the parse_workflow function from maverick.dsl.serialization.parser
        to perform complete YAML parsing and schema validation. This is slower
        than load_metadata but ensures the workflow is valid and executable.

        Args:
            path: Path to workflow file.

        Returns:
            Fully validated WorkflowFile.

        Raises:
            WorkflowDiscoveryError: If validation fails.

        Examples:
            >>> loader = WorkflowLoader()
            >>> workflow = loader.load_full(Path("workflow.yaml"))
            >>> workflow.name
            'fly'
            >>> len(workflow.steps)
            5
        """
        try:
            # Read file contents
            yaml_content = path.read_text(encoding="utf-8")
        except FileNotFoundError as e:
            raise WorkflowDiscoveryError(
                f"Workflow file not found: {path}"
            ) from e
        except PermissionError as e:
            raise WorkflowDiscoveryError(
                f"Permission denied reading workflow file: {path}"
            ) from e
        except OSError as e:
            raise WorkflowDiscoveryError(
                f"Error reading workflow file {path}: {e}"
            ) from e

        try:
            # Use parse_workflow for full validation
            # Pass validate_only=True to skip reference resolution
            # (discovery doesn't need to resolve references)
            workflow = parse_workflow(yaml_content, validate_only=True)
        except Exception as e:
            # Wrap all parse errors as WorkflowDiscoveryError
            raise WorkflowDiscoveryError(
                f"Error parsing workflow file {path}: {e}"
            ) from e

        return workflow
