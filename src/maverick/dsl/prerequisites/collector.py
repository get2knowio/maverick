"""Prerequisite collector that scans workflows and resolves prerequisites.

This module provides PrerequisiteCollector which:
1. Scans all steps in a workflow
2. Collects step-level `requires` declarations
3. Collects component-level `requires` from registry metadata
4. Merges and deduplicates requirements
5. Resolves transitive dependencies
6. Returns a PreflightPlan with execution order
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from maverick.dsl.prerequisites.models import PreflightPlan
from maverick.dsl.prerequisites.registry import PrerequisiteRegistry
from maverick.dsl.types import StepType
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.dsl.serialization.registry import ComponentRegistry
    from maverick.dsl.serialization.schema import (
        StepRecordUnion,
        WorkflowFile,
    )

logger = get_logger(__name__)


class PrerequisiteCollector:
    """Collects and resolves prerequisites for a workflow.

    Scans a workflow definition and its component registrations to build
    a complete PreflightPlan with all required prerequisites.

    Example:
        ```python
        collector = PrerequisiteCollector()
        plan = collector.collect(
            workflow=workflow_file,
            component_registry=component_registry,
            prerequisite_registry=prerequisite_registry,
        )
        print(f"Need to check: {plan.prerequisites}")
        print(f"Execution order: {plan.execution_order}")
        ```
    """

    def collect(
        self,
        workflow: WorkflowFile,
        component_registry: ComponentRegistry,
        prerequisite_registry: PrerequisiteRegistry,
    ) -> PreflightPlan:
        """Collect all prerequisites for a workflow.

        Args:
            workflow: The workflow definition to scan.
            component_registry: Registry containing action/agent metadata.
            prerequisite_registry: Registry of available prerequisite checks.

        Returns:
            PreflightPlan with deduplicated prerequisites in execution order.
        """
        # Mapping: prerequisite name -> set of step names that need it
        prereq_to_steps: dict[str, set[str]] = {}

        # Scan all steps (including nested steps)
        self._scan_steps(
            steps=workflow.steps,
            component_registry=component_registry,
            prereq_to_steps=prereq_to_steps,
        )

        if not prereq_to_steps:
            # No prerequisites needed
            return PreflightPlan(
                prerequisites=(),
                step_requirements={},
                execution_order=(),
            )

        # Get unique prerequisite names
        prereq_names = list(prereq_to_steps.keys())

        # Resolve transitive dependencies and get execution order
        try:
            execution_order = prerequisite_registry.get_all_dependencies(prereq_names)
        except KeyError as e:
            # Unknown prerequisite - log warning and filter it out
            logger.warning(
                f"Unknown prerequisite referenced: {e}. "
                "Will skip unknown prerequisites."
            )
            # Filter to only known prerequisites
            known_names = [
                name for name in prereq_names if prerequisite_registry.has(name)
            ]
            if not known_names:
                return PreflightPlan(
                    prerequisites=(),
                    step_requirements={},
                    execution_order=(),
                )
            execution_order = prerequisite_registry.get_all_dependencies(known_names)

        # Convert step mappings to tuples
        step_requirements = {
            name: tuple(sorted(steps)) for name, steps in prereq_to_steps.items()
        }

        # Ensure all dependencies (including transitive) are in step_requirements
        # Mark transitive deps with empty step list (they're inferred, not explicit)
        for name in execution_order:
            if name not in step_requirements:
                step_requirements[name] = ()

        return PreflightPlan(
            prerequisites=tuple(prereq_names),
            step_requirements=step_requirements,
            execution_order=tuple(execution_order),
        )

    def _scan_steps(
        self,
        steps: list[StepRecordUnion],
        component_registry: ComponentRegistry,
        prereq_to_steps: dict[str, set[str]],
        parent_prefix: str = "",
    ) -> None:
        """Recursively scan steps to collect prerequisites.

        Args:
            steps: List of step records to scan.
            component_registry: Registry for looking up component metadata.
            prereq_to_steps: Accumulator mapping prereq names to step names.
            parent_prefix: Prefix for nested step names (for loops/branches).
        """
        for step in steps:
            step_name = f"{parent_prefix}{step.name}" if parent_prefix else step.name

            # Collect step-level requires (if the step has a requires field)
            step_requires = self._get_step_requires(step)
            for prereq in step_requires:
                prereq_to_steps.setdefault(prereq, set()).add(step_name)

            # Collect component-level requires based on step type
            component_requires = self._get_component_requires(step, component_registry)
            for prereq in component_requires:
                prereq_to_steps.setdefault(prereq, set()).add(step_name)

            # Recurse into nested steps (loops, branches, validate)
            nested_steps = self._get_nested_steps(step)
            if nested_steps:
                self._scan_steps(
                    steps=nested_steps,
                    component_registry=component_registry,
                    prereq_to_steps=prereq_to_steps,
                    parent_prefix=f"{step_name}/",
                )

    def _get_step_requires(self, step: Any) -> list[str]:
        """Get step-level requires declarations.

        Args:
            step: A step record.

        Returns:
            List of prerequisite names from step's requires field.
        """
        # Step may have a 'requires' field (added in schema)
        requires = getattr(step, "requires", None)
        if requires is None:
            return []
        return list(requires)

    def _get_component_requires(
        self,
        step: Any,
        component_registry: ComponentRegistry,
    ) -> list[str]:
        """Get component-level requires from registry metadata.

        Args:
            step: A step record.
            component_registry: Registry for looking up metadata.

        Returns:
            List of prerequisite names from component's registration.
        """
        step_type = StepType(step.type)

        if step_type == StepType.PYTHON:
            # Python step - look up action metadata
            action_name = getattr(step, "action", None)
            if action_name and component_registry.actions.has(action_name):
                return list(component_registry.actions.get_requires(action_name))

        elif step_type == StepType.AGENT:
            # Agent step - look up agent metadata
            agent_name = getattr(step, "agent", None)
            if agent_name and component_registry.agents.has(agent_name):
                return list(component_registry.agents.get_requires(agent_name))

        elif step_type == StepType.GENERATE:
            # Generate step - look up generator metadata
            generator_name = getattr(step, "generator", None)
            if generator_name and component_registry.generators.has(generator_name):
                return list(component_registry.generators.get_requires(generator_name))

        return []

    def _get_nested_steps(self, step: Any) -> list[Any]:
        """Get nested steps from loop, branch, or validate steps.

        Args:
            step: A step record that may contain nested steps.

        Returns:
            List of nested step records, or empty list if none.
        """
        step_type = StepType(step.type)

        if step_type == StepType.LOOP:
            # Loop step has 'steps' field
            return list(getattr(step, "steps", []))

        elif step_type == StepType.BRANCH:
            # Branch step has 'options' with nested steps
            nested: list[Any] = []
            options = getattr(step, "options", [])
            for option in options:
                option_step = getattr(option, "step", None)
                if option_step:
                    nested.append(option_step)
            return nested

        elif step_type == StepType.VALIDATE:
            # Validate step may have 'on_failure' step
            on_failure = getattr(step, "on_failure", None)
            if on_failure:
                return [on_failure]

        return []
