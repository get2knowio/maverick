# Contract: Delta document format

**Feature**: 059-spec-delta-layer
**Status**: Normative
**Location**: `specs/<feature-dir>/deltas/<NNN>-<slug>.md` (pending),
`specs/<feature-dir>/deltas/archive/<NNN>-<slug>.md` (applied)

Parsed with zero model calls (FR-003). Parsing fails loudly on ambiguity rather
than guessing.

---

## Why location is the state

A pending delta and an applied one differ by **directory, never by a marker
inside the file** (FR-023). A status field can disagree with reality — a delta
marked `applied` that was never applied, or the reverse after a bad merge — and
the whole point of this layer is to stop specs and work drifting apart. Moving
the file *is* the state transition.

Upstream Spec Kit neither reads nor writes `deltas/`, and
`detect.py`'s `_has_speckit_shape` checks only for `spec.md` + `tasks.md`, so the
directory cannot affect feature resolution.

---

## Skeleton

````markdown
# Delta: tighten the frontier gate

**Target**: 052-conditional-landing

## MODIFIED FR-014

### Before

- **FR-014**: The land gate MUST block on any open entry of medium or higher
  severity, including open legacy escalation beads.

### After

- **FR-014**: The land gate MUST block on any open entry of **any** severity,
  including low, and including open legacy escalation beads.

## REMOVED FR-021

### Before

- **FR-021**: The gate MUST offer a `--force` bypass for operators.

## ADDED FR-026

### After

- **FR-026**: `review --spec <name> --waive <reason>` MUST bulk-waive every open
  entry a spec owns matching the severity filter.

## RENAMED

- FROM: FR-018
- TO: FR-019

## TASKS

- ADDED: T042 [P] Widen the severity filter in `src/maverick/assumptions/land_report.py`
- WITHDRAWN: T017
````

---

## Grammar

### Header (required)

| Element | Rule |
| --- | --- |
| `# Delta: <title>` | Exactly one, first non-blank line. Title is free text. |
| `**Target**: <feature>` | Exactly one. Resolved through the existing `detect.resolve_feature` — accepts an exact directory name, an `NNN` prefix, or an exact name suffix. |

### Requirement sections

`## <OPERATION> <FR-id>` where OPERATION is one of `ADDED`, `MODIFIED`,
`REMOVED` — and `## RENAMED` with no id (see below).

Requirement ids match `FR-\d{3}[a-z]?`. The letter suffix is not optional to
support: 34 requirements in this repository already carry one.

| Operation | `### Before` | `### After` |
| --- | --- | --- |
| `ADDED` | must be absent | **required** |
| `MODIFIED` | **required** | **required** |
| `REMOVED` | **required** | must be absent |

A `### Before` / `### After` body is the **complete requirement block**,
verbatim, exactly as it appears (or will appear) in `spec.md`: the
`- **FR-NNN**: ` line plus any indent-2 continuation lines and sub-bullets. See
`requirement-block-grammar.md` for what a block is.

**It is never a diff and never a partial excerpt** (FR-002). A diff is ambiguous
about whitespace and applies cleanly against the wrong baseline; a partial
excerpt silently deletes whatever it omits, which is the field's documented
failure mode — the delta looks like a small change and lands as a large
deletion.

### The intent marker

```markdown
## MODIFIED FR-014 [shrink-intended]
```

Suppresses the content-loss guard **for that entry only** (FR-005e). There is
no command-line flag with the same effect, and the marker is recorded in the
application record so a reviewer can see which reductions were declared rather
than caught.

### `## RENAMED`

One section per document, containing one or more `FROM`/`TO` pairs:

```markdown
## RENAMED

- FROM: FR-018
- TO: FR-019
- FROM: FR-030
- TO: FR-031
```

Pairs must alternate and balance. A rename changes an identifier in `spec.md`
and has **no** task consequence unless the document states one — it exists as a
distinct operation precisely so a rename is not modelled as remove-plus-add,
which would destroy the requirement's bead lineage.

### `## TASKS`

Optional. When present, one entry per line:

```markdown
- ADDED: T042 [P] [US3] Description in `path/to/file.py`
- WITHDRAWN: T017
```

`ADDED` carries the **full task line** as it will appear in `tasks.md`, minus
the leading `- [ ] `. It must parse under the existing task grammar
(`speckit/parser.py`'s `_TASK_LINE_RE`), so `[P]` and `[USn]` markers work
exactly as they already do.

`WITHDRAWN` carries a bare task id.

**An absent `## TASKS` section is normal, not an oversight.** It is the dominant
delta shape — only 6.4% of task lines in this repository cite a requirement at
all — and such a delta applies quietly with no warning (FR-007b).

---

## Validation

Rejected, each naming the offending entry and its line number:

| Condition | Why |
| --- | --- |
| No `# Delta:` heading, or no `**Target**:` | Cannot identify the document or its target |
| Target does not resolve to a feature directory | `not-found` |
| Unknown `## <OPERATION>` keyword | Ambiguity, never a guess |
| `MODIFIED`/`REMOVED` naming a requirement the spec does not define | Dangling reference |
| `ADDED` whose id the spec already defines | Collision |
| `RENAMED` whose `TO` id the spec already defines | Collision |
| `RENAMED` with unbalanced `FROM`/`TO` pairs | Malformed |
| `### Before` not matching the spec's current block, byte-for-byte after whitespace normalization | Stale delta — it would apply against the wrong baseline |
| Same requirement named by two operations | Conflict; the fixed apply order resolves *ordering*, not *contradiction* |
| Zero entries of either kind | An apply that can only be a no-op polluting the archive |
| **Content-loss guard**: after-block drops a sub-bullet, or falls below 60% of the before-block's normalized length, without `[shrink-intended]` | FR-005a |
| `ADDED` task line that does not parse under the task grammar | It would corrupt `tasks.md` |
| `WITHDRAWN` task id absent from the current `tasks.md` | Nothing to withdraw |
| Duplicate task id across task entries | Ambiguous |

---

## Apply order

`RENAMED → REMOVED → MODIFIED → ADDED` (FR-004a), fixed as a module constant.

Ordering is defined so a document touching one requirement through more than one
operation has a single outcome rather than one that depends on the order the
author happened to type. Rename first so later operations address the new id;
remove before modify so a removed requirement is not first rewritten; add last
so a new id cannot collide with one still being removed in the same pass.

---

## Application record

Appended to the document as it moves to `deltas/archive/`:

```markdown
---

## Applied

**At**: 2026-08-23T09:14:02.113847+00:00
**Operations**: 1 added, 1 modified, 1 removed, 1 renamed
**Tasks**: 1 added, 1 withdrawn
**Declared reductions**: FR-014

### Acknowledged impacts

- T017 — bead `mv-0417`, status `in_progress` at 2026-08-23T09:13:55+00:00
```

This is what makes the archive readable as the spec's change history without
consulting version-control history (FR-022). "Declared reductions" lists entries
that carried `[shrink-intended]` — a reviewer can see what the guard was told to
ignore.
