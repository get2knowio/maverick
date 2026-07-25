# Contract: `maverick-review` Claude Code skill

**Feature**: 053-assumption-review-console
**Artifact**: `src/maverick/skills/review_console/SKILL.md` (packaged),
installed to `<project>/.claude/skills/maverick-review/SKILL.md` by
`maverick init`; removed by `maverick uninstall`.

This contract specifies the skill's *behavior* — what the SKILL.md
instructions must make Claude Code do. The skill is judgment and
presentation only: its sole effect channel is invoking the JSON verbs
defined in the sibling contracts. It MUST NOT run jj/git/bd commands,
edit files, or mutate ledger state by any other means (FR-011).

## Identity

- Frontmatter: `name: maverick-review`; `description` carries the
  trigger text ("human review console for Maverick assumption sweeps —
  use when the user wants to review pending assumptions, answer or waive
  ledger entries, reconcile answers, or land"); `user-invocable: true`.
- Invocable as `/maverick-review`; also model-invocable when the user
  asks in prose to review assumptions.

## Preflight

1. Run `maverick review --list --json`.
2. On `bd-unavailable` or non-JSON output: report the environment
   problem and stop (suggest `maverick init` / installing `bd`). Never
   guess at queue state.
3. If `entries` is empty: say nothing is pending, then run
   `maverick land --status --json` and report the frontier state
   (FR-013). Offer landing if clear (see Landing below). Done.

## Sweep

4. Present entries **one at a time, in document order** (the listing is
   pre-sorted: spec group → severity high→low → ledger order; FR-009).
   When entering a new spec group, say which spec the following entries
   belong to.
5. For each entry, ask one question (AskUserQuestion) showing: the
   question text, owning spec, severity, and affected change ids.
   Options (FR-010):
   - The adopted answer, marked "(Recommended)" — first option.
   - Each recorded alternative, up to the option surface's capacity.
   - A "Waive / more…" option when alternatives overflow or to reach
     waive/skip.
   - Free-form input arrives via the built-in "Other" affordance.
   Every recorded alternative MUST be reachable (follow-up question for
   overflow); none may be silently dropped.
6. Decision → verb, applied **immediately** (FR-011):
   - Confirm adopted answer → `maverick review <id> --answer "<adopted>" --json`
   - Alternative or free-form → `maverick review <id> --answer "<text>" --json`
     (empty/whitespace free-form: re-prompt, never invoke)
   - Waive → collect a reason, then `maverick review <id> --waive "<reason>" --json`
   - Skip → no invocation; entry stays open; continue.
7. On `already-resolved`: tell the human it was resolved elsewhere
   (show the current state from `error.details.entry`) and continue the
   sweep. On any other `ok: false`: report kind + message and continue
   with remaining entries; never retry an invocation unprompted.
   On `ok: true` with `"degraded": true` (and `entry: null`): the
   decision **was** recorded — only its post-write row was unreadable.
   Report it as recorded and continue; never re-apply.
   **Interruption tolerance (FR-012)**: the skill holds no sweep state —
   every decision was already applied when made. If a session is
   interrupted, a later invocation simply starts at Preflight again; the
   fresh listing contains only the still-open entries, so decided
   entries never reappear.
8. **Bulk-waive shortcut** (clarification Q5): when ≥2 open low-severity
   entries share the current spec group, the skill MAY offer once per
   spec: "waive all remaining low-severity entries in <spec>?" with a
   reason prompt → `maverick review --spec <spec> --waive "<reason>" --json`
   (default low severity). Per-entry presentation remains the default;
   declining continues entry-by-entry. Ids in the result's `unprojected`
   list were waived successfully (row unreadable only) — count them as
   waived, never as failures.

## Batched reconcile (FR-014)

9. After the last entry: if **zero** answers were recorded during the
   sweep (only waives/skips), skip reconcile entirely.
10. Otherwise run `maverick reconcile --json` **exactly once**. Never per
    answer; never re-run on failure.
11. Report outcomes from `result.outcomes`: reconciled entries briefly;
    every `needs_interactive_review` or `skipped` outcome explicitly with
    its `reason` and `escalation_bead_id` (FR-017). On an `ok: false`
    envelope (`dirty-working-copy`, `concurrent-run`, `locked`, …):
    explain, suggest the remedy (e.g. retry after the other run
    finishes), do not retry (spec edge case).

## Frontier report & landing (FR-015, FR-016)

12. Run `maverick land --status --json`. If `result.degraded` is true the
    ledger could not be read — `frontier_clear` is then trivially true
    and means nothing; say so, offer no landing, skip to step 15.
    Otherwise report the frontier in plain language: **verified**,
    **conditionally verified**, or **still blocked** — when blocked, list
    blocking entries with next steps (open → review it;
    pending_reconcile → run reconcile / resolve escalations).
13. If `frontier_clear` is true and `degraded` is not: ask the human
    whether to land now
    (single confirm question). Only on explicit confirmation run
    `maverick land --yes --json`. Report `verification` classification
    and `hint` from the result. On `ok: false` (`frontier-blocked` race,
    `curation-failed`, …): report kind + message; do not retry.
14. If the human declines, end with the frontier summary; state that
    `maverick land` remains available.

## Reporting

15. End every session with a short summary: entries answered / waived /
    skipped, bulk-waives, reconcile outcome counts, frontier state, and
    landing result if any.

## Prohibitions

- No jj / git / bd / file mutations; no verbs outside this contract.
- No blind retries of any failed invocation.
- No landing without explicit human confirmation in this session.
- No parsing of human-mode (non-`--json`) output.
