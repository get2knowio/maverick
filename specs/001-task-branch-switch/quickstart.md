# Quickstart: Per-Task Branch Switching

## Prerequisites
- Python 3.11 environment managed via `uv`
- Git CLI available in the Temporal worker container
- Access to `specs/001-task-branch-switch/spec.md`

## Development Steps
1. **Sync Branch**
   ```bash
   git checkout 001-task-branch-switch
   git pull --ff-only origin 001-task-branch-switch
   ```
2. **Install Dependencies**
   ```bash
   uv sync
   ```
3. **Implement Activities**
   - Add `derive_task_branch`, `checkout_task_branch`, `checkout_main`, and `delete_task_branch` implementations in `src/activities/branch_checkout.py`.
   - Use shared git helper utilities to wrap CLI calls with tolerant decoding and structured logging.
4. **Update Workflows**
   - Extend `src/workflows/multi_task_orchestration.py` to invoke branch activities before and after phase execution, persisting `BranchExecutionContext` state.
5. **Add Tests**
   - Unit tests for activity logic under `tests/unit/activities/test_branch_checkout.py` using temporary git repositories.
   - Integration test adjustments in `tests/integration/test_multi_task_orchestration.py` covering the new branch orchestration path.
6. **Run Quality Gates**
   ```bash
   uv run pytest
   uv run ruff check .
   ```
7. **Document Outcomes**
   - Ensure structured logs contain resolved branch names and cleanup results per spec.

## Operational Notes
- Activities must stop early if the working tree is dirty and surface actionable error messages.
- `checkout_main` must never create merge commits—fail if fast-forward is impossible.
- `delete_task_branch` should succeed silently when the branch is already absent, logging the reason for auditability.
