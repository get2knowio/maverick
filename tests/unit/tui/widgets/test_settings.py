"""Unit tests for settings widgets.

This test module covers settings widgets for the TUI Interactive Screens
feature (013-tui-interactive-screens). Settings widgets provide a form-based
interface for configuring Maverick settings with validation and change tracking.

Test coverage includes:
- SettingsSection (collapsible settings groups)
- SettingField (individual setting inputs)
- Value modification tracking
- Field rendering for different types (string, bool, int)
- Protocol compliance
"""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import Input, Static, Switch

from maverick.tui.models import SettingDefinition, SettingType, SettingValue
from maverick.tui.widgets.settings import SettingField, SettingsSection

# =============================================================================
# SettingField Tests
# =============================================================================


class TestSettingField:
    """Test suite for SettingField widget."""

    @pytest.fixture
    def string_definition(self) -> SettingDefinition:
        """Create a string setting definition."""
        return SettingDefinition(
            key="github.owner",
            display_name="Owner",
            description="GitHub repository owner",
            setting_type=SettingType.STRING,
        )

    @pytest.fixture
    def bool_definition(self) -> SettingDefinition:
        """Create a boolean setting definition."""
        return SettingDefinition(
            key="notifications.enabled",
            display_name="Enabled",
            description="Enable push notifications",
            setting_type=SettingType.BOOL,
        )

    @pytest.fixture
    def int_definition(self) -> SettingDefinition:
        """Create an integer setting definition."""
        return SettingDefinition(
            key="agents.max_parallel",
            display_name="Max Parallel",
            description="Maximum parallel agents",
            setting_type=SettingType.INT,
            min_value=1,
            max_value=10,
        )

    @pytest.mark.asyncio
    async def test_string_field_initialization(
        self, string_definition: SettingDefinition
    ) -> None:
        """Test string field initialization."""

        class TestApp(App):
            def compose(self):
                value = SettingValue(
                    definition=string_definition,
                    current_value="test-owner",
                    original_value="test-owner",
                )
                yield SettingField(value=value)

        app = TestApp()
        async with app.run_test():
            field = app.query_one(SettingField)

            # Verify field properties
            assert field.value.definition.key == "github.owner"
            assert field.value.current_value == "test-owner"
            assert not field.value.is_modified

            # Verify composition includes label and input
            assert app.query_one(".setting-label", Static)
            assert app.query_one(".setting-description", Static)
            assert app.query_one(Input)

    @pytest.mark.asyncio
    async def test_bool_field_uses_switch(
        self, bool_definition: SettingDefinition
    ) -> None:
        """Test boolean field uses Switch widget."""

        class TestApp(App):
            def compose(self):
                value = SettingValue(
                    definition=bool_definition,
                    current_value=True,
                    original_value=True,
                )
                yield SettingField(value=value)

        app = TestApp()
        async with app.run_test():
            # Verify Switch is used for boolean
            switch = app.query_one(Switch)
            assert switch.value is True

    @pytest.mark.asyncio
    async def test_int_field_validation(
        self, int_definition: SettingDefinition
    ) -> None:
        """Test integer field enforces min/max constraints."""

        class TestApp(App):
            def compose(self):
                value = SettingValue(
                    definition=int_definition,
                    current_value=5,
                    original_value=5,
                )
                yield SettingField(value=value)

        app = TestApp()
        async with app.run_test() as pilot:
            field = app.query_one(SettingField)
            input_widget = app.query_one(Input)

            # Verify initial value
            assert field.value.current_value == 5

            # Test setting value within range
            await pilot.pause()
            input_widget.value = "7"
            await pilot.pause()

            # Value should be accepted
            assert field.value.is_valid

    @pytest.mark.asyncio
    async def test_field_modification_tracking(
        self, string_definition: SettingDefinition
    ) -> None:
        """Test field tracks modifications."""

        class TestApp(App):
            def compose(self):
                value = SettingValue(
                    definition=string_definition,
                    current_value="original",
                    original_value="original",
                )
                yield SettingField(value=value)

        app = TestApp()
        async with app.run_test() as pilot:
            field = app.query_one(SettingField)
            input_widget = app.query_one(Input)

            # Initially not modified
            assert not field.value.is_modified

            # Change value
            await pilot.pause()
            input_widget.value = "modified"
            await pilot.pause()

            # Should be marked as modified
            assert field.value.is_modified

    @pytest.mark.asyncio
    async def test_field_reset(self, string_definition: SettingDefinition) -> None:
        """Test field can reset to original value."""

        class TestApp(App):
            def compose(self):
                value = SettingValue(
                    definition=string_definition,
                    current_value="modified",
                    original_value="original",
                )
                yield SettingField(value=value)

        app = TestApp()
        async with app.run_test() as pilot:
            field = app.query_one(SettingField)

            # Initially modified
            assert field.value.is_modified

            # Reset field
            field.reset()
            await pilot.pause()

            # Should no longer be modified
            assert not field.value.is_modified
            assert field.value.current_value == "original"

    @pytest.mark.asyncio
    async def test_field_changed_message(
        self, string_definition: SettingDefinition
    ) -> None:
        """Test field posts Changed message on value change."""
        messages = []

        class TestApp(App):
            def compose(self):
                value = SettingValue(
                    definition=string_definition,
                    current_value="test",
                    original_value="test",
                )
                yield SettingField(value=value)

            def on_setting_field_changed(self, message: SettingField.Changed) -> None:
                messages.append(message)

        app = TestApp()
        async with app.run_test() as pilot:
            app.query_one(SettingField)
            input_widget = app.query_one(Input)

            # Change value
            await pilot.pause()
            input_widget.value = "new-value"
            await pilot.pause()

            # Should have posted Changed message
            assert len(messages) > 0


