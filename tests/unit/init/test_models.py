"""Tests for maverick init models.

This module tests the enums, constants, dataclasses, and Pydantic models
defined in src/maverick/init/models.py.
"""

from __future__ import annotations

import pytest
import yaml

from maverick.constants import CLAUDE_HAIKU_LATEST
from maverick.init.models import (
    MARKER_FILE_MAP,
    MODEL_NAME_MAP,
    PYTHON_DEFAULTS,
    VALIDATION_DEFAULTS,
    DetectionConfidence,
    GitRemoteInfo,
    InitConfig,
    InitGitHubConfig,
    InitModelConfig,
    InitPreflightResult,
    InitResult,
    InitValidationConfig,
    PreflightStatus,
    PrerequisiteCheck,
    ProjectDetectionResult,
    ProjectMarker,
    ProjectType,
    ValidationCommands,
    resolve_model_id,
)

# =============================================================================
# ProjectType Enum Tests
# =============================================================================


class TestProjectType:
    """Test suite for ProjectType enum."""

    def test_all_enum_values_exist(self) -> None:
        """Test that all expected enum values are defined."""
        assert hasattr(ProjectType, "PYTHON")
        assert hasattr(ProjectType, "NODEJS")
        assert hasattr(ProjectType, "GO")
        assert hasattr(ProjectType, "RUST")
        assert hasattr(ProjectType, "ANSIBLE_COLLECTION")
        assert hasattr(ProjectType, "ANSIBLE_PLAYBOOK")
        assert hasattr(ProjectType, "UNKNOWN")

    def test_enum_values_are_strings(self) -> None:
        """Test that enum values are strings with expected values."""
        assert ProjectType.PYTHON == "python"
        assert ProjectType.NODEJS == "nodejs"
        assert ProjectType.GO == "go"
        assert ProjectType.RUST == "rust"
        assert ProjectType.ANSIBLE_COLLECTION == "ansible_collection"
        assert ProjectType.ANSIBLE_PLAYBOOK == "ansible_playbook"
        assert ProjectType.UNKNOWN == "unknown"

    def test_enum_values_match_expected_strings(self) -> None:
        """Test that .value attribute returns expected strings."""
        assert ProjectType.PYTHON.value == "python"
        assert ProjectType.NODEJS.value == "nodejs"
        assert ProjectType.GO.value == "go"
        assert ProjectType.RUST.value == "rust"
        assert ProjectType.ANSIBLE_COLLECTION.value == "ansible_collection"
        assert ProjectType.ANSIBLE_PLAYBOOK.value == "ansible_playbook"
        assert ProjectType.UNKNOWN.value == "unknown"

    def test_enum_is_str_subclass(self) -> None:
        """Test that ProjectType inherits from str for serialization."""
        assert isinstance(ProjectType.PYTHON, str)
        assert isinstance(ProjectType.NODEJS, str)

    def test_enum_iteration(self) -> None:
        """Test that all enum values can be iterated."""
        all_types = list(ProjectType)
        assert len(all_types) == 7
        assert ProjectType.PYTHON in all_types
        assert ProjectType.NODEJS in all_types
        assert ProjectType.GO in all_types
        assert ProjectType.RUST in all_types
        assert ProjectType.ANSIBLE_COLLECTION in all_types
        assert ProjectType.ANSIBLE_PLAYBOOK in all_types
        assert ProjectType.UNKNOWN in all_types

    def test_from_string_lowercase(self) -> None:
        """Test from_string with lowercase input."""
        assert ProjectType.from_string("python") == ProjectType.PYTHON
        assert ProjectType.from_string("nodejs") == ProjectType.NODEJS
        assert ProjectType.from_string("go") == ProjectType.GO
        assert ProjectType.from_string("rust") == ProjectType.RUST
        assert ProjectType.from_string("unknown") == ProjectType.UNKNOWN

    def test_from_string_uppercase(self) -> None:
        """Test from_string with uppercase input (case-insensitive)."""
        assert ProjectType.from_string("PYTHON") == ProjectType.PYTHON
        assert ProjectType.from_string("NODEJS") == ProjectType.NODEJS
        assert ProjectType.from_string("GO") == ProjectType.GO
        assert ProjectType.from_string("RUST") == ProjectType.RUST

    def test_from_string_mixed_case(self) -> None:
        """Test from_string with mixed case input."""
        assert ProjectType.from_string("Python") == ProjectType.PYTHON
        assert ProjectType.from_string("NodeJs") == ProjectType.NODEJS
        assert ProjectType.from_string("Go") == ProjectType.GO
        assert ProjectType.from_string("Rust") == ProjectType.RUST

    def test_from_string_with_hyphens(self) -> None:
        """Test from_string normalizes hyphens to underscores."""
        result = ProjectType.from_string("ansible-collection")
        assert result == ProjectType.ANSIBLE_COLLECTION
        result = ProjectType.from_string("ansible-playbook")
        assert result == ProjectType.ANSIBLE_PLAYBOOK
        result = ProjectType.from_string("ANSIBLE-COLLECTION")
        assert result == ProjectType.ANSIBLE_COLLECTION

    def test_from_string_with_spaces(self) -> None:
        """Test from_string normalizes spaces to underscores."""
        result = ProjectType.from_string("ansible collection")
        assert result == ProjectType.ANSIBLE_COLLECTION
        result = ProjectType.from_string("ansible playbook")
        assert result == ProjectType.ANSIBLE_PLAYBOOK

    def test_from_string_invalid_returns_unknown(self) -> None:
        """Test from_string returns UNKNOWN for invalid inputs."""
        assert ProjectType.from_string("invalid") == ProjectType.UNKNOWN
        assert ProjectType.from_string("java") == ProjectType.UNKNOWN
        assert ProjectType.from_string("csharp") == ProjectType.UNKNOWN
        assert ProjectType.from_string("") == ProjectType.UNKNOWN
        assert ProjectType.from_string("   ") == ProjectType.UNKNOWN

    def test_enum_is_hashable(self) -> None:
        """Test that enum values can be used as dict keys."""
        mapping = {
            ProjectType.PYTHON: "Python project",
            ProjectType.NODEJS: "Node.js project",
            ProjectType.GO: "Go project",
        }
        assert mapping[ProjectType.PYTHON] == "Python project"
        assert mapping[ProjectType.NODEJS] == "Node.js project"


