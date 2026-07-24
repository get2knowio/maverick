# Research: Assumption Ledger

**Feature**: 049-assumption-ledger | **Date**: 2026-07-23

All Technical Context unknowns resolved. Each decision below records what was
chosen, why, and what was rejected. File references are to the current tree.

## R1. Ledger storage: extended beads, not a sidecar store

**Decision**: Each ledger entry IS a bead. Structured fields live in bead
*state* (`bd set-state` key/value, read back via `bd show --json` →
`BeadDetails.state`), long-form text (question, adopted answer, alternatives)
lives in the bead description in a fixed markdown shape, and classification
lives in labels.

**Rationale**: The spec mandates surfacing via `bd ready` and discovered-from
edges — both are bead-native. Bead state is already the established metadata
channel (`speckit_feature` on epics at `src/maverick/speckit/build.py:371`,
`source_bead`/`escalation_type` on today's escalation beads at
`src/maverick/workflows/fly_beads/actions.py:1130-1137`). A sidecar file would
need its own sync with bd and would break `bd ready`/dependency semantics.

**Alternatives considered**: (a) JSON ledger file under `.maverick/` — rejected:
duplicates bd's queue/dependency machinery and drifts from bead status;
(b) new bd entity type — rejected: bd has no such extension point; beads with
labels + state are sufficient.

## R2. State-key and label schema

