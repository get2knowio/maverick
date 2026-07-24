# Data Model: Assumption Ledger

**Feature**: 049-assumption-ledger | **Date**: 2026-07-23
**Sources**: spec.md Key Entities, research.md R1–R3, R5

## Entity: Assumption Ledger Entry (a bead)

One ledger entry = one bd bead. No sidecar store (research R1).

### Bead-level shape

| Bead field | Value |
|------------|-------|
| `bead_type` | `TASK` |
| `category` | `REVIEW` |
| `priority` | high → `1`, medium → `2`, low → `3` |
| `assignee` | `"human"` |
| `parent_id` | owning epic's bead ID |
| `labels` | `["assumption", "assumption-review", "needs-human-review"]` |
| `title` | `Assumption: {question truncated to 150 chars}` |
| `description` | fixed markdown: `## Question`, `## Adopted Answer`, `## Alternatives Considered` (bulleted), `## Context` (source bead id + title) |

The two legacy labels keep the agent-side skip filter
(`library/actions/beads.py:301`) and `brief --human` working unchanged; the
new `assumption` label is the ledger discriminator (legacy escalation beads
have the old labels but not `assumption`).

### State keys (bd `set-state`, all values strings)

| Key | Required | Values / format | Set when |
|-----|----------|-----------------|----------|
| `assumption_severity` | yes | `low` \| `medium` \| `high` | creation |
| `assumption_severity_defaulted` | no | `true` | creation, only if severity was missing/invalid in the payload (FR-011) |
| `assumption_status` | yes | `open` \| `answered` \| `waived` | creation (`open`); resolution |
| `assumption_owner_spec` | yes | spec identifier (see below) | creation |
| `assumption_change_ids` | no | comma-joined jj change IDs, append-only | commit stamping; absent = unstamped (FR-012) |
| `assumption_answer` | no | answer text | on answer |
| `assumption_waived_by` | no | git user name | on waive |
| `assumption_waived_at` | no | ISO-8601 UTC timestamp | on waive |
| `assumption_waive_reason` | no | stated reason (required input) | on waive |
| `source_bead` | yes | spawning bead ID | creation (mirrors edge for `brief --human` compat) |

### Owning-spec derivation (clarification #1, research R3)

Resolved at creation from the parent epic's state, first match wins:

1. `speckit_feature` (speckit epics) — e.g. `049-assumption-ledger`
2. `flight_plan_name` (refuel_maverick epics)
3. fallback: the epic bead ID itself

### Validation rules

- Severity outside `{low, medium, high}` (or absent) → coerced to `medium` +
  `assumption_severity_defaulted=true`; never rejected (FR-011).
- Waive requires a non-empty reason; answer requires non-empty answer text.
- `assumption_change_ids` is append-only; stamping never overwrites existing
  IDs (multi-commit assumptions accumulate).
- Question dedup key: `casefold(collapse_ws(question))` scoped to open
  `assumption` children of the same epic (FR-014).

## Entity: Discovered-from Edge

| Aspect | Value |
|--------|-------|
| Representation | `bd dep add <assumption_bead_id> <source_bead_id> --type discovered-from` |
| Direction | assumption → discovered-from → spawning work bead (same as existing follow-up edges, `fly_beads/_commit.py:257-268`) |
| Typed API | `DependencyType.DISCOVERED_FROM` (new enum member) via `BeadClient.add_dependency` |
| Cardinality | ≥1 per entry; dedup appends extra edges to an existing entry instead of creating duplicates |
| Blocking? | No — provenance only; readiness is unaffected |

## Entity: Blocking Edge (high severity)

| Aspect | Value |
|--------|-------|
| Representation | `bd dep add <next_epic_id> --blocked-by <assumption_bead_id> --type blocks` |
| Created | at recording (if next epic exists) OR at refuel `_chain_epic` (if entry precedes the next epic) — research R8 |
| Released | automatically when the entry bead is closed (answer or waive) |
| High on last spec | no next epic → edge never created → medium behavior (spec US2-S5) |

## Entity: Severity Policy (behavioral mapping)

| Severity | Ready queue | Land gate | Next-epic edge |
|----------|-------------|-----------|----------------|
| `low` | created then `bd defer` (open, out of queue) | never blocks | never |
| `medium` | open, appears in `bd ready` (human-assigned) | blocks while `assumption_status=open` | never |
| `high` | open, appears in `bd ready` (human-assigned) | blocks while open | `blocks` edge onto next spec's epic |

Legacy escalation beads (no `assumption` label / no severity state) are
treated as medium by the land gate at read time, without mutation (FR-013).

## State transitions

```
                    create (record_assumptions)
                              │
                              ▼
                     status=open, bead open
                    ┌─────────┴──────────┐
        low: bd defer                medium/high: in bd ready
                    └─────────┬──────────┘
              ┌───────────────┼────────────────┐
              ▼                                ▼
   answer (maverick review)          waive (maverick review)
   status=answered                   status=waived (+who/when/why)
   bead closed                       bead closed
              └───────────────┬────────────────┘
                              ▼
              blocks edges released by bd (close)
              land gate no longer counts entry
```

Stamping (`assumption_change_ids`) is orthogonal to status: it happens at each
successful commit of the source bead's work and an entry may be resolved
before, after, or without ever being stamped (unstamped = run ended before
commit, FR-012 / US1-S4).

## Payload models (maverick.payloads)

```
AssumptionPayload (frozen, extra="allow")
├── question: str            (min_length 1)
├── adopted_answer: str      (min_length 1)
├── alternatives: tuple[str, ...] = ()
└── severity: str = "medium" (validator coerces unknown → "medium",
                              records defaulted flag for the workflow)

SubmitImplementationPayload  += assumptions: tuple[AssumptionPayload, ...] = ()
SubmitReviewPayload          += assumptions: tuple[AssumptionPayload, ...] = ()
SubmitFixResultPayload       += assumptions: tuple[AssumptionPayload, ...] = ()
```

Backward compatible: absent field → empty tuple; registry keys in
`SUPERVISOR_TOOL_PAYLOAD_MODELS` are unchanged.

## Workflow state keys (fly_beads burr graph)

| Key | Type | Purpose |
|-----|------|---------|
| `pending_assumptions` | list of assumption dicts | accumulated from implement/review/fix payloads within the current bead |
| `recorded_assumption_ids` | list of bead IDs | entries created for the current bead; consumed by `commit` for stamping |
| `commit_change_id` | str | jj change ID captured from `jj_commit_bead` (today discarded) |

All three keys are reset in `process_bead_start` so a bead can never stamp or
re-record the previous bead's entries.

Multi-ID stamps arise from dedup: when a later bead re-records an open
question, the merged entry gains that bead's discovered-from edge and its
commit appends a second change ID.

## Aggregation shape (assumptions.report → brief / land gate)

```
PerSpecAssumptionCounts (frozen dataclass)
├── owner_spec: str
├── open: dict[Severity, int]
├── answered: dict[Severity, int]
├── waived: dict[Severity, int]
└── legacy_open: int          (escalation beads without ledger fields)
```

Specs with epics but zero entries render as explicit zero rows (FR-010).
