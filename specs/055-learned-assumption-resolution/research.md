# Research: Learned Assumption Resolution

All unknowns from Technical Context resolved. Decisions reference real code as of
`main` (post-054).

## R1 — Decision records live in new top-level runway JSONL files, exempt from consolidation

**Decision**: Add `.maverick/runway/decisions.jsonl` and
`.maverick/runway/match-feedback.jsonl` as append-only JSONL logs, addressed by new
constants in `runway/store.py` alongside `_INDEX_FILE`, with `RunwayStore` methods
following the existing append/get/rewrite pattern (`_append_jsonl`/`_read_jsonl`).
They sit at the store root, **not** under `episodic/`.

**Rationale**: `consolidate_runway` (`library/actions/consolidation.py:277`) prunes
the three episodic JSONL files by age/count and rewrites them. Decision records must
survive indefinitely (FR-002) — placing them outside the consolidation set is the
structural guarantee, not a convention. The runway root is git-committed by design
(`.gitignore` excludes `/.maverick/runs` and `/.maverick/notify` but not
`/.maverick/runway`), so the corpus survives clones and travels with the repository —
and stays within FR-022's single-repository scope. The store's existing
`_read_jsonl` skips malformed lines with a warning, giving corruption tolerance
(FR-021) for free.

**Alternatives considered**: (a) episodic files with a consolidation carve-out —
rejected: makes pruning code aware of an exception, easy to break silently.
(b) bd metadata on a dedicated bead — rejected: bd state is per-bead key/value, wrong
shape for a growing queryable corpus, and `bd` availability would become a hard
dependency for suggestion evaluation. (c) semantic markdown — rejected: free-form,
not deterministically parseable (Guardrail X.10).

## R2 — Matching: normalized-text similarity via stdlib `difflib` + token Jaccard; corpus-independent scores

**Decision**: `assumptions/matching.py` (new, pure, sync) defines:

- `normalize_question(text) -> str`: casefold → strip punctuation → collapse
  whitespace (exactly the clarified normalization).
