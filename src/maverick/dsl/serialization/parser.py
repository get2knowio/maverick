"""Workflow YAML/JSON parser (T032-T039).

This module provides functions for parsing and validating workflow files:
- parse_yaml: Parse YAML string to dict with error handling
- validate_schema: Validate dict against WorkflowFile Pydantic schema
- validate_version: Check version is supported (1.0)
- extract_expressions: Extract and statically validate all expressions
- resolve_references: Resolve all component references using registry
- parse_workflow: Main entry point - parse YAML to validated WorkflowFile

The parser supports both strict and lenient modes for reference resolution,
as well as a validate_only mode that skips reference resolution entirely.
"""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import ValidationError

from maverick.dsl.errors import (
    ReferenceResolutionError,
    UnsupportedVersionError,
    WorkflowParseError,
)
from maverick.dsl.expressions.parser import AnyExpression, extract_all
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import (
    AgentStepRecord,
    BranchStepRecord,
    GenerateStepRecord,
    ParallelStepRecord,
    PythonStepRecord,
    StepRecordUnion,
    SubWorkflowStepRecord,
    ValidateStepRecord,
    ValidationResult,
    WorkflowFile,
)

__all__ = [
    "parse_yaml",
    "validate_schema",
    "validate_version",
    "extract_expressions",
    "resolve_references",
    "parse_workflow",
    "parse_workflow_with_validation",
    "parse_workflow_unsafe",
]

# Supported workflow versions
SUPPORTED_VERSIONS = ["1.0"]


# =============================================================================
# YAML Parsing (T032)
# =============================================================================


def parse_yaml(yaml_content: str) -> dict[str, Any]:
    """Parse YAML string to dict with error handling.

    Converts a YAML string to a Python dictionary, handling syntax errors
    and structural issues. Preserves line number information when available
    for better error reporting.

    Args:
        yaml_content: YAML string to parse.

    Returns:
        Parsed YAML as a dictionary.

    Raises:
        WorkflowParseError: If YAML is empty, has syntax errors, or doesn't
            result in a dictionary.

    Examples:
        >>> yaml_str = '''
        ... version: "1.0"
        ... name: test-workflow
        ... '''
        >>> result = parse_yaml(yaml_str)
        >>> result['version']
        '1.0'
    """
    # Check for empty content
    if not yaml_content or yaml_content.isspace():
        raise WorkflowParseError("Empty workflow content")

    try:
        # Parse YAML using safe_load (prevents arbitrary code execution)
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        # Extract line number if available
        line_number = None
        if hasattr(e, "problem_mark"):
            line_number = e.problem_mark.line + 1  # Convert to 1-indexed

        raise WorkflowParseError(
            f"YAML syntax error: {e}",
            line_number=line_number,
            parse_error=e,
        ) from e

    # Ensure result is a dictionary
    if not isinstance(data, dict):
        raise WorkflowParseError(
            f"Workflow file must be an object (dict), got {type(data).__name__}"
        )

    return data


# =============================================================================
# Schema Validation (T033)
# =============================================================================


def validate_schema(data: dict[str, Any]) -> WorkflowFile:
    """Validate dict against WorkflowFile Pydantic schema.

    Uses Pydantic validation to ensure the workflow dict conforms to the
    WorkflowFile schema, including all step types, inputs, and metadata.

    Args:
        data: Workflow dictionary from YAML parsing.

    Returns:
        Validated WorkflowFile instance.

    Raises:
        WorkflowParseError: If schema validation fails (missing fields,
            invalid types, constraint violations, etc.).

    Examples:
        >>> workflow_dict = {
        ...     "version": "1.0",
        ...     "name": "test-workflow",
        ...     "steps": [{"name": "step1", "type": "python", "action": "my_action"}]
        ... }
        >>> workflow = validate_schema(workflow_dict)
        >>> workflow.name
        'test-workflow'
    """
    try:
        workflow = WorkflowFile(**data)
    except ValidationError as e:
        # Extract meaningful error message from Pydantic
        error_details = []
        for error in e.errors():
            loc = ".".join(str(x) for x in error["loc"])
            msg = error["msg"]
            error_details.append(f"{loc}: {msg}")

        raise WorkflowParseError(
            f"Schema validation failed: {'; '.join(error_details)}"
        ) from e

    return workflow


