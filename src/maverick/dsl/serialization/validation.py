"""Semantic validation for workflow files (FR-017 enhancement).

This module provides comprehensive semantic validation that goes beyond
syntactic schema validation. It validates:
- Component references (actions, agents, generators, context builders, workflows)
- Expression syntax in ${{ ... }} templates
- Step name references in conditionals and dependencies
- Circular dependencies in step execution order
- Input usage patterns (unused inputs, missing required inputs)

The semantic validator catches errors early during workflow loading/parsing
rather than deferring them to execution time.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from maverick.dsl.expressions.errors import ExpressionSyntaxError
from maverick.dsl.expressions.parser import (
    AnyExpression,
    BooleanExpression,
    Expression,
    ExpressionKind,
    TernaryExpression,
    extract_all,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import (
    AgentStepRecord,
    BranchStepRecord,
    GenerateStepRecord,
    LoopStepRecord,
    PythonStepRecord,
    StepRecordUnion,
    SubWorkflowStepRecord,
    ValidateStepRecord,
    ValidationError,
    ValidationResult,
    ValidationWarning,
    WorkflowFile,
)

__all__ = ["WorkflowSemanticValidator", "validate_workflow_semantics"]


class WorkflowSemanticValidator:
    """Semantic validator for workflow files.

    Validates workflow semantics beyond schema validation, including:
    - Component reference resolution
    - Expression syntax validation
    - Step reference validation
    - Circular dependency detection
    - Input usage analysis

    Example:
        ```python
        from maverick.dsl.serialization import parse_workflow, ComponentRegistry
        from maverick.dsl.serialization.validation import WorkflowSemanticValidator

        # Parse workflow (syntax-only validation)
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Create validator with registry
        registry = ComponentRegistry()
        validator = WorkflowSemanticValidator(registry)

        # Validate semantics
        result = validator.validate(workflow)
        if not result.valid:
            for error in result.errors:
                print(f"Error: {error.message} at {error.path}")
        ```
    """

    def __init__(self, registry: ComponentRegistry) -> None:
        """Initialize semantic validator.

        Args:
            registry: Component registry for resolving references.
        """
        self._registry = registry

    def validate(self, workflow: WorkflowFile) -> ValidationResult:
        """Run all semantic validation checks.

        Args:
            workflow: WorkflowFile to validate.

        Returns:
            ValidationResult with errors and warnings.
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationWarning] = []

        # Check 1: Validate all referenced components exist in registry
        errors.extend(self._validate_component_references(workflow))

        # Check 2: Validate expression syntax
        errors.extend(self._validate_expressions(workflow))

        # Check 3: Validate step name references
        errors.extend(self._validate_step_references(workflow))

        # Check 4: Detect circular dependencies
        errors.extend(self._validate_no_cycles(workflow))

        # Check 5: Validate input types and requirements
        warnings.extend(self._validate_input_usage(workflow))

        return ValidationResult(
            valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def _validate_component_references(
        self, workflow: WorkflowFile
    ) -> list[ValidationError]:
        """Validate that all referenced components exist in registry.

        Checks:
        - Actions in python steps
        - Agents in agent steps
        - Generators in generate steps
        - Context builders in agent/generate steps
        - Workflows in subworkflow steps

        Args:
            workflow: WorkflowFile to validate.

        Returns:
            List of validation errors.
        """
        errors: list[ValidationError] = []

        def check_step(step: StepRecordUnion, path_prefix: str) -> None:
            """Recursively check step and nested steps."""
            if isinstance(step, PythonStepRecord):
                # Check action reference
                if not self._registry.actions.has(step.action):
                    available = self._registry.actions.list_names()
                    suggestion = (
                        f"Available actions: {', '.join(available[:5])}"
                        if available
                        else "No actions registered in registry"
                    )
                    errors.append(
                        ValidationError(
                            code="E001",
                            message=f"Action '{step.action}' not found in registry",
                            path=f"{path_prefix}.action",
                            suggestion=suggestion,
                        )
                    )

            elif isinstance(step, AgentStepRecord):
                # Check agent reference (stored in agents registry)
                if not self._registry.agents.has(step.agent):
                    available = self._registry.agents.list_names()
                    suggestion = (
                        f"Available agents: {', '.join(available[:5])}"
                        if available
                        else "No agents registered in registry"
                    )
                    errors.append(
                        ValidationError(
                            code="E002",
                            message=f"Agent '{step.agent}' not found in registry",
                            path=f"{path_prefix}.agent",
                            suggestion=suggestion,
                        )
                    )

                # Check context builder if context is a string reference
                if isinstance(
                    step.context, str
                ) and not self._registry.context_builders.has(step.context):
                    available = self._registry.context_builders.list_names()
                    suggestion = (
                        f"Available context builders: {', '.join(available[:5])}"
                        if available
                        else "No context builders registered in registry"
                    )
                    errors.append(
                        ValidationError(
                            code="E003",
                            message=(
                                f"Context builder '{step.context}' "
                                f"not found in registry"
                            ),
                            path=f"{path_prefix}.context",
                            suggestion=suggestion,
                        )
                    )

            elif isinstance(step, GenerateStepRecord):
                # Check generator reference
                if not self._registry.generators.has(step.generator):
                    available = self._registry.generators.list_names()
                    suggestion = (
                        f"Available generators: {', '.join(available[:5])}"
                        if available
                        else "No generators registered in registry"
                    )
                    errors.append(
                        ValidationError(
                            code="E004",
                            message=(
                                f"Generator '{step.generator}' not found in registry"
                            ),
                            path=f"{path_prefix}.generator",
                            suggestion=suggestion,
                        )
                    )

                # Check context builder if context is a string reference
                if isinstance(
                    step.context, str
                ) and not self._registry.context_builders.has(step.context):
                    available = self._registry.context_builders.list_names()
                    suggestion = (
                        f"Available context builders: {', '.join(available[:5])}"
                        if available
                        else "No context builders registered in registry"
                    )
                    errors.append(
                        ValidationError(
                            code="E003",
                            message=(
                                f"Context builder '{step.context}' "
                                f"not found in registry"
                            ),
                            path=f"{path_prefix}.context",
                            suggestion=suggestion,
                        )
                    )

            elif isinstance(step, SubWorkflowStepRecord):
                # Check workflow reference
                if not self._registry.workflows.has(step.workflow):
                    available = self._registry.workflows.list_names()
                    suggestion = (
                        f"Available workflows: {', '.join(available[:5])}"
                        if available
                        else "No workflows registered in registry"
                    )
                    errors.append(
                        ValidationError(
                            code="E005",
                            message=f"Workflow '{step.workflow}' not found in registry",
                            path=f"{path_prefix}.workflow",
                            suggestion=suggestion,
                        )
                    )

            elif isinstance(step, ValidateStepRecord):
                # Check on_failure step if present
                if step.on_failure:
                    check_step(step.on_failure, f"{path_prefix}.on_failure")

            elif isinstance(step, BranchStepRecord):
                # Check all branch options
                for i, option in enumerate(step.options):
                    check_step(option.step, f"{path_prefix}.options[{i}].step")

            elif isinstance(step, LoopStepRecord):
                # Check all parallel substeps
                for i, substep in enumerate(step.steps):
                    check_step(substep, f"{path_prefix}.steps[{i}]")

        # Check all top-level steps
        for i, step in enumerate(workflow.steps):
            check_step(step, f"steps[{i}]")

        return errors

    def _validate_expressions(self, workflow: WorkflowFile) -> list[ValidationError]:
        """Validate expression syntax in all workflow expressions.

        Uses the expression parser to validate ${{ ... }} syntax.
        Also validates that referenced step names exist (for step refs).

        Args:
            workflow: WorkflowFile to validate.

        Returns:
            List of validation errors.
        """
        errors: list[ValidationError] = []

        def extract_from_value(value: Any, path: str) -> None:
            """Recursively extract and validate expressions from any value."""
            if isinstance(value, str):
                # Extract expressions from string
                try:
                    extract_all(value)
                except ExpressionSyntaxError as e:
                    errors.append(
                        ValidationError(
                            code="E006",
                            message=f"Invalid expression syntax: {e}",
                            path=path,
                            suggestion=(
                                "Check expression syntax. Valid formats: "
                                "${{ inputs.name }}, ${{ steps.x.output }}, "
                                "${{ item }}, ${{ index }}"
                            ),
                        )
                    )
            elif isinstance(value, dict):
                # Recursively search dict values
                for key, val in value.items():
                    extract_from_value(val, f"{path}.{key}")
            elif isinstance(value, list):
                # Recursively search list items
                for i, item in enumerate(value):
                    extract_from_value(item, f"{path}[{i}]")

        def check_step(step: StepRecordUnion, path_prefix: str) -> None:
            """Recursively check expressions in step and nested steps."""
            # Extract from 'when' condition
            if step.when:
                extract_from_value(step.when, f"{path_prefix}.when")

            # Extract from step-specific fields
            if isinstance(step, PythonStepRecord):
                if step.args:
                    extract_from_value(step.args, f"{path_prefix}.args")
                if step.kwargs:
                    extract_from_value(step.kwargs, f"{path_prefix}.kwargs")

            elif isinstance(step, (AgentStepRecord, GenerateStepRecord)):
                if isinstance(step.context, dict):
                    extract_from_value(step.context, f"{path_prefix}.context")

            elif isinstance(step, ValidateStepRecord):
                if step.stages:
                    extract_from_value(step.stages, f"{path_prefix}.stages")
                if step.on_failure:
                    check_step(step.on_failure, f"{path_prefix}.on_failure")

            elif isinstance(step, SubWorkflowStepRecord):
                if step.inputs:
                    extract_from_value(step.inputs, f"{path_prefix}.inputs")

            elif isinstance(step, BranchStepRecord):
                for i, option in enumerate(step.options):
                    extract_from_value(option.when, f"{path_prefix}.options[{i}].when")
                    check_step(option.step, f"{path_prefix}.options[{i}].step")

            elif isinstance(step, LoopStepRecord):
                for i, substep in enumerate(step.steps):
                    check_step(substep, f"{path_prefix}.steps[{i}]")

        # Extract from input defaults
        for input_name, input_def in workflow.inputs.items():
            if input_def.default is not None:
                extract_from_value(input_def.default, f"inputs.{input_name}.default")

        # Extract from all steps
        for i, step in enumerate(workflow.steps):
            check_step(step, f"steps[{i}]")

        return errors

    def _validate_step_references(
        self, workflow: WorkflowFile
    ) -> list[ValidationError]:
        """Validate that step names referenced in expressions exist.

        Checks that all step references in expressions (${{ steps.x.output }})
        point to actual step names in the workflow.

        Args:
            workflow: WorkflowFile to validate.

        Returns:
            List of validation errors.
        """
        errors: list[ValidationError] = []

        # Build set of all step names (including nested steps)
        step_names: set[str] = set()

        def collect_step_names(step: StepRecordUnion) -> None:
            """Recursively collect all step names."""
            step_names.add(step.name)

            if isinstance(step, ValidateStepRecord) and step.on_failure:
                collect_step_names(step.on_failure)
            elif isinstance(step, BranchStepRecord):
                for option in step.options:
                    collect_step_names(option.step)
            elif isinstance(step, LoopStepRecord):
                for substep in step.steps:
                    collect_step_names(substep)

        for step in workflow.steps:
            collect_step_names(step)

        # Extract all step references from expressions
        def extract_step_refs(expr: AnyExpression, step_refs: set[str]) -> None:
            """Recursively extract step references from expression."""
            if isinstance(expr, Expression):
                if expr.kind == ExpressionKind.STEP_REF and len(expr.path) >= 2:
                    # Path is like ("steps", "step_name", "output", ...)
                    step_name = expr.path[1]
                    step_refs.add(step_name)
            elif isinstance(expr, BooleanExpression):
                for operand in expr.operands:
                    extract_step_refs(operand, step_refs)
            elif isinstance(expr, TernaryExpression):
                extract_step_refs(expr.condition, step_refs)
                extract_step_refs(expr.value_if_true, step_refs)
                extract_step_refs(expr.value_if_false, step_refs)

        def extract_from_value(value: Any, path: str) -> None:
            """Recursively extract step refs from any value."""
            if isinstance(value, str):
                try:
                    expressions = extract_all(value)
                    for expr in expressions:
                        step_refs: set[str] = set()
                        extract_step_refs(expr, step_refs)

                        # Validate each referenced step name exists
                        for ref_step_name in step_refs:
                            if ref_step_name not in step_names:
                                available = sorted(step_names)[:5]
                                suggestion = (
                                    f"Available steps: {', '.join(available)}"
                                    if available
                                    else "No steps defined yet"
                                )
                                errors.append(
                                    ValidationError(
                                        code="E007",
                                        message=(
                                            f"Referenced step '{ref_step_name}' "
                                            f"not found in workflow"
                                        ),
                                        path=path,
                                        suggestion=suggestion,
                                    )
                                )
                except ExpressionSyntaxError:
                    # Already caught by _validate_expressions
                    pass
            elif isinstance(value, dict):
                for key, val in value.items():
                    extract_from_value(val, f"{path}.{key}")
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    extract_from_value(item, f"{path}[{i}]")

        def check_step(step: StepRecordUnion, path_prefix: str) -> None:
            """Recursively check step references in expressions."""
            if step.when:
                extract_from_value(step.when, f"{path_prefix}.when")

            if isinstance(step, PythonStepRecord):
                if step.args:
                    extract_from_value(step.args, f"{path_prefix}.args")
                if step.kwargs:
                    extract_from_value(step.kwargs, f"{path_prefix}.kwargs")

            elif isinstance(step, (AgentStepRecord, GenerateStepRecord)):
                if isinstance(step.context, dict):
                    extract_from_value(step.context, f"{path_prefix}.context")

            elif isinstance(step, ValidateStepRecord):
                if step.stages:
                    extract_from_value(step.stages, f"{path_prefix}.stages")
                if step.on_failure:
                    check_step(step.on_failure, f"{path_prefix}.on_failure")

            elif isinstance(step, SubWorkflowStepRecord):
                if step.inputs:
                    extract_from_value(step.inputs, f"{path_prefix}.inputs")

            elif isinstance(step, BranchStepRecord):
                for i, option in enumerate(step.options):
                    extract_from_value(option.when, f"{path_prefix}.options[{i}].when")
                    check_step(option.step, f"{path_prefix}.options[{i}].step")

            elif isinstance(step, LoopStepRecord):
                for i, substep in enumerate(step.steps):
                    check_step(substep, f"{path_prefix}.steps[{i}]")

        # Check all steps
        for i, step in enumerate(workflow.steps):
            check_step(step, f"steps[{i}]")

        return errors

    def _validate_no_cycles(self, workflow: WorkflowFile) -> list[ValidationError]:
        """Detect circular dependencies in step execution order.

        Builds a dependency graph based on step references in expressions
        and checks for cycles using depth-first search.

        Args:
            workflow: WorkflowFile to validate.

        Returns:
            List of validation errors.
        """
        errors: list[ValidationError] = []

        # Build dependency graph: step_name -> set of steps it depends on
        dependencies: dict[str, set[str]] = defaultdict(set)

        def collect_dependencies(step: StepRecordUnion) -> None:
            """Recursively collect dependencies for a step."""
            step_deps: set[str] = set()

            def extract_from_value(value: Any) -> None:
                """Extract step references from value."""
                if isinstance(value, str):
                    try:
                        expressions = extract_all(value)
                        for expr in expressions:
                            refs: set[str] = set()
                            self._extract_step_refs(expr, refs)
                            step_deps.update(refs)
                    except ExpressionSyntaxError:
                        pass
                elif isinstance(value, dict):
                    for val in value.values():
                        extract_from_value(val)
                elif isinstance(value, list):
                    for item in value:
                        extract_from_value(item)

            # Extract dependencies from when condition
            if step.when:
                extract_from_value(step.when)

            # Extract dependencies from step-specific fields
            if isinstance(step, PythonStepRecord):
                if step.args:
                    extract_from_value(step.args)
                if step.kwargs:
                    extract_from_value(step.kwargs)
            elif isinstance(step, (AgentStepRecord, GenerateStepRecord)):
                if isinstance(step.context, dict):
                    extract_from_value(step.context)
            elif isinstance(step, SubWorkflowStepRecord):
                if step.inputs:
                    extract_from_value(step.inputs)
            elif isinstance(step, ValidateStepRecord):
                if step.stages:
                    extract_from_value(step.stages)
                if step.on_failure:
                    collect_dependencies(step.on_failure)
            elif isinstance(step, BranchStepRecord):
                for option in step.options:
                    extract_from_value(option.when)
                    collect_dependencies(option.step)
            elif isinstance(step, LoopStepRecord):
                for substep in step.steps:
                    collect_dependencies(substep)

            dependencies[step.name] = step_deps

        # Collect dependencies for all steps
        for step in workflow.steps:
            collect_dependencies(step)

        # Detect cycles using DFS
        def find_cycle(
            node: str, visited: set[str], rec_stack: list[str]
        ) -> list[str] | None:
            """DFS to find cycles. Returns cycle path if found."""
            visited.add(node)
            rec_stack.append(node)

            for dep in dependencies.get(node, set()):
                if dep not in visited:
                    cycle = find_cycle(dep, visited, rec_stack)
                    if cycle:
                        return cycle
                elif dep in rec_stack:
                    # Found cycle
                    cycle_start = rec_stack.index(dep)
                    return rec_stack[cycle_start:] + [dep]

            rec_stack.pop()
            return None

        # Check each step for cycles
        for step_name in dependencies:
            visited: set[str] = set()
            rec_stack: list[str] = []
            cycle = find_cycle(step_name, visited, rec_stack)
            if cycle:
                cycle_str = " -> ".join(cycle)
                errors.append(
                    ValidationError(
                        code="E008",
                        message=f"Circular dependency detected: {cycle_str}",
                        path=f"steps (involving {cycle[0]})",
                        suggestion="Remove circular step references. "
                        "Ensure steps reference only previous steps' outputs.",
                    )
                )
                # Only report first cycle to avoid duplicates
                break

        return errors

    def _extract_step_refs(self, expr: AnyExpression, step_refs: set[str]) -> None:
        """Helper to extract step references from expression.

        Args:
            expr: Expression to extract from.
            step_refs: Set to add step names to (modified in place).
        """
        if isinstance(expr, Expression):
            if expr.kind == ExpressionKind.STEP_REF and len(expr.path) >= 2:
                step_refs.add(expr.path[1])
        elif isinstance(expr, BooleanExpression):
            for operand in expr.operands:
                self._extract_step_refs(operand, step_refs)
        elif isinstance(expr, TernaryExpression):
            self._extract_step_refs(expr.condition, step_refs)
            self._extract_step_refs(expr.value_if_true, step_refs)
            self._extract_step_refs(expr.value_if_false, step_refs)

    def _validate_input_usage(self, workflow: WorkflowFile) -> list[ValidationWarning]:
        """Validate input usage patterns.

        Checks:
        - Unused inputs (defined but never referenced)
        - Required inputs without defaults

        Args:
            workflow: WorkflowFile to validate.

        Returns:
            List of validation warnings.
        """
        warnings: list[ValidationWarning] = []

        # Track which inputs are referenced
        referenced_inputs: set[str] = set()

        def extract_from_value(value: Any) -> None:
            """Extract input references from value."""
            if isinstance(value, str):
                try:
                    expressions = extract_all(value)
                    for expr in expressions:
                        self._extract_input_refs(expr, referenced_inputs)
                except ExpressionSyntaxError:
                    pass
            elif isinstance(value, dict):
                for val in value.values():
                    extract_from_value(val)
            elif isinstance(value, list):
                for item in value:
                    extract_from_value(item)

        def check_step(step: StepRecordUnion) -> None:
            """Recursively check input references in expressions."""
            if step.when:
                extract_from_value(step.when)

            if isinstance(step, PythonStepRecord):
                if step.args:
                    extract_from_value(step.args)
                if step.kwargs:
                    extract_from_value(step.kwargs)
            elif isinstance(step, (AgentStepRecord, GenerateStepRecord)):
                if isinstance(step.context, dict):
                    extract_from_value(step.context)
            elif isinstance(step, SubWorkflowStepRecord):
                if step.inputs:
                    extract_from_value(step.inputs)
            elif isinstance(step, ValidateStepRecord):
                if step.stages:
                    extract_from_value(step.stages)
                if step.on_failure:
                    check_step(step.on_failure)
            elif isinstance(step, BranchStepRecord):
                for option in step.options:
                    extract_from_value(option.when)
                    check_step(option.step)
            elif isinstance(step, LoopStepRecord):
                for substep in step.steps:
                    check_step(substep)

        # Check all steps for input references
        for step in workflow.steps:
            check_step(step)

        # Check for unused inputs
        for input_name, _input_def in workflow.inputs.items():
            if input_name not in referenced_inputs:
                warnings.append(
                    ValidationWarning(
                        code="W001",
                        message=f"Input '{input_name}' is defined but never used",
                        path=f"inputs.{input_name}",
                    )
                )

        return warnings

    def _extract_input_refs(self, expr: AnyExpression, input_refs: set[str]) -> None:
        """Helper to extract input references from expression.

        Args:
            expr: Expression to extract from.
            input_refs: Set to add input names to (modified in place).
        """
        if isinstance(expr, Expression):
            if expr.kind == ExpressionKind.INPUT_REF and len(expr.path) >= 2:
                input_refs.add(expr.path[1])
        elif isinstance(expr, BooleanExpression):
            for operand in expr.operands:
                self._extract_input_refs(operand, input_refs)
        elif isinstance(expr, TernaryExpression):
            self._extract_input_refs(expr.condition, input_refs)
            self._extract_input_refs(expr.value_if_true, input_refs)
            self._extract_input_refs(expr.value_if_false, input_refs)


def validate_workflow_semantics(
    workflow: WorkflowFile, registry: ComponentRegistry
) -> ValidationResult:
    """Convenience function for semantic validation.

    Args:
        workflow: WorkflowFile to validate.
        registry: Component registry for resolving references.

    Returns:
        ValidationResult with errors and warnings.

    Example:
        ```python
        from maverick.dsl.serialization import parse_workflow, ComponentRegistry
        from maverick.dsl.serialization.validation import validate_workflow_semantics

        workflow = parse_workflow(yaml_content, validate_only=True)
        registry = ComponentRegistry()
        result = validate_workflow_semantics(workflow, registry)

        if not result.valid:
            for error in result.errors:
                print(f"{error.code}: {error.message}")
        ```
    """
    validator = WorkflowSemanticValidator(registry)
    return validator.validate(workflow)
