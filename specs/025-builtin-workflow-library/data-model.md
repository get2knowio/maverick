# Data Model: Built-in Workflow Library

**Branch**: `025-builtin-workflow-library` | **Date**: 2025-12-20

## Entity Definitions

### 1. WorkflowSource (Enum)

Identifies the origin location of a discovered workflow.

```python
from enum import Enum

class WorkflowSource(str, Enum):
    """Origin location of a workflow definition."""
    BUILTIN = "builtin"   # Packaged with Maverick
    USER = "user"         # ~/.config/maverick/workflows/
    PROJECT = "project"   # .maverick/workflows/
```

**Precedence Order**: PROJECT > USER > BUILTIN (higher overrides lower)

---

### 2. WorkflowMetadata

Lightweight metadata parsed from workflow file headers for discovery.

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True, slots=True)
class WorkflowMetadata:
    """Metadata for a discovered workflow.

    Parsed from workflow file header without full validation.
    Used for listing and display operations.
    """
    name: str
    version: str
    description: str
    input_names: tuple[str, ...]  # Just names for quick display
    step_count: int
    file_path: Path
    source: WorkflowSource

    @property
    def qualified_name(self) -> str:
        """Return source-qualified name for disambiguation."""
        return f"{self.source.value}:{self.name}"
```

**Validation Rules**:
- `name`: Must match `^[a-z][a-z0-9-]{0,63}$` (from WorkflowFile schema)
- `version`: Must match `^\d+\.\d+$`
- `file_path`: Must exist and be readable

---

### 3. DiscoveredWorkflow

Full workflow definition with source tracking.

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True, slots=True)
class DiscoveredWorkflow:
    """A fully parsed workflow with source information.

    Contains the complete WorkflowFile plus source tracking
    for precedence and override display.
    """
    workflow: WorkflowFile  # From dsl/serialization/schema.py
    file_path: Path
    source: WorkflowSource
    overrides: tuple[Path, ...]  # Paths of overridden workflows (lower precedence)
```

**Relationships**:
- Contains one `WorkflowFile` (existing schema)
- May override zero or more workflows with same name from lower-precedence sources

---

### 4. SkippedWorkflow

Represents a workflow file that failed parsing during discovery.

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True, slots=True)
class SkippedWorkflow:
    """A workflow file that was skipped due to errors.

    Captures error context for reporting while allowing
    discovery to continue for remaining files.
    """
    file_path: Path
    error_message: str
    error_type: str  # e.g., "parse_error", "schema_error", "io_error"
    line_number: int | None = None
```

---

### 5. DiscoveryResult

Aggregated result of workflow discovery across all locations.

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Result of scanning all workflow locations.

    Contains the resolved workflow registry plus metadata
    about the discovery process for debugging and display.
    """
    workflows: tuple[DiscoveredWorkflow, ...]
    fragments: tuple[DiscoveredWorkflow, ...]
    skipped: tuple[SkippedWorkflow, ...]
    locations_scanned: tuple[Path, ...]
    discovery_time_ms: float

    @property
    def workflow_names(self) -> tuple[str, ...]:
        """Return sorted unique workflow names."""
        return tuple(sorted({w.workflow.name for w in self.workflows}))

    @property
    def fragment_names(self) -> tuple[str, ...]:
        """Return sorted unique fragment names."""
        return tuple(sorted({f.workflow.name for f in self.fragments}))

    def get_workflow(self, name: str) -> DiscoveredWorkflow | None:
        """Lookup workflow by name (returns highest precedence)."""
        for w in self.workflows:
            if w.workflow.name == name:
                return w
        return None

    def get_fragment(self, name: str) -> DiscoveredWorkflow | None:
        """Lookup fragment by name (returns highest precedence)."""
        for f in self.fragments:
            if f.workflow.name == name:
                return f
        return None
```

---

### 6. WorkflowConflict

Represents a same-name conflict at the same precedence level.

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True, slots=True)
class WorkflowConflict:
    """Conflict when multiple workflows share name at same precedence.

    Discovery must fail when this occurs (FR-016).
    """
    name: str
    source: WorkflowSource
    conflicting_paths: tuple[Path, ...]

    def to_error_message(self) -> str:
        """Generate human-readable error message."""
        paths_str = "\n  - ".join(str(p) for p in self.conflicting_paths)
        return (
            f"Multiple workflows named '{self.name}' at {self.source.value} level:\n"
            f"  - {paths_str}"
        )
```

---

### 7. TemplateType (Enum)

Available scaffolding template types.

```python
from enum import Enum

class TemplateType(str, Enum):
    """Scaffolding template categories."""
    BASIC = "basic"       # Linear workflow with few steps
    FULL = "full"         # Complete workflow with validation/review/PR
    PARALLEL = "parallel" # Demonstrates parallel step interface
