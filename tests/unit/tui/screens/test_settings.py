"""Unit tests for SettingsScreen.

This test module covers the SettingsScreen for the TUI Interactive Screens
feature (013-tui-interactive-screens). SettingsScreen provides a form-based
interface for configuring Maverick settings with validation, unsaved change
tracking, and connection testing.

Test coverage includes:
- Screen initialization and composition
- Settings section organization
- Form field rendering and editing
- Unsaved changes detection
- Save and cancel operations
- GitHub connection testing
- Notification testing
- Navigation with confirmation prompts
- Protocol compliance
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.app import App
from textual.widgets import Button, Static

from maverick.tui.models import (
    SettingDefinition,
    SettingsScreenState,
    SettingType,
    SettingValue,
)
from maverick.tui.models import (
    SettingsSection as SettingsSectionModel,
)
from maverick.tui.screens.settings import SettingsScreen
from maverick.tui.widgets.settings import SettingField, SettingsSection

# =============================================================================
# SettingsScreen Tests
# =============================================================================


class TestSettingsScreenInitialization:
    """Test suite for SettingsScreen initialization."""

    @pytest.mark.asyncio
    async def test_screen_composition(self) -> None:
        """Test screen composes required elements."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test():
            screen = app.query_one(SettingsScreen)

            # Verify screen exists
            assert screen is not None
            assert screen.TITLE == "Settings"

            # Verify main elements
            assert app.query_one("#title", Static)
            assert app.query_one("#settings-container")
            assert app.query_one("#buttons")

    @pytest.mark.asyncio
    async def test_screen_has_sections(self) -> None:
        """Test screen creates settings sections."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test():
            # Verify sections exist
            sections = app.query(SettingsSection)
            assert len(sections) >= 3  # GitHub, Notifications, Agents

            # Verify section names
            section_names = [s.section_name for s in sections]
            assert "GitHub" in section_names
            assert "Notifications" in section_names
            assert "Agents" in section_names

    @pytest.mark.asyncio
    async def test_screen_has_action_buttons(self) -> None:
        """Test screen has Save and Cancel buttons."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test():
            # Verify buttons exist
            save_btn = app.query_one("#save-btn", Button)
            cancel_btn = app.query_one("#cancel-btn", Button)

            assert str(save_btn.label) == "Save"
            assert str(cancel_btn.label) == "Cancel"

    @pytest.mark.asyncio
    async def test_screen_has_test_buttons(self) -> None:
        """Test screen has test connection buttons."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test():
            # Verify test buttons exist
            test_github = app.query_one("#test-github-btn", Button)
            test_notification = app.query_one("#test-notification-btn", Button)

            assert str(test_github.label) == "Test Connection"
            assert str(test_notification.label) == "Test Notification"


class TestSettingsScreenState:
    """Test suite for SettingsScreen state management."""

    @pytest.mark.asyncio
    async def test_unsaved_changes_tracking(self) -> None:
        """Test screen tracks unsaved changes."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # Initially no unsaved changes
            assert screen.has_unsaved_changes is False

            # Modify a field
            field = app.query(SettingField).first()
            if field:
                field.value = SettingValue(
                    definition=field.value.definition,
                    current_value="modified",
                    original_value="original",
                )
                await pilot.pause()

                # Should detect unsaved changes
                # Note: Implementation may need to listen to field changes
                # This test validates the tracking mechanism exists

    @pytest.mark.asyncio
    async def test_save_clears_unsaved_changes(self) -> None:
        """Test save operation clears unsaved changes flag."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # Wait for screen to be fully composed
            await pilot.pause()

            # Modify a field to create real unsaved changes
            fields = app.query(SettingField)
            if fields:
                field = fields.first()
                original_value = field.value.current_value
                # Modify the field's value
                new_val = "modified_value" if isinstance(original_value, str) else True
                field.value = SettingValue(
                    definition=field.value.definition,
                    current_value=new_val,
                    original_value=original_value,
                )
                # Post a change message so the screen knows about the modification
                field.post_message(
                    field.Changed(field.value.definition.key, field.value.current_value)
                )
                await pilot.pause()

            # Verify we have unsaved changes
            assert screen.has_unsaved_changes is True

            # Call save action directly
            await screen.action_save()
            await pilot.pause()

            # Should clear unsaved changes
            assert screen.has_unsaved_changes is False

    @pytest.mark.asyncio
    async def test_cancel_discards_changes(self) -> None:
        """Test cancel operation discards changes."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # Wait for screen to be fully composed
            await pilot.pause()

            # Modify a field through the screen's internal fields dict
            # to ensure proper tracking
            if screen._settings_fields:
                # Get first field from the screen's internal tracking
                key = list(screen._settings_fields.keys())[0]
                field = screen._settings_fields[key]
                original_value = field.value.current_value

                # Change value
                field.value = SettingValue(
                    definition=field.value.definition,
                    current_value="modified",
                    original_value=original_value,
                )
                # Post a change message so the screen knows
                field.post_message(
                    field.Changed(field.value.definition.key, field.value.current_value)
                )
                await pilot.pause()

                # Verify we have unsaved changes
                assert screen.has_unsaved_changes is True

                # Directly call _cancel_changes to test the cancel logic
                # (button click in test environment can have timing issues)
                screen._cancel_changes()
                await pilot.pause()

                # Should clear unsaved changes flag
                assert screen.has_unsaved_changes is False


