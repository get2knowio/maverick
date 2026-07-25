# Research: Assumption Review Console

**Feature**: 053-assumption-review-console | **Date**: 2026-07-25

All decisions below resolve the unknowns in plan.md's Technical Context. No
NEEDS CLARIFICATION markers remain.

## R1: JSON output mode mechanics (`--json` flag + stdout purity)

**Decision**: Add a `--json` boolean flag to `maverick review`, `maverick
reconcile`, and `maverick land`. `maverick brief` keeps its existing
`--format json` (it already satisfies FR-003 for the briefing surface); no
change to its selector, but its payload gains nothing new in this feature.
When `--json` is set:

- Exactly one JSON document is written to stdout, at process end, via a new
  `emit_json(document)` helper in `maverick/cli/output.py` (serialises with
  `json.dumps`, writes through a dedicated non-markup, non-wrapping Rich
  Console on stdout — same transport idea as `brief`'s
  `console.print_json`, but guaranteed single-document and unstyled).
- All Rich rendering that normally goes to stdout (tables, panels, progress
  from `render_workflow_events`) is either suppressed or redirected to
  stderr. Commands branch early on `json_mode` and skip their human
  renderers; workflow progress events in JSON mode are rendered to
  `err_console` (satisfies the clarified stream-discipline contract).
- Interactive affordances are disabled: any code path that would call
  `click.prompt` / `click.confirm` / `console.input` in JSON mode instead
  returns a structured `confirmation-required` or `validation` error.

**Rationale**: The clarified spec requires stdout to carry only the
structured document. A per-command flag (rather than a global `--output`
option) matches how the four commands are lazily registered in `main.py`
(no group change needed) and matches the user's explicit request ("add a
--json output mode"). `cli/output.py` already owns formatting helpers and
exports an unused `format_json` — extending it is the DRY move.

**Alternatives considered**: (a) Global `--json` on the `maverick` group —
rejected: group-level failures print before subcommand parsing, and only 4
commands need it; (b) reusing `--format text|json` everywhere — rejected:
`brief` is the only precedent and duplicating a two-value enum on three
more commands adds surface without benefit; the spec names `--json`.

## R2: Where each verb lives (mapping spec verbs → CLI surface)

**Decision**:

| Spec verb | CLI surface | New or existing |
|---|---|---|
| List queue (full provenance, filters) | `maverick review --list [--status ...] [--spec ...] [--severity ...] --json` | New `--list` mode on existing `review` |
| Answer entry | `maverick review <id> --answer <text> --json` | Existing + `--json` |
| Waive entry | `maverick review <id> --waive <reason> --json` | Existing + `--json` |
| Bulk-waive by severity | `maverick review --spec <name> --waive <reason> [--severity ...] --json` | Existing + `--json` |
| Reconcile status (detection preview) | `maverick reconcile --dry-run --json` | Existing + `--json` |
| Run reconcile | `maverick reconcile --json` | Existing + `--json` |
| Land status (frontier + report, no curation) | `maverick land --status --json` | New `--status` mode on existing `land` |
| Land | `maverick land --yes --json` | Existing + `--json` |

**Rationale**: FR-003 forbids parallel commands where an existing command
covers the action. Listing has no existing surface; `review` owns the
entry lifecycle, so `--list` is a mode of `review`, not a new command.
Land status must not run curation (it's a read-only query the skill polls
after reconcile), so it's a `--status` mode of `land` that stops after the
gate evaluation + report build/persist — reusing `_check_assumption_gate`
and `_render_and_persist_land_report` exactly as the full command does.

**Alternatives considered**: `maverick brief --assumptions` for listing —
rejected: brief is a bead-status surface; entry provenance and resolution
belong to review's domain and the skill treats list/answer/waive as one
lifecycle. A standalone `maverick assumptions` group — rejected as a
parallel command family (violates FR-003).

## R3: Response envelope and stable error kinds

**Decision**: Every JSON document shares one envelope (documented in
`contracts/error-envelope.md`):

```json
{"schema_version": 1, "verb": "review.list", "ok": true, "result": { ... }}
{"schema_version": 1, "verb": "land.run", "ok": false,
 "error": {"kind": "frontier-blocked", "message": "...", "details": { ... }}}
```

- `verb` is a stable dotted identifier (`review.list`, `review.answer`,
  `review.waive`, `review.bulk-waive`, `reconcile.run`,
  `reconcile.dry-run`, `land.status`, `land.run`).
- `ok: true` means the verb executed and produced its result; outcome
  semantics (e.g., reconcile escalations) live in `result` and drive the
  exit code per verb contract. `ok: false` means the verb refused or
  failed; `error.kind` is a stable registry value.
