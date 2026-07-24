# Data Model: Headless Spec Kit Chain

All models are Pydantic `BaseModel` (persisted) or frozen dataclasses (in-memory
results), per constitution Principle VI. Module homes are shown per entity.

## ChainStep (enum) — `workflows/spec_chain/constants.py`

Ordered: `SPECIFY → CLARIFY → PLAN → TASKS → ANALYZE`. The order is the single source
of truth for FR-002/FR-008 gating; `next_step(state)` derives from it.

## ChainState — `workflows/spec_chain/models.py`, persisted to `.maverick/runs/<run-id>/spec-chain.json`

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | `int` | starts at 1; guards future migrations |
| `run_id` | `str` | matches the `.maverick/runs/` directory |
| `feature` | `str` | user-supplied feature name (resolution key for resume) |
| `feature_dir` | `str \| None` | `specs/NNN-<feature>` allocated by specify (R8); `None` until specify lands |
| `prd_path` | `str` | user-supplied PRD path (original, user-checkout relative) |
| `prd_digest` | `str` | sha256 of PRD content at chain start; resume warns on mismatch |
| `workspace_path` | `str` | hidden workspace root (per-feature: `~/.maverick/workspaces/<project-slug>/spec-chain/<feature>/`) |
| `status` | `Literal["running","halted","completed","failed"]` | terminal: `completed`/`failed`; `halted` is resumable |
| `steps` | `dict[ChainStep, StepRecord]` | one record per attempted step |
| `clarify_decisions` | `list[ClarifyDecision]` | filed decisions (audit copy; ledger beads are canonical) |
| `remediation_bead_ids` | `list[str]` | created finding beads |
| `started_at` / `updated_at` | `datetime` | ISO-8601 |

**State transitions**: `running → halted` (step failure/interrupt after checkpoint);
`running → completed` (analyze step finished, findings recorded); `halted → running`
(resume); `running → failed` (unrecoverable, e.g. workspace creation impossible).
Invariant: a step may be `in_progress` only if all prior steps are `succeeded`.

## StepRecord — nested in ChainState

| Field | Type | Notes |
|-------|------|-------|
| `step` | `ChainStep` | |
| `status` | `Literal["pending","in_progress","succeeded","failed","skipped"]` | `skipped` only for analyze-after-halt reporting |
| `attempts` | `int` | tenacity-visible count |
| `artifacts` | `list[str]` | feature-dir-relative paths landed by this step |
| `landed` | `bool` | artifacts synced to user checkout (FR-016/FR-020 gate) |
| `error` | `str \| None` | classified failure summary |
| `started_at` / `finished_at` | `datetime \| None` | |

## ClarifyDecision — frozen dataclass, `workflows/spec_chain/models.py`

The convergence type for both answering paths (R2).

| Field | Type | Notes |
|-------|------|-------|
| `question` | `str` | verbatim question text |
| `adopted_answer` | `str` | recommended option or informed default |
| `alternatives` | `tuple[str, ...]` | options not chosen (may be empty on fallback path) |
| `severity` | `Severity` (spec 049) | harness-assessed; default `LOW` (FR-007a) |
| `severity_defaulted` | `bool` | true when no clear signal |
| `path` | `Literal["interception","non_interactive"]` | provenance |
| `ledger_bead_id` | `str \| None` | filled after filing |

Maps 1:1 onto the existing `AssumptionPayload` (question, adopted_answer, alternatives,
severity, severity_defaulted) when filed via `record_standalone_assumption` (R5).

## StepReport — Pydantic, structured-output schema for `SpecChainAgent` (R9)

| Field | Type | Notes |
|-------|------|-------|
| `status` | `Literal["completed","blocked","failed"]` | agent's claim; filesystem is ground truth |
| `artifacts` | `list[str]` | paths the agent believes it wrote |
| `questions` | `list[ReportedQuestion]` | clarify only: question/adopted/alternatives |
| `findings` | `list[ReportedFinding]` | analyze only |
| `detail` | `str` | free-text summary / failure reason |

`ReportedQuestion`: `question, adopted_answer, alternatives`. `ReportedFinding`:
`title, category, severity_hint, location, summary`.

## AnalyzeFinding → remediation bead — `workflows/spec_chain/models.py` + bead state

Bead shape (R6): `BeadType.TASK`, no parent, label `spec-remediation`.

| Bead state key | Value |
|----------------|-------|
| `speckit_feature` | `<NNN-feature>` directory name (adoption key, matches refuel delta key) |
| `remediation_source` | `"spec-chain:analyze"` |
| `finding_fingerprint` | sha256 of normalized `title + location` (idempotency) |

Adoption (refuel --speckit post-ingest step): query open beads where
`speckit_feature == feature` and unparented → `update_parent(bead, epic)` or
dependency-edge fallback + `adopted_by_epic` state stamp.

## Standalone ledger entry — extension of spec-049 bead shape (R5)

Identical to `record_assumption` output except: no parent epic;
`source_bead` state key replaced by `source_ref = "spec-chain:clarify"`;
`assumption_owner_spec` set directly to the feature dir name. All existing readers
(`per_spec_counts`, `open_blocking_entries`, `maverick review`) operate on
labels/state keys and remain unchanged.

## SpecChainReport — frozen dataclass returned to the CLI (FR-019)

`feature_dir, status, steps (per-step outcome + timing), ledger_entry_count,
remediation_bead_count, resume_hint (str | None)`. Rendered by `cli/commands/spec.py`
via Rich (sequential completion lines per CLI output rules).

## Validation rules (from requirements)

- PRD: must exist, be readable, non-empty (FR-001) — validated before workspace creation.
- Feature name: non-empty, filesystem-safe slug; collision with an existing *completed*
  spec dir or a foreign directory → error (FR-015); matching *halted* chain → resume (FR-020).
- Step gating: `plan` requires `clarify.status == succeeded`; `tasks` requires `plan`;
  `analyze` requires `tasks` (FR-008). Enforced by the workflow, not prompts.
- Landing: a step's `landed=True` only after atomic sync succeeds; `ChainState` is
  checkpointed after landing (ordering guarantees resume never trusts unlanded work).
