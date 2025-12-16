# Feature Specification: Safety and Logging Hooks

**Feature Branch**: `007-safety-hooks`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create hooks system for safety validation and execution logging using Claude Agent SDK hook capabilities"

## Clarifications

### Session 2025-12-15

- Q: When a safety hook itself throws an exception during validation, should the system fail-open or fail-closed? → A: Fail-closed (block command with generic safety error, log hook failure)
- Q: How should compound commands (e.g., `ls && rm -rf /`) be handled? → A: Parse and check all components; block if any is dangerous
- Q: How should symlinks and relative paths be handled for sensitive path detection? → A: Resolve to canonical path using realpath() before checking
- Q: What should happen when metrics collection grows large due to high volume? → A: Rolling window—keep metrics for last N calls or T time period, discard older
- Q: How should unicode or escape sequences in paths/commands be handled? → A: Normalize first—decode escape sequences and normalize unicode before pattern matching

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Block Dangerous Bash Commands (Priority: P1)

When an agent attempts to execute a potentially destructive bash command (like `rm -rf /` or a fork bomb), the system intercepts the command before execution and blocks it, logging the attempt and notifying the agent that the command was rejected for safety reasons.

**Why this priority**: Preventing destructive system commands is the highest-priority safety concern. A single dangerous command could cause irreversible damage to the system or user data.

**Independent Test**: Can be fully tested by configuring the hook and attempting to execute known dangerous patterns, verifying they are blocked while safe commands execute normally.

**Acceptance Scenarios**:

1. **Given** safety hooks are enabled, **When** an agent attempts `rm -rf /home/user`, **Then** the command is blocked and the agent receives an error message explaining why
2. **Given** safety hooks are enabled, **When** an agent attempts a fork bomb pattern `:(){ :|:& };:`, **Then** the command is blocked before execution
3. **Given** safety hooks are enabled, **When** an agent attempts a normal safe command `ls -la`, **Then** the command executes normally
4. **Given** a custom blocklist is configured, **When** an agent attempts a command matching a custom pattern, **Then** the command is blocked

---

### User Story 2 - Block Writes to Sensitive Paths (Priority: P1)

When an agent attempts to write to a sensitive file path (like `.env` files, SSH keys, or system directories), the system intercepts the write operation and blocks it, protecting credentials and system integrity.

**Why this priority**: Preventing accidental or malicious writes to sensitive files is critical for security. Writing to `.env` or `.ssh` could expose credentials or compromise system access.

**Independent Test**: Can be fully tested by configuring the hook and attempting file writes to various sensitive and non-sensitive paths, verifying correct blocking behavior.

**Acceptance Scenarios**:

1. **Given** safety hooks are enabled, **When** an agent attempts to write to `.env`, **Then** the write is blocked with a clear error message
2. **Given** safety hooks are enabled, **When** an agent attempts to write to `~/.ssh/id_rsa`, **Then** the write is blocked
3. **Given** safety hooks are enabled, **When** an agent attempts to write to `/etc/passwd`, **Then** the write is blocked
4. **Given** an allowlist includes a specific `.env.example` path, **When** an agent writes to that path, **Then** the write is allowed
5. **Given** safety hooks are enabled, **When** an agent writes to a normal project file, **Then** the write proceeds normally

---

### User Story 3 - Log All Tool Executions (Priority: P2)

Every tool execution is logged with relevant details (tool name, sanitized inputs, duration, success/failure) for debugging, auditing, and understanding agent behavior. Logs are structured for easy searching and analysis.

**Why this priority**: Execution logging is essential for debugging workflows and understanding what agents did, but it doesn't prevent harm—it enables post-hoc analysis.

**Independent Test**: Can be fully tested by executing various tools and verifying log entries contain the expected fields with appropriate sanitization.

**Acceptance Scenarios**:

1. **Given** logging hooks are enabled, **When** any tool executes successfully, **Then** a log entry is created with tool name, duration, and success status
2. **Given** logging hooks are enabled, **When** a tool execution fails, **Then** a log entry is created with failure status and error summary
3. **Given** a tool receives sensitive input (containing passwords/tokens), **When** the tool executes, **Then** the log entry contains sanitized inputs with sensitive values redacted
4. **Given** a tool produces large output, **When** logged, **Then** the output summary is truncated to a reasonable length

