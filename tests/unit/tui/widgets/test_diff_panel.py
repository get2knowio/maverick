"""Unit tests for DiffPanel widget."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from maverick.tui.widgets.diff_panel import DiffPanel


class TestDiffPanelInitialization:
    """Tests for DiffPanel initialization."""

    def test_initialization_with_defaults(self) -> None:
        """Test DiffPanel creation with default parameters."""
        panel = DiffPanel()
        assert panel._current_file is None
        assert panel._current_line is None

    def test_initialization_with_custom_parameters(self) -> None:
        """Test DiffPanel creation with custom parameters."""
        panel = DiffPanel(name="custom-diff", id="diff-1", classes="custom")
        assert panel.name == "custom-diff"
        assert panel.id == "diff-1"


class TestDiffPanelUpdateDiff:
    """Tests for update_diff method."""

    def test_update_diff_with_no_file(self) -> None:
        """Test update_diff with no file provided."""
        panel = DiffPanel()

        with patch.object(panel, "_clear_diff") as mock_clear:
            panel.update_diff(file_path=None, line_number=10)

        mock_clear.assert_called_once()

    def test_update_diff_with_no_line_number(self) -> None:
        """Test update_diff with no line number provided."""
        panel = DiffPanel()

        with patch.object(panel, "_clear_diff") as mock_clear:
            panel.update_diff(file_path="test.py", line_number=None)

        mock_clear.assert_called_once()

    def test_update_diff_with_valid_file(self) -> None:
        """Test update_diff with valid file path and line number."""
        panel = DiffPanel()
        test_file = Path("test.py")
        test_content = "def test():\n    pass\n"

        with (
            patch.object(panel, "_read_file_with_context") as mock_read,
            patch.object(panel, "_display_content") as mock_display,
        ):
            mock_read.return_value = (test_content, 1, 2)
            panel.update_diff(file_path=test_file, line_number=1)

        mock_read.assert_called_once()
        mock_display.assert_called_once()

    def test_update_diff_with_missing_file(self) -> None:
        """Test update_diff when file doesn't exist."""
        panel = DiffPanel()
        test_file = Path("nonexistent.py")

        with (
            patch.object(panel, "_read_file_with_context") as mock_read,
            patch.object(panel, "_show_error") as mock_error,
        ):
            mock_read.return_value = None
            panel.update_diff(file_path=test_file, line_number=1)

        mock_error.assert_called_once()

    def test_update_diff_with_relative_path(self) -> None:
        """Test update_diff with relative file path."""
        panel = DiffPanel()
        test_file = Path("src/test.py")
        working_dir = Path("/home/user/project")

        with (
            patch.object(panel, "_read_file_with_context") as mock_read,
            patch.object(panel, "_display_content"),
        ):
            mock_read.return_value = ("content", 1, 2)
            panel.update_diff(
                file_path=test_file, line_number=1, working_directory=working_dir
            )

        # Should resolve relative to working directory
        called_path = mock_read.call_args[0][0]
        assert called_path == working_dir / test_file


class TestDiffPanelReadFileWithContext:
    """Tests for _read_file_with_context method."""

    def test_read_file_with_context_nonexistent_file(self) -> None:
        """Test reading a file that doesn't exist."""
        panel = DiffPanel()
        test_file = Path("/nonexistent/file.py")

        result = panel._read_file_with_context(test_file, 10)

        assert result is None

    def test_read_file_with_context_valid_file(self) -> None:
        """Test reading a valid file with context lines."""
        panel = DiffPanel()
        test_file = Path("test.py")
        # Create test content as a list of lines
        lines = [f"line {i}\n" for i in range(1, 21)]
        test_content = "".join(lines)

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=test_content)),
        ):
            result = panel._read_file_with_context(test_file, 10)

        assert result is not None
        content, start_line, end_line = result
        # Should return 5 lines before and after line 10
        assert start_line == 5
        assert end_line == 15
        assert "line 10" in content

    def test_read_file_with_context_at_file_start(self) -> None:
        """Test reading context when target line is near the start."""
        panel = DiffPanel()
        test_file = Path("test.py")
        lines = [f"line {i}\n" for i in range(1, 11)]
        test_content = "".join(lines)

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=test_content)),
        ):
            result = panel._read_file_with_context(test_file, 2)

        assert result is not None
        content, start_line, end_line = result
        # Should start from line 1 (can't go below)
        assert start_line == 1
        assert end_line == 7

    def test_read_file_with_context_at_file_end(self) -> None:
        """Test reading context when target line is near the end."""
        panel = DiffPanel()
        test_file = Path("test.py")
        lines = [f"line {i}\n" for i in range(1, 11)]
        test_content = "".join(lines)

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=test_content)),
        ):
            result = panel._read_file_with_context(test_file, 9)

        assert result is not None
        content, start_line, end_line = result
        # Should end at line 10 (can't go beyond)
        assert start_line == 4
        assert end_line == 10


