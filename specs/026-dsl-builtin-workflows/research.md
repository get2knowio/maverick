# Research: DSL-Based Built-in Workflow Implementation

**Spec**: 026-dsl-builtin-workflows
**Date**: 2025-12-20

This document captures research findings to resolve technical questions and inform implementation decisions for the DSL-based built-in workflows.

## Research Topics

### 1. Executor Step Type Implementation Gaps

**Question**: Which step types are not yet implemented in `WorkflowFileExecutor` and how should they be completed?

**Findings**:
From `/workspaces/maverick/src/maverick/dsl/serialization/executor.py`:
- `PythonStepRecord`: ✅ Implemented - looks up action in registry, calls with resolved kwargs
- `AgentStepRecord`: ⚠️ Partial - raises `NotImplementedError` after checking registry
- `GenerateStepRecord`: ⚠️ Partial - raises `NotImplementedError` after checking registry
- `ValidateStepRecord`: ⚠️ Stub - returns `{"success": True, "stages": []}`
- `SubWorkflowStepRecord`: ✅ Implemented - supports both `WorkflowFile` and decorated functions
- `BranchStepRecord`: ❌ Not implemented - raises `NotImplementedError`
- `ParallelStepRecord`: ❌ Not implemented - raises `NotImplementedError`

**Decision**: Implement missing step types in executor:
1. **AgentStep**: Resolve agent from registry, build context, call `agent.execute(context)`
2. **GenerateStep**: Resolve generator from registry, call `generator.generate(context)`
3. **ValidateStep**: Use `ValidationRunner` from config/registry to execute stages
4. **BranchStep**: Evaluate options in order, execute first matching step
5. **ParallelStep**: Execute steps using `asyncio.gather()` (currently sequential fallback acceptable)

**Rationale**: The executor needs to support all step types used in built-in workflows. Agent/generate steps require integration with registered components.

**Alternatives Considered**:
- Leave agent/generate as NotImplemented → Rejected: Workflows can't execute
- Inline agent execution in YAML → Rejected: Violates separation of concerns

---

### 2. Python Action Registration Pattern

**Question**: How should Python actions be registered and discovered for workflow execution?

**Findings**:
From `/workspaces/maverick/src/maverick/dsl/serialization/registry.py`:
- `ComponentRegistry` has `TypedRegistry[Callable[..., Any]]` for actions
- Actions registered via `registry.actions.register(name, callable)`
- Actions resolved via `registry.actions.get(name)` → returns callable
- Action names in YAML match registered names (e.g., `action: git_commit`)

From `/workspaces/maverick/src/maverick/dsl/serialization/executor.py`:
```python
action = self._registry.actions.get(step.action)
result = action(**resolved_inputs)
if inspect.iscoroutine(result):
    result = await result
```

**Decision**: Create `src/maverick/library/actions/` module with:
1. Individual modules per domain: `git.py`, `github.py`, `validation.py`, etc.
2. Each module exports functions matching action names in YAML
3. `__init__.py` provides `register_all_actions(registry: ComponentRegistry)` helper
4. Actions are registered at workflow execution startup

**Rationale**: Follows existing registry pattern; keeps actions organized by domain.

**Alternatives Considered**:
- Decorator-based auto-registration → Rejected: Implicit; harder to trace
- Global action dict → Rejected: Violates dependency injection principle

---

### 3. Agent/Generator Registration for Workflow Steps

**Question**: How should agents and generators be registered for use in `agent:` and `generate:` step types?

**Findings**:
From `/workspaces/maverick/src/maverick/agents/registry.py`:
- `AgentRegistry` with `register(name, factory)` pattern
- Agents looked up by name string

From `/workspaces/maverick/src/maverick/dsl/serialization/registry.py`:
- `ComponentRegistry` has `generators: TypedRegistry[Callable[..., Any]]`
- Generators are callables that return generated content

From workflow YAML files:
```yaml
- name: implement
  type: agent
  agent: implementer          # Looks up "implementer" in agent registry
  context:
    task_file: ${{ inputs.task_file }}
```