```

---

### 8. TemplateFormat (Enum)

Output format for scaffolded workflows.

```python
from enum import Enum

class TemplateFormat(str, Enum):
    """Output format for scaffolded workflows."""
    YAML = "yaml"    # YAML workflow file (default)
    PYTHON = "python"  # Python workflow function
```

---

### 9. ScaffoldRequest

Request parameters for creating a new workflow from template.

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True, slots=True)
class ScaffoldRequest:
    """Request to scaffold a new workflow.

    Contains all parameters needed to generate a new workflow
    file from a template.
    """
    name: str                           # Workflow name
    template: TemplateType              # Template to use
    format: TemplateFormat              # Output format
    output_dir: Path                    # Target directory
    description: str = ""               # Optional description
    author: str = ""                    # Optional author

    @property
    def output_path(self) -> Path:
        """Compute output file path."""
        ext = ".yaml" if self.format == TemplateFormat.YAML else ".py"
        return self.output_dir / f"{self.name}{ext}"
```

**Validation Rules**:
- `name`: Must match workflow naming convention `^[a-z][a-z0-9-]{0,63}$`
- `output_dir`: Must be writable
- `output_path`: Must not exist (or user confirms overwrite)

---

### 10. ScaffoldResult

Result of scaffold operation.

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True, slots=True)
class ScaffoldResult:
    """Result of scaffolding operation."""
    success: bool
    output_path: Path | None
    content: str | None       # Generated content (for preview)
    error: str | None
```

---

## Entity Relationships

```
                    ┌─────────────────────┐
                    │   DiscoveryResult   │
                    │                     │
                    │ workflows: [...]    │
                    │ fragments: [...]    │
                    │ skipped: [...]      │
                    └─────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
    ┌─────────────────┐ ┌───────────────┐ ┌────────────────┐
    │DiscoveredWorkflow│ │DiscoveredWorkflow│ │SkippedWorkflow │
    │   (workflow)    │ │  (fragment)   │ │                │
    │                 │ │               │ │ file_path      │
    │ workflow: WF    │ │ workflow: WF  │ │ error_message  │
    │ source: enum    │ │ source: enum  │ │ error_type     │
    │ overrides: [...│ │ overrides:[...│ └────────────────┘
    └─────────────────┘ └───────────────┘
              │               │
              ▼               ▼
    ┌─────────────────────────────────┐
    │         WorkflowFile            │
    │   (from dsl/serialization)      │
    │                                 │
    │ version, name, description      │
    │ inputs: {name: InputDefinition} │
    │ steps: [StepRecordUnion]        │
    └─────────────────────────────────┘
```

---

## State Transitions

### Workflow Discovery States

```
[File Found] ──parse──▶ [Metadata Loaded] ──validate──▶ [Fully Parsed]
     │                         │                              │
     │ (IO error)              │ (parse error)               │ (valid)
     ▼                         ▼                              ▼
[Skipped:io_error]    [Skipped:parse_error]           [DiscoveredWorkflow]
```

### Scaffold States

```
[Request] ──validate──▶ [Validated] ──render──▶ [Content Generated]
    │                        │                         │
    │ (invalid name)         │ (template error)       │ (write)
    ▼                        ▼                         ▼
[Error:validation]    [Error:render]           [File Written]
                                                      │
                                               (path conflict)
                                                      ▼
                                              [Error:exists]
```

---

## Validation Rules Summary

| Entity | Field | Rule |
|--------|-------|------|
| WorkflowMetadata | name | `^[a-z][a-z0-9-]{0,63}$` |
| WorkflowMetadata | version | `^\d+\.\d+$` |
| WorkflowMetadata | file_path | Exists and readable |
| ScaffoldRequest | name | `^[a-z][a-z0-9-]{0,63}$` |
| ScaffoldRequest | output_dir | Exists and writable |
| ScaffoldRequest | output_path | Does not exist (unless overwrite) |
| WorkflowConflict | conflicting_paths | Length >= 2 |

---

## Index Definitions

For efficient lookup in the discovery registry:

| Index | Key | Value | Purpose |
|-------|-----|-------|---------|
| workflows_by_name | workflow.name | DiscoveredWorkflow | O(1) workflow lookup |
| fragments_by_name | fragment.name | DiscoveredWorkflow | O(1) fragment lookup |
| all_by_source | source | list[DiscoveredWorkflow] | Filter by origin |

---

## Migration Notes

### New Tables/Structures
All entities are new for this feature. No migration from existing structures required.

### Integration with Existing Structures
- `WorkflowFile`: Reused from `maverick.dsl.serialization.schema`
- `InputDefinition`: Reused from `maverick.dsl.serialization.schema`
- `StepRecordUnion`: Reused from `maverick.dsl.serialization.schema`
- `ComponentRegistry`: Extended with `DiscoveryRegistry` integration
