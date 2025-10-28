# Contract Mapping: API to Implementation

**Feature**: CLI Prerequisite Check
**Date**: 2025-10-28
**Status**: Implemented

## Overview

This document maps the OpenAPI contract (`openapi.yaml`) to the Temporal workflow implementation and CLI interface.

## API to Implementation Mapping

### POST /readiness-check

The API contract defines a simple endpoint that triggers the readiness workflow and returns results.

**Contract Location**: `openapi.yaml` - `/readiness-check`
**Workflow Implementation**: `src/workflows/readiness.py` - `ReadinessWorkflow`
**CLI Implementation**: `src/cli/readiness.py` - `run_check()`

#### Request

```http
POST /readiness-check
Content-Type: application/json
```

**Request Body**: None (empty request)

#### Response

```http
HTTP/1.1 200 OK
Content-Type: application/json
```

**Response Body**: `ReadinessSummary` (see schema below)

### Workflow Execution Flow

```text
API Request
    │
    ├─> Temporal Client (src/cli/readiness.py)
    │       │
    │       ├─> Execute ReadinessWorkflow
    │       │       │
    │       │       ├─> Activity: check_gh_status (src/activities/gh_status.py)
    │       │       │       └─> Returns PrereqCheckResult for "gh"
    │       │       │
    │       │       └─> Activity: check_copilot_help (src/activities/copilot_help.py)
    │       │               └─> Returns PrereqCheckResult for "copilot"
    │       │
    │       └─> Aggregate results into ReadinessSummary
    │
    └─> Return ReadinessSummary
```

### CLI Equivalent

The CLI provides a human-readable interface to the same workflow:

```bash
uv run readiness:check
```

**Implementation**: `src/cli/readiness.py`
- Connects to Temporal server at `localhost:7233`
- Executes the same `ReadinessWorkflow`
- Formats the `ReadinessSummary` for terminal display
- Returns exit code: 0 (ready), 1 (not ready), 2 (error)

## Data Model Mapping

### PrereqCheckResult

**Contract Schema** (`openapi.yaml`):
```yaml
PrereqCheckResult:
  type: object
  properties:
    tool: string (enum: [gh, copilot])
    status: string (enum: [pass, fail])
    message: string
    remediation: string (optional)
  required: [tool, status, message]
```

**Python Implementation** (`src/models/prereq.py`):
```python
@dataclass
class PrereqCheckResult:
    tool: str
    status: CheckStatus  # Literal["pass", "fail"]
    message: str
    remediation: Optional[str] = None
```

**Activity Output**:
- `check_gh_status()` → `PrereqCheckResult` with tool="gh"
- `check_copilot_help()` → `PrereqCheckResult` with tool="copilot"

**Remediation Content**:
- Present when `status="fail"`
- Contains step-by-step guidance to resolve the issue
- Includes links to official documentation
- Formatted for both JSON serialization and human reading

### ReadinessSummary

**Contract Schema** (`openapi.yaml`):
```yaml
ReadinessSummary:
  type: object
  properties:
    results: array of PrereqCheckResult
    overall_status: string (enum: [ready, not_ready])
    duration_ms: integer (int64)
  required: [results, overall_status]
```

**Python Implementation** (`src/models/prereq.py`):
```python
@dataclass
class ReadinessSummary:
    results: List[PrereqCheckResult]
    overall_status: OverallStatus  # Literal["ready", "not_ready"]
    duration_ms: int
```

**Workflow Output**:
- `ReadinessWorkflow.run()` → `ReadinessSummary`
- Contains exactly 2 results (gh and copilot)
- `overall_status` is "ready" if all checks pass, "not_ready" otherwise
- `duration_ms` measured using workflow-deterministic time

## Status Determination Logic

### Overall Status

**Business Rule**: System is "ready" if and only if ALL prerequisite checks pass.

**Implementation** (`src/workflows/readiness.py`):
```python
all_passed = (
    gh_result.status == "pass" and 
    copilot_result.status == "pass"
)
overall_status = "ready" if all_passed else "not_ready"
```

