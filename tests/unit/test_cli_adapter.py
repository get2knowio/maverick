"""Unit tests for CLI adapter module.

Tests conversion of CLI models to workflow OrchestrationInput.
"""

import tempfile
from pathlib import Path

import pytest

from src.cli._adapter import adapt_to_orchestration_input, build_cli_descriptor
from src.cli._models import CLITaskDescriptor
from src.models.orchestration import OrchestrationInput


def test_adapt_to_orchestration_input_basic():
    """Test basic adapter conversion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        cli_desc = CLITaskDescriptor(
            task_id="001-feature",
            task_file=str(task_file),
            spec_root=str(spec_dir),
            branch_name="001-feature",
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=False,
        )

        result = adapt_to_orchestration_input(
            cli_descriptors=[cli_desc],
            repo_root=str(repo_root),
            return_to_branch="main",
            interactive_mode=False,
            retry_limit=3,
        )

        assert isinstance(result, OrchestrationInput)
        assert result.task_descriptors is not None
        assert len(result.task_descriptors) == 1
        assert result.task_descriptors[0].task_id == "001-feature"
        assert result.task_descriptors[0].spec_path == str(task_file)
        assert result.task_descriptors[0].explicit_branch == "001-feature"
        assert result.interactive_mode is False
        assert result.retry_limit == 3
        assert result.repo_path == str(repo_root)


def test_adapt_to_orchestration_input_multiple_descriptors():
    """Test adapter with multiple task descriptors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"

        # Create two tasks
        spec1_dir = specs_dir / "001-feature-a"
        spec1_dir.mkdir(parents=True)
        task1_file = spec1_dir / "tasks.md"
        task1_file.write_text("# Tasks A")

        spec2_dir = specs_dir / "002-feature-b"
        spec2_dir.mkdir(parents=True)
        task2_file = spec2_dir / "tasks.md"
        task2_file.write_text("# Tasks B")

        cli_desc1 = CLITaskDescriptor(
            task_id="001-feature-a",
            task_file=str(task1_file),
            spec_root=str(spec1_dir),
            branch_name="001-feature-a",
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=False,
        )

        cli_desc2 = CLITaskDescriptor(
            task_id="002-feature-b",
            task_file=str(task2_file),
            spec_root=str(spec2_dir),
            branch_name="002-feature-b",
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=False,
        )

        result = adapt_to_orchestration_input(
            cli_descriptors=[cli_desc1, cli_desc2],
            repo_root=str(repo_root),
            return_to_branch="main",
            interactive_mode=False,
            retry_limit=3,
        )

        assert result.task_descriptors is not None
        assert len(result.task_descriptors) == 2
        assert result.task_descriptors[0].task_id == "001-feature-a"
        assert result.task_descriptors[1].task_id == "002-feature-b"


def test_adapt_to_orchestration_input_derives_branch_name():
    """Test adapter derives branch name when not provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        cli_desc = CLITaskDescriptor(
            task_id="001-feature-task",
            task_file=str(task_file),
            spec_root=str(spec_dir),
            branch_name=None,  # Will be derived
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=False,
        )

        result = adapt_to_orchestration_input(
            cli_descriptors=[cli_desc],
            repo_root=str(repo_root),
            return_to_branch="main",
        )

        # Branch should be derived from task_id
        assert result.task_descriptors is not None
        assert result.task_descriptors[0].explicit_branch == "001-feature-task"


def test_adapt_to_orchestration_input_with_optional_params():
    """Test adapter with optional model and agent profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        cli_desc = CLITaskDescriptor(
            task_id="001-feature",
            task_file=str(task_file),
            spec_root=str(spec_dir),
            branch_name="001-feature",
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=True,
        )

        result = adapt_to_orchestration_input(
            cli_descriptors=[cli_desc],
            repo_root=str(repo_root),
            return_to_branch="main",
            interactive_mode=True,
            default_model="gpt-4",
            default_agent_profile="senior-dev",
            retry_limit=5,
        )

        assert result.interactive_mode is True
        assert result.default_model == "gpt-4"
        assert result.default_agent_profile == "senior-dev"
        assert result.retry_limit == 5


def test_adapt_to_orchestration_input_empty_descriptors():
    """Test adapter raises error for empty descriptor list."""
    with pytest.raises(
        ValueError, match="cli_descriptors must contain at least one descriptor"
    ):
        adapt_to_orchestration_input(
            cli_descriptors=[],
            repo_root="/tmp/repo",
            return_to_branch="main",
        )


