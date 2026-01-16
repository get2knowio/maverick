# Common TUI Bugs and Diagnostic Patterns

Patterns for diagnosing and fixing common TUI issues, with focus on Textual but applicable concepts for other frameworks.

## Data Flow Issues

### Symptom: Background data not appearing in UI

**Root causes:**
1. Thread safety violation (most common)
2. Missing reactive declaration
3. Widget not refreshing

**Diagnostic:**
```python
# Add logging at the update point
def update_data(self, data):
    self.log.info(f"update_data called with: {data}")
    self.my_value = data  # Is this actually being called?
```

**Fix - Thread safety (Textual):**
```python
# WRONG: Updating from background thread
def background_thread(app):
    data = fetch_data()
    app.my_widget.value = data  # Thread unsafe!

# CORRECT: Use call_from_thread
def background_thread(app):
    data = fetch_data()
    app.call_from_thread(app.update_widget, data)

def update_widget(self, data):
    self.my_widget.value = data  # Now safe
```

**Fix - Using Workers (Textual 0.40+):**
```python
@work(thread=True)
async def fetch_data(self):
    data = await some_api_call()
    # Worker results automatically marshal to main thread
    self.my_value = data
```

### Symptom: UI updates but data doesn't propagate back

**Diagnostic:**
```python
# Check if message is being posted
class MyInput(Input):
    def on_input_changed(self, event):
        self.log.info(f"Input changed: {event.value}")
        # Is parent receiving this?
```

**Common fixes:**
1. Ensure parent has handler: `def on_input_changed(self, event):`
2. Check event isn't being stopped: `event.stop()` prevents bubbling
3. Verify widget is in expected container hierarchy

## Rendering Issues

### Symptom: Widget not visible

**Diagnostic checklist:**
```python
widget = app.query_one("#my-widget")
print(f"display: {widget.styles.display}")      # Check not 'none'
print(f"visibility: {widget.styles.visibility}")  # Check not 'hidden'
print(f"size: {widget.size}")                   # Check not (0, 0)
print(f"region: {widget.region}")               # Check has area
print(f"visible prop: {widget.visible}")        # Check True
```

**Common causes:**
1. CSS `display: none` applied
2. Parent container has no space (check parent sizing)
3. Widget height/width explicitly set to 0
4. Widget outside scroll view and not scrolled to

### Symptom: Layout wrong / widgets overlapping

**Diagnostic:**
```python
# Dump layout tree
for widget in app.walk_children():
    print(f"{widget.__class__.__name__} {widget.id}: "
          f"region={widget.region}, size={widget.size}")
```

**Common causes:**
1. Missing `height: auto` or `width: auto` on container
2. Conflicting `dock` settings
3. CSS specificity - more specific rule overriding
4. Percentage heights without explicit parent height

**Fix pattern - explicit sizing:**
```css
/* Instead of relying on auto */
#container {
    height: 100%;
    width: 100%;
}

#child {
    height: 1fr;  /* Fraction of remaining space */
}
```

### Symptom: Text truncated or wrapped incorrectly

**Diagnostic:**
```python
widget = app.query_one("#label")
print(f"content_size: {widget.content_size}")
print(f"container size: {widget.size}")
print(f"overflow: {widget.styles.overflow_x}, {widget.styles.overflow_y}")
```

**Common fixes:**
1. Set `overflow-x: auto` for horizontal scroll
2. Use `min-width` to prevent shrinking
3. Check `text-wrap` CSS property

## Key Binding Issues

### Symptom: Key binding not triggering

**Diagnostic:**
```python
# Check binding registered
for b in app._bindings:
    print(f"{b.key}: {b.action} (priority={b.priority})")

# Check what has focus
print(f"Focused: {app.focused}")
print(f"Focused class: {app.focused.__class__.__name__}")
```

**Common causes:**
1. Binding not registered (missing `BINDINGS` class var)
2. Focus on wrong widget (bindings are focus-dependent)
3. Key captured by child widget first
4. Action method doesn't exist or wrong name

**Fix - Ensure app-level binding:**
```python
class MyApp(App):
    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        ("ctrl+q", "quit", "Quit"),
    ]
    
    def action_save(self):  # Note: action_ prefix
        self.save_data()
```

### Symptom: Key works sometimes but not others

**Diagnostic - focus tracking:**
```python
class MyApp(App):
    def on_focus(self, event):
        self.log.info(f"Focus moved to: {event.widget}")
```

**Common cause:** Different widgets capture the key in different focus states.

## Reactive/Watcher Issues

### Symptom: watch_* method not called

**Diagnostic:**
```python
class MyWidget(Widget):
    my_value = reactive(0)
    
    def watch_my_value(self, value):
        self.log.info(f"watch_my_value: {value}")  # Is this logging?
```

**Common causes:**
1. Watcher method name mismatch (`watch_myvalue` vs `watch_my_value`)
2. Value assigned before mount (watchers not active yet)
3. Same value assigned (no change = no trigger)
4. Reactive defined on wrong class (parent vs child)

**Fix - Force refresh:**
```python
def update_display(self, value):
    self.my_value = value
    self.refresh()  # Force re-render even if value unchanged
```

### Symptom: Computed reactive not updating

```python
class MyWidget(Widget):
    a = reactive(1)
    b = reactive(2)
    
    @property
    def sum(self):  # This won't be reactive!
        return self.a + self.b
```

**Fix - Use compute method:**
```python
class MyWidget(Widget):
    a = reactive(1)
    b = reactive(2)
    total = reactive(0)  # Declare as reactive
    
    def compute_total(self):  # Auto-called when a or b change
        return self.a + self.b
```

## Async/Timing Issues

### Symptom: Test passes locally but fails in CI

**Common cause:** Race conditions with async operations.

**Fix - Always use pause:**
```python
async def test_something():
    async with MyApp().run_test() as pilot:
        await pilot.click("#button")
        await pilot.pause()  # ALWAYS pause after interactions
        
        # Now safe to check state
        assert something
```

### Symptom: Widget state stale after action

**Diagnostic:** Add logging to see timing:
```python
async def test_debug():
    async with MyApp().run_test() as pilot:
        print("Before click")
        await pilot.click("#button")
        print("After click, before pause")
        await pilot.pause()
        print("After pause")
        # State should be stable now
```

### Symptom: Background worker never completes

**Diagnostic:**
```python
# Check worker state
for worker in app.workers:
    print(f"Worker: {worker.name}, state: {worker.state}")
```

**Common causes:**
1. Worker raised exception (check logs)
2. Worker waiting on something that won't happen
3. Worker cancelled unexpectedly

## CSS Debugging

### General CSS debugging pattern

```bash
# Run with CSS debugging
textual run --dev my_app.py
```

Then in console:
- `tree` - Show widget tree
- `css` - Show CSS for focused widget

### Specificity issues

```python
# Check what rules apply
widget = app.query_one("#problem-widget")
print(widget.css_tree)  # Shows specificity chain
```

**Fix - Use more specific selector:**
```css
/* Instead of */
Button { color: red; }

/* Use */
#my-screen Button#submit { color: red; }
```
