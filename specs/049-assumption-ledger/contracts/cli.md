# Contract: CLI Behavior

## `maverick land` — assumption gate (FR-006)

Position: after the commits-above-base check and human-review manifest
display, before curation begins.

| Condition | Behavior |
|-----------|----------|
| No open medium/high entries | Gate passes silently; land proceeds as today |
| ≥1 open medium/high entry (incl. legacy treated as medium) | Print a blocking table — ID, severity, owning spec, question (truncated) — grouped by owning spec, then a hint: `Resolve with: maverick review <id>`; exit non-zero before any curation/push |
| `--dry-run` | Gate still evaluates and prints its table, the rest of the preview continues (no writes as always), and the command exits non-zero at the end if the gate would block a real land |

No bypass flag exists (clarification #3). Waiving via `maverick review` is the
audited escape hatch.

## `maverick review <bead-id>` — answer / waive (FR-009)

Existing command extended for ledger entries (beads labeled `assumption`):

- Displays the full entry: question, adopted answer, alternatives, severity
  (with `(defaulted)` marker when applicable), owning spec, change stamps
  (or `unstamped`), and the discovered-from source bead.
- **Answer flow**: prompts for (or accepts via option) answer text → records
  answer, closes bead. Empty answer rejected.
- **Waive flow**: requires a reason (option or prompt) → records
  who (git user name resolved via GitPython config, per Guardrail 8) /
  when (UTC ISO-8601) / why, closes bead. Empty reason rejected.
- Legacy escalation beads (no `assumption` label) keep today's review
  behavior unchanged.
- Output via Rich console per CLI standards (no emoji, `[green]✓[/]` style).

## `maverick brief` — per-spec assumption counts (FR-010, clarification #5)

- Default text view: compact `Assumptions` table — one row per spec
  (including zero rows for epics with no entries): columns
  `Spec | Open (L/M/H) | Answered | Waived | Legacy`.
- `--human` view: unchanged human queue table, plus the counts table.
- `--format json`: adds an `assumption_counts` array mirroring
  `PerSpecAssumptionCounts`.
- Beads store absent/uninitialized: section omitted (matches existing brief
  degradation behavior).

## `bd ready` (unchanged, verified behavior)

- Medium/high entries appear as ready human-assigned beads (FR-008).
- Low entries are deferred at creation and do not appear.
- Agent-side `select_next_bead` continues to skip them via the existing
  label filter — no contract change.
- A high-severity entry's `blocks` edge onto the next spec's epic keeps that
  epic's work out of `bd ready` until the entry is closed (FR-007).
