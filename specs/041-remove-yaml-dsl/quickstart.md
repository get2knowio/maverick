# Quickstart: Remove Dead YAML DSL Infrastructure

**Feature**: 041-remove-yaml-dsl | **Date**: 2026-03-03

## Verification Checklist

### After Phase 1 (Extract Live Modules)

- [ ] `from maverick.types import StepType, StepMode, AutonomyLevel` works
- [ ] `from maverick.events import ProgressEvent, StepStarted, StepCompleted, AgentStreamChunk` works
- [ ] `from maverick.results import StepResult, WorkflowResult` works
- [ ] `from maverick.executor import ClaudeStepExecutor` works
- [ ] `from maverick.executor.protocol import StepExecutor` works
- [ ] `from maverick.executor.config import StepConfig, resolve_step_config` works
- [ ] `from maverick.executor.errors import OutputSchemaValidationError` works
- [ ] `from maverick.checkpoint import FileCheckpointStore, CheckpointData` works
- [ ] `from maverick.registry import ComponentRegistry, ActionRegistry, AgentRegistry, GeneratorRegistry` works
- [ ] `from maverick.constants import CHECKPOINT_DIR, COMMAND_TIMEOUT` works
- [ ] `from maverick.exceptions import WorkflowStepError, CheckpointNotFoundError` works
- [ ] `make lint` passes
- [ ] `make typecheck` passes
- [ ] `make test` passes (all active tests)

### After Phase 2 (Delete Dead Code)

- [ ] `src/maverick/dsl/` directory does not exist
- [ ] `src/maverick/library/workflows/*.yaml` files do not exist
- [ ] `src/maverick/library/fragments/*.yaml` files do not exist
- [ ] `lark` is not in `pyproject.toml` dependencies
- [ ] `uv sync` succeeds without lark
- [ ] `execute_workflow_run` function does not exist in `cli/workflow_executor.py`
- [ ] `execute_dsl_workflow` function does not exist in `cli/helpers.py`
- [ ] `make lint` passes
- [ ] `make typecheck` passes

### After Phase 3 (Clean Up Tests)

- [ ] `tests/unit/dsl/` directory does not exist
- [ ] `tests/integration/dsl/` directory does not exist
- [ ] `tests/unit/executor/` exists with moved tests
- [ ] `tests/unit/checkpoint/` exists with moved tests
- [ ] `tests/unit/test_events.py` exists with updated imports
- [ ] `tests/unit/test_results.py` exists with updated imports
- [ ] `tests/unit/test_types.py` exists with updated imports
- [ ] `make test` passes
- [ ] `grep -r "maverick\.dsl" src/ tests/` returns no matches

### Final Validation

- [ ] `make check` passes (lint + typecheck + test)
- [ ] `maverick fly --help` works
- [ ] `maverick land --help` works
- [ ] `maverick refuel speckit --help` works
- [ ] `maverick flight-plan generate --help` works

## Key Commands

```bash
# Run all checks
make check

# Verify no DSL references remain
grep -r "maverick\.dsl" src/ tests/

# Verify lark is not installed
uv pip show lark 2>&1 | grep -q "not installed" && echo "OK: lark removed"

# Count lines removed (compare before/after)
find src/maverick -name "*.py" | xargs wc -l | tail -1
find tests -name "*.py" | xargs wc -l | tail -1
```
