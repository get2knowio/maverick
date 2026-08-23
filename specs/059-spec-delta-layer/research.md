# Research: Spec Delta Layer

**Feature**: 059-spec-delta-layer
**Date**: 2026-08-23

Findings were measured against this repository's own corpus (54 specs,
1,139 requirement lines, 2,878 task lines) and verified against the tree at
`fc1f81b`. Two of the spec's original assumptions were falsified here and the
spec was revised before planning; those are R2 and R3.

---

## R1 — The requirement-block grammar

**Question**: can a requirement block be parsed and re-rendered deterministically,
and what does a "block" actually contain in practice?

**Findings** (measured across all 54 `specs/*/spec.md`):

- 1,139 requirement lines, **all** matching `^- \*\*FR-\d{3}[a-z]?\*\*: ` — column
  zero, `- `, bold id, colon, space. Zero exceptions, zero `*` bullets, zero
  indented definitions.
- Ids are unique within each spec, complete (no gaps), always three-digit padded.
  **34 carry a letter suffix** (`FR-019c`) across 13 specs.
- `### Functional Requirements` is present in **54/54** files. The `## Requirements`
  heading is *not* uniform — 52 use `*(mandatory)*`, one uses `_(mandatory)_`,
  one has no suffix.
- Inside the section: **104** `####` sub-headings across 20 specs, **371**
  indent-2 continuation lines across 6 specs, **23** indent-2 sub-bullets across
  3 specs (007, 027, 034), **29** bold pseudo-headings. Zero code fences, zero
  tables. Indent depth is only ever 0 or 2.
- Spec 027 blank-separates *every* requirement, and blank-separates its
  sub-bullets from their parent.

**Decision**: anchor the parser on `^### Functional Requirements\s*$`, terminate
a block at the next requirement line or the next `##`/`###` heading. A `####`
heading is an in-block grouping marker; a blank line is **not** a terminator.

**Rationale**: both `####` and blank lines occur inside blocks that are correct
today. Treating either as a terminator silently truncates real requirements —
10 sub-bullets in 027 alone, and every bold-pseudo-heading group in 010 and 016.

**Alternatives considered**:

| Option | Verdict |
| --- | --- |
| Anchor on `## Requirements` | **Rejected** — three heading variants; two specs would miss entirely |
| Terminate on blank line | **Rejected** — silently truncates 027, 010, 016 |
| Terminate on `####` | **Rejected** — 104 legitimate in-block groupings across 20 specs |
| Regex-replace the single line, no block model | **Rejected** — cannot express MODIFIED for the 371 multi-line requirements |

**Consequence**: SC-010 requires parse-then-render to reproduce every existing
`spec.md` byte-identically. That test is the design's own falsification
mechanism — if the block model is wrong, it fails on the corpus rather than in
production.

---

## R2 — Requirement-to-task coverage is not derivable

**Question**: the original spec assumed "tasks reference the requirements they
implement". Do they?

**Findings**: **184 of 2,878 task lines cite a requirement id — 6.4%.** 24 of 54
feature directories cite none at all. Only three specs are meaningfully traced:
015 (26/43), 057 (53/116), 020 (27/102). Most non-zero files are 1–3 citations
across 90–120 tasks. Spec 048 — the feature that *built* the ingestion layer —
is 2/31. Where citations exist they are freeform prose in three shapes:
`(FR-006)` trailing (110), `per FR-008` inline (54), bare token (rest). One file
(004) uses a per-section `**Maps to**: FR-011, ...` footer, found nowhere else.

There is also no requirement handling anywhere in `src/maverick/speckit/` —
`parse_spec_md` returns only `title`, `success_criteria`, `story_scenarios`.

**Decision**: the layer never derives requirement→task coverage. Requirement
operations govern `spec.md`; task entries — stated explicitly by the delta's
author — govern `tasks.md` and thence beads.

**Rationale**: a design resting on that mapping would work on three specs and
fail silently on the other 51. The contrast is instructive: user stories *do*
have a first-class structural marker (`[USn]` is in the task-line grammar,
stored on `SpeckitTask.story_id`, joined at bead-build time). Requirements have
no equivalent, and inventing `[FR-nnn]` would help only tasks written after it
landed.

**Alternatives considered**:

| Option | Verdict |
| --- | --- |
| Parse FR ids out of task descriptions | **Rejected** — 6.4% coverage, three inconsistent formats |
| Introduce an `[FR-nnn]` task marker | **Rejected for this feature** — does nothing for the existing corpus; worth proposing separately |
| Ask a model to infer coverage | **Rejected** — Guardrail 8, and it would be inference presented as fact |

---

## R3 — Requirements carry no acceptance criteria