# =============================================================================
# DetectionConfidence Enum Tests
# =============================================================================


class TestDetectionConfidence:
    """Test suite for DetectionConfidence enum."""

    def test_all_enum_values_exist(self) -> None:
        """Test that all expected enum values are defined."""
        assert hasattr(DetectionConfidence, "HIGH")
        assert hasattr(DetectionConfidence, "MEDIUM")
        assert hasattr(DetectionConfidence, "LOW")

    def test_enum_values_are_strings(self) -> None:
        """Test that enum values are strings with expected values."""
        assert DetectionConfidence.HIGH == "high"
        assert DetectionConfidence.MEDIUM == "medium"
        assert DetectionConfidence.LOW == "low"

    def test_enum_values_match_expected_strings(self) -> None:
        """Test that .value attribute returns expected strings."""
        assert DetectionConfidence.HIGH.value == "high"
        assert DetectionConfidence.MEDIUM.value == "medium"
        assert DetectionConfidence.LOW.value == "low"

    def test_enum_is_str_subclass(self) -> None:
        """Test that DetectionConfidence inherits from str for serialization."""
        assert isinstance(DetectionConfidence.HIGH, str)
        assert isinstance(DetectionConfidence.MEDIUM, str)
        assert isinstance(DetectionConfidence.LOW, str)

    def test_enum_iteration(self) -> None:
        """Test that all enum values can be iterated."""
        all_levels = list(DetectionConfidence)
        assert len(all_levels) == 3
        assert DetectionConfidence.HIGH in all_levels
        assert DetectionConfidence.MEDIUM in all_levels
        assert DetectionConfidence.LOW in all_levels

    def test_enum_is_hashable(self) -> None:
        """Test that enum values can be used as dict keys."""
        mapping = {
            DetectionConfidence.HIGH: "Certain",
            DetectionConfidence.MEDIUM: "Likely",
            DetectionConfidence.LOW: "Best guess",
        }
        assert mapping[DetectionConfidence.HIGH] == "Certain"


# =============================================================================
# PreflightStatus Enum Tests
# =============================================================================


class TestPreflightStatus:
    """Test suite for PreflightStatus enum."""

    def test_all_enum_values_exist(self) -> None:
        """Test that all expected enum values are defined."""
        assert hasattr(PreflightStatus, "PASS")
        assert hasattr(PreflightStatus, "FAIL")
        assert hasattr(PreflightStatus, "SKIP")

    def test_enum_values_are_strings(self) -> None:
        """Test that enum values are strings with expected values."""
        assert PreflightStatus.PASS == "pass"
        assert PreflightStatus.FAIL == "fail"
        assert PreflightStatus.SKIP == "skip"

    def test_enum_values_match_expected_strings(self) -> None:
        """Test that .value attribute returns expected strings."""
        assert PreflightStatus.PASS.value == "pass"
        assert PreflightStatus.FAIL.value == "fail"
        assert PreflightStatus.SKIP.value == "skip"

    def test_enum_is_str_subclass(self) -> None:
        """Test that PreflightStatus inherits from str for serialization."""
        assert isinstance(PreflightStatus.PASS, str)
        assert isinstance(PreflightStatus.FAIL, str)
        assert isinstance(PreflightStatus.SKIP, str)

    def test_enum_iteration(self) -> None:
        """Test that all enum values can be iterated."""
        all_statuses = list(PreflightStatus)
        assert len(all_statuses) == 3
        assert PreflightStatus.PASS in all_statuses
        assert PreflightStatus.FAIL in all_statuses
        assert PreflightStatus.SKIP in all_statuses


# =============================================================================
# Constants Tests
# =============================================================================


class TestMarkerFileMap:
    """Test suite for MARKER_FILE_MAP constant."""

    def test_marker_file_map_is_dict(self) -> None:
        """Test that MARKER_FILE_MAP is a dictionary."""
        assert isinstance(MARKER_FILE_MAP, dict)

    def test_marker_file_map_has_expected_entries(self) -> None:
        """Test that MARKER_FILE_MAP contains all expected marker files."""
        # Python markers
        assert "pyproject.toml" in MARKER_FILE_MAP
        assert "setup.py" in MARKER_FILE_MAP
        assert "setup.cfg" in MARKER_FILE_MAP
        assert "requirements.txt" in MARKER_FILE_MAP
        assert "Pipfile" in MARKER_FILE_MAP

        # Node.js markers
        assert "package.json" in MARKER_FILE_MAP

        # Go markers
        assert "go.mod" in MARKER_FILE_MAP

        # Rust markers
        assert "Cargo.toml" in MARKER_FILE_MAP

        # Ansible markers
        assert "galaxy.yml" in MARKER_FILE_MAP
        assert "requirements.yml" in MARKER_FILE_MAP
        assert "ansible.cfg" in MARKER_FILE_MAP

    def test_marker_file_map_values_are_tuples(self) -> None:
        """Test that MARKER_FILE_MAP values are (ProjectType, priority) tuples."""
        for filename, value in MARKER_FILE_MAP.items():
            assert isinstance(value, tuple), f"Value for {filename} is not a tuple"
            assert len(value) == 2, f"Value for {filename} has wrong element count"
            project_type, priority = value
            assert isinstance(project_type, ProjectType), (
                f"First element for {filename} is not ProjectType"
            )
            assert isinstance(priority, int), (
                f"Second element for {filename} is not int"
            )
            assert priority >= 1, f"Priority for {filename} should be >= 1"

    def test_marker_file_map_project_type_associations(self) -> None:
        """Test that marker files are associated with correct project types."""
        assert MARKER_FILE_MAP["pyproject.toml"][0] == ProjectType.PYTHON
        assert MARKER_FILE_MAP["package.json"][0] == ProjectType.NODEJS
        assert MARKER_FILE_MAP["go.mod"][0] == ProjectType.GO
        assert MARKER_FILE_MAP["Cargo.toml"][0] == ProjectType.RUST
        assert MARKER_FILE_MAP["galaxy.yml"][0] == ProjectType.ANSIBLE_COLLECTION
        assert MARKER_FILE_MAP["ansible.cfg"][0] == ProjectType.ANSIBLE_PLAYBOOK

    def test_marker_file_map_priority_ordering(self) -> None:
        """Test that Python markers have correct priority ordering."""
        # pyproject.toml should have highest priority (1) for Python
        assert MARKER_FILE_MAP["pyproject.toml"][1] == 1
        assert MARKER_FILE_MAP["setup.py"][1] == 2
        assert MARKER_FILE_MAP["setup.cfg"][1] == 3
        assert MARKER_FILE_MAP["requirements.txt"][1] == 4
        assert MARKER_FILE_MAP["Pipfile"][1] == 5


