"""Unified error types for the Maverick workflow DSL.

This module defines all exceptions for both decorator-based and serialization-based
workflow DSL operations, providing a unified hierarchy for error handling.

Exception Hierarchy:
    DSLError (base for all DSL errors)
    ├── WorkflowDefinitionError (errors in workflow structure/definition)
    │   ├── WorkflowParseError (YAML/JSON parsing failures)
    │   ├── UnsupportedVersionError (unsupported workflow version)
    │   ├── DuplicateComponentError (duplicate component registration)
    │   └── ReferenceResolutionError (unknown component reference)
    ├── WorkflowExecutionError (errors during workflow execution)
    │   ├── DSLWorkflowError (explicit workflow failure)
    │   ├── CheckpointNotFoundError (checkpoint file not found)
    │   └── InputMismatchError (checkpoint input mismatch)
    └── WorkflowSerializationError (serialization/deserialization errors)
        └── (extends WorkflowDefinitionError for backwards compatibility)
"""

from __future__ import annotations

from maverick.exceptions import MaverickError

# ============================================================================
# Base DSL Exception
# ============================================================================


class DSLError(MaverickError):
    """Base exception for all DSL-related errors.

    This is the root of the DSL exception hierarchy. All DSL-specific exceptions
    inherit from this class, allowing callers to catch all DSL errors with a
    single except clause.

    Examples:
        ```python
        try:
            workflow = load_and_execute_workflow("workflow.yaml")
        except DSLError as e:
            logger.error(f"DSL error: {e}")
            sys.exit(1)
        ```
    """

    pass


# ============================================================================
# Definition Errors (Structure, Validation, References)
# ============================================================================


class WorkflowDefinitionError(DSLError):
    """Errors in workflow definition, structure, or validation.

    Raised when a workflow definition is malformed, invalid, or contains
    unresolvable references. This applies to both decorator-based and
    serialized workflows.

    Examples:
        - Invalid workflow structure
        - Missing required fields
        - Unresolvable component references
        - Duplicate component names
        - Unsupported workflow versions
    """

    pass


class WorkflowParseError(WorkflowDefinitionError):
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
        self.file_path = file_path
        self.line_number = line_number
        self.parse_error = parse_error
        super().__init__(message)


class UnsupportedVersionError(WorkflowDefinitionError):
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
        self.file_path = file_path
        message = f"Unsupported workflow version: '{requested_version}'"
        if supported_versions:
            versions_str = ", ".join(f"'{v}'" for v in sorted(supported_versions))
            message += f". Supported versions: {versions_str}"
        super().__init__(message)


class DuplicateComponentError(WorkflowDefinitionError):
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


class ReferenceResolutionError(WorkflowDefinitionError):
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
        self.file_path = file_path
        self.line_number = line_number
        message = f"Unknown {reference_type} reference: '{reference_name}'"
        if available_names:
            names_str = ", ".join(f"'{n}'" for n in sorted(available_names)[:10])
            message += f". Available {reference_type}s: {names_str}"
            if len(available_names) > 10:
                message += f" (and {len(available_names) - 10} more)"
        super().__init__(message)


# ============================================================================
# Execution Errors (Runtime Failures)
# ============================================================================


class WorkflowExecutionError(DSLError):
    """Errors during workflow execution.

    Raised when a workflow fails during execution due to runtime issues such as
    missing checkpoints, input mismatches, or explicit workflow failures.

    Examples:
        - Checkpoint file not found during resume
        - Input hash mismatch when resuming
        - Explicit workflow failure via raise WorkflowError()
    """

    pass


class DSLWorkflowError(WorkflowExecutionError):
    """Explicit workflow failure raised by workflow code.

    Use this to signal that a workflow should stop with a specific
    error reason, distinct from step failures. This is raised explicitly
    by user code via `raise WorkflowError(reason)`.

    Attributes:
        reason: Human-readable explanation of why the workflow failed.

    Examples:
        ```python
        if not validation_passed:
            raise DSLWorkflowError("Validation failed: 3 tests failing")
        ```
    """

    def __init__(self, reason: str) -> None:
        """Initialize the DSLWorkflowError.

        Args:
            reason: Human-readable explanation of why the workflow failed.
        """
        self.reason = reason
        super().__init__(f"Workflow failed: {reason}")


