# Contract: `maverick delta`

**Feature**: 059-spec-delta-layer
**Status**: Normative

---

## Synopsis

```
maverick delta list [FEATURE] [--json]
maverick delta validate <DELTA> [--json]
maverick delta apply <DELTA> [--dry-run] [--ack TASK_ID]... [--json]
```

`DELTA` is `<feature>/<delta-slug>` (e.g. `052/001-tighten-frontier-gate`) or a
path to the document. `<feature>` resolves through the existing
`detect.resolve_feature` — exact directory name, `NNN` prefix, or exact name
suffix — so it behaves identically to `maverick refuel`'s NAME argument.

`maverick refuel` is unaffected by this command's existence: it neither applies
deltas nor changes behavior when they are present (FR-005c). A delta reaches the
beads only via an explicit `delta apply` followed by an ordinary refuel run.

---

## `delta list`

Lists pending deltas, and applied ones with their application date.

```
$ maverick delta list 052
052-conditional-landing

  Pending
    001-tighten-frontier-gate     1 modified, 1 removed, 1 added, 1 renamed
                                  2 task entries

  Applied
    000-initial-scope-cut         2026-08-19    1 removed
```

Exit 0 whether or not anything is pending. With no `FEATURE`, lists every
feature that has a `deltas/` directory.

---

## `delta validate`

Runs every check in `delta-document-format.md` and reports. Writes nothing.

```
$ maverick delta validate 052/001-tighten-frontier-gate
✓ 052/001-tighten-frontier-gate

  Requirements  1 modified, 1 removed, 1 added, 1 renamed
  Tasks         1 added, 1 withdrawn
```

A failure names the entry and its line number:

```
$ maverick delta validate 052/002-bad
✗ 052/002-bad

  line 14   MODIFIED FR-014: after-block is 41% of the before-block
            (floor 60%). Add [shrink-intended] if the reduction is
            deliberate.
  line 31   MODIFIED FR-021: before-block does not match the current
            spec — this delta was written against an older revision.
  line 48   WITHDRAWN T099: no such task in tasks.md.
```

Exit 0 when valid, 1 when not.

---

## `delta apply`

Validates, detects impacts, then rewrites `spec.md` and `tasks.md` and archives
the document. **Writes no beads** (FR-011) — the next `refuel --speckit` picks
up the consequences.

### The common case: no task entries

```
$ maverick delta apply 052/003-reword-fr002
✓ spec.md    MODIFIED FR-002
  tasks.md   unchanged
✓ archived to specs/052-conditional-landing/deltas/archive/003-reword-fr002.md
```

Exit 0, no warning. This is the dominant delta shape — only 6.4% of task lines
in this repository cite a requirement at all — and warning on it would appear on
most applies and devalue every other warning this command emits (FR-007b).

### With task entries and no impacts

```
$ maverick delta apply 052/001-tighten-frontier-gate
✓ spec.md    MODIFIED FR-014, REMOVED FR-021, ADDED FR-026, RENAMED FR-018 → FR-019
✓ tasks.md   +T042, -T017
✓ archived to specs/052-conditional-landing/deltas/archive/001-tighten-frontier-gate.md

  Next: maverick refuel 052 --speckit
        (+1 bead, -1 bead closed)
```

### With blocking impacts — the refusal

```
$ maverick delta apply 052/001-tighten-frontier-gate
Impacts (2) — nothing has been written:

  T017   bead mv-0417   in_progress
  T019   bead mv-0419   closed

Acknowledge each impact you accept, then re-run:
  maverick delta apply 052/001-tighten-frontier-gate --ack T017 --ack T019
```

Exit 1. **Nothing is written** — not `spec.md`, not `tasks.md`, not the archive.

```
$ maverick delta apply 052/001-tighten-frontier-gate --ack T017
Impacts (1) — nothing has been written:

  T019   bead mv-0419   closed
```

Still exit 1: every impact must be named. There is deliberately **no blanket
override** (FR-015) — one would clear impacts the human never read, including
any that arose since the last preview, which is precisely the case the refusal
exists to catch.

An `--ack` naming a task that is not an impact **fails** rather than being
ignored (FR-015b), so a stale acknowledgement left in a script cannot appear to
authorize something while authorizing nothing.

### `--dry-run`

Reports every artifact change and every impact, including ones that would cause
a refusal, with **zero writes** (FR-012). Exit 0 even when impacts exist — a
dry run reports, it does not refuse.

```
$ maverick delta apply 052/001-tighten-frontier-gate --dry-run
Would rewrite:
  spec.md    MODIFIED FR-014, REMOVED FR-021, ADDED FR-026, RENAMED FR-018 → FR-019
  tasks.md   +T042, -T017

Impacts (1) — would block:
  T017   bead mv-0417   in_progress

Would archive to deltas/archive/001-tighten-frontier-gate.md
```

### Already applied

```
$ maverick delta apply 052/000-initial-scope-cut
✓ Already applied 2026-08-19 — nothing to do.
```

Exit 0 (FR-010). A re-run being a reported no-op is what makes the command safe
in a script.

---

## Atomicity (FR-009)

Both files' new contents are computed **fully in memory** and validated before
anything is written. A failure at any point before the first write leaves the
pre-apply state exactly. The archive move happens last, so an interruption can
at worst leave the artifacts rewritten with the delta still pending — which a
re-run detects and reports as already applied, rather than applying twice.

---

## Read-only guarantees

On every path, including every failure path and an interrupt:

- no commit is created, amended, or moved;
- **no bead is created, updated, or closed** — bead consequences belong to a
  later, explicit `refuel --speckit` (FR-011);
- no assumption-ledger entry is created, and the land frontier is unaffected;
- no model is called, on any path (FR-003, FR-019).

Files this command may write, and nothing else:
`specs/<feature-dir>/spec.md`, `specs/<feature-dir>/tasks.md`, and the delta
document's move into `deltas/archive/`.

---

## Exit codes

| Code | Condition |
| --- | --- |
| `0` | Validated, applied, listed, dry-ran, or already applied |
| `1` | Invalid delta, unacknowledged impacts, or an apply failure |
| `130` | Interrupted |