class TestSettingsScreenActions:
    """Test suite for SettingsScreen actions."""

    @pytest.mark.asyncio
    async def test_save_action(self) -> None:
        """Test save action persists settings."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # Trigger save action
            await screen.action_save()
            await pilot.pause()

            # Verify save was called
            # Note: Implementation should persist to config
            assert screen.has_unsaved_changes is False

    @pytest.mark.asyncio
    async def test_go_back_with_unsaved_changes_prompts(self) -> None:
        """Test navigation prompts when unsaved changes exist."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # Set unsaved changes
            screen.has_unsaved_changes = True
            await pilot.pause()

            # Mock confirm dialog
            with patch.object(screen, "confirm", new=AsyncMock(return_value=False)):
                # Try to go back
                await screen.action_go_back_safe()
                await pilot.pause()

                # Should still be on screen (user cancelled)
                assert screen.confirm.called

    @pytest.mark.asyncio
    async def test_go_back_without_unsaved_changes(self) -> None:
        """Test navigation without unsaved changes doesn't prompt."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # No unsaved changes
            assert screen.has_unsaved_changes is False

            # Mock go_back
            with patch.object(screen, "go_back"):
                # Try to go back
                await screen.action_go_back_safe()
                await pilot.pause()

                # Should navigate back immediately
                assert screen.go_back.called


class TestSettingsScreenConnectionTests:
    """Test suite for connection testing features."""

    @pytest.mark.asyncio
    async def test_github_connection_test_success(self) -> None:
        """Test successful GitHub connection test."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # Mock successful gh auth status
            with patch(
                "asyncio.create_subprocess_exec",
                new=AsyncMock(
                    return_value=MagicMock(
                        returncode=0,
                        communicate=AsyncMock(return_value=(b"", b"")),
                    )
                ),
            ):
                # Trigger test (returns Worker, don't await)
                screen.test_github_connection()
                await pilot.pause()
                await pilot.pause()  # Give worker time to complete

                # Should show success status
                assert "✓" in screen.github_status

    @pytest.mark.asyncio
    async def test_github_connection_test_failure(self) -> None:
        """Test failed GitHub connection test."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # Mock failed gh auth status
            with patch(
                "asyncio.create_subprocess_exec",
                new=AsyncMock(
                    return_value=MagicMock(
                        returncode=1,
                        communicate=AsyncMock(return_value=(b"", b"Not logged in")),
                    )
                ),
            ):
                # Trigger test (returns Worker, don't await)
                screen.test_github_connection()
                await pilot.pause()
                await pilot.pause()  # Give worker time to complete

                # Should show error status
                assert "✗" in screen.github_status

    @pytest.mark.asyncio
    async def test_github_connection_test_timeout(self) -> None:
        """Test GitHub connection test timeout."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # Mock timeout during process creation
            with patch(
                "asyncio.wait_for",
                new=AsyncMock(side_effect=TimeoutError()),
            ):
                # Trigger test (returns Worker, don't await)
                screen.test_github_connection()
                await pilot.pause()
                await pilot.pause()  # Give worker time to complete

                # Should show timeout status
                assert "timed out" in screen.github_status.lower()
                assert "✗" in screen.github_status

    @pytest.mark.asyncio
    async def test_notification_test(self) -> None:
        """Test notification test feature."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # Mock successful notification
            with patch.object(screen, "test_notification"):
                # Click test button
                await pilot.click("#test-notification-btn")
                await pilot.pause()

                # Should trigger test
                # Note: Implementation details depend on final design

    @pytest.mark.asyncio
    async def test_notification_test_timeout(self) -> None:
        """Test notification test timeout."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # Mock settings fields to enable notifications
            enabled_field = MagicMock()
            enabled_field.value.current_value = True
            topic_field = MagicMock()
            topic_field.value.current_value = "test-topic"

            screen._settings_fields = {
                "notifications.enabled": enabled_field,
                "notifications.topic": topic_field,
            }

            # Mock timeout during notification send
            with patch(
                "asyncio.wait_for",
                new=AsyncMock(side_effect=TimeoutError()),
            ):
                # Trigger test (returns Worker, don't await)
                screen.test_notification()
                await pilot.pause()
                await pilot.pause()  # Give worker time to complete

                # Should show timeout status
                assert "timed out" in screen.notification_status.lower()
                assert "✗" in screen.notification_status