class TestValidationDefaults:
    """Test suite for VALIDATION_DEFAULTS constant."""

    def test_validation_defaults_is_dict(self) -> None:
        """Test that VALIDATION_DEFAULTS is a dictionary."""
        assert isinstance(VALIDATION_DEFAULTS, dict)

    def test_validation_defaults_has_all_project_types(self) -> None:
        """Test that VALIDATION_DEFAULTS has entries for all project types."""
        assert ProjectType.PYTHON in VALIDATION_DEFAULTS
        assert ProjectType.NODEJS in VALIDATION_DEFAULTS
        assert ProjectType.GO in VALIDATION_DEFAULTS
        assert ProjectType.RUST in VALIDATION_DEFAULTS
        assert ProjectType.ANSIBLE_COLLECTION in VALIDATION_DEFAULTS
        assert ProjectType.ANSIBLE_PLAYBOOK in VALIDATION_DEFAULTS
        assert ProjectType.UNKNOWN in VALIDATION_DEFAULTS

    def test_validation_defaults_values_are_validation_commands(self) -> None:
        """Test that VALIDATION_DEFAULTS values are ValidationCommands instances."""
        for project_type, commands in VALIDATION_DEFAULTS.items():
            assert isinstance(commands, ValidationCommands), (
                f"Value for {project_type} is not ValidationCommands"
            )

    def test_python_defaults(self) -> None:
        """Test Python default validation commands."""
        python = VALIDATION_DEFAULTS[ProjectType.PYTHON]
        assert python.format_cmd == ("ruff", "format", ".")
        assert python.lint_cmd == ("ruff", "check", "--fix", ".")
        assert python.typecheck_cmd == ("mypy", ".")
        assert python.test_cmd == ("pytest", "-x", "--tb=short")

    def test_nodejs_defaults(self) -> None:
        """Test Node.js default validation commands."""
        nodejs = VALIDATION_DEFAULTS[ProjectType.NODEJS]
        assert nodejs.format_cmd == ("prettier", "--write", ".")
        assert nodejs.lint_cmd == ("eslint", "--fix", ".")
        assert nodejs.typecheck_cmd == ("tsc", "--noEmit")
        assert nodejs.test_cmd == ("npm", "test")

    def test_go_defaults(self) -> None:
        """Test Go default validation commands."""
        go = VALIDATION_DEFAULTS[ProjectType.GO]
        assert go.format_cmd == ("gofmt", "-w", ".")
        assert go.lint_cmd == ("golangci-lint", "run")
        assert go.typecheck_cmd is None  # Compiled language
        assert go.test_cmd == ("go", "test", "./...")

    def test_rust_defaults(self) -> None:
        """Test Rust default validation commands."""
        rust = VALIDATION_DEFAULTS[ProjectType.RUST]
        assert rust.format_cmd == ("cargo", "fmt")
        assert rust.lint_cmd == ("cargo", "clippy", "--fix", "--allow-dirty")
        assert rust.typecheck_cmd is None  # Compiled language
        assert rust.test_cmd == ("cargo", "test")

    def test_unknown_defaults_match_python(self) -> None:
        """Test that UNKNOWN type defaults match Python defaults."""
        unknown = VALIDATION_DEFAULTS[ProjectType.UNKNOWN]
        python = VALIDATION_DEFAULTS[ProjectType.PYTHON]
        assert unknown.format_cmd == python.format_cmd
        assert unknown.lint_cmd == python.lint_cmd
        assert unknown.typecheck_cmd == python.typecheck_cmd
        assert unknown.test_cmd == python.test_cmd


class TestPythonDefaults:
    """Test suite for PYTHON_DEFAULTS constant."""

    def test_python_defaults_is_validation_commands(self) -> None:
        """Test that PYTHON_DEFAULTS is a ValidationCommands instance."""
        assert isinstance(PYTHON_DEFAULTS, ValidationCommands)

    def test_python_defaults_matches_validation_defaults(self) -> None:
        """Test that PYTHON_DEFAULTS is the same as VALIDATION_DEFAULTS[PYTHON]."""
        assert PYTHON_DEFAULTS is VALIDATION_DEFAULTS[ProjectType.PYTHON]


# =============================================================================
# ValidationCommands Dataclass Tests
# =============================================================================


class TestValidationCommands:
    """Test suite for ValidationCommands dataclass."""

    def test_create_with_all_commands(self) -> None:
        """Test creating ValidationCommands with all commands specified."""
        commands = ValidationCommands(
            format_cmd=("ruff", "format", "."),
            lint_cmd=("ruff", "check", "--fix", "."),
            typecheck_cmd=("mypy", "."),
            test_cmd=("pytest",),
        )
        assert commands.format_cmd == ("ruff", "format", ".")
        assert commands.lint_cmd == ("ruff", "check", "--fix", ".")
        assert commands.typecheck_cmd == ("mypy", ".")
        assert commands.test_cmd == ("pytest",)

    def test_create_with_no_commands(self) -> None:
        """Test creating ValidationCommands with default None values."""
        commands = ValidationCommands()
        assert commands.format_cmd is None
        assert commands.lint_cmd is None
        assert commands.typecheck_cmd is None
        assert commands.test_cmd is None

    def test_create_with_partial_commands(self) -> None:
        """Test creating ValidationCommands with some commands specified."""
        commands = ValidationCommands(
            format_cmd=("black", "."),
            test_cmd=("pytest", "-v"),
        )
        assert commands.format_cmd == ("black", ".")
        assert commands.lint_cmd is None
        assert commands.typecheck_cmd is None
        assert commands.test_cmd == ("pytest", "-v")

    def test_is_frozen(self) -> None:
        """Test that ValidationCommands is frozen (immutable)."""
        commands = ValidationCommands(format_cmd=("ruff", "format", "."))
        with pytest.raises(AttributeError, match="cannot assign to field"):
            commands.format_cmd = ("black", ".")

    def test_to_dict_with_all_commands(self) -> None:
        """Test to_dict with all commands specified."""
        commands = ValidationCommands(
            format_cmd=("ruff", "format", "."),
            lint_cmd=("ruff", "check", "."),
            typecheck_cmd=("mypy", "."),
            test_cmd=("pytest",),
        )
        result = commands.to_dict()
        assert result == {
            "format_cmd": ["ruff", "format", "."],
            "lint_cmd": ["ruff", "check", "."],
            "typecheck_cmd": ["mypy", "."],
            "test_cmd": ["pytest"],
        }

    def test_to_dict_with_none_values(self) -> None:
        """Test to_dict preserves None values."""
        commands = ValidationCommands(
            format_cmd=("ruff", "format", "."),
            typecheck_cmd=None,
        )
        result = commands.to_dict()
        assert result["format_cmd"] == ["ruff", "format", "."]
        assert result["lint_cmd"] is None
        assert result["typecheck_cmd"] is None
        assert result["test_cmd"] is None

    def test_to_dict_converts_tuples_to_lists(self) -> None:
        """Test that to_dict converts tuples to lists for serialization."""
        commands = ValidationCommands(format_cmd=("a", "b", "c"))
        result = commands.to_dict()
        assert isinstance(result["format_cmd"], list)
        assert result["format_cmd"] == ["a", "b", "c"]

    def test_for_project_type_python(self) -> None:
        """Test for_project_type returns Python defaults."""
        commands = ValidationCommands.for_project_type(ProjectType.PYTHON)
        assert commands == VALIDATION_DEFAULTS[ProjectType.PYTHON]

    def test_for_project_type_nodejs(self) -> None:
        """Test for_project_type returns Node.js defaults."""
        commands = ValidationCommands.for_project_type(ProjectType.NODEJS)
        assert commands == VALIDATION_DEFAULTS[ProjectType.NODEJS]

    def test_for_project_type_go(self) -> None:
        """Test for_project_type returns Go defaults."""
        commands = ValidationCommands.for_project_type(ProjectType.GO)
        assert commands == VALIDATION_DEFAULTS[ProjectType.GO]

    def test_for_project_type_rust(self) -> None:
        """Test for_project_type returns Rust defaults."""
        commands = ValidationCommands.for_project_type(ProjectType.RUST)
        assert commands == VALIDATION_DEFAULTS[ProjectType.RUST]

    def test_for_project_type_unknown(self) -> None:
        """Test for_project_type returns defaults for UNKNOWN type."""
        commands = ValidationCommands.for_project_type(ProjectType.UNKNOWN)
        assert commands == VALIDATION_DEFAULTS[ProjectType.UNKNOWN]

    def test_equality(self) -> None:
        """Test ValidationCommands equality comparison."""
        commands1 = ValidationCommands(format_cmd=("ruff", "format", "."))
        commands2 = ValidationCommands(format_cmd=("ruff", "format", "."))
        commands3 = ValidationCommands(format_cmd=("black", "."))

        assert commands1 == commands2
        assert commands1 != commands3


# =============================================================================
# ProjectMarker Dataclass Tests
# =============================================================================


class TestProjectMarker:
    """Test suite for ProjectMarker dataclass."""

    def test_create_with_required_fields(self) -> None:
        """Test creating ProjectMarker with required fields only."""
        marker = ProjectMarker(
            file_name="pyproject.toml",
            file_path="/project/pyproject.toml",
            project_type=ProjectType.PYTHON,
        )
        assert marker.file_name == "pyproject.toml"
        assert marker.file_path == "/project/pyproject.toml"
        assert marker.project_type == ProjectType.PYTHON
        assert marker.content is None
        assert marker.priority == 1

    def test_create_with_all_fields(self) -> None:
        """Test creating ProjectMarker with all fields."""
        marker = ProjectMarker(
            file_name="package.json",
            file_path="/project/package.json",
            project_type=ProjectType.NODEJS,
            content='{"name": "my-project"}',
            priority=1,
        )
        assert marker.file_name == "package.json"
        assert marker.content == '{"name": "my-project"}'
        assert marker.priority == 1

    def test_is_frozen(self) -> None:
        """Test that ProjectMarker is frozen (immutable)."""
        marker = ProjectMarker(
            file_name="test.txt",
            file_path="/test.txt",
            project_type=ProjectType.PYTHON,
        )
        with pytest.raises(AttributeError, match="cannot assign to field"):
            marker.file_name = "other.txt"

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        marker = ProjectMarker(
            file_name="Cargo.toml",
            file_path="/project/Cargo.toml",
            project_type=ProjectType.RUST,
            content="[package]",
            priority=1,
        )
        result = marker.to_dict()
        assert result == {
            "file_name": "Cargo.toml",
            "file_path": "/project/Cargo.toml",
            "project_type": "rust",
            "content": "[package]",
            "priority": 1,
        }

    def test_to_dict_with_none_content(self) -> None:
        """Test to_dict with None content."""
        marker = ProjectMarker(
            file_name="go.mod",
            file_path="/project/go.mod",
            project_type=ProjectType.GO,
        )
        result = marker.to_dict()
        assert result["content"] is None

    def test_to_dict_project_type_is_string(self) -> None:
        """Test that to_dict converts ProjectType to string value."""
        marker = ProjectMarker(
            file_name="test",
            file_path="/test",
            project_type=ProjectType.ANSIBLE_COLLECTION,
        )
        result = marker.to_dict()
        assert result["project_type"] == "ansible_collection"
        assert isinstance(result["project_type"], str)


# =============================================================================
# PrerequisiteCheck Dataclass Tests
# =============================================================================


