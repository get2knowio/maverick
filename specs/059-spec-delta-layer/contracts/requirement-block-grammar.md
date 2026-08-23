# Contract: Requirement-block grammar

**Feature**: 059-spec-delta-layer
**Status**: Normative
**Implements**: FR-002b, SC-010

Defines what a "requirement block" is in `spec.md`, so a delta's `### Before` /
`### After` bodies have an unambiguous referent and the apply can rewrite one
block without disturbing its neighbours.

Every rule below was measured against this repository's 54 specs (1,139
requirement lines). Where a rule exists to handle a corpus reality, the count is
given — these are not hypotheticals.

---

## Section boundary

**Anchor**: `^### Functional Requirements\s*$`. Present in **54/54** specs.

**Do not anchor on `## Requirements`** — it has three variants in the corpus
(`*(mandatory)*` ×52, `_(mandatory)_` ×1, bare ×1), and two specs would be
missed entirely.

**Terminate** the section at the next `^## ` or `^### ` heading. In 50/54 that
is `### Key Entities`.

---

## Block boundary

A block **starts** at a line matching:

```
^- \*\*FR-\d{3}[a-z]?\*\*: 
```

All 1,139 requirement lines match this with zero exceptions — column zero, `- `,
bold id, colon, space. No `*` bullets, no indented definitions, no missing
colons.

A block **ends** at whichever comes first:

- the next line matching the start pattern, or
- the next `^## ` or `^### ` heading.

### Three things that MUST NOT terminate a block

| Non-terminator | Count | Consequence of getting it wrong |
| --- | --- | --- |
| A blank line | — | Spec 027 blank-separates *every* requirement and blank-separates its sub-bullets from their parents. Terminating here truncates 10 sub-bullets in 027 alone. |
| A `####` heading | **104**, in 20 specs | These are in-block grouping markers (`#### Safety Hooks (PreToolUse)`, `#### The delta document`). Terminating here mis-scopes every group. |
| A bold pseudo-heading (`**Data Structures**:`) | **29**, in specs 010, 016, 052, 055 | Ordinary block content. |

This is the single most error-prone part of the parser, which is why SC-010
exists.

---

## Block contents

| Element | Rule | Count |
| --- | --- | --- |
| Header line | The `- **FR-NNN**: ` line | 1,139 |
| Continuation lines | Indent-2, not starting `- ` — hard-wrapped prose | 371, in 6 specs |
| Sub-bullets | Indent-2, starting `- ` | 23, in specs 007, 027, 034 |

Indent depth is only ever 0 or 2 in the corpus. Zero code fences, zero tables,
zero `[NEEDS CLARIFICATION]` markers appear inside requirement blocks.

Sub-bullets may be separated from their parent by a blank line (spec 027) or not
(spec 007). Both forms are valid and both must round-trip.

---

## Identifiers

**Pattern**: `FR-\d{3}[a-z]?`

- Always exactly three digits — 1,199/1,199 numeric parts are length 3. No
  `FR-1`, no `FR-0001`.
- **34 ids carry a letter suffix** across 13 specs (`FR-002a`, `FR-019c`). A
  parser that assumes `FR-\d{3}` will silently fail to match them.
- Unique within a spec; no duplicates anywhere in the corpus.
- Complete — no gaps in any spec's id set.

**Ordering**: preserve file order; never sort. Two specs (015, 050) have
requirements out of numeric order with complete id sets, and sorting would
silently reorder them. Any sort that is needed must not assume ids sort
numerically — `FR-002a` sits between `FR-002` and `FR-003`.

Other prefixes exist in specs but are **out of scope for deltas**: `SC-` (371,
under `### Measurable Outcomes`) and `NFR-` (2, in specs 014 and 032 only).

---

## Passthrough

Everything inside the section that is not a requirement block — the `####`
headings, the bold pseudo-headings, blank runs between blocks — is carried
**verbatim** and re-emitted untouched.

This is what makes a rewrite safe on a repository whose specs have been
curated: applying a delta to one requirement in one spec must leave the other
1,138 requirements, and the other 53 files, byte-identical.

---

## The round-trip invariant

```
render(parse(text)) == text
```

**for every `specs/*/spec.md` in the repository** (SC-010).

This is the design's own falsification mechanism. Every rule above is a claim
about the corpus; if any of them is wrong, the round-trip fails on a real file
during the test run rather than corrupting someone's spec in production. It is
also why every field stores lines verbatim rather than normalized — normalizing
is precisely what breaks round-trips, and a tool that rewrites specs must not
reformat the ones it was not asked to touch.

The test must run against the **live** `specs/` tree, not a fixture copy. A
fixture would freeze the corpus at the moment it was captured, and the next spec
written in an unanticipated style would pass the suite and fail in use.
