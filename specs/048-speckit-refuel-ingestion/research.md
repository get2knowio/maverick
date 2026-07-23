# Research: Spec Kit Ingestion Mode for Refuel

**Feature**: 048-speckit-refuel-ingestion | **Date**: 2026-07-23

All Technical Context unknowns resolved. Decisions below are grounded in codebase exploration (file:line references verified 2026-07-23).

## D1. Separate workflow vs. branching inside RefuelMaverickWorkflow

- **Decision**: New `SpeckitRefuelWorkflow(PythonWorkflow)` in `src/maverick/workflows/refuel_speckit/`; do not thread a speckit branch through `RefuelMaverickWorkflow`.
- **Rationale**: The existing refuel drives a Burr state machine (`workflows/refuel_maverick/burr_graph.py:66`) whose middle (briefing → decompose → validate → create_beads) is exactly what this feature replaces with a parser. Reusing it would mean stubbing 6 of 9 steps and entering `RefuelSquadron` (`squadron/refuel.py:31`) for nothing — the deterministic path needs no agent runtime at all. `library/actions/beads.create_beads` and `wire_dependencies` (`library/actions/beads.py:30`, `:109`) construct their own `BeadClient`, accept explicit `cwd`, and already implement `dry_run`, so a plain sequential `PythonWorkflow` covers everything. Repo convention is package-per-workflow (CLAUDE.md Debt Prevention #3).
- **Alternatives considered**: (a) Branch inside `RefuelMaverickWorkflow._run_impl` — rejected: two unrelated control flows in one 900-line module already near the refactor threshold. (b) Pure CLI-side implementation without a workflow (like `land`) — rejected: loses `ProgressEvent` rendering, checkpointing conventions, and run-metadata symmetry with classic refuel that FR-016 requires.

## D2. How task beads must be shaped for `fly` to consume them

- **Decision**: Pack complete work-unit markdown into each task bead's `description` — sections `## Task`, `## Acceptance Criteria`, `## File Scope`, `## Verification` — and put the Spec Kit task ID in the title (`T012: Create Entity model …`).
- **Rationale**: `fly` reads *only* `title` + `description`: the implementer prompt is built from them (`workflows/fly_beads/actions.py:308`), the reviewer passes `description` as the work-unit markdown (`:648-663`), and the AC-check re-parses `## Verification` commands out of the description (`:450-467`, executing only `rg/grep/cargo/make` commands). There is no separate acceptance-criteria field on a bead. Classic refuel's `(instructions or task)[:500]` truncation (`workflows/refuel_maverick/actions.py:845`) is a known lossy shortcut — the ingestion path must not repeat it.
- **Alternatives considered**: bead `state` key-value pairs for AC content — rejected: `fly` never reads state for prompt content; state is for machine metadata (see D4).

## D3. Phase-barrier dependency wiring without cross-products

- **Decision**: Wire edges as **sinks(phase N) × sources(phase N+1)**, where within a phase: consecutive non-`[P]` tasks form a serial chain (each depends on the nearest preceding non-`[P]` task), `[P]` tasks have no implicit intra-phase dependencies, and explicit `depends on Txxx` notes in task text add edges. *Sources* = tasks with no intra-phase blockers; *sinks* = tasks with no intra-phase dependents. Transitivity through the intra-phase chains yields the full barrier guarantee (clarification Q2) with far fewer edges than the cross-product.
- **Rationale**: `bd` enforces readiness from dependency edges (`bd ready` only returns unblocked beads — `beads/client.py:239`), so the graph shape directly controls `fly` execution order. The existing `wire_dependencies` action wires category-based structural deps (`library/actions/beads.py:109-222`) which don't express Spec Kit phases; a purpose-built edge computation in `speckit/build.py` emitting `BeadDependency` pairs is simpler than forcing phases into `BeadCategory` semantics. Edges are validated acyclic before creation (defense against pathological explicit notes).
- **Alternatives considered**: (a) Full cross-product barrier — rejected per clarification (O(n²) edges). (b) Per-phase milestone beads as barrier nodes — rejected: `BeadType` supports only `epic|task` (`beads/models.py:14`); synthetic no-op tasks would surface in `bd ready` and confuse `fly`.

## D4. Provenance encoding + delta re-run detection

- **Decision**: On the epic: `set_state(epic_id, {"speckit_feature": "<dir-name>"})` (mirrors the existing `flight_plan_name` attachment, `workflows/refuel_maverick/workflow.py:613`). On each task bead: `set_state(bead_id, {"speckit_task_id": "T012", "speckit_phase": "3", "speckit_parallel": "true|false"})`, plus label `speckit` at creation. Delta detection: find the open epic whose `speckit_feature` state matches the resolved feature dir (via `query("type=epic AND status=open")` + `show()` per candidate); enumerate its children (`BeadClient.children`, `client.py:359`) and their `speckit_task_id` states; ingest only unchecked tasks whose ID is not already present.
- **Rationale**: Task IDs are the stable identity across tasks.md growth (clarification Q1 — converge appends tasks). State keys survive title edits and are the established mechanism (`BeadDetails.state`, `beads/models.py:185`). Labels are creation-only (`client.py:157`) so mutable identity belongs in state.
- **Alternatives considered**: matching by title prefix `T###:` — kept as a human-readable convention but rejected as the identity mechanism (titles are truncated at 490 chars and editable).

## D5. Template version check source

- **Decision**: Read `speckit_version` from the target repo's `.specify/init-options.json`; compare against a declared supported range constant (initially `>=0.14,<0.15`) in `speckit/detect.py`. Outside range → fail upfront with `unsupported template version X, supported: Y` (FR-012). If the file or field is **absent** (older Spec Kit or hand-rolled layout), emit a warning and proceed to structural parsing — grammar-level errors then carry the divergence reporting.
- **Rationale**: This repo's own `.specify/init-options.json` carries `"speckit_version": "0.14.0"` — it is the version record Spec Kit vendors. Clarification Q4 chose fixed-grammar + upfront check; absent metadata is "unknown", not "outside range", and hard-failing every pre-metadata repo would block legitimate users whose artifacts parse cleanly.
- **Alternatives considered**: fingerprinting `.specify/templates/tasks-template.md` structure — rejected: templates are user-editable post-vendoring; version metadata is the intended contract.

## D6. tasks.md grammar (fixed, 0.14.x shape)

- **Decision**: Line-oriented grammar (full EBNF in `contracts/tasks-md-grammar.md`): phase headings `## Phase <n>: <title>`; task lines `- [ ]`/`- [x]` + `T\d{3,}` + optional `[P]` + optional `[US\d+]` + description; explicit deps parsed from `(depends on T012, T013)` / `depends on: …` in task text; file paths extracted by path-token heuristic (`\S+\.\S+` tokens containing `/`, matching `flight/parser.py` file-scope conventions); `## Dependencies*` section parsed for `US2: Depends on US1` story-level entries (expanded to story-sink → story-source edges). Unrecognized `- [ ]` lines inside a phase are hard parse errors (file:line, expected pattern, suggestion); prose/checkpoints/other headings are ignored.
- **Rationale**: Grammar is already exercised by fixtures `SAMPLE_TASKS_MD` / `SAMPLE_TASKS_MD_WITH_DEPS` (`tests/unit/beads/conftest.py:20`, `:50`) matching the vendored `tasks-template.md`. Strictness on task-shaped lines (vs. silently skipping) is what makes FR-012's "actionable error" and SC-002's "zero tasks dropped" testable.
- **Alternatives considered**: markdown-AST parsing (e.g., markdown-it) — rejected: new dependency for a line-oriented format; `flight/parser.py` proves regex-per-line is sufficient and debuggable here.

## D7. spec.md extraction for acceptance criteria

- **Decision**: From spec.md extract (a) `## Success Criteria` → `### Measurable Outcomes` bullets (`SC-\d+`) for the **epic** description, and (b) per user story `### User Story <n> …` → its `**Acceptance Scenarios**` numbered list, attached to task beads carrying the matching `[USn]` label (clarification Q3). Unlabeled tasks get task text + file scope only.
- **Rationale**: Both structures are fixed by the vendored `spec-template.md`; extraction reuses the `_split_h2_sections`/`_split_h3_sections` pattern from `flight/parser.py:145,:174`.
- **Alternatives considered**: copying global SCs onto every task — rejected per clarification (unverifiable per-bead noise).

## D8. Default verification content (no-enrichment path)

- **Decision**: Without `--enrich`, each task bead's `## Verification` section contains deterministic file-scope checks (existence checks derived from parsed file paths, e.g. `rg --files -g '<path>'`) plus any commands already present in the task text. With `--enrich`, a one-shot persona agent may replace/augment these with real test/lint commands.
- **Rationale**: `fly`'s AC-check executes only `rg/grep/cargo/make` commands from `## Verification` (`fly_beads/actions.py:450-467`) and classic refuel's `WorkUnitSpec` treats verification as mandatory non-empty (`workflows/refuel_maverick/models.py:80`); an empty section would silently weaken the fly gate. File-existence checks are the strongest claim derivable without judgment.
- **Alternatives considered**: defaulting to `make test` — rejected: target repos aren't guaranteed a Makefile; wrong-by-default commands would fail every AC check.

## D9. Enrichment agent shape

- **Decision**: `SpeckitEnrichmentAgent` added to `agents/personas.py` as a one-shot persona (`provider_tier = "generate"`), invoked per ingestion run (single batched prompt over all new tasks, returning verification commands per task ID); wired via `runtime_for_agent("generate", agents_config=config.agents)`. Opt-in via `--enrich`; any failure logs a structured warning and ingestion proceeds unenriched (FR-011). Enrichment runs **before** bead creation so dry-run can preview enriched output.
- **Rationale**: Persona agents are the established lightest LLM pattern — exactly how `DERIVE_VERIFICATION` uses `VerificationPropertiesAgent` (`workflows/refuel_maverick/workflow.py:363-392`); no squadron/pool needed. Tier resolution goes through `runtime_for_agent` / `binding_for_role` (`runtime/agent_factory.py:84`, `:50`; `"generate"` ∈ `KNOWN_ROLES`).
- **Alternatives considered**: per-task enrichment calls — rejected: N model calls for marginal quality; batching keeps cost O(1) per run.

## D10. Dry-run mechanics

- **Decision**: `--dry-run` CLI flag threads a `dry_run: bool` workflow input. The workflow runs every step through ingestion-plan construction and validation identically, passes `dry_run=True` to `create_beads`/`wire_dependencies` (which already return synthetic IDs without touching `bd` — `library/actions/beads.py:55`), skips `set_state`/epic-chaining/run-metadata writes, and renders the full would-be plan (epic, tasks, edges, skipped) via `emit_output` plus the result dict.
- **Rationale**: Reuses the actions' built-in dry-run seam rather than inventing a parallel preview path, which guarantees SC-005's "preview matches the subsequent real run" by construction. `land --dry-run` (`cli/commands/land.py:321`) establishes the print-plan-then-exit UX convention.
- **Alternatives considered**: CLI-side inline preview bypassing the workflow — rejected in D1 (loses parity guarantees and event rendering).

## D11. Mode auto-detection and dispatch at the CLI boundary

- **Decision**: In `cli/commands/refuel/_group.py`: resolve `<name>` against both `(cwd)/.maverick/plans/<name>/flight-plan.md` (classic) and `(cwd)/specs/` (speckit: exact dir name, `NNN` prefix, or exact name-suffix match — FR-001). Dispatch: `--speckit` forces speckit (error if unresolvable as speckit); both match without flag → error asking for disambiguation; exactly one match → dispatch accordingly, announcing the selected mode. Detection logic lives in `speckit/detect.py` (returns a typed resolution result), keeping the CLI thin.
- **Rationale**: Detection is needed before choosing which workflow to instantiate, so it must sit at the CLI boundary (Guardrail 7: CLI resolves, layers below receive). Shape check = directory contains `spec.md` + `tasks.md` (plan.md optional per spec Assumptions).
- **Alternatives considered**: a separate `maverick refuel-speckit` command — rejected: the spec's UX is one refuel verb with auto-detection.

## D12. Run metadata + fly handoff

- **Decision**: Write `RunMetadata(plan_name=<feature-dir-name>, epic_id=…, status="refueled")` via `maverick.runway.run_metadata.write_metadata` exactly as classic refuel does, so the CLI's existing `find_latest_run` hint (`cli/commands/refuel/_group.py:153-158`) prints `Next: maverick fly --epic <id>` unchanged (FR-016). Do **not** write `.maverick/plans/<name>/` work-unit files — bead descriptions are the single source of work-unit content on this path. Verify at implementation that `select_next_bead`'s `flight_plan_name` epic-state read (`library/actions/beads.py:342-347`) tolerates absence; if not, set `flight_plan_name` state to the feature dir name as a compatibility shim.
- **Rationale**: FR-016 requires follow-on commands to work unchanged; run metadata is the integration point. Duplicating work-unit files would create a second source of truth the delta path would have to reconcile.
- **Alternatives considered**: emitting `.maverick/plans/` files for parity — rejected: nothing on the fly path reads them for prompt content (D2), and tasks.md remains the user-facing source.

## D13. Failure-ordering and partial-creation reporting

- **Decision**: Strict validate-then-write ordering: resolution → version check → parse (all files) → ingestion-plan build (incl. duplicate-ID, unknown-dep-ref, cycle checks, delta filtering) must all succeed before the first `bd` write (FR-015). During creation, track created IDs; on midway failure, the error report lists created epic/bead IDs; recovery is the delta re-run (already-created task IDs are skipped next run — D4 makes interruption self-healing).
- **Rationale**: `create_beads` creates epic-then-children sequentially (`library/actions/beads.py:30-107`); there is no transaction in `bd`, so pre-validation + idempotent delta is the only route to "no partial trees on *validation* failure" plus graceful recovery from *runtime* failure.
- **Alternatives considered**: compensating deletes on failure — rejected: `bd` close ≠ delete, and destructive cleanup on a failure path violates fail-graceful expectations.
