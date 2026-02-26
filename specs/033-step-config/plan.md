# Implementation Plan: Step Configuration Model

**Branch**: `033-step-config` | **Date**: 2026-02-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/033-step-config/spec.md`

## Summary

Expand Maverick's configuration model to support rich per-step configuration, unifying provider selection (ADR-001) with execution mode and autonomy levels (ADR-002). Replace the existing frozen dataclass `StepExecutorConfig` with a Pydantic-based `StepConfig` model that adds `mode`, `autonomy`, `provider`, `allowed_tools`, `prompt_suffix`, and `prompt_file` fields. Introduce `StepMode` and `AutonomyLevel` enums, extend all step record types to accept an optional `config` field, add project-level step defaults in `MaverickConfig`, and implement four-layer configuration resolution.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Pydantic (config models), PyYAML (serialization), Claude Agent SDK (executor)
**Storage**: N/A (YAML config files only)
**Testing**: pytest + pytest-asyncio, parallel via xdist
**Target Platform**: Linux/macOS CLI
**Project Type**: Single project (Python package)
**Performance Goals**: N/A (config loading is not performance-critical)
**Constraints**: Backward-compatible with existing `executor_config` YAML field; zero behavioral regression for existing workflows
**Scale/Scope**: ~8 step record types, ~12 config fields, 4-layer resolution

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | Config model is synchronous data; no async concerns |
| II. Separation of Concerns | PASS | Config model is pure data; validation/resolution logic separated from agents/workflows |
| III. Dependency Injection | PASS | `StepConfig` is injected into executors, not globally accessed |
| IV. Fail Gracefully | PASS | Invalid config rejected at load time with clear errors |
| V. Test-First | PASS | Tests required for all new models, validators, and resolution logic |
| VI. Type Safety | PASS | Pydantic BaseModel with complete type annotations; enums for mode/autonomy |
| VII. Simplicity & DRY | PASS | Single `StepConfig` model replaces separate config concepts; shared resolution function |
| VIII. Relentless Progress | N/A | Config model, not runtime execution |
| IX. Hardening by Default | PASS | Pydantic validation at boundaries; safe defaults (deterministic mode, operator autonomy) |
| X. Guardrails | PASS | #4 (typed contracts): StepConfig is a Pydantic model, not a dict; #12 (DSL type coercion): string-to-enum coercion handled by Pydantic |
| XI. Modularize Early | PASS | New `StepConfig` stays in `dsl/executor/config.py` (currently 77 LOC); enums in `dsl/types.py` |
| XII. Ownership | PASS | Includes backward compat for `executor_config`, deprecation warnings |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/033-step-config/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── step-config-api.md
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/maverick/
├── dsl/
│   ├── types.py                          # ADD: StepMode, AutonomyLevel enums
│   ├── executor/
│   │   └── config.py                     # MODIFY: Add StepConfig Pydantic model, keep RetryPolicy
│   └── serialization/
│       ├── schema.py                     # MODIFY: Add config field to StepRecord base, backward compat
│       └── executor/
│           └── handlers/
│               └── agent_step.py         # MODIFY: Update _resolve_executor_config → StepConfig
└── config.py                             # MODIFY: Add steps: dict[str, StepConfig] to MaverickConfig

tests/
├── unit/
│   ├── dsl/
│   │   ├── executor/
│   │   │   └── test_config.py            # MODIFY: Add StepConfig tests
│   │   ├── serialization/
│   │   │   └── test_schema.py            # MODIFY: Add config field tests
│   │   └── test_types.py                 # ADD or MODIFY: StepMode, AutonomyLevel tests
│   └── test_config.py                    # MODIFY: Add steps config tests
└── integration/
    └── test_config_loading.py            # MODIFY: Add steps hierarchy tests
```

**Structure Decision**: Extend existing modules. `StepConfig` lives alongside the existing `StepExecutorConfig` in `dsl/executor/config.py` (migrating from dataclass to Pydantic model). Enums go in `dsl/types.py` where `StepType` already lives. No new packages needed.

## Complexity Tracking

> No constitution violations — no entries needed.
