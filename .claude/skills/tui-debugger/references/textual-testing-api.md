# Textual Testing API Reference

Textual's testing API enables headless app execution with full programmatic control. Requires `textual[dev]` installed.

## Core Pattern: run_test()

```python
import asyncio
from my_app import MyApp

async def test_my_app():
    app = MyApp()
    async with app.run_test() as pilot:
        # pilot: Pilot object for interaction
        # pilot.app: Reference to the running app
        
        # Your test/debug code here
        await pilot.pause()  # Wait for reactives to settle

asyncio.run(test_my_app())
```

### run_test() Parameters

```python
async with app.run_test(
    size=(width, height),  # Terminal size, default (80, 24)
    tooltips=True,         # Enable tooltip testing
) as pilot:
```

## Pilot API

### Navigation & Input

```python
# Key presses
await pilot.press("tab")
await pilot.press("enter")
await pilot.press("ctrl+s")
await pilot.press("escape")

# Type text (into focused input)
await pilot.type("hello world")

# Click by selector
await pilot.click("#submit-button")
await pilot.click("Button.primary")

# Click by offset (relative to widget)
await pilot.click("#widget", offset=(5, 2))

# Hover
await pilot.hover("#tooltip-target")
```

### Timing Control

```python
# Wait for reactives and message queue to process
await pilot.pause()

# Wait with explicit duration (rarely needed)
await pilot.pause(delay=0.5)

# Wait for specific condition
await pilot.wait_for_animation()  # CSS animations
await pilot.wait_for_scheduled_animations()
```

### App Control

```python
# Exit the app
await pilot.exit(return_code)

# Take screenshot (returns SVG string)
svg = pilot.app.export_screenshot()
```

## Widget Querying

From `pilot.app`, use CSS-like selectors:

```python
app = pilot.app

# Query single widget (raises if not found or multiple)
button = app.query_one("#my-button")
button = app.query_one("Button")
button = app.query_one("Button.primary")

# Query single widget (returns None if not found)
button = app.query_one("#maybe-exists", Button)

# Query multiple widgets
all_buttons = app.query("Button")
active_items = app.query("ListItem.--active")

# Query with type hint
input_field: Input = app.query_one("#search", Input)
```

### Selector Syntax

```
Widget          # By widget class name
#id             # By ID
.class          # By CSS class
Widget.class    # Combined
Widget#id       # Combined
#parent #child  # Descendant
#parent > Child # Direct child
Widget:focus    # Pseudo-class (focus, hover, disabled)
```

## Widget Inspection

### Common Properties

```python
widget = app.query_one("#my-widget")

# Identity
widget.id           # str | None
widget.classes      # set of CSS classes
widget.name         # Optional name attribute

# State
widget.has_focus    # bool
widget.disabled     # bool
widget.visible      # bool
widget.display      # bool (CSS display)

# Geometry
widget.size         # Size(width, height)
widget.region       # Region(x, y, width, height)
widget.content_region  # Inner region minus padding/border

# For Input widgets
widget.value        # Current text value
widget.cursor_position  # int

# For Button
widget.label        # Button label
widget.variant      # "default", "primary", "success", etc.

# For containers
widget.children     # List of child widgets
```

### Style Inspection

```python
# Computed styles
styles = widget.styles
print(styles.width)
print(styles.height)
print(styles.background)
print(styles.color)
print(styles.display)
print(styles.visibility)

# CSS specificity debugging
print(widget.css_tree)

# Get all applied CSS rules
for rule in widget._css_styles:
    print(rule)
```

### Reactive State

```python
# Check reactive attributes
print(widget._reactive_values)  # Current values

# Watch for changes (add to widget class)
def watch_value(self, new_value):
    self.log.info(f"value changed: {new_value}")

# List all reactive attributes on a class
from textual.reactive import Reactive
for name in dir(widget.__class__):
    attr = getattr(widget.__class__, name, None)
    if isinstance(attr, Reactive):
        print(f"Reactive: {name}")
```

## Message Inspection

### Debug Message Flow

```python
# In your App class, override for debugging:
class MyApp(App):
    def _on_message(self, message):
        self.log.info(f"Message: {message}")
        return super()._on_message(message)
```

### Key Bindings

```python
# View all bindings
for binding in app._bindings:
    print(f"{binding.key} -> {binding.action}")

# Check if binding exists
app._bindings.get_key("ctrl+s")
```

## Testing Patterns

### Verify Widget State After Action

```python
async def test_button_disables():
    async with MyApp().run_test() as pilot:
        button = pilot.app.query_one("#submit")
        
        assert not button.disabled
        await pilot.click("#submit")
        await pilot.pause()
        assert button.disabled
```

### Test Input Handling

```python
async def test_search():
    async with MyApp().run_test() as pilot:
        await pilot.click("#search-input")
        await pilot.type("query")
        await pilot.press("enter")
        await pilot.pause()
        
        results = pilot.app.query_one("#results")
        assert "query" in results.renderable
```

### Test Background Updates

```python
async def test_periodic_update():
    async with MyApp().run_test() as pilot:
        label = pilot.app.query_one("#counter")
        initial = label.renderable
        
        # Wait for background worker to update
        await asyncio.sleep(1.5)
        await pilot.pause()
        
        assert label.renderable != initial
```

### Debugging Session Pattern

```python
async def debug_interactively():
    async with MyApp().run_test() as pilot:
        app = pilot.app
        
        # Set breakpoint here, or:
        import code
        code.interact(local=locals())
```

## Console Debugging

Run app with dev console for live logging:

```bash
textual run --dev my_app.py
```

In your app:
```python
self.log.info("Debug message")
self.log.warning("Warning")
self.log.error("Error")
self.log(widget)  # Pretty-print widget tree
```

The dev console shows:
- All log messages
- Reactive changes
- Message flow
- CSS errors
