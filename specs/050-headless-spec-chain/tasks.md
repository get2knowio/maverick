# Tasks: Headless Spec Kit Chain (`maverick spec`)

**Input**: Design documents from `/specs/050-headless-spec-chain/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the project constitution (Principle V, Test-First) mandates TDD; tests are written before implementation within every story.

**Organization**: Tasks are grouped by user story. US1 delivers the full chain running headlessly (clarify uses the non-interactive convention, analyze is report-only); US2 adds the ledger contract, US3 halt/resume hardening, US4 remediation beads + adoption, US5 init verification.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US5 from spec.md
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Package skeletons and verification of the two implementation gates flagged in research.md

- [ ] T001 Verify implementation gates and record findings in specs/050-headless-spec-chain/research.md: (a) whether the pinned airframe `AgentRuntime` supports per-run working-directory binding (R1 — constructor or `execute()` parameter); (b) whether the `bd` CLI supports re-parenting an existing bead, e.g. `bd update --parent` (R6). Update the affected design decisions in place if either answer differs from the plan's assumption.
- [ ] T002 Create package skeletons with empty `__init__.py` and module stubs: src/maverick/workflows/spec_chain/{__init__.py,constants.py,models.py,state.py,steps.py,clarify.py,landing.py,workflow.py}, src/maverick/workspace/{__init__.py,spec_chain.py}, src/maverick/agents/spec_chain.py, plus test directories tests/unit/workflows/spec_chain/, tests/unit/workspace/, tests/integration/spec_chain/ with directory-scoped conftest.py placeholders.
- [ ] T003 [P] Add `SpecChainError` hierarchy (SpecChainError, SpecChainPreflightError, SpecChainStepError, SpecChainWorkspaceError, SpecChainStateError) in src/maverick/exceptions/spec_chain.py and export from src/maverick/exceptions/__init__.py.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Typed models, chain-state persistence, hidden workspace lifecycle, and the airframe-backed agent — everything every story builds on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 [P] Write failing unit tests for ChainStep ordering + ChainState/StepRecord/ClarifyDecision/StepReport validation and state-transition invariants (per data-model.md) in tests/unit/workflows/spec_chain/test_models.py.
- [ ] T005 [P] Write failing unit tests for atomic state save/load and feature-keyed discovery (newest non-terminal match, per contracts/chain-state.md) in tests/unit/workflows/spec_chain/test_state.py.
- [ ] T006 [P] Write failing unit tests for hidden-workspace lifecycle (per-feature path `~/.maverick/workspaces/<project-slug>/spec-chain/<feature>/`, create via `JjClient.workspace_add`, reuse when state active, forget+recreate on fresh run, isolation between concurrent features, PRD copy-in) with a stubbed JjClient in tests/unit/workspace/test_spec_chain_workspace.py.
- [ ] T007 Implement `ChainStep` enum, step order, labels (`spec-remediation`), state keys (`speckit_feature`, `remediation_source`, `finding_fingerprint`, `source_ref`), and timeout constants in src/maverick/workflows/spec_chain/constants.py.
- [ ] T008 Implement ChainState, StepRecord, ClarifyDecision, StepReport (+ ReportedQuestion/ReportedFinding), AnalyzeFinding, and SpecChainReport models per data-model.md in src/maverick/workflows/spec_chain/models.py (make T004 pass).
- [ ] T009 Implement atomic chain-state persistence (temp+rename), `metadata.json` integration via `runway.run_metadata`, and `discover_resumable(feature, base)` scan in src/maverick/workflows/spec_chain/state.py (make T005 pass).
- [ ] T010 Implement hidden-workspace helper (create/reuse/forget under `~/.maverick/workspaces/<project-slug>/spec-chain/`, PRD copy-in, all jj ops through `JjClient`) in src/maverick/workspace/spec_chain.py (make T006 pass).
- [ ] T011 Implement `SpecChainAgent` (subclass of `maverick.agents.base.Agent`; `provider_tier="generate"`, `result_model=StepReport`, per-run cwd binding per T001 findings) in src/maverick/agents/spec_chain.py, and `SpecChainSquadron` owning its single runtime in src/maverick/squadron/ (following existing squadron module layout); add unit tests with a fake runtime in tests/unit/workflows/spec_chain/test_agent.py.

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — PRD to complete spec artifacts, hands-off (Priority: P1) 🎯 MVP

**Goal**: `maverick spec <feature> --from-prd <file>` runs specify → clarify → plan → tasks → analyze headlessly in the hidden workspace via the repo's own `/speckit.*` commands; completed-step artifacts land atomically in `specs/NNN-<feature>/`. (Clarify runs the non-interactive convention without ledger filing; analyze is executed read-only with findings reported but not yet persisted as beads.)

**Independent Test**: Quickstart Scenario 1 — run against a sample PRD in a Spec Kit repo (stubbed runtimes in CI); a new `specs/NNN-<feature>/` appears with spec/plan/tasks markdown, zero interactive prompts, exit 0.

### Tests for User Story 1 (write first, ensure they FAIL)

- [ ] T012 [P] [US1] Write failing unit tests for per-step prompt builders (slash-command invocation, inline-body fallback when the provider lacks a command surface, structured-report instruction, PRD injection for specify) in tests/unit/workflows/spec_chain/test_steps.py.
- [ ] T013 [P] [US1] Write failing unit tests for atomic per-step artifact landing (workspace → checkout staged copy+rename, feature-dir readback after specify via specs/ diff + `.specify/feature.json` cross-check, filesystem-as-ground-truth step verification) in tests/unit/workflows/spec_chain/test_landing.py.
- [ ] T014 [P] [US1] Write failing integration test for the full five-step happy path (tmp jj+git repo fixture with `.claude/commands/speckit.*.md` and `.specify/` markers, stubbed airframe runtime writing canned artifacts) asserting strict ordering, artifact landing, final report counts, that no interactive input is ever requested (FR-004), and that spec/plan/tasks artifact content is byte-identical before and after the analyze step (FR-011) in tests/integration/spec_chain/test_full_chain.py.
- [ ] T015 [P] [US1] Write failing CLI contract tests for `maverick spec` (argument/option parsing, preflight failures → exit 2 per contracts/cli-spec.md: missing PRD, missing Spec Kit, missing bd) in tests/unit/cli/test_spec_command.py.

### Implementation for User Story 1

- [ ] T016 [US1] Implement per-step prompt builders and step-output handling (five steps; specify consumes the copied PRD; each prompt ends with the StepReport structured-output instruction) in src/maverick/workflows/spec_chain/steps.py (make T012 pass).
- [ ] T017 [US1] Implement per-step artifact landing and feature-dir readback in src/maverick/workflows/spec_chain/landing.py (make T013 pass).
- [ ] T018 [US1] Implement `SpecChainWorkflow` (async orchestration: preflight → workspace → sequential steps with tenacity retries and explicit timeouts → land → checkpoint after every transition → SpecChainReport; step success gated on artifacts, not agent claims) in src/maverick/workflows/spec_chain/workflow.py (make T014 pass).
- [ ] T019 [US1] Implement the `maverick spec` Click command (async_command, `cli_error_handler`, preflight per contracts/cli-spec.md, Rich sequential step lines + final summary per CLI output rules) in src/maverick/cli/commands/spec.py, and register `"spec"` in `_LAZY_COMMANDS` in src/maverick/main.py (make T015 pass).
- [ ] T020 [US1] Wire structured logging (`maverick.logging.get_logger`) for chain lifecycle events (step start/finish, landing, checkpoint) across src/maverick/workflows/spec_chain/workflow.py and landing.py, keeping raw structlog out of CLI output.

**Checkpoint**: US1 fully functional — MVP: PRD in, reviewable artifacts out, hands-off

---

## Phase 4: User Story 2 — Clarify decisions on the record (Priority: P2)

**Goal**: Every clarify question becomes an assumption-ledger entry (question/adopted/alternatives/severity) via interception where the runtime supports it, else via parsing the non-interactive defaults out of the spec — filed by the workflow, never the agent.

**Independent Test**: Quickstart Scenario 2 — run clarify against a vague PRD (stubbed runtime emitting questions); every question appears as an open ledger bead with `assumption_owner_spec=NNN-<feature>`; `maverick brief` counts them; `maverick review` can answer/waive one.

### Tests for User Story 2 (write first, ensure they FAIL)

- [ ] T021 [P] [US2] Write failing unit tests for `record_standalone_assumption` (epic-less bead shape, `source_ref` state key, dedup-by-question within `owner_spec`, severity escalation on merge, per contracts/ledger-and-beads.md) in tests/unit/assumptions/test_standalone_ledger.py.
- [ ] T022 [P] [US2] Write failing unit tests for the clarify policy seam (capability probe selects interception vs non-interactive; interception callback adopts recommended option and captures ClarifyDecision; question with no recommended option → adopted informed default recorded identically, or clarify blocked/halted when no defensible default exists — never silently skipped; non-interactive path parses Assumptions/Clarifications sections from an updated spec.md into ClarifyDecisions; severity defaults low and escalates per the R2 signal-category list) in tests/unit/workflows/spec_chain/test_clarify.py.
- [ ] T023 [P] [US2] Write failing regression test proving standalone ledger entries flow through existing readers unchanged (`per_spec_counts`, `open_blocking_entries`, `maverick review` label lookup) in tests/unit/assumptions/test_standalone_compat.py.

### Implementation for User Story 2

- [ ] T024 [US2] Implement `record_standalone_assumption` in src/maverick/assumptions/ledger.py, reusing `_build_description` and the existing label/state-key constants (make T021 and T023 pass).
- [ ] T025 [US2] Implement the clarify policy seam (`ClarifyPolicy` with interception + non-interactive paths, runtime capability probe, spec.md defaults parser, severity heuristic per FR-007a) in src/maverick/workflows/spec_chain/clarify.py (make T022 pass).
- [ ] T026 [US2] Wire clarify into the workflow: after the clarify step succeeds, file each ClarifyDecision via `record_standalone_assumption` (bd runs in the user checkout, never the workspace), record `ledger_bead_id` back onto ChainState, and surface the count in SpecChainReport — in src/maverick/workflows/spec_chain/workflow.py; extend tests/integration/spec_chain/test_full_chain.py to assert ledger filing on both paths.

**Checkpoint**: US1 + US2 — headless runs leave a complete, auditable decision trail

---

## Phase 5: User Story 3 — Strict ordering, halt, and resume (Priority: P2)

**Goal**: A failed/blocked clarify halts the chain (exit 1, plan/tasks/analyze never run); interrupts checkpoint cleanly (exit 130); re-running auto-resumes from the first non-succeeded step, never regenerating landed artifacts; collision rules per FR-015.

**Independent Test**: Quickstart Scenario 3 — force a clarify failure: exit 1, spec.md landed, no plan.md, persisted state shows halted-at-clarify; re-run resumes at clarify without re-running specify.

### Tests for User Story 3 (write first, ensure they FAIL)

- [ ] T027 [P] [US3] Write failing integration tests for halt semantics (clarify failure → status halted, downstream steps pending/skipped, exit 1, resume hint printed; mid-chain plan failure → same shape; analyze failure → warning + exit 0 per FR-012) in tests/integration/spec_chain/test_halt.py.
- [ ] T028 [P] [US3] Write failing integration tests for resume (halted chain re-run continues from failed step; landed-artifact verification re-runs a step whose artifacts were deleted from the checkout; PRD digest mismatch warns without re-running specify; completed chain + same feature → collision error, exit 2) in tests/integration/spec_chain/test_resume.py.
- [ ] T029 [P] [US3] Write failing unit tests for interrupt handling (graceful SIGINT during a step → state checkpointed with status `halted`, exit 130, workspace preserved for resume; only a hard crash leaves status `running`, which resume treats as stale-resumable per contracts/chain-state.md) in tests/unit/workflows/spec_chain/test_interrupt.py.

### Implementation for User Story 3

- [ ] T030 [US3] Implement resume resolution in the workflow + CLI (discovery via `state.discover_resumable`, `--from-prd` optional on resume, landed-artifact verification, PRD-digest warning, collision rules) across src/maverick/workflows/spec_chain/workflow.py and src/maverick/cli/commands/spec.py (make T028 pass).
- [ ] T031 [US3] Implement halt classification and exit-code mapping (clarify/step failure → halted + exit 1; preflight → exit 2; analyze failure → `[yellow]Warning:[/yellow]` + exit 0) in src/maverick/workflows/spec_chain/workflow.py and src/maverick/cli/commands/spec.py (make T027 pass).
- [ ] T032 [US3] Implement graceful SIGINT handling (checkpoint current state, mark step failed-by-interrupt, print resume hint, exit 130 — mirroring fly's two-stage Ctrl-C pattern where applicable) in src/maverick/cli/commands/spec.py (make T029 pass).

**Checkpoint**: The chain is trustworthy under failure — halt/resume verified end-to-end

---

## Phase 6: User Story 4 — Analyze findings become remediation beads (Priority: P3)

**Goal**: Each analyze finding is persisted as a standalone fingerprinted `spec-remediation` bead; `refuel --speckit` adopts them under the epic it creates; findings never block or fail the run.

**Independent Test**: Quickstart Scenario 4 — chain run with stubbed findings exits 0 and creates one bead per finding keyed `speckit_feature=NNN-<feature>`; a subsequent `refuel --speckit` parents them under the new epic.

### Tests for User Story 4 (write first, ensure they FAIL)

- [ ] T033 [P] [US4] Write failing unit tests for remediation-bead creation (bead shape/labels/state keys per contracts/ledger-and-beads.md, fingerprint idempotency across re-runs, per-bead best-effort error isolation) in tests/unit/workflows/spec_chain/test_remediation.py.
- [ ] T034 [P] [US4] Write failing unit tests for the adoption primitive (preferred `BeadClient.update_parent`, or the dependency-edge + `adopted_by_epic` stamp fallback per T001's finding) in tests/unit/beads/test_update_parent.py, and for the refuel adoption step (query unparented `spec-remediation` beads by `speckit_feature`, idempotent skip of already-adopted) in tests/unit/workflows/refuel_speckit/test_adoption.py.

### Implementation for User Story 4

- [ ] T035 [US4] Implement remediation-bead creation from analyze findings (parse ReportedFindings, fingerprint, create via `BeadClient` in the user checkout, record ids on ChainState, count in SpecChainReport) in src/maverick/workflows/spec_chain/workflow.py plus a `create_remediation_beads` helper in src/maverick/library/actions/beads.py (make T033 pass).
- [ ] T036 [US4] Implement the adoption primitive per T001's finding (`update_parent` in src/maverick/beads/client.py, or dependency-edge fallback) (make the T034 client tests pass).
- [ ] T037 [US4] Add the post-ingest adoption step to `SpeckitRefuelWorkflow` in src/maverick/workflows/refuel_speckit/workflow.py (fresh and delta paths, best-effort per bead) and extend the workflow's existing test module to cover it (make the T034 adoption tests pass).

**Checkpoint**: Analyze closes the loop into the beads workflow without ever blocking

---

## Phase 7: User Story 5 — `maverick init` verifies Spec Kit (Priority: P3)

**Goal**: Init detects Spec Kit presence (`.specify/` + supported version), offers installation on interactive TTYs, succeeds either way; `maverick spec` independently fail-fasts with guidance.

**Independent Test**: Quickstart Scenario 5 — init in a repo without `.specify/` offers install; decline → exit 0 with notice; `maverick spec` then exits 2 with install guidance.

### Tests for User Story 5 (write first, ensure they FAIL)

- [ ] T038 [P] [US5] Write failing unit tests for `check_speckit_installed` (missing `.specify/`, missing/unsupported `speckit_version`, supported → pass; advisory never hard-fails init) in tests/unit/init/test_speckit_prereq.py.
- [ ] T039 [P] [US5] Write failing unit tests for the init offer flow (interactive accept → installer invoked via `CommandRunner`; decline → notice + exit 0; non-interactive → notice only; idempotent re-init silent when compatible) in tests/unit/init/test_speckit_offer.py.

### Implementation for User Story 5

- [ ] T040 [US5] Implement `check_speckit_installed(cwd)` in src/maverick/init/prereqs.py, reusing the `.specify/init-options.json` version gate from `maverick.speckit.detect` (make T038 pass).
- [ ] T041 [US5] Implement the offer-to-install step (Click confirm; installer invoked via `CommandRunner` as `uvx --from 'specify-cli==<pin>' specify init --here` with `<pin>` a named constant selecting the newest release whose templates satisfy `SUPPORTED_SPECKIT_RANGE` (>=0.14,<0.15); `InitResult.speckit_installed` field; notices per contracts/cli-spec.md) in src/maverick/init/__init__.py and src/maverick/cli/commands/init.py (make T039 pass).

**Checkpoint**: All five user stories independently functional

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T042 [P] Amend governance docs for the scoped hidden-workspace exception: CLAUDE.md Guardrail 0 (single-repo model exception for the spec chain) and .specify/memory/constitution.md Appendix E (replace the stale WorkspaceManager narrative with the spec-chain jj-workspace mechanism), bumping the constitution's Sync Impact Report.
- [ ] T043 [P] Update user-facing docs: add `maverick spec` to the CLI Workflows table in CLAUDE.md and the README command reference, including resume and ledger behavior.
- [ ] T044 [P] Add module docstrings and Google-style docstrings across the new public surface (workflows/spec_chain/*, workspace/spec_chain.py, agents/spec_chain.py, new ledger/beads functions); verify no `Path.cwd()` defaults inside src/maverick/workflows/ (Guardrail 7 grep).
- [ ] T045 Run quickstart.md Scenarios 1–5 against /workspaces/sample-maverick-project with a live provider binding; record outcomes (and any deviations as fixes or new tasks) in specs/050-headless-spec-chain/quickstart.md.
- [ ] T046 Run `make format-fix && make ci` and fix all lint/type/test failures across the branch (pre-push gate).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 has no dependencies; T002/T003 immediately after. T001's findings gate T011 (cwd binding) and T036 (adoption primitive) — surface them early.
- **Foundational (Phase 2)**: Depends on Setup. Tests T004–T006 first (parallel), then T007 → T008 → T009/T010 (parallel) → T011. BLOCKS all user stories.
- **US1 (Phase 3)**: After Phase 2. Delivers the MVP.
- **US2 (Phase 4)**: After Phase 2; T026 (workflow wiring) touches workflow.py and therefore lands after T018. T021/T023/T024 (ledger extension) are independent of US1.
- **US3 (Phase 5)**: After US1 (halting/resume harden the US1 workflow); independent of US2/US4.
- **US4 (Phase 6)**: T033/T035 after US1 (analyze step exists); T034/T036/T037 (adoption) are independent of the chain and only need Phase 1–2.
- **US5 (Phase 7)**: Only needs Phase 1 (touches init, not the chain). Can run any time after Setup.
- **Polish (Phase 8)**: After all desired stories; T042/T043/T044 parallel; T045 → T046 last.

### Within Each User Story

- Tests are written first and MUST fail before implementation (Constitution Principle V).
- Models → services/helpers → workflow wiring → CLI.
- Same-file tasks are sequential (workflow.py: T018 → T026 → T030/T031 → T035).

### Parallel Opportunities

- Phase 2: T004, T005, T006 together; then T009 + T010 together.
- US1: T012–T015 (all four test files) together.
- US2 ledger track (T021→T024) parallel to clarify track (T022→T025).
- US3: T027–T029 together.
- US4 adoption track (T034/T036/T037) parallel to remediation track (T033/T035).
- US5 is fully parallel to US2–US4 once Setup is done.
- Polish: T042, T043, T044 together.

## Parallel Example: User Story 1

```bash
# Write all US1 test files together (different files, no deps):
Task: "T012 prompt-builder tests in tests/unit/workflows/spec_chain/test_steps.py"
Task: "T013 landing tests in tests/unit/workflows/spec_chain/test_landing.py"
Task: "T014 full-chain integration test in tests/integration/spec_chain/test_full_chain.py"
Task: "T015 CLI contract tests in tests/unit/cli/test_spec_command.py"

# Then implement sequentially where files converge:
Task: "T016 steps.py" ; Task: "T017 landing.py"   # parallel (different files)
Task: "T018 workflow.py"                            # after T016+T017
Task: "T019 cli/commands/spec.py + main.py"         # after T018
```

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 (gates verified) → Phase 2 (foundation) → Phase 3 (US1).
2. **STOP and VALIDATE**: quickstart Scenario 1 with stubbed runtimes, then a live smoke run in sample-maverick-project.
3. US1 alone is a demoable product: PRD → reviewable spec/plan/tasks, hands-off.

### Incremental Delivery

- US1 (MVP) → US2 (audit trail — the safety half of headless) → US3 (halt/resume hardening) → US4 (beads loop) → US5 (init convenience) → Polish.
- US2 and US3 are both P2: prefer US2 first (no decision off the record) if delivering to users between increments; they touch mostly disjoint files and can proceed in parallel otherwise.

### Notes

- Every task that shells out uses the canonical wrappers (JjClient, BeadClient, CommandRunner, GitPython) — no new subprocess wrappers.
- Commit after each task or logical group; keep `make test-fast` green throughout; `make ci` before push (T046).
