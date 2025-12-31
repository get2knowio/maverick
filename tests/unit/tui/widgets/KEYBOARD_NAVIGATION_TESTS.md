# Keyboard Navigation Tests Implementation

## Overview
This document describes the keyboard navigation tests implemented for Phase 9 of the workflow widgets feature (012-workflow-widgets).

## Test Files Created

### 1. test_workflow_progress_keyboard.py (T118)
**Purpose**: Test WorkflowProgress arrow key navigation

**Tests Implemented**:
- `test_arrow_down_moves_focus_to_next_stage`: Verifies down arrow moves focus to next stage
- `test_arrow_up_moves_focus_to_previous_stage`: Verifies up arrow moves to previous stage
- `test_down_at_last_stage_stays_at_last`: Ensures down at last stage doesn't go out of bounds
- `test_up_at_first_stage_stays_at_first`: Ensures up at first stage doesn't go out of bounds
- `test_enter_toggles_stage_expansion`: Verifies enter key expands/collapses focused stage
- `test_widget_focuses_first_stage_on_focus`: Verifies first stage is focused when widget receives focus (T121)

**Expected Behavior**:
- Widget must track `focused_stage_index` in state
- Down arrow: increment index (clamp to max)
- Up arrow: decrement index (clamp to 0)
- Enter: toggle expansion of focused stage
- On focus: reset to index 0

### 2. test_agent_output_keyboard.py (T119)
**Purpose**: Test AgentOutput Page Up/Down scrolling

**Tests Implemented**:
- `test_page_down_scrolls_content`: Verifies Page Down scrolls output by a page
- `test_page_up_scrolls_content_backwards`: Verifies Page Up scrolls backwards
- `test_page_down_then_page_up_navigation`: Tests combined navigation
- `test_end_key_scrolls_to_bottom`: Verifies End key behavior
- `test_home_key_scrolls_to_top`: Verifies Home key behavior

**Expected Behavior**:
- Page Down: increase scroll_y by viewport height
- Page Up: decrease scroll_y by viewport height
- Home: scroll to top (scroll_y = 0)
- End: scroll to bottom (scroll_y = max)
- Uses VerticalScroll container's native scroll functionality

### 3. test_review_findings_keyboard.py (T120)
**Purpose**: Test ReviewFindings Tab cycling and keyboard shortcuts

**Tests Implemented**:
- `test_tab_cycles_through_findings`: Verifies Tab moves through findings
- `test_shift_tab_cycles_backwards`: Verifies Shift+Tab moves backwards
- `test_tab_reaches_action_buttons`: Verifies Tab reaches bulk action buttons
- `test_down_arrow_moves_to_next_finding`: Verifies down arrow navigation
- `test_up_arrow_moves_to_previous_finding`: Verifies up arrow navigation
- `test_space_toggles_selection`: Verifies space key toggles finding selection
- `test_enter_expands_focused_finding`: Verifies enter expands focused finding
- `test_a_key_selects_all_findings`: Verifies 'a' key selects all
- `test_d_key_deselects_all_findings`: Verifies 'd' key deselects all
- `test_widget_focuses_first_finding_on_focus`: Verifies first finding focused on widget focus (T121)

**Expected Behavior**:
- Widget must track `focused_index` in state
- Tab: native Textual focus cycling through findings and buttons
- Down/Up: navigate focused_index through findings list
- Space: toggle selection of focused finding
- Enter: expand focused finding
- 'a': select all findings
- 'd': deselect all findings
- On focus: reset to index 0

### 4. test_widget_focus_behavior.py (T121)
**Purpose**: Consolidated tests for focus behavior across all widgets

**Test Classes**:
- `TestWorkflowProgressFocusBehavior`: Verifies WorkflowProgress focuses first stage
- `TestReviewFindingsFocusBehavior`: Verifies ReviewFindings focuses first finding
- `TestValidationStatusFocusBehavior`: Verifies ValidationStatus focuses first step
- `TestAgentOutputFocusBehavior`: Verifies AgentOutput allows navigation from top
- `TestPRSummaryFocusBehavior`: Verifies PRSummary can receive focus
- `TestMultiWidgetFocusBehavior`: Tests focus cycling across multiple widgets
- `TestFocusBehaviorEdgeCases`: Tests edge cases (empty widgets, refocus)

