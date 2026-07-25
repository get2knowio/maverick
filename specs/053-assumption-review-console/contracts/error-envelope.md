# Contract: JSON Envelope & Error Kinds

**Feature**: 053-assumption-review-console
**Stability**: Public contract. Additive evolution only — existing keys,
verb ids, and error kinds are never renamed or removed; new ones may be
added. `schema_version` bumps only for breaking changes (none planned).

## Scope

Applies to every document emitted by a Maverick command invoked with
`--json`. One JSON document per invocation, written to **stdout only**;
all diagnostics, warnings, and progress go to **stderr**. No document is
ever partially written: emission happens once, at terminal state.

`maverick brief --format json` predates this contract and keeps its
existing payload shapes (not enveloped); it is unchanged by this feature.

## Envelope

Success:

```json
{
  "schema_version": 1,
  "verb": "<verb-id>",
  "ok": true,
  "result": { }
}
```

Failure:

```json
{
  "schema_version": 1,
  "verb": "<verb-id>",
  "ok": false,
  "error": {
    "kind": "<error-kind>",
    "message": "<human-readable, free to change>",
    "details": { }
  }
}
```

Rules:

- Exactly one of `result` / `error` is present (the other key is omitted,
  never `null`).
- `ok: true` means the verb executed and produced its result. Outcome
  semantics inside `result` (e.g. reconcile escalations) drive the exit
  code per the verb's own contract — `ok` and exit code are related but
  not identical.
- `ok: false` means the verb refused or failed. Exit code is non-zero.
- `error.kind` is a stable identifier — safe to branch on.
- `error.message` is human-readable prose — never branch on it.
- `error.details` is verb-specific structured context (documented per
  verb); absent keys mean "no additional context".

## Verb registry

| Verb id | Command |
|---|---|
| `review.list` | `maverick review --list --json` |
| `review.answer` | `maverick review <id> --answer <text> --json` |
| `review.waive` | `maverick review <id> --waive <reason> --json` |
| `review.bulk-waive` | `maverick review --spec <name> --waive <reason> --json` |
| `reconcile.run` | `maverick reconcile --json` |
| `reconcile.dry-run` | `maverick reconcile --dry-run --json` |
| `land.status` | `maverick land --status --json` |
| `land.run` | `maverick land --json` (incl. `--dry-run`, `--eject`, `--finalize` variants) |

## Error kinds registry

| Kind | Meaning | Typical `details` |
|---|---|---|
| `validation` | Invalid flag combination or input (e.g. `--json` review with no decision flag; empty answer text; interactive-only path reached) | `{"hint": "..."}` |
| `not-found` | Referenced entry/bead/spec does not exist | `{"bead_id": "..."}` or `{"owner_spec": "..."}` |
| `already-resolved` | Entry is no longer open (concurrent resolution) | `{"entry": {row}}` — current entry row |
| `bd-unavailable` | bd CLI missing, not initialized, or ledger query failed. **Every** verb reports this for a failed `verify_available()` / bd-readiness precondition — never `validation` (the shared handler cannot classify a check that never raises, so each verb translates it itself, and they must agree). | — |
| `dirty-working-copy` | Working copy not clean where cleanliness is required | — |
| `concurrent-run` | Another workflow run (e.g. a flying run) blocks this verb | `{"run_id": "..."}` when known |
| `locked` | Run lockfile held | `{"lock_path": "..."}` when known |
| `frontier-blocked` | Land refused by the assumption-frontier gate | `{"report": {LandReport}}` — full report document |
| `confirmation-required` | Action needs explicit consent not supplied (e.g. `land --json` agent-curation without `--yes`) | `{"hint": "pass --yes"}` |
| `curation-failed` | Curation gather/plan/execution failed during land | `{"stage": "gather\|plan\|execute", "error": "..."}` |
| `vcs` | jj/git operation failed outside the kinds above | `{"operation": "..."}` when known |
| `internal` | Unexpected error (the bare-`Exception` boundary) | — |

## Exit codes

Unchanged `ExitCode` enum: `0` success, `1` failure, `2` partial (unused
by these verbs), `130` interrupted. Per-verb exit semantics are defined in
each verb's contract; every `ok: false` document accompanies a non-zero
exit. `KeyboardInterrupt` exits 130 and emits **no** JSON document (the
sole exception to one-document-per-invocation).

## Stream discipline

- stdout: the JSON document, nothing else. Implementations MUST route
  Rich rendering, workflow progress (`render_workflow_events`), and
  warnings to stderr in `--json` mode.
- Group-level failures that occur before subcommand option parsing
  (missing `git`/`gh`, bad `maverick.yaml`) predate flag handling and are
  NOT enveloped; automation should treat non-JSON stdout+non-zero exit as
  an environment error. This is a documented limitation, not a bug.

## Mapping (implementation note, non-normative)

`maverick.cli.json_output.json_error_handler()` is the single boundary
that converts the `MaverickError` hierarchy and known precondition
failures into envelopes. Commands MUST NOT hand-roll error JSON.
