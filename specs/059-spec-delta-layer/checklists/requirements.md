# Specification Quality Checklist: Spec Delta Layer

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-22
**Feature**: [spec.md](../spec.md)

## Content Quality

- [X] No implementation details (languages, frameworks, APIs)
- [X] Focused on user value and business needs
- [X] Written for non-technical stakeholders
- [X] All mandatory sections completed

## Requirement Completeness

- [X] No [NEEDS CLARIFICATION] markers remain
- [X] Requirements are testable and unambiguous
- [X] Success criteria are measurable
- [X] Success criteria are technology-agnostic (no implementation details)
- [X] All acceptance scenarios are defined
- [X] Edge cases are identified
- [X] Scope is clearly bounded
- [X] Dependencies and assumptions identified

## Feature Readiness

- [X] All functional requirements have clear acceptance criteria
- [X] User scenarios cover primary flows
- [X] Feature meets measurable outcomes defined in Success Criteria
- [X] No implementation details leak into specification

## Notes

Five decisions were resolved in-spec rather than left as `[NEEDS CLARIFICATION]`
markers. Two of them the source prompt explicitly asked the spec to settle; three
came out of research and are recorded in Clarifications with their reasoning:

1. **Additive or deviating** (asked by the prompt) — purely additive, and
   structurally so: deltas live in a directory upstream neither reads nor
   writes, and an applied delta's *output* is an ordinary Spec Kit artifact.
2. **In-flight work** (asked by the prompt) — the apply refuses rather than
   mutating or skipping.
3. **Maverick vs. a Spec Kit plugin** — the merge lives in Maverick. Note this
   answer was **revised** during specification: Spec Kit 1.0 does have a real
   plugin architecture (the first assessment, made against our stale 0.16 pin,
   was wrong). The decision now rests on deterministic dispatch and guardrail
   fit, not on the absence of an extension point, and it explicitly leaves
   publishing a plugin open as a later distribution choice.
4. **RENAMED as a fourth operation** — a rename modelled as remove-plus-add
   destroys bead lineage.
5. **Apply does not run refuel** — keeping them separate preserves
   `refuel --dry-run` as a preview of the bead consequences.

## Post-research revisions (2026-08-22)

Two of the spec's assumptions were **measured against this repository's 54
specs and found false**. Both were flagged above as planner risks; both turned
out to be spec-level problems, and the spec was revised rather than the
constraint quietly narrowed during planning.

1. **Requirement-to-task coverage is not derivable.** 184 of 2,878 task lines
   cite a requirement id — 6.4% — and 24 of 54 feature directories cite none.
   The original FR-013/FR-018/FR-020 rested on that mapping. They now join at
   **task identity** instead, which is structural, uniqueness-enforced at parse
   time, and durably recorded on every bead. FR-007a states explicitly that the
   tool must never infer the mapping.
2. **Requirements carry no per-requirement acceptance criteria.** All 247
   acceptance-scenario blocks sit under user stories; none are inside the
   requirements section, and the upstream template puts them there by design.
   The scenario-loss guard became FR-005a, a **content-loss guard** over the
   requirement block, which is a structure the corpus actually has.

One assumption **survived** and got sharper: requirement-block parsing is
feasible. All 1,139 requirement lines match one grammar, ids are unique and
complete. FR-002b now defines a block against five measured corpus realities —
letter-suffixed ids, `####` grouping inside the section, indent-2 continuation
lines, indent-2 sub-bullets, and blank lines that do **not** terminate a block.
SC-010 pins it: parse-then-render must reproduce every existing `spec.md`
byte-identically.

Remaining planner item, unchanged:

- **Partial-region rewrite** of `spec.md` and `tasks.md` — the assumption that
  hand edits outside the delta's named regions survive — is now the riskiest
  thing left in the document. SC-010's round-trip requirement is the mechanism
  that makes it checkable, and it should be built first.

Two incidental findings recorded here so they are not lost:

- `speckit/detect.py`'s `SUPPORTED_SPECKIT_RANGE` is `>=0.14,<0.17`. Upgrading
  to Spec Kit 1.0.x needs that widened; it is not purely a config-pin bump.
- Ingestion stamps bead identity one key at a time and is explicitly
  non-atomic, so a process death between creating a bead and stamping it leaves
  a bead with no task id — invisible to withdrawal detection. FR-020 and a new
  edge case now cover it; the underlying non-atomicity is pre-existing and
  worth its own fix.
