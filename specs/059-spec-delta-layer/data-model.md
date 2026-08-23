# Data Model: Spec Delta Layer

**Feature**: 059-spec-delta-layer
**Date**: 2026-08-23

Frozen Pydantic models, matching `speckit/models.py`'s existing style
(`model_config = ConfigDict(frozen=True)`, field validators for id grammar).
Guardrail 3: no `dict[str, Any]` blobs across any boundary.

---

## Reused unchanged

| Type | Home | Role here |
| --- | --- | --- |
| `SpeckitTask`, `SpeckitPhase` | `speckit/models.py` | The parsed `tasks.md`; task entries resolve against these |
| `SpeckitFeature` | `speckit/models.py` | Feature-dir resolution result |
| `IngestionPlan` | `speckit/build.py` | Gains one field for withdrawals (below) |
| `BeadClient.close()` | `beads/client.py:302` | The only bead mutation this feature performs |

---

## Requirement-block layer (new, in `speckit/requirements.py`)

### `RequirementBlock`

One requirement as it appears in `spec.md`.

| Field | Type | Notes |
| --- | --- | --- |
| `req_id` | `str` | Validated `^FR-\d{3}[a-z]?$`. The suffix form is real — 34 instances (research R1). |
| `header_line` | `str` | The `- **FR-NNN**: ...` line, verbatim |
| `continuation` | `tuple[str, ...]` | Indent-2 prose lines, verbatim |
| `sub_bullets` | `tuple[str, ...]` | Indent-2 `- ` lines, verbatim |
| `trailing_blanks` | `int` | Blank lines before the next block |
| `line_number` | `int` | 1-based, for error messages |

**Invariant — round-trip**: `render(parse(text)) == text` for every
`specs/*/spec.md` in the repository (SC-010). This is why every field stores
lines *verbatim* rather than normalized: normalization is what breaks
round-trips, and a layer that rewrites specs must not reformat the 51 it was not
asked to touch.

`normalized_length` — whitespace-collapsed character count of the whole block,
used only by the content-loss guard. Derived, never stored.

### `RequirementSection`

| Field | Type | Notes |
| --- | --- | --- |
| `heading_line` | `str` | The `### Functional Requirements` line, verbatim |
| `elements` | `tuple[RequirementBlock \| PassthroughLines, ...]` | In file order |
| `start_line` / `end_line` | `int` | Bounds within `spec.md` |

`PassthroughLines` holds anything that is not a requirement block — the 104
`####` grouping headings and 29 bold pseudo-headings (research R1). They are
carried verbatim and re-emitted untouched, which is what makes the round-trip
hold on specs this feature never modifies.

**Ordering**: file order, never sorted. Two specs (015, 050) have requirements
out of numeric order with complete id sets; sorting would silently reorder them.

---

## Delta document layer (new, in `speckit/delta/models.py`)

### `DeltaOperation` (StrEnum)

`ADDED`, `MODIFIED`, `REMOVED`, `RENAMED` — exactly four (FR-001). The value is
the literal section keyword in the document, so it is a contract string.

**Apply order** is fixed by `OPERATION_ORDER = (RENAMED, REMOVED, MODIFIED, ADDED)`
(FR-004a), a module constant — not enum declaration order, which would make
reordering the enum a silent behavior change.

### `RequirementEntry`

| Field | Type | Presence |
| --- | --- | --- |
| `operation` | `DeltaOperation` | always |
| `req_id` | `str` | always (for RENAMED, the *old* id) |
| `new_req_id` | `str \| None` | RENAMED only |
| `before` | `str \| None` | MODIFIED, REMOVED — verbatim block |
| `after` | `str \| None` | MODIFIED, ADDED — verbatim block |
| `shrink_intended` | `bool` | MODIFIED only; the per-entry guard opt-out (FR-005e) |
| `line_number` | `int` | for error messages |

**Invariants**: MODIFIED carries both `before` and `after`; ADDED only `after`;
REMOVED only `before`; RENAMED neither but both ids. A whole block, never a
partial excerpt or a diff (FR-002) — partial content is the field's known
failure mode, silently dropping what it omits.