**Question**: OpenSpec's best idea is a guard refusing a MODIFIED block that
drops scenarios. Can it be implemented here?

**Findings**: **247** occurrences of `**Acceptance Scenarios**:` across 54 specs
— a single uniform literal. **247 of 247** sit under a `### User Story N`
heading inside `## User Scenarios & Testing`. **Zero** appear inside
`## Requirements`. The upstream `spec-template.md` defines them only under user
stories; the `### Functional Requirements` block is bare bullets. Requirements
and user stories are not cross-referenced anywhere, so "which scenarios belong
to FR-007" cannot be derived either.

**Decision**: replace it with a **content-loss guard** over the requirement
block — reject on a dropped sub-bullet, or on the after-block falling below a
fixed fraction of the before-block's normalized length.

**Rationale**: the failure mode being prevented is unchanged (an author working
from an older copy silently deletes content). Only the thing being compared
changes, from a structure the corpus lacks to one it has.

**Alternatives considered**:

| Option | Verdict |
| --- | --- |
| Guard user-story scenarios instead | **Rejected** — no mechanical link from a requirement to its scenarios |
| Sub-bullet loss only | **Rejected** — 23 sub-bullets across 1,139 requirements; the single-line majority stays unguarded |
| Require intent for any reduction | **Rejected** — fires on ordinary tightening until the marker is added reflexively, which is a guard that has stopped guarding |

---

## R4 — The shrink fraction

**Decision**: `SHRINK_FLOOR = 0.6` — reject when the after-block's normalized
length is below 60% of the before-block's. A fixed contract constant, not
configurable (FR-005d).

**Rationale**: an ordinary tightening edit removes a redundant clause, typically
5–20% of a requirement. Losing 40%+ in one edit is a different act. The number
is a judgment call, and the spec pins **both** sides so it stays honest: SC-008
proves it catches the loss case, SC-008a proves it does *not* fire on a
one-clause tightening. If the constant is wrong, SC-008a fails.

Non-configurable because a tunable guard is one an author turns down the first
time it is inconvenient — which is exactly when it is working. The escape is the
per-entry intent marker (FR-005e), which is auditable in the archive; a config
key would not be.

**Alternatives considered**: a configurable threshold (rejected, above); an
absolute character floor instead of a ratio (rejected — a 40-char requirement
and a 400-char one need different sensitivity, which is what a ratio is).

---

## R5 — The delta document grammar

**Decision**: markdown, one file per delta, per the clarify session. Sections
keyed `## <OP> <FR-id>` with `### Before` / `### After` subsections holding
verbatim blocks; one `## RENAMED` section carrying `- FROM:` / `- TO:` pairs;
one `## TASKS` section carrying `- ADDED:` / `- WITHDRAWN:` lines. Full grammar
in `contracts/delta-document-format.md`.

**Rationale**: before/after as labelled subsections rather than a diff is
OpenSpec's rule and it is right — a diff is ambiguous about whitespace and
cannot be validated against the current spec without reconstructing the target
first. Whole-block replacement makes validation a string comparison.

**Alternatives considered**: unified diff (rejected — ambiguous, and a stale diff
applies cleanly against the wrong baseline); YAML (rejected in clarify —
requirement text becomes quoted multi-line scalars that review badly).

---

## R6 — Where withdrawal plugs into refuel

**Findings**: `SpeckitRefuelWorkflow._run` has 11 steps
(`workflows/refuel_speckit/workflow.py:73-410`). Step 3 is
`_find_existing_epic` (`:182`), which returns
`(existing_epic_id, existing_task_map)` where the map is `T### → bd id`, built
by walking `client.children(epic_id)` and reading each child's
`speckit_task_id` state key (`:456-463`). Step 4 builds the ingestion plan.

**Nothing in the Spec Kit path closes a bead today.** The only bead-closing call
sites in `src/` are `library/actions/beads.py:411`, `assumptions/ledger.py:834`
and `:876`, and `cli/commands/review/legacy.py`.

**Decision**: withdrawal detection goes between step 3 and step 4 — the only
point holding both `existing_task_map` and the freshly parsed feature. Withdrawn
tasks are exactly `set(existing_task_map) - {every parsed task_id}`, needing no
extra `bd` queries. It surfaces as a new `IngestionPlan` field beside
`skipped_existing` so `--dry-run` previews it for free
(dry-run rendering is at `workflow.py:298-319`).

`_adopt_remediation_beads` (`workflow.py:536-602`) is the template for the
closing step: per-bead isolation with `except Exception → logger.warning`, and
its own `emit_step_started`/`emit_step_completed` bracketing.

