# Research Findings

- **Decision**: Parse `tasks.md` phases by scanning for headings matching `## Phase <ordinal>: <label>` and capturing subsequent checklist bullets until the next phase heading.
  - **Rationale**: Aligns with FR-002, keeps parsing deterministic inside an activity, and matches current Speckit template structure. Enables easy detection of missing or empty phases for edge cases.
  - **Alternatives considered**: Using a full Markdown parser (python-markdown, mistletoe) was rejected because it adds heavy dependencies and variability that complicates determinism and testing.

- **Decision**: Represent parsed data with `PhaseDefinition`, `TaskItem`, `PhaseExecutionContext`, `PhaseResult`, and `WorkflowCheckpoint` dataclasses stored within workflow state.
  - **Rationale**: Mirrors spec entity list, keeps workflow state strongly typed, and allows activity responses to specify `result_type` for Temporal serialization requirements.
  - **Alternatives considered**: Passing plain dicts sacrifices type checking and increases risk of serialization bugs; using Enums violates Temporal serialization guidance.

- **Decision**: Execute `speckit.implement` via an activity that shells out with `asyncio.create_subprocess_exec`, capturing stdout/stderr with `errors="replace"`, enforcing configurable timeout/backoff.
  - **Rationale**: Meets FR-004/FR-009, leverages existing CLI, and complies with Error Handling requirements from the constitution.
  - **Alternatives considered**: Calling Speckit as a Python library is unsupported; synchronous subprocess calls would block event loop and complicate timeout handling.

- **Decision**: After each phase, the activity reloads `tasks.md` from disk (or provided content), verifies all targeted tasks marked `- [X]`, and produces a signed hash (`blake2b`) of the file stored in `PhaseResult` and `WorkflowCheckpoint`.
  - **Rationale**: Implements FR-005/FR-007, provides idempotent resume capability, and uses deterministic hashing available across platforms.
  - **Alternatives considered**: Trusting CLI output without re-reading the file risks drift; using non-cryptographic hashes (e.g., `hash()`) is non-deterministic between runs.

- **Decision**: Workflow resume compares stored checkpoint hash with live file; on mismatch, it treats live content as authoritative, recalculates checkpoints for completed phases, and continues with earliest incomplete phase.
  - **Rationale**: Fulfills Clarification guidance and FR-008, keeps workflow deterministic by recomputing derived state inside activities, and avoids manual operator steps.
  - **Alternatives considered**: Failing the workflow on hash mismatch contradicts clarified requirement; attempting in-workflow diffing violates determinism.

- **Decision**: Log activity progress with `src/utils/logging.get_structured_logger` and workflow milestones with `workflow.logger`, emitting phase start/completion events and persisting structured `PhaseResult` JSON per SC-003.
  - **Rationale**: Satisfies Observability mandates, provides machine-readable audit trail, and keeps workflows deterministic.
  - **Alternatives considered**: Using module-level loggers inside workflows violates the constitution; raw CLI stdout lacks structure for consumers.