**Decision**:
1. Extend `ComponentRegistry` with `agents: TypedRegistry[Type[MaverickAgent]]` registry
2. Register agent classes by name: `implementer`, `code_reviewer`, `issue_fixer`, etc.
3. Register generator instances: `commit_message_generator`, `pr_body_generator`, etc.
4. Executor creates agent instances and calls `await agent.execute(context)`
5. Executor calls generators with resolved context dict

**Rationale**: Matches existing patterns; agents are classes (need instantiation), generators are already instances.

**Alternatives Considered**:
- Register agent instances → Rejected: Agents may need per-execution config
- Inline agent definitions in YAML → Rejected: Violates separation of concerns

---

### 4. Context Builder Implementation

**Question**: How should context builders work for dynamic context construction in agent/generate steps?

**Findings**:
From workflow YAML:
```yaml
- name: review
  type: agent
  agent: code_reviewer
  context: review_context      # String reference to context builder
```

From `/workspaces/maverick/src/maverick/dsl/types.py`:
```python
ContextBuilder: TypeAlias = Callable[["WorkflowContext"], Awaitable[dict[str, Any]]]
```

From `/workspaces/maverick/src/maverick/dsl/serialization/executor.py`:
```python
if isinstance(step.context, dict):
    # Resolve expressions in dict
else:
    # Context is a string reference (context builder name)
    resolved["_context_builder"] = step.context
```

**Decision**: Create `src/maverick/dsl/context_builders.py` with:
1. Named context builder functions: `async def review_context(ctx) -> dict`
2. Register builders in ComponentRegistry: `registry.context_builders.register(name, func)`
3. Builders receive `WorkflowContext` with `inputs` and `results` from prior steps
4. Builders construct agent-specific context dicts (gather diff, files, etc.)

Context builders needed:
- `implementation_context`: Task file content, project structure, spec artifacts
- `review_context`: Git diff, changed files, project conventions
- `issue_fix_context`: Issue details, related files, project context
- `commit_message_context`: Git diff, git log, staged files
- `pr_body_context`: Commits, diff stats, validation results, task summary
- `pr_title_context`: Commits, branch name, task summary

**Rationale**: Context builders encapsulate the logic for gathering context-specific data (file reads, git commands, etc.) outside of YAML definitions.

**Alternatives Considered**:
- Inline context gathering in YAML kwargs → Rejected: Too complex for YAML
- Always use static context dicts → Rejected: Many contexts need dynamic data

---

### 5. Dry-Run Mode Implementation

**Question**: How should `dry_run` mode be implemented for fly and refuel workflows?

**Findings**:
From spec.md FR-008a:
> When dry_run=True, the fly workflow MUST log planned operations for each stage without executing branches, commits, agent invocations, or PRs.

From existing workflow patterns:
- Dry-run should skip side effects but still emit progress events
- Step results should indicate what would have happened

**Decision**: Implement dry-run as conditional step skipping:
1. Add `dry_run` input to fly/refuel workflow definitions
2. Use `when: ${{ not inputs.dry_run }}` on steps with side effects
3. Add parallel "dry_run" steps that log planned operations:
   ```yaml
   - name: commit_and_push_dry
     type: python
     action: log_dry_run
     when: ${{ inputs.dry_run }}
     kwargs:
       operation: "commit_and_push"
       details: "Would commit changes and push to ${{ inputs.branch_name }}"
   ```
4. Create `log_dry_run` action that returns informational dict without side effects

**Rationale**: Uses existing conditional step mechanism; keeps dry-run logic in YAML; avoids modifying Python actions.

**Alternatives Considered**:
- Pass dry_run flag to each action → Rejected: Every action needs dry_run handling
- Global dry_run context variable → Rejected: Harder to trace which steps skip

---

### 6. Progress Event Mapping for TUI

**Question**: How do DSL progress events map to workflow-specific TUI events?

**Findings**:
From `/workspaces/maverick/src/maverick/dsl/events.py`:
- `WorkflowStarted`, `WorkflowCompleted`
- `StepStarted`, `StepCompleted`
- `CheckpointSaved`, `RollbackStarted`, `RollbackCompleted`

