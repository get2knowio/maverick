# Data Model: Transactional Reconcile of Changed Human Answers

References: [research.md](research.md) decisions R1–R14; existing models in
`src/maverick/assumptions/models.py`, `src/maverick/jj/models.py`.

## 1. Ledger extension (bd state keys — persisted on the entry bead)

Existing keys (unchanged): `assumption_status`, `assumption_answer`,
`assumption_severity`, `assumption_change_ids` (comma-joined, append-only),
`assumption_owner_spec`, `source_bead`, waive keys.

New keys (constants in `assumptions/models.py`):

| Key | Constant | Values / format | Written by |
|---|---|---|---|
| `assumption_reconcile_status` | `KEY_RECONCILE_STATUS` | `reconciled` \| `needs-interactive-review` | `mark_reconciled` / `mark_needs_interactive_review`; **cleared** by `ledger.answer()` on re-answer (FR-017 re-arm) |
| `assumption_reconciled_at` | `KEY_RECONCILED_AT` | UTC ISO-8601 | `mark_reconciled` |
| `assumption_reconciled_answer` | `KEY_RECONCILED_ANSWER` | normalized answer text applied | `mark_reconciled` (idempotence check, SC-008) |
| `assumption_reconcile_change_id` | `KEY_RECONCILE_CHANGE_ID` | jj change id of target after fold | `mark_reconciled` |
| `assumption_reconcile_reason` | `KEY_RECONCILE_REASON` | short failure/skip reason | `mark_needs_interactive_review` |

Status values: `RECONCILE_STATUS_RECONCILED = "reconciled"`,
`RECONCILE_STATUS_NEEDS_REVIEW = "needs-interactive-review"`.

### Entry reconcile lifecycle

```
answered ──detection──▶ pending ──apply──▶ reconciled            (terminal until re-answered)
                          │
                          ├─ failure/rollback ─▶ needs-interactive-review ──human re-answers──▶ answered (re-armed)
                          └─ immutable / unlocatable target ─▶ needs-interactive-review (reason recorded)
```

Waived entries, legacy escalation beads (`assumption-review` without
`assumption` label), and entries whose normalized answer equals the adopted
answer or the previously reconciled answer never enter `pending`.

## 2. Workflow value objects (`workflows/reconcile/models.py` — frozen dataclasses)

### `ChangedAnswer`
| Field | Type | Notes |
|---|---|---|
| `entry_id` | `str` | bd bead id |
| `question` | `str` | parsed from description |
| `adopted_answer` | `str` | parsed from description (old assumption) |
| `human_answer` | `str` | `assumption_answer` state |
| `severity` | `Severity` | existing enum |
| `owner_spec` | `str` | |
| `stamped_change_ids` | `tuple[str, ...]` | raw from state |
| `target_change_id` | `str \| None` | earliest resolvable stamp (R2); `None` → unlocatable |
| `stack_index` | `int` | position in `::@` (0 = earliest); sort key (FR-002) |

Validation: `target_change_id is None` ⇒ terminal `needs-interactive-review`
before any mutation.

### `AnswerOutcome`
| Field | Type | Notes |
|---|---|---|
| `entry_id` | `str` | |
| `status` | `Literal["reconciled","skipped","needs_interactive_review"]` | exactly one terminal status (FR-019) |
| `reason` | `str` | empty for reconciled |
| `stage_reached` | `ReconcileStage` | see state machine below |
| `target_change_id` | `str \| None` | post-fold id when reconciled |
| `escalation_bead_id` | `str \| None` | set on budget exhaustion |
| `gate_passed` | `bool \| None` | `None` if gate never ran |
| `no_change_required` | `bool` | empty-delta edge case |

Status taxonomy (FR-019): `skipped` = no mutation attempted (immutable or
unlocatable target); `needs_interactive_review` = application attempted and
rolled back. **Both** write the `needs-interactive-review` ledger state so the
FR-017 re-arm rule applies uniformly. One status, three per-layer spellings —
each layer uses exactly one:

| Layer | Spelling |
|---|---|
| bd state value (`assumption_reconcile_status`) | `needs-interactive-review` |
| Python `AnswerOutcome.status` literal | `needs_interactive_review` |
| CLI summary table | `needs interactive review` |