# =============================================================================
# Version Validation (T034)
# =============================================================================


def validate_version(workflow: WorkflowFile) -> None:
    """Check version is supported.

    Validates that the workflow version is in the list of supported versions.
    Currently only version "1.0" is supported.

    Args:
        workflow: Validated WorkflowFile instance.

    Raises:
        UnsupportedVersionError: If the workflow version is not supported.

    Examples:
        >>> workflow = WorkflowFile(
        ...     version="1.0",
        ...     name="test-workflow",
        ...     steps=[{"name": "step1", "type": "python", "action": "my_action"}]
        ... )
        >>> validate_version(workflow)  # No error
    """
    if workflow.version not in SUPPORTED_VERSIONS:
        raise UnsupportedVersionError(
            requested_version=workflow.version,
            supported_versions=SUPPORTED_VERSIONS,
        )


# =============================================================================
# Expression Extraction (T035-T036)
# =============================================================================


def _extract_from_value(value: Any, expressions: list[AnyExpression]) -> None:
    """Recursively extract expressions from any value (str, dict, list, etc.).

    Helper function that traverses data structures to find all expression
    strings and parse them.

    Args:
        value: Value to search for expressions (can be str, dict, list, etc.).
        expressions: List to append found expressions to (modified in-place).
    """
    if isinstance(value, str):
        # Extract expressions from string
        found = extract_all(value)
        expressions.extend(found)
    elif isinstance(value, dict):
        # Recursively search dict values
        for v in value.values():
            _extract_from_value(v, expressions)
    elif isinstance(value, list):
        # Recursively search list items
        for item in value:
            _extract_from_value(item, expressions)
    # For other types (int, bool, None, etc.), no expressions possible


def _extract_from_step(step: StepRecordUnion, expressions: list[AnyExpression]) -> None:
    """Extract expressions from a single step (including nested steps).

    Handles all step types including nested structures (branch, parallel).

    Args:
        step: Step record to extract expressions from.
        expressions: List to append found expressions to (modified in-place).
    """
    # Extract from 'when' condition
    if step.when:
        _extract_from_value(step.when, expressions)

    # Extract from step-specific fields
    if isinstance(step, PythonStepRecord):
        _extract_from_value(step.args, expressions)
        _extract_from_value(step.kwargs, expressions)
    elif isinstance(step, (AgentStepRecord, GenerateStepRecord)):
        _extract_from_value(step.context, expressions)
    elif isinstance(step, ValidateStepRecord):
        _extract_from_value(step.stages, expressions)
        if step.on_failure:
            _extract_from_step(step.on_failure, expressions)
    elif isinstance(step, SubWorkflowStepRecord):
        _extract_from_value(step.inputs, expressions)
    elif isinstance(step, BranchStepRecord):
        for option in step.options:
            _extract_from_value(option.when, expressions)
            _extract_from_step(option.step, expressions)
    elif isinstance(step, ParallelStepRecord):
        for substep in step.steps:
            _extract_from_step(substep, expressions)


