# Data Model: Spec Kit Ingestion Mode for Refuel

**Feature**: 048-speckit-refuel-ingestion | **Date**: 2026-07-23

All new models are frozen Pydantic (per Guardrail 3), living in `src/maverick/speckit/models.py` unless noted. Existing bead models (`maverick.beads.models`) are reused unchanged.

## Parsing layer (`speckit/models.py`)

### SpeckitTask

One task line from tasks.md.

| Field | Type | Rules |
| --- | --- | --- |
| `task_id` | `str` | Matches `T\d{3,}`; unique within the feature (duplicate → parse error) |
| `description` | `str` | Full task text after markers; non-empty |
| `completed` | `bool` | `[x]` → True, `[ ]` → False |
| `parallel` | `bool` | `[P]` marker present |
| `story_id` | `str \| None` | From `[USn]` marker (e.g. `"US1"`) |
| `phase_number` | `int` | Owning phase (≥ 1) |
| `file_paths` | `tuple[str, ...]` | Path tokens extracted from description (may be empty) |
| `explicit_deps` | `tuple[str, ...]` | Task IDs from `depends on Txxx[, Tyyy]` notes; every referenced ID must exist (unknown → parse error) |
| `line_number` | `int` | 1-based source line in tasks.md (for error reporting and stable ordering) |

### SpeckitPhase

| Field | Type | Rules |
| --- | --- | --- |
| `number` | `int` | From `## Phase <n>:` heading; strictly increasing in file order |
| `title` | `str` | Heading text after the colon |
| `tasks` | `tuple[SpeckitTask, ...]` | In file order; a phase may be empty (warning, not error) |

### ParsedSpec

Extraction from spec.md.

| Field | Type | Rules |
| --- | --- | --- |
| `title` | `str` | From `# Feature Specification: <title>` (fallback: first H1) |
| `success_criteria` | `tuple[str, ...]` | `SC-\d+` bullets under Success Criteria → Measurable Outcomes |
| `story_scenarios` | `dict[str, tuple[str, ...]]` | Key `"USn"` → that story's Acceptance Scenarios items; stories without scenarios map to empty tuple |

### SpeckitFeature

Aggregate of one feature directory (output of the parse step).

| Field | Type | Rules |
| --- | --- | --- |
| `feature_dir` | `Path` | Absolute resolved `specs/NNN-name/` |
| `feature_name` | `str` | Directory basename (e.g. `048-speckit-refuel-ingestion`) |
| `spec` | `ParsedSpec` | Required (spec.md must exist) |
| `phases` | `tuple[SpeckitPhase, ...]` | Required (tasks.md must exist); ≥ 1 open task overall or ingestion fails ("nothing to ingest") |
| `story_deps` | `tuple[tuple[str, str], ...]` | `(dependent_story, blocker_story)` pairs from the Dependencies section (e.g. `("US2", "US1")`) |
| `has_plan` | `bool` | plan.md present (absence → note, not error) |

### TemplateCompatibility (`speckit/detect.py`)

| Field | Type | Rules |
| --- | --- | --- |
| `vendored_version` | `str \| None` | `speckit_version` from `.specify/init-options.json`; None if absent |
| `supported_range` | `str` | Constant, initially `>=0.14,<0.15` |
| `status` | `Literal["supported", "unsupported", "unknown"]` | `unsupported` → fail upfront; `unknown` → warn + structural parsing |

### FeatureResolution (`speckit/detect.py`)

CLI-boundary dispatch result.

| Field | Type | Rules |
| --- | --- | --- |
| `query` | `str` | The `<name>` argument as given |
| `speckit_dir` | `Path \| None` | Resolved feature dir (exact name / `NNN` prefix / exact suffix); multiple candidates → `AmbiguousFeatureError` listing them |
| `flight_plan_path` | `Path \| None` | Classic `.maverick/plans/<name>/flight-plan.md` if it exists |
| `mode` | `Literal["speckit", "classic", "ambiguous", "unresolved"]` | Both non-None without `--speckit` → `ambiguous` |

## Ingestion-plan layer (`speckit/build.py`)

### PlannedBead

