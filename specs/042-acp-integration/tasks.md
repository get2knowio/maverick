# Tasks: ACP Integration

**Input**: Design documents from `/specs/042-acp-integration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in spec. Test tasks included only for new modules (executor, client, registry) since they replace existing tested code.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add ACP dependency and prepare project for migration

- [X] T001 Add `agent-client-protocol` v0.8.1+ dependency via `uv add agent-client-protocol`
- [X] T002 Add `PermissionMode` enum and `AgentProviderConfig` frozen Pydantic model to `src/maverick/config.py` with fields: command (list[str]), env (dict[str,str]), permission_mode (PermissionMode), default (bool)
- [X] T003 Add `agent_providers: dict[str, AgentProviderConfig]` field to `MaverickConfig` in `src/maverick/config.py` with default empty dict

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create `AgentProviderRegistry` in `src/maverick/executor/provider_registry.py` with `from_config()` factory (synthesizes default Claude Code provider when empty), `get(name)`, `default()`, and `names()` methods per contracts/acp-step-executor.py
- [X] T005 [P] Create unit tests for `AgentProviderRegistry` in `tests/unit/executor/test_provider_registry.py` covering: from_config with providers, from_config empty (default synthesis), get existing/missing, default resolution, multiple-default validation error
- [X] T006 Change `provider` field type from `Literal["claude"] | None` to `str | None` in `StepConfig` in `src/maverick/executor/config.py`
- [X] T007 Refactor `MaverickAgent` base class in `src/maverick/agents/base.py`: add abstract `build_prompt(context: TContext) -> str` method, keep name/instructions/allowed_tools/model properties, keep constructor fields (_name, _instructions, _allowed_tools, _model, _mcp_servers, _max_tokens, _temperature, _output_model). Do NOT remove SDK-coupled methods yet (they are removed in US4)
- [X] T008 Update unit tests for `MaverickAgent` in `tests/unit/agents/test_base.py` to test the new `build_prompt()` abstract method alongside existing tests

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Workflow Executes Steps via ACP Agent (Priority: P1) 🎯 MVP

**Goal**: A workflow step executes via ACP subprocess instead of Claude Agent SDK. The agent spawns, receives prompts, streams output to TUI, and returns structured results.

**Independent Test**: Run a fly workflow with a single bead. Verify the ACP agent subprocess spawns, receives the prompt, streams output chunks to the TUI, and returns a result that the workflow can process.

### Implementation for User Story 1

- [X] T009 [P] [US1] Create `MaverickAcpClient` in `src/maverick/executor/acp_client.py` extending `acp.Client` with: `session_update()` mapping ACP events (AgentMessageChunk, AgentThoughtChunk, ToolCallStart, ToolCallProgress) to `AgentStreamChunk` events; `request_permission()` with auto_approve mode; `reset()` for session state; `get_accumulated_text()` for output extraction; `_SessionState` dataclass for per-session mutable state (text_chunks, tool_call_counts, abort flag)
- [X] T010 [P] [US1] Create `AcpStepExecutor` in `src/maverick/executor/acp.py` implementing `StepExecutor` protocol with: `execute()` method (resolve provider, get/create connection, create session, build prompt, send via `conn.prompt()`, collect result), `cleanup()` for subprocess termination, `_get_or_create_connection()` for lazy connection caching, `_build_acp_prompt()` to convert prompt + instructions to ACP content blocks, `_extract_json_output()` to extract last JSON block from accumulated text and validate against Pydantic schema. Include ACP lifecycle logging per FR-023: info-level for subprocess spawn/cleanup, debug-level for session create/prompt send/response complete
- [X] T011 [US1] Migrate `ImplementerAgent` in `src/maverick/agents/implementer.py`: implement `build_prompt(context: ImplementerContext) -> str` extracting prompt-building logic from current `execute()` method
- [X] T012 [US1] Migrate `CodeReviewerAgent` in `src/maverick/agents/code_reviewer/agent.py`: implement `build_prompt()` extracting prompt-building logic from current `execute()` method
- [X] T013 [P] [US1] Migrate `FixerAgent` in `src/maverick/agents/fixer.py`: implement `build_prompt()` extracting prompt-building logic from current `execute()` method
- [X] T014 [P] [US1] Migrate `IssueFixerAgent` in `src/maverick/agents/issue_fixer.py`: implement `build_prompt()` extracting prompt-building logic from current `execute()` method
- [X] T015 [P] [US1] Migrate `DecomposerAgent` in `src/maverick/agents/decomposer.py`: implement `build_prompt()` extracting prompt-building logic from current `execute()` method
- [X] T016 [P] [US1] Migrate `FlightPlanGeneratorAgent` in `src/maverick/agents/flight_plan_generator.py`: implement `build_prompt()` extracting prompt-building logic from current `execute()` method
- [X] T017 [P] [US1] Migrate `UnifiedReviewerAgent` in `src/maverick/agents/reviewers/unified_reviewer.py`: implement `build_prompt()` extracting prompt-building logic from current `execute()` method
- [X] T018 [P] [US1] Migrate `SimpleFixerAgent` in `src/maverick/agents/reviewers/simple_fixer.py`: implement `build_prompt()` extracting prompt-building logic from current `execute()` method
- [X] T019 [US1] Refactor `GeneratorAgent` base class in `src/maverick/agents/generators/base.py`: add abstract `build_prompt(context: dict[str, Any]) -> str` method alongside existing `generate()`. (Note: SDK machinery kept for generate() backward compat; full removal in T046)
- [X] T020 [P] [US1] Migrate `CommitMessageGenerator` in `src/maverick/agents/generators/commit_message.py`: implement `build_prompt()` extracting prompt-building logic from current `generate()` method
- [X] T021 [P] [US1] Migrate `PRDescriptionGenerator` in `src/maverick/agents/generators/pr_description.py`: implement `build_prompt()` extracting prompt-building logic from current `generate()` method
- [X] T022 [P] [US1] Migrate `PRTitleGenerator` in `src/maverick/agents/generators/pr_title.py`: implement `build_prompt()` extracting prompt-building logic from current `generate()` method
- [X] T023 [P] [US1] Migrate `BeadEnricherGenerator` in `src/maverick/agents/generators/bead_enricher.py`: implement `build_prompt()` extracting prompt-building logic from current `generate()` method
- [X] T024 [P] [US1] Migrate `DependencyExtractorGenerator` in `src/maverick/agents/generators/dependency_extractor.py`: implement `build_prompt()` extracting prompt-building logic from current `generate()` method
- [X] T025 [P] [US1] Migrate `CodeAnalyzerGenerator` in `src/maverick/agents/generators/code_analyzer.py`: implement `build_prompt()` extracting prompt-building logic from current `generate()` method
- [X] T026 [P] [US1] Migrate `ErrorExplainerGenerator` in `src/maverick/agents/generators/error_explainer.py`: implement `build_prompt()` extracting prompt-building logic from current `generate()` method
- [X] T027 [US1] Migrate `CuratorAgent` in `src/maverick/agents/curator.py`: refactor from `GeneratorAgent` subclass to prompt-builder pattern, implement `build_prompt()` extracting prompt-building logic. Note: CuratorAgent extends GeneratorAgent (not MaverickAgent)
- [X] T028 [US1] Wire `AcpStepExecutor` into CLI: update `src/maverick/cli/workflow_executor.py` to instantiate `AcpStepExecutor` with `AgentProviderRegistry.from_config(config.agent_providers)` instead of `ClaudeStepExecutor`
- [X] T029 [US1] Update `src/maverick/executor/__init__.py` to export `AcpStepExecutor` and `AgentProviderRegistry`; keep `ClaudeStepExecutor` export temporarily for backwards compatibility
- [X] T030 [P] [US1] Create unit tests for `MaverickAcpClient` in `tests/unit/executor/test_acp_client.py` covering: session_update event mapping (message chunks → output, thinking chunks → thinking, tool call start/progress), text accumulation, reset between sessions, permission auto-approve
- [X] T031 [P] [US1] Create unit tests for `AcpStepExecutor` in `tests/unit/executor/test_acp_executor.py` covering: basic execute flow (mock ACP connection), prompt building with instructions prepended, structured output extraction (fenced JSON, raw brace-matched JSON, validation error), connection caching (same provider reuses connection), cleanup terminates all subprocesses, lifecycle logging at correct levels

**Checkpoint**: At this point, User Story 1 should be fully functional — workflow steps execute via ACP

---

## Phase 4: User Story 2 — Configurable Agent Providers (Priority: P2)

**Goal**: Multiple ACP agent providers can be configured in `maverick.yaml`. Steps select a provider explicitly or fall back to the default.

**Independent Test**: Configure two agent entries in `maverick.yaml`. Run a step with `provider: "claude"` and another with `provider: "gemini"`. Verify each step spawns the correct agent subprocess.

### Implementation for User Story 2

- [X] T032 [US2] Add multi-provider selection logic to `AcpStepExecutor.execute()` in `src/maverick/executor/acp.py`: resolve provider from `config.provider` falling back to `registry.default()`, pass provider-specific command/env to `spawn_agent_process()`
- [X] T033 [US2] Add zero-config default synthesis validation: ensure `AgentProviderRegistry.from_config({})` produces a working Claude Code default in `src/maverick/executor/provider_registry.py`, and that config loading with no `agent_providers` section works end-to-end
- [X] T034 [US2] Add unit tests for multi-provider scenarios in `tests/unit/executor/test_acp_executor.py`: step with explicit provider selects correct config, step with no provider uses default, step with unknown provider raises ConfigError, two providers with different commands spawn different subprocesses

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 — Error Resilience and Safety (Priority: P2)

**Goal**: Agent subprocess crashes, timeouts, runaway loops, and dangerous tool calls are all handled gracefully with appropriate Maverick exceptions.

**Independent Test**: Simulate agent subprocess crash, timeout, and excessive tool calls. Verify each triggers the correct Maverick exception and the workflow continues or fails gracefully.

### Implementation for User Story 3

- [X] T035 [US3] Implement circuit breaker in `MaverickAcpClient.session_update()` in `src/maverick/executor/acp_client.py`: track tool call counts from `ToolCallStart` events per tool name, trigger abort when any tool exceeds `MAX_SAME_TOOL_CALLS` (15), call `conn.cancel(session_id)`, raise `CircuitBreakerError` in executor after prompt returns
- [X] T036 [US3] Implement timeout enforcement in `AcpStepExecutor.execute()` in `src/maverick/executor/acp.py`: wrap `conn.prompt()` with `asyncio.wait_for(timeout=config.timeout)`, map `asyncio.TimeoutError` to `MaverickTimeoutError`
- [X] T037 [US3] Implement retry logic in `AcpStepExecutor.execute()` in `src/maverick/executor/acp.py`: use `tenacity.AsyncRetrying` with `stop_after_attempt(config.max_retries + 1)` and `wait_exponential`, create fresh ACP session per retry attempt while reusing the cached connection
- [X] T038 [US3] Implement error mapping in `AcpStepExecutor` in `src/maverick/executor/acp.py`: map ACP `RequestError` → `AgentError`, subprocess non-zero exit → `ProcessError`, `FileNotFoundError` → `CLINotFoundError`, transport errors → `NetworkError`, JSON decode errors → `MalformedResponseError` per research.md R-009
- [X] T039 [US3] Implement `deny_dangerous` permission mode in `MaverickAcpClient.request_permission()` in `src/maverick/executor/acp_client.py`: allow read/search tools (Read, Glob, Grep, WebSearch, WebFetch), deny write/bash/destructive tools (Bash, Write, Edit, NotebookEdit) based on pattern matching against allowed_tools and dangerous tool patterns
- [X] T040 [US3] Implement transparent reconnect in `AcpStepExecutor._get_or_create_connection()` in `src/maverick/executor/acp.py`: detect transport/connection errors, close old connection, re-spawn subprocess, re-initialize, retry prompt once before raising error (FR-021)
- [X] T041 [US3] Wire `AcpStepExecutor.cleanup()` into workflow teardown: ensure `src/maverick/cli/workflow_executor.py` (or workflow runner) calls `executor.cleanup()` in a finally block to terminate all cached subprocesses (FR-019)
- [X] T042 [P] [US3] Add unit tests for error resilience in `tests/unit/executor/test_acp_executor.py`: timeout raises MaverickTimeoutError, retry creates fresh sessions, subprocess crash raises ProcessError, command not found raises CLINotFoundError, reconnect on connection drop
- [X] T043 [P] [US3] Add unit tests for circuit breaker and permissions in `tests/unit/executor/test_acp_client.py`: circuit breaker triggers at threshold, abort flag set, deny_dangerous blocks write tools, deny_dangerous allows read tools, interactive mode raises NotImplementedError

**Checkpoint**: At this point, User Stories 1, 2, AND 3 should all work independently

---

## Phase 6: User Story 4 — Clean SDK Removal (Priority: P3)

**Goal**: The `claude-agent-sdk` package is fully removed. No imports, mocks, or references remain. All tests pass without it.

**Independent Test**: Remove `claude-agent-sdk` from the virtualenv and run `make check`. All tests pass, no import errors.

### Implementation for User Story 4

- [X] T044 [US4] Remove SDK-coupled methods from `MaverickAgent` in `src/maverick/agents/base.py`: delete `query()`, `_build_options()`, `_wrap_sdk_error()`, `_extract_usage()`, `_extract_structured_output()`, `_extract_tool_calls()`, `_check_circuit_breaker()`, `stream_callback` property, and all `claude_agent_sdk` imports
- [X] T045 [US4] Remove `execute()` method from all MaverickAgent concrete subclasses (keep only `build_prompt()`): update `src/maverick/agents/implementer.py`, `src/maverick/agents/code_reviewer/agent.py`, `src/maverick/agents/fixer.py`, `src/maverick/agents/issue_fixer.py`, `src/maverick/agents/decomposer.py`, `src/maverick/agents/flight_plan_generator.py`, `src/maverick/agents/reviewers/unified_reviewer.py`, `src/maverick/agents/reviewers/simple_fixer.py`
- [X] T046 [US4] Remove `generate()` method and SDK-coupled infrastructure from `GeneratorAgent` base in `src/maverick/agents/generators/base.py` and all concrete generators: keep only `build_prompt()`. Update `src/maverick/agents/curator.py` accordingly
- [X] T047 [US4] Remove SDK-specific utilities from `src/maverick/agents/utils.py`: delete `extract_usage()`, `extract_text()`, `extract_streaming_text()` and any `claude_agent_sdk` references; keep `get_zero_usage()` if still used
- [X] T048 [US4] Remove SDK-specific extraction from `src/maverick/agents/result.py` if any SDK references exist; verify `AgentUsage` and `AgentResult` are SDK-independent
- [X] T049 [US4] Delete `src/maverick/executor/claude.py` (ClaudeStepExecutor — fully replaced by AcpStepExecutor)
- [X] T050 [US4] Update `src/maverick/executor/__init__.py`: remove `ClaudeStepExecutor` export, ensure `AcpStepExecutor` is the only executor export
- [X] T051 [US4] Remove `claude-agent-sdk` from project dependencies via `uv remove claude-agent-sdk`
- [X] T052 [US4] Sweep entire codebase for remaining `claude_agent_sdk` or `claude-agent-sdk` references: search `src/`, `tests/`, `pyproject.toml`, and remove or update all occurrences
- [X] T053 [US4] Delete old executor tests `tests/unit/executor/test_claude.py` and update all agent tests in `tests/unit/agents/` (including `tests/unit/agents/generators/`) to mock ACP interactions (or pure `build_prompt()` calls) instead of SDK types
- [X] T054 [US4] Update `tests/conftest.py`: remove any SDK mock fixtures, add ACP mock fixtures (mock `spawn_agent_process`, mock `ClientSideConnection`, mock `acp.Client`)
- [X] T055 [US4] Run `make check` (lint + typecheck + test) and fix any remaining failures from SDK removal

**Checkpoint**: SDK fully removed, `make check` passes with zero SDK references

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup across all user stories

- [X] T056 [P] Verify structured output extraction handles edge cases in `src/maverick/executor/acp.py`: malformed JSON returns error with raw text, no JSON block returns plain text result, nested JSON blocks extracts last one
- [X] T057 Run `make check` end-to-end and fix any remaining lint, type, or test failures
- [X] T058 Run quickstart.md validation: verify all code examples in `specs/042-acp-integration/quickstart.md` are accurate against final implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (T001 for ACP package) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 (registry, config, base class refactor)
- **US2 (Phase 4)**: Depends on US1 (Phase 3) — extends executor with multi-provider logic
- **US3 (Phase 5)**: Depends on US1 (Phase 3) — adds resilience to executor and client
- **US4 (Phase 6)**: Depends on US1+US2+US3 (Phases 3-5) — can only remove SDK after ACP is fully functional
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — No dependencies on other stories
- **User Story 2 (P2)**: Depends on US1 — extends the AcpStepExecutor with provider selection
- **User Story 3 (P2)**: Depends on US1 — extends the AcpStepExecutor and MaverickAcpClient with resilience
- **User Story 4 (P3)**: Depends on US1+US2+US3 — cleanup can only happen after full ACP path works

### Within Each User Story

- New modules before consumers (client before executor, executor before CLI wiring)
- MaverickAgent subclass migrations (T011-T018) can run in parallel after executor exists
- GeneratorAgent base refactor (T019) must complete before generator migrations (T020-T027)
- Generator migrations (T020-T026) can run in parallel after GeneratorAgent base is refactored
- Tests can run in parallel with each other

### Parallel Opportunities

- T002 and T003 can run in parallel (config changes in same file but different sections)
- T004 and T006 can run in parallel (different files)
- T009 and T010 can run in parallel (different new files)
- T011-T018 MaverickAgent migrations are all parallelizable (different files)
- T020-T026 generator migrations are all parallelizable (different files, after T019)
- T030 and T031 test files can run in parallel
- T035-T041 resilience features can be implemented sequentially (same files) but T042 and T043 tests are parallel
- T044-T054 SDK removal tasks are mostly sequential (interdependent)

---

## Parallel Example: User Story 1

```bash
# Launch both new ACP modules together (different files):
Task T009: "Create MaverickAcpClient in src/maverick/executor/acp_client.py"
Task T010: "Create AcpStepExecutor in src/maverick/executor/acp.py"

