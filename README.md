# Maverick

[![CI](https://github.com/get2knowio/maverick/actions/workflows/ci.yml/badge.svg)](https://github.com/get2knowio/maverick/actions/workflows/ci.yml)
[![npm version](https://img.shields.io/npm/v/@get2knowio/maverick)](https://www.npmjs.com/package/@get2knowio/maverick)
[![license: MIT](https://img.shields.io/npm/l/@get2knowio/maverick)](LICENSE)

**Maverick** is an AI-powered workflow automation toolkit that orchestrates multi-phase development tasks using AI agents like OpenAI Codex and CodeRabbit. It reads structured task specifications, executes implementation phases, performs code reviews, and applies fixes—all while maintaining progress tracking and deterministic execution.

## Features

- 📋 **Task-driven workflows**: Parse structured `tasks.md` files with phase-based task lists
- 🤖 **AI agent orchestration**: Integrate with `opencode` (OpenAI) and `coderabbit` for implementation and review
- 🔄 **Iterative execution**: Automatically re-run phases until all tasks are complete
- 📊 **Progress tracking**: Real-time heartbeat monitoring and verbose logging
- 🎯 **Modular step system**: Clean separation between step description, execution, and workflow logic
- 🔌 **Extensible**: Easy-to-use DSL for adding new step types and workflows

## Installation

```bash
npm install -g @get2knowio/maverick
```

You can also invoke without a global install:

```bash
npx @get2knowio/maverick --help
```

## Usage

### Basic Command

```bash
maverick <branch> [options]
```

The CLI creates a temporary git worktree based on your branch (`origin/<branch>` if available, otherwise a local `<branch>`, otherwise `main`) and looks for `specs/<branch>/tasks.md` by default.

### Examples

```bash
# Run workflow for a specific branch (looks for specs/<branch>/tasks.md)
maverick 006-build-subcommand

# Enable verbose logging
maverick 006-build-subcommand --verbose

# Use custom tasks file
maverick 006-build-subcommand --tasks custom-tasks.md

# Override AI models for different phases
maverick 006-build-subcommand \
  --build-model github-copilot/gpt-4o \
  --review-model github-copilot/claude-sonnet-4.5
```

### Options

| Flag | Short | Description | Default |
|------|-------|-------------|---------|
| `--branch` | `-b` | Override branch name | Required (positional arg or `--branch`) |
| `--tasks` | `-t` | Override tasks file path | `specs/<branch>/tasks.md` |
| `--build-model` | | Model for implementation phases | `github-copilot/claude-sonnet-4.5` |
| `--review-model` | | Model for review phase | `github-copilot/claude-sonnet-4.5` |
| `--fix-model` | | Model for fix phase | `github-copilot/claude-sonnet-4.5` |
| `--keep-worktree` | | Keep the temporary worktree after successful runs (worktrees are always preserved on failure) | `false` |
| `--reuse-worktree` | | Reuse existing worktree if one exists (default: automatically removes and creates fresh) | `false` |
| `--verbose` | `-v` | Enable verbose internal logging | `false` |
| `--help` | | Show help message | |

## Task File Format

Maverick expects a `tasks.md` file with the following structure:

```markdown
## Phase 1: Setup Infrastructure

- [ ] Initialize project configuration
- [ ] Set up CI/CD pipeline
- [x] Configure linting rules

## Phase 2: Implement Core Features

- [ ] Add authentication module
- [ ] Implement data validation
- [ ] Write unit tests
```

Phases are identified by `## Phase <identifier>: <title>` headers. Tasks use standard Markdown checkbox syntax (`- [ ]` for incomplete, `- [x]` for complete).

## Workflow Phases

1. **Implementation**: Executes each phase with outstanding tasks using AI agents
2. **Review**: Runs CodeRabbit and Opencode reviews (generates `coderabbit.md` and `review.md`)
3. **Fix**: Addresses issues identified in reviews

## Architecture

Maverick is modular and extensible, organized into clear layers:

### Core Modules

- **`src/steps/core.mjs`**: Step execution engine (`executeStep`, `executeSteps`, execution primitives)
- **`src/steps/{shell,opencode,coderabbit}.mjs`**: Generic step type factories for different command types
- **`src/steps/speckit.mjs`**: Domain-specific workflow steps (`opencodeImplementPhase`, `coderabbitReview`, `opencodeReview`, `opencodeFix`)
- **`src/tasks/markdown.mjs`**: Task file parsing and validation
- **`src/workflows/default.mjs`**: Default workflow implementation (phase execution → review → fix)
- **`src/workflow.mjs`**: CLI entry point

### Design Principles

1. **Step Description**: Plain data objects describing *what* to run (no side effects)
2. **Step Execution**: Centralized logic for *how* to run steps (logging, timing, capture)
3. **Workflow Orchestration**: High-level flow control (parsing, iteration, phase management)

External users can:
- Create custom step types by implementing new `src/steps/*.mjs` modules
- Create custom workflows by implementing new `src/workflows/*.mjs` modules
- Reuse the core execution engine without depending on specific step types

See [CONTRIBUTING.md](./CONTRIBUTING.md) for detailed architecture documentation and extension guides.

## Dependencies

- **[execa](https://github.com/sindresorhus/execa)**: Process execution with streaming output
- **[listr2](https://github.com/listr2/listr2)**: Task list UI rendering
- **[meow](https://github.com/sindresorhus/meow)**: CLI argument parsing

## Requirements

- Node.js 18+ (ESM support required)
- `opencode` CLI (for AI implementation)
- `coderabbit` CLI (for code review)
- Git repository context

## OpenCode Configuration

Maverick automatically configures OpenCode with full permissions to avoid repeated prompts during workflow execution. This is done by:

1. Bundling a Maverick-specific config file at `config/opencode-maverick.json` with all permissions set to `"allow"`
2. Passing this config via the `OPENCODE_CONFIG` environment variable when invoking OpenCode

The config uses OpenCode's deep merge strategy, which means:
- **Maverick's permission settings are applied** to prevent workflow interruptions
- **Your project's existing OpenCode config is preserved** (models, themes, agents, etc.)
- **Non-conflicting settings from both configs are combined**

If your project has an existing `opencode.json` or `.opencode/opencode.json`, Maverick's permissions will be merged with your settings without overriding your model configurations or other preferences.

## Development

```bash
# Run workflow with verbose logging
npm run maverick -- 006-build-subcommand --verbose

# Test with custom task file
npm run maverick -- my-branch --tasks ./custom/tasks.md
```

## License

MIT
