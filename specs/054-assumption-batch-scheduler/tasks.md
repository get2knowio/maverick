# Tasks: Assumption Batch Scheduler

**Input**: Design documents from `/specs/054-assumption-batch-scheduler/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the constitution mandates test-first (Principle V,
red-green-refactor). Every test task must be written and observed failing
before its implementation task.

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Include exact file paths in descriptions

## Path Conventions

Single project: `src/maverick/`, `tests/` at repository root (per plan.md).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton so all subsequent tasks have homes

- [X] T001 Create package skeleton: `src/maverick/assumptions/schedule/__init__.py` (empty public-surface module), empty `models.py`, `evaluate.py`, `state.py`, `deliver.py` in the same directory, plus `tests/unit/assumptions/schedule/__init__.py`; confirm `make lint` and `make typecheck` stay green

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `created_at` plumbing, config models, domain dataclasses, and persisted-state module — every user story reads these

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Write failing tests for `created_at` propagation: extend `tests/unit/assumptions/test_models.py` (AssumptionRecord carries `created_at`), `tests/unit/assumptions/test_serialize.py` (`entry_to_dict` row includes `created_at`), and `tests/unit/assumptions/test_ledger_query.py` (`report_entries` copies `created_at` from `BeadDetails`, including the legacy-entry path)
- [X] T003 Add `created_at: str | None = None` to `BeadDetails` in `src/maverick/beads/models.py` (bd emits UTC ISO-8601 per research R1 probe)
- [X] T004 Thread `created_at` through the ledger: add field to `AssumptionRecord` in `src/maverick/assumptions/models.py`, populate it in `_record_from_details` and `_legacy_record_from_details` in `src/maverick/assumptions/ledger.py`, and emit it from `entry_to_dict` in `src/maverick/assumptions/serialize.py`; T002 tests go green
- [X] T005 [P] Write failing config tests in `tests/unit/config/test_assumptions_schedule_config.py`: defaults per contracts/config-schema.md, HH:MM validation, duplicate/empty windows rejected, `quiet_hours.start == end` rejected, non-decreasing backoff enforced, `auto_waive_low.enabled` without `rationale` rejected, env-override via `MAVERICK_ASSUMPTIONS__SCHEDULE__...`
- [X] T006 Implement config models in `src/maverick/config.py`: `QuietHoursConfig`, `AutoWaivePolicyConfig`, `AssumptionScheduleConfig`, `AssumptionsConfig`; wire `MaverickConfig.assumptions` with `default_factory`; export via `__all__`; T005 tests go green
- [X] T007 Implement evaluation domain models in `src/maverick/assumptions/schedule/models.py`: frozen dataclasses `WindowOccurrence`, `BatchSummary`, `DeliveryDecision`, `SkipDecision`, `AutoWaiveDecision`, `EvaluationOutcome`, enums `DecisionKind`, `SkipReason` (shapes per data-model.md §3)
- [X] T008 [P] Write failing state tests in `tests/unit/assumptions/schedule/test_state.py`: round-trip load/save of `DeliveryState` (schema per contracts/delivery-state-schema.md), atomic write via `maverick.utils.atomic`, missing file → empty state, `schema_version != 1` → refusal error, corrupt file → empty state + structured warning, pid lockfile acquire/release/stale-reclaim, FR-023 prune predicate (terminal + 90 days, never prunes records referencing open entries)
- [X] T009 Implement `src/maverick/assumptions/schedule/state.py`: frozen Pydantic models `DeliveryState`, `WindowDecisionRecord`, `EntryTrackingRecord`, `TerminalOutcome`, `DeliveryRecord`; `async load_state(cwd)` / `async save_state(state, cwd)` using `asyncio.to_thread(atomic_write_json, ...)` under `<cwd>/.maverick/notify/state.json`; `async acquire_lock(cwd) -> bool` / `async release_lock(cwd)` mirroring `src/maverick/workflows/reconcile/state.py`'s pid pattern; `prune(state, now) -> DeliveryState`; T008 tests go green

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Batched morning summons (Priority: P1) 🎯 MVP

**Goal**: Medium-severity entries accumulate and deliver as exactly one ntfy
batch per review window, respecting quiet hours and minimum batch size; low
stays silent but counted; the summons carries counts/specs/age/invocation and
never entry contents.

**Independent Test**: quickstart.md Scenarios 1–3 — seed medium entries, run
`maverick notify --json` at a simulated 09:00 with quiet hours 22:00–07:00,
verify one delivery with correct summary; re-run delivers nothing; unconfigured
repo is an exit-0 no-op.

### Tests for User Story 1 (write first, observe failing)

- [X] T010 [P] [US1] Write failing window-evaluation tests in `tests/unit/assumptions/schedule/test_evaluate_windows.py`: occurrence due/not-yet-due, delayed-cron delivery after window time, `already-delivered` skip on decided occurrence, min-batch-size skip rolls entries forward, midnight-spanning quiet hours suppress and shift occurrences to quiet-end (research R8), DST spring-forward gap and fall-back non-double-delivery (research R6), empty-batch occurrence records `empty` decision (FR-014) — all via direct `evaluate(entries, schedule, state, now)` calls with injected aware local datetimes
- [X] T011 [P] [US1] Write failing severity-tier tests in `tests/unit/assumptions/schedule/test_evaluate_severity.py`: medium batches at windows only, low never triggers delivery but appears in `BatchSummary.counts` (clarification Q5) and yields `low-never-proactive` skip entries, legacy entries (`is_legacy=True`, synthesized medium) batch like medium (FR-019), resolved-before-window entries excluded structurally
- [X] T012 [P] [US1] Write failing deliverer tests in `tests/unit/assumptions/schedule/test_deliver.py` using `httpx.MockTransport`: POST to `{server}/{topic}`, Title/Priority/Tags headers and body template per contracts/ntfy-payload.md, `window-batch` → priority `default`, retry on 5xx/transport error (3 attempts, tenacity), no retry on 4xx, exhausted retries raise the typed delivery error, body contains no entry-content fields
- [X] T013 [P] [US1] Write failing CLI tests in `tests/unit/cli/test_notify_command.py` (human mode: unconfigured single-line no-op exit 0, "Nothing due.", delivery completion line, `✗` + warning on failure) and `tests/unit/cli/commands/test_notify_json.py` (envelope per contracts/cli-notify-json.md: verbs `notify.run`/`notify.dry-run`, `configured: false` no-op `ok: true`, schedule-present-but-notifications-unusable → `validation` naming the missing key, bd unavailable → `bd-unavailable`, delivery exhausted → `delivery-failed` exit 1, dry-run zero side effects) — mock `BeadClient` per house pattern, invoke via `cli_runner`

### Implementation for User Story 1

- [X] T014 [US1] Implement window-batch evaluation in `src/maverick/assumptions/schedule/evaluate.py`: pure `evaluate(entries, schedule, state, now) -> EvaluationOutcome` covering occurrence computation (fold-aware `zoneinfo` arithmetic), quiet-hours shifting, min-batch-size, batching by severity tier, skips with `rule` citations, age from `created_at` with `first_seen` fallback (research R1); T010 + T011 go green
- [X] T015 [US1] Implement `src/maverick/assumptions/schedule/deliver.py`: `NtfyDeliverer` with `httpx.AsyncClient` (10s timeout), `tenacity.AsyncRetrying`, payload construction from `BatchSummary` only; typed `DeliveryFailedError`; T012 goes green
- [X] T016 [US1] Add `ErrorKind.DELIVERY_FAILED = "delivery-failed"` to `src/maverick/cli/json_output.py` and extend `tests/unit/cli/test_json_output.py` for the new kind (additive registry contract)
- [X] T017 [US1] Implement `src/maverick/cli/commands/notify.py`: `@async_command` with `--dry-run`/`--json`; resolve `cwd` once; load config; FR-021 inert path; notifications-usable enforcement; bd preflight (`bd_ready_reason` + `verify_available()` translated to `bd-unavailable`); read entries via `report_entries`; call `evaluate` with `datetime.now().astimezone()`; deliver due decisions; persist state write-after-success per decision (FR-012); emit envelope or Rich output per contracts/cli-notify-json.md; T013 goes green
- [X] T018 [US1] Register the command: add `"notify"` entry to `_LAZY_COMMANDS` in `src/maverick/main.py` pointing at `maverick.cli.commands.notify:notify` with help text; verify `maverick notify --help` renders

**Checkpoint**: MVP — quickstart Scenarios 1–3 pass end-to-end; `make test-fast` green

---

## Phase 4: User Story 2 - High-severity interrupt (Priority: P2)

**Goal**: High-severity entries deliver as `urgent` interrupts at the next
permissible evaluation, gated by `high_overrides_quiet`, exactly once per
entry.

**Independent Test**: quickstart.md Scenario 4 — record a high entry, run
outside any window, receive one urgent push; repeat inside quiet hours under
both policy values; re-run never re-delivers.

> **Scope note**: spec US2 acceptance scenario 4 (backoff re-notification of
> aged high entries) is deliberately implemented in Phase 6 (T025/T027) with
> the rest of the escalation machinery — this phase's checkpoint covers US2
> scenarios 1–3 only.

### Tests for User Story 2 (write first, observe failing)

- [X] T019 [P] [US2] Write failing interrupt tests in `tests/unit/assumptions/schedule/test_evaluate_severity.py` (extend): high entry → `INTERRUPT` decision outside windows, `interrupt_delivered_at` set in `state_after` and suppresses re-delivery, quiet hours + `high_overrides_quiet=true` → delivers, `=false` → `quiet-hours` skip then due at first post-quiet evaluation, multiple simultaneous high entries coalesce into one interrupt delivery with combined summary

### Implementation for User Story 2

- [X] T020 [US2] Implement interrupt tier in `src/maverick/assumptions/schedule/evaluate.py`: high-severity decision path with `high_overrides_quiet` gating and `EntryTrackingRecord.interrupt_delivered_at` idempotence; T019 goes green
- [X] T021 [US2] Wire interrupt delivery through `src/maverick/cli/commands/notify.py` and `deliver.py` (`interrupt` kind → priority `urgent`, title per contracts/ntfy-payload.md); extend `tests/unit/cli/commands/test_notify_json.py` with an interrupt-delivery envelope case

**Checkpoint**: US1 and US2 both pass independently; a mixed ledger produces one batch + one interrupt with no cross-talk

---

## Phase 5: User Story 3 - Idempotent evaluation from cron (Priority: P3)

**Goal**: Arbitrary re-runs and overlapping invocations never double-deliver;
failed deliveries stay due; persisted state fully explains every fire/skip.

**Independent Test**: quickstart.md Scenarios 5–6 — double invocation delivers
once; concurrent invocations produce one evaluation + one benign skip;
unreachable ntfy leaves the batch due and re-delivers after recovery.

### Tests for User Story 3 (write first, observe failing)

- [X] T022 [P] [US3] Write failing idempotence/failure tests: extend `tests/unit/assumptions/schedule/test_state.py` (delivery failure excluded from `state_after` → occurrence stays undecided, partial success persists only succeeded decisions) and `tests/unit/cli/commands/test_notify_json.py` (second run same window → `already-delivered` skip + zero transport calls; held lock with live pid → `ok: true`, `result.skipped: "concurrent-evaluation"`, exit 0 per research R7; stale lock reclaimed and evaluation proceeds; ledger read failure (`AssumptionLedgerError`) → `validation` envelope with zero state-file mutation, per the spec's ledger-unreadable edge case)
- [X] T023 [P] [US3] Write failing end-to-end integration test in `tests/integration/test_notify_flow.py`: simulated multi-day run (mocked `BeadClient.query/show`, `httpx.MockTransport`, injected `now` sequence) — overnight accumulation delivers exactly one 09:00 batch (SC-001), repeated invocations idempotent (SC-003), every fire/skip reconstructible from `state.json` alone (SC-004), every entry accounted for (SC-005)

### Implementation for User Story 3

- [X] T024 [US3] Harden the effects layer in `src/maverick/cli/commands/notify.py`: per-decision write-after-success (failed delivery → decision excluded from saved state, envelope `error.details.failed_deliveries`, exit 1; partial successes recorded), lock acquire/release around the whole evaluate-deliver-save sequence with benign-skip result on contention; T022 + T023 go green

**Checkpoint**: Command is cron-safe; all three stories pass independently

---

## Phase 6: User Story 4 - Age-based escalation and explicit expiry (Priority: P4)

**Goal**: Aged medium/high entries escalate past batching rules; high
re-notifies on the backoff ladder; opted-in aged low entries auto-waive with
recorded rationale; nothing leaves tracking without a persisted outcome.

**Independent Test**: quickstart-style simulation — a lone medium entry below
min-batch-size delivers once its age exceeds `max_entry_age_hours`; an
unanswered high entry re-notifies at 4/8/16/24h spacing; with auto-waive
enabled, an aged low entry is waived with the configured rationale visible in
`maverick review --list`.

### Tests for User Story 4 (write first, observe failing)

- [X] T025 [P] [US4] Write failing escalation tests in `tests/unit/assumptions/schedule/test_evaluate_escalation.py`: medium past `max_entry_age_hours` → `ESCALATION` decision bypassing min-batch-size (US4 scenario 1), medium escalates exactly once (FR-007), high past max age → `RENOTIFY` decisions at backoff-ladder spacing with `renotify_count`/`next_renotify_at` advancing and last rung repeating, low never escalates to delivery (clarification Q2), escalation respects `high_overrides_quiet` gating during quiet hours
- [X] T026 [P] [US4] Write failing auto-waive tests: extend `tests/unit/assumptions/schedule/test_evaluate_escalation.py` (policy absent/disabled → never an `AutoWaiveDecision`; enabled + aged low → decision with full rationale text) and `tests/unit/cli/commands/test_notify_json.py` (real run calls `ledger.waive` with `waived_by="maverick-scheduler"`, records `terminal: {kind: "auto-waived"}` in state; `--dry-run` reports would-waive with zero bd calls)

### Implementation for User Story 4

- [X] T027 [US4] Implement escalation + backoff in `src/maverick/assumptions/schedule/evaluate.py`: max-age escalation for medium/high, backoff-ladder re-notification for high (`renotify_backoff_hours`, last value repeating), quiet-hours gating; T025 goes green
- [X] T028 [US4] Implement auto-waive effects in `src/maverick/cli/commands/notify.py`: execute `AutoWaiveDecision`s via `assumptions.ledger.waive(client, bead_id=..., reason="auto-waived by schedule policy after {h}h: {rationale}", waived_by="maverick-scheduler")` (research R10), record `TerminalOutcome` in state, skip entirely in dry-run; extend `deliver.py` with `escalation`/`renotify` payload kinds (priority `urgent`); T026 goes green

**Checkpoint**: All four stories independently functional; full FR coverage

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T029 [P] Update `CLAUDE.md`: add `notify` to the shared-commands table and a `### notify` subsection (severity tiers, config blocks, state location, JSON verbs, benign-lock divergence from reconcile), mirroring the existing per-command sections
- [X] T030 [P] Pin serializer contract against regressions: confirm `entry_to_dict`'s new `created_at` field flows into `review --list --json` and the land report without regression (`tests/unit/cli/commands/test_review_listing.py`, `tests/unit/assumptions/test_land_report.py` — extend, don't fork)
- [X] T031 Run quickstart.md Scenarios 1–6 against a live ntfy topic in a scratch repo; fix any drift between contracts and behavior
- [X] T032 Run `make format-fix && make ci` (the pre-push gate — `make lint` alone misses `ruff format --check`) and resolve anything red

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on T001 — BLOCKS all user stories
- **US1 (Phase 3)**: depends on Phase 2 — delivers the MVP
- **US2 (Phase 4)**: depends on Phase 2; shares `evaluate.py`/`notify.py` with US1, so runs after US1 in a serial fly (file-scope overlap, not logical dependency)
- **US3 (Phase 5)**: depends on US1 (exercises its delivery path); T024 touches `notify.py`
- **US4 (Phase 6)**: depends on US1 (escalation reuses batch delivery machinery); touches `evaluate.py`/`notify.py`/`deliver.py`
- **Polish (Phase 7)**: depends on US1–US4

