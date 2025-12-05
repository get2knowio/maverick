# Migration Guide

## What Changed (v2.0)

Maverick has been restructured to a cleaner plugin architecture with consolidated commands.

## Current Structure

```
.claude-plugin/
├── marketplace.json        # Marketplace catalog
└── plugin.json             # Marketplace manifest
plugins/
└── maverick/               # Workflow automation plugin
    ├── .claude-plugin/
    │   └── plugin.json
    ├── commands/
    │   ├── fly.md          # Spec-based workflow
    │   └── refuel.md       # Tech-debt resolution
    ├── agents/
    │   ├── rust-code-reviewer.md
    │   ├── speckit-rust-implementer.md
    │   ├── spec-compliance-reviewer.md
    │   └── issue-implementer.md
    ├── skills/
    │   ├── code-review/
    │   │   └── SKILL.md
    │   └── validation/
    │       └── SKILL.md
    └── scripts/
        ├── sync-branch.sh
        ├── get-changed-files.sh
        ├── run-validation.sh
        ├── manage-pr.sh
        └── notify.sh
```

## Migration Path

### From Previous Versions

If you previously installed maverick:

```
# Remove old installation
/plugin uninstall maverick

# Add marketplace and reinstall
/plugin marketplace add get2knowio/maverick
/plugin install maverick
```

### Command Changes

| Old Command | New Command | Description |
|-------------|-------------|-------------|
| `/project:fly` | `/fly` | Spec-based development workflow |
| `/maverick.fly` | `/fly` | Spec-based development workflow |
| `/techdebt.delegate` | `/refuel` | Tech-debt resolution (now built-in) |

## Key Changes

1. **Simplified command names** - Commands no longer have plugin prefix (plugin namespace is automatic)
2. **Tech debt is built-in** - The `/refuel` command replaces the separate tech-debt plugin
3. **Added Skills** - Reusable workflow skills for code review and validation
4. **New agent** - `issue-implementer` for GitHub issue resolution

## Benefits

1. **Single plugin** - Everything in one place
2. **Shared workflows** - Skills reduce duplication between commands
3. **Cleaner names** - `/fly` and `/refuel` are shorter and clearer
4. **Consistent approach** - Same review and validation for all workflows

## Documentation

See [plugins/maverick/README.md](plugins/maverick/README.md) for full documentation.
