"""MCP tool validation utilities for testing.

This module provides utilities for validating MCP tool responses
against expected schemas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeGuard


def is_string_value(value: Any) -> TypeGuard[str]:
    """Type guard for string values."""
    return isinstance(value, str)


def is_dict_value(value: Any) -> TypeGuard[dict[str, Any]]:
    """Type guard for dict values."""
    return isinstance(value, dict)


def is_list_value(value: Any) -> TypeGuard[list[Any]]:
    """Type guard for list values."""
    return isinstance(value, list)


@dataclass
class ValidationResult:
    """Result of schema validation.

    Attributes:
        valid: Whether the response matched the schema
        errors: List of validation error messages
    """

    valid: bool
    errors: list[str] = field(default_factory=list)


class MCPToolValidator:
    """Validates MCP tool responses against expected schemas.

    Provides a simple way to register expected response schemas for MCP tools
    and validate actual responses against them.

    Example:
        >>> validator = MCPToolValidator()
        >>> validator.register_schema("create_pr", {
        ...     "type": "object",
        ...     "required": ["url", "number"],
        ...     "properties": {
        ...         "url": {"type": "string"},
        ...         "number": {"type": "integer"},
        ...     }
        ... })
        >>> response = {"url": "https://github.com/...", "number": 123}
        >>> validator.assert_valid("create_pr", response)
    """

    def __init__(self) -> None:
        """Initialize the validator with empty schema registry."""
        self._schemas: dict[str, dict[str, Any]] = {}

    def register_schema(self, tool_name: str, schema: dict[str, Any]) -> None:
        """Register an expected schema for a tool.

        Args:
            tool_name: Name of the MCP tool
            schema: JSON Schema-like dict defining expected response structure
        """
        self._schemas[tool_name] = schema

    def validate(self, tool_name: str, response: Any) -> ValidationResult:
        """Validate a response against a registered schema.

        Args:
            tool_name: Name of the MCP tool
            response: The response to validate

        Returns:
            ValidationResult with valid flag and any error messages
        """
        if tool_name not in self._schemas:
            return ValidationResult(
                valid=False, errors=[f"No schema registered for tool '{tool_name}'"]
            )

        schema = self._schemas[tool_name]
        errors: list[str] = []

        self._validate_value(response, schema, "", errors)

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def _validate_value(
        self, value: Any, schema: dict[str, Any], path: str, errors: list[str]
    ) -> None:
        """Recursively validate a value against a schema.

        Args:
            value: The value to validate
            schema: The schema to validate against
            path: Current path in the object (for error messages)
            errors: List to append errors to
        """
        schema_type = schema.get("type")

        if schema_type == "object":
            self._validate_object(value, schema, path, errors)
        elif schema_type == "array":
            self._validate_array(value, schema, path, errors)
        elif schema_type == "string":
            if not is_string_value(value):
                errors.append(
                    f"{path or 'root'}: expected string, got {type(value).__name__}"
                )
        elif schema_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(
                    f"{path or 'root'}: expected integer, got {type(value).__name__}"
                )
        elif schema_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(
                    f"{path or 'root'}: expected number, got {type(value).__name__}"
                )
        elif schema_type == "boolean":
            if not isinstance(value, bool):
                errors.append(
                    f"{path or 'root'}: expected boolean, got {type(value).__name__}"
                )
        elif schema_type == "null" and value is not None:
            errors.append(
                f"{path or 'root'}: expected null, got {type(value).__name__}"
            )

    def _validate_object(
        self, value: Any, schema: dict[str, Any], path: str, errors: list[str]
    ) -> None:
        """Validate an object value against an object schema."""
        if not is_dict_value(value):
            errors.append(
                f"{path or 'root'}: expected object, got {type(value).__name__}"
            )
            return

        # Check required fields
        required = schema.get("required", [])
        for req_field in required:
            if req_field not in value:
                field_path = f"{path}.{req_field}" if path else req_field
                errors.append(f"{field_path}: required field missing")

        # Validate properties
        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name in value:
                prop_path = f"{path}.{prop_name}" if path else prop_name
                self._validate_value(value[prop_name], prop_schema, prop_path, errors)

    def _validate_array(
        self, value: Any, schema: dict[str, Any], path: str, errors: list[str]
    ) -> None:
        """Validate an array value against an array schema."""
        if not is_list_value(value):
            errors.append(
                f"{path or 'root'}: expected array, got {type(value).__name__}"
            )
            return

        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(value):
                item_path = f"{path}[{i}]"
                self._validate_value(item, items_schema, item_path, errors)

    def assert_valid(self, tool_name: str, response: Any) -> None:
        """Assert that a response is valid according to the registered schema.

        Args:
            tool_name: Name of the MCP tool
            response: The response to validate

        Raises:
            AssertionError: If the response is invalid
        """
        result = self.validate(tool_name, response)
        if not result.valid:
            raise AssertionError(
                f"Invalid response for tool '{tool_name}':\n"
                + "\n".join(f"  - {e}" for e in result.errors)
            )

    def assert_invalid(self, tool_name: str, response: Any) -> None:
        """Assert that a response is invalid according to the registered schema.

        Args:
            tool_name: Name of the MCP tool
            response: The response to validate

        Raises:
            AssertionError: If the response is valid
        """
        result = self.validate(tool_name, response)
        if result.valid:
            raise AssertionError(
                f"Expected invalid response for tool '{tool_name}', but it was valid"
            )