class TestPrerequisiteCheck:
    """Test suite for PrerequisiteCheck dataclass."""

    def test_create_with_required_fields(self) -> None:
        """Test creating PrerequisiteCheck with required fields."""
        check = PrerequisiteCheck(
            name="git_installed",
            display_name="Git",
            status=PreflightStatus.PASS,
            message="Git is installed",
        )
        assert check.name == "git_installed"
        assert check.display_name == "Git"
        assert check.status == PreflightStatus.PASS
        assert check.message == "Git is installed"
        assert check.remediation is None
        assert check.duration_ms == 0

    def test_create_with_all_fields(self) -> None:
        """Test creating PrerequisiteCheck with all fields."""
        check = PrerequisiteCheck(
            name="gh_auth",
            display_name="GitHub CLI",
            status=PreflightStatus.FAIL,
            message="Not authenticated",
            remediation="Run 'gh auth login'",
            duration_ms=150,
        )
        assert check.name == "gh_auth"
        assert check.display_name == "GitHub CLI"
        assert check.status == PreflightStatus.FAIL
        assert check.message == "Not authenticated"
        assert check.remediation == "Run 'gh auth login'"
        assert check.duration_ms == 150

    def test_is_frozen(self) -> None:
        """Test that PrerequisiteCheck is frozen (immutable)."""
        check = PrerequisiteCheck(
            name="test",
            display_name="Test",
            status=PreflightStatus.PASS,
            message="OK",
        )
        with pytest.raises(AttributeError, match="cannot assign to field"):
            check.status = PreflightStatus.FAIL

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        check = PrerequisiteCheck(
            name="api_key",
            display_name="Claude API Key",
            status=PreflightStatus.SKIP,
            message="Optional check skipped",
            remediation=None,
            duration_ms=10,
        )
        result = check.to_dict()
        assert result == {
            "name": "api_key",
            "display_name": "Claude API Key",
            "status": "skip",
            "message": "Optional check skipped",
            "remediation": None,
            "duration_ms": 10,
        }

    def test_to_dict_status_is_string(self) -> None:
        """Test that to_dict converts PreflightStatus to string value."""
        check = PrerequisiteCheck(
            name="test",
            display_name="Test",
            status=PreflightStatus.PASS,
            message="OK",
        )
        result = check.to_dict()
        assert result["status"] == "pass"
        assert isinstance(result["status"], str)


# =============================================================================
# GitRemoteInfo Dataclass Tests
# =============================================================================


class TestGitRemoteInfo:
    """Test suite for GitRemoteInfo dataclass."""

    def test_create_with_defaults(self) -> None:
        """Test creating GitRemoteInfo with default values."""
        info = GitRemoteInfo()
        assert info.owner is None
        assert info.repo is None
        assert info.remote_url is None
        assert info.remote_name == "origin"

    def test_create_with_all_fields(self) -> None:
        """Test creating GitRemoteInfo with all fields."""
        info = GitRemoteInfo(
            owner="anthropics",
            repo="maverick",
            remote_url="git@github.com:anthropics/maverick.git",
            remote_name="origin",
        )
        assert info.owner == "anthropics"
        assert info.repo == "maverick"
        assert info.remote_url == "git@github.com:anthropics/maverick.git"
        assert info.remote_name == "origin"

    def test_is_frozen(self) -> None:
        """Test that GitRemoteInfo is frozen (immutable)."""
        info = GitRemoteInfo(owner="test", repo="repo")
        with pytest.raises(AttributeError, match="cannot assign to field"):
            info.owner = "other"

    def test_full_name_with_both_owner_and_repo(self) -> None:
        """Test full_name property returns owner/repo format."""
        info = GitRemoteInfo(owner="anthropics", repo="maverick")
        assert info.full_name == "anthropics/maverick"

    def test_full_name_with_only_owner(self) -> None:
        """Test full_name property returns None when repo is missing."""
        info = GitRemoteInfo(owner="anthropics", repo=None)
        assert info.full_name is None

    def test_full_name_with_only_repo(self) -> None:
        """Test full_name property returns None when owner is missing."""
        info = GitRemoteInfo(owner=None, repo="maverick")
        assert info.full_name is None

    def test_full_name_with_neither(self) -> None:
        """Test full_name property returns None when both are missing."""
        info = GitRemoteInfo()
        assert info.full_name is None

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        info = GitRemoteInfo(
            owner="anthropics",
            repo="maverick",
            remote_url="https://github.com/anthropics/maverick.git",
            remote_name="origin",
        )
        result = info.to_dict()
        assert result == {
            "owner": "anthropics",
            "repo": "maverick",
            "remote_url": "https://github.com/anthropics/maverick.git",
            "remote_name": "origin",
            "full_name": "anthropics/maverick",
        }

    def test_to_dict_includes_full_name(self) -> None:
        """Test that to_dict includes the computed full_name property."""
        info = GitRemoteInfo(owner="org", repo="project")
        result = info.to_dict()
        assert "full_name" in result
        assert result["full_name"] == "org/project"

    def test_to_dict_with_none_full_name(self) -> None:
        """Test to_dict when full_name is None."""
        info = GitRemoteInfo(owner="org")
        result = info.to_dict()
        assert result["full_name"] is None


# =============================================================================
# ProjectDetectionResult Dataclass Tests
# =============================================================================


class TestProjectDetectionResult:
    """Test suite for ProjectDetectionResult dataclass."""

    def test_create_with_required_fields(self) -> None:
        """Test creating ProjectDetectionResult with required field only."""
        result = ProjectDetectionResult(primary_type=ProjectType.PYTHON)
        assert result.primary_type == ProjectType.PYTHON
        assert result.detected_types == ()
        assert result.confidence == DetectionConfidence.LOW
        assert result.findings == ()
        assert result.markers == ()
        assert isinstance(result.validation_commands, ValidationCommands)
        assert result.detection_method == "markers"

    def test_create_with_all_fields(self) -> None:
        """Test creating ProjectDetectionResult with all fields."""
        marker = ProjectMarker(
            file_name="pyproject.toml",
            file_path="/project/pyproject.toml",
            project_type=ProjectType.PYTHON,
        )
        commands = ValidationCommands(format_cmd=("ruff", "format", "."))

        result = ProjectDetectionResult(
            primary_type=ProjectType.PYTHON,
            detected_types=(ProjectType.PYTHON, ProjectType.NODEJS),
            confidence=DetectionConfidence.HIGH,
            findings=("Found pyproject.toml", "Found package.json"),
            markers=(marker,),
            validation_commands=commands,
            detection_method="claude",
        )
        assert result.primary_type == ProjectType.PYTHON
        assert result.detected_types == (ProjectType.PYTHON, ProjectType.NODEJS)
        assert result.confidence == DetectionConfidence.HIGH
        assert len(result.findings) == 2
        assert len(result.markers) == 1
        assert result.validation_commands == commands
        assert result.detection_method == "claude"

    def test_is_frozen(self) -> None:
        """Test that ProjectDetectionResult is frozen (immutable)."""
        result = ProjectDetectionResult(primary_type=ProjectType.PYTHON)
        with pytest.raises(AttributeError, match="cannot assign to field"):
            result.primary_type = ProjectType.NODEJS

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        marker = ProjectMarker(
            file_name="pyproject.toml",
            file_path="/pyproject.toml",
            project_type=ProjectType.PYTHON,
        )
        commands = ValidationCommands(format_cmd=("ruff", "format", "."))

        result = ProjectDetectionResult(
            primary_type=ProjectType.PYTHON,
            detected_types=(ProjectType.PYTHON,),
            confidence=DetectionConfidence.HIGH,
            findings=("Found pyproject.toml",),
            markers=(marker,),
            validation_commands=commands,
            detection_method="markers",
        )
        output = result.to_dict()

        assert output["primary_type"] == "python"
        assert output["detected_types"] == ["python"]
        assert output["confidence"] == "high"
        assert output["findings"] == ["Found pyproject.toml"]
        assert len(output["markers"]) == 1
        assert output["markers"][0]["file_name"] == "pyproject.toml"
        assert output["validation_commands"]["format_cmd"] == ["ruff", "format", "."]
        assert output["detection_method"] == "markers"

    def test_to_dict_converts_tuples_to_lists(self) -> None:
        """Test that to_dict converts all tuples to lists for serialization."""
        result = ProjectDetectionResult(
            primary_type=ProjectType.GO,
            detected_types=(ProjectType.GO, ProjectType.RUST),
            findings=("finding1", "finding2"),
        )
        output = result.to_dict()
        assert isinstance(output["detected_types"], list)
        assert isinstance(output["findings"], list)
        assert isinstance(output["markers"], list)


