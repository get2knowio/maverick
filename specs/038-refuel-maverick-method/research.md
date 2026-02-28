# Research: Refuel Maverick Method

**Branch**: `038-refuel-maverick-method` | **Date**: 2026-02-27

## R1: Agent Invocation Strategy — StepExecutor vs GeneratorAgent

**Decision**: Use StepExecutor with Pydantic `output_schema` for structured decomposition output.

**Rationale**: StepExecutor integrates with the workflow's event system (emits `AgentStreamChunk` for streaming), supports `output_schema` validation via `model_validate()`, and is already injected into PythonWorkflow subclasses. GeneratorAgent (used by DependencyExtractor) is simpler but doesn't support structured output validation or streaming events.

**Alternatives considered**:
- GeneratorAgent: Simpler, but returns raw text requiring manual parsing. No streaming events. Would require raw JSON parsing instead of Pydantic validation.
- Custom MaverickAgent: Overkill — decomposition doesn't need multi-turn tool use, just a single prompt with structured output.

## R2: Decomposition Output Schema

**Decision**: Define a `DecompositionOutput` Pydantic model containing a list of `WorkUnitSpec` models (lightweight input specs), then convert to full `WorkUnit` models after validation.

**Rationale**: The agent produces a structured list of work unit specifications. Using Pydantic `output_schema` with StepExecutor gives automatic validation. A separate `WorkUnitSpec` model (subset of WorkUnit fields) avoids requiring the agent to produce loader-specific fields like `source_path`.

**Alternatives considered**:
- Direct WorkUnit models: WorkUnit has `source_path` and `flight_plan` fields that the agent shouldn't need to produce. A dedicated output model is cleaner.
- Raw dict parsing: Loses type safety and validation guarantees.

## R3: Codebase Context Gathering

**Decision**: Read in-scope files directly using `pathlib.Path.read_text()` (via `asyncio.to_thread`), not `gather_local_review_context`.

**Rationale**: `gather_local_review_context` is designed for PR review — it computes diffs, extracts commit messages, and builds `PRMetadata`. The decomposition workflow needs raw file contents for files listed in `in_scope`, not diff-based context. Direct file reading is simpler and more appropriate.

**Alternatives considered**:
- `gather_local_review_context`: Returns diffs and PR metadata, not raw file contents. Would require significant adaptation.
- `AsyncGitRepository.show()`: Could read files at specific revisions, but we want current working directory state, not a git ref.

## R4: Bead Creation from Work Units

**Decision**: Reuse existing `create_beads` and `wire_dependencies` actions from `maverick.library.actions.beads`, adapting the input dict format to match what these functions expect.

**Rationale**: These actions already handle BeadClient interaction, dry-run mode, synthetic ID generation, and error collection. The work_definitions format (list of dicts with `title`, `bead_type`, `priority`, `category`, `description`) is flexible enough to accommodate work unit data.

**Alternatives considered**:
- Direct BeadClient usage: Would duplicate error handling, dry-run logic, and created_map tracking already in the actions.
- New bead actions: Unnecessary duplication of existing, tested logic.

## R5: Dependency Wiring from WorkUnit depends_on

**Decision**: Map WorkUnit `depends_on` fields directly to bead dependencies using the `created_map` (title → bd_id mapping). No need for DependencyExtractor — dependencies are explicit in the WorkUnit model.

**Rationale**: Unlike RefuelSpeckit (which extracts inter-story dependencies from free-text via an agent), the maverick method has explicit `depends_on` references in each WorkUnit. The dependency graph is already structured.

**Alternatives considered**:
- DependencyExtractor agent: Unnecessary — dependencies are already explicit, not inferred from text.
- Structural deps (FOUNDATION→stories→CLEANUP): The speckit pattern uses phase-based structural deps, but work units have explicit per-unit dependencies that are more precise.

## R6: CLI Command Naming

**Decision**: Name the file `maverick_cmd.py` to avoid Python import collision with the `maverick` package itself. The Click command name will be `maverick` (no suffix).

**Rationale**: Python cannot have a module named `maverick.py` inside a package that imports from `maverick.*`. The `_cmd` suffix is a common convention for disambiguation.

**Alternatives considered**:
- `decompose.py`: Doesn't match the CLI name pattern (`maverick refuel maverick`).
- `method_maverick.py`: Unclear naming.

## R7: Work Unit File Naming

**Decision**: Use `{sequence:03d}-{id}.md` pattern (e.g., `001-add-models.md`), matching the existing `WorkUnitFile` loader's glob pattern `[0-9][0-9][0-9]-*.md`.

**Rationale**: `WorkUnitFile.load_directory()` already expects this pattern and sorts by sequence number. Using it ensures round-trip compatibility (write → load).

**Alternatives considered**: None — the existing convention is clear and mandatory for `load_directory()` compatibility.

## R8: Agent Retry Strategy

**Decision**: Use tenacity `AsyncRetrying` with `stop_after_attempt(3)` (initial + 2 retries), `wait_exponential(multiplier=1, min=1, max=10)`, retrying only on transient errors (API timeouts, rate limits). Fail immediately on `OutputSchemaValidationError`.

**Rationale**: Matches the project's canonical retry pattern (tenacity, Guardrail #8). The 2-retry clarification from the spec maps to `stop_after_attempt(3)` in tenacity terminology (1 initial + 2 retries).

**Alternatives considered**:
- No retries: Too fragile for an agent call that may take 30+ seconds.
- Retry on all errors: Would retry on validation errors where the agent fundamentally misunderstood the schema — wasteful.

## R9: Success Criteria Coverage Validation

**Decision**: Implement as a post-decomposition validation step that checks each flight plan `SuccessCriterion` has at least one WorkUnit `AcceptanceCriterion` with a matching `trace_ref`. Log warnings for uncovered criteria but do not block.

**Rationale**: Spec clarification specifies warning-level enforcement. The `trace_ref` field on `AcceptanceCriterion` uses `SC-###` format, which maps directly to the index of `SuccessCriterion` entries in the flight plan.

**Alternatives considered**:
- Blocking validation: Rejected in clarification — some criteria are cross-cutting.
- No validation: Would miss a key quality signal.

## R10: Dependency Graph Validation

**Decision**: Implement topological sort using the existing `ExecutionOrder` and `ExecutionBatch` models from `maverick.flight.models`. These already provide `from_work_units()` class method that performs cycle detection and topological sorting.

**Rationale**: The models are already built for exactly this purpose. `ExecutionOrder.from_work_units(units)` raises on circular dependencies and produces sorted batches with parallel group assignments.

**Alternatives considered**:
- Custom graph validation: Unnecessary — the model already does this.
- Skip validation: Would allow invalid dependency graphs to reach bead creation, causing confusing errors.
