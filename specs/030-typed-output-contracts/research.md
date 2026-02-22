# Research: Typed Agent Output Contracts

**Feature Branch**: `030-typed-output-contracts`
**Date**: 2026-02-21

## R1: Claude Agent SDK Structured Output Support

**Decision**: Use the SDK's built-in `output_format` parameter for structured output enforcement, with a `validate_output()` fallback for backward compatibility.

**Rationale**: The Claude Agent SDK (v0.1.18, installed in this project) already supports structured output via the `output_format` field on `ClaudeAgentOptions`. The field accepts `{"type": "json_schema", "schema": <pydantic_schema>}` and is wired to the `--json-schema` CLI flag. The `ResultMessage` object carries a `structured_output` field with the validated result. The spec's assumption (line 118) anticipated this: "If it does, that capability should be used."

**Alternatives Considered**:
- **Two-pass extraction** (agent produces markdown, then validate): More complex, fragile, adds latency. Still needed as fallback for edge cases.
- **Prompt-only enforcement** ("Return ONLY JSON..."): Already used by some agents (e.g., CuratorAgent). Unreliable without schema constraint.

**Key Details**:
- `ClaudeAgentOptions.output_format`: `dict[str, Any] | None` at v0.1.18
- `ResultMessage.structured_output`: `Any` (populated when `output_format` is set)
- Error subtype: `"error_max_structured_output_retries"` when agent cannot produce valid output
- Compatible with both `query()` (one-shot) and `ClaudeSDKClient` (multi-turn)

**Integration Point**: `MaverickAgent._build_options()` in `src/maverick/agents/base.py:256` needs an optional `output_format` parameter.

---

## R2: Existing Output Type Landscape

**Decision**: Convert frozen dataclass output types to Pydantic models. Adopt SDK structured output for agents that produce JSON.

**Rationale**: The codebase has a heterogeneous mix of output types. Standardizing on Pydantic enables uniform `model_dump_json()` serialization, schema generation for `output_format`, and `validate_output()` support.

**Current State**:

| Agent | Return Type | Type System | Parsing Strategy |
|-------|------------|-------------|-----------------|
| FixerAgent | `AgentResult` | frozen dataclass | None (opaque text) |
| IssueFixerAgent | `FixResult` | Pydantic | Manual text extraction |
| ImplementerAgent | `ImplementationResult` | Pydantic | File change detection |
| CodeReviewerAgent | `ReviewResult` | Pydantic | Regex code block extraction |
| UnifiedReviewerAgent | `ReviewResult` (dc) | frozen dataclass | Regex code block extraction |
| SimpleFixerAgent | `list[FixOutcome]` | frozen dataclass | Regex code block extraction |

**Types to Convert** (frozen dataclass -> Pydantic):
1. `Finding` (`review_models.py:31`) - has `to_dict()`/`from_dict()`
2. `FindingGroup` (`review_models.py:81`) - has `to_dict()`/`from_dict()`
3. `ReviewResult` (`review_models.py:112`) - rename to `GroupedReviewResult`
4. `FixOutcome` (`review_models.py:149`) - has `to_dict()`/`from_dict()`

**Types Already Pydantic** (adopt as-is into contracts):
- `ReviewFinding` (`review.py:97`)
- `ReviewResult` (`review.py:169`)
- `ImplementationResult` (`implementation.py:539`)
- `FixResult` (`issue_fix.py:46`) - needs tightening per FR-007

---

## R3: Regex Extraction Locations

**Decision**: Replace all three regex extraction sites with SDK structured output + `validate_output()` fallback.

**Rationale**: Regex extraction is the single most fragile point in the output pipeline. All three locations silently return empty results on parse failure.

**Locations**:

1. **CodeReviewerAgent** (`code_reviewer/parsing.py:23-64`):
   - `extract_json()`: regex `r"```(?:json)?\s*\n(.*?)\n```"` + raw JSON fallback
   - `parse_findings()` (line 67): calls `extract_json()`, returns `[]` on failure
   - Already uses `ReviewResult.model_json_schema()` in prompt (line 723 of agent.py)

