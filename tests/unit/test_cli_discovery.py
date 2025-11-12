"""Unit tests for CLI discovery module.

Tests task discovery ordering, filtering, and error handling.
"""

import tempfile
from pathlib import Path

import pytest

from src.cli._discovery import discover_tasks
from src.cli._models import DiscoveredTask


def test_discover_tasks_empty_specs_dir():
    """Test discovery with no task files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir()

        result = discover_tasks(repo_root)

        assert result == []


def test_discover_tasks_no_specs_dir():
    """Test discovery when specs/ directory doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)

        result = discover_tasks(repo_root)

        assert result == []


def test_discover_tasks_single_task():
    """Test discovery with a single task file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir()

        spec_001 = specs_dir / "001-feature-a"
        spec_001.mkdir()
        tasks_file = spec_001 / "tasks.md"
        tasks_file.write_text("# Tasks")

        result = discover_tasks(repo_root)

        assert len(result) == 1
        assert result[0].directory_name == "001-feature-a"
        assert result[0].numeric_prefix == 1
        assert result[0].file_path == str(tasks_file.resolve())
        assert result[0].spec_dir == str(spec_001.resolve())


def test_discover_tasks_ordering_by_numeric_prefix():
    """Test discovery orders by numeric prefix first."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir()

        # Create tasks with different numeric prefixes
        spec_003 = specs_dir / "003-feature-c"
        spec_003.mkdir()
        (spec_003 / "tasks.md").write_text("# Tasks C")

        spec_001 = specs_dir / "001-feature-a"
        spec_001.mkdir()
        (spec_001 / "tasks.md").write_text("# Tasks A")

        spec_002 = specs_dir / "002-feature-b"
        spec_002.mkdir()
        (spec_002 / "tasks.md").write_text("# Tasks B")

        result = discover_tasks(repo_root)

        assert len(result) == 3
        assert result[0].directory_name == "001-feature-a"
        assert result[1].directory_name == "002-feature-b"
        assert result[2].directory_name == "003-feature-c"


def test_discover_tasks_ordering_by_name_when_no_prefix():
    """Test discovery orders by name when no numeric prefix."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir()

        # Create tasks without numeric prefixes
        spec_c = specs_dir / "feature-c"
        spec_c.mkdir()
        (spec_c / "tasks.md").write_text("# Tasks C")

        spec_a = specs_dir / "feature-a"
        spec_a.mkdir()
        (spec_a / "tasks.md").write_text("# Tasks A")

        spec_b = specs_dir / "feature-b"
        spec_b.mkdir()
        (spec_b / "tasks.md").write_text("# Tasks B")

        result = discover_tasks(repo_root)

        assert len(result) == 3
        # Should be ordered lexicographically when prefix is 0
        assert result[0].directory_name == "feature-a"
        assert result[1].directory_name == "feature-b"
        assert result[2].directory_name == "feature-c"
        assert all(r.numeric_prefix == 0 for r in result)


def test_discover_tasks_mixed_prefix_and_no_prefix():
    """Test discovery prioritizes prefixed directories before non-prefixed ones."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir()

        # Prefixed
        spec_002 = specs_dir / "002-feature-b"
        spec_002.mkdir()
        (spec_002 / "tasks.md").write_text("# Tasks B")

        # Non-prefixed (will have prefix 0)
        spec_z = specs_dir / "feature-z"
        spec_z.mkdir()
        (spec_z / "tasks.md").write_text("# Tasks Z")

        # Prefixed
        spec_001 = specs_dir / "001-feature-a"
        spec_001.mkdir()
        (spec_001 / "tasks.md").write_text("# Tasks A")

        result = discover_tasks(repo_root)

        assert len(result) == 3
        # Prefixed specs should come first ordered by numeric prefix
        assert result[0].directory_name == "001-feature-a"
        assert result[0].numeric_prefix == 1
        assert result[1].directory_name == "002-feature-b"
        assert result[1].numeric_prefix == 2
        # Non-prefixed follow, ordered lexicographically
        assert result[2].directory_name == "feature-z"
        assert result[2].numeric_prefix == 0