### Individual Check Status

**GitHub CLI (`gh`)** - Determined by `src/activities/gh_status.py`:
- **pass**: `gh auth status` returns exit code 0 (authenticated)
- **fail**: 
  - `gh` command not found (not installed)
  - `gh auth status` returns non-zero (not authenticated)
  - Command timeout or other error

**Copilot CLI** - Determined by `src/activities/copilot_help.py`:
- **pass**: `copilot help` returns exit code 0
- **fail**:
  - `copilot` command not found (not installed)
  - `copilot help` returns non-zero exit code
  - Command timeout or other error

## CLI Output Format

The CLI transforms the JSON response into human-readable format:

```text
============================================================
CLI Readiness Check
============================================================

✓ GH: PASS
  GitHub CLI is installed and authenticated

✗ COPILOT: FAIL
  Copilot CLI is not installed or not found in PATH

  Remediation:
    Copilot CLI is not installed.
    
    Install the standalone Copilot CLI:
      • Download from: https://github.com/github/gh-copilot
      • Or install via GitHub CLI extension:
        gh extension install github/gh-copilot
        
    Note: This check requires the standalone 'copilot' binary...
    
    Official documentation: https://docs.github.com/en/copilot...

------------------------------------------------------------
✗ Overall Status: NOT READY

Some prerequisites are not satisfied. Please review the
remediation guidance above and try again.

Check completed in 542ms
============================================================
```

**Formatting Rules** (`src/cli/readiness.py:format_summary()`):
- Status symbols: ✓ (pass), ✗ (fail)
- Tool names in uppercase
- Remediation indented with heading
- Multi-line remediation guidance preserved
- Clear overall status with explanation
- Execution duration displayed

## Error Handling

### Workflow Level

- Activities are retried up to 3 times with exponential backoff
- `FileNotFoundError` is non-retryable (tool not installed)
- Activity timeout: 30 seconds per check
- Workflow completes successfully even when checks fail

### CLI Level

**Exit Codes**:
- `0`: All checks passed (ready)
- `1`: One or more checks failed (not ready)
- `2`: Error executing workflow (e.g., Temporal server unavailable)

**Error Messages** (stderr):
```text
Error: Failed to execute readiness check: <error details>

Troubleshooting:
  1. Ensure Temporal server is running (temporal server start-dev)
  2. Ensure the readiness worker is running (uv run readiness:worker)
  3. Check logs for more details
```

## Testing Coverage

### Unit Tests

- `tests/unit/test_gh_status.py`: Activity behavior for various gh states
- `tests/unit/test_copilot_help.py`: Activity behavior for various copilot states
- `tests/unit/test_remediation_messages.py`: Remediation content validation

### Integration Tests

- `tests/integration/test_readiness_workflow.py`: End-to-end workflow execution
  - All checks pass scenario
  - Individual check failure scenarios
  - Multiple failures scenario
  - Remediation guidance presence validation

## Implementation Notes

### Temporal Considerations

1. **Determinism**: Workflow uses `workflow.now()` instead of `time.time()` for duration calculation
2. **Type Safety**: Activities specify `result_type=PrereqCheckResult` to ensure proper deserialization
3. **Literal Types**: Status enums use `Literal` instead of `Enum` to avoid custom serialization
4. **Parallel Execution**: Both activity checks run in parallel for performance

### Non-Interactive Design

- All checks execute without user prompts
- No environment modifications (report-only)
- Suitable for CI/CD integration
- Deterministic workflow execution

### Extension Points

To add new prerequisite checks:

1. Create activity in `src/activities/`
2. Add activity call to `src/workflows/readiness.py`
3. Update contract schemas to include new tool
4. Add remediation guidance constants
5. Update tests

## Related Documentation

- **Feature Specification**: `../spec.md`
- **Data Model**: `../data-model.md`
- **Implementation Plan**: `../plan.md`
- **OpenAPI Contract**: `./openapi.yaml`
- **Quick Start Guide**: `../quickstart.md`
