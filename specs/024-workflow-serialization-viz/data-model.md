# Data Model: Workflow Serialization & Visualization

**Feature Branch**: `024-workflow-serialization-viz`
**Date**: 2025-12-20

## Overview

This document defines the data models for workflow serialization, expression parsing, component registries, and visualization. All models use Pydantic for schema validation and dataclasses for immutable value objects.

---

## 1. Workflow Schema Models

### 1.1 WorkflowFile

Top-level schema for YAML/JSON workflow files.

```python
class WorkflowFile(BaseModel):
    """Top-level workflow file schema (FR-006)."""

    version: str  # Semver major.minor, e.g., "1.0"
    name: str  # Workflow identifier (1-64 chars, alphanumeric + dashes)
    description: str = ""  # Optional human-readable description
    inputs: dict[str, InputDefinition] = {}  # Named input declarations
    steps: list[StepRecord]  # Ordered step definitions
```

**Validation Rules**:
- `version`: Must match pattern `^\d+\.\d+$`
- `name`: Must match pattern `^[a-z][a-z0-9-]{0,63}$`
- `steps`: At least one step required; step names must be unique

---

### 1.2 InputDefinition

Declares a workflow input parameter (FR-007).

```python
class InputDefinition(BaseModel):
    """Workflow input declaration."""

    type: InputType  # string, integer, boolean, float, object, array
    required: bool = True
    default: Any = None  # Must match declared type if provided
    description: str = ""
```

**Validation Rules**:
- If `required=True`, `default` must be `None`
- If `default` is provided, must be valid for declared `type`

---

### 1.3 InputType

Enumeration of supported input types.

```python
class InputType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    FLOAT = "float"
    OBJECT = "object"  # dict[str, Any]
    ARRAY = "array"    # list[Any]
```

---

### 1.4 StepRecord

Base schema for step definitions with discriminated union (FR-008, FR-009).

```python
class StepRecord(BaseModel):
    """Step definition record (discriminated by type field)."""

    name: str  # Unique step name within workflow
    type: StepType  # python, agent, generate, validate, subworkflow, branch, parallel
    when: str | None = None  # Optional condition expression (FR-010)

    # Type-specific fields populated by subclasses
```

**Subclasses**:

| Type | Subclass | Additional Fields |
|------|----------|-------------------|
| `python` | `PythonStepRecord` | `action: str`, `args: list[Any]`, `kwargs: dict[str, Any]` |
| `agent` | `AgentStepRecord` | `agent: str`, `context: dict[str, Any] \| str` |
| `generate` | `GenerateStepRecord` | `generator: str`, `context: dict[str, Any] \| str` |
| `validate` | `ValidateStepRecord` | `stages: list[str]`, `retry: int`, `on_failure: StepRecord \| None` |
| `subworkflow` | `SubWorkflowStepRecord` | `workflow: str`, `inputs: dict[str, Any]` |
| `branch` | `BranchStepRecord` | `options: list[BranchOption]` |
| `parallel` | `ParallelStepRecord` | `steps: list[StepRecord]` |

---

### 1.5 PythonStepRecord

```python
class PythonStepRecord(StepRecord):
    """Python callable step."""

    type: Literal[StepType.PYTHON] = StepType.PYTHON
    action: str  # Fully qualified function name or registry key
    args: list[Any] = []  # Positional arguments (may contain expressions)
    kwargs: dict[str, Any] = {}  # Keyword arguments (may contain expressions)
```

---

### 1.6 AgentStepRecord

```python
class AgentStepRecord(StepRecord):
    """Agent invocation step."""

    type: Literal[StepType.AGENT] = StepType.AGENT
    agent: str  # Agent registry name
    context: dict[str, Any] | str  # Static dict or context builder name
```

---

### 1.7 GenerateStepRecord

```python
class GenerateStepRecord(StepRecord):
    """Text generation step."""

    type: Literal[StepType.GENERATE] = StepType.GENERATE
    generator: str  # Generator registry name
    context: dict[str, Any] | str  # Static dict or context builder name
```

---

### 1.8 ValidateStepRecord

```python
class ValidateStepRecord(StepRecord):
    """Validation step with retry."""

    type: Literal[StepType.VALIDATE] = StepType.VALIDATE
    stages: list[str] | str  # Stage list or config key
    retry: int = 3  # Max retry attempts (0 = no retry)
    on_failure: StepRecord | None = None  # Step to run before retry
```

