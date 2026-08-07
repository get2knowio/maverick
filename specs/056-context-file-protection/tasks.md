# Tasks: Context File Protection

**Input**: Design documents from `/specs/056-context-file-protection/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the constitution (Principle V, Test-First) mandates TDD; every implementation task has a red test task preceding it.

**Organization**: Tasks are grouped by user story. US1 = enforcement (P1), US2 = audit/visibility (P2), US3 = configurability (P3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Single project: `src/maverick/`, `tests/` at repository root (per plan.md).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependency + package scaffolding

- [X] T001 Add `pathspec` to runtime dependencies and bump `airframe-agents` to `>=0.9.2` (ships the Claude permission-gating fix, airframe#79) in `pyproject.toml`, run `uv lock && uv sync`, and verify `python -c "import pathspec, airframe"` (note `[tool.uv] exclude-newer = "7 days"` — v0.9.2 released 2026-08-07, so use an explicit pin or a temporary per-package exclude-newer override if the cooldown rejects it; `pathspec` should be a version at least a week old)
- [X] T002 [P] Create package skeleton: `src/maverick/protection/{__init__.py,policy.py,matching.py,snapshot.py,records.py,config.py}` with module docstrings and empty `__all__`, plus `tests/unit/protection/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the pure core every story consumes — records, matching, policy. Defaults-only at this stage (config arrives in US3).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Red tests for `BlockRecord` (frozen, `to_dict()` per contracts/block-event.md field list) and `BlockCollector` (`append`/`drain`, drain empties) in `tests/unit/protection/test_records.py`
- [X] T004 [P] Red tests for normalization + default-rule matching in `tests/unit/protection/test_matching.py`: basename `AGENTS.md`/`CLAUDE.md` case-insensitive (`claude.md`, `Agents.MD`) at root and nested depths; `.specify/memory/**` tree; literal-vs-resolved dual matching (symlink pointing at protected target; symlink planted at protected path); paths resolving outside root are not protected; unprotected paths pass
- [X] T005 [P] Red tests for `ProtectionPolicy.decide` in `tests/unit/protection/test_policy.py`: create/edit/delete match single target; rename blocked when either source or destination protected (FR-003); `PolicyDecision` carries rule label + reason; internal evaluation error fails closed for default names and open otherwise (FR-011, data-model step 4)
- [X] T006 Implement `src/maverick/protection/records.py` — green T003
- [X] T007 Implement `src/maverick/protection/matching.py` — green T004 (pure functions; posix relpaths from a `root: Path`)
- [X] T008 Implement `ProtectionPolicy` + `PolicyDecision` in `src/maverick/protection/policy.py` — green T005 (`ProtectionPolicy.build(root, config)` accepts a `ProtectionConfig` but only default rules are exercised until US3)

**Checkpoint**: matcher/policy/records green — user stories can begin.

---

## Phase 3: User Story 1 - Protected files survive an implementer's helpful rewrite (Priority: P1) 🎯 MVP

**Goal**: agent write attempts against protected paths are prevented (pre-write where the provider supports callbacks) or undone (post-step backstop, universally); the bead continues; protected files end byte-identical.

**Independent Test**: quickstart §2 — stub-runtime bead mutates `CLAUDE.md`, creates `sub/AGENTS.md`, deletes `.specify/memory/constitution.md`, edits `src/real_work.py`; protected files byte-identical after, real change survives, bead completes (SC-001, SC-003, SC-005).

### Tests for User Story 1

- [X] T009 [P] [US1] Red tests for snapshot/restore in `tests/unit/protection/test_snapshot.py`: manifest capture via pruned walk (skips `.git`, `.jj`, `.venv`, `node_modules`, `.maverick`, symlinked dirs); restore matrix per data-model.md (edit→rewrite, delete/rename-away→rewrite, create/rename-to→remove, symlink plant→unlink), each byte-identical and each yielding a `BlockRecord(operation="restore")` with inferred-op detail; restore failure logs error and continues; per-step snapshot failure doesn't abort the step and the post-step compare falls back to the squadron-open baseline manifest (FR-011, research R6)
- [X] T010 [P] [US1] Red tests for `PermissionGate` in `tests/unit/protection/test_permission_gate.py`: deny + reason on file-write tools targeting protected paths (`file_path`, `path`, `old_path`/`new_path`, notebook variants); allow on unprotected targets; allow on Bash-like/unknown tools; every deny appends a `BlockRecord(layer="pre-write")`; callback-internal exception → fail-closed literal match on default names (FR-011)
- [X] T011 [P] [US1] Red tests for session-based Agent execution in `tests/unit/agents/test_agent_session_protection.py` (fake runtime implementing `session(on_permission=...)`): `open()` creates a session and attaches the gate only when the capability probe says supported; `rotate_session()` closes and reopens the session; `close()` closes session then runtime; backstop snapshot/restore brackets `_execute_via_runtime` and `_execute_text_via_runtime`; `policy=None` disables both layers with zero behavior change

