# Implementation Plan: Unified Maverick Init with Claude-Powered Detection

**Branch**: `028-maverick-init` | **Date**: 2025-12-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/028-maverick-init/spec.md`

## Summary

Replace `maverick config init` with a comprehensive `maverick init` command that:
1. Validates all prerequisites (git, gh CLI, GitHub auth, Anthropic API)
2. Uses Claude (claude-3-5-haiku) to analyze project structure and detect project type
3. Derives GitHub owner/repo from git remote URL
4. Generates complete `maverick.yaml` with appropriate validation commands
5. Adds Anthropic API validation to fly/refuel workflow preflight checks

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Click, Pydantic, PyYAML, GitPython
**Storage**: YAML files (`maverick.yaml`, `~/.config/maverick/config.yaml`)
**Testing**: pytest + pytest-asyncio (all tests async-compatible)
**Target Platform**: Linux, macOS, Windows (cross-platform CLI)
**Project Type**: Single Python package with CLI entry point
**Performance Goals**: Init command completes in <30 seconds (SC-001); Preflight API check <5 seconds
**Constraints**: Must support offline marker-based detection (`--no-detect` flag)
**Scale/Scope**: Single-project initialization; monorepo primary type selection

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Gate Evaluation

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | ✅ PASS | All external calls (git, gh, Anthropic API) will use async patterns via CommandRunner and claude_agent_sdk.query() |
| II. Separation of Concerns | ✅ PASS | CLI handles user I/O; detection logic in dedicated module; preflight in runners |
| III. Dependency Injection | ✅ PASS | Git repo, API client, runner injected; no global state |
| IV. Fail Gracefully | ✅ PASS | Prerequisite failures provide actionable errors; detection fallback to Python defaults |
| V. Test-First | ✅ PASS | Unit tests for detection, prereqs, config generation; integration tests for full init |
| VI. Type Safety | ✅ PASS | Pydantic models for ProjectDetectionResult, PreflightResult; dataclasses for entities |
| VII. Simplicity & DRY | ✅ PASS | Reuse existing prereqs.py pattern, git utilities, config loading |
| VIII. Relentless Progress | ✅ PASS | Init fails fast on prerequisite failures (appropriate for setup command) |
| IX. Hardening by Default | ✅ PASS | Timeouts on all external calls; specific exception handling |
| X. Architectural Guardrails | ✅ PASS | No TUI subprocess calls; runners handle execution |
| XI. Modularize Early | ✅ PASS | New init logic in `src/maverick/cli/commands/init.py` and `src/maverick/init/` package |
| XII. Ownership & Follow-Through | ✅ PASS | Deprecation warning for `config init`; complete migration path |

### Constitution Alignment Summary

**No violations identified.** The feature design aligns with all 12 principles:
- Uses existing async patterns from prereqs.py and generators/base.py
- Follows established CLI command structure in cli/commands/
- Reuses git remote parsing from workflows
- Integrates with existing preflight validation system

## Project Structure

### Documentation (this feature)

```text
specs/028-maverick-init/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/maverick/
├── cli/
│   └── commands/
│       ├── init.py              # NEW: maverick init command
│       └── config.py            # MODIFY: add deprecation warning
├── init/                        # NEW: init package
│   ├── __init__.py
│   ├── detector.py              # Project type detection (Claude + marker-based)
│   ├── prereqs.py               # Prerequisite validation (git, gh, API)
│   ├── config_generator.py      # maverick.yaml generation
│   └── models.py                # ProjectType, ProjectDetectionResult, etc.
├── runners/
│   └── preflight.py             # MODIFY: add Anthropic API validator
└── exceptions/
    └── init.py                  # NEW: InitError exceptions

tests/
├── unit/
│   └── init/                    # NEW: unit tests
│       ├── test_detector.py
│       ├── test_prereqs.py
│       └── test_config_generator.py
└── integration/
    └── test_init_command.py     # NEW: integration tests
```

**Structure Decision**: Single project (Option 1) - extends existing `src/maverick/` layout with new `init/` package following the modularization guidelines from Appendix A.

## Complexity Tracking

> **No violations requiring justification** - design follows established patterns.

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Detection module location | New `src/maverick/init/` package | Follows Appendix A pattern for feature isolation |
| Claude model | claude-3-5-haiku | Spec requirement (FR-007); fast and cheap for detection |
| Preflight integration | Extend existing PreflightValidator | Reuse existing pattern rather than parallel implementation |

---

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1 design completion.*

| Principle | Status | Post-Design Notes |
|-----------|--------|-------------------|
| I. Async-First | ✅ PASS | All contracts specify async functions; `query()` from SDK is async generator |
| II. Separation of Concerns | ✅ PASS | Clear module boundaries: prereqs.py, detector.py, config_generator.py |
| III. Dependency Injection | ✅ PASS | `run_init()` accepts optional project_path; validators receive config |
| IV. Fail Gracefully | ✅ PASS | Exception hierarchy defined; PrerequisiteCheck captures remediation |
| V. Test-First | ✅ PASS | Test file structure defined; unit + integration coverage planned |
| VI. Type Safety | ✅ PASS | Frozen dataclasses with `to_dict()`; Pydantic for config; explicit enums |
| VII. Simplicity & DRY | ✅ PASS | Reuses git parsing regex; delegates to CommandRunner; constants extracted |
| VIII. Relentless Progress | ✅ PASS | Init command is setup (fail-fast appropriate); workflows have retry via preflight |
| IX. Hardening by Default | ✅ PASS | All external calls have explicit timeouts in contracts |
| X. Architectural Guardrails | ✅ PASS | AnthropicAPIValidator follows ValidatableRunner protocol |
| XI. Modularize Early | ✅ PASS | ~5 modules in init/; each <300 LOC estimated |
| XII. Ownership & Follow-Through | ✅ PASS | Deprecation path documented; migration from config init seamless |

**Post-Design Verdict**: ✅ **All 12 principles satisfied.** No design changes required.

---

## Generated Artifacts

| Artifact | Path | Status |
|----------|------|--------|
| Plan | `/specs/028-maverick-init/plan.md` | ✅ Complete |
| Research | `/specs/028-maverick-init/research.md` | ✅ Complete |
| Data Model | `/specs/028-maverick-init/data-model.md` | ✅ Complete |
| CLI Interface Contract | `/specs/028-maverick-init/contracts/cli-interface.md` | ✅ Complete |
| Internal API Contract | `/specs/028-maverick-init/contracts/internal-api.md` | ✅ Complete |
| Quickstart | `/specs/028-maverick-init/quickstart.md` | ✅ Complete |

## Next Steps

Run `/speckit.tasks` to generate the implementation task list from these design artifacts.
