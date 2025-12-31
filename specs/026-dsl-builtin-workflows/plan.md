# Implementation Plan: DSL-Based Built-in Workflow Implementation

**Branch**: `026-dsl-builtin-workflows` | **Date**: 2025-12-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/026-dsl-builtin-workflows/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

This spec implements all built-in workflows (fly, refuel, review, validate, quick_fix) and reusable fragments (validate_and_fix, commit_and_push, create_pr_with_summary) using the DSL from Specs 22-24. The workflows implement the interfaces defined in Specs 8-10 (FlyWorkflow, RefuelWorkflow, ValidationWorkflow) while following the Python-orchestrated patterns from Spec 20 (agents for judgment, Python for deterministic operations).

The implementation focuses on:
1. Completing the existing YAML workflow definitions with proper step implementations
2. Implementing Python actions required by workflow steps
3. Integrating agents and generators via the ComponentRegistry
4. Ensuring progress events flow correctly for TUI consumption
5. Enabling checkpointing for resumability

## Technical Context

**Language/Version**: Python 3.10+ with `from __future__ import annotations`
**Primary Dependencies**:
- claude-agent-sdk (Claude Agent SDK for agent execution)
- pydantic (configuration and data models)
- PyYAML (workflow file parsing)
- textual (TUI for progress display)
- click (CLI entry point)

**Storage**: N/A for persistence; in-memory state during workflow execution; optional JSON checkpoints under `.maverick/checkpoints/`

**Testing**: pytest + pytest-asyncio (all tests async-compatible)

**Target Platform**: Linux/macOS CLI (cross-platform Python)

**Project Type**: Single Python project (CLI/TUI application)

**Performance Goals**:
- Token usage reduced 40-60% vs non-orchestrated implementations by using Python for deterministic operations
- Workflows emit progress events at each stage transition for real-time TUI updates

