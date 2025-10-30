# Feature Specification: Containerized Validation with Docker Compose

**Feature Branch**: `001-docker-compose-runner`  
**Created**: 2025-10-30  
**Status**: Draft  
**Input**: User description: "Add a step to our workflow that runs before our existing steps that spins up a Docker container via Docker Compose. Then, all of our existing subsequent validation steps will be executed on that Docker container using Docker Compose exec. The Docker Compose YAML will be provided as a parameter to the workflow and made available to this activity."

## Clarifications

### Session 2025-10-30

- Q: Which Docker Compose version should the implementation target? → A: Docker Compose V2 (integrated `docker compose` plugin)
- Q: What is the maximum allowed size for the Docker Compose YAML parameter? → A: 1 MB (allows complex multi-service setups with extended configs)
- Q: How long should failed containers be retained before automatic cleanup? → A: No automatic cleanup (could fail overnight)
- Q: How should Docker Compose project names be managed to avoid conflicts between concurrent or successive workflow runs? → A: Generate unique project name per workflow run (e.g., `maverick-<workflow_id>-<run_id>`)
- Q: Should the workflow require Docker Compose health checks to be defined for the target service? → A: Required with validation - check health status before running validations

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Run validations inside a container (Priority: P1)

As a developer running the readiness workflow, I can provide a Docker Compose YAML so that the workflow brings up a fresh containerized environment before any checks, and all existing validation steps execute inside that environment, returning the same structured results as today.

**Why this priority**: Enables consistent, reproducible validation across machines by isolating checks in a container; foundational for subsequent scenarios.

**Independent Test**: Trigger the workflow with a valid Compose YAML that starts a single service. Verify the environment starts, validations run inside the container, and the workflow returns a readiness summary.

**Acceptance Scenarios**:

1. **Given** a valid Compose YAML with one service, **When** the workflow starts, **Then** it starts the container(s) before any validation and executes all checks inside the container, returning a readiness summary.
1. **Given** a valid Compose YAML and successful container startup, **When** validations complete, **Then** the environment is cleaned up automatically and results are recorded.

---

### User Story 2 - Fail fast on invalid configuration (Priority: P2)

As a developer, if the provided Compose YAML is invalid or the environment fails to start, I receive a clear, actionable error and the workflow stops before running validations, with no orphaned resources left behind.

**Why this priority**: Prevents wasted time running checks in a broken environment; reduces local contamination.

**Independent Test**: Provide malformed YAML or a service that cannot start. Verify the workflow fails with a clear message and resources are cleaned up.

**Acceptance Scenarios**:

1. **Given** an invalid Compose YAML, **When** the workflow attempts to start the environment, **Then** it fails within the defined timeout and reports a human-readable error.
2. **Given** a startup failure after YAML is parsed (e.g., health check fails), **When** the workflow handles the error, **Then** it retains all created resources for manual troubleshooting and returns a failure with diagnostics and cleanup instructions.

---

### User Story 3 - Target a specific service (Priority: P3)

As a developer using a multi-service Compose file, I can specify which service is used for executing validations; if omitted, a sensible default is applied.

Default selection policy:
- If the Compose file defines exactly one service, that service is used.
- If multiple services are defined, the service named "app" is used.
- If multiple services are defined and no service named "app" exists, the workflow fails with a clear message requiring explicit service selection.

**Why this priority**: Many Compose setups have multiple services; the validation target must be explicit or sensibly defaulted.

**Independent Test**: Provide a Compose file with multiple services and specify the target service; verify checks run in that service. Repeat without specifying target to exercise default behavior.

**Acceptance Scenarios**:

1. **Given** a multi-service Compose YAML and a specified target service, **When** validations run, **Then** they execute in the specified service.
2. **Given** a multi-service Compose YAML and no target specified, **When** validations run, **Then** default target selection is applied consistently (see Clarification) and documented in results.

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

