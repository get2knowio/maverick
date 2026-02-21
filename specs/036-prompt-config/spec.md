# Feature Specification: Three-Tier Prompt Configuration

**Feature Branch**: `036-prompt-config`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Implement the three-tier prompt configuration layer from ADR-001: Maverick defaults -> provider-specific defaults -> user overrides."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Default Prompts Work Without Configuration (Priority: P1)

A workflow author runs Maverick with zero prompt customization. Every agent and generator step receives its shipped default instructions automatically, without requiring any configuration in `maverick.yaml` or step-level overrides.

**Why this priority**: This is the foundation. If default prompts don't resolve correctly for every step, nothing else works. Every existing Maverick user depends on this behavior continuing seamlessly.

**Independent Test**: Run any built-in workflow (e.g., `fly-beads`) with no prompt-related configuration. All agents receive their expected instructions and produce correct output.

**Acceptance Scenarios**:

1. **Given** a project with no prompt configuration in `maverick.yaml`, **When** the `fly-beads` workflow executes an agent step (e.g., `implement`), **Then** the agent receives the shipped default instructions for that step name.
2. **Given** a project with no prompt configuration, **When** a generator step (e.g., `commit_message`) executes, **Then** the generator receives its shipped default system prompt.
3. **Given** a new agent is added to the registry without a matching default prompt entry, **When** the prompt resolution function is called, **Then** it raises a clear error indicating the missing default prompt.

---

### User Story 2 - Append Custom Guidance to a Step's Prompt (Priority: P2)

A workflow operator wants to add project-specific coding conventions (e.g., "always use snake_case for database columns") to the implementer agent without losing Maverick's default implementation instructions. They add a `prompt_suffix` to their project configuration, and it is appended to the default prompt at execution time.

**Why this priority**: This is the safest and most common customization. It preserves Maverick's carefully tuned defaults while allowing project-specific augmentation. Most users will start here.

**Independent Test**: Add a `prompt_suffix` for the `implement` step in `maverick.yaml`, run a workflow, and verify the agent's instructions contain both the default text and the appended suffix.

**Acceptance Scenarios**:

1. **Given** a `prompt_suffix` is configured for step `implement`, **When** prompt resolution runs, **Then** the resolved prompt equals the default instructions followed by a separator and the suffix text.
2. **Given** a `prompt_suffix` is configured for a step that only allows augmentation, **When** prompt resolution runs, **Then** the suffix is appended (not replaced) regardless of suffix length.
3. **Given** a `prompt_suffix` contains template variables (e.g., project type), **When** prompt resolution runs, **Then** template variables are rendered before appending.

---

### User Story 3 - Replace a Step's Prompt via File (Priority: P3)

A power user wants full control over the PR description generator's prompt. They write a custom prompt file and reference it in their configuration. Since PR description generation has unconstrained output (not consumed by downstream structured parsing), the system allows full replacement.

**Why this priority**: Full replacement is a power-user feature. It's important for teams with highly customized workflows but carries risk of breaking structured output contracts, so it must be gated by step-level policy.

**Independent Test**: Create a prompt file, reference it as `prompt_file` for a replaceable step, run the workflow, and verify the agent receives only the file's contents (not the default).

**Acceptance Scenarios**:

1. **Given** a `prompt_file` is configured for a step whose override policy is `replace`, **When** prompt resolution runs, **Then** the resolved prompt is the file's contents, not the default.
2. **Given** a `prompt_file` is configured for a step whose override policy is `augment_only`, **When** prompt resolution runs, **Then** the system raises an error explaining that full replacement is not allowed for this step.
3. **Given** a `prompt_file` path does not exist, **When** prompt resolution runs, **Then** the system raises a clear error with the missing file path.

---

### User Story 4 - Provider-Specific Prompt Variants (Priority: P4)

A team uses multiple AI providers (e.g., Claude for implementation, a different provider for review). Each provider has different prompt optimization needs. The prompt registry supports provider-keyed variants so that when a step is configured to use a specific provider, the provider-optimized prompt is selected automatically.

**Why this priority**: Multi-provider support is an advanced use case. Most teams use a single provider. However, the registry design must account for this from the start to avoid a breaking redesign later.

**Independent Test**: Register a provider-specific variant for a step, configure that step to use that provider, and verify the provider-specific prompt is selected over the generic default.

**Acceptance Scenarios**:

1. **Given** the registry has both a generic default and a provider-specific variant for step `review`, **When** prompt resolution runs with `provider="gemini"`, **Then** the Gemini-specific prompt is returned.
2. **Given** the registry has only a generic default for step `implement` (no provider variant), **When** prompt resolution runs with `provider="gemini"`, **Then** the generic default is returned as a fallback.
3. **Given** a provider variant exists but the step is configured with no explicit provider, **When** prompt resolution runs with the default provider, **Then** the generic default is returned (not the provider variant).

---

### Edge Cases