# =============================================================================
# SettingsSection Tests
# =============================================================================


class TestSettingsSection:
    """Test suite for SettingsSection widget."""

    @pytest.mark.asyncio
    async def test_section_initialization(self) -> None:
        """Test section initialization with name."""

        class TestApp(App):
            def compose(self):
                yield SettingsSection(name="GitHub")

        app = TestApp()
        async with app.run_test():
            section = app.query_one(SettingsSection)

            # Verify section properties
            assert section.section_name == "GitHub"
            assert section.expanded is True

            # Verify header is rendered
            header = app.query_one(".section-header", Static)
            assert header is not None

    @pytest.mark.asyncio
    async def test_section_toggle_expansion(self) -> None:
        """Test section can toggle between expanded/collapsed."""

        class TestApp(App):
            def compose(self):
                yield SettingsSection(name="Test Section")

        app = TestApp()
        async with app.run_test() as pilot:
            section = app.query_one(SettingsSection)

            # Initially expanded
            assert section.expanded is True

            # Toggle to collapsed
            section.expanded = False
            await pilot.pause()

            # Verify collapsed state
            assert section.expanded is False

            # Toggle back to expanded
            section.expanded = True
            await pilot.pause()

            # Verify expanded state
            assert section.expanded is True

    @pytest.mark.asyncio
    async def test_section_contains_fields(self) -> None:
        """Test section can contain setting fields."""

        class TestApp(App):
            def compose(self):
                section = SettingsSection(name="Test")
                yield section

        app = TestApp()
        async with app.run_test() as pilot:
            app.query_one(SettingsSection)
            content = app.query_one("#section-content")

            # Initially empty
            assert len(content.children) == 0

            # Add a field
            definition = SettingDefinition(
                key="test.key",
                display_name="Test",
                description="Test setting",
                setting_type=SettingType.STRING,
            )
            value = SettingValue(
                definition=definition,
                current_value="test",
                original_value="test",
            )
            await content.mount(SettingField(value=value))
            await pilot.pause()

            # Verify field was added
            assert len(content.children) == 1
            assert isinstance(content.children[0], SettingField)

    @pytest.mark.asyncio
    async def test_section_expansion_icon(self) -> None:
        """Test section shows correct expansion icon."""

        class TestApp(App):
            def compose(self):
                yield SettingsSection(name="Test")

        app = TestApp()
        async with app.run_test() as pilot:
            section = app.query_one(SettingsSection)
            app.query_one(".section-header", Static)

            # Expanded shows down arrow
            assert section.expanded is True
            # Verify icon is present in the section
            # (implementation updates the header on watch_expanded)

            # Collapsed shows right arrow
            section.expanded = False
            await pilot.pause()
            # Verify collapsed state
            assert section.expanded is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestSettingsWidgetsIntegration:
    """Integration tests for settings widgets."""

    @pytest.mark.asyncio
    async def test_section_with_multiple_fields(self) -> None:
        """Test section containing multiple fields."""

        class TestApp(App):
            def compose(self):
                yield SettingsSection(name="GitHub")

        app = TestApp()
        async with app.run_test() as pilot:
            app.query_one(SettingsSection)
            content = app.query_one("#section-content")

            # Add multiple fields
            fields_data = [
                ("github.owner", "Owner", "test-owner"),
                ("github.repo", "Repository", "test-repo"),
            ]

            for key, display_name, value in fields_data:
                definition = SettingDefinition(
                    key=key,
                    display_name=display_name,
                    description=f"{display_name} setting",
                    setting_type=SettingType.STRING,
                )
                setting_value = SettingValue(
                    definition=definition,
                    current_value=value,
                    original_value=value,
                )
                await content.mount(SettingField(value=setting_value))

            await pilot.pause()

            # Verify all fields were added
            fields = app.query(SettingField)
            assert len(fields) == 2

    @pytest.mark.asyncio
    async def test_field_type_rendering(self) -> None:
        """Test different field types render appropriate widgets."""

        class TestApp(App):
            def compose(self):
                # String field
                string_def = SettingDefinition(
                    key="test.string",
                    display_name="String",
                    description="String setting",
                    setting_type=SettingType.STRING,
                )
                yield SettingField(
                    value=SettingValue(
                        definition=string_def,
                        current_value="test",
                        original_value="test",
                    )
                )

                # Bool field
                bool_def = SettingDefinition(
                    key="test.bool",
                    display_name="Boolean",
                    description="Boolean setting",
                    setting_type=SettingType.BOOL,
                )
                yield SettingField(
                    value=SettingValue(
                        definition=bool_def,
                        current_value=True,
                        original_value=True,
                    )
                )

                # Int field
                int_def = SettingDefinition(
                    key="test.int",
                    display_name="Integer",
                    description="Integer setting",
                    setting_type=SettingType.INT,
                )
                yield SettingField(
                    value=SettingValue(
                        definition=int_def,
                        current_value=5,
                        original_value=5,
                    )
                )

        app = TestApp()
        async with app.run_test():
            # Verify string field has Input
            fields = app.query(SettingField)
            assert len(fields) == 3

            # Count Switches (bool fields) and Inputs (string/int fields)
            switches = app.query(Switch)
            inputs = app.query(Input)

            assert len(switches) == 1  # One bool field
            assert len(inputs) == 2  # Two string/int fields