- Error kinds registry (initial): `validation`, `not-found`,
  `already-resolved`, `bd-unavailable`, `dirty-working-copy`,
  `concurrent-run`, `locked`, `frontier-blocked`, `confirmation-required`,
  `curation-failed`, `vcs`, `internal`. Additive evolution only.
- Implemented as a frozen dataclass `JsonEnvelope` + `ErrorKind` StrEnum in
  a new `maverick/cli/json_output.py`, plus a `json_error_handler()`
  context manager — the JSON-mode sibling of `cli_error_handler()` that
  maps the `MaverickError` hierarchy (and `BeadClient` availability
  failures, `JjClient` errors, lock/concurrency `WorkflowError`s) onto
  error kinds, emits the error envelope on stdout, and exits non-zero.

**Rationale**: The spec requires stable machine-distinguishable kinds and
success-or-structured-error on every invocation (FR-005). A single
envelope means the skill parses one shape. Mapping in one context manager
keeps land/review (which today hand-roll errors) from growing per-command
error plumbing — the constitutionally mandated single canonical wrapper.

**Alternatives considered**: Per-verb bespoke top-levels (brief's current
style) — rejected: the skill would need N parsers and error output would
stay unstructured. HTTP-style numeric codes — rejected: string kinds are
self-documenting and match `LandVerification`-style StrEnum precedent.

## R4: Entry serialization — one canonical row shape

**Decision**: Extract `land_report._entry_to_dict` into a public
`entry_to_dict(entry: AssumptionReportEntry) -> dict` in
`maverick/assumptions/serialize.py` (re-exported from `land_report` for
backward compatibility), extended with `owner_spec`, `bucket`, and
`blocks_landing` fields needed by the flat listing. `review --list` and
the land report both use it, so the skill sees the same row shape in both
documents (the land report nests rows under spec sections; the listing is
flat with `owner_spec` inline).

**Rationale**: FR-001's provenance fields are exactly what
`AssumptionReportEntry` + `_entry_to_dict` already carry (question,
adopted answer, alternatives, severity, owning spec, affected change ids,
status/bucket, waiver, reconcile state). Duplicating the projection would
guarantee drift between the listing and the land report (Principle VII).
The land-report schema contract is additive-only, so adding fields to the
row is legal; `owner_spec` inside the row is redundant with the section
key in land-report context but harmless and consistent.

**Alternatives considered**: A new Pydantic model per row — rejected:
`AssumptionReportEntry` is already the typed contract; the dict projection
is a serializer, not a second model.

## R5: Listing filters and defaults

**Decision**: `review --list` supports `--status open|answered|waived`
(repeatable; default `open` — the sweep population), `--spec <owner>`
(repeatable), `--severity low|medium|high` (repeatable). Backed by
`ledger.report_entries()` (one bd sweep) with client-side filtering; the
result document carries `entries` (sorted: owner_spec, severity high→low,
then stable ledger order — the clarified sweep order, so the skill can
present in document order without re-sorting) and `counts` per
status/severity.

**Rationale**: Matches clarification Q1 (full ledger reachable, open is
the default selection) and Q3 (ordering is decided once, server-side, so
the skill and any future client agree). `report_entries` is the single
canonical reader; filters are cheap in-process.

## R6: JSON-mode behavior of existing interactive paths in `review`

**Decision**: In `--json` mode, `review <id>` requires exactly one of
`--answer`/`--waive` (ledger entries) or `--approve`/`--reject`/`--defer`
(legacy escalation beads); absence → `validation` error envelope. The
"not flagged for review — Review anyway?" confirm becomes a `validation`
error. Answering an entry whose status is no longer `open` returns
`already-resolved` with the entry's current state in `error.details`
(spec edge case: concurrent resolution) — implemented as a pre-check in
the command reading the entry's current status before calling
`ledger.answer`/`ledger.waive`. `waived_by` resolution (git user name)
is unchanged.

**Rationale**: FR-004 (no prompts) plus the concurrent-sweep edge case.
`ledger.answer`/`waive` don't themselves guard against re-resolution, so
the CLI boundary adds the check — boundary validation per Principle IX.

## R7: Reconcile verb in JSON mode

**Decision**: `reconcile --json` runs the existing flow (preconditions →
`execute_python_workflow` with progress rendered to stderr → `load_run_state`)
and emits `result` = `ReconcileReport.to_dict()` (already the workflow's
`final_output`), augmented with the per-answer terminal detail from
`ReconcileRunState` when present. Exit codes preserve the existing
contract: 0 when nothing to reconcile or all outcomes `reconciled`; 1
otherwise (with `ok: true` — the verb ran; the outcomes say what
happened). Precondition failures (dirty working copy, concurrent fly run,
held lock, bd unavailable) map to `dirty-working-copy` /
`concurrent-run` / `locked` / `bd-unavailable` error envelopes.
`reconcile --dry-run --json` emits the dry-run prediction report
(statuses `reconciled`/`skipped` only) and always exits 0, per the
existing 051 contract. Both are synchronous (clarification Q4) — no job
protocol.