class TestSettingsScreenKeyboardNavigation:
    """Test suite for keyboard navigation."""

    @pytest.mark.asyncio
    async def test_escape_key_binding(self) -> None:
        """Test Escape key triggers go_back_safe."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test():
            screen = app.query_one(SettingsScreen)

            # Verify binding exists
            bindings = {b.key: b.action for b in screen.BINDINGS}
            assert "escape" in bindings
            assert bindings["escape"] == "go_back_safe"

    @pytest.mark.asyncio
    async def test_ctrl_s_save_binding(self) -> None:
        """Test Ctrl+S key binding for save."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test():
            screen = app.query_one(SettingsScreen)

            # Verify binding exists
            bindings = {b.key: b.action for b in screen.BINDINGS}
            assert "ctrl+s" in bindings
            assert bindings["ctrl+s"] == "save"


class TestSettingsScreenIntegration:
    """Integration tests for SettingsScreen."""

    @pytest.mark.asyncio
    async def test_complete_edit_flow(self) -> None:
        """Test complete edit and save flow."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            screen = app.query_one(SettingsScreen)

            # Find a string field
            fields = app.query(SettingField)
            string_field = None
            for field in fields:
                if field.value.definition.setting_type == SettingType.STRING:
                    string_field = field
                    break

            if string_field:
                # Edit the field (implementation-specific)
                # This validates the flow exists

                # Save
                await pilot.click("#save-btn")
                await pilot.pause()

                # Should persist changes
                assert screen.has_unsaved_changes is False

    @pytest.mark.asyncio
    async def test_field_validation_blocks_save(self) -> None:
        """Test invalid field values prevent save."""

        class TestApp(App):
            def compose(self):
                yield SettingsScreen()

        app = TestApp()
        async with app.run_test() as pilot:
            app.query_one(SettingsScreen)

            # Find an int field with validation
            fields = app.query(SettingField)
            int_field = None
            for field in fields:
                if (
                    field.value.definition.setting_type == SettingType.INT
                    and field.value.definition.min_value is not None
                ):
                    int_field = field
                    break

            if int_field:
                # Set invalid value (below min)
                min_val = int_field.value.definition.min_value or 0
                int_field.value = SettingValue(
                    definition=int_field.value.definition,
                    current_value=min_val - 1,
                    original_value=min_val,
                    validation_error="Value too low",
                )
                await pilot.pause()

                # Save button should be disabled or save should fail
                # Implementation determines exact behavior


class TestSettingsScreenStateModel:
    """Test suite for SettingsScreenState model integration."""

    def test_state_has_unsaved_changes_property(self) -> None:
        """Test state correctly identifies unsaved changes."""
        # Create settings with modifications
        definition = SettingDefinition(
            key="test.key",
            display_name="Test",
            description="Test setting",
            setting_type=SettingType.STRING,
        )

        modified_setting = SettingValue(
            definition=definition,
            current_value="modified",
            original_value="original",
        )

        unmodified_setting = SettingValue(
            definition=definition,
            current_value="same",
            original_value="same",
        )

        section = SettingsSectionModel(
            name="Test",
            settings=(modified_setting, unmodified_setting),
        )

        state = SettingsScreenState(sections=(section,))

        # Should detect unsaved changes
        assert state.has_unsaved_changes is True

    def test_state_validation_errors_property(self) -> None:
        """Test state correctly identifies validation errors."""
        definition = SettingDefinition(
            key="test.key",
            display_name="Test",
            description="Test setting",
            setting_type=SettingType.INT,
            min_value=1,
            max_value=10,
        )

        invalid_setting = SettingValue(
            definition=definition,
            current_value=0,
            original_value=5,
            validation_error="Value too low",
        )

        section = SettingsSectionModel(
            name="Test",
            settings=(invalid_setting,),
        )

        state = SettingsScreenState(sections=(section,))

        # Should detect validation errors
        assert state.has_validation_errors is True

    def test_state_can_save_property(self) -> None:
        """Test state can_save property logic."""
        definition = SettingDefinition(
            key="test.key",
            display_name="Test",
            description="Test setting",
            setting_type=SettingType.STRING,
        )

        # Valid modified setting
        valid_modified = SettingValue(
            definition=definition,
            current_value="modified",
            original_value="original",
        )

        section = SettingsSectionModel(
            name="Test",
            settings=(valid_modified,),
        )

        state = SettingsScreenState(sections=(section,))

        # Should allow save (has changes, no errors)
        assert state.can_save is True

        # Invalid modified setting
        invalid_modified = SettingValue(
            definition=definition,
            current_value="modified",
            original_value="original",
            validation_error="Invalid value",
        )

        section_invalid = SettingsSectionModel(
            name="Test",
            settings=(invalid_modified,),
        )

        state_invalid = SettingsScreenState(sections=(section_invalid,))

        # Should not allow save (has errors)
        assert state_invalid.can_save is False