| Field | Type | Rules |
| --- | --- | --- |
| `task_id` | `str` | Source task ID (epic uses sentinel `"EPIC"`) |
| `definition` | `BeadDefinition` (existing) | `title` = `"T012: <desc>"` (≤ 490 chars) for tasks, feature title for the epic; `description` = full work-unit markdown per contracts/bead-encoding.md; `labels` include `"speckit"` |
| `state` | `dict[str, str]` | Post-creation `set_state` payload: `speckit_task_id`, `speckit_phase`, `speckit_parallel` (task) or `speckit_feature` (epic) |

### IngestionPlan

Complete, validated, side-effect-free description of one run (the dry-run rendering and the real run consume this same object — parity by construction).

| Field | Type | Rules |
| --- | --- | --- |
| `feature` | `SpeckitFeature` | Source |
| `epic` | `PlannedBead \| None` | None on delta runs (existing epic adopted) |
| `existing_epic_id` | `str \| None` | Set on delta runs |
| `new_tasks` | `tuple[PlannedBead, ...]` | Open tasks not previously ingested, in execution-safe order |
| `skipped_completed` | `tuple[str, ...]` | Task IDs checked `[x]` |
| `skipped_existing` | `tuple[str, ...]` | Task IDs already ingested under the epic (delta) |
| `edges` | `tuple[tuple[str, str], ...]` | `(blocker_task_id, blocked_task_id)` pairs; validated acyclic; on delta runs may reference existing bead IDs via `existing_task_map` |
| `existing_task_map` | `dict[str, str]` | `task_id → bead_id` for previously ingested tasks (delta edge wiring) |

**Validation rules enforced at build time (before any write — FR-015)**: unique task IDs; explicit deps reference known IDs; dependency graph acyclic; ≥ 1 new task OR delta no-op flagged; story labels referenced by tasks exist in spec (missing story → warning, scenarios omitted).

### Derived dependency edges (from clarification Q2)

For each phase `p` (in order):
1. **Intra-phase serial chain**: each non-`[P]` task depends on the nearest preceding non-`[P]` task in `p`.
2. **Explicit notes**: each `explicit_deps` entry adds `(dep, task)`.
3. **Phase barrier**: `sinks(p) × sources(p+1)` — sinks = tasks in `p` with no intra-phase dependents; sources = tasks in `p+1` with no intra-phase blockers. Transitivity through chains yields the full barrier.
4. **Story deps**: for `(US_b, US_a)` in `story_deps`, add sink-of-`US_a` × source-of-`US_b` edges only where the blocked task is not already reachable from the blocker via edges from rules 1–3 (graph reachability check, computed before cycle validation).

On delta runs, edges whose blocker is an already-ingested task resolve through `existing_task_map`; edges whose blocker is a *completed* (skipped) task are dropped (already satisfied).

## Workflow layer (`workflows/refuel_speckit/models.py`)

### SpeckitRefuelResult

Dataclass mirroring `RefuelMaverickResult.to_dict()` conventions (`workflows/refuel_maverick/models.py:225`).

| Field | Type |
| --- | --- |
| `feature_name` | `str` |
| `epic_id` | `str` (real or `dry-run-epic`) |
| `created_bead_ids` | `list[str]` |
| `skipped_completed` / `skipped_existing` | `list[str]` |
| `edge_count` | `int` |
| `delta_run` | `bool` |
| `dry_run` | `bool` |
| `enriched` | `bool` |
| `warnings` | `list[str]` |

## State transitions

```
tasks.md task:  [ ] unchecked ──ingest──▶ bead (open) ──fly──▶ bead (closed)
                [x] checked   ──ingest──▶ skipped_completed (no bead)
re-run:         unchecked + bead exists ─▶ skipped_existing (no new bead)
                unchecked + no bead     ─▶ new bead under existing epic (delta)
epic:           first run → created + chained behind open-epic tail
                delta run → adopted (existing_epic_id); no new epic, no re-chaining
```

## Relationships

```
SpeckitFeature 1──* SpeckitPhase 1──* SpeckitTask
SpeckitFeature 1──1 ParsedSpec (story_scenarios keyed by SpeckitTask.story_id)
IngestionPlan 1──* PlannedBead ──1 BeadDefinition (existing model)
IngestionPlan edges ──▶ BeadDependency (existing model) at execution time
epic bead 1──* task beads (bd parent/child) ──▶ state carries speckit_* provenance
```
