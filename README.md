# Maverick

A Claude Code plugin for AI-powered development workflow automation.

## Installation

### Add the Marketplace

```
/plugin marketplace add get2knowio/maverick
```

### Install the Plugin

```
/plugin install maverick
```

## Overview

Maverick orchestrates the full development cycle with AI-powered automation:

1. **Feature Implementation** - Execute tasks from a structured task list using parallel subagents
2. **Tech Debt Resolution** - Pick up and fix GitHub issues in parallel
3. **Code Review** - Run automated reviews (CodeRabbit + architecture analysis) and fix issues
4. **Convention Learning** - Update project conventions based on review findings
5. **PR Management** - Create or update pull requests with comprehensive summaries

## Commands

| Command | Description |
|---------|-------------|
| `/fly [branch-name]` | Run the full spec-based workflow |
| `/refuel [label]` | Pick up and fix tech-debt issues (default label: `tech-debt`) |

## Agents

| Agent | Purpose |
|-------|---------|
| `rust-code-reviewer` | Senior Rust code reviewer |
| `speckit-rust-implementer` | Speckit specification implementer |
| `spec-compliance-reviewer` | Specification compliance validator |
| `issue-implementer` | GitHub issue fixer for tech-debt |

## Skills

| Skill | Purpose |
|-------|---------|
| `code-review-workflow` | Parallel CodeRabbit + architecture review with fix execution |
| `validation-workflow` | Format/lint/build/test validation with iterative fixes |

[Full documentation](plugins/maverick/README.md)

## Plugin Structure

```
plugins/
└── maverick/
    ├── .claude-plugin/
    │   └── plugin.json     # Plugin manifest
    ├── commands/           # Slash commands
    ├── agents/             # Agent definitions
    ├── skills/             # Reusable workflow skills
    └── scripts/            # Shell scripts
```

## Requirements

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- [GitHub CLI](https://cli.github.com/) (`gh`) for PR and issue management
- Git repository with remote origin
- Optional: [CodeRabbit CLI](https://coderabbit.ai/) for enhanced code review
- Optional: [ntfy](https://ntfy.sh) for push notifications

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT
