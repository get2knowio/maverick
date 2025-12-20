"""Serialization-specific error types for the Maverick workflow DSL.

This module defines exceptions specific to workflow serialization and deserialization,
including YAML/JSON parsing, version checking, and reference resolution.
"""

from __future__ import annotations

from maverick.exceptions import MaverickError


class WorkflowSerializationError(MaverickError):
    """Base exception for all workflow serialization errors.

    This is the parent class for all exceptions that can occur during workflow
    serialization and deserialization operations. It provides a common base for
    catching all serialization-related errors.

    Attributes:
        message: Human-readable error message.
        file_path: Optional path to the file being serialized/deserialized.
        line_number: Optional line number where the error occurred.

    Examples:
        ```python
        try:
            workflow = load_workflow("workflow.yaml")
        except WorkflowSerializationError as e:
            logger.error(f"Serialization error: {e.message}")
            if e.file_path:
                logger.error(f"  File: {e.file_path}")
            if e.line_number:
                logger.error(f"  Line: {e.line_number}")
        ```
    """

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        line_number: int | None = None,
    ) -> None:
        """Initialize the WorkflowSerializationError.

        Args:
            message: Human-readable error message.
            file_path: Optional path to the file being processed.
            line_number: Optional line number where the error occurred.
        """
        self.file_path = file_path
        self.line_number = line_number
        super().__init__(message)


class WorkflowParseError(WorkflowSerializationError):
    """Exception raised when YAML/JSON parsing fails.

    Raised when a workflow file cannot be parsed due to invalid YAML/JSON syntax,
    malformed structure, or missing required fields.

    Attributes:
        message: Human-readable error message.
        file_path: Path to the file being parsed.
        line_number: Line number where the parse error occurred (if known).
        parse_error: The underlying parse error from the YAML/JSON library.

    Examples:
        ```python
        # Invalid YAML syntax
        raise WorkflowParseError(
            "Invalid YAML syntax: expected ':', got '='",
            file_path="workflow.yaml",
            line_number=15,
        )

        # Missing required field
        raise WorkflowParseError(
            "Missing required field 'name' in workflow definition",
            file_path="workflow.yaml",
        )

        # Malformed structure
        raise WorkflowParseError(
            "Invalid step definition: expected object, got string",
            file_path="workflow.yaml",
            line_number=42,
        )
        ```
    """

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        line_number: int | None = None,
        parse_error: Exception | None = None,
    ) -> None:
        """Initialize the WorkflowParseError.

        Args:
            message: Human-readable error message.
            file_path: Path to the file being parsed.
            line_number: Line number where the parse error occurred.
            parse_error: The underlying parse error from the YAML/JSON library.
        """
        self.parse_error = parse_error
        super().__init__(message, file_path, line_number)


class UnsupportedVersionError(WorkflowSerializationError):
    """Exception raised when a workflow version is not supported.

    Raised when attempting to load a workflow file with a version that is not
    supported by the current deserializer. Includes information about which
    versions are supported to help users upgrade or downgrade.

    Attributes:
        message: Human-readable error message.
        file_path: Path to the file with unsupported version.
        requested_version: The version found in the workflow file.
        supported_versions: List of versions supported by this deserializer.

    Examples:
        ```python
        # Future version
        raise UnsupportedVersionError(
            requested_version="2.0",
            supported_versions=["1.0"],
            file_path="workflow.yaml",
        )

        # Legacy version
        raise UnsupportedVersionError(
            requested_version="0.9",
            supported_versions=["1.0", "1.1"],
            file_path="old_workflow.yaml",
        )
        ```
    """

    def __init__(
        self,
        requested_version: str,
        supported_versions: list[str],
        file_path: str | None = None,
    ) -> None:
        """Initialize the UnsupportedVersionError.

        Args:
            requested_version: The version found in the workflow file.
            supported_versions: List of versions supported by this deserializer.
            file_path: Path to the file with unsupported version.
        """
        self.requested_version = requested_version
        self.supported_versions = supported_versions
        message = f"Unsupported workflow version: '{requested_version}'"
        if supported_versions:
            versions_str = ", ".join(f"'{v}'" for v in sorted(supported_versions))
            message += f". Supported versions: {versions_str}"
        super().__init__(message, file_path)


class DuplicateComponentError(WorkflowSerializationError):
    """Exception raised when attempting to register a component with a duplicate name.

    Raised when a component (action, agent, generator, etc.) is registered with
    a name that is already in use. This is distinct from ReferenceResolutionError
    which handles lookup failures.

    Attributes:
        message: Human-readable error message.
        component_type: Type of component (e.g., "action", "generator", "workflow").
        component_name: Name that was already registered.

    Examples:
        ```python
        raise DuplicateComponentError(
            component_type="action",
            component_name="validate_files",
        )
        ```
    """

    def __init__(
        self,
        component_type: str,
        component_name: str,
    ) -> None:
        """Initialize the DuplicateComponentError.

        Args:
            component_type: Type of component (e.g., "action", "generator").
            component_name: Name that was already registered.
        """
        self.component_type = component_type
        self.component_name = component_name
        message = (
            f"Duplicate {component_type} registration: "
            f"'{component_name}' is already registered"
        )
        super().__init__(message)


class ReferenceResolutionError(WorkflowSerializationError):
    """Exception raised when a reference to an unknown component cannot be resolved.

    Raised when a workflow definition references a component (action, agent, generator,
    etc.) that does not exist or is not registered. This includes step references,
    agent references, generator references, and other cross-references within the
    workflow definition.

    Attributes:
        message: Human-readable error message.
        file_path: Path to the file containing the unresolved reference.
        line_number: Line number where the reference appears.
        reference_type: Type of reference (e.g., "agent", "generator", "step").
        reference_name: Name of the component that could not be resolved.
        available_names: Optional list of available component names for suggestions.

    Examples:
        ```python
        # Unknown agent reference
        raise ReferenceResolutionError(
            reference_type="agent",
            reference_name="code_reviewer",
            available_names=["implementer", "issue_fixer"],
            file_path="workflow.yaml",
            line_number=25,
        )

        # Unknown generator reference
        raise ReferenceResolutionError(
            reference_type="generator",
            reference_name="pr_body_generator",
            available_names=["commit_msg", "issue_body"],
            file_path="workflow.yaml",
        )

        # Unknown step reference in conditional
        raise ReferenceResolutionError(
            reference_type="step",
            reference_name="validate_tests",
            file_path="workflow.yaml",
            line_number=60,
        )
        ```
    """

    def __init__(
        self,
        reference_type: str,
        reference_name: str,
        available_names: list[str] | None = None,
        file_path: str | None = None,
        line_number: int | None = None,
    ) -> None:
        """Initialize the ReferenceResolutionError.

        Args:
            reference_type: Type of reference (e.g., "agent", "generator", "step").
            reference_name: Name of the component that could not be resolved.
            available_names: Optional list of available component names.
            file_path: Path to the file containing the unresolved reference.
            line_number: Line number where the reference appears.
        """
        self.reference_type = reference_type
        self.reference_name = reference_name
        self.available_names = available_names or []
        message = f"Unknown {reference_type} reference: '{reference_name}'"
        if available_names:
            names_str = ", ".join(f"'{n}'" for n in sorted(available_names)[:10])
            message += f". Available {reference_type}s: {names_str}"
            if len(available_names) > 10:
                message += f" (and {len(available_names) - 10} more)"
        super().__init__(message, file_path, line_number)