def test_adapt_to_orchestration_input_empty_repo_root():
    """Test adapter raises error for empty repo root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        cli_desc = CLITaskDescriptor(
            task_id="001-feature",
            task_file=str(task_file),
            spec_root=str(spec_dir),
            branch_name="001-feature",
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=False,
        )

        with pytest.raises(ValueError, match="repo_root must be non-empty"):
            adapt_to_orchestration_input(
                cli_descriptors=[cli_desc],
                repo_root="",
                return_to_branch="main",
            )


def test_adapt_to_orchestration_input_empty_return_branch():
    """Test adapter raises error for empty return branch."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        cli_desc = CLITaskDescriptor(
            task_id="001-feature",
            task_file=str(task_file),
            spec_root=str(spec_dir),
            branch_name="001-feature",
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=False,
        )

        with pytest.raises(ValueError, match="return_to_branch must be non-empty"):
            adapt_to_orchestration_input(
                cli_descriptors=[cli_desc],
                repo_root=str(repo_root),
                return_to_branch="",
            )


def test_adapt_to_orchestration_input_invalid_retry_limit():
    """Test adapter raises error for invalid retry limit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        cli_desc = CLITaskDescriptor(
            task_id="001-feature",
            task_file=str(task_file),
            spec_root=str(spec_dir),
            branch_name="001-feature",
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=False,
        )

        with pytest.raises(ValueError, match="retry_limit must be between 1 and 10"):
            adapt_to_orchestration_input(
                cli_descriptors=[cli_desc],
                repo_root=str(repo_root),
                return_to_branch="main",
                retry_limit=0,
            )

        with pytest.raises(ValueError, match="retry_limit must be between 1 and 10"):
            adapt_to_orchestration_input(
                cli_descriptors=[cli_desc],
                repo_root=str(repo_root),
                return_to_branch="main",
                retry_limit=11,
            )


def test_build_cli_descriptor_basic():
    """Test building CLI descriptor from paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        result = build_cli_descriptor(
            task_file=task_file,
            spec_root=spec_dir,
            repo_root=repo_root,
            return_to_branch="main",
            interactive=False,
        )

        assert isinstance(result, CLITaskDescriptor)
        assert result.task_id == "001-feature-tasks"  # Derived from spec_dir.name + file
        assert result.task_file == str(task_file.resolve())
        assert result.spec_root == str(spec_dir.resolve())
        assert result.repo_root == str(repo_root.resolve())
        assert result.return_to_branch == "main"
        assert result.interactive is False
        assert result.branch_name is None
        assert result.model_prefs is None


def test_build_cli_descriptor_with_branch_hint():
    """Test building CLI descriptor with explicit branch name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        result = build_cli_descriptor(
            task_file=task_file,
            spec_root=spec_dir,
            repo_root=repo_root,
            return_to_branch="main",
            interactive=True,
            branch_name_hint="custom-branch",
        )

        assert result.branch_name == "custom-branch"
        assert result.interactive is True


def test_build_cli_descriptor_with_model_prefs():
    """Test building CLI descriptor with model preferences."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        model_prefs = {
            "provider": "openai",
            "model": "gpt-4",
            "max_tokens": 2000,
        }

        result = build_cli_descriptor(
            task_file=task_file,
            spec_root=spec_dir,
            repo_root=repo_root,
            return_to_branch="main",
            model_prefs=model_prefs,
        )

        assert result.model_prefs == model_prefs


def test_build_cli_descriptor_task_file_not_exists():
    """Test building CLI descriptor raises error when task file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        # Don't create file

        with pytest.raises(ValueError, match="Task file does not exist"):
            build_cli_descriptor(
                task_file=task_file,
                spec_root=spec_dir,
                repo_root=repo_root,
                return_to_branch="main",
            )


def test_build_cli_descriptor_spec_root_not_exists():
    """Test building CLI descriptor raises error when spec root doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        # Create a separate temp directory for task file
        task_dir = repo_root / "temp"
        task_dir.mkdir()
        task_file = task_dir / "tasks.md"
        task_file.write_text("# Tasks")

        # Reference a non-existent spec_dir
        spec_dir = repo_root / "specs" / "001-feature"

        with pytest.raises(ValueError, match="Spec root does not exist"):
            build_cli_descriptor(
                task_file=task_file,
                spec_root=spec_dir,
                repo_root=repo_root,
                return_to_branch="main",
            )


def test_build_cli_descriptor_empty_return_branch():
    """Test building CLI descriptor raises error for empty return branch."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        with pytest.raises(ValueError, match="return_to_branch must be non-empty"):
            build_cli_descriptor(
                task_file=task_file,
                spec_root=spec_dir,
                repo_root=repo_root,
                return_to_branch="",
            )