def extract_expressions(workflow: WorkflowFile) -> list[AnyExpression]:
    """Extract and statically validate all expressions from workflow.

    Traverses the entire workflow structure (inputs, steps, nested steps)
    to find all expression strings (${{ ... }}) and parse them. Validates
    expression syntax but does not validate references.

    Args:
        workflow: Validated WorkflowFile instance.

    Returns:
        List of all parsed Expression objects found in the workflow.

    Raises:
        ExpressionSyntaxError: If any expression has invalid syntax.

    Examples:
        >>> workflow = WorkflowFile(
        ...     version="1.0",
        ...     name="test-workflow",
        ...     steps=[{
        ...         "name": "step1",
        ...         "type": "python",
        ...         "action": "my_action",
        ...         "kwargs": {"flag": "${{ inputs.dry_run }}"}
        ...     }]
        ... )
        >>> expressions = extract_expressions(workflow)
        >>> len(expressions)
        1
        >>> expressions[0].raw
        '${{ inputs.dry_run }}'
    """
    expressions: list[AnyExpression] = []

    # Extract from input defaults (rare but possible)
    for input_def in workflow.inputs.values():
        if input_def.default is not None:
            _extract_from_value(input_def.default, expressions)

    # Extract from all steps
    for step in workflow.steps:
        _extract_from_step(step, expressions)

    return expressions


# =============================================================================
# Reference Resolution (T037-T039)
# =============================================================================


def _resolve_step_references(
    step: StepRecordUnion, registry: ComponentRegistry
) -> None:
    """Resolve all component references in a step (including nested steps).

    Validates that all referenced components (actions, agents, generators,
    context builders, workflows) exist in the registry.

    Args:
        step: Step record to resolve references in.
        registry: Component registry to look up references in.

    Raises:
        ReferenceResolutionError: If any reference cannot be resolved
            (only in strict mode).
    """
    # Resolve step-specific references
    if isinstance(step, PythonStepRecord):
        # Resolve action reference
        if not registry.actions.has(step.action) and registry.strict:
            raise ReferenceResolutionError(
                reference_type="action",
                reference_name=step.action,
                available_names=registry.actions.list_names(),
            )
    elif isinstance(step, AgentStepRecord):
        # Resolve agent reference (stored in generators registry)
        if not registry.generators.has(step.agent) and registry.strict:
            raise ReferenceResolutionError(
                reference_type="agent",
                reference_name=step.agent,
                available_names=registry.generators.list_names(),
            )
        # Resolve context builder if context is a string
        if (
            isinstance(step.context, str)
            and not registry.context_builders.has(step.context)
            and registry.strict
        ):
            raise ReferenceResolutionError(
                reference_type="context_builder",
                reference_name=step.context,
                available_names=registry.context_builders.list_names(),
            )
    elif isinstance(step, GenerateStepRecord):
        # Resolve generator reference
        if not registry.generators.has(step.generator) and registry.strict:
            raise ReferenceResolutionError(
                reference_type="generator",
                reference_name=step.generator,
                available_names=registry.generators.list_names(),
            )
        # Resolve context builder if context is a string
        if (
            isinstance(step.context, str)
            and not registry.context_builders.has(step.context)
            and registry.strict
        ):
            raise ReferenceResolutionError(
                reference_type="context_builder",
                reference_name=step.context,
                available_names=registry.context_builders.list_names(),
            )
    elif isinstance(step, SubWorkflowStepRecord):
        # Resolve workflow reference
        if not registry.workflows.has(step.workflow) and registry.strict:
            raise ReferenceResolutionError(
                reference_type="workflow",
                reference_name=step.workflow,
                available_names=registry.workflows.list_names(),
            )
    elif isinstance(step, ValidateStepRecord):
        # Resolve on_failure step if present
        if step.on_failure:
            _resolve_step_references(step.on_failure, registry)
    elif isinstance(step, BranchStepRecord):
        # Resolve references in all branch options
        for option in step.options:
            _resolve_step_references(option.step, registry)
    elif isinstance(step, ParallelStepRecord):
        # Resolve references in all parallel substeps
        for substep in step.steps:
            _resolve_step_references(substep, registry)