- What happens when both `prompt_suffix` and `prompt_file` are configured for the same step? The system rejects this as a configuration error at validation time (mutual exclusivity).
- What happens when a `prompt_file` uses a relative path? It is resolved relative to the project root (where `maverick.yaml` lives).
- What happens when a step name in user config doesn't match any registered step? The system raises a validation error listing valid step names.
- What happens when the default prompt registry is empty (e.g., during testing)? The system raises an error at workflow startup, not silently at step execution.
- What happens when a `prompt_suffix` is an empty string? It is treated as "no suffix" — the default prompt is returned unchanged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a prompt registry that maps step names to their default instructions text, shipped as part of Maverick's codebase.
- **FR-002**: The prompt registry MUST support a two-level key: `(step_name, provider)`, where provider defaults to a sentinel value meaning "generic/any provider."
- **FR-003**: The prompt registry MUST be populated at application startup by collecting existing agent prompt constants from their current locations (no duplication of prompt text into a second file).
- **FR-004**: System MUST provide a `resolve_prompt()` function that accepts a step name, provider, user overrides (suffix or file), and the registry, and returns the final resolved instructions string.
- **FR-005**: The resolution order MUST be: (1) select base prompt from registry using `(step_name, provider)` with fallback to `(step_name, generic)`, (2) if user `prompt_file` is configured and step policy allows replacement, use file contents as base, (3) if user `prompt_suffix` is configured, append it to the base prompt.
- **FR-006**: `prompt_suffix` and `prompt_file` MUST be mutually exclusive per step. Configuring both for the same step MUST raise a validation error.
- **FR-007**: Each step registered in the prompt registry MUST declare an override policy: either `replace` (allows full prompt replacement via `prompt_file`) or `augment_only` (only allows `prompt_suffix`).
- **FR-008**: When a `prompt_file` is configured for a step with `augment_only` policy, the system MUST raise a clear error at configuration validation time, not at step execution time.
- **FR-009**: When `prompt_suffix` is configured, the resolved prompt MUST be the base prompt followed by a clear separator (e.g., double newline and a heading) and then the suffix text.
- **FR-010**: The `prompt_file` path MUST be resolved relative to the project root when relative, or used as-is when absolute.
- **FR-011**: System MUST validate that referenced `prompt_file` paths exist and are readable at workflow startup (fail-fast), not at step execution time.
- **FR-012**: The prompt registry MUST be read-only after initialization. Runtime mutations are not permitted.
- **FR-013**: Generator agents (one-shot, using `system_prompt`) MUST participate in the same registry and resolution mechanism as interactive agents (using `instructions`).
- **FR-014**: The `resolve_prompt()` function MUST support template variable rendering (e.g., `$project_conventions`, `$validation_commands`) in both default prompts and user-supplied suffixes/files, using the existing `render_prompt()` mechanism.

### Key Entities

- **PromptRegistry**: An immutable mapping of `(step_name, provider)` to `PromptEntry` objects. Populated at startup from existing agent prompt constants.
- **PromptEntry**: Contains the default instructions text and the override policy (`replace` or `augment_only`) for a single step+provider combination.
- **OverridePolicy**: An enumeration with two values: `replace` (full replacement allowed) and `augment_only` (only suffix appending allowed).
- **PromptOverride**: User-provided override configuration for a single step, containing either `prompt_suffix` or `prompt_file` (mutually exclusive).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing workflows produce identical agent behavior when no prompt configuration is present (zero-regression on default prompts).
- **SC-002**: A user can append custom guidance to any step's prompt by adding a single configuration entry, without modifying Maverick source code.
- **SC-003**: A user can fully replace the prompt for steps that allow it, using a file path in configuration.
- **SC-004**: Attempting to replace the prompt for a step that requires structured output results in a clear, actionable error message before any agent execution begins.
- **SC-005**: Provider-specific prompt variants are selected automatically when a step targets a specific provider, with transparent fallback to the generic default.
- **SC-006**: All prompt resolution paths (default, suffix, file, provider variant) are covered by automated tests.
- **SC-007**: Configuration validation catches all invalid prompt configurations (missing files, mutual exclusivity violations, policy violations) at startup, not at runtime.

### Assumptions

- **A-001**: The `StepConfig` model from Spec 033 will be implemented (or its `prompt_suffix` and `prompt_file` fields will be made available) before or concurrently with this feature. If not yet available, this feature will define its own lightweight override model that can later be absorbed into `StepConfig`.
- **A-002**: The existing `render_prompt()` function in `skill_prompts.py` is the canonical template rendering mechanism and will be reused, not duplicated.
- **A-003**: The prompt registry does not need to support hot-reloading. Prompts are resolved once per step execution, and changes require restarting the workflow.
- **A-004**: Provider names are free-form strings (e.g., `"claude"`, `"gemini"`, `"openai"`), not an enum, to support future providers without code changes.
