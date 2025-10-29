# Data Model: CLI Prerequisite Check

**Feature**: /workspaces/maverick/specs/001-cli-prereq-check/spec.md  
**Date**: 2025-10-28

## Entities

### PrereqCheckResult
- tool: string (e.g., "gh", "copilot")
- status: enum ["pass", "fail"]
- message: string (human-readable detail)
- remediation: string (human-readable guidance; optional)

### ReadinessSummary
- results: PrereqCheckResult[] (at least 2 for gh and copilot)
- overall_status: enum ["ready", "not_ready"]
- duration_ms: number (execution time)

## Validation Rules
- Each `tool` must be unique within `results`.
- `overall_status` is `ready` iff all `results.status == pass`.
- `message` MUST be present for both pass and fail to aid observability.

## State Transitions
- Initial: not_ready (implicit before run)
- After workflow run: ready | not_ready based on results