### Implementation for User Story 1

- [X] T012 [US1] Implement `src/maverick/protection/snapshot.py` — green T009 (`SnapshotManifest.capture`, `restore_and_report`; file IO via `asyncio.to_thread`, restores via `maverick.utils.atomic.atomic_write_text`; includes the research R6 fail-closed fallback — a baseline manifest captured once at squadron open is used for the post-step compare when a per-step snapshot fails, so a failed snapshot never leaves protected paths unguarded per FR-011)
- [X] T013 [US1] Implement `PermissionGate` in `src/maverick/protection/policy.py` — green T010
- [X] T014 [P] [US1] Add permission-callback capability probe in `src/maverick/runtime/agent_factory.py` (read the adapter's advertised `PERMISSION_CALLBACK` capability for a resolved binding; unit test in `tests/unit/runtime/test_agent_factory.py` or its existing test module)
- [X] T015 [US1] Adopt sessions + backstop in `src/maverick/agents/base.py` — green T011: `Agent.__init__` gains optional `protection_policy`/`block_collector` (DI, default `None`); `open()` builds `runtime.session(on_permission=gate)` when capable, else plain session/execute path; `_execute_via_runtime`/`_execute_text_via_runtime` wrap the call in snapshot → execute → `restore_and_report` → collector
- [X] T016 [US1] Build policy + collector once per run in `src/maverick/squadron/base.py` (`ProtectionPolicy.build(root=cwd, config=lookup_protection_config(self._config))`) and pass them to every agent constructed by the subclasses `src/maverick/squadron/{fly,refuel,plan,reconcile,spec_chain}.py`; extend the squadron unit tests accordingly (defaults-only config until US3 — `lookup_protection_config` may stub to defaults here if US3 hasn't landed)
- [X] T017 [P] [US1] Landing guard in `src/maverick/workflows/spec_chain/landing.py`: `land_step_artifacts` refuses to copy protected-matching paths from the landed tree, with unit test in `tests/unit/workflows/spec_chain/test_landing_protection.py` (research R10 belt-and-braces)
- [X] T018 [US1] Integration test `tests/integration/test_context_file_protection.py` (stub-runtime pattern from `tests/unit/workflows/conftest.py::stub_squadron_io`): the quickstart §2 scenario — protected restored byte-identical at all depths/operations, unprotected change survives, bead completes with normal outcome; spec-chain variant runs the same assertions with a workspace-rooted policy; plus an FR-010 assertion that a mutation performed *outside* the agent execute path (a workflow-owned write to a protected path between agent steps) is never reverted by the backstop

**Checkpoint**: MVP — protection enforces end-to-end; blocks are recorded in collectors but not yet surfaced (US2).

---

## Phase 4: User Story 2 - Every block is visible and auditable (Priority: P2)

**Goal**: each block/restore becomes a structured run event, one end-of-run warning summarizes them, and `protection-blocks.json` persists the audit trail; zero output on clean runs.

**Independent Test**: trigger a blocked write in the stub-runtime workflow; assert a `ContextFileWriteBlocked` event with role/workflow/path/operation/layer, a single end-of-run warning, an artifact matching contracts/block-event.md, and silence on a clean run (SC-002, FR-005/006).

### Tests for User Story 2

- [X] T019 [P] [US2] Red tests for `ContextFileWriteBlocked` in the existing events test module (`tests/unit/test_events.py`): field set per contracts/block-event.md, `to_dict()`/`event_from_dict` round-trip, `_EVENT_CLASSES` registration
- [X] T020 [P] [US2] Red tests for fly accumulation in `tests/unit/workflows/fly_beads/test_protection_backstop.py`: `protection_blocks` state slot seeded `[]` in the graph; collector drained after implement/fix, review, and aggregate agent calls; exactly one `StepOutput(level="warning", metadata={"block_count": n})` at loop exit when n≥1 and none when zero; slot never read by any fix-loop action (Guardrail 10)

### Implementation for User Story 2

- [X] T021 [US2] Add `ContextFileWriteBlocked` frozen dataclass to `src/maverick/events.py` and register in `_EVENT_CLASSES` — green T019
- [X] T022 [US2] Render the event in `src/maverick/cli/workflow_executor.py` as a yellow warning line (escape agent-influenced `detail`/paths with `rich.markup.escape`)
- [X] T023 [US2] Fly wiring — green T020: seed `protection_blocks` in `src/maverick/workflows/fly_beads/burr_graph.py`; drain the squadron collector into the slot and emit events in `src/maverick/workflows/fly_beads/actions.py` after each agent-calling site; loop-exit summary warning; persist `.maverick/runs/<run-id>/protection-blocks.json` (schema per contracts/block-event.md, only when non-empty, write-failure degrades to warning) from final state in `src/maverick/workflows/fly_beads/workflow.py`
- [X] T024 [US2] Spec-chain wiring: `protection_blocks: list[dict]` on `ChainState` in `src/maverick/workflows/spec_chain/models.py` (checkpointed via existing `spec-chain.json` state writes); per-step drain in `src/maverick/workflows/spec_chain/workflow.py`; artifact write at chain completion; blocks line in `_render_summary_and_exit` in `src/maverick/cli/commands/spec.py`; tests in `tests/unit/workflows/spec_chain/test_protection_blocks.py` including survive-resume
- [X] T025 [US2] Remaining agent-bearing workflows (reconcile, refuel `--enrich`, generate_flight_plan, land curation): shared drain-and-report helper (in `src/maverick/protection/records.py` or `src/maverick/workflows/base.py`) called at workflow end — artifact + one `emit_output(level="warning")`; unit tests beside each workflow's existing test module
- [X] T026 [US2] Extend `tests/integration/test_context_file_protection.py`: per-attempt events (repeated retries individually recorded, summarized once), artifact schema assertion, and explicit no-assumption-ledger-entries assertion (FR-005)

**Checkpoint**: US1 + US2 — enforcement plus full audit trail.

---

## Phase 5: User Story 3 - Repositories that want agents to maintain context files can opt in (Priority: P3)

**Goal**: `protection:` block in maverick.yaml — `additional_globs` extends the protected set, `allowlist` exempts; malformed config degrades to defaults with a warning, never widens access.

**Independent Test**: allowlist `AGENTS.md`, run stub workflow editing it → edit lands, `CLAUDE.md` still blocked; add custom glob → matching file blocked; malformed block → defaults + warning (SC-004, FR-007/008/012).

### Tests for User Story 3

- [X] T027 [P] [US3] Red tests in `tests/unit/config/test_protection_config.py` (follow `test_assumptions_schedule_config.py` idioms: `clean_env`, `temp_dir`, YAML heredoc, `load_config()`): absent block → defaults; valid block parses; malformed shape (list, string, wrong types) → defaults + `logger.warning`, load does NOT raise; individually invalid pattern dropped with warning while the rest applies; `MAVERICK_PROTECTION__...` env override; `__all__` exports

### Implementation for User Story 3

- [X] T028 [US3] Add `protection: dict[str, Any] | None = None` raw passthrough to `MaverickConfig` in `src/maverick/config.py` and implement `lookup_protection_config()` in `src/maverick/protection/config.py` (the `lookup_tiers_config` idiom, warning keys `protection_config_invalid_shape`/`protection_config_parse_failed`) — green T027
- [X] T029 [US3] Config-driven rules in `src/maverick/protection/{policy.py,matching.py}`: compile `additional_globs`/`allowlist` with `pathspec` gitwildmatch; allowlist evaluated first; extend `tests/unit/protection/test_matching.py` and `test_policy.py` with the SC-004 matrix (allowlist exempts exactly its matches; custom glob blocks; allowlist entry never disables an unrelated protection)
- [X] T030 [US3] Replace the defaults-only policy construction in `src/maverick/squadron/base.py` with `lookup_protection_config(self._config)` (remove any T016 stub), extend squadron tests for a configured run
- [X] T031 [US3] Allowlist + custom-glob variants in `tests/integration/test_context_file_protection.py`: allowlisted write lands with no block event; non-allowlisted protected write still blocked in the same run (SC-004)

**Checkpoint**: all three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T032 Retire the orphaned `src/maverick/hooks/` package (stubs unwired since ACP migration — research R3): delete the package, port any still-referenced normalization into `src/maverick/protection/matching.py`, remove `tests/unit/hooks/`, `tests/unit/test_hooks_safety.py`, `tests/unit/test_hooks_logging.py`, `tests/integration/hooks/`, and prune now-orphaned `src/maverick/exceptions/hooks.py` exports from `src/maverick/exceptions/__init__.py`
- [X] T033 [P] Document the feature: `protection:` block + default set + backstop semantics in `CLAUDE.md` (new subsection near the assumption-ledger docs) and a pointer from `specs/056-context-file-protection/contracts/protection-config.md` if wording drifted during implementation
- [X] T034 Verify Layer 1 live on Claude (airframe v0.9.2, already pinned in T001): confirm the capability probe attaches the gate for `claude` bindings, wire airframe's portable `test_integration_permission_callback_denies_tool` contract from `airframe.testing.integration` into `tests/integration/test_context_file_protection.py` if applicable, and run the quickstart §4 live smoke
- [X] T035 Run quickstart.md validation end-to-end (§1–§3) and `make format-fix && make ci` as the pre-push gate

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none
- **Foundational (Phase 2)**: after Setup — BLOCKS all stories
- **US1 (Phase 3)**: after Foundational
- **US2 (Phase 4)**: after US1 (surfaces the records US1's enforcement produces; T019/T021/T022 are independent of US1 and may start after Foundational)
- **US3 (Phase 5)**: after Foundational; T030 touches the same squadron seam as T016, so land US1 first
- **Polish (Phase 6)**: after desired stories (airframe v0.9.2 shipped, so T034 has no external blocker — it needs only an authenticated Claude binding for the live smoke)

### Within stories

Red tests before green implementations (T003–T005 → T006–T008; T009–T011 → T012–T015; T019–T020 → T021–T023; T027 → T028). Models before services before wiring: records/matching → policy → snapshot/gate → agent/squadron → workflows.

### Parallel Opportunities

- Phase 2: T003, T004, T005 together; then T006–T008 (T006/T007 in parallel, T008 after both)
- US1: T009, T010, T011 together; T012–T013 in parallel; T014 and T017 parallel to T015; T016 after T015
- US2: T019, T020 together; T021/T022 parallel; T024/T025 parallel after T021
- US3: T027 alone, then T028 → T029 → T030/T031
- Polish: T033 parallel to anything; T032 after US1–US3 (it removes tests that must stay green until then)

## Parallel Example: User Story 1

```bash
# Red tests together:
Task: "T009 snapshot/restore tests in tests/unit/protection/test_snapshot.py"
Task: "T010 PermissionGate tests in tests/unit/protection/test_permission_gate.py"
Task: "T011 Agent session tests in tests/unit/agents/test_agent_session_protection.py"

# Then greens:
Task: "T012 snapshot.py"  +  Task: "T013 PermissionGate"   (parallel)
Task: "T014 capability probe"  +  Task: "T017 landing guard"  (parallel with T015)
```

## Implementation Strategy

**MVP first**: Phases 1–3 (T001–T018) deliver the P1 guarantee — protected files cannot be corrupted — with audit limited to collector contents. Stop, run quickstart §2, validate.

**Incremental**: add US2 (visibility) → validate events/artifact; add US3 (config) → validate allowlist matrix; polish.

**External dependency**: resolved — airframe v0.9.2 (with the #79 permission-gating fix) shipped 2026-08-07 and is pinned at T001, so pre-write blocking on Claude is active from the MVP onward; the backstop still independently carries the universal guarantee.

## Notes

- Zero model calls anywhere in this feature (Principle XIII / Guardrail 10)
- `protection_blocks` never shares a slot with fixer inputs (Guardrail 10 corollary)
- All new file IO on async paths goes through `asyncio.to_thread` (Guardrail 1)
- Commit after each task or logical red/green pair
