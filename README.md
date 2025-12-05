# Maverick Plugins

A Claude Code plugin marketplace for AI-powered development workflow automation.

## Available Plugins

| Plugin | Description |
|--------|-------------|
| **[maverick](plugins/maverick/)** | Orchestrates multi-phase workflows: feature implementation, code review, convention updates, and PR management |
| **[tech-debt](plugins/tech-debt/)** | Analyzes and delegates technical debt issues for parallel resolution via Copilot |

## Installation

### Add the Marketplace

```
/plugin marketplace add get2knowio/maverick
```

### Install Individual Plugins

```
/plugin install maverick
/plugin install tech-debt
```

Or install both:

```
/plugin install maverick tech-debt
```

## Plugins

### Maverick

AI-powered development workflow automation that orchestrates the full development cycle:

1. **Feature Implementation** - Execute tasks from a structured task list using parallel subagents
2. **Code Review** - Run automated reviews (CodeRabbit + architecture analysis) and fix issues
3. **Convention Learning** - Update project conventions based on review findings
4. **PR Management** - Create or update pull requests with comprehensive summaries

**Commands:**
- `/maverick.fly [branch-name]` - Run the full workflow

**Agents:**
- `rust-code-reviewer` - Senior Rust code reviewer
- `speckit-rust-implementer` - Speckit specification implementer
- `spec-compliance-reviewer` - Specification compliance validator

[Full documentation](plugins/maverick/README.md)

### Tech Debt

Technical debt analysis and delegation for parallel issue resolution:

1. **Issue Discovery** - Retrieves open tech debt issues from GitHub
2. **Impact Analysis** - Analyzes file/module impact and conflict potential
3. **Delegation** - Assigns non-conflicting issues to Copilot for parallel work
4. **Reporting** - Generates structured summary reports

**Commands:**
- `/techdebt.delegate` - Analyze and delegate tech debt issues

**Agents:**
- `tech-debt-delegator` - Technical debt analyst for parallel assignment

[Full documentation](plugins/tech-debt/README.md)

## Marketplace Structure

```
.claude-plugin/
├── marketplace.json        # Marketplace catalog
└── plugin.json             # Marketplace manifest
plugins/
├── maverick/
│   ├── .claude-plugin/
│   │   └── plugin.json     # Plugin manifest
│   ├── commands/           # Slash commands
│   ├── agents/             # Agent definitions
│   └── scripts/            # Shell scripts
└── tech-debt/
    ├── .claude-plugin/
    │   └── plugin.json     # Plugin manifest
    ├── commands/           # Slash commands
    └── agents/             # Agent definitions
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