From `/workspaces/maverick/src/maverick/workflows/fly.py`:
- `FlyWorkflowStarted`, `FlyStageStarted`, `FlyStageCompleted`, etc.
- Custom events with workflow-specific metadata

**Decision**: Create adapter layer that:
1. DSL workflows yield generic `ProgressEvent` types
2. Wrapper in `FlyWorkflow`/`RefuelWorkflow` translates to typed events:
   ```python
   async def execute(self, inputs: FlyInputs) -> AsyncIterator[FlyProgressEvent]:
       workflow = self._load_workflow("fly")
       async for event in self._executor.execute(workflow, inputs.model_dump()):
           yield self._translate_event(event, inputs)
   ```
3. Translation maps step names to stages: `"implement"` → `IMPLEMENTATION`

**Rationale**: Maintains backward compatibility with existing TUI consumers while leveraging DSL execution.

**Alternatives Considered**:
- Emit only DSL events → Rejected: Breaks existing TUI integration
- Dual event emission → Rejected: Redundant, complex

---

### 7. Error Handling in Sub-Workflows

**Question**: How should errors in sub-workflows propagate to parent workflows?

**Findings**:
From spec.md FR-104:
> When a sub-workflow fails, the parent workflow fails and reports the sub-workflow's error in its result.

From executor implementation:
```python
async for event in sub_executor.execute(workflow, inputs=sub_inputs):
    if hasattr(event, "result"):
        result = event.result
return result
```

**Decision**:
1. Sub-workflow execution captures `WorkflowResult` from child
2. If `sub_result.success == False`, raise `SubWorkflowError(sub_result)`
3. Parent step catches this and records failure in `StepResult`
4. Parent workflow stops (fail-fast) or continues based on step config

Error handling config per step:
```yaml
- name: validate_and_fix
  type: subworkflow
  workflow: validate-and-fix
  on_error: continue   # Optional: continue to next step even on failure
```

**Rationale**: Matches existing error handling patterns; provides control over fail-fast vs continue behavior.

**Alternatives Considered**:
- Always fail-fast on sub-workflow error → Rejected: Some workflows need to continue
- Ignore sub-workflow errors → Rejected: Violates fail gracefully principle

---

### 8. Checkpoint Integration

**Question**: How should checkpointing work with YAML-defined workflows?

**Findings**:
From `/workspaces/maverick/src/maverick/dsl/checkpoint/`:
- `CheckpointData`: workflow_name, step_name, inputs, step_results, metadata
- `FileCheckpointStore`: saves to `.maverick/checkpoints/{workflow}_{timestamp}.json`

From `/workspaces/maverick/src/maverick/dsl/steps/checkpoint.py`:
- `CheckpointStep` saves current state to store

From spec.md FR-041:
> All workflows MUST support checkpointing for resumability at key stages.

**Decision**: Add checkpoint steps after major stages in workflow YAML:
```yaml
- name: implement
  type: agent
  agent: implementer
  context: implementation_context

- name: checkpoint_after_implement
  type: checkpoint
  description: "After implementation, before validation"
```

Resume functionality:
1. CLI option: `maverick workflow run fly --resume <checkpoint-file>`
2. Executor loads checkpoint, skips completed steps, continues from saved point
3. `WorkflowFileExecutor.execute()` accepts optional `checkpoint: CheckpointData`

**Rationale**: Explicit checkpoint steps give control over save points; matches DSL checkpoint step type.

**Alternatives Considered**:
- Automatic checkpoint after every step → Rejected: Too much I/O, most steps don't need it
- Checkpoint only on failure → Rejected: Can't resume partial progress

---

### 9. Branch and Parallel Step Execution

**Question**: How should branch and parallel steps be executed in the WorkflowFileExecutor?

**Findings**:
From `/workspaces/maverick/src/maverick/dsl/serialization/schema.py`:
- `BranchStepRecord`: has `options: list[BranchOptionRecord]` with `when` and `step`
- `ParallelStepRecord`: has `steps: list[StepRecordUnion]`

