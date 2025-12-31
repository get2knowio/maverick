# Plugin Debugging Notes

Issues encountered and fixes applied to get the maverick plugin working with Claude Code.

## Issue 1: Install Path Mismatch

**Symptom**: Inconsistent UI states - "1 plugin available", "already installed", and "no plugins installed" shown simultaneously.

**Root Cause**: Claude Code's plugin installer ignores the `pluginRoot` field in `marketplace.json`. It was computing:
- `/opt/maverick` + `./maverick` = `/opt/maverick/maverick` (WRONG)

Instead of:
- `/opt/maverick` + `pluginRoot(../plugins)` + `./maverick` = `/opt/maverick/plugins/maverick` (CORRECT)

**Fix**: In `.claude-plugin/marketplace.json`, change the plugin `source` to include the full path:
```json
// Before (broken)
"source": "./maverick"

// After (working)
"source": "./plugins/maverick"
```

The `pluginRoot` field appears to be ignored, so the full relative path must be specified in `source`.

## Issue 2: Missing Command Frontmatter

**Symptom**: Plugin installed but slash commands (`/fly`, `/refuel`) not appearing.

**Root Cause**: Command markdown files were missing YAML frontmatter with `description` field.

**Fix**: Add frontmatter to all command files in `commands/`:
```markdown
---
description: Brief description of what the command does
---

# Command Title
...
```

## Issue 3: Explicit Path Declarations (Possibly)

**Symptom**: Commands still not appearing after frontmatter fix.

**Root Cause**: Explicit `commands` and `agents` paths in `plugin.json` may have been resolved incorrectly.

**Fix**: Remove explicit path declarations from `.claude-plugin/plugin.json`:
```json
// Before
{
  "name": "maverick",
  ...
  "commands": "./commands",
  "agents": "./agents"
}

// After
{
  "name": "maverick",
  ...
  // Let Claude Code auto-discover commands/ and agents/ at plugin root
}
```

Claude Code automatically discovers `commands/`, `agents/`, `skills/`, and `hooks/` directories at the plugin root.

## Debugging Checklist

When plugin commands aren't appearing:

1. **Check install path**: Look at `~/.claude/plugins/installed_plugins.json` - does `installPath` point to an existing directory?

2. **Verify directory structure**:
   ```
   plugin-root/
   ├── .claude-plugin/
   │   └── plugin.json      # Manifest only
   ├── commands/            # At plugin root, NOT in .claude-plugin/
   │   └── command.md
   ├── agents/
   └── skills/
   ```

3. **Check frontmatter**: Every command file needs:
   ```markdown
   ---
   description: Command description here
   ---
   ```

4. **Check enabled status**: `~/.claude/settings.json` should have:
   ```json
   {
     "enabledPlugins": {
       "plugin-name@marketplace-name": true
     }
   }
   ```

5. **Clean reinstall**: After making changes:
   ```bash
   rm -f ~/.claude/plugins/installed_plugins.json
   rm -f ~/.claude/plugins/known_marketplaces.json
   rm -rf ~/.claude/plugins/marketplaces/
   # Restart Claude Code, then /plugin to reinstall
   ```

## Key Learnings

- `pluginRoot` in marketplace.json is ignored - use full relative path in `source`
- Don't specify explicit `commands`/`agents` paths in plugin.json - let auto-discovery work
- Command files MUST have YAML frontmatter with `description`
- Plugin state files can get corrupted - clean reinstall often helps