class CheckpointNotFoundError(WorkflowExecutionError):
    """Raised when resuming from a non-existent checkpoint.

    Attributes:
        workflow_id: ID of the workflow that was being resumed.
        checkpoint_id: Specific checkpoint that was not found (if any).

    Examples:
        ```python
        raise CheckpointNotFoundError(
            workflow_id="fly-123",
            checkpoint_id="after_validation",
        )
        ```
    """

    def __init__(
        self,
        workflow_id: str,
        checkpoint_id: str | None = None,
    ) -> None:
        """Initialize the CheckpointNotFoundError.

        Args:
            workflow_id: ID of the workflow.
            checkpoint_id: Specific checkpoint ID (optional).
        """
        self.workflow_id = workflow_id
        self.checkpoint_id = checkpoint_id
        msg = f"No checkpoint found for workflow '{workflow_id}'"
        if checkpoint_id:
            msg += f" at '{checkpoint_id}'"
        super().__init__(msg)


class InputMismatchError(WorkflowExecutionError):
    """Raised when resume inputs don't match checkpoint inputs.

    Attributes:
        expected_hash: Hash from the checkpoint.
        actual_hash: Hash of current inputs.

    Examples:
        ```python
        raise InputMismatchError(
            expected_hash="abc123",
            actual_hash="def456",
        )
        ```
    """

    def __init__(
        self,
        expected_hash: str,
        actual_hash: str,
    ) -> None:
        """Initialize the InputMismatchError.

        Args:
            expected_hash: Hash stored in checkpoint.
            actual_hash: Hash of current inputs.
        """
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            f"Input hash mismatch: checkpoint has '{expected_hash}', "
            f"current inputs have '{actual_hash}'"
        )


class LoopStepExecutionError(WorkflowExecutionError):
    """Raised when one or more iterations in a loop step fail.

    This error is raised when a loop step completes but one or more of its
    iterations encountered errors. It provides details about which iterations
    failed and what errors occurred.

    Attributes:
        step_name: Name of the loop step that failed.
        failed_iterations: List of (index, error_message) tuples for failed iterations.
        total_iterations: Total number of iterations attempted.

    Examples:
        ```python
        raise LoopStepExecutionError(
            step_name="implement_by_phase",
            failed_iterations=[(2, "git commit failed: Author identity unknown")],
            total_iterations=5,
        )
        ```
    """

    def __init__(
        self,
        step_name: str,
        failed_iterations: list[tuple[int, str]],
        total_iterations: int,
    ) -> None:
        """Initialize the LoopStepExecutionError.

        Args:
            step_name: Name of the loop step.
            failed_iterations: List of (index, error_message) tuples.
            total_iterations: Total number of iterations.
        """
        self.step_name = step_name
        self.failed_iterations = failed_iterations
        self.total_iterations = total_iterations

        # Build error message
        failed_count = len(failed_iterations)
        if failed_count == 1:
            idx, error = failed_iterations[0]
            message = f"Loop step '{step_name}' failed: iteration {idx} error: {error}"
        else:
            indices = ", ".join(str(idx) for idx, _ in failed_iterations[:5])
            if failed_count > 5:
                indices += f", ... ({failed_count - 5} more)"
            first_error = failed_iterations[0][1]
            message = (
                f"Loop step '{step_name}' failed: {failed_count}/{total_iterations} "
                f"iterations failed (indices: {indices}). First error: {first_error}"
            )
        super().__init__(message)


# ============================================================================
# Serialization Errors (Backwards Compatibility Alias)
# ============================================================================


class WorkflowSerializationError(WorkflowDefinitionError):
    """Base exception for all workflow serialization errors.

    This is an alias for WorkflowDefinitionError, maintained for backwards
    compatibility with code that catches WorkflowSerializationError specifically.

    New code should use WorkflowDefinitionError or more specific subclasses.

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
