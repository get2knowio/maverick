# Contract: Decision Records, Match Feedback, and the Matching Formula

## Storage

| File | Format | Writer | Pruned by consolidation? |
|---|---|---|---|
| `.maverick/runway/decisions.jsonl` | JSONL, one `DecisionRecord.to_dict()` per line | human review surfaces only (single answer/waive, bulk waive) | **Never** — outside `episodic/` by design |
| `.maverick/runway/match-feedback.jsonl` | JSONL, one `MatchFeedbackRecord.to_dict()` per line | human review surfaces on resolving an entry that carried a suggestion | **Never** |

Both files are created by `RunwayStore.initialize()` (touch, like the episodic
files) and tolerated absent (read ⇒ empty corpus). Malformed lines are skipped with
the store's existing `runway_jsonl_parse_error` warning. The runway root is
git-committed; these files travel with the repository and never cross repositories.

## RunwayStore API additions

```python
async def append_decision(self, record: DecisionRecord) -> None
async def get_decisions(self, *, source_entry_id: str | None = None) -> list[DecisionRecord]
async def append_match_feedback(self, record: MatchFeedbackRecord) -> None
async def get_match_feedback(self) -> list[MatchFeedbackRecord]
```

Same conventions as existing methods: async, `aiofiles` append (non-atomic,
O_APPEND), read-side filtering by equality.

## Record shapes

See [data-model.md](../data-model.md) for field tables. JSON example lines:

```json
{"source_entry_id": "mv-142", "question": "Should retries use exponential backoff?", "normalized_question": "should retries use exponential backoff", "adopted_answer": "Yes, tenacity default", "resolution_type": "answered", "resolution": "Yes — AsyncRetrying, 3 attempts", "severity": "medium", "owner_spec": "052-conditional-landing", "resolved_by": "Paul O'Fallon", "resolved_at": "2026-08-06T14:03:22+00:00"}
```

```json
{"normalized_question": "should retries use exponential backoff", "source_entry_id": "mv-142", "outcome": "rejected", "recorded_at": "2026-08-07T09:15:02+00:00"}
```

## Matching formula (normative)

Defined in `assumptions/matching.py`; deterministic, zero model calls (FR-008).

```
normalize(text)  = collapse_ws(strip_punctuation(casefold(text)))
tokens(ntext)    = {t for t in ntext.split() if len(t) > 1}
base(a, b)       = 0.5 * SequenceMatcher(None, na, nb).ratio()
                 + 0.5 * |tokens(na) ∩ tokens(nb)| / |tokens(na) ∪ tokens(nb)|
                   (Jaccard term is 0 when both token sets are empty)

penalty(pairing) = 0.30 * max(0, rejections(pairing) - acceptances(pairing))
effective(entry, candidate) = base(entry.question, candidate.question) - penalty
```

`REJECTION_PENALTY` is 0.30 by construction, not tuning: the maximum possible base
score is 1.0, so a single net rejection drops any pairing — including an exact
match — to ≤ 0.70, below `PRESENTATION_THRESHOLD` (0.75). This is what makes
FR-015 ("a rejected pairing MUST NOT be presented as a default again") hold
unconditionally, while a subsequent acceptance (net 0) restores the pairing.

- **Corpus preparation**: collapse records per `source_entry_id` (latest
  `resolved_at` authoritative); exclude candidates where
  `source_entry_id == entry.bead_id` (self-match).
- **Selection**: candidates with `effective >= PRESENTATION_THRESHOLD (0.75)`;
  pick max by (`effective` desc, `resolved_at` desc, `source_entry_id` asc).
  Result is exactly zero or one suggestion.
- **Auto-resolution eligibility** (all required): entry severity is `low` (legacy
  entries synthesize medium ⇒ ineligible); `assumptions.resolution.auto_resolve_low.enabled`;
  `effective >= confidence_threshold` (validated `>= 0.75` at config load).

Changing `PRESENTATION_THRESHOLD`, `REJECTION_PENALTY`, or the blend weights is a
contract change to this file, not a tuning knob.

## Decision capture points (admission contract)

| Path | Writes DecisionRecord? | Writes MatchFeedback? |
|---|---|---|
| `maverick review <id> --answer/--waive` (human) | yes | yes, if entry carried a suggestion |
| `maverick review --spec … --waive` (human bulk) | yes, one per waived entry | yes, per entry carrying a suggestion |
| `maverick notify` scheduler auto-waive (`waived_by="maverick-scheduler"`) | **no** | no |
| Auto-resolution (`waived_by="maverick-resolver"`) | **no** | no |
| Human re-answer of an auto-resolved entry | yes | yes — recorded as **rejected** for the auto-resolving pairing |

Feedback classification: **accepted** iff resolution type equals the suggestion's
type AND `normalize(resolution text) == normalize(suggestion.resolution)`;
otherwise **rejected**.

All capture is best-effort: a failed write logs `[yellow]Warning:[/]` and never
fails the review action (FR-004).
