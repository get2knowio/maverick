# Feature Specification: Maverick Foundation - Project Skeleton & Configuration System

**Feature Branch**: `001-maverick-foundation`
**Created**: 2025-12-12
**Status**: Draft
**Input**: Create a spec for the foundation of "Maverick", a Python CLI application that automates AI-powered development workflows using the Claude Agent SDK. Requirements: Python 3.10+ project using pyproject.toml, Dependencies (claude-agent-sdk, textual, click, pyyaml, pydantic), src/maverick layout, Configuration system using Pydantic models with YAML config files, environment variable overrides, and settings for GitHub integration, notifications, model selection, parallel execution limits, and agent-specific configs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Developer Installs Maverick (Priority: P1)

A developer wants to install Maverick into their Python environment to begin using AI-powered development workflows.

**Why this priority**: Installation is the first interaction any user has with the application. Without successful installation, no other features can be used.

**Independent Test**: Can be tested by running pip install on the project and verifying the `maverick` command is available in the terminal.

**Acceptance Scenarios**:

1. **Given** a Python 3.10+ environment, **When** developer runs `pip install .` in the project root, **Then** the `maverick` command becomes available in the terminal
2. **Given** an installed Maverick package, **When** developer runs `maverick --version`, **Then** the current version number is displayed
3. **Given** an installed Maverick package, **When** developer runs `maverick --help`, **Then** available commands and options are displayed

---

### User Story 2 - Developer Configures Maverick for Their Project (Priority: P2)

A developer wants to configure Maverick with project-specific settings such as GitHub repository details, notification preferences, and model selection so that workflows operate correctly within their project context.

**Why this priority**: Configuration is essential before any workflow can execute. Without proper configuration, workflows would fail or behave unexpectedly.

**Independent Test**: Can be tested by creating a `maverick.yaml` file in a project directory and verifying Maverick loads the settings correctly.

**Acceptance Scenarios**:

1. **Given** a project directory without configuration, **When** developer runs a Maverick command, **Then** Maverick uses sensible defaults and informs the user about the default configuration being used
2. **Given** a `maverick.yaml` file in the project root, **When** developer runs a Maverick command, **Then** Maverick loads and applies those project-specific settings
3. **Given** conflicting settings in project config and environment variables, **When** developer runs a Maverick command, **Then** environment variables take precedence over file-based configuration
4. **Given** a configuration file with an invalid structure, **When** developer runs a Maverick command, **Then** Maverick displays clear error messages identifying the invalid fields

---

### User Story 3 - Developer Uses User-Level Configuration (Priority: P3)

A developer wants to set personal preferences (like preferred notification settings or default model) that apply across all their projects without repeating configuration in each project.

**Why this priority**: User-level configuration improves developer experience by reducing repetitive setup, but projects can function with only project-level config.

**Independent Test**: Can be tested by creating a config file at `~/.config/maverick/config.yaml` and verifying settings are applied when running Maverick in a project without local configuration.

**Acceptance Scenarios**:

1. **Given** a config file at `~/.config/maverick/config.yaml`, **When** developer runs Maverick in any project directory, **Then** those user-level settings are applied
2. **Given** both user-level and project-level configuration files, **When** developer runs Maverick, **Then** project-level settings override user-level settings for conflicting keys
3. **Given** partial configuration at user-level and partial at project-level, **When** developer runs Maverick, **Then** the configurations are merged with project taking precedence

---

### User Story 4 - Developer Adjusts Logging Verbosity (Priority: P4)

A developer troubleshooting an issue wants to increase logging verbosity to understand what Maverick is doing internally.

**Why this priority**: Debugging capability is important for troubleshooting but not required for basic operation.

**Independent Test**: Can be tested by running a command with `-v` flag and observing more detailed log output.

**Acceptance Scenarios**:

1. **Given** default settings, **When** developer runs a Maverick command, **Then** only warnings and errors are displayed
2. **Given** the `-v` flag, **When** developer runs a Maverick command, **Then** informational messages are also displayed
3. **Given** the `-vv` flag, **When** developer runs a Maverick command, **Then** debug-level messages are displayed
4. **Given** `verbosity: debug` in configuration, **When** developer runs a Maverick command without flags, **Then** debug-level messages are displayed

---

### Edge Cases