# =============================================================================
# InitPreflightResult Dataclass Tests
# =============================================================================


class TestInitPreflightResult:
    """Test suite for InitPreflightResult dataclass."""

    def test_create_with_required_field(self) -> None:
        """Test creating InitPreflightResult with required field only."""
        result = InitPreflightResult(success=True)
        assert result.success is True
        assert result.checks == ()
        assert result.total_duration_ms == 0
        assert result.failed_checks == ()
        assert result.warnings == ()

    def test_create_with_all_fields(self) -> None:
        """Test creating InitPreflightResult with all fields."""
        check1 = PrerequisiteCheck(
            name="git",
            display_name="Git",
            status=PreflightStatus.PASS,
            message="OK",
        )
        check2 = PrerequisiteCheck(
            name="gh",
            display_name="GitHub CLI",
            status=PreflightStatus.FAIL,
            message="Not found",
        )

        result = InitPreflightResult(
            success=False,
            checks=(check1, check2),
            total_duration_ms=250,
            failed_checks=("gh",),
            warnings=("Consider installing GitHub CLI",),
        )
        assert result.success is False
        assert len(result.checks) == 2
        assert result.total_duration_ms == 250
        assert result.failed_checks == ("gh",)
        assert result.warnings == ("Consider installing GitHub CLI",)

    def test_is_frozen(self) -> None:
        """Test that InitPreflightResult is frozen (immutable)."""
        result = InitPreflightResult(success=True)
        with pytest.raises(AttributeError, match="cannot assign to field"):
            result.success = False

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        check = PrerequisiteCheck(
            name="git",
            display_name="Git",
            status=PreflightStatus.PASS,
            message="OK",
            duration_ms=50,
        )
        result = InitPreflightResult(
            success=True,
            checks=(check,),
            total_duration_ms=100,
            failed_checks=(),
            warnings=("Warning message",),
        )
        output = result.to_dict()

        assert output["success"] is True
        assert len(output["checks"]) == 1
        assert output["checks"][0]["name"] == "git"
        assert output["total_duration_ms"] == 100
        assert output["failed_checks"] == []
        assert output["warnings"] == ["Warning message"]

    def test_to_dict_converts_tuples_to_lists(self) -> None:
        """Test that to_dict converts tuples to lists."""
        result = InitPreflightResult(
            success=False,
            failed_checks=("check1", "check2"),
            warnings=("warn1", "warn2"),
        )
        output = result.to_dict()
        assert isinstance(output["checks"], list)
        assert isinstance(output["failed_checks"], list)
        assert isinstance(output["warnings"], list)


# =============================================================================
# Pydantic Model Tests - InitGitHubConfig
# =============================================================================


class TestInitGitHubConfig:
    """Test suite for InitGitHubConfig Pydantic model."""

    def test_create_with_defaults(self) -> None:
        """Test creating InitGitHubConfig with default values."""
        config = InitGitHubConfig()
        assert config.owner is None
        assert config.repo is None
        assert config.default_branch == "main"

    def test_create_with_all_fields(self) -> None:
        """Test creating InitGitHubConfig with all fields."""
        config = InitGitHubConfig(
            owner="anthropics",
            repo="maverick",
            default_branch="develop",
        )
        assert config.owner == "anthropics"
        assert config.repo == "maverick"
        assert config.default_branch == "develop"

    def test_model_dump(self) -> None:
        """Test model_dump serialization."""
        config = InitGitHubConfig(owner="org", repo="project")
        output = config.model_dump()
        assert output == {
            "owner": "org",
            "repo": "project",
            "default_branch": "main",
        }

    def test_model_dump_exclude_none(self) -> None:
        """Test model_dump with exclude_none option."""
        config = InitGitHubConfig()
        output = config.model_dump(exclude_none=True)
        assert output == {"default_branch": "main"}


# =============================================================================
# Pydantic Model Tests - InitValidationConfig
# =============================================================================


class TestInitValidationConfig:
    """Test suite for InitValidationConfig Pydantic model."""

    def test_create_with_defaults(self) -> None:
        """Test creating InitValidationConfig with default values."""
        config = InitValidationConfig()
        assert config.format_cmd is None
        assert config.lint_cmd is None
        assert config.typecheck_cmd is None
        assert config.test_cmd is None
        assert config.timeout_seconds == 300
        assert config.max_errors == 50

    def test_create_with_all_fields(self) -> None:
        """Test creating InitValidationConfig with all fields."""
        config = InitValidationConfig(
            format_cmd=["ruff", "format", "."],
            lint_cmd=["ruff", "check", "."],
            typecheck_cmd=["mypy", "."],
            test_cmd=["pytest"],
            timeout_seconds=600,
            max_errors=100,
        )
        assert config.format_cmd == ["ruff", "format", "."]
        assert config.lint_cmd == ["ruff", "check", "."]
        assert config.typecheck_cmd == ["mypy", "."]
        assert config.test_cmd == ["pytest"]
        assert config.timeout_seconds == 600
        assert config.max_errors == 100

    def test_model_dump(self) -> None:
        """Test model_dump serialization."""
        config = InitValidationConfig(format_cmd=["black", "."])
        output = config.model_dump()
        assert output["format_cmd"] == ["black", "."]
        assert output["timeout_seconds"] == 300
        assert output["max_errors"] == 50