**Decision**: New `assumption` label marks ledger entries (alongside the
existing `assumption-review` + `needs-human-review` labels so the
agent-side skip filter at `src/maverick/library/actions/beads.py:301` and
`brief --human` filter at `src/maverick/cli/commands/brief.py:371` keep
working unchanged). State keys (all `dict[str, str]`, bd's constraint):

| Key | Values | Purpose |
|-----|--------|---------|
| `assumption_severity` | `low` \| `medium` \| `high` | severity policy input |
| `assumption_severity_defaulted` | `true` (absent otherwise) | FR-011 visibility |
| `assumption_status` | `open` \| `answered` \| `waived` | resolution lifecycle |
| `assumption_owner_spec` | e.g. `049-assumption-ledger` | owning spec (see R3) |
| `assumption_change_ids` | comma-joined jj change IDs | change stamp (see R5) |
| `assumption_answer` | short answer text | set on answer |
| `assumption_waived_by` / `assumption_waived_at` / `assumption_waive_reason` | strings | audited waiver |
| `source_bead` | bead ID | kept for `brief --human` compatibility |

**Rationale**: bd state is string→string; comma-joining change IDs is the
established pattern for multi-valued state. Reusing existing labels keeps
FR-013 (legacy compatibility) nearly free.

**Alternatives considered**: severity as a label (`severity:high`) — rejected:
state is the read-back channel every consumer already uses (`details.state`),
and labels are currently coarse routing tags only.

## R3. Owning-spec attribution (clarification #1)

**Decision**: At recording time, the workflow reads the owning epic's state:
`speckit_feature` (speckit epics, set at
`src/maverick/workflows/refuel_speckit/workflow.py:314`) with fallback to
`flight_plan_name` (refuel_maverick epics, set at
`src/maverick/workflows/refuel_maverick/workflow.py:613-615`), and copies the
value into `assumption_owner_spec` on the entry. If neither key exists
(legacy/adopted epics), the epic bead ID is used as the owner identifier so
aggregation still functions.

**Rationale**: Deterministic, agent-free (per clarification), and both epic
families are cleanly partitioned by which key they populate. Copying onto the
entry makes per-spec aggregation a single pass over assumption beads without
per-entry epic lookups.

**Alternatives considered**: resolving owner at read time via `parent_id` →
epic state — rejected: every report/gate query would need N extra `bd show`
calls; copy-on-write is stable because a bead never changes epics.

## R4. Recording path (clarification #4)

**Decision**: New frozen Pydantic model `AssumptionPayload` (question,
adopted_answer, alternatives tuple, severity) added to `maverick.payloads`;
`SubmitImplementationPayload`, `SubmitReviewPayload`, and
`SubmitFixResultPayload` gain `assumptions: tuple[AssumptionPayload, ...] = ()`.
Fly actions (`implement`, `review`, `fix` paths in
`src/maverick/workflows/fly_beads/actions.py`) accumulate these into a new
`pending_assumptions` state key. A new deterministic burr action
`record_assumptions` (wired before `commit` in
`src/maverick/workflows/fly_beads/burr_graph.py`) creates the ledger beads:
one bead per deduped assumption, `assignee="human"`, parent = owning epic,
plus a `discovered-from` edge to the source bead.

**Rationale**: Matches the batch-at-step-end clarification and Guardrail 3
(agents judge, workflows own side effects). The base payload class is
`extra="allow"` so older agent prompts that omit the field are unaffected
(defaults to empty tuple). Placing `record_assumptions` before `commit` lets
the same bead's commit stamp the entries moments later (R5).

**Alternatives considered**: recording inside the `commit` action — rejected:
commit already has one job and its failure semantics (non-fatal stamping)
differ from entry creation; a dedicated action keeps both testable.

## R5. Change-ID capture and stamping

**Decision**: Fix the active `commit` action
(`src/maverick/workflows/fly_beads/actions.py:1163-1203`) to capture the
return of `jj_commit_bead` — a dict whose `change_id` is the stable jj change
ID of the finalized change (`src/maverick/library/actions/jj.py:247-288`,
`JjClient.commit` → `JjCommitResult.change_id`) — instead of discarding it.
After a successful commit, the action appends that change ID to
`assumption_change_ids` on every entry recorded for the current bead
(`recorded_assumption_ids`, reset per bead). Multi-ID stamps arise via dedup:
when a later bead re-records an open question, the merged entry is stamped
again by that bead's commit. Stamping failure logs a warning and never fails
the commit (FR-012).

**Rationale**: jj change IDs are the stable identity across rewrites (git SHAs
change under curation in `land`); the return value already exists and is
merely dropped today. Stamping in `commit` is the only place where both the
entry IDs and the change ID are simultaneously known.

**Alternatives considered**: git commit SHA — rejected: `land` curation
rewrites commits, invalidating SHAs; `JjCommitResult` doesn't even expose one.

## R6. Severity policy — low (advisory)

**Decision**: Low-severity entries are created like all others, then
immediately removed from the ready queue via `bd defer <id>` (existing
pattern: `defer_bead` at `src/maverick/library/actions/beads.py:408-426`).
They remain open (countable, answerable if a human seeks them out) but never
appear in `bd ready`, never block land, and never wire epic dependencies.

**Rationale**: "Advisory only" (FR-005) plus "counts include open entries"
(FR-010) means low entries must exist but stay out of every queue and gate.
`bd defer` is exactly that semantic and already has a wrapper.

**Alternatives considered**: creating low entries pre-closed — rejected: they
would count as "resolved" in reports, misrepresenting an unanswered advisory.

## R7. Severity policy — medium (land gate, clarification #3)

**Decision**: A new pre-land assumption gate runs in
`src/maverick/cli/commands/land.py` immediately after the existing
commit-count check / human-review manifest display (land.py:148-151) and
before curation. It queries open beads labeled `assumption` with
`assumption_severity` ∈ {medium, high} and `assumption_status == open`,
grouped by `assumption_owner_spec`. Any hit blocks land with a listing of the
blocking entries (ID, severity, question, owning spec) and exits non-zero.
There is **no bypass flag** — the only paths forward are `maverick review`
answer/waive (R9). Legacy escalation beads without `assumption_severity` are
listed in the existing human-review manifest as today and treated by the gate
as medium (severity-defaulting rule FR-011 applied at read time for legacy
entries, without mutating them).

**Rationale**: land is cwd-scoped with no epic parameter (land.py:130-131), so
"the owning spec's land" concretely means: the gate blocks the cwd-wide land
while any spec that would be swept into it has open medium/high entries — and
identifies them per spec. No-bypass matches the clarification; the waiver is
the audited escape hatch.

**Alternatives considered**: `--force` flag — rejected per clarification #3;
scoping the gate to a single epic — rejected: land has no epic identity and
pushes the whole branch, so a narrower gate would let unanswered assumptions
ride along.

## R8. Severity policy — high (next-epic dependency, clarification #2)

**Decision**: Dependency-only, wired at two hooks so ordering doesn't matter:

1. **Recording time** (`record_assumptions`): if a next chained epic exists —
   discovered as the open epic whose `speckit_feature` NNN prefix is the
   smallest strictly greater than the owning epic's (`next_chained_epic` in
   the ledger API; flight-plan epics without `speckit_feature` never match) —
   add `bd dep add <next_epic> --blocked-by <assumption_bead> --type blocks`.
2. **Refuel time** (`_chain_epic`): when a new speckit epic is created, in
   addition to chaining behind the tail epic, wire `blocks` edges from every
   open high-severity assumption entry owned by earlier specs onto the new
   epic.

Additionally, `_chain_epic`'s "tail" selection is made deterministic by
sorting open epics by their `speckit_feature` NNN prefix (today it relies on
unspecified `bd query` ordering — a latent bug this feature would otherwise
inherit).

**Rationale**: `bd ready` already enforces blocking edges, so work past the
boundary "simply never becomes ready" with zero new pause machinery — exactly
the clarified behavior, and it works identically within one run or across
runs. The dual hook covers both temporal orders (assumption recorded before
vs. after the next spec is refueled). When no next epic ever appears, the
entry degrades to medium behavior (land gate only) — matching the spec's
last-spec rule with no extra code.