- What happens when the config file exists but is empty? System uses defaults and logs a warning about the empty configuration file.
- What happens when environment variables contain invalid values (e.g., non-integer for parallel limit)? System displays a clear validation error identifying the problematic variable.
- What happens when the user config directory doesn't exist? System creates it on first use if needed, or operates without user-level config.
- What happens when config file has unknown keys? System ignores unknown keys and logs a warning to alert the user.
- What happens when required settings are missing? System uses defaults where reasonable, or displays clear error messages for truly required settings.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST use `pyproject.toml` as the sole build configuration file (no setup.py)
- **FR-002**: System MUST use the `src/maverick/` package layout structure
- **FR-003**: System MUST declare dependencies on: claude-agent-sdk, textual, click, pyyaml, pydantic (using minimum version pins, e.g., `click>=8.1`)
- **FR-004**: System MUST expose a `maverick` CLI entry point when installed
- **FR-005**: System MUST provide `--version` and `--help` options at the root command level
- **FR-006**: System MUST load configuration from YAML files in this priority order (highest to lowest): project (`maverick.yaml` in current directory), user (`~/.config/maverick/config.yaml`), built-in defaults
- **FR-007**: System MUST support environment variable overrides with the `MAVERICK_` prefix (e.g., `MAVERICK_GITHUB_OWNER` overrides `github.owner`)
- **FR-008**: System MUST use Pydantic models for configuration validation and parsing
- **FR-009**: System MUST define a `MaverickConfig` model as the central configuration object
- **FR-010**: Configuration MUST include a `github` section with settings for: repository owner, repository name, default branch
- **FR-011**: Configuration MUST include a `notifications` section with settings for: ntfy server URL, ntfy topic name, enable/disable flag
- **FR-012**: Configuration MUST include a `model` section with settings for: model identifier (e.g., `claude-sonnet-4-20250514`, `claude-opus-4-20250514`; default: `claude-sonnet-4-20250514`), maximum tokens (default: 8192), temperature (default: 0.7)
- **FR-013**: Configuration MUST include a `parallel` section with settings for: maximum concurrent agents, maximum concurrent tasks
- **FR-014**: Configuration MUST include an `agents` section allowing agent-specific configuration overrides
- **FR-015**: System MUST configure Python logging with configurable verbosity levels (error, warning, info, debug)
- **FR-016**: System MUST support verbosity configuration via CLI flags (`-v`, `-vv`) and configuration file
- **FR-017**: System MUST display clear, actionable error messages when configuration validation fails
- **FR-018**: System MUST merge configurations from multiple sources, with more specific sources overriding more general ones
- **FR-019**: System MUST NOT support sensitive values (API keys, tokens) in YAML configuration files; secrets MUST be provided exclusively via environment variables
- **FR-020**: System MUST define a `MaverickError` base exception class and a `ConfigError` subclass for configuration-related errors

### Key Entities

- **MaverickConfig**: The root configuration object containing all settings. Composed of nested configuration sections for different concerns.
- **GitHubConfig**: Settings for GitHub integration including repository owner, name, and default branch.
- **NotificationConfig**: Settings for ntfy-based push notifications including server URL, topic, and enable flag.
- **ModelConfig**: Settings for Claude model selection including model ID, max tokens, and temperature.
- **ParallelConfig**: Settings for concurrency limits including max agents and max tasks.
- **AgentConfig**: Flat key-value configuration for a single agent, supporting overrides for model, max_tokens, and temperature. Accessed via `agents.<agent_name>.<setting>` (e.g., `agents.code_reviewer.model`).
- **MaverickError**: Base exception class for all Maverick-specific errors. Enables consistent error handling at CLI boundaries.
- **ConfigError**: Subclass of MaverickError for configuration loading, parsing, and validation errors.

## Out of Scope

The following are explicitly excluded from this foundation spec and will be addressed in separate features:

- **Workflow logic**: FlyWorkflow, RefuelWorkflow, and any orchestration logic
- **Agent implementations**: CodeReviewerAgent, and other concrete agent classes
- **TUI application**: Textual screens, widgets, and interactive UI components
- **MCP tool definitions**: Custom tools for GitHub, notifications, or other integrations
- **Hooks**: Safety and logging hook implementations

This spec focuses solely on project skeleton, CLI entry point, and configuration system.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developer can install Maverick and execute `maverick --help` within 1 minute of cloning the repository
- **SC-002**: Configuration errors produce human-readable messages that identify the specific field and expected format
- **SC-003**: 100% of configuration fields have documented defaults, so Maverick runs without any configuration file
- **SC-004**: Environment variable overrides work for all configuration fields using consistent `MAVERICK_SECTION_KEY` naming
- **SC-005**: Configuration loading from all three sources (project, user, defaults) completes in under 100 milliseconds
- **SC-006**: All configuration models have complete type hints and validate input data on load

## Clarifications

### Session 2025-12-12

- Q: How should Maverick handle sensitive values (API keys, tokens) in configuration files? → A: Environment variables only for secrets (no file storage)
- Q: What structure should the `agents` configuration section use for agent-specific overrides? → A: Flat key-value pairs per agent name (e.g., `agents.code_reviewer.model`)
- Q: What should be explicitly out of scope for this foundation spec? → A: Workflow logic, agent implementations, and TUI all excluded
- Q: How should dependency versions be specified in `pyproject.toml`? → A: Minimum version pins (e.g., `click>=8.1`) for flexibility
- Q: Should this foundation define a base exception hierarchy for Maverick? → A: Yes, define `MaverickError` base + `ConfigError` subclass now

## Assumptions

- The developer has Python 3.10 or higher installed on their system
- The developer has basic familiarity with CLI tools and YAML configuration files
- The ntfy notification service is optional; Maverick functions without it
- The GitHub CLI (`gh`) may not be installed; configuration validation does not require it
- Agent-specific configurations will be defined by future agent implementations; the system provides a flexible container
- The XDG Base Directory specification is followed for user config on Linux; `~/.config/maverick/` is used
