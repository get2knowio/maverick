# Contract: Ledger Operations API (`maverick.assumptions`)

Public async API consumed by fly_beads actions, refuel_speckit `_chain_epic`,
and the land/review/brief CLI commands. All functions take explicit
`cwd: Path` (Guardrail 7 — no `Path.cwd()` defaults) and operate through
`BeadClient`; all return frozen dataclasses.

## models.py

```python
class Severity(StrEnum):
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"

@dataclass(frozen=True, slots=True)
class AssumptionRecord:
    bead_id: str
    question: str
    adopted_answer: str
    alternatives: tuple[str, ...]
    severity: Severity
    severity_defaulted: bool
    status: str                      # "open" | "answered" | "waived"
    owner_spec: str
    source_bead: str
    change_ids: tuple[str, ...]      # empty = unstamped
    is_legacy: bool                  # escalation bead without ledger fields

@dataclass(frozen=True, slots=True)
class PerSpecAssumptionCounts: ...   # see data-model.md aggregation shape
```

State-key string constants (`ASSUMPTION_LABEL`, `KEY_SEVERITY`, ...) are
exported here — no bare string literals at call sites (Constitution VI).

## ledger.py

| Function | Behavior contract |
|----------|-------------------|
| `record_assumption(client, *, payload, source_bead_id, epic_id) -> AssumptionRecord \| None` | Creates the entry bead per data-model shape: derives owner spec from epic state, applies the severity rule (see below), wires discovered-from edge, defers low-severity entries, wires next-epic blocks edge for high severity when a next chained epic exists. Dedup: returns the existing record (with a new discovered-from edge appended) instead of creating a duplicate when an open entry with the same normalized question exists under the epic. Never raises for policy reasons; bd failures raise typed `AssumptionLedgerError` for the caller's non-fatal handling. |
| `next_chained_epic(client, *, epic_id) -> str \| None` | Discovery rule for the high-severity edge target: among open epics with a `speckit_feature` state value, the one with the smallest NNN prefix strictly greater than the owning epic's NNN prefix (the same ordering `_chain_epic` uses). Returns `None` when the owning epic has no `speckit_feature` (flight-plan runs never wire next-epic edges) or no later epic exists — high then degrades to medium behavior. |
| `stamp_change_id(client, *, entry_ids, change_id) -> StampResult` | Appends `change_id` to `assumption_change_ids` on each entry. Append-only, idempotent per (entry, change_id). Partial failure returns per-entry outcomes; NEVER raises (FR-012 — a commit must not fail because stamping failed). |
| `answer(client, *, bead_id, answer_text) -> AssumptionRecord` | Requires non-empty text. Sets `assumption_answer`, `assumption_status=answered`, closes the bead (releasing blocks edges). |
| `waive(client, *, bead_id, reason, waived_by) -> AssumptionRecord` | Requires non-empty reason. Records who/when/why, `assumption_status=waived`, closes the bead. |
| `open_blocking_entries(client) -> tuple[AssumptionRecord, ...]` | Open entries with severity ∈ {medium, high}, including legacy escalation beads mapped to severity=medium with `is_legacy=True`. Powers the land gate. |
| `open_high_entries_before(client, *, epic_id) -> tuple[AssumptionRecord, ...]` | Open high-severity entries owned by specs ordered before the given epic; powers `_chain_epic` wiring at refuel. |

## report.py

| Function | Behavior contract |
|----------|-------------------|
| `per_spec_counts(client) -> tuple[PerSpecAssumptionCounts, ...]` | Aggregates all `assumption` beads by `assumption_owner_spec`; legacy escalation beads counted in `legacy_open`; every epic in the store yields a row even at zero counts (FR-010); ordered by owner spec identifier. |

## Severity rule (single authority)

The coercion rule — value ∉ {low, medium, high} (or absent) → `medium` +
defaulted flag — is defined once and applied in two layers with the same
semantics: `AssumptionPayload`'s validator coerces and exposes
`severity_defaulted: bool` (agent path), and `record_assumption` re-applies
the identical rule for direct callers, persisting
`assumption_severity_defaulted=true` whenever either layer defaulted.

## Error contract

`AssumptionLedgerError(MaverickError)` — single typed error for bd-layer
failures. Callers decide fatality: `record_assumptions` (workflow action)
warns and continues (mirrors `create_human_bead` non-fatal pattern);
CLI commands surface it as a formatted error.
