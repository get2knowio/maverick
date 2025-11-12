# Research: Maverick CLI

Date: 2025-11-10
Feature: Maverick CLI (Temporal orchestration front door)
Branch: 001-maverick-cli

## Decisions & Rationale

### 1. CLI Framework Choice
- **Decision**: Adopt `click` for the initial implementation.
- **Rationale**: Provides decorators, parameter types, unified help formatting, and immediate extensibility (subcommands, shared options). Sets foundation for future richer UX (integration with `rich` or migration to `textual` for a TUI) without rewriting parsing. Dependency cost is minimal and justified under Simplicity First because it prevents hand-rolled parsing/validation complexity as command surface grows.
- **Alternatives Considered**:
  - `argparse`: Zero extra dependency but quickly becomes verbose for multiple commands/options; less ergonomic for nested commands.
  - `typer`: High developer ergonomics but an additional abstraction layer over Click; auto-magic behaviors less transparent for fine-grained CLI contract testing.
  - `rich` alone: Enhances output styling but does not handle argument parsing.
  - `textual`: Powerful TUI framework; higher complexity; deferred until we implement interactive dashboards (future run/status live pane). Feasible future integration by wrapping Click commands.
  - `prompt_toolkit`: Excellent for interactive shells; heavier than current needs.

### 2. Multi-task Workflow Start Interface
- **Decision**: Use existing workflow entry point as previously implemented (name resolved from orchestration module) and pass array of TaskDescriptors; avoid introducing a new dataclass layer if stable model already exists.
- **Rationale**: Minimizes duplication; preserves replay compatibility; adheres to Simplicity First.
- **Alternatives**:
  - New wrapper dataclass: Adds maintenance overhead; risk of divergence.
  - REST proxy endpoint: Adds infrastructure complexity prematurely.

### 3. Status Polling Mechanism
- **Decision**: Use workflow queries `get_progress` and `get_task_results` via workflow handle.
- **Rationale**: Already implemented, deterministic, avoids custom activities. Query latency acceptable for 2s poll.
- **Alternatives**:
  - Separate status Activity: Redundant; extra latency; unnecessary complexity.
  - Event sourcing log tail: Requires new persistence layer (violates storage constraints).

### 4. Metric Emission Format
- **Decision**: Emit metrics in JSON mode as top-level keys in output object and in human mode as prefixed lines `METRIC name=value`.
- **Rationale**: Human readability + machine parsability. Prefix allows easy grep. JSON embedding aligns with scriptability.
- **Alternatives**:
  - Dedicated metrics file: Adds IO & state.
  - Prometheus exposition: Overkill for local dev CLI.

### 5. `--compact` Status Output
- **Decision**: Single-line summary per refresh: `taskIndex/total phase=<phase or -> status=<running|paused> elapsed=<s> failure=<msg-if-any>`.
- **Rationale**: Keeps long runs clean. Easy to parse. Avoids multi-line flooding.
- **Alternatives**:
  - TUI (curses): Complexity and reduced portability.
  - Spinner-only: Hides detail; poor observability.

### 6. TaskDescriptor Definition (CLI side)
- **Decision**: Reuse existing workflow `TaskDescriptor` model when compatible; supplement transient CLI-only fields (`return_to_branch`, `interactive`, `model_prefs`) via an adapter function before workflow invocation.
- **Rationale**: Reduces data model proliferation; centralizes validation; easier test coverage.
- **Alternatives**:
  - Separate CLI dataclass: Increases conversion overhead.
  - Plain dicts: Loses invariant validation.

### 7. Ordering Implementation
- **Decision**: Parse numeric prefix from directory names under `specs/` using regex `^(\d+)-`; sort by int(prefix), then lexicographic file name.
- **Rationale**: Matches spec requirement; robust to zero padding.
- **Alternatives**:
  - Natural sort of full path: Would conflate prefix semantics.

### 8. Dirty Working Tree Check
- **Decision**: Reuse `utils.git_cli` to run `git status --porcelain`; dirty if output non-empty.
- **Rationale**: Already tolerant decoding; avoids rewriting logic.
- **Alternatives**:
  - Direct pygit2 dependency: Additional lib; unnecessary; Simplicity First.

### 9. Branch Name Hint Derivation
- **Decision**: Slug: replace non-alphanum with `-` from `task_id`, truncate to 50 chars, lower-case.
- **Rationale**: Git branch naming safety; deterministic.
- **Alternatives**:
  - Hash-based names: Less human-friendly.

### 10. Interrupt Handling
- **Decision**: Capture SIGINT; gracefully stop polling loop, print final known progress and instruct `maverick status <id>` for continuation.
- **Rationale**: Non-destructive; workflow continues.
- **Alternatives**:
  - Signal to workflow to cancel: Not requested; reduces flexibility.

### 11. JSON Output Stability
- **Decision**: Use ordered dict (insertion order has been guaranteed since Python 3.7) with fixed key order for top-level outputs.
- **Rationale**: Predictability for scripts.
- **Alternatives**:
  - Arbitrary order: Harder for diffing & contract tests.

### 12. Poll Latency Measurement
- **Decision**: Measure `workflow.now()` alternative not available in CLI; use `time.monotonic()` (CLI not a workflow) for poll round-trip latency; aggregate p95 at end if run completes.
- **Rationale**: Monotonic appropriate for duration; determinism not required outside workflow.
- **Alternatives**:
  - `time.time()`: Subject to system clock changes.

## TUI Candidate Research (for future phases)

- Textual (textualize.io)
  - Pros: Modern TUI, asyncio-native, excellent layout/widgets, integrates with Rich; good for dashboards and live updates.
  - Cons: Higher complexity; not needed for simple streaming yet.
- Rich
  - Pros: Beautiful styled output, tables, progress bars; can enhance Click output immediately.
  - Cons: Not a TUI framework by itself.
- prompt_toolkit
  - Pros: Great for REPLs and advanced input handling; autocompletion.
  - Cons: Heavier than we need; focus on interactive shells vs dashboards.
- urwid/curses
  - Pros: Mature; low-level control.
  - Cons: Lower developer velocity; more work to produce modern UX.

Decision trajectory: Start with Click + simple stdout; optionally add Rich for styling; migrate to Textual when a true TUI is warranted (multi-pane status, controls). 

## Open Clarifications Resolved
All previously flagged NEEDS CLARIFICATION items now have Decisions above. No remaining unknowns block Phase 1.

## Risk Assessment
- Adding dependency (`click`) introduces version maintenance; mitigated by pinning in `pyproject.toml`.
- Potential mismatch between CLI TaskDescriptor and workflow expectation; adapter function plus unit tests ensure stability.
- Polling efficiency: 2s interval acceptable; adjust if p95 > requirement.
- Future TUI (Textual) could necessitate refactor of streaming loop; isolation of streaming logic behind a function keeps migration cost low.

## Future Considerations (Out of Scope)
- `maverick list` to enumerate historical runs.
- `--cancel <workflow-id>` to terminate workflows.
- Rich formatting (`rich`) and eventual multi-pane TUI (`textual`) for live status.
- Metrics export to Prometheus via sidecar.

## References
- Temporal Constitution sections IV, V for determinism & logging separation.
- Feature spec FR-001..FR-013 and SC-001..SC-006.