**Alternatives considered**: in-run pause state machine — rejected per
clarification #2; blocking the next epic's *tasks* individually — rejected:
blocking the epic bead blocks its subtree in `bd ready --parent` traversal
and needs one edge instead of N. (Verification that a blocked epic suppresses
its children from `bd ready` is a quickstart scenario; if bd treats epic
blocking as non-transitive, the fallback is wiring the same edge to the next
epic's phase-source tasks, computed by the existing `_phase_sources` logic.)

## R9. Answer / waive surface

**Decision**: Extend the existing `maverick review` command
(`src/maverick/cli/commands/review.py`, already "lightweight human review of
assumption beads") with explicit resolution flows: answering records
`assumption_answer`, sets `assumption_status=answered`, and closes the bead;
waiving requires a reason, records `assumption_waived_by` (git user name) /
`assumption_waived_at` (ISO timestamp) / `assumption_waive_reason`, sets
`assumption_status=waived`, and closes the bead. Closing is what releases
`blocks` edges (bd readiness) and removes the entry from `bd ready`.

**Rationale**: `review` is already the human's resolution surface for these
beads; closing-on-resolve makes bd itself release the epic dependency (SC-006,
"no manual dependency surgery"). Status + close state together distinguish
answered/waived/open for reporting.

**Alternatives considered**: a new `maverick assumptions` command — rejected:
duplicates an existing surface; `bd close` directly — insufficient: loses the
audited answer/waiver record.

## R10. Queue surfacing & dedup

**Decision**: Medium/high entries are ordinary open human-assigned beads, so
they appear in `bd ready` natively (bd is the human's queue per the spec) and
in `maverick brief --human` (existing label filter). The agent-side
`select_next_bead` filter already skips them
(`src/maverick/library/actions/beads.py:295-311`) — no change needed.
Dedup (FR-014): `record_assumptions` normalizes the question (casefold,
collapse whitespace) and skips creation when an open `assumption` bead with
the same normalized question already exists under the same owning epic;
instead it appends the new source bead's discovered-from edge to the existing
entry. In-payload duplicates within one step are collapsed the same way.

**Rationale**: Reuses every existing queue mechanism untouched; normalized
question matching under one epic is cheap (children listing already exists)
and matches the spec's "same question within one bead" minimum while also
covering repeat offenders across fix rounds.

**Alternatives considered**: content-hash state key — rejected as premature;
normalized-text comparison over the epic's open assumption children is
sufficient at realistic volumes (tens of entries).

## R11. DependencyType enum gap

**Decision**: Add `DISCOVERED_FROM = "discovered-from"` to `DependencyType`
(`src/maverick/beads/models.py:44-51`) and route all new edge creation through
`BeadClient.add_dependency`. The two raw `bd dep add ... --type
discovered-from` call sites in `fly_beads/_commit.py:257-268,365-370` are
migrated to the typed client as collateral cleanup (Guardrail 5: one canonical
wrapper; Constitution XII: fix what you find).

**Rationale**: The feature needs discovered-from edges programmatically; the
enum is the single missing piece blocking typed usage, flagged during
research as a pre-existing inconsistency.

**Alternatives considered**: keep raw CLI calls — rejected: violates the
one-canonical-wrapper guardrail and duplicates edge-writing logic in a third
place.

## R12. Per-spec reporting in brief

**Decision**: `maverick brief` gains an assumption-counts section: aggregate
all beads labeled `assumption` (plus legacy `assumption-review` beads counted
in a "legacy" bucket) grouped by `assumption_owner_spec`, showing
open/answered/waived × severity counts. Epics present in the store whose spec
has zero entries render as zero rows (FR-010). Shown in the default brief view
as a compact table and in `--human` view in full; `--format json` includes the
raw aggregation.

**Rationale**: brief already queries beads globally and has the human filter
plumbing (`brief.py:98-125,357-407`); a section there matches clarification
#5. Zero rows require enumerating epics, which `query("type=epic")` provides.

**Alternatives considered**: new subcommand — rejected per clarification #5.

## R13. New package layout

**Decision**: New package `src/maverick/assumptions/` — `models.py` (frozen
dataclasses: `AssumptionRecord`, `Severity` StrEnum, state-key constants),
`ledger.py` (async create/stamp/resolve/query operations over `BeadClient`),
`report.py` (per-spec aggregation used by brief and the land gate). Workflow
actions, CLI commands, and refuel hooks import from this package; nothing in
it imports workflow or CLI modules.

**Rationale**: Modularize-early (Constitution XI): the ledger logic is needed
from four consumers (fly, land, review, brief, refuel) and would otherwise be
duplicated or dumped into an already-large `actions.py` (1200+ lines).

**Alternatives considered**: putting ledger ops in `library/actions/beads.py`
— rejected: that module is the generic bead action layer; assumption policy
(severity, waivers, stamping) is a distinct domain with its own vocabulary.