---

### User Story 4 - Collect Execution Metrics (Priority: P2)

The system collects metrics about tool usage including call counts by tool type, success/failure rates, and execution times. These metrics enable monitoring workflow health and identifying performance bottlenecks.

**Why this priority**: Metrics provide operational visibility and help optimize workflows, but are less critical than safety and basic logging for initial operation.

**Independent Test**: Can be fully tested by executing a series of tools and querying the metrics collector to verify accurate counts and timings.

**Acceptance Scenarios**:

1. **Given** metrics collection is enabled, **When** tools are executed, **Then** call counts are incremented per tool type
2. **Given** metrics collection is enabled, **When** some tools succeed and some fail, **Then** success/failure rates are accurately tracked
3. **Given** metrics collection is enabled, **When** tools execute, **Then** execution times are recorded and can be queried for averages/percentiles
4. **Given** multiple workflows run concurrently, **When** metrics are queried, **Then** metrics accurately reflect all executions without data loss

---

### User Story 5 - Configure Hooks Per-Project (Priority: P3)

Project maintainers can configure which hooks are enabled/disabled and customize blocklists/allowlists through configuration. Different projects may have different security requirements.

**Why this priority**: Configuration flexibility is important for adoption but the default secure configuration covers most use cases.

**Independent Test**: Can be fully tested by loading different configurations and verifying hooks behave according to configuration.

**Acceptance Scenarios**:

1. **Given** a configuration disabling bash validation, **When** hooks are created, **Then** bash commands are not validated
2. **Given** a configuration with custom blocklist patterns, **When** hooks validate commands, **Then** custom patterns are enforced
3. **Given** a configuration with custom sensitive paths, **When** hooks validate file writes, **Then** custom paths are protected
4. **Given** no configuration file exists, **When** hooks are created, **Then** secure defaults are applied

---

### Edge Cases

- **Hook exception handling**: Safety hooks fail-closed—if a hook throws an exception during validation, the operation is blocked with a generic safety error and the hook failure is logged.
- **Compound command handling**: Compound commands (`&&`, `||`, `;`, `|`) are parsed and each component is validated; the entire command is blocked if any component matches a dangerous pattern.
- **Path resolution**: File paths are resolved to canonical form using `realpath()` (resolving symlinks and normalizing `..` sequences) before checking against sensitive path patterns.
- **Environment variable expansion**: Already covered by FR-008—environment variables in commands are expanded before validation.
- **Metrics memory bounds**: Metrics collector uses a rolling window, keeping data for a configurable number of calls or time period; older entries are discarded to bound memory usage.
- **Unicode/escape normalization**: Inputs are normalized (escape sequences decoded, unicode normalized) before pattern matching to prevent encoding-based bypass attempts.

## Requirements *(mandatory)*

### Functional Requirements

#### Hook Infrastructure

- **FR-001**: System MUST provide a `create_safety_hooks(config)` factory function that returns configured safety hooks
- **FR-002**: System MUST provide a `create_logging_hooks(config)` factory function that returns configured logging hooks
- **FR-003**: All hooks MUST be composable (multiple hooks can be combined and all execute in order)
- **FR-004**: All hooks MUST be independently testable without requiring a full agent setup
- **FR-005**: Hook factories MUST accept a `HookConfig` configuration object

#### Safety Hooks (PreToolUse)

- **FR-006**: `validate_bash_command` hook MUST block commands matching dangerous patterns:
  - `rm -rf` with root (`/`), home (`~`, `$HOME`), or system paths
  - Fork bombs and similar resource exhaustion patterns
  - Disk formatting commands (`mkfs`, `dd if=`)
  - Writes to system directories (`/etc`, `/usr`, `/bin`, `/sbin`)
- **FR-007**: `validate_bash_command` MUST support a configurable blocklist of additional patterns
- **FR-008**: `validate_bash_command` MUST expand environment variables and resolve relative paths before validation
- **FR-008a**: `validate_bash_command` MUST parse compound commands (`&&`, `||`, `;`, `|`) and validate each component; block if any component is dangerous
- **FR-008b**: `validate_bash_command` MUST normalize inputs (decode escape sequences, normalize unicode to NFC form) before pattern matching
- **FR-009**: `validate_file_write` hook MUST block writes to sensitive paths:
  - Environment files (`.env`, `.env.*`)
  - Secrets directories (`secrets/`, `.secrets/`)
  - SSH configuration (`~/.ssh/`)
  - Cloud credentials (`~/.aws/`, `~/.config/gcloud/`)
  - System paths (`/etc/`, `/usr/`, `/bin/`)