class TestDiffPanelGetLexerForExtension:
    """Tests for _get_lexer_for_extension method."""

    def test_get_lexer_for_python(self) -> None:
        """Test lexer selection for Python files."""
        panel = DiffPanel()
        assert panel._get_lexer_for_extension("py") == "python"

    def test_get_lexer_for_javascript(self) -> None:
        """Test lexer selection for JavaScript files."""
        panel = DiffPanel()
        assert panel._get_lexer_for_extension("js") == "javascript"

    def test_get_lexer_for_typescript(self) -> None:
        """Test lexer selection for TypeScript files."""
        panel = DiffPanel()
        assert panel._get_lexer_for_extension("ts") == "typescript"

    def test_get_lexer_for_unknown_extension(self) -> None:
        """Test lexer selection for unknown file extension."""
        panel = DiffPanel()
        assert panel._get_lexer_for_extension("xyz") == "text"

    def test_get_lexer_case_insensitive(self) -> None:
        """Test lexer selection is case-insensitive."""
        panel = DiffPanel()
        assert panel._get_lexer_for_extension("PY") == "python"
        assert panel._get_lexer_for_extension("Js") == "javascript"


class TestDiffPanelClearDiff:
    """Tests for _clear_diff method."""

    def test_clear_diff_resets_state(self) -> None:
        """Test that clear_diff resets the panel state."""
        panel = DiffPanel()
        panel._current_file = Path("test.py")
        panel._current_line = 10

        with patch.object(panel, "query_one") as mock_query:
            mock_scroll = MagicMock()
            mock_query.return_value = mock_scroll
            panel._clear_diff()

        assert panel._current_file is None
        assert panel._current_line is None
        mock_scroll.remove_children.assert_called_once()


class TestDiffPanelShowError:
    """Tests for _show_error method."""

    def test_show_error_displays_message(self) -> None:
        """Test that _show_error displays error message."""
        panel = DiffPanel()
        error_message = "File not found"

        with patch.object(panel, "query_one") as mock_query:
            mock_scroll = MagicMock()
            mock_query.return_value = mock_scroll
            panel._show_error(error_message)

        mock_scroll.remove_children.assert_called_once()
        mock_scroll.mount.assert_called_once()


class TestDiffPanelIntegrationWithReviewScreen:
    """Integration tests for DiffPanel with ReviewScreen."""

    def test_diff_panel_updates_on_issue_selection(self) -> None:
        """Test that diff panel updates when an issue is selected."""
        panel = DiffPanel()
        test_file = Path("test.py")
        test_line = 42

        with (
            patch.object(panel, "_read_file_with_context") as mock_read,
            patch.object(panel, "_display_content") as mock_display,
        ):
            mock_read.return_value = ("content", 37, 47)
            panel.update_diff(file_path=test_file, line_number=test_line)

        assert panel._current_file == test_file
        assert panel._current_line == test_line
        mock_display.assert_called_once()

    def test_diff_panel_clears_on_no_selection(self) -> None:
        """Test that diff panel clears when no issue is selected."""
        panel = DiffPanel()
        panel._current_file = Path("test.py")
        panel._current_line = 10

        with patch.object(panel, "_clear_diff") as mock_clear:
            panel.update_diff(file_path=None, line_number=None)

        mock_clear.assert_called_once()