From `/workspaces/maverick/src/maverick/dsl/steps/branch.py`:
- `BranchStep.execute()` evaluates options in order, returns first match

**Decision**:

**Branch execution**:
```python
async def _execute_branch_step(self, step, resolved_inputs, context):
    for option in step.options:
        if self._evaluate_condition(option.when, context):
            return await self._execute_step(option.step, context)
    return None  # No matching branch
```

**Parallel execution**:
```python
async def _execute_parallel_step(self, step, resolved_inputs, context):
    tasks = [self._execute_step(s, context) for s in step.steps]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Aggregate results; fail if any failed
    return {"results": results}
```

**Rationale**: Follows DSL step semantics; parallel uses asyncio.gather for true concurrency.

**Alternatives Considered**:
- Sequential parallel execution → Acceptable fallback but loses concurrency benefits
- Fail immediately on first parallel failure → Rejected: Want all results for debugging

---

### 10. Integration with Existing Workflow Classes

**Question**: How do DSL-based workflows integrate with existing `FlyWorkflow` and `RefuelWorkflow` classes?

**Findings**:
From `/workspaces/maverick/src/maverick/workflows/fly.py`:
- `FlyWorkflow` class with `execute(inputs: FlyInputs) -> AsyncIterator[FlyProgressEvent]`
- Complex orchestration logic in Python methods

From spec requirements:
- FR-044: Workflows MUST use existing interface types (FlyInputs, FlyResult, etc.)
- SC-009: Follow interface contracts from Specs 8-10

**Decision**: Create DSL execution wrappers in existing workflow classes:

```python
class FlyWorkflow:
    def __init__(self, config: FlyConfig, registry: ComponentRegistry):
        self._config = config
        self._registry = registry
        self._executor = WorkflowFileExecutor(registry=registry, config=config)

    async def execute(self, inputs: FlyInputs) -> AsyncIterator[FlyProgressEvent]:
        # Load YAML workflow
        workflow = self._load_workflow("fly")

        # Execute via DSL engine
        async for event in self._executor.execute(workflow, inputs.model_dump()):
            # Translate DSL events to FlyProgressEvent
            yield self._translate_event(event)

        # Build FlyResult from workflow result
        result = self._executor.get_result()
        yield FlyWorkflowCompleted(result=self._build_fly_result(result))
```

**Rationale**: Preserves existing interface contracts while delegating to DSL execution.

**Alternatives Considered**:
- Replace workflow classes entirely → Rejected: Breaks interface contracts
- Maintain parallel implementations → Rejected: Duplication, drift risk

---

## Summary of Key Decisions

| Area | Decision |
|------|----------|
| Executor gaps | Implement AgentStep, GenerateStep, ValidateStep, BranchStep, ParallelStep |
| Action registration | Module-based actions in `library/actions/` with central registration |
| Agent/Generator registration | Extend ComponentRegistry with agents registry; register by name |
| Context builders | Named functions in `context_builders.py`; registered in ComponentRegistry |
| Dry-run mode | Conditional step skipping with `when: ${{ not inputs.dry_run }}` |
| Progress events | Adapter layer translates DSL events to workflow-specific types |
| Sub-workflow errors | Raise SubWorkflowError; parent decides fail-fast vs continue |
| Checkpointing | Explicit checkpoint steps in YAML at key stages |
| Branch/Parallel | Implement in executor; parallel uses asyncio.gather |
| Workflow integration | DSL wrapper in existing FlyWorkflow/RefuelWorkflow classes |

## Dependencies Identified

1. **Spec 22-24 DSL**: Core step types, engine, context ✅ Already implemented
2. **Spec 25 Library**: Discovery, precedence, built-in metadata ✅ Already implemented
3. **Spec 3-4 Agents**: ImplementerAgent, CodeReviewerAgent, IssueFixerAgent ✅ Already implemented
4. **Spec 19 Generators**: CommitMessageGenerator, PRDescriptionGenerator ✅ Already implemented
5. **Spec 8-10 Interfaces**: FlyInputs, RefuelInputs, ValidationResult ✅ Already implemented

All dependencies are satisfied; implementation can proceed.
