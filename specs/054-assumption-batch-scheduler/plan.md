# Implementation Plan: Assumption Batch Scheduler

**Branch**: `054-assumption-batch-scheduler` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/054-assumption-batch-scheduler/spec.md`

## Summary

Add `maverick notify` — an idempotent, daemonless CLI command (cron/systemd-timer
friendly) that reads the assumption ledger via the existing `BeadClient`,
evaluates it against a new `assumptions.schedule` config block with a **pure,
clock-injected evaluation function**, and delivers severity-tiered ntfy push
notifications: high = interrupt at next evaluation, medium = batched at review
windows, low = never proactive. Delivery state persists under
`.maverick/notify/` (atomic writes + pid lockfile, mirroring the reconcile
state module) so re-runs never double-deliver and every fire/skip is auditable.
Zero model calls, zero agents, zero Burr — this is a deterministic library +
CLI feature (Principle XIII).

## Technical Context

**Language/Version**: Python 3.11+ (`from __future__ import annotations`)

**Primary Dependencies**: Click + Rich (CLI), Pydantic v2 (config + state
models), httpx (ntfy HTTP publish — already a declared dependency, first use),
tenacity `AsyncRetrying` (delivery retries), structlog via
`maverick.logging.get_logger`, `maverick.utils.atomic` (atomic state writes),
`maverick.beads.client.BeadClient` (ledger reads, auto-waive writes)

**Storage**: JSON file state at `<cwd>/.maverick/notify/state.json` (frozen
Pydantic models, `schema_version: 1`, atomic writes) + pid-stamped advisory
lockfile `<cwd>/.maverick/notify/lock`; the ledger itself remains bd beads

**Testing**: pytest + pytest-asyncio (`asyncio_mode = "auto"`), CliRunner for
CLI, `unittest.mock.patch` on `BeadClient.query/show` (house pattern — no bd
subprocess in unit tests); evaluation tested as a pure function of
`(entries, config, state, now)`

**Target Platform**: Linux/macOS developer machines (local timezone semantics
via `datetime.now().astimezone()`; DST handled by wall-clock window occurrences)

**Project Type**: Single project — library modules under
`src/maverick/assumptions/schedule/` + one CLI command

**Performance Goals**: One evaluation completes in seconds at realistic ledger
scale (tens of entries; `report_entries` costs 1 `bd query` + 2 subprocesses
per candidate bead — acceptable at cron frequency, noted in research R12)

**Constraints**: No resident process; idempotent under repeated and concurrent
invocation; delivery failure must never be recorded as delivered; notifications
carry summaries only, never entry contents; evaluation must be reconstructible
from ledger + config + persisted state alone

**Scale/Scope**: Single repository per invocation; ledgers of ~10–200 entries;
2–4 review windows/day; state file bounded by FR-023 retention (90 days past
terminal state)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Async-First | PASS | All I/O paths async: `BeadClient`, httpx `AsyncClient`, state writes via `asyncio.to_thread(atomic_write_*)`. No `subprocess.run` anywhere in async paths. |
| II. Separation of Concerns | PASS | No agents, no Burr — a deterministic command in the same class as `review --list`/`land --status`. Pure evaluation (decisions) is separated from effects (delivery, state writes, auto-waive). |
| III. Dependency Injection | PASS | `evaluate()` receives entries, schedule config, prior state, and an injected `now: datetime` — the codebase's first clock seam, chosen over module-level `datetime.now()` precisely for this principle. CLI boundary resolves `cwd`, config, and clock once. |
| IV. Fail Gracefully | PASS | ntfy failure → clear error, batch stays due, state untouched (FR-012). Ledger unreadable → abort with diagnostic, no state mutation. Lock contention → benign skip (research R7). |
| V. Test-First | PASS | Pure evaluation function is designed for exhaustive unit testing (windows, quiet hours, DST, min-batch, escalation, backoff) without I/O. |
| VI. Type Safety & Typed Contracts | PASS | Frozen dataclasses for decisions, frozen Pydantic models for config + persisted state; no `dict[str, Any]` blobs (Guardrail 3). |
| VII. Simplicity | PASS | No new abstractions beyond one evaluation module, one state module, one deliverer, one command. |
| VIII. Determinism over Inference (XIII) | PASS | Zero model calls. Every decision is a pure function of parseable inputs. |
| IX. Hardening by Default | PASS | httpx explicit timeout (10s), tenacity retry with exponential backoff, specific exception handling mapped to envelope error kinds. |
| X. Guardrail 0/7 (single-repo, explicit cwd) | PASS | State under `<cwd>/.maverick/notify/`; `cwd` resolved at CLI boundary and threaded explicitly; no `Path.cwd()` below the CLI. |
| X. Guardrail 5 (one canonical wrapper) | PASS | ntfy is a new external system; `assumptions/schedule/deliver.py` becomes its single canonical wrapper. No other module may talk to ntfy. |
| Appendix C (CLI output, JSON verbs) | PASS | Rich console only; `--json` emits the shared `JsonEnvelope` (verbs `notify.run` / `notify.dry-run`); narration to `err_console` in JSON mode. |

**Post-Phase-1 re-check**: PASS — design artifacts introduce no violations; the
one deliberate divergence (lock contention exits 0 for notify while reconcile
exits non-zero) is a contract choice for cron ergonomics, documented in
research R7 and the CLI contract, not a constitution violation.

## Project Structure

### Documentation (this feature)

```text
specs/054-assumption-batch-scheduler/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli-notify-json.md        # Command surface + JSON envelope contract
│   ├── config-schema.md          # assumptions.schedule + notifications config
│   ├── delivery-state-schema.md  # Persisted state, retention, locking
│   └── ntfy-payload.md           # Notification content contract
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/maverick/
├── assumptions/
│   ├── models.py                # MODIFIED: created_at on AssumptionRecord/AssumptionReportEntry
│   ├── serialize.py             # MODIFIED: created_at + age surfaced in entry_to_dict
│   └── schedule/                # NEW package — all scheduler logic
│       ├── __init__.py          # public surface re-exports
│       ├── models.py            # frozen dataclasses: WindowOccurrence, DeliveryDecision,
│       │                        #   SkipReason, EvaluationOutcome, BatchSummary
│       ├── evaluate.py          # pure evaluation: (entries, config, state, now) → outcome
│       ├── state.py             # DeliveryState Pydantic models, load/save/prune,
│       │                        #   pid lockfile (mirrors workflows/reconcile/state.py)
│       └── deliver.py           # NtfyDeliverer: httpx + tenacity, the one ntfy wrapper
├── beads/
│   └── models.py                # MODIFIED: created_at: str | None on BeadDetails
├── cli/
│   ├── commands/
│   │   └── notify.py            # NEW: maverick notify [--dry-run] [--json]
│   └── json_output.py           # MODIFIED: ErrorKind.DELIVERY_FAILED (additive)
├── config.py                    # MODIFIED: AssumptionScheduleConfig, QuietHoursConfig,
│                                #   AutoWaivePolicyConfig, AssumptionsConfig; wired as
│                                #   MaverickConfig.assumptions (NotificationConfig reused as-is)
└── main.py                      # MODIFIED: "notify" entry in _LAZY_COMMANDS