def resolve_references(workflow: WorkflowFile, registry: ComponentRegistry) -> None:
    """Resolve all component references using registry.

    Validates that all referenced components (actions, agents, generators,
    context builders, workflows) exist in the provided registry. In strict
    mode, raises errors for unresolved references. In lenient mode, defers
    errors until runtime.

    Args:
        workflow: Validated WorkflowFile instance.
        registry: Component registry containing available components.

    Raises:
        ReferenceResolutionError: If any reference cannot be resolved
            (only in strict mode).

    Examples:
        >>> registry = ComponentRegistry(strict=True)
        >>> registry.actions.register("my_action", lambda: None)
        >>> workflow = WorkflowFile(
        ...     version="1.0",
        ...     name="test-workflow",
        ...     steps=[{"name": "step1", "type": "python", "action": "my_action"}]
        ... )
        >>> resolve_references(workflow, registry)  # No error
    """
    # Resolve references in all top-level steps
    for step in workflow.steps:
        _resolve_step_references(step, registry)


# =============================================================================
# Main Entry Point (T032-T039)
# =============================================================================


def parse_workflow(
    yaml_content: str,
    registry: ComponentRegistry | None = None,
    validate_only: bool = False,
    validate_semantic: bool = True,
) -> WorkflowFile:
    """Main entry point: parse YAML to validated WorkflowFile.

    Orchestrates the complete workflow parsing pipeline:
    1. Parse YAML to dict
    2. Validate against schema
    3. Validate version
    4. Extract and validate expressions
    5. Run semantic validation (if enabled and registry provided)
    6. Resolve component references (optional)

    Args:
        yaml_content: YAML string to parse.
        registry: Optional component registry for reference resolution and
            semantic validation. If None, reference resolution and semantic
            validation are skipped.
        validate_only: If True, skip reference resolution even if registry
            is provided. Useful for syntax-only validation.
        validate_semantic: If True and registry is provided, run semantic
            validation before reference resolution. Defaults to True for
            safety. Set to False to skip semantic validation (not recommended
            except for testing).

    Returns:
        Fully validated WorkflowFile instance.

    Raises:
        WorkflowParseError: For YAML syntax, schema validation errors, or
            semantic validation errors (if validate_semantic=True).
        UnsupportedVersionError: For unsupported workflow versions.
        ExpressionSyntaxError: For invalid expression syntax.
        ReferenceResolutionError: For unresolved references (strict mode only).

    Examples:
        >>> yaml_str = '''
        ... version: "1.0"
        ... name: test-workflow
        ... steps:
        ...   - name: step1
        ...     type: python
        ...     action: my_action
        ... '''
        >>> workflow = parse_workflow(yaml_str)
        >>> workflow.name
        'test-workflow'
    """
    # Import here to avoid circular imports
    from maverick.dsl.serialization.validation import validate_workflow_semantics

    # Step 1: Parse YAML to dict
    data = parse_yaml(yaml_content)

    # Step 2: Validate against schema
    workflow = validate_schema(data)

    # Step 3: Validate version
    validate_version(workflow)

    # Step 4: Extract and validate expressions
    # Note: We extract expressions to validate syntax, but don't need to
    # store the result since expressions are evaluated at runtime
    extract_expressions(workflow)

    # Step 5: Run semantic validation if enabled and registry is provided
    if validate_semantic and registry is not None:
        validation_result = validate_workflow_semantics(workflow, registry)

        # If there are errors, raise WorkflowParseError with all error details
        if not validation_result.valid:
            error_messages = [
                f"{error.code} at {error.path}: {error.message}"
                for error in validation_result.errors
            ]

            # Include first error's suggestion if available
            suggestion_text = ""
            if validation_result.errors and validation_result.errors[0].suggestion:
                suggestion_text = (
                    f"\n\nSuggestion: {validation_result.errors[0].suggestion}"
                )

            full_message = (
                "Semantic validation failed:\n  "
                + "\n  ".join(error_messages)
                + suggestion_text
            )

            raise WorkflowParseError(message=full_message)

    # Step 6: Resolve component references (if registry provided and not validate_only)
    if registry is not None and not validate_only:
        resolve_references(workflow, registry)

    return workflow