### `TaskEntry`

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | `Literal["added", "withdrawn"]` | |
| `task_id` | `str` | Validated `^T\d{3,}$` — reuses `speckit/models.py`'s pattern |
| `line` | `str \| None` | The full task line, `added` only |

Stated by the author, **never** derived from a `RequirementEntry` (FR-007a).

### `DeltaDocument`

| Field | Type | Notes |
| --- | --- | --- |
| `path` | `Path` | Where it was read from — decides pending vs. applied |
| `title` | `str` | From the `# Delta: ...` heading |
| `target_feature` | `str` | Resolved through the existing `detect.resolve_feature` |
| `requirement_entries` | `tuple[RequirementEntry, ...]` | file order |
| `task_entries` | `tuple[TaskEntry, ...]` | file order |
| `sequence` | `int` | Numeric filename prefix; archive ordering (research R10) |

`is_applied` ⇔ `path` is under `deltas/archive/`. Location is the state, never a
marker inside the document (FR-023).

`is_empty` ⇔ both entry tuples are empty → rejected at validation (FR-005).
Note a delta with requirement entries and **no** task entries is *not* empty and
applies quietly (FR-007b) — the dominant shape, per research R2.

---

## Impact layer

### `Impact`

A collision between a task entry and existing work.

| Field | Type | Notes |
| --- | --- | --- |
| `task_id` | `str` | |
| `bead_id` | `str` | From `existing_task_map` |
| `bead_status` | `str` | At detection time |
| `reason` | `Literal["in-flight", "closed", "unstamped"]` | |

`blocks` ⇔ `bead_status` is anything other than open-and-unstarted.
`unstamped` is the research R7 hazard: a bead under the epic with no recorded
task identity. It is reported, never closed and never ignored (FR-020).

### `Acknowledgement`

| Field | Type |
| --- | --- |
| `task_id` | `str` |
| `bead_id` | `str` |
| `bead_status` | `str` |
| `acknowledged_at` | `str` (UTC ISO-8601) |

Records the impact's state **at the time it was cleared** — so the archive
answers "what was knowingly overridden", not merely "an override happened"
(FR-015a).

### `ApplicationRecord`

| Field | Type |
| --- | --- |
| `applied_at` | `str` (UTC ISO-8601) |
| `counts` | `Mapping[str, int]` — per operation, all four keys, zeros included |
| `task_counts` | `Mapping[str, int]` — `added` / `withdrawn` |
| `acknowledgements` | `tuple[Acknowledgement, ...]` |
| `shrink_intended_ids` | `tuple[str, ...]` — which reductions were *declared* rather than caught (FR-005e) |

Appended to the delta document as it moves to `deltas/archive/`, so the archive
is readable without any other source (FR-022).

---

## Ingestion layer (modified)

`IngestionPlan` (`speckit/build.py:41-57`) gains:

| Field | Type | Notes |
| --- | --- | --- |
| `withdrawn` | `tuple[WithdrawnTask, ...]` | Ingested tasks absent from the reparsed feature |

`WithdrawnTask`: `task_id`, `bead_id`, `bead_status`, `closable: bool`.

Computed at the one point holding both `existing_task_map` and the parsed
feature (research R6) as `set(existing_task_map) - {parsed task ids}` — no extra
`bd` queries. Placing it on the plan means `refuel --dry-run` previews
withdrawals for free, through the existing dry-run renderer.

---

## Relationships

```
DeltaDocument
├── RequirementEntry*  ──apply──►  RequirementSection ── RequirementBlock*
│                                        (spec.md, round-trip preserved)
├── TaskEntry*         ──apply──►  tasks.md task lines
│                       └─detect─►  Impact*  ──cleared by──  Acknowledgement*
└── ApplicationRecord  ──archive──►  deltas/archive/<file>.md

refuel (separate run)
└── IngestionPlan.withdrawn ──►  BeadClient.close()
```

Nothing here writes a commit, and the only bead mutation is `close()` on an
open, unstarted bead during a later refuel — never during `delta apply`
(FR-011).
