"""Tests for WorkflowLocator class."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from maverick.dsl.discovery.locator import WorkflowLocator


class TestWorkflowLocator:
    """Tests for WorkflowLocator class."""

    # T137: WorkflowLocator scan() with empty directory
    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        """Should return empty list when scanning empty directory."""
        locator = WorkflowLocator()
        result = locator.scan(tmp_path)
        assert result == []

    # T138: WorkflowLocator scan() with non-existent directory
    def test_scan_nonexistent_directory(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should return empty list and log warning for non-existent directory."""
        locator = WorkflowLocator()
        nonexistent = tmp_path / "does_not_exist"

        with caplog.at_level(logging.WARNING):
            result = locator.scan(nonexistent)

        assert result == []
        assert "does not exist" in caplog.text
        assert str(nonexistent) in caplog.text

    # T139: WorkflowLocator scan() with file path instead of directory
    def test_scan_file_instead_of_directory(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should return empty list and log warning when path is a file."""
        locator = WorkflowLocator()
        file_path = tmp_path / "not_a_directory.txt"
        file_path.write_text("dummy content")

        with caplog.at_level(logging.WARNING):
            result = locator.scan(file_path)

        assert result == []
        assert "not a directory" in caplog.text
        assert str(file_path) in caplog.text

    # T140: WorkflowLocator scan() finds YAML files
    def test_scan_finds_yaml_files(self, tmp_path: Path) -> None:
        """Should find all *.yaml files in directory."""
        locator = WorkflowLocator()

        # Create multiple YAML files
        yaml1 = tmp_path / "workflow1.yaml"
        yaml2 = tmp_path / "workflow2.yaml"
        yaml3 = tmp_path / "another-workflow.yaml"

        yaml1.write_text("name: workflow1")
        yaml2.write_text("name: workflow2")
        yaml3.write_text("name: another-workflow")

        result = locator.scan(tmp_path)

        assert len(result) == 3
        assert yaml1 in result
        assert yaml2 in result
        assert yaml3 in result

    # T141: WorkflowLocator scan() ignores non-YAML files
    def test_scan_ignores_non_yaml_files(self, tmp_path: Path) -> None:
        """Should only return *.yaml files, ignoring other extensions."""
        locator = WorkflowLocator()

        # Create YAML files
        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text("name: workflow")

        # Create non-YAML files that should be ignored
        py_file = tmp_path / "script.py"
        py_file.write_text("print('hello')")

        json_file = tmp_path / "config.json"
        json_file.write_text('{"key": "value"}')

        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("readme content")

        yml_file = tmp_path / "workflow.yml"
        yml_file.write_text("name: yml_workflow")

        md_file = tmp_path / "docs.md"
        md_file.write_text("# Documentation")

        result = locator.scan(tmp_path)

        # Should only find the .yaml file
        assert len(result) == 1
        assert yaml_file in result

        # Verify other files are not included
        assert py_file not in result
        assert json_file not in result
        assert txt_file not in result
        assert yml_file not in result
        assert md_file not in result

    # T142: WorkflowLocator scan() ignores directories with .yaml extension
    def test_scan_ignores_directories_matching_yaml_pattern(
        self, tmp_path: Path
    ) -> None:
        """Should ignore directories even if they match *.yaml pattern."""
        locator = WorkflowLocator()

        # Create a regular YAML file
        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text("name: workflow")

        # Create a directory with .yaml extension
        yaml_dir = tmp_path / "workflows.yaml"
        yaml_dir.mkdir()

        # Create a file inside the directory
        (yaml_dir / "nested.txt").write_text("content")

        result = locator.scan(tmp_path)

        # Should only find the file, not the directory
        assert len(result) == 1
        assert yaml_file in result
        assert yaml_dir not in result

    # T143: WorkflowLocator scan() handles permission errors
    def test_scan_handles_permission_errors(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should handle permission errors gracefully and return empty list."""
        locator = WorkflowLocator()

        # Mock Path.glob to raise PermissionError
        with patch.object(Path, "glob", side_effect=PermissionError("Access denied")):
            with caplog.at_level(logging.WARNING):
                result = locator.scan(tmp_path)

            assert result == []
            assert "Permission denied" in caplog.text

    # T144: WorkflowLocator scan() handles OSError
    def test_scan_handles_os_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should handle OSError during glob and return empty list."""
        locator = WorkflowLocator()

        # Mock Path.glob to raise OSError
        with patch.object(Path, "glob", side_effect=OSError("Disk I/O error")):
            with caplog.at_level(logging.WARNING):
                result = locator.scan(tmp_path)

            assert result == []
            assert "Error reading" in caplog.text
            assert "Disk I/O error" in caplog.text

    # T145: WorkflowLocator scan() returns absolute paths
    def test_scan_returns_absolute_paths(self, tmp_path: Path) -> None:
        """Should return absolute paths for all found files."""
        locator = WorkflowLocator()

        # Create YAML files
        yaml1 = tmp_path / "workflow1.yaml"
        yaml2 = tmp_path / "workflow2.yaml"
        yaml1.write_text("name: workflow1")
        yaml2.write_text("name: workflow2")

        result = locator.scan(tmp_path)

        # All returned paths should be absolute
        assert len(result) == 2
        for path in result:
            assert path.is_absolute()
            assert path.exists()
            assert path.suffix == ".yaml"

    # T146: WorkflowLocator scan() with relative path
    def test_scan_with_relative_path(self, tmp_path: Path, monkeypatch) -> None:
        """Should handle relative paths correctly."""
        locator = WorkflowLocator()

        # Create a YAML file
        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text("name: workflow")

        # Change to the parent directory and use a relative path
        parent_dir = tmp_path.parent
        relative_dir = tmp_path.name

        monkeypatch.chdir(parent_dir)
        result = locator.scan(Path(relative_dir))

        # Should find the file
        assert len(result) == 1
        # The returned path may be absolute or relative depending on glob behavior
        # But it should point to an existing file
        assert result[0].exists()
        assert result[0].name == "workflow.yaml"

    # T147: WorkflowLocator scan() logs debug message when files found
    def test_scan_logs_debug_when_files_found(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log debug message when workflow files are found."""
        locator = WorkflowLocator()

        # Create YAML files
        (tmp_path / "workflow1.yaml").write_text("name: workflow1")
        (tmp_path / "workflow2.yaml").write_text("name: workflow2")
        (tmp_path / "workflow3.yaml").write_text("name: workflow3")

        with caplog.at_level(logging.DEBUG):
            result = locator.scan(tmp_path)

        assert len(result) == 3
        assert "Found 3 workflow file(s)" in caplog.text
        assert str(tmp_path) in caplog.text

    # T148: WorkflowLocator scan() logs debug message when no files found
    def test_scan_logs_debug_when_no_files_found(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log debug message when no workflow files found in
        existing directory."""
        locator = WorkflowLocator()

        # Create some non-YAML files
        (tmp_path / "readme.txt").write_text("readme")
        (tmp_path / "config.json").write_text("{}")

        with caplog.at_level(logging.DEBUG):
            result = locator.scan(tmp_path)

        assert len(result) == 0
        assert "No workflow files found" in caplog.text
        assert str(tmp_path) in caplog.text

    # T149: WorkflowLocator scan() multiple times is consistent
    def test_scan_multiple_times_consistent(self, tmp_path: Path) -> None:
        """Should return consistent results across multiple scans."""
        locator = WorkflowLocator()

        # Create YAML files
        yaml1 = tmp_path / "workflow1.yaml"
        yaml2 = tmp_path / "workflow2.yaml"
        yaml1.write_text("name: workflow1")
        yaml2.write_text("name: workflow2")

        # Scan multiple times
        result1 = locator.scan(tmp_path)
        result2 = locator.scan(tmp_path)
        result3 = locator.scan(tmp_path)

        # All results should be identical
        assert len(result1) == 2
        assert set(result1) == set(result2)
        assert set(result2) == set(result3)

    # T150: WorkflowLocator scan() is non-recursive
    def test_scan_is_non_recursive(self, tmp_path: Path) -> None:
        """Should only scan immediate directory, not subdirectories."""
        locator = WorkflowLocator()

        # Create YAML file in the directory
        yaml_in_root = tmp_path / "workflow.yaml"
        yaml_in_root.write_text("name: root_workflow")

        # Create subdirectory with YAML file
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        yaml_in_subdir = subdir / "nested_workflow.yaml"
        yaml_in_subdir.write_text("name: nested_workflow")

        # Create nested subdirectory with YAML file
        nested_subdir = subdir / "deeper"
        nested_subdir.mkdir()
        yaml_in_nested = nested_subdir / "deep_workflow.yaml"
        yaml_in_nested.write_text("name: deep_workflow")

        result = locator.scan(tmp_path)

        # Should only find the file in the immediate directory
        assert len(result) == 1
        assert yaml_in_root in result
        assert yaml_in_subdir not in result
        assert yaml_in_nested not in result

    # T151: WorkflowLocator scan() with hidden files
    def test_scan_with_hidden_yaml_files(self, tmp_path: Path) -> None:
        """Should find hidden YAML files (starting with dot)."""
        locator = WorkflowLocator()

        # Create regular YAML file
        regular_yaml = tmp_path / "workflow.yaml"
        regular_yaml.write_text("name: regular")

        # Create hidden YAML file
        hidden_yaml = tmp_path / ".hidden_workflow.yaml"
        hidden_yaml.write_text("name: hidden")

        result = locator.scan(tmp_path)

        # Should find both files
        assert len(result) == 2
        assert regular_yaml in result
        assert hidden_yaml in result

    # T152: WorkflowLocator scan() preserves filesystem order
    def test_scan_preserves_order(self, tmp_path: Path) -> None:
        """Should return files in a deterministic order."""
        locator = WorkflowLocator()

        # Create multiple YAML files
        files = [
            tmp_path / "a_workflow.yaml",
            tmp_path / "b_workflow.yaml",
            tmp_path / "c_workflow.yaml",
        ]
        for f in files:
            f.write_text(f"name: {f.stem}")

        result = locator.scan(tmp_path)

        # Should find all files
        assert len(result) == 3
        # Order should be consistent (though not necessarily alphabetical)
        # Multiple scans should return the same order
        result2 = locator.scan(tmp_path)
        assert result == result2
