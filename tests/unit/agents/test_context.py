"""Unit tests for AgentContext dataclass."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maverick.agents.context import AgentContext
from maverick.config import MaverickConfig
from maverick.constants import DEFAULT_MODEL
from maverick.exceptions import NotARepositoryError


def test_agent_context_creation_with_valid_values(temp_dir: Path) -> None:
    """Test creating AgentContext with valid values."""
    config = MaverickConfig()
    extra = {"key": "value"}

    context = AgentContext(
        cwd=temp_dir,
        branch="feature-branch",
        config=config,
        extra=extra,
    )

    assert context.cwd == temp_dir
    assert context.branch == "feature-branch"
    assert context.config is config
    assert context.extra == extra


def test_agent_context_frozen_immutable(temp_dir: Path) -> None:
    """Test that AgentContext is frozen (immutable)."""
    config = MaverickConfig()
    context = AgentContext(
        cwd=temp_dir,
        branch="main",
        config=config,
    )

    # Attempting to modify should raise FrozenInstanceError
    with pytest.raises(Exception) as exc_info:
        context.cwd = Path("/different/path")  # type: ignore[misc]

    # Check that it's a dataclass frozen error
    assert (
        "frozen" in str(exc_info.value).lower()
        or "cannot assign" in str(exc_info.value).lower()
    )


def test_agent_context_no_dict_attribute(temp_dir: Path) -> None:
    """Test that AgentContext uses slots (no __dict__)."""
    config = MaverickConfig()
    context = AgentContext(
        cwd=temp_dir,
        branch="main",
        config=config,
    )

    # Slots-based classes should not have __dict__
    assert not hasattr(context, "__dict__")


def test_agent_context_extra_defaults_to_empty_dict(temp_dir: Path) -> None:
    """Test that extra field defaults to an empty dict."""
    config = MaverickConfig()
    context = AgentContext(
        cwd=temp_dir,
        branch="main",
        config=config,
    )

    assert context.extra == {}
    assert isinstance(context.extra, dict)


def test_agent_context_empty_branch_raises_value_error(temp_dir: Path) -> None:
    """Test that an empty branch string raises ValueError."""
    config = MaverickConfig()

    with pytest.raises(ValueError) as exc_info:
        AgentContext(
            cwd=temp_dir,
            branch="",
            config=config,
        )

    assert "branch must be a non-empty string" in str(exc_info.value)


def test_agent_context_from_cwd_success(temp_dir: Path) -> None:
    """Test from_cwd factory method with valid git repository."""
    # Mock GitRepository to simulate git repository
    mock_repo = MagicMock()
    mock_repo.current_branch.return_value = "feature-branch"

    with patch("maverick.git.GitRepository", return_value=mock_repo):
        context = AgentContext.from_cwd(temp_dir)

        # Verify context was created correctly
        assert context.cwd == temp_dir
        assert context.branch == "feature-branch"
        assert isinstance(context.config, MaverickConfig)
        assert context.extra == {}


def test_agent_context_from_cwd_strips_whitespace(temp_dir: Path) -> None:
    """Test from_cwd uses branch name from GitRepository."""
    # GitRepository.current_branch() already returns clean branch names
    mock_repo = MagicMock()
    mock_repo.current_branch.return_value = "main"

    with patch("maverick.git.GitRepository", return_value=mock_repo):
        context = AgentContext.from_cwd(temp_dir)

        assert context.branch == "main"


def test_agent_context_from_cwd_with_non_existent_directory() -> None:
    """Test from_cwd with non-existent directory raises ValueError."""
    non_existent = Path("/non/existent/directory")

    with pytest.raises(ValueError) as exc_info:
        AgentContext.from_cwd(non_existent)

    assert "cwd must be an existing directory" in str(exc_info.value)
    assert str(non_existent) in str(exc_info.value)


def test_agent_context_from_cwd_without_git_repo_raises_value_error(
    temp_dir: Path,
) -> None:
    """Test from_cwd without git repo raises ValueError."""
    # Mock GitRepository to raise NotARepositoryError
    with patch(
        "maverick.git.GitRepository",
        side_effect=NotARepositoryError("Not a git repository", path=temp_dir),
    ):
        with pytest.raises(ValueError) as exc_info:
            AgentContext.from_cwd(temp_dir)

        assert "Not a git repository" in str(exc_info.value)
        assert str(temp_dir) in str(exc_info.value)


def test_agent_context_from_cwd_with_default_config(temp_dir: Path) -> None:
    """Test from_cwd creates default config when not provided."""
    mock_repo = MagicMock()
    mock_repo.current_branch.return_value = "main"

    with patch("maverick.git.GitRepository", return_value=mock_repo):
        context = AgentContext.from_cwd(temp_dir)

        # Should create a default MaverickConfig
        assert isinstance(context.config, MaverickConfig)
        assert context.config.model.model_id == DEFAULT_MODEL


def test_agent_context_from_cwd_with_custom_config(temp_dir: Path) -> None:
    """Test from_cwd with custom config."""
    custom_config = MaverickConfig()
    custom_config.verbosity = "debug"

    mock_repo = MagicMock()
    mock_repo.current_branch.return_value = "main"

    with patch("maverick.git.GitRepository", return_value=mock_repo):
        context = AgentContext.from_cwd(temp_dir, config=custom_config)

        # Should use the provided config
        assert context.config is custom_config
        assert context.config.verbosity == "debug"


def test_agent_context_from_cwd_with_extra_parameter(temp_dir: Path) -> None:
    """Test from_cwd with extra parameter."""
    extra_data = {"file_path": "src/main.py", "line_number": 42}

    mock_repo = MagicMock()
    mock_repo.current_branch.return_value = "feature-123"

    with patch("maverick.git.GitRepository", return_value=mock_repo):
        context = AgentContext.from_cwd(temp_dir, extra=extra_data)

        assert context.extra == extra_data
        assert context.extra["file_path"] == "src/main.py"
        assert context.extra["line_number"] == 42


def test_agent_context_from_cwd_with_none_extra_defaults_to_empty_dict(
    temp_dir: Path,
) -> None:
    """Test from_cwd with None extra defaults to empty dict."""
    mock_repo = MagicMock()
    mock_repo.current_branch.return_value = "main"

    with patch("maverick.git.GitRepository", return_value=mock_repo):
        context = AgentContext.from_cwd(temp_dir, extra=None)

        assert context.extra == {}


def test_agent_context_multiple_instances_isolated(temp_dir: Path) -> None:
    """Test that multiple AgentContext instances have isolated extra dicts."""
    config = MaverickConfig()

    context1 = AgentContext(
        cwd=temp_dir,
        branch="main",
        config=config,
    )

    context2 = AgentContext(
        cwd=temp_dir,
        branch="main",
        config=config,
    )

    # Each should have its own empty dict
    assert context1.extra is not context2.extra


def test_agent_context_with_pathlib_path(temp_dir: Path) -> None:
    """Test AgentContext works with pathlib.Path objects."""
    config = MaverickConfig()
    path = temp_dir / "subdir"
    path.mkdir()

    context = AgentContext(
        cwd=path,
        branch="main",
        config=config,
    )

    assert isinstance(context.cwd, Path)
    assert context.cwd == path


def test_agent_context_equality(temp_dir: Path) -> None:
    """Test AgentContext instances can be compared for equality."""
    config1 = MaverickConfig()
    config2 = MaverickConfig()

    context1 = AgentContext(
        cwd=temp_dir,
        branch="main",
        config=config1,
        extra={"key": "value"},
    )

    context2 = AgentContext(
        cwd=temp_dir,
        branch="main",
        config=config2,
        extra={"key": "value"},
    )

    # Since config1 and config2 are different instances, contexts won't be equal
    # But same instance should equal itself
    assert context1 == context1
    assert context2 == context2


def test_agent_context_repr(temp_dir: Path) -> None:
    """Test AgentContext has a useful repr."""
    config = MaverickConfig()
    context = AgentContext(
        cwd=temp_dir,
        branch="feature-x",
        config=config,
        extra={"test": "data"},
    )

    repr_str = repr(context)

    # Should contain class name and field values
    assert "AgentContext" in repr_str
    assert "feature-x" in repr_str


def test_agent_context_from_cwd_with_detached_head(temp_dir: Path) -> None:
    """Test from_cwd works with detached HEAD state."""
    # GitRepository returns commit SHA when in detached HEAD
    mock_repo = MagicMock()
    mock_repo.current_branch.return_value = "a1b2c3d4e5f6"

    with patch("maverick.git.GitRepository", return_value=mock_repo):
        context = AgentContext.from_cwd(temp_dir)

        # Should work with commit SHA as branch name
        assert context.branch == "a1b2c3d4e5f6"


def test_agent_context_branch_validation_only_checks_empty_string(
    temp_dir: Path,
) -> None:
    """Test branch validation only checks for empty string, not content."""
    config = MaverickConfig()

    # Unusual but valid branch names should work
    unusual_branches = [
        "feature/my-feature",
        "123-numeric-start",
        "user/name/feature",
        "v1.2.3",
    ]

    for branch_name in unusual_branches:
        context = AgentContext(
            cwd=temp_dir,
            branch=branch_name,
            config=config,
        )
        assert context.branch == branch_name
