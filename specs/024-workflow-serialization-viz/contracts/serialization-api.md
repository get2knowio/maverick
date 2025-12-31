# Serialization API Contract

**Feature**: 024-workflow-serialization-viz
**Date**: 2025-12-20

## Overview

This document defines the Python API contracts for workflow serialization (YAML/JSON ↔ Python objects).

---

## 1. Parser Interface

### 1.1 WorkflowParser

```python
class WorkflowParser(Protocol):
    """Parser for workflow files (FR-003, FR-004)."""

    def parse_yaml(self, yaml_content: str) -> WorkflowFile:
        """Parse YAML string to WorkflowFile.

        Args:
            yaml_content: Raw YAML string.

        Returns:
            Validated WorkflowFile Pydantic model.

        Raises:
            WorkflowParseError: If YAML is invalid or schema validation fails.
            UnsupportedVersionError: If schema version is not supported (FR-018).
        """
        ...

    def parse_dict(self, data: dict[str, Any]) -> WorkflowFile:
        """Parse dictionary to WorkflowFile (FR-003).

        Args:
            data: Dictionary representation of workflow.

        Returns:
            Validated WorkflowFile Pydantic model.

        Raises:
            WorkflowParseError: If schema validation fails.
        """
        ...

    def validate_only(self, yaml_content: str) -> ValidationResult:
        """Validate workflow without building executable (FR-019).

        Args:
            yaml_content: Raw YAML string.

        Returns:
            ValidationResult with errors and warnings.
        """
        ...
```

---

### 1.2 parse_workflow (Function)

```python
def parse_workflow(
    yaml_content: str,
    registry: ComponentRegistry | None = None,
    validate_only: bool = False,
) -> WorkflowFile:
    """Parse and resolve workflow from YAML source.

    Orchestrates the complete workflow parsing pipeline:
    1. Parse YAML to dict
    2. Validate against Pydantic schema
    3. Validate version
    4. Extract and validate expressions
    5. Resolve component references (optional)

    Args:
        yaml_content: YAML string to parse.
        registry: Optional component registry for reference resolution.
            If None, reference resolution is skipped.
        validate_only: If True, skip reference resolution even if registry
            is provided. Useful for syntax-only validation.

    Returns:
        Fully validated WorkflowFile instance (Pydantic model).

    Raises:
        WorkflowParseError: For YAML syntax or schema validation errors.
        UnsupportedVersionError: For unsupported workflow versions.
        ExpressionSyntaxError: For invalid expression syntax.
        ReferenceResolutionError: For unresolved references (when registry provided).

    Note:
        WorkflowFile is distinct from WorkflowDefinition (used by @workflow decorator).
        WorkflowFile is the Pydantic model for YAML/JSON file-based workflows.
    """
    ...
```

---

## 2. Writer Interface

### 2.1 WorkflowWriter

```python
class WorkflowWriter(Protocol):
    """Writer for serializing workflows (FR-001, FR-002)."""

    def to_dict(self, workflow: WorkflowDefinition) -> dict[str, Any]:
        """Serialize workflow to dictionary (FR-001).

        Args:
            workflow: WorkflowDefinition to serialize.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        ...

    def to_yaml(self, workflow: WorkflowDefinition) -> str:
        """Serialize workflow to YAML string (FR-002).

        Args:
            workflow: WorkflowDefinition to serialize.

        Returns:
            YAML string representation.
        """
        ...

    def to_json(self, workflow: WorkflowDefinition, indent: int = 2) -> str:
        """Serialize workflow to JSON string.

        Args:
            workflow: WorkflowDefinition to serialize.
            indent: JSON indentation level.

        Returns:
            JSON string representation.
        """
        ...
```

---

## 3. Registry Interfaces

### 3.1 Registry (Generic Protocol)

```python
from typing import TypeVar, Protocol

T = TypeVar("T")

class Registry(Protocol[T]):
    """Generic registry interface (FR-014)."""

    def register(self, name: str, component: T | None = None) -> T | Callable[[T], T]:
        """Register a component by name.

        Can be used as decorator: @registry.register("name")
        Or called directly: registry.register("name", component)

        Args:
            name: Unique component name.
            component: Component to register (None for decorator use).

        Returns:
            Component when called directly, decorator when component is None.

        Raises:
            DuplicateRegistrationError: If name already registered.
        """
        ...

    def get(self, name: str) -> T:
        """Get component by name (FR-015).

        Args:
            name: Component name.

        Returns:
            Registered component.

        Raises:
            NotFoundError: If name not registered.
        """
        ...

    def has(self, name: str) -> bool:
        """Check if name is registered.

        Args:
            name: Component name.

        Returns:
            True if registered.
        """
        ...

    def list_names(self) -> list[str]:
        """List all registered names.

        Returns:
            Sorted list of registered names.
        """
        ...
```

---

### 3.2 ComponentRegistry

