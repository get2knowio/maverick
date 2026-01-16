---
name: tui-debugger
description: "Debug TUI (Text User Interface) applications through visual observation and semantic inspection. Use when: (1) debugging rendering issues in terminal UIs, (2) troubleshooting widget behavior or key bindings, (3) diagnosing data flow issues where updates aren't appearing in widgets, (4) investigating layout problems, (5) any TUI application debugging where you need to observe runtime state. Supports Textual (Python) with deep semantic inspection, and any TUI via mcp-tui-server visual observation."
---

# TUI Debugger

Debug TUI applications through two complementary approaches: **visual observation** (any TUI) via mcp-tui-server, and **semantic inspection** (Textual apps) via the framework's testing API. Supports iterative debugging cycles: observe → identify → fix → verify → repeat.

## Prerequisites

- **mcp-tui-server**: Must be configured in MCP settings (provides `tui_*` tools)
- **Textual apps**: Requires `textual[dev]` installed in the app's environment

## Debugging Approach Selection

```
Is this a Textual (Python) application?
├─ YES → Use Semantic Mode (preferred) + Visual Mode for rendering issues
│        Semantic mode provides widget tree access, state inspection, CSS queries
└─ NO  → Use Visual Mode only
         Works with any TUI: Bubble Tea, curses, blessed, Ink, etc.
```

## Debugging Cycle

This skill supports iterative debugging. Repeat steps 2-5 until resolved:

```
1. Setup observation session
2. Capture state (baseline or post-change)
3. Interact / reproduce issue
4. Analyze: compare expected vs actual
5. Apply fix to code
→ Loop to step 2 to verify
```

## Visual Mode (Any TUI)

Uses mcp-tui-server MCP tools. See `references/mcp-tui-tools.md` for full API.

### Launch and Observe

```python
# Launch TUI in observable session
tui_launch(command="python my_app.py", session_id="debug1")

# Get current screen state
tui_text(session_id="debug1")           # Plain text content
tui_snapshot(session_id="debug1")       # Accessibility-style with element refs
tui_screenshot(session_id="debug1")     # Visual PNG capture
```

### Interact

```python
# Keyboard input
tui_press_key(session_id="debug1", key="Tab")
tui_press_key(session_id="debug1", key="Enter")
tui_press_key(session_id="debug1", key="ctrl+c")

# Type text
tui_type(session_id="debug1", text="search query")

# Click element (use refs from tui_snapshot)
tui_click(session_id="debug1", ref="button-1")
```

### Compare States

Capture snapshots before/after interactions, save to files, then:

```bash
python scripts/snapshot_diff.py before.txt after.txt
```

## Semantic Mode (Textual)

Provides deep inspection via Textual's testing API. More powerful than visual mode for Textual apps.

### Headless Inspection

Run `scripts/textual_inspector.py` to capture complete app state:

```bash
python scripts/textual_inspector.py my_app:MyApp --output state.json
```

Captures: widget tree, CSS styles, current values, focus state, data bindings.

### Interactive Test Session

For complex debugging, create a test harness:

```python
import asyncio
from my_app import MyApp

async def debug_session():
    async with MyApp().run_test() as pilot:
        app = pilot.app
        
        # Query widgets by CSS selector
        button = app.query_one("#submit-button")
        input_field = app.query_one("Input.search")
        all_labels = app.query("Label")
        
        # Inspect state
        print(f"Button disabled: {button.disabled}")
        print(f"Input value: {input_field.value}")
        print(f"Focus: {app.focused}")
        
        # Simulate interaction
        await pilot.press("tab")
        await pilot.click("#submit-button")
        await pilot.pause()  # Let reactives update
        
        # Check result
        print(f"After click - Button: {button.disabled}")

asyncio.run(debug_session())
```

### Common Inspection Patterns

```python
# Widget tree dump
for widget in app.walk_children():
    print(f"{widget.__class__.__name__}: {widget.id or '(no id)'}")

# Check reactive bindings
print(app._bindings)  # Key bindings
print(widget.watchers)  # Reactive watchers

# CSS debugging
print(widget.styles)  # Applied styles
print(widget.css_tree)  # CSS specificity

# Message flow debugging (add to app)
def on_mount(self):
    self.log.info("Mounted")  # Use textual console: textual run --dev
```

## Diagnosing Common Issues

### UI Not Updating

**Symptoms**: Data changes but widget doesn't reflect it

**Diagnostic steps**:
1. Verify reactive is triggering: add `watch_*` method with logging
2. Check if `refresh()` is needed for non-reactive updates
3. Verify message handlers are connected (`on_*` methods)
4. Use `textual run --dev` to see reactive log

```python
# In your App/Widget class:
def watch_my_value(self, new_value):
    self.log.info(f"my_value changed to {new_value}")  # Should see this
```

### Widget Not Rendering Correctly

**Diagnostic steps**:
1. Visual mode: `tui_screenshot` to see actual render
2. Semantic mode: inspect `widget.styles`, `widget.size`, `widget.region`
3. Check CSS specificity conflicts
4. Verify container constraints aren't clipping

### Key Binding Not Working

**Diagnostic steps**:
1. Check `app._bindings` for registration
2. Verify focus is on correct widget: `app.focused`
3. Check if key is captured by parent widget
4. Use visual mode to test: `tui_press_key` + `tui_snapshot`

### Data Flow Issues (App ↔ TUI)

**Symptoms**: Backend data updates but TUI doesn't show them, or TUI actions don't trigger backend

**Diagnostic steps**:
1. Add logging at integration boundary
2. Verify `call_from_thread()` for background thread → TUI updates
3. Check message posting: `self.post_message(MyMessage(data))`
4. Inspect worker state if using Textual workers

```python
# Background thread updating TUI (must use call_from_thread)
def background_work(app):
    while True:
        data = fetch_data()
        app.call_from_thread(app.update_display, data)  # Safe
        # app.update_display(data)  # WRONG - not thread-safe
```

See `references/common-tui-bugs.md` for more patterns.

## Scripts

- `scripts/textual_inspector.py` - Dump Textual app state to JSON
- `scripts/snapshot_diff.py` - Compare two TUI text snapshots, highlight changes

## References

- `references/mcp-tui-tools.md` - Complete mcp-tui-server tool reference
- `references/textual-testing-api.md` - Textual's run_test/Pilot API patterns  
- `references/common-tui-bugs.md` - Common TUI bugs and diagnostic patterns