# =============================================================================
# Pydantic Model Tests - InitModelConfig
# =============================================================================


class TestInitModelConfig:
    """Test suite for InitModelConfig Pydantic model."""

    def test_create_with_defaults(self) -> None:
        """Test creating InitModelConfig with default values."""
        config = InitModelConfig()
        assert config.model_id == "claude-sonnet-4-5-20250929"
        assert config.max_tokens == 64000
        assert config.temperature == 0.0

    def test_create_with_custom_values(self) -> None:
        """Test creating InitModelConfig with custom values."""
        config = InitModelConfig(
            model_id="claude-opus-4-20250514",
            max_tokens=16384,
            temperature=0.7,
        )
        assert config.model_id == "claude-opus-4-20250514"
        assert config.max_tokens == 16384
        assert config.temperature == 0.7

    def test_model_dump(self) -> None:
        """Test model_dump serialization."""
        config = InitModelConfig()
        output = config.model_dump()
        assert output == {
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 64000,
            "temperature": 0.0,
        }


# =============================================================================
# Pydantic Model Tests - InitConfig
# =============================================================================


class TestInitConfig:
    """Test suite for InitConfig Pydantic model."""

    def test_create_with_defaults(self) -> None:
        """Test creating InitConfig with default values."""
        config = InitConfig()
        assert isinstance(config.github, InitGitHubConfig)
        assert isinstance(config.validation, InitValidationConfig)
        assert isinstance(config.model, InitModelConfig)
        assert config.notifications == {"enabled": False}
        assert config.parallel == {"max_agents": 3, "max_tasks": 5}
        assert config.verbosity == "warning"

    def test_create_with_custom_values(self) -> None:
        """Test creating InitConfig with custom values."""
        config = InitConfig(
            github=InitGitHubConfig(owner="org", repo="project"),
            validation=InitValidationConfig(format_cmd=["black", "."]),
            model=InitModelConfig(model_id="custom-model"),
            notifications={"enabled": True, "topic": "test"},
            parallel={"max_agents": 5, "max_tasks": 10},
            verbosity="debug",
        )
        assert config.github.owner == "org"
        assert config.validation.format_cmd == ["black", "."]
        assert config.model.model_id == "custom-model"
        assert config.notifications["enabled"] is True
        assert config.parallel["max_agents"] == 5
        assert config.verbosity == "debug"

    def test_model_dump(self) -> None:
        """Test model_dump serialization."""
        config = InitConfig()
        output = config.model_dump()

        assert "github" in output
        assert "validation" in output
        assert "model" in output
        assert "notifications" in output
        assert "parallel" in output
        assert "verbosity" in output

    def test_to_yaml(self) -> None:
        """Test to_yaml serialization."""
        config = InitConfig(
            github=InitGitHubConfig(owner="anthropics", repo="maverick"),
            validation=InitValidationConfig(format_cmd=["ruff", "format", "."]),
        )
        yaml_output = config.to_yaml()

        # Verify it's valid YAML
        parsed = yaml.safe_load(yaml_output)
        assert parsed["github"]["owner"] == "anthropics"
        assert parsed["github"]["repo"] == "maverick"
        assert parsed["validation"]["format_cmd"] == ["ruff", "format", "."]

    def test_to_yaml_excludes_none(self) -> None:
        """Test that to_yaml excludes None values."""
        config = InitConfig()
        yaml_output = config.to_yaml()
        parsed = yaml.safe_load(yaml_output)

        # format_cmd is None by default, should be excluded
        assert "format_cmd" not in parsed.get("validation", {})

    def test_to_yaml_format(self) -> None:
        """Test that to_yaml uses block style (not flow style)."""
        config = InitConfig(
            github=InitGitHubConfig(owner="org", repo="project"),
        )
        yaml_output = config.to_yaml()

        # Block style means no { } for dicts and no [ ] for short lists
        assert "{" not in yaml_output or "}" not in yaml_output

    def test_to_yaml_preserves_key_order(self) -> None:
        """Test that to_yaml preserves key order (sort_keys=False)."""
        config = InitConfig()
        yaml_output = config.to_yaml()

        # Check that 'github' appears before 'verbosity' in the output
        github_pos = yaml_output.find("github:")
        verbosity_pos = yaml_output.find("verbosity:")
        assert github_pos < verbosity_pos


# =============================================================================
# InitResult Dataclass Tests
# =============================================================================


