# mcp-tui-server Tool Reference

Quick reference for mcp-tui-server MCP tools. All tools require a `session_id` parameter.

## Session Management

### tui_launch
Launch a TUI application in an observable PTY session.

```
tui_launch(command: str, session_id: str, width?: int, height?: int)
```

- `command`: Shell command to run (e.g., `"python my_app.py"`)
- `session_id`: Unique identifier for this session
- `width/height`: Optional terminal dimensions (default: 80x24)

### tui_close
Close a TUI session.

```
tui_close(session_id: str)
```

### tui_resize
Resize terminal dimensions (useful for testing responsive layouts).

```
tui_resize(session_id: str, width: int, height: int)
```

## Observation Tools

### tui_text
Get plain text content of the terminal screen.

```
tui_text(session_id: str) -> str
```

Returns raw text without formatting. Best for simple content extraction.

### tui_snapshot
Get accessibility-style snapshot with element references.

```
tui_snapshot(session_id: str) -> str
```

Returns text with element refs like `[button-1]`, `[input-2]`, `[span-3]`.
Use these refs with `tui_click` for targeted interaction.

Example output:
```
╭─ Header ──────────────────────────────╮
│ [span-1]Welcome to MyApp[/span-1]     │
│ [button-1]Submit[/button-1] [button-2]Cancel[/button-2] │
╰───────────────────────────────────────╯
```

### tui_screenshot
Capture a PNG screenshot of the terminal.

```
tui_screenshot(session_id: str) -> base64_png
```

Returns base64-encoded PNG image. Use for visual debugging or when text extraction loses important styling information.

## Input Tools

### tui_press_key
Send a key press to the TUI.

```
tui_press_key(session_id: str, key: str)
```

Key formats:
- Single characters: `"a"`, `"1"`, `" "` (space)
- Named keys: `"Enter"`, `"Tab"`, `"Escape"`, `"Backspace"`, `"Delete"`
- Arrow keys: `"Up"`, `"Down"`, `"Left"`, `"Right"`
- Function keys: `"F1"` through `"F12"`
- Modifiers: `"ctrl+c"`, `"ctrl+x"`, `"alt+f"`, `"shift+Tab"`

### tui_type
Type a string of text (simulates sequential key presses).

```
tui_type(session_id: str, text: str)
```

Use for entering text into input fields. For special keys, use `tui_press_key`.

### tui_click
Click on an element by its reference from `tui_snapshot`.

```
tui_click(session_id: str, ref: str)
```

- `ref`: Element reference from snapshot (e.g., `"button-1"`, `"span-3"`)

### tui_mouse_click
Click at specific coordinates.

```
tui_mouse_click(session_id: str, x: int, y: int, button?: str)
```

- `x/y`: Terminal coordinates (0-indexed from top-left)
- `button`: `"left"` (default), `"right"`, `"middle"`

## Scripting (Advanced)

### tui_run_script
Execute JavaScript in the session context (Boa engine).

```
tui_run_script(session_id: str, script: str) -> str
```

Available APIs in script context:
- `screen.getText()` - Get screen text
- `screen.getSnapshot()` - Get accessibility snapshot
- `input.pressKey(key)` - Send key
- `input.type(text)` - Type text
- `input.click(ref)` - Click element
- `wait(ms)` - Wait milliseconds

Example:
```javascript
input.type("search term");
input.pressKey("Enter");
wait(500);
return screen.getText();
```

## Common Patterns

### Debug Loop Pattern
```python
# 1. Launch
tui_launch(command="python app.py", session_id="dbg")

# 2. Observe initial state
initial = tui_snapshot(session_id="dbg")

# 3. Interact
tui_press_key(session_id="dbg", key="Tab")
tui_click(session_id="dbg", ref="button-1")

# 4. Observe result
result = tui_snapshot(session_id="dbg")

# 5. Compare (save to files, use snapshot_diff.py)

# 6. Cleanup when done
tui_close(session_id="dbg")
```

### Testing Key Bindings
```python
tui_launch(command="python app.py", session_id="keys")

# Test each binding
for key in ["ctrl+s", "ctrl+q", "F1", "?"]:
    before = tui_text(session_id="keys")
    tui_press_key(session_id="keys", key=key)
    after = tui_text(session_id="keys")
    print(f"{key}: {'changed' if before != after else 'no change'}")
```

### Responsive Layout Testing
```python
tui_launch(command="python app.py", session_id="layout")

for width, height in [(80, 24), (120, 40), (40, 20)]:
    tui_resize(session_id="layout", width=width, height=height)
    tui_screenshot(session_id="layout")  # Capture each size
```