def test_discover_tasks_ignores_specs_completed():
    """Test discovery ignores specs-completed/ directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir()

        # Active spec
        spec_001 = specs_dir / "001-feature-a"
        spec_001.mkdir()
        (spec_001 / "tasks.md").write_text("# Tasks A")

        # Completed spec (should be ignored)
        specs_completed = repo_root / "specs-completed"
        specs_completed.mkdir()
        spec_002_completed = specs_completed / "002-feature-b"
        spec_002_completed.mkdir()
        (spec_002_completed / "tasks.md").write_text("# Tasks B")

        result = discover_tasks(repo_root)

        assert len(result) == 1
        assert result[0].directory_name == "001-feature-a"


def test_discover_tasks_skips_directories_without_tasks_md():
    """Test discovery skips directories without tasks.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir()

        # Has tasks.md
        spec_001 = specs_dir / "001-feature-a"
        spec_001.mkdir()
        (spec_001 / "tasks.md").write_text("# Tasks A")

        # No tasks.md
        spec_002 = specs_dir / "002-feature-b"
        spec_002.mkdir()

        result = discover_tasks(repo_root)

        assert len(result) == 1
        assert result[0].directory_name == "001-feature-a"


def test_discover_tasks_skips_files_in_specs_root():
    """Test discovery skips files directly in specs/ directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir()

        # File in specs root (should be ignored)
        (specs_dir / "README.md").write_text("# README")

        # Valid spec directory
        spec_001 = specs_dir / "001-feature-a"
        spec_001.mkdir()
        (spec_001 / "tasks.md").write_text("# Tasks A")

        result = discover_tasks(repo_root)

        assert len(result) == 1
        assert result[0].directory_name == "001-feature-a"


def test_discover_tasks_single_target_file():
    """Test discovery with specific target task file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir()

        # Create multiple specs
        spec_001 = specs_dir / "001-feature-a"
        spec_001.mkdir()
        tasks_001 = spec_001 / "tasks.md"
        tasks_001.write_text("# Tasks A")

        spec_002 = specs_dir / "002-feature-b"
        spec_002.mkdir()
        tasks_002 = spec_002 / "tasks.md"
        tasks_002.write_text("# Tasks B")

        # Discover only spec_002
        result = discover_tasks(repo_root, target_task_file=tasks_002)

        assert len(result) == 1
        assert result[0].directory_name == "002-feature-b"
        assert result[0].file_path == str(tasks_002.resolve())


def test_discover_tasks_target_file_not_found():
    """Test discovery raises error when target file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir()

        nonexistent_file = specs_dir / "001-feature" / "tasks.md"

        with pytest.raises(ValueError, match="Target task file does not exist"):
            discover_tasks(repo_root, target_task_file=nonexistent_file)


def test_discover_tasks_target_file_outside_repo():
    """Test discovery raises error when target file is outside repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir()

        # Create file outside repo
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            outside_file = Path(f.name)
            outside_file.write_text("# Tasks")

        try:
            with pytest.raises(
                ValueError, match="Target task file must be under repo_root"
            ):
                discover_tasks(repo_root, target_task_file=outside_file)
        finally:
            outside_file.unlink()


def test_discover_tasks_invalid_repo_root():
    """Test discovery raises error for invalid repo root."""
    with pytest.raises(ValueError, match="Repository root does not exist"):
        discover_tasks(Path("/nonexistent/path"))


def test_discover_tasks_repo_root_is_file():
    """Test discovery raises error when repo root is a file."""
    with tempfile.NamedTemporaryFile() as tmpfile:
        with pytest.raises(ValueError, match="Repository root is not a directory"):
            discover_tasks(Path(tmpfile.name))


def test_discovered_task_validation():
    """Test DiscoveredTask model validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "001-feature"
        spec_dir.mkdir()
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        # Valid task
        task = DiscoveredTask(
            file_path=str(task_file),
            spec_dir=str(spec_dir),
            numeric_prefix=1,
            directory_name="001-feature",
        )
        assert task.file_path == str(task_file)

        # Invalid: file doesn't exist
        with pytest.raises(ValueError, match="file_path does not exist"):
            DiscoveredTask(
                file_path="/nonexistent/file",
                spec_dir=str(spec_dir),
                numeric_prefix=1,
                directory_name="001-feature",
            )

        # Invalid: negative prefix
        with pytest.raises(ValueError, match="numeric_prefix must be >= 0"):
            DiscoveredTask(
                file_path=str(task_file),
                spec_dir=str(spec_dir),
                numeric_prefix=-1,
                directory_name="001-feature",
            )

        # Invalid: empty directory name
        with pytest.raises(ValueError, match="directory_name must be non-empty"):
            DiscoveredTask(
                file_path=str(task_file),
                spec_dir=str(spec_dir),
                numeric_prefix=1,
                directory_name="",
            )