class TestInitResult:
    """Test suite for InitResult dataclass."""

    def test_create_with_required_fields(self) -> None:
        """Test creating InitResult with required fields."""
        preflight = InitPreflightResult(success=True)
        git_info = GitRemoteInfo(owner="org", repo="project")
        config = InitConfig()

        result = InitResult(
            success=True,
            config_path="/project/maverick.yaml",
            preflight=preflight,
            git_info=git_info,
            config=config,
        )
        assert result.success is True
        assert result.config_path == "/project/maverick.yaml"
        assert result.preflight == preflight
        assert result.git_info == git_info
        assert result.config == config
        assert result.detection is None
        assert result.findings_printed is False

    def test_create_with_all_fields(self) -> None:
        """Test creating InitResult with all fields."""
        preflight = InitPreflightResult(success=True)
        git_info = GitRemoteInfo(owner="org", repo="project")
        config = InitConfig()
        detection = ProjectDetectionResult(primary_type=ProjectType.PYTHON)

        result = InitResult(
            success=True,
            config_path="/project/maverick.yaml",
            preflight=preflight,
            git_info=git_info,
            config=config,
            detection=detection,
            findings_printed=True,
        )
        assert result.detection == detection
        assert result.findings_printed is True

    def test_is_frozen(self) -> None:
        """Test that InitResult is frozen (immutable)."""
        preflight = InitPreflightResult(success=True)
        git_info = GitRemoteInfo()
        config = InitConfig()

        result = InitResult(
            success=True,
            config_path="/test",
            preflight=preflight,
            git_info=git_info,
            config=config,
        )
        with pytest.raises(AttributeError, match="cannot assign to field"):
            result.success = False

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        check = PrerequisiteCheck(
            name="git",
            display_name="Git",
            status=PreflightStatus.PASS,
            message="OK",
        )
        preflight = InitPreflightResult(success=True, checks=(check,))
        git_info = GitRemoteInfo(owner="org", repo="project")
        config = InitConfig(
            github=InitGitHubConfig(owner="org", repo="project"),
        )
        detection = ProjectDetectionResult(
            primary_type=ProjectType.PYTHON,
            confidence=DetectionConfidence.HIGH,
        )

        result = InitResult(
            success=True,
            config_path="/project/maverick.yaml",
            preflight=preflight,
            git_info=git_info,
            config=config,
            detection=detection,
            findings_printed=True,
        )
        output = result.to_dict()

        assert output["success"] is True
        assert output["config_path"] == "/project/maverick.yaml"
        assert output["preflight"]["success"] is True
        assert output["preflight"]["checks"][0]["name"] == "git"
        assert output["git_info"]["owner"] == "org"
        assert output["git_info"]["full_name"] == "org/project"
        assert output["config"]["github"]["owner"] == "org"
        assert output["detection"]["primary_type"] == "python"
        assert output["detection"]["confidence"] == "high"
        assert output["findings_printed"] is True

    def test_to_dict_without_detection(self) -> None:
        """Test to_dict when detection is None."""
        preflight = InitPreflightResult(success=True)
        git_info = GitRemoteInfo()
        config = InitConfig()

        result = InitResult(
            success=False,
            config_path="/test",
            preflight=preflight,
            git_info=git_info,
            config=config,
            detection=None,
        )
        output = result.to_dict()
        assert output["detection"] is None

    def test_to_dict_config_uses_model_dump(self) -> None:
        """Test that to_dict uses model_dump for config (Pydantic model)."""
        preflight = InitPreflightResult(success=True)
        git_info = GitRemoteInfo()
        config = InitConfig()

        result = InitResult(
            success=True,
            config_path="/test",
            preflight=preflight,
            git_info=git_info,
            config=config,
        )
        output = result.to_dict()

        # config should be a dict, not InitConfig instance
        assert isinstance(output["config"], dict)
        assert "github" in output["config"]
        assert "validation" in output["config"]
        assert "model" in output["config"]


# =============================================================================
# Model ID Resolution Tests
# =============================================================================


class TestModelNameMap:
    """Test suite for MODEL_NAME_MAP constant."""

    def test_contains_expected_keys(self) -> None:
        """Test that MODEL_NAME_MAP contains expected simple names."""
        assert "opus" in MODEL_NAME_MAP
        assert "sonnet" in MODEL_NAME_MAP
        assert "haiku" in MODEL_NAME_MAP

    def test_all_values_are_full_model_ids(self) -> None:
        """Test that all values start with 'claude-'."""
        for name, model_id in MODEL_NAME_MAP.items():
            assert model_id.startswith("claude-"), (
                f"{name} maps to invalid ID: {model_id}"
            )

    def test_opus_maps_to_correct_model(self) -> None:
        """Test opus maps to correct full model ID."""
        assert MODEL_NAME_MAP["opus"] == "claude-opus-4-5-20251101"

    def test_sonnet_maps_to_correct_model(self) -> None:
        """Test sonnet maps to correct full model ID."""
        assert MODEL_NAME_MAP["sonnet"] == "claude-sonnet-4-5-20250929"

    def test_haiku_maps_to_correct_model(self) -> None:
        """Test haiku maps to correct full model ID."""
        assert MODEL_NAME_MAP["haiku"] == CLAUDE_HAIKU_LATEST


class TestResolveModelId:
    """Test suite for resolve_model_id function."""

    def test_resolve_simple_name_opus(self) -> None:
        """Test resolving 'opus' to full model ID."""
        result = resolve_model_id("opus")
        assert result == "claude-opus-4-5-20251101"

    def test_resolve_simple_name_sonnet(self) -> None:
        """Test resolving 'sonnet' to full model ID."""
        result = resolve_model_id("sonnet")
        assert result == "claude-sonnet-4-5-20250929"

    def test_resolve_simple_name_haiku(self) -> None:
        """Test resolving 'haiku' to full model ID."""
        result = resolve_model_id("haiku")
        assert result == CLAUDE_HAIKU_LATEST

    def test_resolve_uppercase_name(self) -> None:
        """Test that uppercase names are normalized."""
        result = resolve_model_id("OPUS")
        assert result == "claude-opus-4-5-20251101"

    def test_resolve_mixed_case_name(self) -> None:
        """Test that mixed case names are normalized."""
        result = resolve_model_id("Sonnet")
        assert result == "claude-sonnet-4-5-20250929"

    def test_resolve_name_with_whitespace(self) -> None:
        """Test that whitespace is stripped."""
        result = resolve_model_id("  haiku  ")
        assert result == CLAUDE_HAIKU_LATEST

    def test_full_model_id_returned_unchanged(self) -> None:
        """Test that full model IDs are returned as-is."""
        full_id = "claude-opus-4-5-20251101"
        result = resolve_model_id(full_id)
        assert result == full_id

    def test_full_model_id_with_different_version(self) -> None:
        """Test that custom full model IDs are accepted."""
        custom_id = "claude-sonnet-3-6-20240307"
        result = resolve_model_id(custom_id)
        assert result == custom_id

    def test_preserve_case_for_full_ids(self) -> None:
        """Test that case is preserved for full model IDs."""
        # Even though unlikely, if someone passes mixed case, preserve it
        full_id = "Claude-Opus-4-5-20251101"
        result = resolve_model_id(full_id)
        assert result == full_id

    def test_invalid_simple_name_raises_error(self) -> None:
        """Test that invalid simple names raise ValueError."""
        with pytest.raises(ValueError, match="Unknown model name 'invalid'"):
            resolve_model_id("invalid")

    def test_error_message_includes_valid_names(self) -> None:
        """Test that error message lists valid names."""
        with pytest.raises(ValueError, match="haiku, opus, sonnet"):
            resolve_model_id("badmodel")

    def test_error_message_mentions_full_ids(self) -> None:
        """Test that error message mentions full model IDs option."""
        with pytest.raises(ValueError, match="full model IDs starting with 'claude-'"):
            resolve_model_id("xyz")
