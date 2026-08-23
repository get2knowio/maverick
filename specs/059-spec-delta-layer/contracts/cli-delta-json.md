# Contract: `maverick delta --json`

**Feature**: 059-spec-delta-layer
**Status**: Normative
**Depends on**: `specs/053-assumption-review-console/contracts/error-envelope.md`

Exactly one JSON document on stdout on every path. All progress, warnings, and
diagnostics go to stderr.

---

## Verbs

| Invocation | `verb` |
| --- | --- |
| `delta list --json` | `delta.list` |
| `delta validate <d> --json` | `delta.validate` |
| `delta apply <d> --json` | `delta.apply` |
| `delta apply <d> --dry-run --json` | `delta.dry-run` |

`dry-run` is a separate verb rather than a flag inside the result, matching
`reconcile.dry-run` and `notify.dry-run` — a consumer must be able to tell from
the verb alone whether anything was written.

---

## `delta.apply` — success

```json
{
  "ok": true,
  "verb": "delta.apply",
  "result": {
    "schema_version": 1,
    "delta": "052-conditional-landing/001-tighten-frontier-gate",
    "applied_at": "2026-08-23T09:14:02.113847+00:00",
    "requirements": {
      "added": ["FR-026"],
      "modified": ["FR-014"],
      "removed": ["FR-021"],
      "renamed": [{ "from": "FR-018", "to": "FR-019" }]
    },
    "tasks": { "added": ["T042"], "withdrawn": ["T017"] },
    "acknowledgements": [
      { "task_id": "T017", "bead_id": "mv-0417", "bead_status": "in_progress",
        "acknowledged_at": "2026-08-23T09:14:02.113847+00:00" }
    ],
    "declared_reductions": ["FR-014"],
    "archived_to": "specs/052-conditional-landing/deltas/archive/001-tighten-frontier-gate.md"
  }
}
```

`requirements` always carries all four keys, empty arrays included — a consumer
must never distinguish "nothing was removed" from "the key is missing". Same for
`tasks`.

`declared_reductions` lists entries that carried `[shrink-intended]`, so a
reviewer can see what the content-loss guard was told to ignore.

---

## `delta.apply` — the refusal

Unacknowledged impacts are `ok: false` with kind `confirmation-required`:

```json
{
  "ok": false,
  "verb": "delta.apply",
  "error": {
    "kind": "confirmation-required",
    "message": "2 impacts must be acknowledged before applying",
    "details": {
      "impacts": [
        { "task_id": "T017", "bead_id": "mv-0417", "bead_status": "in_progress",
          "reason": "in-flight" },
        { "task_id": "T019", "bead_id": "mv-0419", "bead_status": "closed",
          "reason": "closed" }
      ],
      "acknowledged": ["T017"],
      "outstanding": ["T019"]
    }
  }
}
```

Exit 1, and **nothing was written**. `outstanding` is what the caller still has
to pass to `--ack`, so a scripted consumer does not have to diff `impacts`
against `acknowledged` itself.

`confirmation-required` is an existing `ErrorKind` and means exactly this. No
new value is introduced (FR-021 of the shared envelope contract).

---

## `delta.dry-run`

Always `ok: true` when the delta is valid — a dry run reports, it does not
refuse. Impacts ride in the **result**, not an error:

```json
{
  "ok": true,
  "verb": "delta.dry-run",
  "result": {
    "schema_version": 1,
    "delta": "052-conditional-landing/001-tighten-frontier-gate",
    "requirements": { "added": ["FR-026"], "modified": ["FR-014"],
                      "removed": ["FR-021"], "renamed": [] },
    "tasks": { "added": ["T042"], "withdrawn": ["T017"] },
    "impacts": [
      { "task_id": "T017", "bead_id": "mv-0417", "bead_status": "in_progress",
        "reason": "in-flight" }
    ],
    "would_block": true,
    "wrote_nothing": true
  }
}
```

`would_block` lets a consumer branch on "will this apply cleanly" without
provoking the refusal. `wrote_nothing` is always `true` here and exists so the
dry-run and apply documents are distinguishable on a field, not only on the verb.

---

## `delta.validate`

```json
{
  "ok": false,
  "verb": "delta.validate",
  "error": {
    "kind": "validation",
    "message": "3 problems in 052-conditional-landing/002-bad",
    "details": {
      "problems": [
        { "line": 14, "entry": "MODIFIED FR-014", "code": "content-loss",
          "message": "after-block is 41% of the before-block (floor 60%)" },
        { "line": 31, "entry": "MODIFIED FR-021", "code": "stale-before",
          "message": "before-block does not match the current spec" },
        { "line": 48, "entry": "WITHDRAWN T099", "code": "unknown-task",
          "message": "no such task in tasks.md" }
      ]
    }
  }
}
```

Each problem carries a stable `code` — branch on that, never on `message`.
Codes: `content-loss`, `stale-before`, `dangling-requirement`,
`duplicate-requirement`, `conflicting-operations`, `unknown-task`,
`duplicate-task`, `malformed-task-line`, `unbalanced-rename`, `empty-delta`,
`malformed-document`.

---

## Error kinds

No new `ErrorKind` value is introduced.

| Condition | `kind` |
| --- | --- |
| Any validation problem, including the content-loss guard | `validation` |
| `--ack` naming a task that is not an impact | `validation` |
| Delta or feature not found | `not-found` |
| Delta already applied (on `apply`) | *not an error* — `ok: true`, see below |
| Unacknowledged impacts | `confirmation-required` |
| `bd` unavailable during impact detection | `bd-unavailable` |
| Filesystem failure during rewrite | `internal` |

`bd-unavailable` follows the precondition convention in `json_output.py`'s
module docstring: `verify_available()` returns `False` rather than raising, so
the command translates it into an envelope itself.

**Already applied is a success**, not an error:

```json
{ "ok": true, "verb": "delta.apply",
  "result": { "already_applied": true, "applied_at": "2026-08-19T…" } }
```

Exit 0. A re-run being a reported no-op is what makes `delta apply` safe to put
in a script (FR-010), and reporting it as a failure would defeat that.
