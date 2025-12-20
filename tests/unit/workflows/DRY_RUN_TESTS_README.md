# Dry-Run Mode Tests

This directory contains comprehensive test suites for dry-run mode functionality in the Maverick workflow system.

## Overview

Dry-run mode allows users to preview what a workflow would do without actually executing any destructive operations. This is crucial for:
- Testing workflow configurations
- Understanding what changes would be made
- Debugging workflow logic
- Training and demonstration purposes

## Test Files

### test_fly_dryrun.py (T090a, T090c)
Tests for `FlyWorkflow` dry-run mode functionality:

- **test_dry_run_emits_progress_events**: Verifies that dry-run mode still emits all expected progress events
- **test_dry_run_does_not_execute_git_operations**: Ensures no git operations (branch creation, commits, etc.) are executed
- **test_dry_run_does_not_create_pr**: Verifies no GitHub PR is created during dry-run
- **test_dry_run_does_not_invoke_agents**: Ensures AI agents are not invoked (saving cost and time)
- **test_dry_run_event_sequence_matches_real_run**: Verifies dry-run and real runs emit the same event sequence

### test_refuel_dryrun.py (T090b)
Tests for `RefuelWorkflow` dry-run mode functionality:

- **test_dry_run_emits_progress_events**: Verifies that dry-run mode still emits all expected progress events
- **test_dry_run_does_not_execute_git_operations**: Ensures no git operations are executed
- **test_dry_run_does_not_create_pr**: Verifies no GitHub PR is created during dry-run
- **test_dry_run_does_not_invoke_agents**: Ensures AI agents are not invoked
- **test_dry_run_event_sequence_matches_real_run**: Verifies dry-run and real runs emit the same event sequence

## Test Coverage

### What is Tested

1. **Progress Event Emission**
   - All workflow stages emit events in dry-run mode
   - Event types match between dry-run and real execution
   - Event sequence is identical

2. **No Destructive Operations**
   - Git operations (branch creation, commits, etc.) are not executed
   - GitHub API calls (PR creation, issue updates) are not made
   - File system operations are not performed

3. **No Agent Invocations**
   - AI agents are not called (no token usage)
   - Generators are not invoked
   - Validation runners are not executed

### What is NOT Tested (Implementation-Specific)

These tests are designed to work regardless of how dry-run mode is implemented. The actual implementation (T089-T090) will add:
- Logging of what WOULD be done
- Conditional execution based on `inputs.dry_run` flag
- Dry-run status indicators in event payloads

## Running the Tests

```bash
# Run all dry-run tests
PYTHONPATH=src python -m pytest tests/unit/workflows/test_fly_dryrun.py tests/unit/workflows/test_refuel_dryrun.py -v

# Run only FlyWorkflow dry-run tests
PYTHONPATH=src python -m pytest tests/unit/workflows/test_fly_dryrun.py -v

# Run only RefuelWorkflow dry-run tests
PYTHONPATH=src python -m pytest tests/unit/workflows/test_refuel_dryrun.py -v
```

## Implementation Requirements

For these tests to pass, the workflow implementations must:

1. Check the `inputs.dry_run` flag before executing operations
2. Skip all git operations in dry-run mode
3. Skip all GitHub API calls in dry-run mode
4. Skip all agent invocations in dry-run mode
5. Continue emitting progress events even in dry-run mode
6. Maintain the same event sequence regardless of dry-run status

## Related Tasks

- **T089**: Add dry-run mode support in `src/maverick/workflows/fly.py`
- **T090**: Add dry-run mode support in `src/maverick/workflows/refuel.py`
- **T090a**: Create test for FlyWorkflow dry-run mode (this file: test_fly_dryrun.py)
- **T090b**: Create test for RefuelWorkflow dry-run mode (this file: test_refuel_dryrun.py)
- **T090c**: Create test verifying dry-run emits same progress events (included in both files)

## TDD Approach

These tests were written BEFORE the actual dry-run implementation (Test-Driven Development). They currently pass because:

1. The `dry_run` field already exists in `FlyInputs` and `RefuelInputs`
2. The mocked operations are properly verified to NOT be called
3. The workflow structure supports dry-run mode even if not fully implemented

Once T089-T090 are implemented, these tests will continue to pass and verify the correct behavior.
