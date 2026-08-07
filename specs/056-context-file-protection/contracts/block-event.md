# Contract: block events and the run artifact

## `ContextFileWriteBlocked` (ProgressEvent)

New frozen dataclass in `maverick/events.py`, registered in `_EVENT_CLASSES`
(and `_TUPLE_FIELDS` if tuple-carrying). Emitted once per blocked attempt or
backstop restore.

| Field | Type | Notes |
| --- | --- | --- |
| `agent_role` | `str` | e.g. `implement`, `review`, `generate` |
| `workflow` | `str` | e.g. `fly-beads`, `spec-chain`, `reconcile` |
| `operation` | `Literal["create","edit","delete","rename","restore"]` | `restore` = backstop undid a mutation that slipped through; its `detail` names the inferred original operation |
| `path` | `str` | repo-relative posix path (resolved) |
| `destination_path` | `str \| None` | rename only |
| `layer` | `Literal["pre-write","backstop"]` | which enforcement layer acted |
| `bead_id` | `str \| None` | when inside a bead |
| `detail` | `str \| None` | reason / inferred-op note; agent-authored strings are escaped at render time |
| `timestamp` | `float` | `time.time()` default, as all events |

Rendering: `render_workflow_events` shows each as a yellow warning line as it
streams. A run with ≥1 block also gets exactly one end-of-run
`StepOutput(level="warning", metadata={"block_count": n})` summary (repeated
retries of the same write are individually recorded but summarized once —
spec edge case). A run with zero blocks emits nothing (FR-006).

## Run artifact: `.maverick/runs/<run-id>/protection-blocks.json`

Written by the owning workflow at completion **only when at least one block
occurred** (no empty files). Follows the `refuel-report.json` /
`land-report.json` precedent; persistence failure degrades to a warning and
never fails the run.

```json
{
  "schema_version": 1,
  "run_id": "3f2a9c1d",
  "workflow": "fly-beads",
  "generated_at": "2026-08-07T17:03:12Z",
  "blocks": [
    {
      "agent_role": "implement",
      "workflow": "fly-beads",
      "operation": "edit",
      "path": "CLAUDE.md",
      "destination_path": null,
      "layer": "pre-write",
      "bead_id": "bd-1234",
      "detail": "matched default rule: basename CLAUDE.md",
      "timestamp": 1786121809.412
    }
  ]
}
```

`blocks[*]` is exactly `BlockRecord.to_dict()` (see `data-model.md`) — one
projection, so the artifact and the event stream can never drift.

Spec-chain additionally checkpoints its accumulated records in
`spec-chain.json` (`ChainState.protection_blocks`) so blocks survive
mid-chain resume; on chain completion the same
`protection-blocks.json` artifact is written beside it.

## Explicit non-interactions (FR-005)

Block records never create assumption-ledger entries, never gain
`assumption_*` bd state keys, and are invisible to the land frontier gate and
`maverick review`. Nothing here enters any fix loop (Guardrail 10: separate
state slot).