**Closing API**: `BeadClient.close(bead_id, reason="") -> ClosedBead`
(`beads/client.py:302-345`) — calls `assert_checkout` first (Guardrail 0
satisfied). The swallowing wrapper is
`library.actions.beads.mark_bead_complete`.

---

## R7 — The bead ↔ task join, and a latent hazard

**Findings**: the durable join is bd state keys written at `build.py:341-349`:
`speckit_task_id`, `speckit_phase`, `speckit_parallel`, plus `speckit_feature`
on the epic. `BeadDefinition.task_ids` exists in Python but **`create_bead`
never sends it to `bd`** (`client.py:127-201`), so it is lost on write. The
title carries `T007: ...` but that is a fallback, not the contract.

**Hazard**: `set_state` issues **one `bd set-state` call per key and is
explicitly non-atomic** (`client.py:490-517`). A process death between
`create_bead` and `set_state` leaves a bead with no `speckit_task_id` — invisible
to withdrawal detection, and duplicated by the next delta run.

**Decision**: FR-020 requires reporting any bead under the epic carrying no task
identity rather than closing or ignoring it. This feature does not fix the
non-atomicity — that is a pre-existing ingestion defect with its own blast
radius — but it must not pretend the case cannot arise.

**Alternatives considered**: close unstamped beads (rejected — cannot know what
they are); ignore them silently (rejected — this is exactly the silent-drift
class the feature exists to end).

---

## R8 — Atomic multi-file rewrite

**Question**: FR-009 requires apply to be atomic across `spec.md`, `tasks.md`,
and the archive move. `utils/atomic.py` gives per-file atomicity, not
cross-file.

**Decision**: read both files, compute both new contents fully **in memory**,
validate, and only then write — `atomic_write_text` each, archive move last. On
any failure before the first write, nothing has changed. The window where one
file is written and the other is not is reduced to the gap between two atomic
writes, and is closed by a pre-write backup restored on failure.

**Rationale**: a true multi-file transaction would need either a staging
directory swap or a jj operation restore. The jj route is available
(`reconcile/workflow.py` captures `jj_snapshot_operation` restore points) but
would make `delta apply` a commit-graph operation, which it is not — the command
writes working-copy files and nothing else. The in-memory-then-write shape is
what `refuel_speckit` already does for its own artifact writes.

**Alternatives considered**: jj operation restore (rejected — turns a file edit
into a VCS operation); write-then-verify-then-rollback (rejected — rollback is
itself a write that can fail, at which point the state is worse than either).

---

## R9 — CLI shape

**Decision**: `maverick delta validate|apply|list`, registered as one lazy entry
in `main.py`'s `_LAZY_COMMANDS`, following `notify.py`'s structure exactly —
`@click.group` with subcommands, `cwd = Path.cwd().resolve()` at each command
body, config from `ctx.obj` with `load_config()` fallback, thin dispatch to
`_run_*_json` / `_run_*_human`, `json_error_handler(verb)` vs
`cli_error_handler()`, and `emit_json` + `SystemExit` on every JSON terminal
path.

Verbs: `delta.validate`, `delta.apply`, `delta.dry-run`, `delta.list`.

**Error kinds** — no new `ErrorKind` value:

| Condition | Kind |
| --- | --- |
| Malformed delta; content-loss guard; stale before-block; `--ack` naming a non-impact | `validation` |
| Named delta or feature not found | `not-found` |
| Delta already applied | `already-resolved` |
| Unacknowledged impacts | `confirmation-required` |
| `bd` unavailable during impact detection | `bd-unavailable` |

`confirmation-required` already exists and means precisely this. Reusing it
keeps the refusal machine-branchable without widening the taxonomy.

**Not added** to `commands_needing_git_gh` or `commands_needing_config` — the
command needs neither `gh` nor a mandatory `maverick.yaml`, and makes zero model
calls.

---

## R10 — Archive ordering

**Decision**: an applied delta moves to `deltas/archive/` keeping its filename,
and gains an application record appended to the document itself. Ordering is by
a numeric prefix in the filename, assigned at authoring time.

**Rationale**: FR-023 requires pending-versus-applied to be a matter of location
alone, never a status marker inside the file that can disagree with reality — so
the move *is* the state transition. Ordering by filename prefix rather than
mtime survives a `git clone`, which mtime does not.

---

## R11 — Spec Kit version range

**Finding**: `speckit/detect.py:28` pins
`SUPPORTED_SPECKIT_RANGE = ">=0.14,<0.17"`. Upstream is 1.0.1.

**Decision**: out of scope for this feature, recorded so it is not lost. Deltas
live in a directory `_has_speckit_shape` does not inspect
(`detect.py:128-129` checks only for `spec.md` + `tasks.md`), so the delta layer
cannot break feature resolution either way. The upgrade is its own change.