### Within Each User Story

- Test tasks first; observe them fail; then implementation (red-green-refactor)
- `models.py` → `evaluate.py`/`state.py`/`deliver.py` → `notify.py` → registration

### Parallel Opportunities

- Phase 2: T002 ∥ T005 ∥ T008 (three disjoint test files); after T004+T006: T007 ∥ T009
- Phase 3: T010 ∥ T011 ∥ T012 ∥ T013 (four disjoint test files), then T014 ∥ T015 (disjoint modules), then T016 → T017 → T018
- Phases 4–6 are internally small; their test tasks ([P]) parallelize against nothing else in-phase because implementations share `evaluate.py`/`notify.py`
- Phase 7: T029 ∥ T030

---

## Parallel Example: User Story 1

```bash
# Launch all US1 test authoring together (four disjoint files):
Task: "T010 window-evaluation tests in tests/unit/assumptions/schedule/test_evaluate_windows.py"
Task: "T011 severity-tier tests in tests/unit/assumptions/schedule/test_evaluate_severity.py"
Task: "T012 deliverer tests in tests/unit/assumptions/schedule/test_deliver.py"
Task: "T013 CLI tests in tests/unit/cli/test_notify_command.py + tests/unit/cli/commands/test_notify_json.py"

# Then implementation in two parallel tracks:
Task: "T014 evaluate.py window batching"
Task: "T015 deliver.py NtfyDeliverer"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 → Phase 2 (foundation blocks everything)
2. Phase 3 (US1) → **STOP and VALIDATE**: quickstart Scenarios 1–3 with a real
   ntfy topic
3. This alone retires the feature's core promise: no more polling for
   medium-severity questions

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → batched windows work (MVP — deployable to cron immediately)
3. US2 → high-severity interrupts
4. US3 → cron-hardening (idempotence + concurrency + failure semantics proven
   end-to-end)
5. US4 → escalation, backoff, auto-waive
6. Polish → docs, contract pinning, `make ci`

Each story lands green and independently testable; `bead(<id>)` commits per
task or logical group.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- Every test task must fail before its implementation task starts (Principle V)
- No new external dependencies: httpx, tenacity, Pydantic, atomicwrites are all
  already declared (research R5)
- `evaluate()` stays pure — any temptation to read disk/network inside it is a
  design violation (plan.md Constitution Check, Principle III)
- Zero model calls anywhere in this feature (Principle XIII)