# Launch all MaverickAgent migrations together (different files):
Task T011: "Migrate ImplementerAgent in src/maverick/agents/implementer.py"
Task T012: "Migrate CodeReviewerAgent in src/maverick/agents/code_reviewer/agent.py"
Task T013: "Migrate FixerAgent in src/maverick/agents/fixer.py"
Task T014: "Migrate IssueFixerAgent in src/maverick/agents/issue_fixer.py"
Task T015: "Migrate DecomposerAgent in src/maverick/agents/decomposer.py"
Task T016: "Migrate FlightPlanGeneratorAgent in src/maverick/agents/flight_plan_generator.py"
Task T017: "Migrate UnifiedReviewerAgent in src/maverick/agents/reviewers/unified_reviewer.py"
Task T018: "Migrate SimpleFixerAgent in src/maverick/agents/reviewers/simple_fixer.py"

# After T019 (GeneratorAgent base), launch all generator migrations together:
Task T020: "Migrate CommitMessageGenerator in src/maverick/agents/generators/commit_message.py"
Task T021: "Migrate PRDescriptionGenerator in src/maverick/agents/generators/pr_description.py"
Task T022: "Migrate PRTitleGenerator in src/maverick/agents/generators/pr_title.py"
Task T023: "Migrate BeadEnricherGenerator in src/maverick/agents/generators/bead_enricher.py"
Task T024: "Migrate DependencyExtractorGenerator in src/maverick/agents/generators/dependency_extractor.py"
Task T025: "Migrate CodeAnalyzerGenerator in src/maverick/agents/generators/code_analyzer.py"
Task T026: "Migrate ErrorExplainerGenerator in src/maverick/agents/generators/error_explainer.py"

# Launch test files together:
Task T030: "Unit tests for MaverickAcpClient in tests/unit/executor/test_acp_client.py"
Task T031: "Unit tests for AcpStepExecutor in tests/unit/executor/test_acp_executor.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T008)
3. Complete Phase 3: User Story 1 (T009-T031)
4. **STOP and VALIDATE**: Run `make check`, verify ACP executor works end-to-end
5. Both old (ClaudeStepExecutor) and new (AcpStepExecutor) paths coexist at this point

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → ACP execution works → Validate (MVP!)
3. Add User Story 2 → Multi-provider selection works → Validate
4. Add User Story 3 → Error resilience complete → Validate
5. Add User Story 4 → SDK fully removed → `make check` clean
6. Polish → Edge cases, quickstart validation

### Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US2 and US3 both depend on US1 but are independent of each other — they could theoretically run in parallel
- US4 is strictly last since it removes the old SDK that the codebase still uses during US1-US3 development
- Two distinct agent hierarchies need migration: `MaverickAgent` (8 concrete subclasses) and `GeneratorAgent` (7 concrete subclasses + CuratorAgent which extends GeneratorAgent)
