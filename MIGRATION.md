# Migration Guide: Marketplace Structure

## What Changed (v2.0)

Maverick has been restructured from a single plugin to a **plugin marketplace** containing multiple plugins. This follows the idiomatic Claude Code plugin marketplace pattern.

## New Structure

```
.claude-plugin/
├── marketplace.json        # Marketplace catalog
└── plugin.json             # Marketplace manifest
plugins/
├── maverick/               # Workflow automation plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── commands/
│   │   └── maverick.fly.md
│   ├── agents/
│   │   ├── rust-code-reviewer.md
│   │   ├── speckit-rust-implementer.md
│   │   └── spec-compliance-reviewer.md
│   └── scripts/
│       ├── sync-branch.sh
│       ├── get-changed-files.sh
│       ├── run-validation.sh
│       ├── manage-pr.sh
│       └── notify.sh
└── tech-debt/              # Tech debt delegation plugin
    ├── .claude-plugin/
    │   └── plugin.json
    ├── commands/
    │   └── techdebt.delegate.md
    └── agents/
        └── tech-debt-delegator.md
```

## Migration Path

### From Single Plugin Installation

If you previously installed maverick as a single plugin:

```
# Remove old installation
/plugin uninstall maverick

# Add marketplace and reinstall
/plugin marketplace add get2knowio/maverick
/plugin install maverick
```

### Command Changes

| Old Command | New Command |
|-------------|-------------|
| `/project:fly` | `/maverick.fly` |
| `/maverick.delegate` | `/techdebt.delegate` |

### Installing Both Plugins

To get both plugins:

```
/plugin marketplace add get2knowio/maverick
/plugin install maverick tech-debt
```

### Installing Just One Plugin

You can install plugins individually:

```
# Just workflow automation
/plugin install maverick

# Just tech debt delegation
/plugin install tech-debt
```

## Breaking Changes

1. **Command namespaces changed** - Commands now use plugin-specific prefixes
2. **Tech debt is a separate plugin** - Must be installed separately if needed
3. **Script paths changed** - Internal script references updated (no user action needed)

## Benefits of Marketplace Structure

1. **Modular installation** - Install only what you need
2. **Independent versioning** - Plugins can be versioned separately
3. **Clearer organization** - Each plugin is self-contained
4. **Standard pattern** - Follows Claude Code plugin marketplace conventions

## Questions?

See individual plugin READMEs for detailed documentation:
- [plugins/maverick/README.md](plugins/maverick/README.md)
- [plugins/tech-debt/README.md](plugins/tech-debt/README.md)
