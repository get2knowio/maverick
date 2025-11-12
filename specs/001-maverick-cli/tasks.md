# Tasks: Maverick CLI (Click-based)

Feature: Maverick CLI for Local Temporal AI Workflow Orchestration  
Branch: 001-maverick-cli  
Context: Click CLI, Temporal Python SDK, uv; optional Rich; future TUI: Textual

---

## Phase 1: Setup (project initialization)

Goal: Establish CLI dependency, entry point, and baseline structure to enable incremental delivery.

Independent test: `maverick --help` prints a Click help banner; repository installs/runs without errors.

- [X] T001 Add Click dependency in pyproject.toml ([project.dependencies])
- [X] T002 [P] Add console script entrypoint `maverick = src.cli.maverick:cli` in pyproject.toml ([project.scripts])
- [X] T003 Create CLI entry file at src/cli/maverick.py with Click group and version option
- [X] T004 Configure ruff per-file-ignores to allow T201 only in `src/cli/*.py` in ruff.toml
- [X] T005 [P] Ensure README mentions `timeout 600 uv run pytest` and update quickstart if needed (already aligned)

## Phase 2: Foundational (blocking prerequisites)

Goal: Core CLI building blocks for discovery, validation, and workflow input adaptation.

Independent test: Unit tests pass for discovery ordering, dirty-tree detection, and adapter mapping; no Temporal calls needed.

- [X] T006 Create CLI-local models at src/cli/_models.py (CLITaskDescriptor with validation per data-model.md)
- [X] T007 Implement discovery module at src/cli/_discovery.py to find `specs/*/tasks.md`, ignore `specs-completed/`, sort by numeric prefix then filename
- [X] T008 [P] Implement git helpers at src/cli/_git.py using src/utils/git_cli.run_git_command to get current branch and dirty status
- [X] T009 Implement adapter at src/cli/_adapter.py to map CLITaskDescriptor[] → OrchestrationInput without setting phases (workflow derives phases). Include repo_root, return_to_branch, interactive_mode, and model_prefs.
- [X] T010 Add unit test: tests/unit/test_cli_discovery.py for ordering and filtering
- [X] T011 [P] Add unit test: tests/unit/test_cli_git_guard.py for dirty-tree guard and current branch detection
- [X] T012 [P] Add unit test: tests/unit/test_cli_adapter.py for mapping to OrchestrationInput (including phases placeholder)
- [X] T013 [P] Add unit test: tests/unit/test_cli_json_contracts.py to assert JSON schema keys per contracts/openapi.yaml

## Phase 3: User Story 1 - Run workflow from a repo (P1)

Goal: `maverick run` discovers tasks, builds descriptors, starts MultiTaskOrchestrationWorkflow, and streams progress.

Independent test: From a clean repo with one task, `maverick run` prints workflow_id/run_id within 5s and shows progress lines until completion (or continues streaming until stopped in tests via mocks).

- [X] T014 [US1] Wire `maverick run` command options: `--task`, `--interactive`, `--dry-run`, `--json`, `--allow-dirty`, `--compact` in src/cli/maverick.py
- [X] T015 [US1] Implement discovery and descriptor build in run command using _discovery.py and _models.py
- [X] T016 [US1] Enforce dirty-tree guard; honor `--allow-dirty` and interactive flag in src/cli/maverick.py
- [X] T017 [US1] Build OrchestrationInput via _adapter.py including repo_root and return_to_branch
- [X] T018 [US1] Integrate Temporal client start of "MultiTaskOrchestrationWorkflow" with task queue; capture workflow_id/run_id
- [X] T019 [US1] Implement streaming status loop with a fixed 2s refresh interval via queries `get_progress` and `get_task_results`; support `--compact`; handle Ctrl+C gracefully (clean exit, workflow continues).
- [X] T020 [US1] Emit metrics: task_count, discovery_ms, workflow_start_ms, status_poll_latency_ms_p95 (on completion), errors_count
- [X] T021 [US1] Emit JSON outputs when `--json` supplied matching contracts/ schemas
- [X] T022 [US1] Add integration test: tests/integration/test_cli_run.py (mock Temporal client) to verify start and streaming messages

