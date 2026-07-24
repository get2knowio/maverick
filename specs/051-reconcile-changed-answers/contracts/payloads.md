# Contract: Reconcile structured-output payloads

Module: `src/maverick/payloads.py`. All payloads subclass
`SupervisorInboxPayload` and are registered in
`SUPERVISOR_TOOL_PAYLOAD_MODELS` (keys are stable public API). All `Field(...)`
declarations carry `description=` (constitution VI).

## `submit_correction` → `SubmitCorrectionPayload`

Returned by `ReconcilerAgent.correct(...)` after editing the working-copy
child of the target change.

```json
{
  "summary": "string, min_length=1 — what the correction changes and why",
  "files_touched": ["repo-relative paths the agent edited"],
  "no_change_required": false
}
```

Rules:
- `no_change_required=true` MUST be accompanied by `files_touched=[]`;
  validator enforces. Workflow cross-checks against `diff_stat("@")`: agent
  claim and actual delta must agree (empty↔empty), else the answer fails
  (payload/working-copy mismatch is a correctness failure, not a retry).
- No `assumptions` field by design — a reconcile agent that cannot proceed
  without adopting a new assumption must say so in `summary` and leave the
  delta empty; the workflow escalates.

## `submit_conflict_resolution` → `SubmitConflictResolutionPayload`

Returned by `ReconcilerAgent.resolve_conflicts(...)` per conflicted change per
round.

```json
{
  "resolved_files": ["files whose conflict markers were fully removed"],
  "unresolvable": ["files the agent declines to resolve"],
  "notes": "optional string"
}
```

Rules:
- Non-empty `unresolvable` immediately ends the round loop for this answer
  (counts as budget-terminating: rollback + escalation — do not spend
  remaining rounds re-asking the same impossible question).
- Workflow verifies ground truth via the `conflicts()` revset after each
  round; payload contents are advisory, revset state is authoritative.

## `submit_semantic_dependents` → `SubmitSemanticDependentsPayload`

Returned by `SemanticDependentsAgent.analyze(...)` for a batch of descendant
diffs.

```json
{
  "findings": [
    {
      "change_id": "jj change id of the analyzed descendant",
      "dependent": true,
      "reason": "why this code depends on the old assumption",
      "fix_instructions": "imperative instructions for the fix (empty when dependent=false)"
    }
  ]
}
```

Rules:
- Exactly one finding per analyzed descendant (workflow supplies the list;
  validator checks ids ⊆ supplied set; missing ids treated as
  `dependent=false`).
- `dependent=true` with empty `fix_instructions` is invalid (validator).
- Fixes are applied by the ReconcilerAgent via the correction mechanism, never
  by the semantic agent.

## Agent context contract (prompt inputs, FR-005/FR-007)

Every reconcile agent call receives, verbatim: the ledger `question`, the
`adopted_answer` (old assumption), the `human_answer` (new answer), plus
stage-specific content (target diff / conflicted files / correction diff +
descendant diff). Prompt builders live with the agents
(`agents/reconciler.py`, `agents/semantic_reviewer.py`) per the
agents-know-HOW rule.
