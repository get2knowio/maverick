# Feature Specification: Typed Agent Output Contracts

**Feature Branch**: `030-typed-output-contracts`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Evolve Maverick's agent output system from opaque string-based results to typed Pydantic output contracts."

## Clarifications

### Session 2026-02-21

- Q: What parsing strategy should `validate_output` use — extract JSON from markdown code blocks, require pure JSON, or a hybrid approach? → A: Extract JSON from markdown code blocks, then validate with Pydantic. No raw-text fallbacks (no regex fallback for JSON embedded in prose). If no code block is found or JSON is invalid, return a structured validation error.
- Q: How should the `ReviewResult` naming collision (Pydantic model vs. frozen dataclass) be resolved for the contracts module? → A: Rename the dataclass version (from `review_models.py`) to `GroupedReviewResult` to reflect its grouped-findings structure. The Pydantic `ReviewResult` keeps its name.
- Q: Should frozen dataclass output types (`Finding`, `FindingGroup`, `GroupedReviewResult`, `FixOutcome`) be converted to Pydantic models or left as dataclasses? → A: Convert all output dataclasses to Pydantic models for uniform `model_dump_json()` serialization, schema validation, and consistent `validate_output` support.
- Q: What level of detail should the new `FixerResult` model capture? → A: Lightweight — `success: bool`, `summary: str`, `files_mentioned: list[str]`, `error_details: str | None`. The file list is agent best-effort (not authoritative); workflows rely on git diff for ground truth.
- Q: What should be explicitly out of scope for this feature? → A: Three items excluded: (1) agent input contracts/context types, (2) changes to agent system prompts or Claude prompting strategy, (3) converting the `AgentResult` frozen dataclass itself to Pydantic.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Eliminate Regex JSON Extraction from Agent Outputs (Priority: P1)

When a workflow runs a code review or fix cycle, the system currently prompts Claude to embed JSON in free text and then uses regex to extract it. This is fragile — malformed JSON, extra text, or unexpected formatting silently degrades results. A developer maintaining Maverick should be able to trust that agent outputs are validated structured data, not best-effort regex parses.

**Why this priority**: Regex-based extraction is the single most fragile point in the agent output pipeline. It causes silent data loss (findings that fail to parse are silently dropped) and makes debugging difficult. Replacing it with validated structured output eliminates an entire class of runtime errors.

**Independent Test**: Can be tested by running the code reviewer and simple fixer agents against sample diffs and verifying that all outputs are validated Pydantic models — no regex extraction in the code path.

**Acceptance Scenarios**:

1. **Given** a code review agent processes a diff, **When** it produces findings, **Then** the findings are returned as validated `ReviewFinding` Pydantic model instances without regex extraction from free text.
2. **Given** a simple fixer agent processes findings, **When** it reports outcomes, **Then** the outcomes are returned as validated `FixOutcome` model instances without regex extraction from free text.
3. **Given** an agent produces output that does not conform to the expected schema, **When** the output is parsed, **Then** the system returns a validation error with details about what failed — not an empty list.

---

### User Story 2 - Replace FixerAgent's Opaque Output with a Typed Contract (Priority: P2)

The `FixerAgent` returns `AgentResult` with an opaque `output: str` field. Downstream workflow code cannot programmatically determine what the fixer actually did without parsing free text. A workflow author should receive a structured result describing which files were changed and whether fixes were applied.

**Why this priority**: The FixerAgent is used in validation fix loops where knowing what changed is important for iteration decisions. A typed contract enables workflows to make informed retry/abort decisions instead of blindly re-running validation.

**Independent Test**: Can be tested by running the FixerAgent against a sample fix prompt and verifying the result is a typed model with structured file change information.

**Acceptance Scenarios**:

1. **Given** a `FixerAgent` successfully applies a fix, **When** the result is returned, **Then** it includes structured information about which files were modified and what was changed.
2. **Given** a `FixerAgent` fails to apply a fix, **When** the result is returned, **Then** it includes structured error information — not just a raw text dump.
3. **Given** downstream workflow code receives a `FixerAgent` result, **When** it inspects the result, **Then** it can access typed fields without string parsing.

---

### User Story 3 - Centralized Output Contract Registry (Priority: P3)

When a developer adds a new agent or needs to understand what agents return, they must currently read each agent's source code to find the result type. A single contracts module should serve as the authoritative catalog of all agent output types, making them discoverable and importable from one location.

**Why this priority**: Discoverability and maintainability. New agents should follow the established pattern, and orchestration code should import contracts from a single, well-documented location rather than reaching into individual agent packages.

**Independent Test**: Can be tested by verifying that all agent output types are importable from the contracts module and that orchestration code imports from there.

**Acceptance Scenarios**:

1. **Given** a developer needs to consume an agent's output type, **When** they look for it, **Then** they can import it from the centralized contracts module.
2. **Given** a new agent is being built, **When** the developer follows the documented pattern, **Then** they know to define a Pydantic output model and register it in the contracts module.
3. **Given** orchestration code needs to validate raw agent output during a transition period, **When** it uses the validation utility, **Then** it receives either a validated model or a clear validation error.

---

### Edge Cases

