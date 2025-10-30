# Research: Containerized Validation with Docker Compose

Date: 2025-10-30  
Feature: 001-docker-compose-runner

## Decisions

### 1. Parameter Format for Compose Input

**Decision**: Accept a file path to a Docker Compose YAML in the CLI; parse to a Python dict structure and pass to workflow as parameter.

**Rationale**: 
- Temporal best practice: Workflow parameters should contain all necessary data for replay determinism
- File paths are ephemeral; files may not exist during workflow replay or on different workers
- Temporal supports events up to 2MB; 1MB YAML limit is well within this
- All workflow state lives in Temporal history; no external file dependencies
- Parsing in CLI enables early validation before workflow starts

**Implementation**: CLI reads file, validates size (≤1MB), parses with PyYAML, passes dict structure to workflow.

**Alternatives considered**:
  - Raw YAML string parameter: ✅ Selected variant (parsed dict is YAML string parsed to structure)
  - Pass file path only: ❌ File may not exist during replay; breaks determinism
  - Pre-hosted artifact URL: ❌ Adds external dependency and retrieval complexity

### 2. YAML Parsing Library

**Decision**: Use PyYAML (`yaml.safe_load`) for reading Compose YAML in CLI, before workflow invocation.

**Rationale**: Widely used, sufficient for Compose v2 schema; no need for ruamel round-trip editing; `safe_load` prevents code execution vulnerabilities.

**Alternatives considered**:
  - ruamel.yaml: heavier; beneficial for round-tripping, not needed here
  - Native ad-hoc parsing: error-prone and inconsistent with standards

### 3. Target Service Selection Policy

**Decision**: If one service exists → use it. If multiple → use "app". If multiple and no "app" → require explicit selection and fail otherwise.

**Rationale**: Simple, predictable default matching spec clarifications. Explicit is better than implicit when ambiguous.

**Alternatives considered**:
  - First-listed service: order-dependent, surprising
  - Heuristics by exposed ports or healthchecks: brittle and complex

### 4. Temporary Directory Management

**Decision**: Use Python's `tempfile.mkdtemp()` with context manager for compose file storage within activities.

**Rationale**:
- Cross-platform: Works in dev containers, Docker-in-Docker, and native Linux
- Automatic cleanup: Context manager handles cleanup on success
- Unique paths: Each activity invocation gets isolated directory
- No conflicts: Parallel workflow runs won't collide

**Implementation**: Activity receives parsed dict, serializes to temporary YAML file, passes to `docker compose -f`.

**Alternatives considered**:
  - Fixed path `/tmp/compose-<workflow_id>.yml`: ❌ Risk of conflicts; manual cleanup complex
  - Pass via stdin: ❌ Docker Compose V2 requires file paths (no stdin support)

### 5. Health Check Polling Strategy

**Decision**: Implement exponential backoff polling using `docker compose ps --format json` to check service health.

**Rationale**:
- Explicit status: Reports health per service (healthy, unhealthy, starting)
- Structured output: JSON format enables reliable parsing
- Efficient: Exponential backoff reduces polling frequency (1s, 2s, 4s, 8s, ..., max 30s)
- Timeout-bounded: Activity timeout serves as hard limit

**Implementation**: Poll in loop with backoff; return immediately on "healthy" or "unhealthy"; timeout if still "starting".

**Alternatives considered**:
  - `docker inspect` on containers: ❌ Requires container ID lookup; compose ps is simpler
  - Fixed-interval polling: ❌ Wastes cycles during slow startup
  - `docker compose up --wait`: ⚠️ Less control over timeout/logging

### 6. Error Message Extraction

**Decision**: Capture stderr from subprocess, decode with `errors='replace'`, extract last 50 lines for user-facing messages.

**Rationale**:
- User context: Includes image pull failures, port conflicts, invalid YAML, health check failures
- Volume management: Full logs can be massive; truncate to most relevant
- Encoding safety: `errors='replace'` prevents UnicodeDecodeError (per constitution)
- Structured logging: Log full stderr; show truncated version to user

**Common error patterns**: Image pull failures, port conflicts, invalid YAML, health check timeouts.

**Alternatives considered**:
  - Parse structured JSON logs: ❌ Compose errors are human-readable text
  - Show full stderr: ❌ Too overwhelming
  - Regex extraction: ❌ Too brittle

### 7. Cleanup Policy

**Decision**: Separate cleanup activity with two modes: "graceful" (success) and "preserve" (failure).

**Rationale**:
- Spec requirement: Preserve failed environments indefinitely for troubleshooting
- Separation of concerns: Cleanup is distinct operation
- Idempotency: Can be retried safely
- Explicit control: Workflow decides based on success/failure

**Implementation**: 
- Success path: `docker compose -p <project> down -v` (removes volumes)
- Failure path: Log manual cleanup instructions; skip teardown

**Alternatives considered**:
  - Always down: ❌ Violates spec (need failure inspection)
  - Time-based auto-cleanup: ❌ Spec says no auto-cleanup ("could fail overnight")
  - Cleanup in startup activity: ❌ Violates separation of concerns

### 8. Execution Model

**Decision**: Activity writes YAML to temp directory, runs `docker compose up -d`, validations execute via `docker compose exec <service> ...`.

**Rationale**: Keeps workflows deterministic; side effects in activities; aligns with constitution.

**Alternatives considered**:
  - Use Docker SDK (python): ❌ Adds dependency; CLI sufficient

### 9. Timeouts

**Decision**: 
- Startup (including health checks): 300s default (5 minutes)
- Per-validation step: 60s default
- Configurable via workflow parameters

**Rationale**: Balances common image pull times with feedback speed. Spec requires 5 min for 95% of runs.

**Alternatives considered**:
  - Unlimited: ❌ Risks hung runs
  - Very short (<60s): ❌ Brittle under network fluctuations

## Unknowns Resolved

- **Compose schema version differences**: Treat as opaque mapping; let docker compose validate
- **Docker availability**: Pre-check using `docker --version` and `docker compose version` in activity
- **Log capture**: Capture stderr/stdout with tolerant decoding `errors='replace'` (per constitution)
- **Project naming**: Use `workflow.info().workflow_id` and `run_id` for unique project names (deterministic)
- **Health check requirement**: Spec requires health checks; fail early if missing for target service

## Risks & Mitigations

- **Large image pulls causing timeouts**: Document increasing startup timeout; allow pre-pulled images
- **Port conflicts**: Surface container errors promptly; suggest `docker ps`/`docker logs` for diagnostics
- **Multi-service ambiguity**: Explicit selection required when no default; documented in error messages
- **Resource accumulation**: Failed runs preserved; document manual cleanup commands in logs and results
- **Concurrent runs**: Unique project names prevent conflicts

## Technical Dependencies

- **PyYAML**: YAML parsing and validation (`uv add pyyaml`)
- **Docker Compose V2**: `docker compose` command (not legacy `docker-compose`)
- **Python stdlib**: `tempfile`, `subprocess`, `json`, `time`