2. **UnifiedReviewerAgent** (`reviewers/unified_reviewer.py:362`):
   - `_parse_review_output()`: regex `r"```json\s*(\{.*?\})\s*```"` + raw JSON fallback
   - Returns `ReviewResult(groups=())` on failure (silent empty)

3. **SimpleFixerAgent** (`reviewers/simple_fixer.py:326`):
   - `_parse_outcomes()`: regex `r"```json\s*(\{.*?\})\s*```"` + raw JSON fallback
   - Returns `[]` on failure (silent empty)

---

## R4: FixerAgent Output Contract Design

**Decision**: Create `FixerResult` Pydantic model with lightweight fields per spec clarification.

**Rationale**: The FixerAgent currently returns `AgentResult` with opaque `output: str`. Downstream workflows cannot programmatically determine what the fixer did. A typed contract enables informed retry/abort decisions.

**Alternatives Considered**:
- **Heavyweight model** with diff tracking: Over-engineering. Workflows use `git diff` for ground truth.
- **Extending AgentResult**: Violates spec's out-of-scope rule (AgentResult stays as-is).
- **Reusing FixResult from IssueFixerAgent**: Different semantics (issue-level vs. finding-level fixes).

**Design**:
```python
class FixerResult(BaseModel):
    success: bool
    summary: str
    files_mentioned: list[str]  # best-effort, not authoritative
    error_details: str | None = None
```

---

## R5: IssueFixerAgent FixResult Tightening

**Decision**: Add typed sub-model for `files_changed` field. Current `list[FileChange]` is already typed. Audit `output: str` field — it carries structured data that should be typed.

**Rationale**: FR-007 requires auditing `FixResult` for `str` fields carrying structured data. Current fields:
- `root_cause: str` — free text, appropriate as str
- `fix_description: str` — free text, appropriate as str
- `output: str` — raw agent output dump, could be deprecated
- `files_changed: list[FileChange]` — already typed (good)

**Action**: Mark `output: str` as deprecated with guidance to use `fix_description` + `files_changed`. No structural change needed beyond deprecation annotation.

---

## R6: _extract_output_text Compatibility

**Decision**: Extend `_extract_output_text` to handle all new typed result models via duck-typing pattern matching.

**Rationale**: The function at `agent_step.py:340` uses `hasattr()` checks to extract display text from various result types. New models (FixerResult, GroupedReviewResult) need corresponding branches.

**Current handled types**: AgentResult (`.output`), dict (`["output"]`), ImplementationResult (`.tasks_completed`), str, fallback `str()`.

**New types to handle**: FixerResult (`.summary`), GroupedReviewResult (`.all_findings` count), list[FixOutcome] (count + summary).

---

## R7: Naming Collision Resolution

**Decision**: Rename dataclass `ReviewResult` (from `review_models.py`) to `GroupedReviewResult` per spec clarification.

**Rationale**: Two `ReviewResult` types exist:
- Pydantic `ReviewResult` in `review.py:169` (used by CodeReviewerAgent) — keeps name
- Frozen dataclass `ReviewResult` in `review_models.py:112` (used by UnifiedReviewerAgent) — renamed to `GroupedReviewResult`

**Migration**: Update all imports of the dataclass version to use `GroupedReviewResult`. After Pydantic conversion, re-export from contracts module.

---

## R8: Backward Compatibility Strategy

**Decision**: Maintain `AgentResult` as-is, mark deprecated. Converted Pydantic models preserve `to_dict()`/`from_dict()` as aliases for `model_dump()`/`model_validate()`.

**Rationale**:
- Spec explicitly excludes `AgentResult` conversion (out of scope)
- Existing checkpoint JSON files use `to_dict()` output — Pydantic `model_dump()` produces compatible dicts
- `from_dict()` maps to `model_validate()` — same input format
- Adding `.to_dict()` and `.from_dict()` as thin wrappers on converted models ensures zero-breakage migration
