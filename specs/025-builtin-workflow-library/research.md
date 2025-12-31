# Research: Built-in Workflow Library

**Branch**: `025-builtin-workflow-library` | **Date**: 2025-12-20

## Research Questions & Findings

### 1. How should built-in workflows be packaged and discovered?

**Decision**: Package built-in workflows as YAML files within `src/maverick/library/workflows/` using `importlib.resources` for access.

**Rationale**:
- YAML format aligns with user-defined workflows (spec 024)
- `importlib.resources` is the standard Python mechanism for accessing package data
- Allows built-ins to serve as canonical examples users can copy and modify
- Consistent with existing pattern for accessing package resources

**Alternatives Considered**:
1. **Python-decorated workflow functions**: Rejected because user workflows will primarily be YAML, and built-ins should match user format for consistency
2. **External workflow repository**: Rejected as it adds network dependency and complexity

### 2. How should multi-location discovery work?

**Decision**: Implement a `WorkflowDiscovery` class that scans locations in precedence order (project → user → built-in) and builds a unified registry.

**Rationale**:
- Matches config loading precedence (spec 001: project → user → defaults)
- Clear override semantics: project-specific customizations take precedence
- Single point of discovery enables consistent behavior across CLI/TUI

**Implementation Approach**:
```python
class WorkflowDiscovery:
    def discover(self) -> DiscoveryResult:
        # 1. Scan built-in: src/maverick/library/workflows/*.yaml
        # 2. Scan user: ~/.config/maverick/workflows/*.yaml
        # 3. Scan project: .maverick/workflows/*.yaml
        # Apply override: later locations override earlier by name
```

**Discovery Locations** (FR-013):
- Built-in: `maverick.library.workflows` package resource
- User: `~/.config/maverick/workflows/` (XDG-compliant, confirmed in spec clarifications)
- Project: `.maverick/workflows/` in project root

### 3. How should override precedence conflicts be handled?

**Decision**: Fail discovery with a clear error listing both conflicting file paths when two workflows share the same name at the same precedence level (FR-016).

**Rationale**:
- Explicit failure prevents silent precedence ambiguity
- Users need to know which file to modify
- Consistent with "fail fast" principle

**Example Error**:
```
WorkflowConflictError: Multiple workflows named 'fly' at project level:
  - .maverick/workflows/fly.yaml
  - .maverick/workflows/fly-v2.yaml
```

### 4. How should workflow fragments be implemented?

**Decision**: Implement fragments as sub-workflows using the existing `SubWorkflowStep` from spec 022/023.

**Rationale**:
- SubWorkflowStep already supports workflow invocation with inputs
- Fragments follow same override precedence as workflows (FR-012a)
- No new step type needed - reuse existing infrastructure

**Fragment Location**: `src/maverick/library/fragments/` with same discovery precedence.

**Fragment Invocation in YAML**:
```yaml
- name: validate-and-fix
  type: subworkflow
  workflow: validate_and_fix  # Fragment name
  inputs:
    stages: ${{ inputs.validation_stages }}
    max_attempts: 3
```

### 5. How should templates be implemented for scaffolding?

**Decision**: Use Jinja2 templates stored in `src/maverick/library/templates/` with a `TemplateScaffolder` class.

**Rationale**:
- Jinja2 is widely used and already a common dependency pattern
- Templates can include placeholders for workflow name, description, and customization points
- Supports both YAML and Python output formats (FR-022)

**Template Variables**:
```python
@dataclass
class TemplateContext:
    name: str           # Workflow name (e.g., "my-workflow")
    description: str    # User-provided description
    author: str         # Optional author name
    date: str           # Generation date
```

**CLI Command** (FR-017):
```bash
maverick workflow new my-workflow --template full --format yaml
maverick workflow new my-workflow --template basic --format python
```

### 6. What are the input specifications for each built-in workflow?

**Fly Workflow** (FR-004):
| Input | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| branch_name | string | yes | - | Feature branch name |
| task_file | string | no | auto-detect | Path to tasks.md |
| skip_review | boolean | no | false | Skip code review stage |

**Refuel Workflow** (FR-005):
| Input | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| label | string | no | "tech-debt" | Issue label to filter |
| limit | integer | no | 5 | Maximum issues to process |
| parallel | boolean | no | true | Process issues in parallel |

**Review Workflow** (FR-006):
| Input | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| pr_number | integer | no | - | PR number (auto-detect if omitted) |
| base_branch | string | no | "main" | Base branch for comparison |

**Validate Workflow** (FR-007):
| Input | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| fix | boolean | no | true | Attempt automatic fixes |
| max_attempts | integer | no | 3 | Maximum fix attempts |

**Quick Fix Workflow** (FR-008):
| Input | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| issue_number | integer | yes | - | GitHub issue number |

### 7. What are the fragment input specifications?

