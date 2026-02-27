# Implementation Plan: Three-Tier Prompt Configuration

**Branch**: `036-prompt-config` | **Date**: 2026-02-27 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/036-prompt-config/spec.md`

## Summary

Implement a three-tier prompt configuration layer (ADR-001): Maverick defaults → provider-specific variants → user overrides (suffix or file replacement). The system adds a `PromptRegistry` populated at startup from existing agent prompt constants (no duplication), a `resolve_prompt()` function that applies user overrides with policy enforcement, and a `prompts:` YAML config section for project-specific customization. Integration reuses the existing `StepConfig` resolution chain (spec 033) and `render_prompt()` template engine.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Pydantic (config models), structlog (logging), Claude Agent SDK (agents)
**Storage**: N/A (YAML config files only)
**Testing**: pytest + pytest-asyncio (parallel via xdist)
**Target Platform**: Linux/macOS CLI
**Project Type**: Single project (extends existing `src/maverick/` structure)
**Performance Goals**: Registry lookup < 1ms (in-memory dict), prompt resolution < 10ms including file I/O
**Constraints**: Zero regression on existing workflows; no hot-reloading; immutable registry after startup
**Scale/Scope**: ~12 default registry entries (agents + generators), extensible for future agents

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | Registry is sync (in-memory dict lookups); resolve_prompt() is sync (acceptable for simple file reads). No event loop blocking. |
| II. Separation of Concerns | PASS | Registry is data-only; resolution is a pure function; config parsing uses Pydantic. Agents remain unaware of registry internals. |
| III. Dependency Injection | PASS | Registry and overrides are passed into resolve_prompt() — no global state. |
| IV. Fail Gracefully | PASS | All errors are PromptConfigError (subclass of ConfigError). Validation at startup prevents runtime failures. |
| V. Test-First | PASS | Quickstart scenarios define 7 test scenarios; contracts define API surface. TDD approach. |
| VI. Type Safety | PASS | Frozen dataclasses with slots=True for PromptEntry/PromptResolution. Enums for OverridePolicy/PromptSource. No dict[str, Any] blobs. |
| VII. Simplicity & DRY | PASS | Registry imports existing constants by reference (FR-003). Config merges into existing StepConfig chain (R-005). No duplication. |
| VIII. Relentless Progress | N/A | Not a workflow; startup validation provides fail-fast. |
| IX. Hardening | PASS | File path security (project root restriction). Empty registry rejection. Startup validation. |
| X. Guardrails | PASS | #4 (typed contracts): PromptResolution is a frozen dataclass. #8 (canonical libs): Uses structlog. #12 (DSL type safety): N/A (no DSL expressions in prompts module). |
| XI. Modularize Early | PASS | New `src/maverick/prompts/` package with focused modules (~100-200 LOC each). |
| XII. Ownership | PASS | Full test coverage required per quickstart scenarios. |

**Post-Design Re-check**: All principles still pass. The `prompts:` config integration reuses existing StepConfig resolution (no new precedence chain).

## Project Structure

### Documentation (this feature)

```text
specs/036-prompt-config/
├── plan.md              # This file
├── research.md          # Phase 0 output (8 research decisions)
├── data-model.md        # Phase 1 output (6 entities, resolution algorithm)
├── quickstart.md        # Phase 1 output (7 integration scenarios)
├── contracts/           # Phase 1 output
│   └── prompt_api.py    # Public API contract (types, functions)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/maverick/prompts/
├── __init__.py          # Public API re-exports (PromptRegistry, resolve_prompt, etc.)
├── models.py            # OverridePolicy, PromptSource, PromptEntry, PromptResolution, PromptConfigError
├── registry.py          # PromptRegistry class (immutable mapping)
├── resolver.py          # resolve_prompt() function + render_prompt integration
├── config.py            # PromptOverrideConfig (Pydantic model for maverick.yaml)
├── defaults.py          # build_default_registry() — imports agent constants by reference
└── validation.py        # validate_prompt_config() — startup validation

src/maverick/config.py   # Modified: add prompts: dict[str, PromptOverrideConfig] field

tests/unit/prompts/
├── conftest.py          # Shared fixtures (sample registries, entries, overrides)
├── test_models.py       # OverridePolicy, PromptEntry, PromptResolution, PromptSource
├── test_registry.py     # PromptRegistry (get, get_policy, has, step_names, validate_override)
├── test_resolver.py     # resolve_prompt() (all 7 quickstart scenarios + edge cases)
├── test_config.py       # PromptOverrideConfig validation (mutual exclusivity, empty string)
├── test_defaults.py     # build_default_registry() (all agent entries present)
└── test_validation.py   # validate_prompt_config() (unknown steps, policy violations, file paths)
```

**Structure Decision**: New `src/maverick/prompts/` package follows the constitution's modularize-early principle (Appendix A: package-per-feature). Each module stays well under 500 LOC. Config integration touches `src/maverick/config.py` for the `prompts:` YAML section.

## Key Design Decisions

### D-001: Registry Imports Agent Constants by Reference (FR-003)

`build_default_registry()` imports prompt constants from their current agent module locations. No prompt text is duplicated. The registry holds references to the same string objects.

### D-002: Config Integration via StepConfig Merge (R-005)

The `prompts:` YAML section is a user-friendly alias. During config validation, prompt overrides are merged into the `steps:` config dict so the existing `resolve_step_config()` 4-layer precedence handles them. This avoids a separate resolution chain.

### D-003: Sync Resolution Function

`resolve_prompt()` is a synchronous function — registry lookups are dict operations and file reads are small. No async needed; keeps the API simple.

### D-004: Reuse render_prompt() from skill_prompts.py (A-002)

Template rendering uses the existing `render_prompt()` with `string.Template.safe_substitute()`. This leaves unmatched `$variables` unchanged, which is important for user-supplied suffixes that may contain dollar signs.

### D-005: Security via Project Root Restriction (FR-010)

`prompt_file` paths are resolved relative to project root. `Path.resolve()` canonicalizes the path, then a prefix check ensures it's within the project root. Absolute paths and `../` traversal are rejected at validation time.

## Integration Points

1. **Agent step handler** (`handlers/agent_step.py`): After resolving agent context, call `resolve_prompt()` to get final instructions before passing to `StepExecutor.execute()`.

2. **Generator step handler** (`handlers/generate_step.py`): After instantiating the generator, override its `system_prompt` with the resolved prompt.

3. **Dispatch handler** (`handlers/dispatch.py`): Already builds instructions from intent + prompt_suffix + prompt_file. Integrate with `resolve_prompt()` for consistency.

4. **MaverickConfig** (`config.py`): Add `prompts: dict[str, PromptOverrideConfig]` field with `model_validator` to merge into `steps:` dict.

## Complexity Tracking

No constitution violations. All principles pass without deviations.
