# Implementation Plan: Preflight Validation System

**Branch**: `027-preflight-validation` | **Date**: 2024-12-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/027-preflight-validation/spec.md`

## Summary

Design and implement a Preflight Validation system for Maverick workflows that:

- Validates all required tools and configurations **before** creating any branches or modifying state
- Introduces a `ValidatableRunner` protocol that existing runners (`GitRunner`, `GitHubCLIRunner`, `ValidationRunner`, `CodeRabbitRunner`) implement
- Aggregates all validation failures into a single, actionable error report
- Runs validations in parallel with configurable timeouts (default 5s per check)
- Integrates into `FlyWorkflow` and `RefuelWorkflow` via a shared preflight method in `WorkflowDSLMixin`

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)  
**Primary Dependencies**: asyncio, shutil, Pydantic (dataclasses/validation), pytest-asyncio  
**Storage**: N/A (terminal output only, no persistence)  
**Testing**: pytest + pytest-asyncio  
**Target Platform**: Linux/macOS/Windows CLI  
**Project Type**: Single project - existing `src/maverick/` structure  
**Performance Goals**: Preflight completes in <2 seconds when all tools present  
**Constraints**: <5 seconds timeout per individual check, no blocking on async event loop  
**Scale/Scope**: 4 core runners to validate, 2 workflows to integrate

## Constitution Check

_GATE: Must pass before Phase 0 research. Re-check after Phase 1 design._

| Principle                                     | Status  | Notes                                                                                                               |
| --------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| **I. Async-First**                            | ✅ PASS | All validation methods will be async; uses `asyncio.gather` for parallel checks; no `subprocess.run` on async paths |
| **II. Separation of Concerns**                | ✅ PASS | Runners validate themselves; workflows orchestrate; TUI receives events only                                        |
| **III. Dependency Injection**                 | ✅ PASS | Runners are injected into workflows; no global state                                                                |
| **IV. Fail Gracefully, Recover Aggressively** | ✅ PASS | Aggregates all errors; doesn't fail on first error                                                                  |
| **V. Test-First**                             | ✅ PASS | Tests must accompany implementation                                                                                 |
| **VI. Type Safety & Typed Contracts**         | ✅ PASS | `ValidationResult` and `PreflightResult` are frozen dataclasses; `ValidatableRunner` is a Protocol                  |
| **VII. Simplicity & DRY**                     | ✅ PASS | Single `ValidatableRunner` protocol; shared preflight method in mixin                                               |
| **VIII. Relentless Progress**                 | ✅ PASS | Preflight enables better progress by failing early rather than mid-workflow                                         |
| **IX. Hardening by Default**                  | ✅ PASS | Per-check timeouts; explicit error handling; no bare `except`                                                       |
| **X. Architectural Guardrails**               | ✅ PASS | No TUI subprocess calls; async-safe; deterministic ops in workflows                                                 |
| **XI. Modularize Early**                      | ✅ PASS | New `preflight.py` module ~200-300 LOC; protocol in `protocols.py`                                                  |
| **XII. Ownership & Follow-Through**           | ✅ PASS | Complete feature including tests and integration                                                                    |

## Project Structure

### Documentation (this feature)

```text
specs/027-preflight-validation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/maverick/
├── runners/
│   ├── __init__.py      # Add ValidationResult, PreflightResult exports
│   ├── protocols.py     # NEW: ValidatableRunner protocol
│   ├── preflight.py     # NEW: PreflightValidator, aggregate results
│   ├── git.py           # ADD: validate() method
│   ├── github.py        # ADD: validate() method
│   ├── validation.py    # ADD: validate() method (tool availability)
│   └── coderabbit.py    # ADD: validate() method
├── workflows/
│   └── base.py          # ADD: run_preflight() method to WorkflowDSLMixin
└── exceptions/
    └── preflight.py     # NEW: PreflightValidationError

tests/unit/runners/
├── test_preflight.py    # NEW: PreflightValidator tests
└── test_*_validation.py # MODIFY: Add validate() tests to existing runner tests

tests/integration/
└── test_preflight_integration.py  # NEW: End-to-end preflight tests
```

**Structure Decision**: Single project structure following existing Maverick conventions. New code goes into `src/maverick/runners/` (preflight.py, protocols.py) with workflow integration in `workflows/base.py`.

## Complexity Tracking

> No violations - design follows all constitution principles.