- What happens when an agent returns completely empty output (no text at all)?
- What happens when an agent returns text that is valid JSON but does not match the expected schema (e.g., missing required fields)?
- What happens when a chunked code review produces findings in some chunks but malformed output in others? Partial results should still be returned for successful chunks.
- What happens when the `FixerAgent` applies changes via tools but then produces malformed structured output? The file changes still happened — the system must not discard tool-side effects based on output parsing failures.
- How does the system handle backward compatibility if a new output model adds required fields? Existing serialized results (e.g., in checkpoint files) must still deserialize.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `FixerAgent` MUST return a typed Pydantic model describing fix outcomes instead of the generic `AgentResult` with opaque `output: str`.
- **FR-002**: The code reviewer's parsing pipeline MUST replace regex-based JSON extraction with a validated parsing approach that returns Pydantic model instances or explicit errors.
- **FR-003**: The `SimpleFixerAgent`'s `_parse_outcomes` method MUST replace regex-based JSON extraction with validated parsing consistent with FR-002.
- **FR-004**: A centralized contracts module MUST re-export all agent output models from a single import location.
- **FR-005**: The contracts module MUST include a `validate_output(raw: str, model: type[BaseModel]) -> BaseModel` utility that extracts JSON from markdown code blocks (` ```json ... ``` `), validates it against the given Pydantic model, and returns a validated instance or raises a descriptive error. No raw-text or regex fallbacks for JSON embedded in prose.
- **FR-006**: All output models MUST be Pydantic `BaseModel` subclasses, serializable to JSON via `.model_dump_json()` for cross-context passing. Existing frozen dataclass output types (`Finding`, `FindingGroup`, `GroupedReviewResult`, `FixOutcome`) MUST be converted to Pydantic models.
- **FR-007**: The `IssueFixerAgent`'s `FixResult` model MUST be audited and tightened — any `str` fields that carry structured data (e.g., `files_changed`) should use typed sub-models.
- **FR-008**: Orchestration code in the review-fix workflow MUST consume typed result models, not raw string outputs.
- **FR-009**: The DSL agent step handler's `_extract_output_text` function MUST support all new typed result models for display/streaming purposes.
- **FR-010**: The base `AgentResult` type MUST remain available for backward compatibility but be marked as deprecated in docstrings with guidance to use specific result types.
- **FR-011**: Parsing failures MUST produce structured error information (what was expected, what was received, where parsing failed) rather than silently returning empty results.
- **FR-012**: Existing tests MUST continue to pass. New tests MUST cover the contract validation utility and any changed parsing logic.

### Key Entities

- **Agent Output Contract**: A Pydantic `BaseModel` subclass that defines the structured return type for a specific agent. Each agent has exactly one output contract. Contracts are immutable once published (additive changes only).
- **FixerResult**: New output contract for `FixerAgent`. Fields: `success: bool`, `summary: str`, `files_mentioned: list[str]` (best-effort, not authoritative — workflows use git diff for ground truth), `error_details: str | None`. Replaces the generic `AgentResult`.
- **Contracts Module**: Centralized registry that re-exports all output contracts and provides the `validate_output` utility.
- **ReviewFinding / FixOutcome / FixResult / ImplementationResult / ReviewResult / GroupedReviewResult**: Existing output types that are already structured. These are adopted into the contracts module as-is (or with minor tightening for `FixResult`). The dataclass `ReviewResult` from `review_models.py` is renamed to `GroupedReviewResult` to resolve the naming collision with the Pydantic `ReviewResult` from `review.py`.

### Out of Scope

- **Agent input contracts / context types**: Typing or restructuring agent input models (e.g., `AgentContext`, `ReviewContext`) is not part of this feature.
- **Agent prompt changes**: No modifications to agent system prompts or Claude prompting strategy. Agents already produce JSON in markdown code blocks; this feature changes how that output is parsed, not how it is produced.
- **`AgentResult` dataclass-to-Pydantic conversion**: The `AgentResult` frozen dataclass remains as-is for backward compatibility. It is deprecated in docstrings but not converted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero regex-based JSON extraction calls remain in the agent output parsing path — all agent outputs are parsed via Pydantic model validation.
- **SC-002**: All six agents (`FixerAgent`, `IssueFixerAgent`, `ImplementerAgent`, `CodeReviewerAgent`, `UnifiedReviewerAgent`, `SimpleFixerAgent`) return typed Pydantic models, not generic `AgentResult`.
- **SC-003**: 100% of existing tests pass without modification (new tests are additive).
- **SC-004**: The contracts module exports every agent output type and the validation utility, importable in a single `from maverick.agents.contracts import ...` statement.
- **SC-005**: When an agent produces malformed output, the system provides a descriptive validation error instead of silently returning empty results — observable via structured log output.

### Assumptions

- The Claude Agent SDK does not currently offer built-in structured output enforcement (e.g., constrained decoding). If it does, that capability should be used. Otherwise, a two-pass approach (agent produces text, then parsing validates against the schema) is acceptable.
- The `MaverickAgent[TContext, TResult]` base class signature is correct as-is and does not need changes.
- Existing checkpoint serialization uses JSON-compatible formats, so Pydantic models with `.model_dump()` are drop-in compatible.
- The `AgentResult` frozen dataclass can coexist with Pydantic models during the transition — it does not need to be converted to Pydantic immediately.
