# Research: CLI Prerequisite Check

**Feature**: /workspaces/maverick/specs/001-cli-prereq-check/spec.md  
**Date**: 2025-10-28  
**Branch**: 001-cli-prereq-check

## Decisions

### D1: Temporal testing approach
- Decision: Use Temporal Python SDK testing utilities with deterministic workflow tests; unit tests for activities; integration tests for workflow execution.
- Rationale: Ensures non-determinism is controlled and workflow logic is validated end-to-end.
- Alternatives considered: Pure unit tests without workflow runner (insufficient coverage); manual testing only (unacceptable per TDD).

### D2: Checking GitHub CLI authentication
- Decision: Execute `gh auth status --show-token=false` and rely on exit code and stderr/stdout parsing for human-readable summary.
- Rationale: Exit code reliably indicates auth state; avoids leaking tokens.
- Alternatives considered: Running API calls via gh to probe (slower, adds network dependency).

### D3: Detecting Copilot CLI availability
- Decision: Execute `copilot help` and check exit code; do not require gh extension.
- Rationale: Aligns with spec decision Q1=A (standalone binary authoritative).
- Alternatives considered: `which copilot` (less robust on shells); `gh copilot` (out of scope).

### D4: Non-interactive design
- Decision: Non-interactive execution only; no environment modification or prompts.
- Rationale: Safe for CI and first-run; aligns with spec decision Q2=A.
- Alternatives considered: Optional interactive remediation (deferred; adds complexity).

### D5: Output format
- Decision: Human-readable only; no JSON.
- Rationale: Aligns with spec decision Q3=A; keeps MVP minimal.
- Alternatives considered: JSON flag for automation (can be future enhancement).

## Open Questions

None; all clarifications resolved in spec.