### `ReconcileReport`
`run_id: str`, `outcomes: tuple[AnswerOutcome, ...]`,
`dry_run: bool`, `started_at/finished_at: str`. Exit-code rule:
`all(o.status == "reconciled" for o in outcomes)` (or empty) → 0, else 1.

## 3. Run state (`workflows/reconcile/state.py` — Pydantic, persisted)

`ReconcileRunState` → `.maverick/runs/<run-id>/reconcile.json`
(atomic write, spec-chain pattern; `schema_version: 1`).

| Field | Type | Notes |
|---|---|---|
| `run_id` | `str` | `uuid4().hex[:8]` |
| `status` | `"running" \| "completed" \| "failed"` | resumable discovery keys on `running` |
| `updated_at` | `str` | UTC ISO |
| `answers` | `list[AnswerState]` | ordered by `stack_index` |

`AnswerState`: `entry_id`, `target_change_id`, `restore_op_id: str | None`
(jj op id captured at answer start), `stage: ReconcileStage`,
`terminal_status: str | None`, `reason: str`.

### `ReconcileStage` (per-answer state machine)

```
PENDING → SNAPSHOTTED → CORRECTED → CONFLICTS_RESOLVED → SEMANTIC_DONE → GATED → TERMINAL
```

Any stage before TERMINAL, on failure or interruption discovery:
`restore_operation(restore_op_id)` → TERMINAL(`needs_interactive_review`).
Transitions persist to disk before the next jj mutation, so crash recovery
(FR-016) always finds an accurate `restore_op_id` + stage.

## 4. Structured-output payloads (`payloads.py`, registered in `SUPERVISOR_TOOL_PAYLOAD_MODELS`)

### `SubmitCorrectionPayload` (`"submit_correction"`)
| Field | Type | Notes |
|---|---|---|
| `summary` | `str` | what the correction changes |
| `files_touched` | `tuple[str, ...]` | repo-relative |
| `no_change_required` | `bool = False` | paraphrase / already-correct case |

### `SubmitConflictResolutionPayload` (`"submit_conflict_resolution"`)
| Field | Type | Notes |
|---|---|---|
| `resolved_files` | `tuple[str, ...]` | files whose markers were removed |
| `unresolvable` | `tuple[str, ...]` | files the agent could not resolve (triggers early budget accounting) |
| `notes` | `str = ""` | |

### `SubmitSemanticDependentsPayload` (`"submit_semantic_dependents"`)
| Field | Type | Notes |
|---|---|---|
| `findings` | `tuple[SemanticFinding, ...]` | one per analyzed descendant |

`SemanticFinding`: `change_id: str`, `dependent: bool`, `reason: str`,
`fix_instructions: str` (empty when not dependent).

All three subclass `SupervisorInboxPayload`; validation at the structured-output
boundary (existing mechanism). None carry an `assumptions` field — reconcile
agents must not adopt new assumptions; anything unresolvable escalates.

## 5. Config (`config.py`)

`ReconcileConfig(BaseModel)`:
| Field | Type | Default | Meaning |
|---|---|---|---|
| `resolution_rounds` | `int` (ge=1) | `3` | conflict-resolution round budget per answer (clarification Q2) |
| `semantic_rounds` | `int` (ge=1) | `3` | semantic-dependents round budget per answer (clarification Q5) |

Mounted as `reconcile: ReconcileConfig = Field(default_factory=ReconcileConfig)`
on `MaverickConfig`; YAML section `reconcile:`; env
`MAVERICK_RECONCILE__RESOLUTION_ROUNDS` etc. for free.

## 6. Escalation bead (reuses existing shapes)

Created only after rollback completes (R8), via the ledger/bead layer with:
labels `["assumption-review", "needs-human-review"]`, `assignee="human"`,
category REVIEW, description sections `## Question`, `## Old Adopted Answer`,
`## New Human Answer`, `## Remaining Conflicts` (or `## Unresolved Dependents`),
state `source_bead=<entry_id>`, `escalation_type="reconcile_exhaustion"`, and a
`discovered-from` edge to the ledger entry. Deliberately shaped like fly's
`create_human_bead` output so `maverick review` and `brief --human` handle it
unchanged.