**validate_and_fix Fragment** (FR-010):
| Input | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| stages | array | no | ["format", "lint", "typecheck", "test"] | Validation stages |
| max_attempts | integer | no | 3 | Maximum retry attempts |
| fixer_agent | string | no | "validation_fixer" | Agent for fixes |

**commit_and_push Fragment** (FR-011):
| Input | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| message | string | no | - | Commit message (auto-generate if omitted) |
| push | boolean | no | true | Push after commit |

**create_pr_with_summary Fragment** (FR-012):
| Input | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| base_branch | string | no | "main" | PR base branch |
| draft | boolean | no | false | Create as draft PR |
| title | string | no | - | PR title (auto-generate if omitted) |

### 8. How should the CLI be extended for workflow new?

**Decision**: Extend the existing `workflow` command group with a `new` subcommand.

**Rationale**:
- Consistent with existing CLI structure (`maverick workflow list/show/validate/run`)
- Click's command groups support easy extension
- Follows convention of `<noun> new` for scaffolding

**Command Signature**:
```python
@workflow.command("new")
@click.argument("name")
@click.option("--template", type=click.Choice(["basic", "full", "parallel"]), default="basic")
@click.option("--format", type=click.Choice(["yaml", "python"]), default="yaml")
@click.option("--output-dir", type=click.Path(), default=".maverick/workflows")
def workflow_new(name: str, template: str, format: str, output_dir: str) -> None:
    """Create a new workflow from a template."""
```

### 9. How should discovery performance be optimized?

**Decision**: Use lazy loading with metadata caching.

**Rationale**:
- Discovery < 500ms for 100 files (performance goal)
- Only parse YAML headers initially (version, name, description, inputs)
- Full parsing deferred until workflow execution
- Cache metadata in memory during session

**Implementation**:
```python
@dataclass
class WorkflowMetadata:
    name: str
    version: str
    description: str
    inputs: dict[str, InputDefinition]
    file_path: Path
    source: Literal["builtin", "user", "project"]

class LazyWorkflowLoader:
    def load_metadata(self, path: Path) -> WorkflowMetadata:
        # Parse only header section
        ...

    def load_full(self, metadata: WorkflowMetadata) -> WorkflowFile:
        # Parse complete workflow on demand
        ...
```

### 10. How should invalid workflow files be handled during discovery?

**Decision**: Log a warning with file path and error details, skip the file, and continue discovering remaining workflows (FR-016a).

**Rationale**:
- Consistent with "fail gracefully" constitution principle
- One bad file shouldn't prevent discovery of valid workflows
- Warnings provide visibility without blocking

**Implementation**:
```python
try:
    metadata = loader.load_metadata(file_path)
    discovered.append(metadata)
except WorkflowParseError as e:
    logger.warning(f"Skipping invalid workflow {file_path}: {e.message}")
    skipped.append(SkippedWorkflow(path=file_path, error=str(e)))
```

## Integration Points

### Existing Infrastructure to Leverage

1. **WorkflowFile schema** (`dsl/serialization/schema.py`): Defines YAML structure
2. **ComponentRegistry** (`dsl/serialization/registry.py`): Registration pattern to extend
3. **parse_workflow** (`dsl/serialization/parser.py`): YAML parsing with validation
4. **WorkflowFileExecutor** (`dsl/serialization/executor.py`): Execution engine
5. **Click CLI** (`main.py`): Extend workflow command group

### New Modules Required

1. `maverick.dsl.discovery`: Multi-location workflow discovery
   - `WorkflowLocator`: File scanning
   - `WorkflowLoader`: Parsing with lazy loading
   - `DiscoveryRegistry`: Aggregation with precedence

2. `maverick.library`: Built-in workflow library
   - `workflows/`: YAML workflow definitions
   - `fragments/`: Reusable sub-workflows
   - `templates/`: Jinja2 scaffolding templates

3. `maverick.cli.scaffold`: Template-based scaffolding
   - `TemplateScaffolder`: Generate new workflows

## Dependencies

### Required (Existing)
- PyYAML: YAML parsing
- Pydantic: Schema validation
- Click: CLI framework
- pathlib: Path handling

### Required (New)
- Jinja2: Template rendering for scaffolding

### Optional
- None identified

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Discovery performance regression | Low | Medium | Lazy loading + caching |
| Template versioning conflicts | Low | Low | Version templates with workflow DSL version |
| Fragment circular references | Medium | High | Detect and error at parse time |
| Override confusion for users | Medium | Medium | Clear `workflow show` output with source |

## Next Steps

1. **Phase 1**: Create data-model.md with entity definitions
2. **Phase 1**: Create contracts for discovery and scaffold APIs
3. **Phase 1**: Create quickstart.md with usage examples
4. **Phase 2**: Generate tasks.md from design artifacts