---

### 1.9 SubWorkflowStepRecord

```python
class SubWorkflowStepRecord(StepRecord):
    """Sub-workflow invocation step."""

    type: Literal[StepType.SUBWORKFLOW] = StepType.SUBWORKFLOW
    workflow: str  # Workflow registry name or file path
    inputs: dict[str, Any] = {}  # Input values (may contain expressions)
```

---

### 1.10 BranchStepRecord

```python
class BranchStepRecord(StepRecord):
    """Branching step with condition-based selection."""

    type: Literal[StepType.BRANCH] = StepType.BRANCH
    options: list[BranchOptionRecord]  # Ordered condition → step pairs

class BranchOptionRecord(BaseModel):
    """Single branch option."""

    when: str  # Condition expression (evaluated in order)
    step: StepRecord  # Step to execute if condition true
```

---

### 1.11 ParallelStepRecord

```python
class ParallelStepRecord(StepRecord):
    """Parallel execution step."""

    type: Literal[StepType.PARALLEL] = StepType.PARALLEL
    steps: list[StepRecord]  # Steps to execute (names must be unique)
```

---

## 2. Expression Models

### 2.1 Expression

Parsed expression AST node.

```python
@dataclass(frozen=True, slots=True)
class Expression:
    """Parsed expression from ${{ ... }} syntax."""

    raw: str  # Original expression string
    kind: ExpressionKind  # input_ref, step_ref, config_ref, negation
    path: tuple[str, ...]  # Access path (e.g., ("inputs", "name"))
    negated: bool = False  # True if wrapped in 'not'
```

---

### 2.2 ExpressionKind

```python
class ExpressionKind(str, Enum):
    INPUT_REF = "input_ref"  # ${{ inputs.name }}
    STEP_REF = "step_ref"    # ${{ steps.x.output }}
```

---

### 2.3 ExpressionError

```python
@dataclass(frozen=True, slots=True)
class ExpressionError:
    """Expression parsing or evaluation error."""

    expression: str  # The expression that failed
    message: str  # Human-readable error message
    position: int = 0  # Character position in expression (if applicable)
```

---

## 3. Registry Models

### 3.1 ComponentRegistry

Unified facade for all component registries.

```python
@dataclass
class ComponentRegistry:
    """Aggregated component registries for workflow parsing."""

    actions: ActionRegistry  # Python callable registry
    agents: AgentRegistry  # MaverickAgent registry (existing)
    generators: GeneratorRegistry  # GeneratorAgent registry
    context_builders: ContextBuilderRegistry  # Context builder function registry
    workflows: WorkflowRegistry  # Named workflow registry

    strict: bool = True  # If False, defer resolution errors
    _deferred_errors: list[RegistryError] = field(default_factory=list)
```

---

### 3.2 ActionRegistry

```python
class ActionRegistry:
    """Registry for Python callables (actions)."""

    def register(self, name: str, fn: Callable | None = None) -> ...: ...
    def get(self, name: str) -> Callable: ...
    def list_names(self) -> list[str]: ...
    def has(self, name: str) -> bool: ...
```

---

### 3.3 RegistryError

```python
@dataclass(frozen=True, slots=True)
class RegistryError:
    """Registry resolution error."""

    registry_type: str  # "action", "agent", "generator", etc.
    name: str  # The name that failed to resolve
    location: str  # Where in the workflow file this was referenced
```

---

## 4. Visualization Models

### 4.1 WorkflowGraph

Intermediate graph representation for visualization.

```python
@dataclass(frozen=True, slots=True)
class WorkflowGraph:
    """Graph representation of workflow for visualization."""

    name: str
    description: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
```

---

### 4.2 GraphNode

```python
@dataclass(frozen=True, slots=True)
class GraphNode:
    """Node in workflow graph."""

    id: str  # Unique node ID (step name)
    label: str  # Display label
    step_type: StepType
    is_conditional: bool = False  # Has 'when' clause
    condition: str | None = None  # The 'when' expression
    children: tuple[GraphNode, ...] = ()  # For parallel/branch steps
```

---

### 4.3 GraphEdge

