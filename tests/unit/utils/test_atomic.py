"""Unit tests for atomic file write utilities."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maverick.utils.atomic import atomic_write_json, atomic_write_text


class TestAtomicWriteText:
    """Tests for atomic_write_text function."""

    def test_write_text_creates_file(self, tmp_path: Path) -> None:
        """Test that atomic_write_text creates a new file."""
        file_path = tmp_path / "test.txt"
        content = "Hello, world!"

        atomic_write_text(file_path, content)

        assert file_path.exists()
        assert file_path.read_text() == content

    def test_write_text_overwrites_existing(self, tmp_path: Path) -> None:
        """Test that atomic_write_text overwrites existing file."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("original content")

        atomic_write_text(file_path, "new content")

        assert file_path.read_text() == "new content"

    def test_write_text_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test that atomic_write_text creates parent directories when mkdir=True."""
        file_path = tmp_path / "subdir" / "nested" / "test.txt"
        content = "nested content"

        atomic_write_text(file_path, content, mkdir=True)

        assert file_path.exists()
        assert file_path.read_text() == content

    def test_write_text_fails_without_mkdir_if_parent_missing(
        self, tmp_path: Path
    ) -> None:
        """Test that atomic_write_text fails when mkdir=False and parent missing."""
        file_path = tmp_path / "nonexistent" / "test.txt"

        with pytest.raises(OSError):
            atomic_write_text(file_path, "content", mkdir=False)

    def test_write_text_accepts_str_path(self, tmp_path: Path) -> None:
        """Test that atomic_write_text accepts string paths."""
        file_path = str(tmp_path / "test.txt")
        content = "string path content"

        atomic_write_text(file_path, content)

        assert Path(file_path).read_text() == content

    def test_write_text_custom_encoding(self, tmp_path: Path) -> None:
        """Test that atomic_write_text respects encoding parameter."""
        file_path = tmp_path / "test.txt"
        # Unicode content that needs specific encoding
        content = "Hello, \u4e16\u754c!"  # "Hello, World!" in Chinese

        atomic_write_text(file_path, content, encoding="utf-8")

        assert file_path.read_text(encoding="utf-8") == content

    def test_write_text_no_temp_file_remains_on_success(self, tmp_path: Path) -> None:
        """Test that no temporary files remain after successful write."""
        file_path = tmp_path / "test.txt"

        atomic_write_text(file_path, "content")

        # Check no temp files in directory
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_write_text_preserves_content_integrity(self, tmp_path: Path) -> None:
        """Test that content is written exactly as provided."""
        file_path = tmp_path / "test.txt"
        # Content with special characters, newlines, etc.
        content = "Line 1\nLine 2\n\tIndented\n\u2603 Snowman"

        atomic_write_text(file_path, content)

        assert file_path.read_text() == content


class TestAtomicWriteJson:
    """Tests for atomic_write_json function."""

    def test_write_json_creates_file(self, tmp_path: Path) -> None:
        """Test that atomic_write_json creates a new JSON file."""
        file_path = tmp_path / "test.json"
        data = {"key": "value", "number": 42}

        atomic_write_json(file_path, data)

        assert file_path.exists()
        loaded = json.loads(file_path.read_text())
        assert loaded == data

    def test_write_json_with_indentation(self, tmp_path: Path) -> None:
        """Test that atomic_write_json respects indent parameter."""
        file_path = tmp_path / "test.json"
        data = {"key": "value"}

        atomic_write_json(file_path, data, indent=4)

        content = file_path.read_text()
        # With indent=4, should have proper formatting
        assert "    " in content  # 4-space indent
        assert json.loads(content) == data

    def test_write_json_compact(self, tmp_path: Path) -> None:
        """Test that atomic_write_json with indent=None produces compact JSON."""
        file_path = tmp_path / "test.json"
        data = {"key": "value", "items": [1, 2, 3]}

        atomic_write_json(file_path, data, indent=None)

        content = file_path.read_text()
        # Compact JSON should not have newlines within the content
        assert "\n" not in content
        assert json.loads(content) == data

    def test_write_json_preserves_unicode(self, tmp_path: Path) -> None:
        """Test that atomic_write_json preserves Unicode with ensure_ascii=False."""
        file_path = tmp_path / "test.json"
        data = {"greeting": "\u4f60\u597d"}  # "Hello" in Chinese

        atomic_write_json(file_path, data, ensure_ascii=False)

        content = file_path.read_text()
        assert "\u4f60\u597d" in content  # Unicode preserved, not escaped
        assert json.loads(content) == data

    def test_write_json_escapes_unicode_when_requested(self, tmp_path: Path) -> None:
        """Test that atomic_write_json escapes Unicode with ensure_ascii=True."""
        file_path = tmp_path / "test.json"
        data = {"greeting": "\u4f60\u597d"}

        atomic_write_json(file_path, data, ensure_ascii=True)

        content = file_path.read_text()
        assert "\\u4f60\\u597d" in content  # Unicode escaped
        assert json.loads(content) == data

    def test_write_json_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test that atomic_write_json creates parent directories when mkdir=True."""
        file_path = tmp_path / "subdir" / "nested" / "test.json"
        data = {"nested": True}

        atomic_write_json(file_path, data, mkdir=True)

        assert file_path.exists()
        assert json.loads(file_path.read_text()) == data

    def test_write_json_fails_without_mkdir_if_parent_missing(
        self, tmp_path: Path
    ) -> None:
        """Test that atomic_write_json fails when mkdir=False and parent missing."""
        file_path = tmp_path / "nonexistent" / "test.json"

        with pytest.raises(OSError):
            atomic_write_json(file_path, {"key": "value"}, mkdir=False)

    def test_write_json_accepts_str_path(self, tmp_path: Path) -> None:
        """Test that atomic_write_json accepts string paths."""
        file_path = str(tmp_path / "test.json")
        data = {"string_path": True}

        atomic_write_json(file_path, data)

        assert json.loads(Path(file_path).read_text()) == data

    def test_write_json_raises_on_non_serializable(self, tmp_path: Path) -> None:
        """Test that atomic_write_json raises TypeError for non-serializable data."""
        file_path = tmp_path / "test.json"
        data = {"function": lambda x: x}  # Functions are not JSON serializable

        with pytest.raises(TypeError):
            atomic_write_json(file_path, data)

    def test_write_json_list_data(self, tmp_path: Path) -> None:
        """Test that atomic_write_json handles list data."""
        file_path = tmp_path / "test.json"
        data = [1, 2, {"nested": "value"}, [3, 4]]

        atomic_write_json(file_path, data)

        assert json.loads(file_path.read_text()) == data

    def test_write_json_no_temp_file_remains_on_success(self, tmp_path: Path) -> None:
        """Test that no temporary files remain after successful write."""
        file_path = tmp_path / "test.json"

        atomic_write_json(file_path, {"key": "value"})

        # Check no temp files in directory
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0


class TestAtomicWriteIntegration:
    """Integration tests for atomic write functions."""

    def test_multiple_sequential_writes(self, tmp_path: Path) -> None:
        """Test multiple sequential writes to the same file."""
        file_path = tmp_path / "test.txt"

        for i in range(5):
            atomic_write_text(file_path, f"content-{i}")
            assert file_path.read_text() == f"content-{i}"

    def test_write_large_content(self, tmp_path: Path) -> None:
        """Test writing large content atomically."""
        file_path = tmp_path / "large.txt"
        # 1MB of content
        content = "x" * (1024 * 1024)

        atomic_write_text(file_path, content)

        assert file_path.read_text() == content

    def test_write_json_complex_structure(self, tmp_path: Path) -> None:
        """Test writing complex nested JSON structure."""
        file_path = tmp_path / "complex.json"
        data = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "array": [1, "two", 3.0, None],
            "nested": {"deep": {"value": "found"}},
        }

        atomic_write_json(file_path, data)

        assert json.loads(file_path.read_text()) == data
