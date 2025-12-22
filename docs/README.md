# Maverick Documentation

AI-powered development workflow orchestration with autonomous agent execution.

## Overview

Maverick is a Python CLI/TUI application that orchestrates complex AI-powered development workflows using the Claude Agent SDK. It automates the complete development lifecycle from task implementation through code review, validation, and PR management.

## Documentation Contents

### Presentations

- **[Training Slides](./slides/)** - Comprehensive training on Maverick's architecture, workflows, agents, and extensibility

### Quick Links

- [Main Repository](https://github.com/get2knowio/maverick)
- [Contributing Guide](https://github.com/get2knowio/maverick/blob/main/CONTRIBUTING.md)
- [Project Constitution](https://github.com/get2knowio/maverick/blob/main/.specify/memory/constitution.md)

## Key Features

- **Autonomous Agent Execution** - AI agents handle implementation, review, and fixes independently
- **Smart Workflow Orchestration** - DSL-based workflows with parallel execution and conditional logic
- **Interactive TUI** - Real-time visibility into agent operations
- **Resilient Operation** - Automatic retries, checkpointing, and graceful degradation
- **Extensible Architecture** - Custom workflows, agents, and MCP tools

## Getting Started

```bash
# Clone the repository
git clone https://github.com/get2knowio/maverick.git
cd maverick

# Install with pip
pip install -e .

# Initialize configuration
maverick config init

# Run a workflow
maverick fly feature-branch-name
```

## Architecture

```
CLI/TUI Layer (Click + Textual)
         ↓
Workflow Layer (Orchestration)
         ↓
Agent Layer (Claude Agent SDK)
         ↓
Tool Layer (MCP Tools)
```

## Core Workflows

| Workflow | Purpose |
|----------|---------|
| **FlyWorkflow** | Complete spec-based development from tasks.md to PR |
| **RefuelWorkflow** | Automated tech-debt resolution from GitHub issues |

## License

MIT
