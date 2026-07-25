# Research: Conditional Landing on the Assumption Frontier

All unknowns from Technical Context resolved. Decisions below are grounded in
a code-level survey of `cli/commands/land.py`, `assumptions/`,
`workflows/fly_beads/` (Burr graph), and `workflows/reconcile/`.

## R1 — Frontier computation: new reader beside `open_blocking_entries`, not a mutation of it

**Decision**: Add `ledger.report_entries(client) -> tuple[AssumptionReportEntry, ...]`
— a repo-wide reader over **all** assumption beads (any status, via the
existing `_ALL_STATUS_TASK_FILTER` pattern) plus legacy `assumption-review`
beads, materializing per-entry answer/waiver/reconcile state keys that
`AssumptionRecord` deliberately omits. The land frontier is then derived in
`assumptions/land_report.py`: open entries of **any** severity (incl. legacy,
treated as medium) + answered entries matching 051's pending-reconciliation
predicate. `open_blocking_entries()` (medium/high only) is left untouched.

**Rationale**: `open_blocking_entries` also has non-land semantics
(brief/refuel expectations, 049 tests assert medium/high-only); changing its
contract would ripple. The report needs closed beads (answered/waived) and
state keys (`KEY_ANSWER`, `KEY_WAIVED_*`, `KEY_RECONCILE_*`) that today are
only read ad-hoc — one canonical reader removes that duplication (Principle
VII). Land's gate becomes "frontier from the same data the report shows",
guaranteeing the report and the gate can never disagree.

**Alternatives considered**: (a) widen `open_blocking_entries` to all
severities — rejected: breaks 049 semantics for other callers; (b) compute
frontier in the CLI from raw bd queries — rejected: ledger logic must live in
`assumptions/` (package charter), and the CLI stays a renderer.

## R2 — Gate scope: repo-wide, grouped per spec in the report

**Decision**: The land gate evaluates the frontier repo-wide (as the existing
gate does), and the report groups entries by `owner_spec`.

**Rationale**: `maverick land` curates and lands the whole branch, not one
spec — a per-spec gate would let spec A land while carrying spec B's
assumption-laden commits in the same push. The existing gate is already
repo-wide; the spec's per-spec framing is satisfied by per-spec grouping in
the report and per-spec `owner_spec` attribution on every row.

**Alternatives considered**: spec-scoped gating via `--spec` filter —
rejected: single-branch landing makes partial gating unsound; revisit only if
land ever grows per-spec landing.

## R3 — Verification classification rules

**Decision**: A `LandVerification` StrEnum in `assumptions/models.py`:

- `BLOCKED` — frontier non-empty: any open entry (any severity, incl. open
  legacy) **or** any answered entry pending reconciliation (non-terminal).
- `CONDITIONALLY_VERIFIED` — frontier empty and ≥1 entry has
  `status=waived`.
- `VERIFIED` — frontier empty and every entry is answered (or no entries).

Classification is computed by a pure function
`classify(entries) -> LandVerification` in `land_report.py`, unit-testable
without bd. Entries in terminal reconcile states (`skipped`,
`needs-interactive-review`) do **not** block but are annotated on their report
rows (FR-006).

**Rationale**: Direct transcription of the clarified spec (Clarifications
2026-07-24: strict gate incl. low; pending-reconciliation blocks). A StrEnum
mirrors the existing `Severity` idiom and serializes cleanly into JSON.

## R4 — Pending-reconciliation check reuses 051's detection verbatim

**Decision**: Land calls `answered_unreconciled_entries(client)` (the exact
051 predicate) to find pending-reconciliation entries; no new predicate.
Frontier rows produced from it carry `pending_reconcile=True` and land's
blocked table hints `maverick reconcile` for those rows (vs `maverick review`
for open rows).

**Rationale**: One notion of "pending changed answer" repo-wide (per
clarification Q5); two predicates would drift. The function already excludes
terminal states and applies the idempotence guard — exactly FR-006's contract.

## R5 — Report persistence & PR body: artifact files; no PR automation added