**Expected Behavior**:
- When any widget receives focus, the first focusable item should be selected/focused
- Empty widgets should handle focus gracefully without crashing
- Tabbing between widgets should maintain proper focus state

## Test Patterns Used

All tests follow the established patterns from existing test files:

```python
@pytest.mark.asyncio
async def test_example() -> None:
    """Test description."""
    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(WidgetType)

        # Setup widget state
        widget.update_data(...)
        await pilot.pause()

        # Focus widget
        widget.focus()
        await pilot.pause()

        # Simulate key press
        await pilot.press("down")
        await pilot.pause()

        # Assert expected behavior
        assert widget.state.focused_index == expected_value
```

## State Properties Required

For these tests to pass, widgets need to implement the following state properties:

### WorkflowProgress
- `focused_stage_index: int` - Index of currently focused stage (0-based)

### ReviewFindings
- `focused_index: int` - Index of currently focused finding (0-based)

### ValidationStatus
- `focused_step_index: int` - Index of currently focused validation step (0-based)

### AgentOutput
- No special state needed - uses VerticalScroll's native scroll properties

### PRSummary
- No special state needed - may use Textual's native focus system

## Keyboard Bindings Required

### WorkflowProgress
```python
BINDINGS = [
    Binding("up", "move_up", "Previous stage", show=False),
    Binding("down", "move_down", "Next stage", show=False),
    Binding("enter", "toggle_expand", "Expand/collapse", show=False),
]
```

### ReviewFindings
```python
BINDINGS = [
    Binding("up", "move_up", "Previous finding", show=False),
    Binding("down", "move_down", "Next finding", show=False),
    Binding("enter", "toggle_expand", "Expand/collapse", show=False),
    Binding("space", "toggle_select", "Toggle selection", show=False),
    Binding("a", "select_all", "Select all", show=False),
    Binding("d", "deselect_all", "Deselect all", show=False),
]
```

### AgentOutput
```python
BINDINGS = [
    Binding("pagedown", "page_down", "Page down", show=False),
    Binding("pageup", "page_up", "Page up", show=False),
    Binding("home", "scroll_home", "Scroll to top", show=False),
    Binding("end", "scroll_end", "Scroll to bottom", show=False),
]
```

### ValidationStatus
```python
BINDINGS = [
    Binding("up", "move_up", "Previous step", show=False),
    Binding("down", "move_down", "Next step", show=False),
    Binding("enter", "toggle_expand", "Expand/collapse", show=False),
]
```

## TDD Approach

These tests are written following TDD (Test-Driven Development):

1. **Red**: Tests are written first and will FAIL because keyboard navigation isn't implemented
2. **Green**: Implement the keyboard navigation functionality to make tests pass
3. **Refactor**: Clean up implementation while keeping tests passing

## Running the Tests

```bash
# Run all keyboard navigation tests
pytest tests/unit/tui/widgets/test_*keyboard*.py -v

# Run specific widget tests
pytest tests/unit/tui/widgets/test_workflow_progress_keyboard.py -v
pytest tests/unit/tui/widgets/test_agent_output_keyboard.py -v
pytest tests/unit/tui/widgets/test_review_findings_keyboard.py -v

# Run focus behavior tests
pytest tests/unit/tui/widgets/test_widget_focus_behavior.py -v
```

## Next Steps

After implementing the keyboard navigation functionality:

1. Verify all tests pass
2. Test keyboard navigation manually in the TUI
3. Update documentation with keyboard shortcuts
4. Consider adding keyboard shortcut help overlay in TUI

## Implementation Notes

- All keyboard bindings use `show=False` to hide them from the default Textual bindings list
- Focus indices should be clamped to valid ranges (0 to len(items)-1)
- Empty widgets should handle focus gracefully
- Keyboard navigation should work seamlessly with mouse interaction
- Consider accessibility: ensure tab order is logical and intuitive
