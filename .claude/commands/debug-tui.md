---
description: Debug the Maverick TUI using the mcp-tui-server and sample project. Launches workflow execution and observes the streaming-first interface.
---

# Debug Maverick TUI

This command uses the **tui-debugger skill** and the **mcp-tui-server MCP tools** to debug the Maverick TUI against the **sample-maverick-project**.

## User Input

```text
$ARGUMENTS
```

Consider the user input above when deciding what to debug or which workflow to run (if not empty).

## Prerequisites

1. **mcp-tui-server**: Must be configured in MCP settings (provides `tui_*` tools)
2. **sample-maverick-project**: Must exist at `/workspaces/sample-maverick-project`
3. **Maverick**: Must be runnable via `uv run --project /workspaces/maverick maverick`

## Debugging Process

### 1. Load the TUI Debugger Skill

First, ensure you have access to the tui-debugger skill from `.claude/skills/tui-debugger/SKILL.md`. This provides patterns for:
- Visual observation via mcp-tui-server
- Semantic inspection for Textual apps
- Common TUI bug diagnosis

### 2. Verify Sample Project State

Check the sample project is ready:

```bash
cd /workspaces/sample-maverick-project && git status
```

If the sample project has uncommitted changes from a previous run, reset it:

```bash
/workspaces/sample-maverick-project/scripts/reset-repo.sh --force
```

### 3. Launch TUI Session

Use mcp-tui-server to launch maverick in an observable session:

```python
tui_launch(
    command="uv",
    args=["run", "--project", "/workspaces/maverick", "maverick", "fly", "feature", "-i", "branch_name=001-greet-cli"],
    cwd="/workspaces/sample-maverick-project",
    cols=120,
    rows=24
)
```

**Alternative workflows to test:**
- `maverick fly feature -i branch_name=001-greet-cli` - Full feature workflow
- `maverick fly feature -i branch_name=001-greet-cli --dry-run` - Dry run mode
- `maverick fly feature --list-steps` - List workflow steps only

### 4. Observe and Monitor

Use these mcp-tui-server tools to observe the TUI:

| Tool | Purpose |
|------|---------|
| `tui_screenshot` | Visual PNG capture of current state |
| `tui_text` | Plain text content of the terminal |
| `tui_snapshot` | Accessibility-style snapshot with element refs |
| `tui_wait_for_idle` | Wait for screen to stabilize |
| `tui_get_scrollback` | Check for scrolled-off content |

**Observation pattern:**
```python
# Take initial screenshot
tui_screenshot(session_id="...")

# Wait for activity, then capture state
tui_wait_for_idle(session_id="...", timeout_ms=5000, idle_ms=500)
tui_text(session_id="...")

# For structured analysis
tui_snapshot(session_id="...")
```

### 5. Interact with TUI

If interaction is needed:

```python
# Press keys
tui_press_key(session_id="...", key="Enter")
tui_press_key(session_id="...", key="Escape")
tui_press_key(session_id="...", key="Ctrl+c")

# Click elements (use ref from tui_snapshot)
tui_click(session_id="...", ref_id="button-1")
```

### 6. Diagnose Issues

Common issues to check for:

**Streaming not appearing:**
- Check if `StepOutput` events are being emitted
- Verify `UnifiedStreamWidget` is receiving messages
- Look for errors in the event stream

**Layout problems:**
- Use `tui_screenshot` to see actual render
- Check terminal size (cols/rows) is adequate
- Verify CSS styles in Textual widgets

**Workflow stuck:**
- Use `tui_text` to see current step status
- Check elapsed time indicator
- Look for error messages in the stream

### 7. Cleanup

When done, close the TUI session:

```python
tui_close(session_id="...")
```

Then reset the sample project:

```bash
/workspaces/sample-maverick-project/scripts/reset-repo.sh --force
```

## Key Files

| File | Purpose |
|------|---------|
| `src/maverick/tui/screens/workflow_execution.py` | Main workflow execution screen |
| `src/maverick/tui/widgets/unified_stream.py` | Streaming output widget |
| `src/maverick/dsl/events.py` | Workflow event definitions |
| `.claude/skills/tui-debugger/SKILL.md` | Full TUI debugger skill docs |

## Example Session

```
# Launch
tui_launch(command="uv", args=["run", "--project", "/workspaces/maverick", "maverick", "fly", "feature", "-i", "branch_name=001-greet-cli"], cwd="/workspaces/sample-maverick-project")

# Monitor every 30s
tui_screenshot(session_id="...")
tui_text(session_id="...")

# When complete
tui_close(session_id="...")
```