```python
@dataclass(frozen=True, slots=True)
class GraphEdge:
    """Edge in workflow graph."""

    source: str  # Source node ID
    target: str  # Target node ID
    label: str = ""  # Edge label (for conditions)
    edge_type: EdgeType = EdgeType.SEQUENTIAL

class EdgeType(str, Enum):
    SEQUENTIAL = "sequential"  # Normal flow
    CONDITIONAL = "conditional"  # Based on 'when' clause
    RETRY = "retry"  # Retry loop
    BRANCH = "branch"  # Branch option
```

---

## 5. Validation Result Models

### 5.1 ValidationResult

```python
@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of workflow file validation (FR-017)."""

    valid: bool
    errors: tuple[ValidationError, ...]
    warnings: tuple[ValidationWarning, ...]
```

---

### 5.2 ValidationError

```python
@dataclass(frozen=True, slots=True)
class ValidationError:
    """Validation error with location context."""

    code: str  # Error code (e.g., "E001", "E002")
    message: str  # Human-readable message
    path: str  # JSON path to error location (e.g., "steps[2].agent")
    suggestion: str = ""  # Fix suggestion if available
```

---

### 5.3 ValidationWarning

```python
@dataclass(frozen=True, slots=True)
class ValidationWarning:
    """Validation warning (non-fatal)."""

    code: str  # Warning code (e.g., "W001")
    message: str
    path: str
```

---

## 6. Entity Relationships

```
WorkflowFile
├── inputs: dict[str, InputDefinition]
├── steps: list[StepRecord]
│   ├── PythonStepRecord
│   │   └── action → ActionRegistry
│   ├── AgentStepRecord
│   │   └── agent → AgentRegistry
│   ├── GenerateStepRecord
│   │   └── generator → GeneratorRegistry
│   ├── ValidateStepRecord
│   │   └── on_failure → StepRecord (recursive)
│   ├── SubWorkflowStepRecord
│   │   └── workflow → WorkflowRegistry
│   ├── BranchStepRecord
│   │   └── options: list[BranchOptionRecord]
│   │       └── step → StepRecord (recursive)
│   └── ParallelStepRecord
│       └── steps: list[StepRecord] (recursive)
└── (validation) → ValidationResult

StepRecord.when → Expression (parsed at load time)
StepRecord.args/kwargs/context → may contain Expression strings

Expression
├── kind: ExpressionKind
├── path: tuple[str, ...]
└── (evaluation) → WorkflowContext → Any

WorkflowGraph
├── nodes: tuple[GraphNode, ...]
│   └── children: tuple[GraphNode, ...] (for parallel/branch)
└── edges: tuple[GraphEdge, ...]

ComponentRegistry
├── actions: ActionRegistry
├── agents: AgentRegistry
├── generators: GeneratorRegistry
├── context_builders: ContextBuilderRegistry
└── workflows: WorkflowRegistry
```

---

## 7. State Transitions

### 7.1 Workflow Parsing States

```
[YAML/JSON String]
       │
       ▼ parse_yaml()
[Raw Dict]
       │
       ▼ validate_schema()
[WorkflowFile (Pydantic)]
       │
       ▼ resolve_references(registry)
[WorkflowDefinition + StepDefinitions]
       │
       ▼ build_graph()
[WorkflowGraph]
       │
       ├─ to_mermaid()
       │  └─ [Mermaid String]
       └─ to_ascii()
          └─ [ASCII String]
```

### 7.2 Expression Lifecycle

```
[Raw Expression String: "${{ steps.review.output.findings }}"]
       │
       ▼ parse_expression()
[Expression AST]
       │
       ▼ validate_references(workflow_file)  # Static check
[Validated Expression]
       │
       ▼ evaluate(context)  # Runtime
[Resolved Value]
```

---

## 8. Pydantic Discriminated Union Configuration

For step type discrimination:

```python
from pydantic import BaseModel, Field
from typing import Annotated, Union

StepRecordUnion = Annotated[
    Union[
        PythonStepRecord,
        AgentStepRecord,
        GenerateStepRecord,
        ValidateStepRecord,
        SubWorkflowStepRecord,
        BranchStepRecord,
        ParallelStepRecord,
    ],
    Field(discriminator="type"),
]

class WorkflowFile(BaseModel):
    # ...
    steps: list[StepRecordUnion]
```

This enables Pydantic to automatically select the correct subclass based on the `type` field value.
