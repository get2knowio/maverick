# Quickstart: Validating Learned Assumption Resolution

Runnable scenarios proving the feature end-to-end. Prerequisites: a Maverick-managed
repository with `bd` initialized, the runway store initialized
(`maverick runway init`), and at least one assumption-ledger entry flow available
(any repo where `maverick fly` or `maverick spec` has recorded entries — the
sample-maverick-project works).

Contracts referenced: [decision-records.md](contracts/decision-records.md),
[entry-row-suggestion.md](contracts/entry-row-suggestion.md),
[config-schema.md](contracts/config-schema.md).

## Scenario 1 — Terminal outcomes become decision records (User Story 1)

```bash
# Resolve entries through the human surfaces:
maverick review <entry-1> --answer "Use exponential backoff via tenacity" --json
maverick review <entry-2> --waive "Accepted risk for v1" --json

# Verify: one JSONL line per resolution, human-attributed
cat .maverick/runway/decisions.jsonl | python3 -m json.tool --json-lines
```

Expect: two records with correct `question`, `resolution_type`, `resolution`,
`severity`, `owner_spec`, `resolved_by` (your git user.name). Re-answer `<entry-1>`
with different text and confirm a **third** line appears for the same
`source_entry_id` (history preserved; latest authoritative).

Negative check: run `maverick notify` with an `auto_waive_low` schedule policy that
waives an aged low entry — confirm **no** new line in `decisions.jsonl`
(scheduler waives are machine-initiated, excluded by FR-005).

## Scenario 2 — Suggestions surface with provenance (User Story 2)

```bash
# Record a new assumption closely matching an answered one (e.g. run a bead whose
# implementer adopts a near-identical question, or use the test fixtures), then:
maverick review --list --json | python3 -m json.tool
```

Expect on the matching entry's row: `"suggestion"` object with `resolution`,
`source_entry_id`, `source_spec`, `resolved_at`, `confidence >= 0.75`; unrelated
entries carry `"suggestion": null`. The entry still has `"blocks_landing": true` —
confirm `maverick land --status --json` reports it in `blocking.open` (suggestion
never bypasses the gate).

Skill check: invoke `/maverick-review` and confirm the suggested resolution is the
first option, labeled `(Recommended — prior decision from <spec>, <date>)`.

## Scenario 3 — Rejection suppresses the pairing (User Story 3)

```bash
# Resolve the suggested entry with a DIFFERENT answer:
maverick review <entry-with-suggestion> --answer "No, fixed interval" --json
cat .maverick/runway/match-feedback.jsonl   # expect outcome: "rejected"

# Record another assumption with the same question shape; list again:
maverick review --list --json
```

Expect: the previously rejected pairing's effective confidence dropped by 0.30 per
net rejection — enough to suppress even an exact match (max base 1.0 − 0.30 < 0.75)
— so the new entry carries `"suggestion": null`. Accepting a suggestion verbatim
instead writes `outcome: "accepted"`.

## Scenario 4 — Opt-in auto-resolution (User Story 4)

```yaml
# maverick.yaml
assumptions:
  resolution:
    auto_resolve_low:
      enabled: true
      confidence_threshold: 0.9
```

Record a **low**-severity assumption whose question matches a prior decision at
≥ 0.9 effective confidence. Expect:

- Entry is waived immediately: `review --list --status waived --json` shows
  `"auto_resolved": true`, `waiver.by == "maverick-resolver"`, waive reason citing
  the source decision.
- `maverick land --status --json`: `frontier_clear: true` (if nothing else open),
  and a real `maverick land` classifies **conditionally-verified** with the
  auto-resolved entry rendered distinctly in `land-report.md`.
- A medium-severity entry with the same match confidence stays open (severity
  ceiling).
- Human override: `maverick review <auto-resolved-id> --answer "..." --json`
  succeeds (no `already-resolved` refusal), supersedes the waive, and appends a
  `rejected` feedback line.
- Config guard: set `confidence_threshold: 0.5` and confirm config load fails.

## Scenario 5 — Degradation (FR-004 / FR-021, SC-007)

```bash
mv .maverick/runway .maverick/runway.bak    # simulate store outage
maverick review --list --json               # entries render, suggestion: null, exit 0
maverick review <id> --answer "still works" --json   # ledger write succeeds; warning only
mv .maverick/runway.bak .maverick/runway
```

Also corrupt one line of `decisions.jsonl` and confirm listing still works
(malformed line skipped with a warning).

## Automated validation

```bash
make test-fast                     # unit: matching, suggestions, store, serialize, config
make test                          # full parallel suite
make ci                            # pre-push gate (lint + typecheck + tests + format)
```

Key test modules (see plan.md structure): `tests/unit/assumptions/test_matching.py`
(formula determinism, normalization, tie-breaks, penalty fold),
`tests/unit/assumptions/test_suggestions.py` (attach/back-fill/auto-resolve,
self-match, degradation), `tests/unit/runway/test_store_decisions.py`
(append/read/collapse, consolidation leaves the files untouched).
