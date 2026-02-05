"""Workflow writer for serializing WorkflowFile to various formats.

This module provides the WorkflowWriter class for converting WorkflowFile
schema models to dict, YAML, and JSON formats.

Key features:
- Converts WorkflowFile to dict with proper field ordering
- Serializes to YAML with human-readable formatting
- Serializes to JSON with configurable indentation
- Preserves expression syntax (${{ ... }})
- Handles all step types including nested structures
- Omits None values and preserves empty collections

Usage:
    writer = WorkflowWriter()

    # Convert to dict
    data = writer.to_dict(workflow)

    # Convert to YAML
    yaml_str = writer.to_yaml(workflow)

    # Convert to JSON
    json_str = writer.to_json(workflow, indent=2)
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from maverick.dsl.serialization.schema import (
    AgentStepRecord,
    BranchOptionRecord,
    BranchStepRecord,
    GenerateStepRecord,
    InputDefinition,
    LoopStepRecord,
    PythonStepRecord,
    StepRecord,
    SubWorkflowStepRecord,
    ValidateStepRecord,
    WorkflowFile,
)

__all__ = ["WorkflowWriter"]


class WorkflowWriter:
    """Serializes WorkflowFile to various formats.

    This class converts WorkflowFile Pydantic models to dict, YAML, and JSON
    formats suitable for file storage and transmission.

    Features:
        - Field ordering: Preserves logical field order for readability
        - None omission: Excludes None values from output
        - Expression preservation: Maintains ${{ ... }} syntax
        - Nested structures: Handles complex nested step types

    Example:
        >>> workflow = WorkflowFile(version="1.0", name="my-workflow", steps=[...])
        >>> writer = WorkflowWriter()
        >>> yaml_str = writer.to_yaml(workflow)
        >>> with open("workflow.yaml", "w") as f:
        ...     f.write(yaml_str)
    """

    def to_dict(self, workflow: WorkflowFile) -> dict[str, Any]:
        """Convert WorkflowFile to dict suitable for YAML/JSON serialization.

        Args:
            workflow: WorkflowFile instance to convert.

        Returns:
            Dictionary with proper field ordering and None values omitted.

        Example:
            >>> workflow = WorkflowFile(version="1.0", name="test", steps=[...])
            >>> writer = WorkflowWriter()
            >>> data = writer.to_dict(workflow)
            >>> data["version"]
            "1.0"
        """
        # Build the workflow dict with proper field ordering
        result: dict[str, Any] = {
            "version": workflow.version,
            "name": workflow.name,
        }

        # Add optional description if present
        if workflow.description:
            result["description"] = workflow.description

        # Add inputs if present
        if workflow.inputs:
            result["inputs"] = {
                name: self._serialize_input(input_def)
                for name, input_def in workflow.inputs.items()
            }

        # Add steps (always present, validated by schema)
        result["steps"] = [self._serialize_step(step) for step in workflow.steps]

        return result

    def to_yaml(self, workflow: WorkflowFile) -> str:
        """Convert WorkflowFile to YAML string.

        Args:
            workflow: WorkflowFile instance to convert.

        Returns:
            YAML string representation with human-readable formatting.

        Example:
            >>> workflow = WorkflowFile(version="1.0", name="test", steps=[...])
            >>> writer = WorkflowWriter()
            >>> yaml_str = writer.to_yaml(workflow)
            >>> print(yaml_str)
            version: '1.0'
            name: test
            ...
        """
        data = self.to_dict(workflow)
        # Use safe_dump for security and default_flow_style=False for readability
        result: str = yaml.safe_dump(
            data,
            default_flow_style=False,
            sort_keys=False,  # Preserve our field ordering
            allow_unicode=True,
        )
        return result

    def to_json(self, workflow: WorkflowFile, indent: int | None = 2) -> str:
        """Convert WorkflowFile to JSON string.

        Args:
            workflow: WorkflowFile instance to convert.
            indent: Number of spaces for indentation. Use None for compact output.
                Default is 2 for readability.

        Returns:
            JSON string representation.

        Example:
            >>> workflow = WorkflowFile(version="1.0", name="test", steps=[...])
            >>> writer = WorkflowWriter()
            >>> json_str = writer.to_json(workflow, indent=4)
            >>> print(json_str)
            {
                "version": "1.0",
                "name": "test",
                ...
            }
        """
        data = self.to_dict(workflow)
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def _serialize_input(self, input_def: InputDefinition) -> dict[str, Any]:
        """Serialize InputDefinition to dict.

        Args:
            input_def: InputDefinition to serialize.

        Returns:
            Dictionary with input definition fields.
        """
        result: dict[str, Any] = {
            "type": input_def.type.value,  # Convert enum to string
            "required": input_def.required,
        }

        # Add optional fields
        if input_def.default is not None:
            result["default"] = input_def.default

        if input_def.description:
            result["description"] = input_def.description

        return result

    def _serialize_step(self, step: StepRecord) -> dict[str, Any]:
        """Serialize a step record to dict.

        Dispatches to specific serialization methods based on step type.

        Args:
            step: StepRecord (discriminated union) to serialize.

        Returns:
            Dictionary with step fields in logical order.
        """
        # Common fields (name, type, when)
        result: dict[str, Any] = {
            "name": step.name,
            "type": step.type.value,  # Convert enum to string
        }

        # Add optional when field
        if step.when is not None:
            result["when"] = step.when

        # Dispatch to type-specific serialization
        if isinstance(step, PythonStepRecord):
            self._serialize_python_step(step, result)
        elif isinstance(step, AgentStepRecord):
            self._serialize_agent_step(step, result)
        elif isinstance(step, GenerateStepRecord):
            self._serialize_generate_step(step, result)
        elif isinstance(step, ValidateStepRecord):
            self._serialize_validate_step(step, result)
        elif isinstance(step, SubWorkflowStepRecord):
            self._serialize_subworkflow_step(step, result)
        elif isinstance(step, BranchStepRecord):
            self._serialize_branch_step(step, result)
        elif isinstance(step, LoopStepRecord):
            self._serialize_parallel_step(step, result)
        else:  # pragma: no cover - unreachable; discriminated union validation
            raise ValueError(f"Unknown step type: {type(step)}")

        return result

    def _serialize_python_step(
        self, step: PythonStepRecord, result: dict[str, Any]
    ) -> None:
        """Add PythonStepRecord-specific fields to result dict.

        Args:
            step: PythonStepRecord to serialize.
            result: Dictionary to add fields to (modified in place).
        """
        result["action"] = step.action

        # Include args/kwargs even if empty (explicit is better)
        result["args"] = step.args
        result["kwargs"] = step.kwargs

    def _serialize_agent_step(
        self, step: AgentStepRecord, result: dict[str, Any]
    ) -> None:
        """Add AgentStepRecord-specific fields to result dict.

        Args:
            step: AgentStepRecord to serialize.
            result: Dictionary to add fields to (modified in place).
        """
        result["agent"] = step.agent
        result["context"] = step.context  # Can be dict or string

    def _serialize_generate_step(
        self, step: GenerateStepRecord, result: dict[str, Any]
    ) -> None:
        """Add GenerateStepRecord-specific fields to result dict.

        Args:
            step: GenerateStepRecord to serialize.
            result: Dictionary to add fields to (modified in place).
        """
        result["generator"] = step.generator
        result["context"] = step.context  # Can be dict or string

    def _serialize_validate_step(
        self, step: ValidateStepRecord, result: dict[str, Any]
    ) -> None:
        """Add ValidateStepRecord-specific fields to result dict.

        Args:
            step: ValidateStepRecord to serialize.
            result: Dictionary to add fields to (modified in place).
        """
        result["stages"] = step.stages  # Can be list or string
        result["retry"] = step.retry

        # Add optional on_failure step
        if step.on_failure is not None:
            result["on_failure"] = self._serialize_step(step.on_failure)

    def _serialize_subworkflow_step(
        self, step: SubWorkflowStepRecord, result: dict[str, Any]
    ) -> None:
        """Add SubWorkflowStepRecord-specific fields to result dict.

        Args:
            step: SubWorkflowStepRecord to serialize.
            result: Dictionary to add fields to (modified in place).
        """
        result["workflow"] = step.workflow
        result["inputs"] = step.inputs

    def _serialize_branch_step(
        self, step: BranchStepRecord, result: dict[str, Any]
    ) -> None:
        """Add BranchStepRecord-specific fields to result dict.

        Args:
            step: BranchStepRecord to serialize.
            result: Dictionary to add fields to (modified in place).
        """
        result["options"] = [
            self._serialize_branch_option(option) for option in step.options
        ]

    def _serialize_branch_option(self, option: BranchOptionRecord) -> dict[str, Any]:
        """Serialize a branch option to dict.

        Args:
            option: BranchOptionRecord to serialize.

        Returns:
            Dictionary with when and step fields.
        """
        return {
            "when": option.when,
            "step": self._serialize_step(option.step),
        }

    def _serialize_parallel_step(
        self, step: LoopStepRecord, result: dict[str, Any]
    ) -> None:
        """Add LoopStepRecord-specific fields to result dict.

        Args:
            step: LoopStepRecord to serialize.
            result: Dictionary to add fields to (modified in place).
        """
        result["steps"] = [
            self._serialize_step(child_step) for child_step in step.steps
        ]

        # Add for_each if present
        if step.for_each is not None:
            result["for_each"] = step.for_each

        # Serialize parallel or max_concurrency (mutually exclusive)
        # Prefer parallel if it was explicitly set
        if step.parallel is not None:
            result["parallel"] = step.parallel
        elif step.max_concurrency != 1:
            # Only include max_concurrency if not the default value
            result["max_concurrency"] = step.max_concurrency
