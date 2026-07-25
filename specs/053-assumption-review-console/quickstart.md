# Quickstart: Assumption Review Console

**Feature**: 053-assumption-review-console

Runnable validation scenarios proving the feature end-to-end. Row/document
shapes referenced here are normative in [contracts/](./contracts/) and
[data-model.md](./data-model.md).

## Prerequisites

- Maverick installed (`uv sync`), `bd` CLI available, repo initialized
  (`maverick init` — jj colocated, beads ready).
- A ledger with entries to exercise. For a synthetic fixture, seed via
  the test helpers (see `tests/integration/cli/test_json_verbs_scenario.py`)
  or use any repo where `maverick fly` recorded assumptions.
- `jq` for spot-checking output (optional).

## Scenario 1 — Headless verbs (User Story 1)

```bash
# 1. List the open queue (sweep population), machine-readable
maverick review --list --json | jq '.verb, .ok, .result.counts'
# EXPECT: "review.list", true, counts object; exit 0
# EXPECT: stdout is exactly one JSON document (pipe through jq -e '.' to assert)

# 2. Filters
maverick review --list --status waived --severity low --json | jq '.result.entries | length'

# 3. Answer an entry (pick an id from step 1)
maverick review <bead-id> --answer "Use ISO-8601 everywhere" --json \
  | jq '.result.action, .result.entry.status, .result.entry.reconcile.status'
# EXPECT: "answered", "answered", "pending"; exit 0

# 4. Answer it again from a "concurrent" session after waiving elsewhere
maverick review <waived-id> --answer "x" --json | jq '.ok, .error.kind'
# EXPECT: false, "already-resolved"; exit 1

# 5. Waive + bulk-waive
maverick review <bead-id> --waive "accepted risk" --json | jq '.result.action'
maverick review --spec <owner-spec> --waive "low-sev noise" --json \
  | jq '.result | {waived: (.waived|length), failed}'
# EXPECT: per-entry enumeration; exit 0 when failed == {}

# 6. No TTY anywhere: re-run any verb with stdin/stdout detached
maverick review --list --json < /dev/null | jq -e '.ok'
```

## Scenario 2 — Reconcile verbs

```bash
# Detection preview (status verb): read-only, always exit 0
maverick reconcile --dry-run --json | jq '.result.dry_run, [.result.outcomes[].status]'
# EXPECT: true, statuses only "reconciled"/"skipped"

# Real run: exactly once, synchronous; progress on stderr only
maverick reconcile --json 2>progress.log | jq '.result.exit_success, [.result.outcomes[].status]'
# EXPECT: stdout parseable in isolation; exit 0 iff nothing to do or all reconciled
# EXPECT: needs_interactive_review outcomes carry reason + escalation_bead_id

# Precondition failure shape (run with a dirty working copy)
maverick reconcile --json | jq '.ok, .error.kind'
# EXPECT: false, "dirty-working-copy"; exit 1
```

## Scenario 3 — Land verbs

```bash
# Status query: never fails on "blocked", never curates
maverick land --status --json | jq '.result.frontier_clear, .result.verification, .result.blocking'
# EXPECT: exit 0 whether clear or blocked; report persisted under .maverick/runs/<id>/

# Apply while blocked: refusal envelope, same gate as human mode
maverick land --json | jq '.ok, .error.kind, (.error.details.report.totals)'
# EXPECT: false, "frontier-blocked"; exit 1

# Consent guard (run BEFORE landing — needs a clear frontier and work to land):
# agent-curation path without --yes
maverick land --json | jq '.error.kind'
# EXPECT: "confirmation-required" (when gate passes and agent curation is reached)

# Apply with clear frontier, consent supplied by caller
maverick land --yes --json | jq '.result.landed, .result.verification, .result.mode'
# EXPECT: true, "verified" or "conditionally-verified"; exit 0
```

## Scenario 4 — Skill install & guided sweep (User Stories 2–3)

```bash
# Install/refresh the skill into the project
maverick init
test -f .claude/skills/maverick-review/SKILL.md && echo installed
# EXPECT: installed; re-running init refreshes it idempotently

# Uninstall removes it
maverick uninstall --dry-run   # shows the skill among removals
```

Then, in Claude Code inside the project:

1. Run `/maverick-review` (or ask "review my pending assumptions").
2. EXPECT: entries presented one at a time, grouped by spec, severity
   high→low; each question offers the adopted answer (Recommended),
   alternatives, free-form via Other, and a route to waive/skip.
3. Decide a few entries; interrupt the session; re-invoke.
   EXPECT: decided entries do not reappear (immediate application).
4. Complete the sweep. EXPECT: exactly one `maverick reconcile --json`
   invocation (verify in the session transcript), a plain-language
   frontier report, and a landing offer only if clear.
5. Confirm landing. EXPECT: `maverick land --yes --json` runs; the
   classification banner is relayed; no jj/git commands appear anywhere
   in the skill's transcript.

## Scenario 5 — Regression: human modes unchanged

```bash
# No --json: outputs and exit codes identical to pre-feature behavior
maverick review <bead-id>          # interactive menu still works (FR-018)
maverick reconcile --dry-run       # Rich table preview
maverick land --dry-run            # full preview, deferred exit on block
maverick brief --format json       # pre-existing payload untouched
```

## Automated validation

```bash
make test               # unit + integration, includes new test modules
make ci                 # pre-push gate: lint + typecheck + tests + format
```

Key automated coverage (see plan.md test layout): envelope/error-kind
mapping, stdout purity (no stray bytes around the document), listing
filters + canonical ordering, already-resolved guard, reconcile/land
envelope projections, gate-refusal with embedded report, init
install/refresh + uninstall removal, and human-mode snapshot regressions.