```python
@dataclass
class ComponentRegistry:
    """Unified component registry facade (FR-014).

    Attributes:
        actions: Registry for Python callables.
        agents: Registry for MaverickAgent classes.
        generators: Registry for GeneratorAgent classes.
        context_builders: Registry for context builder functions.
        workflows: Registry for named workflows.
        strict: If False, defer resolution errors (FR-016a).
    """

    actions: ActionRegistry
    agents: AgentRegistry
    generators: GeneratorRegistry
    context_builders: ContextBuilderRegistry
    workflows: WorkflowRegistry
    strict: bool = True

    def resolve(
        self,
        ref_type: Literal["action", "agent", "generator", "context_builder", "workflow"],
        name: str,
    ) -> Any:
        """Resolve a reference by type and name.

        Args:
            ref_type: Type of component to resolve.
            name: Component name.

        Returns:
            Resolved component.

        Raises:
            ReferenceResolutionError: If strict=True and not found.
        """
        ...

    def get_deferred_errors(self) -> list[RegistryError]:
        """Get list of deferred resolution errors (when strict=False).

        Returns:
            List of RegistryError for unresolved references.
        """
        ...

    @classmethod
    def default(cls) -> ComponentRegistry:
        """Create registry with default global singletons.

        Returns:
            ComponentRegistry with module-level registries.
        """
        ...
```

---

## 4. Expression Interfaces

### 4.1 ExpressionParser

```python
class ExpressionParser(Protocol):
    """Parser for ${{ }} expressions (FR-011)."""

    def parse(self, expr_str: str) -> Expression:
        """Parse expression string to AST.

        Args:
            expr_str: Expression like "${{ inputs.name }}"

        Returns:
            Parsed Expression object.

        Raises:
            ExpressionSyntaxError: If syntax is invalid.
        """
        ...

    def extract_all(self, text: str) -> list[tuple[str, Expression]]:
        """Extract all expressions from text.

        Args:
            text: Text potentially containing ${{ }} expressions.

        Returns:
            List of (original_match, parsed_expression) tuples.
        """
        ...
```

---

### 4.2 ExpressionEvaluator

```python
class ExpressionEvaluator(Protocol):
    """Runtime evaluator for expressions (FR-012)."""

    def evaluate(
        self,
        expr: Expression,
        context: WorkflowContext,
    ) -> Any:
        """Evaluate expression against context.

        Args:
            expr: Parsed expression.
            context: Workflow execution context.

        Returns:
            Resolved value.

        Raises:
            ExpressionEvaluationError: If evaluation fails (FR-013).
        """
        ...

    def evaluate_string(
        self,
        text: str,
        context: WorkflowContext,
    ) -> str:
        """Evaluate all expressions in text, returning string.

        Args:
            text: Text with embedded ${{ }} expressions.
            context: Workflow execution context.

        Returns:
            Text with expressions replaced by their values.

        Raises:
            ExpressionEvaluationError: If any expression fails.
        """
        ...
```

---

## 5. Error Types

```python
class WorkflowSerializationError(MaverickError):
    """Base exception for serialization errors."""
    pass

class WorkflowParseError(WorkflowSerializationError):
    """Error parsing workflow file (FR-017)."""

    errors: list[ValidationError]  # Structured error list
    source: str  # File path or "<string>"

class UnsupportedVersionError(WorkflowSerializationError):
    """Unsupported schema version (FR-018)."""

    version: str  # Requested version
    supported: list[str]  # List of supported versions

class ReferenceResolutionError(WorkflowSerializationError):
    """Failed to resolve component reference (FR-015)."""

    ref_type: str  # "action", "agent", etc.
    name: str  # The unresolved name
    location: str  # Where in workflow file

class ExpressionSyntaxError(WorkflowSerializationError):
    """Invalid expression syntax."""

    expression: str
    position: int
    message: str

class ExpressionEvaluationError(WorkflowSerializationError):
    """Expression evaluation failed (FR-013)."""

    expression: str
    reason: str  # "missing_input", "missing_step", "missing_field"
    path: str  # The access path that failed
```

---

## 6. Round-Trip Guarantee (FR-005)

The serialization system MUST satisfy:

```python
# For any valid workflow definition:
original = create_workflow_definition()

# Serialize to dict
dict_repr = writer.to_dict(original)

# Parse back
parsed = parser.parse_dict(dict_repr)

# Semantic equivalence
assert parsed.name == original.name
assert parsed.description == original.description
assert len(parsed.parameters) == len(original.parameters)
assert len(parsed.steps) == len(original.steps)
for orig_step, parsed_step in zip(original.steps, parsed.steps):
    assert orig_step.name == parsed_step.name
    assert orig_step.step_type == parsed_step.step_type
    # ... additional step-specific checks
```

---

## 7. Performance Contracts

| Operation | Max Time | Workflow Size |
|-----------|----------|---------------|
| parse_yaml | 2 seconds | 100 steps |
| validate_only | 1 second | 100 steps |
| to_yaml | 500ms | 100 steps |
| resolve references | 500ms | 100 steps |

If exceeded, log warning but continue (SC-005).