## Phase 4: User Story 2 - Targeted run and dry-run (P2)

Goal: Allow running a single specified task, interactive pauses, and dry-run descriptor printing.

Independent test: `maverick run --task <path> --interactive` starts exactly one task; `maverick run --task <path> --dry-run --json` prints descriptors and exits 0 without Temporal calls.

- [X] T023 [US2] Implement `--task <path>` path normalization and validation (must reside under repo root) in src/cli/maverick.py
- [X] T024 [US2] Implement `--dry-run` behavior to print descriptors (human + JSON) and exit without starting workflow
- [X] T025 [US2] Ensure `--interactive` sets descriptor field(s) and propagates to OrchestrationInput.interactive_mode
- [X] T026 [US2] Add unit test: tests/unit/test_cli_dry_run.py for descriptor JSON structure and exit code

## Phase 5: User Story 3 - Check status of a workflow (P3)

Goal: `maverick status <workflow-id>` prints current state and last activity; supports `--json`.

Independent test: Given a valid workflow_id, `maverick status <id>` prints current task/phase/last activity; with `--json`, prints schema-aligned status.

- [X] T027 [US3] Implement `maverick status <workflow-id> [--json]` in src/cli/maverick.py
- [X] T028 [US3] Query `get_progress` and `get_task_results`, assemble summary and JSON output
- [X] T029 [US3] Add unit test: tests/unit/test_cli_status.py using mocked workflow handle to assert outputs

## Final Phase: Polish & Cross-Cutting

Goal: Improve UX, robustness, and docs; keep behavior stable.

- [X] T030 Add helpful error messages and remediation (Temporal server unavailable, outside git repo)
- [X] T031 [P] Optional: add `--rich` styling flag with Rich if installed (no hard dependency)
- [X] T032 [P] Document CLI commands and options in README and quickstart.md (ensure consistency)
- [X] T033 Validate and pin Click version in pyproject.toml; add to lockfile via uv
- [X] T034 Ensure all pytest invocations in CI/scripts use `timeout 600` per constitution

### Additional Cross-Cutting and Coverage Tasks

- [X] T035 [P] Wire CLI logging via `src/common/logging.py` (FR-013). Human-readable by default; JSON when `--json` is set. Include correlation fields (`workflow_id`, `run_id`) after workflow start.
- [X] T036 [P] Add unit test: `tests/unit/test_cli_logging_fields.py` to assert JSON logs include correlation and metrics fields (`task_count`, `discovery_ms`, `workflow_start_ms`, `status_poll_latency_ms_p95`, `errors_count`).
- [X] T037 [P] Add performance test: `tests/perf/test_cli_discovery_perf.py` to synthesize ≥200 task files and assert discovery+descriptor build completes ≤ 5s in the devcontainer (FR-010).
- [X] T038 [P] Add unit test: `tests/unit/test_cli_safety_no_repo_writes.py` to ensure no git write operations (checkout/commit/merge/rebase) are invoked by CLI paths (FR-011).
- [X] T039 [US3] Add negative test for invalid workflow_id (non-existent) ensuring non-zero exit and JSON error payload when `--json` is supplied.

---

## Dependencies (story order and blockers)

Order: US1 → US2 → US3

- Phase 1 must complete before Phase 2.
- Phase 2 (foundational) must complete before US1.
- US1 provides shared streaming/query helpers consumed by US3.

## Parallel Opportunities

- T002, T003 can proceed in parallel.
- T007 (discovery), T008 (git), T009 (adapter), and tests T010–T013 can run in parallel once T006 exists.
- Polish items (T031–T033) can run in parallel after core commands land.

## Implementation Strategy

- MVP scope: Deliver US1 only (run command with discovery, start, and streaming). Defer US2/US3 to subsequent increments.
- TDD: Write unit tests (T010–T013) before implementing command logic (US1).
- Keep CLI surface stable; JSON contracts must not break across increments.

## Format Validation

All tasks follow required checklist format:
- Checkbox: `- [ ]` present
- Task ID: T001..T039 sequential (T035–T039 are cross-cutting polish/validation tasks)
- [P] marker only on safe-parallel tasks
- [USn] labels present only for user story phases
- File paths included in descriptions