**Rationale**: `ReconcileReport.to_dict()` already exists and is
deterministic; wrapping it beats inventing a second report. Keeping exit
semantics identical between human and JSON modes means the skill and a
human reading the table can never disagree about what happened.

## R8: Land verbs in JSON mode

**Decision**:

- `land --status --json`: evaluate gate (`_check_assumption_gate`) →
  build + persist land report → emit `result` containing the
  `LandReport.to_dict()` document plus `frontier_clear: bool` and
  `blocking` summary (open vs pending-reconcile entry ids). **Always
  exits 0 unless a real error occurs** — blocked is an answer, not a
  failure, for a status query. Skips curation, consolidation, and the
  human-review manifest display entirely.
- `land --json` (apply): the frontier gate refusing to land emits
  `ok: false`, `kind: frontier-blocked`, with the full report dict in
  `error.details.report`, exit 1 — same gate, no bypass (FR-007).
  When the gate passes, curation proceeds; the agent-curation approval
  prompt is a `confirmation-required` error unless `--yes` was given
  (consent is gathered by the caller — the skill asks the human first,
  per the spec's Assumptions). Success emits the report dict plus
  curation summary (`mode`, `curation` outcome, `verification`
  classification, mode-specific `hint`), exit 0. `--dry-run --json`
  mirrors the human dry-run (runs the full preview, defers non-zero exit
  to the end when blocked).

**Rationale**: `LandReport.to_dict()` is already a versioned public
contract (052) with the terminal renderer deliberately derived from it —
the JSON verb is the third consumer of the same dict, so nothing can
drift. Distinguishing status (query, exit 0) from apply (action, exit 1
on refusal) matches the spec's acceptance scenarios for both.

## R9: Skill authoring, packaging, and installation

**Decision**: The skill is a new packaged asset:

- Source of truth: `src/maverick/skills/review_console/SKILL.md`
  (Markdown with YAML frontmatter: `name: maverick-review`,
  `description` with trigger text, `user-invocable: true`), included in
  the wheel via a `pyproject.toml` include entry (same mechanism as
  `agents/system_prompts/*.md`).
- Installed by `maverick init` into
  `<project>/.claude/skills/maverick-review/SKILL.md` as a new idempotent
  init step (always overwrite — the file is Maverick-owned and versioned
  with the package; a header comment says so). Non-fatal on failure
  (advisory, like the Spec Kit offer). `maverick uninstall` removes it.
- The skill body instructs Claude Code to: run `maverick review --list
  --json`; sweep entries in document order, one `AskUserQuestion` per
  entry (adopted answer marked Recommended, alternatives as options,
  free-form via the built-in Other, waive/skip reachable — when
  alternatives exceed the option surface, a follow-up question presents
  the remainder; nothing is silently dropped); apply each decision
  immediately via `review <id> --answer/--waive --json`; offer spec-level
  bulk-waive when multiple open low-severity entries share a spec; after
  the sweep run `maverick reconcile --json` once (skip when no answers
  were given); report the frontier via `maverick land --status --json`;
  offer landing and on explicit confirmation run `maverick land --yes
  --json`; surface every `ok: false` envelope and every
  `needs_interactive_review` outcome verbatim, never retrying.

**Rationale**: Exploration confirmed Maverick ships no skills today and
`uninstall.py` documents that the old `~/.claude/skills/maverick-*`
mechanism is gone — project-local `.claude/skills/` is the current Claude
Code convention (this repo's own skills use it) and travels with the
repo. `maverick init` is the established idempotent provisioning surface.
Always-overwrite keeps the skill in lockstep with the CLI contract it
drives (the skill and the verbs version together in the wheel).

**Alternatives considered**: user-level `~/.claude/skills` install —
rejected (explicitly retired by uninstall.py's history; per-project
versioning is safer when different projects run different maverick
versions). Publishing as a Claude Code plugin — rejected: out of scope,
no marketplace mechanism in this repo.

## R10: Module layout to respect Principle XI (review.py growth)

**Decision**: `cli/commands/review.py` is ~490 LOC; adding `--list`,
JSON envelopes, and the already-resolved guard would push it past the
soft limit. Split it into a package as part of this feature:
`cli/commands/review/{__init__.py (command + dispatch), listing.py,
entry_actions.py, legacy.py}` re-exporting `review` from `__init__` so
`main.py`'s lazy registration string keeps working. `land.py` (~680 LOC)
gains only the `--status` branch and JSON emission (+~80 LOC): extract
the status/report path into `cli/commands/land_status.py` helper module
consumed by the command rather than splitting the whole command in this
slice.

**Rationale**: Constitution XI refactor trigger; backwards-compatible
package split is the constitution's preferred pattern.
