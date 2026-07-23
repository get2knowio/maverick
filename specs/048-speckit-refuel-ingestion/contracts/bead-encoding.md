# Contract: Bead encoding of Spec Kit artifacts

**Feature**: 048-speckit-refuel-ingestion

How ingestion encodes Spec Kit content into beads. This is a public interface: `fly` consumes it (prompts read `title` + `description`; AC-check parses `## Verification` from `description`), and delta re-runs depend on the state keys.

## Epic bead

| Facet | Value |
| --- | --- |
| type / priority | `epic` / 1 |
| title | Feature title from spec.md (fallback: feature dir name) |
| labels (at creation) | `speckit` |
| description | Markdown: feature summary line, `## Success Criteria` (SC bullets from spec.md), `## Source` (repo-relative feature dir path) |
| state (post-creation) | `speckit_feature=<dir basename>` (delta-run lookup key); `flight_plan_name=<dir basename>` only if implementation verification shows `select_next_bead` requires it (D12) |
| chaining | blocked-by tail of existing open-epic chain, exactly as classic refuel (`workflow.py:625-654` pattern) — first run only |

## Task bead

| Facet | Value |
| --- | --- |
| type / priority | `task` / 2 |
| parent | the feature's epic (`parent_id` at creation) |
| title | `"<task_id>: <description>"`, truncated to 490 chars |
| labels (at creation) | `speckit` |
| state (post-creation) | `speckit_task_id=T###` (delta identity — REQUIRED), `speckit_phase=<n>`, `speckit_parallel=true\|false` |

### Task bead `description` (work-unit markdown consumed by fly)

```markdown
## Task
<full task text from tasks.md> (Phase <n>: <phase title>[, Story USn][, parallel-eligible])

## Acceptance Criteria
- <task text restated as the completion claim>
- <story USn acceptance scenarios, verbatim, if task is story-labeled>   # clarification Q3

## File Scope
- <extracted file path>  (section omitted when no paths parsed)

## Verification
- <deterministic file-scope checks (rg-based existence checks)>
- <commands found verbatim in task text, if any>
- <enrichment-supplied commands, when --enrich succeeded>
```

Constraints:
- `## Verification` is never empty (fly's AC-check gate executes only `rg/grep/cargo/make` commands from it — D8).
- No content is exclusive to bead state: everything an implementer needs is in `description` (fly reads nothing else — D2).
- Description is NOT truncated (unlike classic refuel's 500-char cap).

## Dependency edges

`BeadDependency(blocker_id, blocked_id, dep_type=BLOCKS)` via `BeadClient.add_dependency`, from `IngestionPlan.edges`:

1. intra-phase serial chain between consecutive non-`[P]` tasks;
2. explicit `depends on T###` notes;
3. phase barrier: sinks(phase n) × sources(phase n+1);
4. story-dependency section pairs (where not already implied).

Delta runs: blocker IDs of previously ingested tasks resolve via `existing_task_map` (state lookup); edges from *completed* tasks are dropped (already satisfied). Graph validated acyclic before any write.

## Delta identity rules

- Epic lookup: open epic (`query("type=epic AND status=open")`) whose state `speckit_feature` equals the resolved feature dir basename. Zero → fresh run. One → delta run. Multiple → error (corrupt state; message lists epic IDs).
- Task identity: child bead state `speckit_task_id` == tasks.md task ID. Title text is display-only and carries no identity.

## Run metadata

`RunMetadata(run_id, plan_name=<feature dir basename>, epic_id, started_at, completed_at, status)` written to `<cwd>/.maverick/runs/<run_id>/metadata.json` on real runs only — statuses `refueling` → `refueled`/`failed`, matching classic refuel so `find_latest_run`-based hints and `brief` work unchanged (FR-016).
