# Quickstart: `maverick delta`

**Feature**: 059-spec-delta-layer

Validation scenarios that prove the feature end to end. Every one is runnable
against a scratch repository; none needs a model, a network, or a configured
provider — the whole layer makes zero model calls.

---

## Prerequisites

A Spec Kit feature directory with `spec.md` and `tasks.md`. `bd` is needed only
for impact detection (scenarios 3 and 5); scenarios 1, 2, and 4 run without it.

No `maverick.yaml` agent bindings are required.

---

## Scenario 1 — the common case: a requirement change with no task consequence

The dominant shape. Proves FR-007b.

```bash
mkdir -p specs/052-conditional-landing/deltas
cat > specs/052-conditional-landing/deltas/001-reword.md <<'EOF'
# Delta: reword the gate requirement

**Target**: 052-conditional-landing

## MODIFIED FR-002

### Before

- **FR-002**: The gate MUST evaluate the frontier before curating.

### After

- **FR-002**: The gate MUST evaluate the assumption frontier before any
  curation step runs, on all three curation paths.
EOF

maverick delta validate 052/001-reword
maverick delta apply 052/001-reword
```

**Expect**: validate reports `1 modified`. Apply rewrites `spec.md`, leaves
`tasks.md` untouched, archives the document, exits 0 **with no warning**.

```bash
git diff --stat specs/052-conditional-landing/
# spec.md only — tasks.md unchanged
ls specs/052-conditional-landing/deltas/archive/
# 001-reword.md
```

---

## Scenario 2 — the round-trip invariant (SC-010)

The design's own falsification mechanism. Proves the block model matches the
real corpus rather than an idealized version of it.

```bash
uv run pytest tests/integration/delta/test_requirement_roundtrip.py -q
```

**Expect**: every `specs/*/spec.md` in the repository parses and re-renders
byte-identically — 54 files, 1,139 requirement blocks. A failure names the file
and the first line that differs.

This test runs against the **live** `specs/` tree, not a fixture. A fixture
would freeze the corpus at capture time, and the next spec written in an
unanticipated style would pass the suite and fail in use.

---

## Scenario 3 — the refusal (FR-014, FR-015)

The safety property. Proves apply writes nothing when work is already in flight.

Set up a feature whose `T017` bead is in progress, then:

```bash
cat > specs/052-conditional-landing/deltas/002-drop-t017.md <<'EOF'
# Delta: drop the force-bypass work

**Target**: 052-conditional-landing

## REMOVED FR-021

### Before

- **FR-021**: The gate MUST offer a `--force` bypass for operators.

## TASKS

- WITHDRAWN: T017
EOF

maverick delta apply 052/002-drop-t017
```

**Expect**: exit 1, an impact table naming `T017`, its bead, and `in_progress`,
and **nothing written** — verify with `git status --porcelain` before and after.

```bash
maverick delta apply 052/002-drop-t017 --ack T099
```

**Expect**: exit 1, `validation` — `T099` is not an impact. A stale
acknowledgement must fail rather than be ignored (FR-015b).

```bash
maverick delta apply 052/002-drop-t017 --ack T017
```

**Expect**: exit 0, artifacts rewritten, archive records the acknowledgement
with the bead's status *at the time it was cleared*.

---

## Scenario 4 — the content-loss guard (SC-008, SC-008a)

Both sides. A guard that only ever fires is as useless as one that never does.

```bash
# Fires: after-block is 41% of the before-block
maverick delta validate 052/003-truncated
# ✗ line 14  MODIFIED FR-014: after-block is 41% of the before-block (floor 60%)

# Does not fire: ordinary tightening, one redundant clause removed
maverick delta validate 052/004-tightened
# ✓ 1 modified

# Fires: a sub-bullet dropped, even though length barely changed
maverick delta validate 052/005-lost-bullet
# ✗ line 22  MODIFIED FR-009: after-block drops 1 sub-bullet

# Suppressed for that entry only, by the marker
maverick delta validate 052/006-declared
# ✓ 1 modified (1 declared reduction: FR-014)
```

**Expect**: exactly that pattern. Scenario 004 is the one that matters most — if
it fails, the threshold is wrong and authors will learn to mark everything.

---

## Scenario 5 — consequences reach the beads (SC-002)

Proves the apply/ingest split, and that only open-unstarted beads are closed.

```bash
maverick refuel 052 --speckit --dry-run
```

**Expect**: `+1 bead` for the added task, `-1 bead closed` for the withdrawn
one, no second epic, zero writes.

```bash
maverick refuel 052 --speckit
bd show mv-0417
```

**Expect**: the withdrawn task's bead is closed with a reason citing the delta.
Every bead that was already in progress or closed is **untouched** — compare
complete `bd list` snapshots before and after.

---

## Scenario 6 — machine consumption

```bash
maverick delta apply 052/001-reword --dry-run --json | jq '.result.would_block'
# false

maverick delta apply 052/002-drop-t017 --json | jq -r '.error.details.outstanding[]'
# T017

maverick delta list --json | jq -r '.result.features[].pending[].delta'
```

**Expect**: exactly one JSON document on stdout in every case, success and
failure alike, with all narration on stderr.

---

## What this feature will not do

- It will not run `refuel`. Applying rewrites artifacts; beads change on the
  next explicit refuel run.
- It will not derive which tasks a requirement covers. Only 6.4% of task lines
  in this repository cite a requirement, so any such derivation would work on
  three specs and fail silently on the other 51. A delta that changes work says
  so explicitly.
- It will not close, reopen, or edit a bead a human or agent has started or
  completed — on any path.
- It will not call a model, on any path.
- It will not touch a repository that has no `deltas/` directory. Every existing
  command behaves identically there, verifiable by the existing suite.
