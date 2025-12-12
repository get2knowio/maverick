# Feature Specification: Agent Tool Permissions

**Feature Branch**: `021-agent-tool-permissions`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Reduce tool permissions across all agents to enforce orchestration pattern"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Constrained Agent Execution (Priority: P1)

As a workflow orchestrator, I need agents to only have access to tools relevant to their core judgment tasks, so that agents cannot accidentally interfere with git state, make unexpected API calls, or perform actions that should be handled by the Python orchestration layer.

**Why this priority**: This is the core architectural principle - agents should be limited to their area of expertise (code reading/writing, analysis, text generation) while the orchestration layer handles all external system interactions (git, GitHub API, test execution). This prevents agents from breaking workflow state and makes their behavior predictable.

**Independent Test**: Can be tested by executing each agent type and verifying they only have access to their designated tool set, and that attempts to perform orchestration actions (git operations, API calls) are not possible from within the agent.

**Acceptance Scenarios**:

1. **Given** an ImplementerAgent is executing, **When** it needs to make code changes, **Then** it can only use Read, Write, Edit, MultiEdit, Glob, and Grep tools
2. **Given** a CodeReviewerAgent is executing, **When** it analyzes code, **Then** it can only use Read, Glob, and Grep tools (read-only access)
3. **Given** a GeneratorAgent is executing, **When** it generates text (commit messages, PR descriptions), **Then** it has no tool access and relies solely on context provided in its prompt

---

### User Story 2 - Centralized Tool Set Management (Priority: P2)

As a developer maintaining the agent framework, I need a centralized definition of tool sets that can be reused across agents, so that tool permissions are consistent, documented, and easy to audit.

**Why this priority**: Without centralized tool set definitions, each agent would define its own tools, leading to inconsistency and making it difficult to audit what each agent can do. This supports the principle of least privilege.

**Independent Test**: Can be tested by verifying that tool set constants/enums exist and that all agents reference these shared definitions rather than hardcoding tool lists.

**Acceptance Scenarios**:

1. **Given** predefined tool set constants exist, **When** configuring an agent, **Then** the appropriate tool set constant can be assigned to enforce consistent permissions
2. **Given** a tool set is modified, **When** agents using that tool set are instantiated, **Then** all affected agents automatically receive the updated tool permissions

---

### User Story 3 - Context-Driven Agent Prompts (Priority: P2)

As a workflow orchestrator, I need agent system prompts to reflect their constrained role, so that agents understand they receive pre-gathered context and focus solely on their designated task without attempting actions they cannot perform.

**Why this priority**: Aligned system prompts prevent agents from wasting tokens attempting unavailable actions and ensure they operate within their designed boundaries. This improves efficiency and reliability.

**Independent Test**: Can be tested by reviewing agent system prompts and verifying they contain guidance about receiving pre-gathered context and not attempting orchestration actions.

**Acceptance Scenarios**:

1. **Given** an agent's system prompt, **When** the prompt is read, **Then** it contains no instructions about running git commands, creating PRs, or making API calls
2. **Given** an agent's system prompt, **When** the prompt is read, **Then** it includes guidance that context is pre-gathered and the orchestration layer handles validation

---

### User Story 4 - New FixerAgent for Validation Fixes (Priority: P3)

As a workflow orchestrator, I need a minimal FixerAgent specialized for applying validation fixes, so that validation error correction uses the smallest possible tool set and operates with laser focus on specific files.

**Why this priority**: A specialized FixerAgent with minimal tools (Read, Write, Edit only) provides a more secure and efficient option for applying targeted fixes compared to the full ImplementerAgent tool set.

**Independent Test**: Can be tested by instantiating a FixerAgent and verifying it has only Read, Write, and Edit tools, and can successfully apply a targeted fix to a specific file.

**Acceptance Scenarios**:

1. **Given** a validation error on a specific file, **When** FixerAgent is invoked, **Then** it can read the file, apply the fix, and write the changes
2. **Given** FixerAgent is executing, **When** it attempts code search operations, **Then** it cannot use Glob or Grep (must be given explicit file paths)

---

### Edge Cases

- What happens when an agent encounters a task that would require tools it doesn't have? The agent should recognize the limitation and report what it cannot do, allowing the orchestration layer to handle the situation.
- How does the system handle agents that previously relied on removed tools? System prompts must be updated to remove references to unavailable tools, and workflows must be refactored to provide necessary context upfront.
- What happens if a GeneratorAgent needs to inspect code to generate accurate descriptions? The workflow must gather and provide all necessary code context in the prompt before invoking the generator.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST define a ToolSet enum or constants module containing predefined tool permission sets
- **FR-002**: ImplementerAgent MUST be configured with only Read, Write, Edit, MultiEdit, Glob, and Grep tools (no Bash)
- **FR-003**: CodeReviewerAgent MUST be configured with only Read, Glob, and Grep tools (read-only, no Bash)
- **FR-004**: IssueFixerAgent MUST be configured with only Read, Write, Edit, Glob, and Grep tools (no Bash, no GitHub MCP tools)
- **FR-005**: System MUST implement a new FixerAgent with only Read, Write, and Edit tools
- **FR-006**: GeneratorAgents (CommitMessageGenerator, PRDescriptionGenerator, etc.) MUST be configured with no tools (empty tool list)
- **FR-007**: All agent system prompts MUST be updated to remove instructions about git commands, PR creation, and API calls
- **FR-008**: All agent system prompts MUST include guidance stating that context is pre-gathered and the orchestration layer handles validation
- **FR-009**: Workflows MUST be refactored to provide necessary context (git diffs, file contents, etc.) in agent prompts rather than expecting agents to gather it themselves

### Key Entities

- **ToolSet**: A named collection of tool identifiers representing permissions for a category of agent operations (implementation, review, fix, generation)
- **Agent**: An AI-powered component that performs a specific judgment task using its assigned tool set
- **Orchestration Layer**: The Python code that manages agent execution, provides context, and handles all external system interactions

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All agents operate with their designated minimal tool sets without requiring additional tools for their core tasks
- **SC-002**: No agent can execute git commands, GitHub API calls, or test execution directly
- **SC-003**: Agent execution is faster due to reduced tool options that the model must consider
- **SC-004**: All agent behaviors are predictable and auditable by examining their tool set assignment
- **SC-005**: Workflows successfully provide all necessary context to agents without agents needing to gather it themselves
- **SC-006**: System maintains all existing functionality with agents operating under reduced permissions

## Assumptions

- The Python orchestration layer already exists or will be implemented to handle git operations, GitHub API calls, and test execution (per spec 020)
- The Claude Agent SDK supports restricting tools available to agents via the `allowed_tools` parameter
- Workflows can be refactored to pre-gather context (git diffs, file contents) before invoking agents
- Agents will cooperate with their constraints and not attempt to work around missing tools
