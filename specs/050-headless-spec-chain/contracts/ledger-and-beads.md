# Contract: Ledger extension & remediation-bead adoption

## `record_standalone_assumption` (new, `assumptions/ledger.py`)

```python
async def record_standalone_assumption(
    client: BeadClient,
    *,
    payload: AssumptionPayload,     # question, adopted_answer, alternatives, severity, severity_defaulted
    owner_spec: str,                # "NNN-<feature>" directory name
    source_ref: str,                # e.g. "spec-chain:clarify"
) -> AssumptionRecord | None:      # None on dedup-merge, same as record_assumption
```

Bead shape: identical to `record_assumption` output (TASK/REVIEW, assignee "human",
labels `assumption` + `assumption-review` + `needs-human-review`, state keys
`assumption_severity`, `assumption_severity_defaulted`, `assumption_status="open"`,
`assumption_owner_spec=owner_spec`) with two differences: **no parent epic**, and state
key `source_ref` replaces `source_bead`. Dedup: normalized-question match against open
entries with the same `owner_spec` (escalate severity on merge, as today).

**Compatibility invariant** (FR-007, verified against current readers): `maverick brief`
(`per_spec_counts`), `maverick review` (label lookup), and the land gate
(`open_blocking_entries`) key on labels + state keys only — standalone entries flow
through all three unchanged. A regression test pins this.

## Remediation beads (created by spec-chain analyze step)

`BeadType.TASK`, unparented, label `spec-remediation`, state keys:
`speckit_feature=<NNN-feature>`, `remediation_source="spec-chain:analyze"`,
`finding_fingerprint=sha256(normalized title + location)`. Creation is idempotent per
fingerprint (re-run of analyze never duplicates). Severity hint goes in the description,
not the priority (findings are advisory — FR-012).

## Adoption (extension to `workflows/refuel_speckit`)

After epic create/find (fresh or delta), a new post-ingest step:

1. `client.query("status=open")`-based lookup of beads with
   `state["speckit_feature"] == feature` and no parent, label `spec-remediation`.
2. Preferred primitive: `BeadClient.update_parent(bead_id, parent_id)` — **implementation
   gate**: verify `bd update --parent` support at build start; if unsupported, fallback is
   `add_dependency(parent-child)` + state stamp `adopted_by_epic=<epic-id>`.
3. Adoption is idempotent (skip beads already parented / already stamped) and best-effort
   per bead (one failure does not abort ingestion — Principle IV).

Ledger beads are **not** adopted — they stay standalone with `owner_spec` linkage,
matching spec-049's epic-derivation-by-state, and remain governed by their own
answer/waive lifecycle.