**Constraints**:
- All workflows must be async-first
- Credentials injected via MaverickConfig; never logged in step results or progress events
- Workflows must handle partial failures gracefully (one agent failure doesn't crash workflow)

**Scale/Scope**:
- 5 main workflows (fly, refuel, review, validate, quick_fix)
- 3 reusable fragments (validate_and_fix, commit_and_push, create_pr_with_summary)
- 1 sub-workflow (process_single_issue for refuel)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Async-First ✅
- All workflow executions use async generators yielding `ProgressEvent`
- DSL engine (`WorkflowEngine`) and executor (`WorkflowFileExecutor`) are async
- Agent and generator steps await SDK interactions
- Python action steps support both sync and async callables

### II. Separation of Concerns ✅
- **Agents**: Know HOW to do tasks (ImplementerAgent, CodeReviewerAgent, IssueFixerAgent, generators)
- **Workflows**: Know WHAT to do and WHEN (YAML DSL definitions orchestrate stages)
- **TUI**: Consumes progress events (no business logic)
- **Tools/Runners**: Wrap external systems (GitRunner, GithubRunner, ValidationRunner)

### III. Dependency Injection ✅
- All agents, runners, and generators passed via `ComponentRegistry`
- Configuration injected via `MaverickConfig`
- No module-level mutable state in workflow implementations

### IV. Fail Gracefully, Recover Aggressively ✅
- Workflows capture errors per-step and continue with remaining work
- `validate_and_fix` fragment implements retry with max_attempts
- Refuel workflow aggregates partial results when some issues fail
- Each step result includes success status and error details

### V. Test-First ✅
- 100% test coverage target for all workflow definitions
- Tests use mocked runners and agents per existing patterns
- Async tests with `pytest.mark.asyncio`

### VI. Type Safety ✅
- Pydantic `BaseModel` for all workflow inputs/outputs (FlyInputs, RefuelInputs, etc.)
- `@dataclass(frozen=True)` for immutable result objects
- Complete type hints throughout

### VII. Simplicity ✅
- Workflows are declarative YAML files (minimal code)
- Reusable fragments avoid duplication
- No premature abstractions; fragments only for truly common patterns

### VIII. Relentless Progress ✅
- Checkpointing via `CheckpointStep` for resumability
- Graceful degradation: validation failures don't crash workflow (PR created as draft)
- Error recovery with retry and fallback patterns

## Project Structure

### Documentation (this feature)

```text
specs/026-dsl-builtin-workflows/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/maverick/
├── library/                      # Spec 25: Built-in workflow library
│   ├── workflows/               # Built-in workflow YAML files
│   │   ├── fly.yaml             # [UPDATE] Add dry_run, process_single_issue
│   │   ├── refuel.yaml          # [UPDATE] Add iteration via python action
│   │   ├── review.yaml          # [UPDATE] Complete review orchestration
│   │   ├── validate.yaml        # [UPDATE] Integrate validate_and_fix fragment
│   │   ├── quick_fix.yaml       # [UPDATE] Complete single-issue flow
│   │   └── process_single_issue.yaml  # [NEW] Sub-workflow for refuel
│   ├── fragments/               # Reusable workflow fragments
│   │   ├── validate_and_fix.yaml      # [DONE] Already complete
│   │   ├── commit_and_push.yaml       # [DONE] Already complete
│   │   └── create_pr_with_summary.yaml # [DONE] Already complete
│   ├── builtins.py              # [UPDATE] Add metadata for new workflows
│   └── actions/                 # [NEW] Python actions for workflow steps
│       ├── __init__.py
│       ├── git.py               # git_commit, git_push, create_git_branch
│       ├── github.py            # fetch_github_issues, fetch_github_issue, create_github_pr
│       ├── validation.py        # run_fix_retry_loop, generate_validation_report
│       ├── workspace.py         # init_workspace
│       ├── review.py            # gather_pr_context, run_coderabbit_review, combine_review_results
│       └── refuel.py            # process_selected_issues, generate_refuel_summary
│
├── dsl/
│   ├── serialization/
│   │   ├── executor.py          # [UPDATE] Implement branch/parallel steps
│   │   └── registry.py          # [UPDATE] Register actions/agents/generators
│   └── context_builders.py      # [NEW] Context builders for agent/generate steps
│
├── workflows/
│   ├── fly.py                   # [UPDATE] Add DSL execution wrapper
│   ├── refuel.py                # [UPDATE] Add DSL execution wrapper
│   └── validation.py            # [EXISTING] ValidationWorkflow interface

tests/
├── unit/
│   ├── library/
│   │   └── actions/             # [NEW] Unit tests for Python actions
│   │       ├── test_git_actions.py
│   │       ├── test_github_actions.py
│   │       └── test_validation_actions.py
│   └── dsl/
│       └── test_workflow_execution.py  # [NEW] Integration tests for YAML workflows
└── integration/
    └── test_builtin_workflows.py       # [NEW] End-to-end workflow tests
```

**Structure Decision**: Single Python project with workflows defined as YAML files under `src/maverick/library/workflows/` and Python actions under `src/maverick/library/actions/`. This follows the established Maverick architecture and extends Spec 25's built-in workflow library with executable implementations.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | No constitution violations | Design aligns with all 8 principles |

All complexity is inherent to the domain:
- Workflows require orchestration logic → DSL provides declarative structure
- Multiple step types need different execution paths → Discriminated union in schema
- Reusable patterns across workflows → Fragments avoid duplication

## Constitution Check - Post-Design Re-evaluation

*Re-evaluated after Phase 1 design completion.*

### I. Async-First ✅ CONFIRMED
- **Design evidence**: All Python actions defined with `async def` signatures
- **Context builders**: Return `Awaitable[dict[str, Any]]`
- **Executor**: Uses `await` for step execution, `asyncio.gather` for parallel

### II. Separation of Concerns ✅ CONFIRMED
- **Agents**: Registered in ComponentRegistry, invoked by AgentStep
- **Workflows**: YAML definitions orchestrate; Python actions handle mechanics
- **Context builders**: Bridge between workflow context and agent-specific needs
- **Result types**: Frozen dataclasses for immutable step outputs

### III. Dependency Injection ✅ CONFIRMED
- **ComponentRegistry extended**: Agents, context builders, actions all injectable
- **No globals**: Registry passed to executor at construction
- **Testable**: All actions accept dependencies as parameters

### IV. Fail Gracefully ✅ CONFIRMED
- **Action contracts**: All return `success: bool` and `error: str | None`
- **Refuel**: `ProcessedIssueEntry` captures per-issue status
- **Validation**: `ValidationReportResult` aggregates failures and suggestions

### V. Test-First ✅ PLANNED
- **Action contracts**: Protocol types enable mock verification
- **Test structure**: Unit tests per action module, integration tests for workflows

### VI. Type Safety ✅ CONFIRMED
- **Frozen dataclasses**: All result types use `@dataclass(frozen=True, slots=True)`
- **Protocol types**: Action contracts define precise signatures
- **Pydantic**: Context builders return typed dicts matching agent expectations

### VII. Simplicity ✅ CONFIRMED
- **Single purpose actions**: Each action does one thing (git_commit, git_push, etc.)
- **Context builders centralized**: One module with all builders
- **No inheritance hierarchy**: Flat action functions, not classes

### VIII. Relentless Progress ✅ CONFIRMED
- **Checkpoints**: Explicit checkpoint steps in workflow YAML at key stages
- **Resume capability**: Executor accepts checkpoint data for resumption
- **Partial results**: RefuelSummaryResult aggregates all outcomes including failures

### Conclusion

Post-design review confirms all constitution principles are satisfied. The design maintains:
- Clean separation between YAML orchestration and Python implementation
- Full async support throughout the execution path
- Comprehensive type safety with frozen result types
- Graceful error handling with aggregated results

No constitution violations or justified complexity needed.