- Compose YAML refers to images that are slow to pull or unavailable (network issues, rate limits).
- Port conflicts or resource limits on the host prevent containers from starting.
- Docker/Compose is not installed or not accessible to the workflow host.
- Service reports healthy but required executables for validations are missing inside the container.
- Long-running startup with health checks exceeding the timeout window.
- Health check is not defined for the target service (workflow must fail with clear guidance).
- Health check is defined but never succeeds (workflow must fail after timeout with diagnostic information).
- Cleanup fails on success (e.g., volumes or networks remain) after graceful shutdown.
- User must manually clean up retained resources from failed runs; orphaned resources from prior failures may accumulate over time.

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: The workflow MUST accept a Docker Compose YAML as an input parameter and validate it before use. The YAML MUST define a health check for the target service.
- **FR-002**: The workflow MUST start a containerized environment from the provided Compose definition before any existing validation steps run. The system MUST wait for the target service to report healthy status before proceeding with validations.
- **FR-003**: The system MUST execute all existing validation steps inside the running environment for a single, well-defined service.
- **FR-004**: The system MUST provide a means to select the target service for execution; if not provided, the default selection policy applies: (a) use the single service if only one is defined; (b) if multiple services, use the service named "app"; (c) if multiple services and no "app" exists, fail with instructions to specify a service.
- **FR-005**: The system MUST expose clear, human-readable error messages when environment startup or in-container execution fails, including captured logs. If health checks fail or are not defined for the target service, the workflow MUST fail with specific guidance.
- **FR-006**: The system MUST enforce reasonable timeouts for environment startup (including health check validation) and for each validation step execution; timeouts SHOULD be configurable per run.
- **FR-007**: The system MUST tear down the environment on success and retain it indefinitely on failure to aid troubleshooting; failed environments require manual cleanup.
- **FR-008**: The system MUST avoid leaving orphaned containers, networks, or volumes created by the run. Each workflow run MUST use a unique Docker Compose project name derived from the workflow execution identifier (e.g., `maverick-<workflow_id>-<run_id>`) to prevent conflicts between concurrent or successive runs.
- **FR-009**: The system MUST perform early parameter validation (non-empty YAML, maximum size of 1 MB, valid YAML structure, optional target service name format).
- **FR-010**: The system MUST record in the readiness summary that validations ran inside a containerized environment and identify the target service used.
- **FR-011**: The system MUST fail fast if Docker Compose resources with conflicting names are detected, providing clear remediation steps. The use of unique project names per workflow run ensures concurrent executions do not interfere with each other.

### Key Entities *(include if feature involves data)*

- **ComposeConfig**: The provided YAML configuration (string) that defines services used for the validation environment.
- **TargetService**: The name of the service within the Compose config where validations are executed.
- **ContainerSession**: An identifier and metadata for the lifecycle of the containerized environment for a single workflow run (workflow ID, run ID, unique project name derived from these identifiers, start time, cleanup policy, status).
- **ValidationStep**: Existing validation operations that must be executed inside the selected service.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: With a valid configuration, the workflow starts a containerized environment and completes all current validation steps inside it within 5 minutes for 95% of runs.
- **SC-002**: On invalid configuration or startup failure, the workflow terminates within 60 seconds with a clear error message and leaves no residual environment resources.
- **SC-003**: Validation outcomes inside the containerized environment are consistent with non-containerized baseline outcomes for identical inputs in at least 95% of cases.
- **SC-004**: After successful runs, 100% of environment resources created by the workflow are cleaned up automatically. After failed runs, resources are retained indefinitely for troubleshooting and require manual cleanup.

## Assumptions

- A single target service is sufficient to execute all existing validation steps.
- The provided configuration includes any dependencies required by the validations within the selected service.
- Access to a container runtime with Docker Compose V2 (`docker compose` plugin) is available wherever the workflow executes.
- If multiple services are present and none is named "app", callers will provide the explicit service name.
- The target service defines a health check in the Compose YAML; the workflow will not attempt to infer readiness through other means.

