# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed - BREAKING CHANGE

- **Python Decorator DSL (`@workflow`, `WorkflowEngine`)**: The decorator-based workflow DSL has been completely removed in favor of the YAML-based serialization DSL (`WorkflowFile`, `WorkflowFileExecutor`).

  **Migration Required**: All workflows must now be defined using YAML/JSON files. See `docs/migrating-from-decorator-dsl.md` for migration guidance.

  **Impact**: ~8,500 lines of code deleted across 43 files:
  - Core DSL modules: `builder.py`, `decorator.py`, `engine.py`
  - Step implementations: `conditional.py`, `error_handler.py`, `retry.py`, `rollback.py`, `subworkflow.py`
  - Test files: 9 test modules removed

  **Rationale**: The decorator DSL and serialization DSL were redundant, creating maintenance overhead and technical debt. The YAML-based approach provides:
  - Declarative syntax with better discoverability
  - Automatic schema validation
  - Shareability across teams (no Python required)
  - Visualization support (ASCII/Mermaid diagrams)
  - No mixing of workflow definition and execution logic

### Changed

- Workflow definitions now use `WorkflowFile` schema (YAML/JSON)
- Workflow execution now uses `WorkflowFileExecutor`
- Context builders now require exactly 2 parameters: `inputs: dict` and `step_results: dict`

### Migration Guide

See `docs/migrating-from-decorator-dsl.md` for detailed migration instructions and examples.

#### Before (Decorator DSL - Removed):
```python
from maverick.dsl import workflow, PythonStep

@workflow
async def my_workflow():
    result = await PythonStep("step1", action=my_action)()
    return result
```

#### After (YAML DSL - Current):
```yaml
version: "1.0"
name: my-workflow
steps:
  - name: step1
    type: python
    action: my_action
```

```python
from maverick.dsl.serialization import WorkflowFile, WorkflowFileExecutor

workflow = WorkflowFile.from_yaml(yaml_content)
executor = WorkflowFileExecutor()
async for event in executor.execute(workflow):
    # Handle events
    pass
```
