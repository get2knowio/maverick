"""DiffPanel widget for displaying file diffs with line highlighting.

This widget displays file content with syntax highlighting and highlights
the specific line referenced by a review finding.

Feature: Issue #50 - Add side panel with file diffs for selected findings
Date: 2025-12-22
"""

from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from maverick.logging import get_logger

logger = get_logger(__name__)

__all__ = ["DiffPanel"]


class DiffPanel(Widget):
    """Widget for displaying file diffs with line highlighting.

    Features:
    - Syntax highlighting using Rich
    - Line highlighting for the finding location
    - Context lines around the finding (5 lines before/after)
    - Handles missing files gracefully
    - Empty state when no finding is selected

    Example:
        panel = DiffPanel()
        panel.update_diff(file_path="src/main.py", line_number=42)
    """

    DEFAULT_CSS = """
    DiffPanel {
        height: 100%;
        width: 100%;
        border-left: solid $border;
        background: $surface;
    }

    DiffPanel VerticalScroll {
        height: 100%;
        width: 100%;
        background: $surface;
        padding: 1;
    }

    DiffPanel .panel-header {
        height: auto;
        padding: 0 0 1 0;
        border-bottom: solid $border;
        color: $text;
        text-style: bold;
        margin-bottom: 1;
    }

    DiffPanel .file-path {
        color: $accent;
        text-style: bold;
    }

    DiffPanel .line-number {
        color: $text-muted;
    }

    DiffPanel .empty-state {
        height: 100%;
        width: 100%;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }

    DiffPanel .error-state {
        padding: 1;
        background: $error 20%;
        border: solid $error;
        color: $error;
    }

    DiffPanel .code-content {
        background: $surface-elevated;
        border: solid $border;
        padding: 1;
    }
    """

    CONTEXT_LINES = 5  # Lines before and after the target line

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the DiffPanel widget.

        Args:
            name: The name of the widget.
            id: The ID of the widget in the DOM.
            classes: The CSS classes for the widget.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._current_file: Path | None = None
        self._current_line: int | None = None

    def compose(self) -> ComposeResult:
        """Create the diff panel layout.

        Yields:
            ComposeResult: Diff display with header and code content.
        """
        with VerticalScroll(id="diff-scroll"):
            yield Static(
                "[dim]Select a finding to view the file diff[/dim]",
                id="diff-content",
                classes="empty-state",
            )

    def update_diff(
        self,
        file_path: str | Path | None = None,
        line_number: int | None = None,
        working_directory: Path | None = None,
    ) -> None:
        """Update the diff panel with new file content.

        Args:
            file_path: Path to the file to display (relative or absolute).
            line_number: Line number to highlight (1-indexed).
            working_directory: Working directory to resolve relative paths.
                             Defaults to current working directory.
        """
        # Clear if no file provided
        if not file_path or not line_number:
            self._clear_diff()
            return

        # Store current state
        self._current_file = Path(file_path)
        self._current_line = line_number

        # Resolve the file path
        working_dir = working_directory or Path.cwd()
        if not self._current_file.is_absolute():
            resolved_path = working_dir / self._current_file
        else:
            resolved_path = self._current_file

        # Read and display the file content
        try:
            content = self._read_file_with_context(resolved_path, line_number)
            if content is None:
                self._show_error(f"File not found: {resolved_path}")
                return

            self._display_content(resolved_path, line_number, content)

        except Exception as e:
            logger.exception("Error reading file for diff panel: %s", e)
            self._show_error(f"Error reading file: {e}")

    def _read_file_with_context(
        self, file_path: Path, line_number: int
    ) -> tuple[str, int, int] | None:
        """Read file content with context lines around the target line.

        Args:
            file_path: Path to the file to read.
            line_number: Target line number (1-indexed).

        Returns:
            Tuple of (content, start_line, end_line) or None if file not found.
            start_line and end_line are 1-indexed.
        """
        if not file_path.exists():
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()

            # Calculate the range of lines to display
            total_lines = len(lines)
            start_line = max(1, line_number - self.CONTEXT_LINES)
            end_line = min(total_lines, line_number + self.CONTEXT_LINES)

            # Extract the content (convert to 0-indexed for slicing)
            content_lines = lines[start_line - 1 : end_line]
            content = "".join(content_lines)

            return (content, start_line, end_line)

        except Exception as e:
            logger.exception("Error reading file %s: %s", file_path, e)
            return None

    def _display_content(
        self, file_path: Path, target_line: int, content_data: tuple[str, int, int]
    ) -> None:
        """Display the file content with syntax highlighting.

        Args:
            file_path: Path to the file being displayed.
            target_line: The line number to highlight (1-indexed).
            content_data: Tuple of (content, start_line, end_line).
        """
        content, start_line, end_line = content_data

        # Determine the file extension for syntax highlighting
        file_extension = file_path.suffix.lstrip(".")
        lexer = self._get_lexer_for_extension(file_extension)

        # Calculate the relative line number within the displayed content
        highlight_line = target_line - start_line + 1

        # Create syntax-highlighted content
        try:
            syntax_markup: Syntax | str = Syntax(
                content,
                lexer,
                line_numbers=True,
                start_line=start_line,
                highlight_lines={highlight_line},
                theme="monokai",
                line_range=(1, end_line - start_line + 1),
            )
        except Exception as e:
            logger.warning("Failed to create syntax highlighting: %s", e)
            # Fallback to plain text
            syntax_markup = content

        # Build the header
        header_text = (
            f"[bold]File:[/bold] [.file-path]{file_path}[/.file-path]\n"
            f"[bold]Line:[/bold] [.line-number]{target_line}[/.line-number]\n"
            f"[dim]Showing lines {start_line}-{end_line}[/dim]"
        )

        # Update the content widget
        try:
            content_widget = self.query_one("#diff-content", Static)
            content_widget.remove_class("empty-state")
            content_widget.remove_class("error-state")
            content_widget.update("")

            # Remove old children and rebuild the content
            content_widget.update("")
            self._rebuild_content(header_text, syntax_markup)

        except Exception as e:
            logger.exception("Error displaying content: %s", e)
            self._show_error(f"Error displaying content: {e}")

    def _rebuild_content(self, header_text: str, syntax_markup: Syntax | str) -> None:
        """Rebuild the content area with header and code.

        Args:
            header_text: The header text to display.
            syntax_markup: The syntax-highlighted code (Syntax object or str).
        """
        try:
            scroll_widget = self.query_one("#diff-scroll", VerticalScroll)
            scroll_widget.remove_children()

            # Add header
            header = Static(header_text, classes="panel-header")
            scroll_widget.mount(header)

            # Add code content
            code_static = Static(syntax_markup, classes="code-content")
            scroll_widget.mount(code_static)

        except Exception as e:
            logger.exception("Error rebuilding content: %s", e)

    def _get_lexer_for_extension(self, extension: str) -> str:
        """Get the appropriate lexer for a file extension.

        Args:
            extension: File extension (without dot).

        Returns:
            Lexer name for Rich's Syntax class.
        """
        # Map common extensions to lexers
        lexer_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "tsx": "tsx",
            "jsx": "jsx",
            "java": "java",
            "c": "c",
            "cpp": "cpp",
            "cc": "cpp",
            "h": "c",
            "hpp": "cpp",
            "cs": "csharp",
            "go": "go",
            "rs": "rust",
            "rb": "ruby",
            "php": "php",
            "swift": "swift",
            "kt": "kotlin",
            "scala": "scala",
            "sh": "bash",
            "bash": "bash",
            "zsh": "bash",
            "yaml": "yaml",
            "yml": "yaml",
            "json": "json",
            "xml": "xml",
            "html": "html",
            "css": "css",
            "scss": "scss",
            "sql": "sql",
            "md": "markdown",
            "rst": "rst",
            "txt": "text",
        }

        return lexer_map.get(extension.lower(), "text")

    def _clear_diff(self) -> None:
        """Clear the diff panel and show empty state."""
        self._current_file = None
        self._current_line = None

        try:
            scroll_widget = self.query_one("#diff-scroll", VerticalScroll)
            scroll_widget.remove_children()
            scroll_widget.mount(
                Static(
                    "[dim]Select a finding to view the file diff[/dim]",
                    id="diff-content",
                    classes="empty-state",
                )
            )
        except Exception:
            pass

    def _show_error(self, message: str) -> None:
        """Show an error message in the diff panel.

        Args:
            message: Error message to display.
        """
        try:
            scroll_widget = self.query_one("#diff-scroll", VerticalScroll)
            scroll_widget.remove_children()
            error_widget = Static(
                f"[bold]Error:[/bold]\n{message}",
                id="diff-content",
                classes="error-state",
            )
            scroll_widget.mount(error_widget)
        except Exception:
            pass
