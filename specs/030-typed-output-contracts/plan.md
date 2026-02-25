# Implementation Plan: Typed Agent Output Contracts

**Branch**: `030-typed-output-contracts` | **Date**: 2026-02-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/030-typed-output-contracts/spec.md`

## Summary

Evolve Maverick's agent output system from opaque string-based results to typed Pydantic output contracts. The implementation leverages the Claude Agent SDK's built-in `output_format` parameter for structured output enforcement, with a `validate_output()` fallback for backward compatibility. Four frozen dataclass types are converted to Pydantic, one new `FixerResult` model is created, regex-based JSON extraction is eliminated from three parsing sites, and a centralized contracts module provides single-import access to all output types.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Pydantic (validation/models), Claude Agent SDK v0.1.18 (`output_format` structured output)
**Storage**: N/A (no persistence changes; existing checkpoint JSON remains compatible via `model_dump()`)
**Testing**: pytest + pytest-asyncio (parallel via xdist)
**Target Platform**: CLI (macOS/Linux)
**Project Type**: Single project (existing Maverick CLI application)
**Performance Goals**: N/A (no performance-sensitive paths affected)
**Constraints**: Backward compatibility with existing checkpoint JSON files; `AgentResult` frozen dataclass must remain unchanged
**Scale/Scope**: 6 agents, ~10 model types, 3 regex extraction sites to replace

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | No new blocking calls. Agent `execute()` methods remain async. |
| II. Separation of Concerns | PASS | Output contracts belong to models layer. Parsing moves from agents to shared utility. Agents still own judgment, workflows own orchestration. |
| III. Dependency Injection | PASS | `output_model` parameter is injected at construction time. No global state. |
| IV. Fail Gracefully | PASS | `OutputValidationError` provides structured error info instead of silent empty returns. Fallback from SDK structured output to `validate_output()`. |
| V. Test-First | PASS | New tests required for: `validate_output()`, converted Pydantic models, each agent's typed output path. |
| VI. Type Safety & Typed Contracts | PASS | **Primary beneficiary.** Eliminates `dict[str, Any]` and opaque `str` returns. All output models are Pydantic with typed fields. |
| VII. Simplicity & DRY | PASS | Centralizes scattered output types. Replaces 3 duplicate regex extractors with one shared `validate_output()`. |
| VIII. Relentless Progress | PASS | Fallback chain (SDK structured -> validate_output) ensures agent output is always captured. |
| IX. Hardening by Default | PASS | `validate_output()` replaces silent failures with explicit errors. |
| X. Architectural Guardrails | — | See sub-checks below. |
| X.4 (typed contracts) | PASS | Core goal of this feature. |
| X.8 (canonical libraries) | PASS | Uses Pydantic (canonical). No new libraries. |
| X.12 (DSL expression coercion) | N/A | No new DSL steps. |
| XI. Modularize Early | PASS | New `contracts.py` is small (re-exports + utility). `FixerResult` in separate `models/fixer.py`. |
| XII. Ownership | PASS | Feature fixes existing fragility (regex extraction) beyond its own scope. |

**Gate result**: PASS — no violations.

### Post-Phase 1 Re-check

| Principle | Status | Notes |
|-----------|--------|-------|
| VI. Typed Contracts | PASS | All output models are Pydantic. `validate_output()` provides typed parsing. SDK `output_format` uses `model_json_schema()`. |
| VII. Simplicity & DRY | PASS | Converted models add `to_dict()`/`from_dict()` aliases (thin wrappers, not duplication). |
| XI. Modularize Early | PASS | `contracts.py` is a re-export module (~50 LOC). `validate_output()` is ~40 LOC. Well under limits. |

## Project Structure

### Documentation (this feature)

```text
specs/030-typed-output-contracts/
├── plan.md                                # This file
├── spec.md                                # Feature specification
├── research.md                            # Phase 0: Research findings
├── data-model.md                          # Phase 1: Entity definitions
├── quickstart.md                          # Phase 1: Usage guide
├── contracts/
│   ├── contracts-module-api.md            # Phase 1: Contracts module public API
│   └── structured-output-integration.md   # Phase 1: SDK integration contract
└── tasks.md                               # Phase 2: Task breakdown (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/maverick/
├── agents/
│   ├── base.py                  # MODIFIED: add output_model param, _extract_structured_output()
│   ├── contracts.py             # NEW: centralized re-exports + validate_output()
│   ├── fixer.py                 # MODIFIED: return FixerResult instead of AgentResult
│   ├── result.py                # MODIFIED: add deprecation docstring to AgentResult
│   ├── code_reviewer/
│   │   ├── agent.py             # MODIFIED: use SDK output_format + validate_output fallback
│   │   └── parsing.py           # MODIFIED: replace extract_json with validate_output
│   └── reviewers/
│       ├── unified_reviewer.py  # MODIFIED: use SDK output_format + validate_output fallback
│       └── simple_fixer.py      # MODIFIED: use SDK output_format + validate_output fallback
├── models/
│   ├── fixer.py                 # NEW: FixerResult Pydantic model
│   ├── review_models.py         # MODIFIED: convert frozen dataclasses to Pydantic
│   └── issue_fix.py             # MODIFIED: deprecation note on FixResult.output
└── dsl/serialization/executor/handlers/
    └── agent_step.py            # MODIFIED: extend _extract_output_text for new types

tests/
├── unit/
│   ├── agents/
│   │   ├── test_contracts.py    # NEW: validate_output tests
│   │   └── test_fixer.py        # MODIFIED: test FixerResult output
│   └── models/
│       ├── test_fixer_model.py  # NEW: FixerResult model tests
│       └── test_review_models.py # MODIFIED: test converted Pydantic models
```

**Structure Decision**: Single project, extending existing `src/maverick/` layout. New files are minimal: `agents/contracts.py` (registry + utility) and `models/fixer.py` (new model). All other changes are modifications to existing files.

## Complexity Tracking

> No constitution violations. No complexity justifications needed.