- **FR-010**: `validate_file_write` MUST support configurable allowlist (exceptions) and blocklist (additional paths)
- **FR-010a**: `validate_file_write` MUST resolve paths to canonical form using `realpath()` (resolving symlinks and normalizing relative paths) before pattern matching
- **FR-010b**: `validate_file_write` MUST normalize path inputs (decode escape sequences, normalize unicode) before pattern matching
- **FR-011**: Safety hooks MUST return a clear, actionable error message when blocking an operation
- **FR-011a**: Safety hooks MUST fail-closed—if a hook throws an exception during validation, the operation MUST be blocked with a generic safety error and the exception MUST be logged

#### Logging Hooks (PostToolUse)

- **FR-012**: `log_tool_execution` hook MUST log: tool name, sanitized inputs, duration (milliseconds), success/failure status, truncated output summary
- **FR-013**: `log_tool_execution` MUST sanitize sensitive data in inputs (passwords, tokens, API keys) before logging
- **FR-014**: `log_tool_execution` MUST truncate output summaries to a configurable maximum length (default 1000 characters)
- **FR-015**: `metrics_collector` hook MUST track: call counts per tool type, success count, failure count, execution times
- **FR-016**: `metrics_collector` MUST be async-safe for concurrent workflow execution (using asyncio synchronization primitives)
- **FR-017**: `metrics_collector` MUST provide methods to query current metrics (counts, rates, timing statistics)
- **FR-017a**: `metrics_collector` MUST use a rolling window (configurable max entries or time period) to bound memory usage; older entries are discarded

#### Configuration

- **FR-018**: `HookConfig` MUST include enable/disable flags for each hook type
- **FR-019**: `HookConfig` MUST include configurable patterns for bash command blocklist
- **FR-020**: `HookConfig` MUST include configurable paths for file write allowlist/blocklist
- **FR-021**: `HookConfig` MUST include log level and output destination settings
- **FR-022**: `HookConfig` MUST have secure defaults when not explicitly configured

### Key Entities

- **HookConfig**: Configuration dataclass containing enable flags, pattern lists, and settings for all hooks
- **SafetyHook**: PreToolUse hook that validates operations before execution and can block them
- **LoggingHook**: PostToolUse hook that records execution details after tool completion
- **MetricsCollector**: Stateful component that aggregates execution metrics across tool calls
- **ValidationResult**: Result of a safety validation: allowed (boolean), reason (string if blocked)
- **ToolExecutionLog**: Structured log entry with tool name, inputs, duration, status, output summary
- **ToolMetrics**: Aggregated metrics for a tool type: call_count, success_count, failure_count, avg_duration

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of known dangerous command patterns are blocked by safety hooks in testing
- **SC-002**: 0% false positives on a test suite of 100 common safe commands
- **SC-003**: All sensitive path patterns are correctly blocked with no bypasses via symlinks or path manipulation
- **SC-004**: Hook validation adds less than 10ms overhead to tool execution
- **SC-005**: Log entries are created for 100% of tool executions when logging is enabled
- **SC-006**: Sensitive data (passwords, tokens) never appears in plain text in logs
- **SC-007**: Metrics accurately reflect actual tool executions with less than 1% counting error under concurrent load
- **SC-008**: Hooks can be enabled/disabled without code changes through configuration
- **SC-009**: Each hook can be unit tested independently without requiring full agent infrastructure

## Assumptions

- Claude Agent SDK provides hook points for PreToolUse and PostToolUse events
- Hooks receive tool name, inputs, and (for PostToolUse) outputs/results
- The execution environment has standard Unix paths and conventions
- Log output is directed to standard logging infrastructure (configurable destination)
- Metrics are held in memory; persistence is out of scope for this feature
- Pattern matching uses standard glob/regex patterns supported by the runtime
- Workflows may run concurrently, requiring thread-safe metrics collection