- `base_score(a, b) -> float` in [0, 1]:
  `0.5 * difflib.SequenceMatcher(None, na, nb).ratio() + 0.5 * jaccard(tokens(na), tokens(nb))`
  where `tokens` splits normalized text on whitespace and drops 1-char tokens
  (mirroring the store's `_tokenize` convention).
- `PRESENTATION_THRESHOLD: Final = 0.75` (built-in, not configurable — clarify Q3).
- `REJECTION_PENALTY: Final = 0.30` — sized so one net rejection suppresses **any**
  pairing: max base is 1.0, and 1.0 − 0.30 = 0.70 < 0.75, which is what makes
  FR-015's "never presented as default again" unconditional rather than
  base-score-dependent.
- `effective_confidence = base_score - REJECTION_PENALTY * max(0, rejections - acceptances)`
  per pairing (clarify Q1: pairing = normalized question text × decision identity).

**Rationale**: Scores must be comparable to a fixed threshold across time, so they
must not depend on corpus composition. BM25 (`rank_bm25`, already used by
`RunwayStore.query`) is corpus-dependent — IDF shifts as records accumulate, and raw
scores are unbounded, making a fixed presentation threshold meaningless.
`SequenceMatcher` captures phrasing similarity; Jaccard captures shared vocabulary
regardless of order; the 50/50 blend is simple, documented, and reproducible
(FR-008). Both are stdlib/existing — no new dependency. Pairwise cost over ≤500
records of ≤150-char questions is well under SC-006's budget (R13).

**Alternatives considered**: BM25 over the corpus (rejected above); embedding
similarity (rejected: model call, violates FR-008/X.10); exact-normalized-match only
(rejected: too brittle — near-identical questions with one differing word would never
match, failing the feature's purpose).

## R3 — Feedback pairing keys on (normalized question text, source **entry** id); records are versions

**Decision**: A decision's stable identity is the ledger entry it resolved
(`source_entry_id` = the assumption bead id). Re-answering appends a new
`DecisionRecord` for the same `source_entry_id`; readers collapse per
`source_entry_id`, latest `resolved_at` authoritative (FR-003 — history preserved in
the log). `MatchFeedbackRecord` pairs `normalized_question` with
`source_entry_id`, so feedback survives re-answers of the underlying decision.

**Rationale**: The clarify session fixed the pairing as (normalized question text,
source decision record identity). Using a per-append record id would orphan feedback
whenever a decision is re-answered; the source entry id is the durable identity that
"the decision" denotes across its versions.

## R4 — Suggestion persists as ONE JSON-encoded bd state key: `assumption_suggestion`

**Decision**: New state keys in `assumptions/models.py`:
`KEY_SUGGESTION = "assumption_suggestion"` (value: compact JSON object — resolution
text, resolution type, source entry id, source spec, resolved-at, confidence,
computed-at) and `KEY_AUTO_RESOLVED = "assumption_auto_resolved"` (`"true"` when the
policy fired). `ledger.report_entry_from_details` parses `KEY_SUGGESTION` into a
typed `Suggestion` value on `AssumptionReportEntry`; unparseable JSON degrades to no
suggestion with a debug log.

**Rationale**: `BeadClient.set_state` issues **one bd invocation per key**
(`beads/client.py:467-511`) — a multi-key suggestion could be half-written, surfacing
a suggestion without its provenance. One key = one bd call = atomic. Precedent for
encoding structure into a single value exists (`assumption_change_ids` is
comma-joined); JSON is the right shape for seven typed fields. Persisting on the bead
(rather than recomputing) is what makes suggestions stable within and across sweeps
(clarify Q5) and lets `entry_to_dict` project them with zero extra I/O.

**Alternatives considered**: one state key per field (rejected: non-atomic);
recompute-on-read (rejected by clarify Q5 — unstable, and every listing would need
the runway corpus loaded).

**Addendum (quickstart validation)**: "JSON is the right shape" didn't anticipate
that `bd set-state` stores this value as part of a `"<dimension>:<value>"` label
with a total-length budget that **silently truncates on overflow — no error, no
warning**. Empirically verified against a real bd 1.1.2 sandbox: the safe value
length is ~254 minus `len(key)`, i.e. ~233 chars for `assumption_suggestion` (21
chars), and — contrary to an earlier hypothesis involving the event bead's
500-char title — independent of the bead id or `--reason` text length (neither
appears in the truncated label string). Full-field-name JSON with default
separators already costs ~235 chars with an *empty* `resolution` alone, i.e. the
original wire format overflowed before any real content was added — a
ship-blocking bug, not an edge case. Fixed by: (1) abbreviated internal keys
(`r`/`rt`/`sid`/`ss`/`ra`/`c`/`ca`) + compact JSON separators, cutting the
empty-resolution overhead to ~145 chars (`suggestion_to_json`/
`suggestion_from_json` in `assumptions/models.py`); (2) a defensive
`_MAX_SUGGESTION_JSON_LENGTH = 220` guard in `assumptions/suggestions.py`
(`_evaluate_and_persist`) that skips the `set_state` write entirely — treating
the suggestion as absent rather than persisting a truncated value — whenever the
encoded JSON would exceed it, a 13-char margin below the observed 233-char hard
boundary that still comfortably fits realistic content (a 64-char resolution +
24-char owner spec + live microsecond `computed_at` encodes to 214 chars).
This wire-format change is internal-only: `entry_to_dict`'s
full-field-name projection (`assumptions/serialize.py`, via `dataclasses.asdict`)
is untouched, so `review --list --json`/the land report are byte-identical to
before.

## R5 — Orchestration lives in `assumptions/suggestions.py`; ledger and runway stay decoupled

**Decision**: A new module `assumptions/suggestions.py` owns composition:

- `evaluate_suggestion(record, corpus, feedback) -> Suggestion | None` — pure; applies
  self-match exclusion (`candidate.source_entry_id != record.bead_id`), collapse
  (R3), scoring + effective confidence (R2), best-candidate selection with the
  deterministic tie-break (highest confidence, then most recent `resolved_at`, then
  lexically smallest `source_entry_id`).
- `attach_suggestions(client, store, records) -> None` — async; loads corpus +
  feedback once, evaluates each newly recorded entry, persists `KEY_SUGGESTION` for
  hits, and applies auto-resolution (R7) when the policy allows. Never raises:
  store-unavailable or write failure logs a warning and returns (FR-021).
- `backfill_suggestions(client, store, entries) -> updated_entries` — async; for
  listed entries with no stored suggestion, evaluate + persist; existing stored
  suggestions never replaced (clarify Q5).
- `record_decision(store, entry, *, resolution_type, resolution, resolved_by)` and
  `record_feedback(store, entry, *, accepted)` — async, best-effort (FR-004).

Call sites: `fly_beads/actions.py::record_assumptions` (after each
`record_assumption`), `spec_chain/workflow.py` (after each
`record_standalone_assumption`), `cli/commands/review/listing.py::run_list`
(back-fill), `cli/commands/review/entry_actions.py` (decision capture + feedback,
single and bulk paths).

**Rationale**: `ledger.py` (1347 LOC, Principle XI refactor-trigger territory) must
not grow an import on `runway` — the assumptions package deliberately imports no
workflow/CLI modules today, and keeping matching orchestration in a sibling module
preserves that layering while giving every call site one shared implementation
(Principle VII). Composition at call sites also keeps capture semantics untouched
(spec's out-of-scope: no change to how assumptions are captured — the ledger
functions' signatures and behavior are unchanged; suggestion attachment is a
post-step).

## R6 — Corpus capture happens in the human review surfaces, not inside `ledger.answer`/`waive`

**Decision**: `entry_actions.py` writes decision records + feedback after a
successful ledger write, in both `_review_ledger_entry` (answer/waive) and
`_bulk_waive_flow` (one record per waived entry). The scheduler's auto-waive path
(`cli/commands/notify.py::_execute_auto_waives`, `waived_by="maverick-scheduler"`)
and this feature's auto-resolution never touch these helpers — machine outcomes are
excluded structurally (FR-005), not by filtering.

**Rationale**: Corpus admission is defined by *who initiated* the resolution.
`maverick review` (single, bulk) is exactly the human surface; placing capture there
means no `actor` parameter threading through `ledger.waive` and no risk that a new
machine caller of `waive()` silently feeds the corpus. Follows the existing
`_project_after_write` pattern: post-write side work runs outside the JSON error
handler and fails soft (FR-004).

**Feedback derivation**: after resolution, if the entry carried a stored suggestion —
accepted iff resolution type matches and `normalize_question`-style normalization of
the resolution text equals the suggestion's; anything else (different answer, waive
where an answer was suggested, answer where a waive was suggested) is a rejection.

## R7 — Auto-resolution waives via `ledger.waive` with `waived_by="maverick-resolver"`; land gate and reconcile untouched

**Decision**: When the opt-in policy is enabled and a **low**-severity entry's
effective confidence ≥ the configured threshold, `attach_suggestions` calls the
existing `ledger.waive(client, bead_id=..., reason=..., waived_by="maverick-resolver")`
with a rationale citing the source decision (entry id, spec, date), then sets
`KEY_AUTO_RESOLVED="true"`. Severity gating uses the entry's recorded severity;
legacy entries synthesize medium (`_legacy_record_from_details`) so they are
structurally ineligible (FR-017) — no new code needed.

**Rationale**: The clarify session fixed waive-not-answer precisely because
`answered_unreconciled_entries` (`ledger.py:983`) would otherwise route machine
answers into reconcile's history rewriting. Waiving means:
- `classify()` (`land_report.py:57-69`) already downgrades any waived entry to
  `CONDITIONALLY_VERIFIED` — FR-019 holds with **zero changes to the land gate**.
- `waived_by` provenance is already rendered in the land report
  (`"Waived by {waived_by} at {waived_at}: {waive_reason}"`) and projected in
  `entry_to_dict`'s `waiver` object — distinguishability (FR-018) needs only the
  `auto_resolved` flag added to the row projection.
- Human override: `maverick review <id> --answer` on a waived entry currently fails
  the `ALREADY_RESOLVED` pre-check (`entry_actions.py:226-239`). FR-020 requires the
  pre-check to allow re-answering an **auto-resolved** waive (detected via
  `KEY_AUTO_RESOLVED`); the override records a rejection for the pairing that
  auto-resolved it. Human-waived entries keep the existing already-resolved refusal.

**Actor constant**: `"maverick-resolver"`, mirroring 054's `"maverick-scheduler"`.

## R8 — Config: new `assumptions.resolution` block beside `assumptions.schedule`

**Decision**: Extend `AssumptionsConfig` (`config.py:571`) with
`resolution: AssumptionResolutionConfig | None = None`:

```python
class AutoResolvePolicyConfig(BaseModel):
    enabled: bool = False
    confidence_threshold: float = Field(default=0.9, ge=0.75, le=1.0)

class AssumptionResolutionConfig(BaseModel):
    auto_resolve_low: AutoResolvePolicyConfig | None = None
```

`ge=0.75` encodes "at least as strict as the built-in presentation threshold"
(clarify Q3); the module asserts the bound equals
`matching.PRESENTATION_THRESHOLD` via a unit test so the two cannot drift. Absent
block ⇒ suggestions still work (they need no config); only auto-resolution is inert.

**Rationale**: Follows 054's proven pattern (`AssumptionScheduleConfig` +
double-opt-in sub-policy like `AutoWaivePolicyConfig`); Pydantic bound validation
gives FR-016's fail-on-misconfiguration for free through the existing config-load
error path.