tests/
├── unit/
│   ├── assumptions/schedule/
│   │   ├── test_evaluate_windows.py      # windows, min-batch, rolling, DST, midnight quiet hours
│   │   ├── test_evaluate_severity.py     # interrupt/batch/silent tiers, legacy→medium
│   │   ├── test_evaluate_escalation.py   # max-age escalation, high backoff, medium once
│   │   ├── test_state.py                 # persistence, idempotence keys, retention pruning, lock
│   │   └── test_deliver.py               # payload shape, retry, failure-not-recorded
│   ├── cli/commands/test_notify_json.py  # envelope, verbs, error kinds, exit codes
│   ├── cli/test_notify_command.py        # human-mode output, unconfigured no-op
│   └── config/test_assumptions_schedule_config.py
└── integration/test_notify_flow.py       # end-to-end with mocked BeadClient + ntfy transport
```

**Structure Decision**: Scheduler logic lives under
`src/maverick/assumptions/schedule/` because all ledger logic already lives in
`src/maverick/assumptions/` and the scheduler is a pure consumer of it; the CLI
command is a thin module registered lazily in `main.py` per house convention.
No workflow package is created — there is no state machine, no agents, and no
squadron (Principle XIII: a model call on a path where parsing would do is a
design smell; here even parsing is trivial).

## Complexity Tracking

No constitution violations — table intentionally empty.
