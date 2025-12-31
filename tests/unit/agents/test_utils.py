"""Unit tests for agent utility functions.

Tests for text extraction utilities that process Claude SDK Message objects.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.agents.utils import detect_file_changes, extract_all_text, extract_text
from maverick.models.implementation import ChangeType, FileChange

# =============================================================================
# Mock Objects
# =============================================================================


def create_text_block(text: str) -> MagicMock:
    """Create a mock TextBlock with text attribute.

    Args:
        text: The text content for the block.

    Returns:
        Mock TextBlock object.
    """
    block = MagicMock()
    block.text = text
    # Set type name for type checking
    type(block).__name__ = "TextBlock"
    return block


def create_tool_use_block(tool_name: str) -> MagicMock:
    """Create a mock ToolUseBlock (non-text content).

    Args:
        tool_name: The name of the tool being used.

    Returns:
        Mock ToolUseBlock object.
    """
    block = MagicMock()
    block.name = tool_name
    type(block).__name__ = "ToolUseBlock"
    return block


def create_assistant_message(content_blocks: list[MagicMock]) -> MagicMock:
    """Create a mock AssistantMessage with content list.

    Args:
        content_blocks: List of content blocks (TextBlock, ToolUseBlock, etc.).

    Returns:
        Mock AssistantMessage object.
    """
    message = MagicMock()
    message.content = content_blocks
    type(message).__name__ = "AssistantMessage"
    return message


def create_user_message(text: str) -> MagicMock:
    """Create a mock UserMessage (non-assistant message type).

    Args:
        text: The message text content.

    Returns:
        Mock UserMessage object.
    """
    message = MagicMock()
    message.text = text
    type(message).__name__ = "UserMessage"
    return message


def create_system_message(text: str) -> MagicMock:
    """Create a mock SystemMessage (non-assistant message type).

    Args:
        text: The message text content.

    Returns:
        Mock SystemMessage object.
    """
    message = MagicMock()
    message.text = text
    type(message).__name__ = "SystemMessage"
    return message


# =============================================================================
# extract_text Tests
# =============================================================================


class TestExtractText:
    """Tests for extract_text function."""

    def test_extracts_text_from_message_with_single_text_block(self) -> None:
        """Test extracts text from message with TextBlock content."""
        # Arrange
        text_block = create_text_block("Hello, world!")
        message = create_assistant_message([text_block])

        # Act
        result = extract_text(message)

        # Assert
        assert result == "Hello, world!"

    def test_handles_message_with_multiple_text_blocks(self) -> None:
        """Test handles message with multiple TextBlocks."""
        # Arrange
        text_block1 = create_text_block("First paragraph.")
        text_block2 = create_text_block("Second paragraph.")
        message = create_assistant_message([text_block1, text_block2])

        # Act
        result = extract_text(message)

        # Assert
        # Should concatenate multiple text blocks with newline
        assert result == "First paragraph.\nSecond paragraph."

    def test_handles_message_with_mixed_content_blocks(self) -> None:
        """Test handles message with mixed content blocks (only extracts TextBlock)."""
        # Arrange
        text_block = create_text_block("Here is some text.")
        tool_block = create_tool_use_block("Read")
        message = create_assistant_message([text_block, tool_block])

        # Act
        result = extract_text(message)

        # Assert
        # Should only extract text from TextBlock, ignore ToolUseBlock
        assert result == "Here is some text."

    def test_handles_empty_content_list(self) -> None:
        """Test handles message with empty content list."""
        # Arrange
        message = create_assistant_message([])

        # Act
        result = extract_text(message)

        # Assert
        assert result == ""

    def test_handles_message_with_only_non_text_blocks(self) -> None:
        """Test handles message with only non-text content blocks."""
        # Arrange
        tool_block1 = create_tool_use_block("Read")
        tool_block2 = create_tool_use_block("Write")
        message = create_assistant_message([tool_block1, tool_block2])

        # Act
        result = extract_text(message)

        # Assert
        assert result == ""

    def test_handles_none_input(self) -> None:
        """Test handles None input gracefully."""
        # Act
        result = extract_text(None)

        # Assert
        assert result == ""

    def test_handles_message_without_content_attribute(self) -> None:
        """Test handles message without content attribute."""
        # Arrange
        message = MagicMock(spec=[])  # No content attribute

        # Act
        result = extract_text(message)

        # Assert
        assert result == ""


# =============================================================================
# extract_all_text Tests
# =============================================================================


class TestExtractAllText:
    """Tests for extract_all_text function."""

    def test_extracts_and_concatenates_text_from_multiple_assistant_messages(
        self,
    ) -> None:
        """Test extracts and concatenates text from multiple AssistantMessages."""
        # Arrange
        message1 = create_assistant_message([create_text_block("First message.")])
        message2 = create_assistant_message([create_text_block("Second message.")])
        message3 = create_assistant_message([create_text_block("Third message.")])
        messages = [message1, message2, message3]

        # Act
        result = extract_all_text(messages)

        # Assert
        # Should join with double newlines
        assert result == "First message.\n\nSecond message.\n\nThird message."

    def test_filters_non_assistant_message_objects_from_list(self) -> None:
        """Test filters non-AssistantMessage objects from list."""
        # Arrange
        assistant_msg = create_assistant_message([create_text_block("Assistant text.")])
        user_msg = create_user_message("User text.")
        system_msg = create_system_message("System text.")
        messages = [user_msg, assistant_msg, system_msg]

        # Act
        result = extract_all_text(messages)

        # Assert
        # Should only extract text from AssistantMessage
        assert result == "Assistant text."

    def test_returns_empty_string_for_empty_list(self) -> None:
        """Test returns empty string for empty list."""
        # Arrange
        messages: list[MagicMock] = []

        # Act
        result = extract_all_text(messages)

        # Assert
        assert result == ""

    def test_returns_empty_string_for_list_with_no_assistant_messages(self) -> None:
        """Test returns empty string for list with no AssistantMessages."""
        # Arrange
        user_msg = create_user_message("User text.")
        system_msg = create_system_message("System text.")
        messages = [user_msg, system_msg]

        # Act
        result = extract_all_text(messages)

        # Assert
        assert result == ""

    def test_joins_text_with_double_newline_separator(self) -> None:
        """Test joins text with double newline separator."""
        # Arrange
        message1 = create_assistant_message([create_text_block("Line 1")])
        message2 = create_assistant_message([create_text_block("Line 2")])
        messages = [message1, message2]

        # Act
        result = extract_all_text(messages)

        # Assert
        assert result == "Line 1\n\nLine 2"

    def test_handles_messages_with_multiple_text_blocks(self) -> None:
        """Test handles messages where each has multiple TextBlocks."""
        # Arrange
        message1 = create_assistant_message(
            [
                create_text_block("First part."),
                create_text_block("Second part."),
            ]
        )
        message2 = create_assistant_message(
            [
                create_text_block("Third part."),
                create_text_block("Fourth part."),
            ]
        )
        messages = [message1, message2]

        # Act
        result = extract_all_text(messages)

        # Assert
        # Each message's text blocks joined with newline, messages with double newline
        assert result == "First part.\nSecond part.\n\nThird part.\nFourth part."

    def test_handles_messages_with_mixed_content_blocks(self) -> None:
        """Test handles messages with mixed content (text and tool use)."""
        # Arrange
        message1 = create_assistant_message(
            [
                create_text_block("Reading file..."),
                create_tool_use_block("Read"),
            ]
        )
        message2 = create_assistant_message(
            [
                create_tool_use_block("Write"),
                create_text_block("File written."),
            ]
        )
        messages = [message1, message2]

        # Act
        result = extract_all_text(messages)

        # Assert
        # Should only extract TextBlocks
        assert result == "Reading file...\n\nFile written."

    def test_handles_messages_with_empty_content(self) -> None:
        """Test handles messages with empty content lists."""
        # Arrange
        message1 = create_assistant_message([create_text_block("Has content.")])
        message2 = create_assistant_message([])  # Empty content
        message3 = create_assistant_message([create_text_block("Also has content.")])
        messages = [message1, message2, message3]

        # Act
        result = extract_all_text(messages)

        # Assert
        # Should skip empty messages in concatenation
        assert result == "Has content.\n\nAlso has content."

    def test_handles_single_message_in_list(self) -> None:
        """Test handles single message in list (no joining needed)."""
        # Arrange
        message = create_assistant_message([create_text_block("Single message.")])
        messages = [message]

        # Act
        result = extract_all_text(messages)

        # Assert
        assert result == "Single message."

    def test_handles_none_in_message_list(self) -> None:
        """Test handles None values in message list."""
        # Arrange
        message1 = create_assistant_message([create_text_block("First.")])
        message2 = None
        message3 = create_assistant_message([create_text_block("Third.")])
        messages = [message1, message2, message3]

        # Act
        result = extract_all_text(messages)

        # Assert
        # Should skip None values
        assert result == "First.\n\nThird."


# =============================================================================
# detect_file_changes Tests
# =============================================================================


class TestDetectFileChanges:
    """Tests for detect_file_changes function."""

    @pytest.mark.asyncio
    async def test_detect_file_changes_returns_list(self, tmp_path: Path) -> None:
        """Test returns list of FileChange objects."""
        from maverick.git import DiffStats

        mock_stats = DiffStats(
            files_changed=2,
            insertions=30,
            deletions=2,
            file_list=("src/file.py", "tests/test_file.py"),
            per_file={
                "src/file.py": (10, 2),
                "tests/test_file.py": (20, 0),
            },
        )

        mock_repo = MagicMock()
        mock_repo.diff_stats = AsyncMock(return_value=mock_stats)

        with patch("maverick.git.AsyncGitRepository", return_value=mock_repo):
            changes = await detect_file_changes(tmp_path)

            assert isinstance(changes, list)
            assert len(changes) == 2
            assert all(isinstance(c, FileChange) for c in changes)

    @pytest.mark.asyncio
    async def test_detect_file_changes_parses_stats_correctly(
        self, tmp_path: Path
    ) -> None:
        """Test correctly parses file stats into FileChange objects."""
        from maverick.git import DiffStats

        mock_stats = DiffStats(
            files_changed=1,
            insertions=15,
            deletions=3,
            file_list=("src/module.py",),
            per_file={"src/module.py": (15, 3)},
        )

        mock_repo = MagicMock()
        mock_repo.diff_stats = AsyncMock(return_value=mock_stats)

        with patch("maverick.git.AsyncGitRepository", return_value=mock_repo):
            changes = await detect_file_changes(tmp_path)

            assert len(changes) == 1
            assert changes[0].file_path == "src/module.py"
            assert changes[0].lines_added == 15
            assert changes[0].lines_removed == 3
            assert changes[0].change_type == ChangeType.MODIFIED

    @pytest.mark.asyncio
    async def test_detect_file_changes_handles_errors_gracefully(
        self, tmp_path: Path
    ) -> None:
        """Test returns empty list on git errors."""
        with patch(
            "maverick.git.AsyncGitRepository",
            side_effect=Exception("Git command failed"),
        ):
            changes = await detect_file_changes(tmp_path)

            assert changes == []

    @pytest.mark.asyncio
    async def test_detect_file_changes_handles_empty_diff(self, tmp_path: Path) -> None:
        """Test handles empty diff stats (no changes)."""
        from maverick.git import DiffStats

        mock_stats = DiffStats(
            files_changed=0,
            insertions=0,
            deletions=0,
            file_list=(),
            per_file={},
        )

        mock_repo = MagicMock()
        mock_repo.diff_stats = AsyncMock(return_value=mock_stats)

        with patch("maverick.git.AsyncGitRepository", return_value=mock_repo):
            changes = await detect_file_changes(tmp_path)

            assert changes == []