## R9 — Row projection: additive `suggestion` and `auto_resolved` keys in `entry_to_dict`

**Decision**: `serialize.entry_to_dict` gains `"suggestion"` (object or `None`) and
`"auto_resolved"` (bool). Because the land report's `_entry_to_dict` aliases the same
function, `review --list --json`, `review.answer`/`review.waive` payloads,
bulk-waive rows, and `land-report.json` all pick the fields up in one change —
FR-011's "cannot drift" is structural. Additive keys; `land-report.json`
`schema_version` stays 1 (documented in the contract).

## R10 — Skill delta: suggestion becomes the recommended default, attributed

**Decision**: `skills/review_console/SKILL.md` sweep step: when an entry row carries
`suggestion`, its resolution is presented as the **first** option labeled
`"(Recommended — prior decision from <source_spec>, <resolved_at date>)"`; the
adopted answer drops to second (losing its "(Recommended)" suffix); alternatives,
waive, skip, and overflow chaining are unchanged. A waive-sourced suggestion makes
"Waive this entry (recommended — prior decision …)" the first option with the prior
reason pre-filled. Entries without a suggestion render exactly as today (FR-018 of
053 preserved). The skill still applies decisions through the JSON verbs only.

## R11 — Degradation matrix

| Failure | Behavior | Source |
|---|---|---|
| Runway store missing/uninitialized | No suggestions, no decision capture; debug log; all commands proceed | FR-021, `_get_store` pattern (`library/actions/runway.py:33`) |
| Corrupt JSONL line | Skipped with `runway_jsonl_parse_error` warning (existing) | store `_read_jsonl:499` |
| Decision-record write fails | `[yellow]Warning:[/]`, ledger write already durable | FR-004, R6 |
| `KEY_SUGGESTION` write fails during attach | Entry simply has no stored suggestion; back-fill retries on next listing | clarify Q5 |
| Unparseable stored suggestion JSON | Treated as absent (debug log); back-fill will NOT overwrite (existing key present) — listed without suggestion | R4; conservative: never silently replace |
| Auto-resolution `waive` fails | Warning; entry stays open with its suggestion; retried never (attach is once) — human resolves normally | FR-021 |

## R12 — Self-match and dedup interplay

`record_assumption` already dedups identical open questions per epic
(`_find_existing_open_entry`) and `record_standalone_assumption` per owner spec — so
a *new* entry can still legitimately match a *resolved* prior entry with the same
question (the resolved bead is closed and invisible to dedup). Self-match exclusion
in `evaluate_suggestion` (`candidate.source_entry_id != record.bead_id`) covers the
back-fill path, where an entry could otherwise match the decision record produced by
its own earlier resolution after a re-open/re-answer cycle.

## R13 — Performance check (SC-006)

500 decision records × `SequenceMatcher.ratio()` on ~100–150-char normalized strings
≈ 10–30 µs/pair pure-Python ⇒ ~15 ms per entry, plus one JSONL read (~100 KB) per
attach/back-fill batch (loaded once for the whole batch, not per entry). Recording a
typical bead's 0–3 assumptions and listing a 30-entry sweep both stay well under the
1-second budget. No caching or indexing needed at this scale; revisit only if
corpora exceed ~10k records.