**Decision**: `land_report.py` persists two artifacts per land evaluation
under `.maverick/runs/<land-run-id>/` (land mints an 8-hex run id, mirroring
reconcile's CLI): `land-report.json` (typed `LandReport.to_dict()`, atomic
write via `utils/atomic.py`) and `land-report.md` (PR-ready markdown:
classification banner + resolved/waived/open tables with provenance).
`--dry-run` persists too (it is an evaluation; SC-002 audit trail). Land's
mode hints are updated to reference the markdown, e.g. the `--finalize` hint
becomes `gh pr create ... --body-file .maverick/runs/<id>/land-report.md`.
Persistence failure degrades to `[yellow]Warning:[/yellow]` and never blocks.

**Rationale**: Land today creates **no** PRs — all three modes only print
next-step hints (`land.py:197-215`, by design per its docstring). FR-008's
"included in the PR description when landing creates a PR" is therefore
satisfied by making the PR body *available and referenced in the hint*; if
land later automates PRs, `library/actions/github.create_github_pr(generated_body=...)`
is already wired to accept the markdown. Inventing PR automation here would
expand scope beyond the spec (which conditions on "when landing creates a
PR") and contradict land's deliberate push-is-manual slice.

**Alternatives considered**: (a) add real `gh pr create` to `--finalize` —
rejected as scope expansion; (b) persist under `.maverick/plans/` — rejected:
run-scoped artifacts belong with run metadata (`runway/run_metadata.py`
precedent).

## R6 — Mid-flight trigger: new Burr action on the bead boundary

**Decision**: Splice a new action `reconcile_answers` into the fly graph on
the `record_outcome → select_next_bead` and `abandon_bead → select_next_bead`
edges, plus one final invocation on the loop-exit path (before
`aggregate_review`) so answers arriving during the last bead are processed
before the run completes (FR-009 guarantee). The action is a thin wrapper; the
logic lives in `fly_beads/mid_flight.py`:

1. If graceful stop was requested or `config.reconcile.mid_flight` is false →
   skip (answers stay detectable; FR-014).
2. Run detection: `answered_unreconciled_entries(client)` — cheap bd query.
   Empty → no-op.
3. Non-empty → invoke `ReconcileWorkflow` **in-process** with inputs
   `{run_id: <fresh 8-hex>, cwd, dry_run: False, active_fly_run_id: <fly's run id>}`,
   forwarding its `ProgressEvent`s into fly's event queue.
4. Any `WorkflowError`/`MaverickError` → structured warning event; drain
   continues (FR-013). Never re-raise into the Burr loop.

**Rationale**: The bead boundary is the only safe window — `commit()` ends
with a fresh empty `@` child, satisfying reconcile's clean-working-copy guard;
mid-bead the tree is dirty and history rebase would corrupt in-progress work
(FR-011). The boundary is already explicit in the graph
(`burr_graph.py:242`), and a dedicated action keeps `select_next_bead`
single-responsibility and gives the pass its own progress grouping. Detection
re-runs at *every* boundary, which natively implements FR-014's
queue-for-next-pass semantics. Watch-mode idle cycles pass through
`select_next_bead` too, so a run that is idling in `--watch` still processes
arrivals.

**Alternatives considered**: (a) background task concurrent with bead
implementation — rejected: violates FR-011 (concurrent jj history mutation
under a live working copy) and reconcile's clean-tree guard; (b) detection
inside `select_next_bead` — rejected: muddies an already four-way-terminating
action and loses distinct progress reporting; (c) reuse one long-lived
`ReconcileSquadron` across passes — rejected for now: squadron open cost is
paid only when detection is non-empty (rare), and per-pass lifecycle reuses
`ReconcileWorkflow` unchanged (Principle VII beats micro-optimization).

## R7 — Reconcile's concurrent-fly guard: exclude the calling run

**Decision**: `ReconcileWorkflow` gains an optional input
`active_fly_run_id: str | None = None`. `_find_flying_run(cwd)` gains an
`exclude_run_id` parameter; the guard raises only if a *different* run has
`status == "flying"`. The standalone CLI passes nothing (behavior unchanged).
All other guards stay: clean-working-copy (holds at bead boundaries),
interrupted-run recovery, and the reconcile lockfile (also protects against a
concurrent standalone reconcile — FR-015's cross-processor exclusion).

**Rationale**: The guard's intent is "don't rewrite history under someone
else's live fly run"; the calling run is, by construction, parked at a safe
boundary awaiting this pass. Excluding the caller preserves the guard's
protection against *other* concurrent runs. Idempotence across processors is
already carried by ledger reconcile-state markings (051 SC-008) plus the
lockfile.

**Alternatives considered**: (a) temporarily flip fly's run-metadata status —
rejected: lies to every other observer (brief, tooling) and is crash-fragile;
(b) extract a guard-free core function from `ReconcileWorkflow` — rejected:
larger refactor, two entry points to keep aligned; the input flag is one
narrow, explicit seam.

## R8 — Bulk waive: ledger helper + review command selector flags

**Decision**: Add `ledger.bulk_waive(client, *, owner_spec, severities,
reason, waived_by) -> tuple[AssumptionRecord, ...]` that lists matching
**open** entries (assumption-labeled, filtered by `owner_spec` and severity
set, default `{low}`; legacy entries included when `medium` is selected) and
loops the existing `waive()` per entry — full who/when/why metadata recorded
on each (FR-016). `maverick review` makes `BEAD_ID` optional and adds
`--spec <name>` + `--severity <low|medium|high>` (repeatable, default low),
valid only with `--waive <reason>`: `maverick review --spec 052-conditional-landing
--waive "accepted for MVP"`. Supplying both `BEAD_ID` and `--spec` is an
error; a bulk waive matching zero entries reports "nothing to waive" and
exits zero. Per-entry failures are collected: the command waives what it can,
lists failures, and exits non-zero if any entry failed.

**Rationale**: Looping `waive()` keeps a single write path (no second
waiver-stamping implementation to drift); the strict low-severity gate
(Clarification Q1) makes this UX necessary (Clarification Q4). Severity
default `low` bounds the blast radius of an accidental sweep; the spec-scope
requirement forces deliberate targeting.

**Alternatives considered**: variadic `BEAD_ID...` — rejected: humans don't
know the ids in bulk situations, the spec/severity selector matches the
actual task ("clear the low noise for this spec"); interactive multi-select —
rejected per clarification.

## R9 — Config: single kill-switch, no new tuning knobs

**Decision**: One new field: `ReconcileConfig.mid_flight: bool = True`
(pydantic, `maverick.yaml` key `reconcile.mid_flight`). No cadence/interval
knobs — cadence is structurally "every bead boundary".

**Rationale**: A first release of in-run history rewriting warrants an
operational kill-switch (Hardening by Default); anything more is YAGNI. Round
budgets already exist on `ReconcileConfig` and are inherited unchanged.

## R10 — Downstream readiness release (FR-012) needs no new mechanism

**Decision**: No new code for readiness propagation. `ledger.answer()`/
`waive()` close the entry bead, which releases bd `blocks` edges;
`select_next_bead` re-queries `bd_select` every cycle, so newly-ready beads
are picked up at the next boundary automatically.

**Rationale**: Verified against the drain loop: readiness is re-evaluated per
cycle (`actions.py:148-218`). One caveat documented in quickstart: with
`fly --epic <id>`, beads outside that epic are out of scope by definition —
cross-spec unblocking within one run manifests on global runs (no `--epic`)
or `--watch` runs; the epic-scoped run still benefits at land time.

## R11 — Stale-doc corrections in passing

**Decision**: While touching `fly_beads/`, fix stale xoscar-era references
(`FlySupervisor` mentions in `graceful_stop.py` / `actions.py` docstrings)
and note in CLAUDE.md that fly's drain loop is Burr-driven (the "fly" section
already describes behavior correctly; only the architecture note needs a
line). Scoped strictly to comments/docs encountered in edited files
(Principle XII), not a documentation sweep.
