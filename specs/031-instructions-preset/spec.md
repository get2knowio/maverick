# Feature Specification: Instructions Preset

**Feature Branch**: `031-instructions-preset`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Update Maverick's agent base class to use the Claude Agent SDK's claude_code system prompt preset instead of raw system prompt strings."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agents Inherit Claude Code Capabilities (Priority: P1)

As a Maverick workflow operator, when agents execute tasks (implementation, review, fixing), each agent automatically benefits from Claude Code's built-in system prompt — including tool usage patterns, code editing guidelines, and safety guardrails — without the agent author needing to replicate any of that guidance manually.

**Why this priority**: This is the core value proposition. Without the preset, every agent must manually encode Claude Code's capabilities, leading to drift, inconsistency, and missed capabilities as Claude Code evolves.

**Independent Test**: Can be fully tested by running any MaverickAgent-based agent and verifying it exhibits Claude Code behaviors (e.g., reads files before editing, uses dedicated tools instead of shell commands) that are NOT mentioned in its agent-specific instructions.

**Acceptance Scenarios**:

1. **Given** a MaverickAgent with role-specific instructions only (e.g., "You are a code reviewer"), **When** the agent is invoked, **Then** it also follows Claude Code conventions (e.g., preferring Edit over sed) even though those conventions are not in its instructions.
2. **Given** the Claude Code preset is updated in a new SDK version, **When** agents are run with the updated SDK, **Then** agents automatically benefit from the new preset behavior without any Maverick code changes.
3. **Given** a MaverickAgent with an empty instructions string, **When** the agent is invoked, **Then** it operates with the full Claude Code preset as its system prompt.

---

### User Story 2 - Clear Separation of Instructions from System Prompt (Priority: P2)

As a developer creating or maintaining a Maverick agent, I can clearly distinguish between the agent's role-specific guidance (its "job description") and the underlying system prompt. The parameter I provide describes WHO the agent is and HOW it should behave for its specific role — it does not replace or override the foundational system prompt.

**Why this priority**: Naming clarity prevents developers from accidentally overriding the entire system prompt when they only intend to add role-specific guidance. This reduces bugs and makes the agent API self-documenting.

**Independent Test**: Can be tested by reviewing the agent base class interface and confirming that the parameter for agent-specific guidance is named and documented distinctly from the system prompt concept.

**Acceptance Scenarios**:

1. **Given** a developer creating a new concrete agent, **When** they provide the agent's role-specific guidance, **Then** the parameter name and documentation make it clear this guidance is appended to (not replacing) the base system prompt.
2. **Given** a developer reading existing agent code, **When** they see the role guidance parameter, **Then** they understand it is the agent's "job description" without needing to trace through the base class implementation.

---

### User Story 3 - Project and User Configuration Loaded Automatically (Priority: P3)

As a developer working on a project that uses Maverick, project-level configuration files (e.g., CLAUDE.md) and user-level configuration are automatically loaded by all agents. This means project-specific coding conventions, architectural decisions, and team standards are available to every agent without explicit configuration.

**Why this priority**: Ensures agents respect the project's established conventions and the user's personal preferences, improving output quality and reducing manual correction.

**Independent Test**: Can be tested by placing a project-level configuration file with a distinctive instruction (e.g., "Always use tabs for indentation") and verifying that agents follow it.

**Acceptance Scenarios**:

1. **Given** a project with a CLAUDE.md file containing specific conventions, **When** any MaverickAgent runs in that project, **Then** the agent follows those conventions in its output.
2. **Given** a user with personal configuration preferences, **When** any MaverickAgent runs, **Then** the agent respects those user-level settings.
3. **Given** a project with no CLAUDE.md file, **When** any MaverickAgent runs, **Then** the agent operates normally using only the preset and its own instructions.

---

### Edge Cases

- What happens when an agent's instructions string is empty? The agent should still function using the Claude Code preset alone.
- What happens when agent instructions contain markdown formatting or special characters? They should be passed through without corruption.
- How are agents that do NOT need Claude Code capabilities handled? One-shot generator-style agents (which produce structured output without interactive tool use) may use a direct system prompt instead of the preset, since they don't need Claude Code's tool-usage patterns.
- What happens when project-level and user-level settings conflict with agent instructions? The standard Claude Code precedence rules should apply (agent instructions are most specific and take priority).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All interactive agents (those that use tools and multi-turn conversations) MUST receive the Claude Code system prompt preset as their foundational prompt
- **FR-002**: Each agent's role-specific guidance MUST be appended to the preset, not used as a standalone replacement
- **FR-003**: The parameter for agent-specific guidance MUST be named to clearly indicate it is appended instructions, not a full system prompt
- **FR-004**: All interactive agents MUST load project-level and user-level configuration sources when constructing their system prompt
- **FR-005**: One-shot agents (generators that produce structured output without tool use) MAY use a direct system prompt without the preset, as they do not benefit from Claude Code's interactive capabilities
- **FR-006**: Agents with no role-specific guidance (empty instructions) MUST still function correctly using the preset alone
- **FR-007**: All existing concrete agent implementations MUST be updated to use the new parameter naming convention

### Key Entities

- **MaverickAgent**: The abstract base class for all interactive, tool-using agents. Owns the preset configuration and instructions-appending behavior.
- **GeneratorAgent**: A separate base class for one-shot, structured-output agents. Does not use the preset pattern.
- **Agent Instructions**: Role-specific guidance text that describes who the agent is and how it should behave for its specific task domain. Appended to the preset.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of interactive agents use the Claude Code preset as their foundational system prompt
- **SC-002**: Zero agent implementations pass a raw system prompt string that replaces the preset (for interactive agents)
- **SC-003**: All existing agent test suites pass without modification to agent behavior (behavioral backward compatibility)
- **SC-004**: A new agent can be created by providing only role-specific instructions, with no need to manually include Claude Code conventions
- **SC-005**: Project-level configuration files are loaded by all interactive agents without explicit per-agent setup

## Assumptions

- The Claude Agent SDK supports the preset system prompt pattern with an append mechanism.
- The Claude Agent SDK supports loading project-level and user-level setting sources.
- The GeneratorAgent hierarchy intentionally does not need the Claude Code preset, as generators are one-shot and do not use interactive tools.
- Existing agent prompt constants (the role-specific guidance strings) are valid as "instructions" appended to the preset — they do not rely on being the entire system prompt.
- The Claude Code preset includes all standard Claude Code behaviors (tool usage patterns, file editing conventions, safety guardrails) and is maintained by the SDK.
