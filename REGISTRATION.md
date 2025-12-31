# Agent and Generator Registration

This document describes the registration system for agents and generators used by DSL-based workflows.

## Overview

The DSL workflow system requires agents and generators to be registered in the `ComponentRegistry` before they can be referenced by name in YAML workflow files. This registration happens through dedicated registration modules.

## Registration Modules

### Agents Registration

**Location**: `src/maverick/library/agents/__init__.py`

**Function**: `register_all_agents(registry: ComponentRegistry) -> None`

**Registered Agents**:
- `implementer` → `ImplementerAgent` - Executes tasks from task files
- `code_reviewer` → `CodeReviewerAgent` - Performs code review
- `issue_fixer` → `IssueFixerAgent` - Fixes GitHub issues
- `validation_fixer` → `FixerAgent` - Applies validation fixes

**Not Yet Registered**:
- `issue_analyzer` - Referenced in refuel.yaml but not yet implemented

### Generators Registration

**Location**: `src/maverick/library/generators/__init__.py`

**Function**: `register_all_generators(registry: ComponentRegistry) -> None`

**Registered Generators**:
- `commit_message_generator` → `CommitMessageGenerator` - Generates commit messages
- `pr_body_generator` → `PRDescriptionGenerator` - Generates PR descriptions
- `pr_title_generator` → `PRTitleGenerator` - Generates PR titles

## Usage in Workflows

### Example: Agent Step
```yaml
- name: implement
  type: agent
  agent: implementer  # Resolved via registry
  context:
    task_file: ${{ inputs.task_file }}
```

### Example: Generate Step
```yaml
- name: generate_message
  type: generate
  generator: commit_message_generator  # Resolved via registry
  context: commit_message_context
```

## Integration Points

### Main CLI (`src/maverick/main.py`)

The `create_registered_registry()` helper function creates a fully-initialized registry:

```python
def create_registered_registry(strict: bool = False) -> ComponentRegistry:
    """Create a ComponentRegistry with all built-in components registered."""
    registry = ComponentRegistry(strict=strict)
    
    # Register all built-in components
    register_all_actions(registry)
    register_all_agents(registry)
    register_all_generators(registry)
    register_all_context_builders(registry)
    
    return registry
```

This function is called:
1. When validating workflow files with `--strict` flag
2. When executing workflows via `maverick workflow run`

### Workflow Classes

The `FlyWorkflow` and `RefuelWorkflow` classes accept an optional `registry` parameter in their constructors. If not provided, they create an empty registry (which won't work for DSL execution). Callers should use `create_registered_registry()`.

## Adding New Agents or Generators

### Adding an Agent

1. Implement the agent class (e.g., `IssueAnalyzerAgent`)
2. Add import to `src/maverick/library/agents/__init__.py`
3. Add registration call in `register_all_agents()`:
   ```python
   registry.agents.register("issue_analyzer", IssueAnalyzerAgent)
   ```

### Adding a Generator

1. Implement the generator class (e.g., `PRCommentGenerator`)
2. Add import to `src/maverick/library/generators/__init__.py`
3. Add registration call in `register_all_generators()`:
   ```python
   registry.generators.register("pr_comment_generator", PRCommentGenerator)
   ```

## Testing

Unit tests verify registration:
- `tests/unit/library/test_agent_registration.py` - Tests agent registration
- `tests/unit/library/test_generator_registration.py` - Tests generator registration

Each test suite verifies:
- All expected components are registered
- Components can be retrieved by name
- Components can be instantiated
- Correct class types are registered

## Workflow YAML References

Components are referenced in these workflow files:

**Agents**:
- `implementer` - fly.yaml
- `code_reviewer` - fly.yaml, review.yaml
- `issue_fixer` - quick_fix.yaml, process_single_issue.yaml
- `validation_fixer` - validate-and-fix fragment (via input parameter)

**Generators**:
- `commit_message_generator` - commit-and-push fragment
- `pr_body_generator` - create-pr-with-summary fragment
- `pr_title_generator` - create-pr-with-summary fragment