def parse_workflow_unsafe(
    yaml_content: str,
    registry: ComponentRegistry | None = None,
    validate_only: bool = False,
) -> WorkflowFile:
    """Parse workflow WITHOUT semantic validation (unsafe mode).

    This is equivalent to parse_workflow(..., validate_semantic=False).
    Use this function when you need to bypass semantic validation for
    testing or advanced use cases. NOT RECOMMENDED for production use.

    Args:
        yaml_content: YAML string to parse.
        registry: Optional component registry for reference resolution.
        validate_only: If True, skip reference resolution even if registry
            is provided.

    Returns:
        WorkflowFile instance (with only syntactic validation).

    Raises:
        WorkflowParseError: For YAML syntax or schema validation errors.
        UnsupportedVersionError: For unsupported workflow versions.
        ExpressionSyntaxError: For invalid expression syntax.
        ReferenceResolutionError: For unresolved references (strict mode only).

    Warning:
        This function skips semantic validation. Invalid workflows may fail
        at runtime with cryptic errors. Use parse_workflow() instead unless
        you have a specific reason to skip validation.

    Examples:
        >>> # Testing invalid workflow without validation
        >>> workflow = parse_workflow_unsafe(yaml_content)
    """
    return parse_workflow(
        yaml_content,
        registry=registry,
        validate_only=validate_only,
        validate_semantic=False,
    )


def parse_workflow_with_validation(
    yaml_content: str,
    registry: ComponentRegistry,
    validate_semantic: bool = True,
) -> tuple[WorkflowFile, ValidationResult | None]:
    """Parse YAML to WorkflowFile with optional semantic validation.

    Extended entry point that supports semantic validation in addition
    to syntactic validation. Returns both the workflow and validation
    result for more granular error handling.

    Orchestrates the complete workflow parsing pipeline:
    1. Parse YAML to dict
    2. Validate against schema
    3. Validate version
    4. Extract and validate expressions
    5. Optionally run semantic validation (default: True)
    6. Resolve component references (if semantic validation passed)

    Args:
        yaml_content: YAML string to parse.
        registry: Component registry for reference resolution and validation.
        validate_semantic: If True, run semantic validation before reference
            resolution. If False, only run syntactic validation.

    Returns:
        Tuple of (WorkflowFile, ValidationResult or None).
        ValidationResult is None if validate_semantic=False.

    Raises:
        WorkflowParseError: For YAML syntax or schema validation errors.
        UnsupportedVersionError: For unsupported workflow versions.
        ExpressionSyntaxError: For invalid expression syntax.

    Note:
        Unlike parse_workflow(), this function does NOT raise on semantic
        validation errors. Instead, errors are returned in ValidationResult.
        This allows callers to handle validation errors gracefully (e.g.,
        display them in TUI).

    Examples:
        >>> yaml_str = '''
        ... version: "1.0"
        ... name: test-workflow
        ... steps:
        ...   - name: step1
        ...     type: python
        ...     action: my_action
        ... '''
        >>> registry = ComponentRegistry()
        >>> workflow, result = parse_workflow_with_validation(yaml_str, registry)
        >>> if result and not result.valid:
        ...     for error in result.errors:
        ...         print(f"{error.code}: {error.message}")
    """
    # Import here to avoid circular imports
    from maverick.dsl.serialization.validation import validate_workflow_semantics

    # Step 1: Parse YAML to dict
    data = parse_yaml(yaml_content)

    # Step 2: Validate against schema
    workflow = validate_schema(data)

    # Step 3: Validate version
    validate_version(workflow)

    # Step 4: Extract and validate expressions (syntactic validation)
    extract_expressions(workflow)

    # Step 5: Run semantic validation if requested
    validation_result: ValidationResult | None = None
    if validate_semantic:
        validation_result = validate_workflow_semantics(workflow, registry)

        # Only resolve references if validation passed
        # (avoid cryptic runtime errors for invalid workflows)
        if validation_result.valid:
            resolve_references(workflow, registry)
    else:
        # No semantic validation - resolve references directly
        resolve_references(workflow, registry)

    return workflow, validation_result
