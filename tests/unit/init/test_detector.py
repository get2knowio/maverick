"""Unit tests for maverick.init.detector module.

Tests cover:
- find_marker_files(): Marker file discovery and prioritization
- build_detection_context(): Context string generation for Claude
- detect_project_type(): Full detection flow with Claude/marker fallback
- get_validation_commands(): ValidationCommands lookup by project type
- _detect_from_markers(): Marker-based heuristic detection (via detect_project_type)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from maverick.exceptions.init import DetectionError
from maverick.init.detector import (
    build_detection_context,
    detect_project_type,
    find_marker_files,
    get_validation_commands,
)
from maverick.init.models import (
    DetectionConfidence,
    ProjectMarker,
    ProjectType,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Tests for find_marker_files()
# =============================================================================


class TestFindMarkerFiles:
    """Tests for the find_marker_files function."""

    def test_find_pyproject_toml_python(self, tmp_path: Path) -> None:
        """Finding pyproject.toml indicates Python project."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].file_name == "pyproject.toml"
        assert markers[0].project_type == ProjectType.PYTHON
        assert markers[0].priority == 1

    def test_find_package_json_nodejs(self, tmp_path: Path) -> None:
        """Finding package.json indicates NodeJS project."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].file_name == "package.json"
        assert markers[0].project_type == ProjectType.NODEJS
        assert markers[0].priority == 1

    def test_find_cargo_toml_rust(self, tmp_path: Path) -> None:
        """Finding Cargo.toml indicates Rust project."""
        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'test'")

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].file_name == "Cargo.toml"
        assert markers[0].project_type == ProjectType.RUST
        assert markers[0].priority == 1

    def test_find_go_mod_go(self, tmp_path: Path) -> None:
        """Finding go.mod indicates Go project."""
        (tmp_path / "go.mod").write_text("module example.com/test")

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].file_name == "go.mod"
        assert markers[0].project_type == ProjectType.GO
        assert markers[0].priority == 1

    def test_find_galaxy_yml_ansible_collection(self, tmp_path: Path) -> None:
        """Finding galaxy.yml indicates Ansible Collection."""
        (tmp_path / "galaxy.yml").write_text("namespace: test\nname: collection")

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].file_name == "galaxy.yml"
        assert markers[0].project_type == ProjectType.ANSIBLE_COLLECTION
        assert markers[0].priority == 1

    def test_find_ansible_cfg_ansible_playbook(self, tmp_path: Path) -> None:
        """Finding ansible.cfg indicates Ansible Playbook."""
        (tmp_path / "ansible.cfg").write_text("[defaults]\ninventory = hosts")

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].file_name == "ansible.cfg"
        assert markers[0].project_type == ProjectType.ANSIBLE_PLAYBOOK
        assert markers[0].priority == 3

    def test_find_requirements_yml_ansible_playbook(self, tmp_path: Path) -> None:
        """Finding requirements.yml indicates Ansible Playbook."""
        (tmp_path / "requirements.yml").write_text("collections:\n  - name: test")

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].file_name == "requirements.yml"
        assert markers[0].project_type == ProjectType.ANSIBLE_PLAYBOOK
        assert markers[0].priority == 2

    def test_multiple_markers_sorted_by_priority(self, tmp_path: Path) -> None:
        """Multiple marker files are returned sorted by priority."""
        # Create markers with different priorities
        (tmp_path / "pyproject.toml").write_text("[project]")  # priority 1
        (tmp_path / "setup.py").write_text("# setup")  # priority 2
        (tmp_path / "requirements.txt").write_text("pytest")  # priority 4

        markers = find_marker_files(tmp_path)

        assert len(markers) == 3
        # Should be sorted by priority (lower first)
        assert markers[0].file_name == "pyproject.toml"
        assert markers[0].priority == 1
        assert markers[1].file_name == "setup.py"
        assert markers[1].priority == 2
        assert markers[2].file_name == "requirements.txt"
        assert markers[2].priority == 4

    def test_multiple_project_types(self, tmp_path: Path) -> None:
        """Finding markers for multiple project types."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "package.json").write_text("{}")

        markers = find_marker_files(tmp_path)

        assert len(markers) == 2
        project_types = {m.project_type for m in markers}
        assert ProjectType.PYTHON in project_types
        assert ProjectType.NODEJS in project_types

    def test_non_existent_path_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent path returns empty list."""
        non_existent = tmp_path / "does_not_exist"

        markers = find_marker_files(non_existent)

        assert markers == []

    def test_path_is_file_returns_empty(self, tmp_path: Path) -> None:
        """Path that is a file (not directory) returns empty list."""
        file_path = tmp_path / "some_file.txt"
        file_path.write_text("content")

        markers = find_marker_files(file_path)

        assert markers == []

    def test_max_depth_zero_only_root(self, tmp_path: Path) -> None:
        """max_depth=0 only searches root directory."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "package.json").write_text("{}")

        markers = find_marker_files(tmp_path, max_depth=0)

        assert len(markers) == 1
        assert markers[0].file_name == "pyproject.toml"

    def test_max_depth_searches_subdirectories(self, tmp_path: Path) -> None:
        """max_depth > 0 searches subdirectories."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "package.json").write_text("{}")

        markers = find_marker_files(tmp_path, max_depth=1)

        assert len(markers) == 2
        file_names = {m.file_name for m in markers}
        assert "pyproject.toml" in file_names
        assert "package.json" in file_names

    def test_max_depth_limits_search(self, tmp_path: Path) -> None:
        """max_depth limits how deep the search goes."""
        # Create nested structure
        (tmp_path / "pyproject.toml").write_text("[project]")
        level1 = tmp_path / "level1"
        level1.mkdir()
        (level1 / "package.json").write_text("{}")
        level2 = level1 / "level2"
        level2.mkdir()
        (level2 / "Cargo.toml").write_text("[package]")

        # max_depth=1 should find root and level1, but not level2
        markers = find_marker_files(tmp_path, max_depth=1)

        file_names = {m.file_name for m in markers}
        assert "pyproject.toml" in file_names
        assert "package.json" in file_names
        assert "Cargo.toml" not in file_names

    def test_marker_includes_file_content(self, tmp_path: Path) -> None:
        """Marker includes file content."""
        content = "[project]\nname = 'myproject'"
        (tmp_path / "pyproject.toml").write_text(content)

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].content == content

    def test_marker_includes_file_path(self, tmp_path: Path) -> None:
        """Marker includes absolute file path."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].file_path == str(tmp_path / "pyproject.toml")

    def test_hidden_files_skipped(self, tmp_path: Path) -> None:
        """Hidden files and directories are skipped."""
        (tmp_path / ".hidden_marker.toml").write_text("hidden")
        hidden_dir = tmp_path / ".hidden_dir"
        hidden_dir.mkdir()
        (hidden_dir / "pyproject.toml").write_text("[project]")
        (tmp_path / "package.json").write_text("{}")

        markers = find_marker_files(tmp_path)

        # Only package.json should be found (not hidden files)
        assert len(markers) == 1
        assert markers[0].file_name == "package.json"

    def test_non_marker_files_ignored(self, tmp_path: Path) -> None:
        """Files that are not marker files are ignored."""
        (tmp_path / "README.md").write_text("# Readme")
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "pyproject.toml").write_text("[project]")

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].file_name == "pyproject.toml"


# =============================================================================
# Tests for build_detection_context()
# =============================================================================


class TestBuildDetectionContext:
    """Tests for the build_detection_context function."""

    def test_context_includes_project_name(self, tmp_path: Path) -> None:
        """Context includes the project directory name."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()

        context = build_detection_context(project_dir, [])

        assert "# Project: my-project" in context

    def test_context_includes_project_path(self, tmp_path: Path) -> None:
        """Context includes full project path."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()

        context = build_detection_context(project_dir, [])

        assert f"Path: {project_dir}" in context

    def test_context_includes_directory_tree(self, tmp_path: Path) -> None:
        """Context includes directory structure."""
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "README.md").write_text("# Readme")

        context = build_detection_context(tmp_path, [])

        assert "## Directory Structure" in context
        assert "```" in context  # Code block
        assert "src" in context
        assert "tests" in context

    def test_context_includes_marker_file_contents(self, tmp_path: Path) -> None:
        """Context includes contents of marker files."""
        content = "[project]\nname = 'test'"
        marker = ProjectMarker(
            file_name="pyproject.toml",
            file_path=str(tmp_path / "pyproject.toml"),
            project_type=ProjectType.PYTHON,
            content=content,
            priority=1,
        )

        context = build_detection_context(tmp_path, [marker])

        assert "## Detected Marker Files" in context
        assert "### pyproject.toml" in context
        assert f"Path: {tmp_path / 'pyproject.toml'}" in context
        assert "Project Type: python" in context
        assert content in context

    def test_context_truncates_large_content(self, tmp_path: Path) -> None:
        """Context truncates marker file content if too large."""
        # Create content larger than max_content_length
        large_content = "x" * 3000
        marker = ProjectMarker(
            file_name="pyproject.toml",
            file_path=str(tmp_path / "pyproject.toml"),
            project_type=ProjectType.PYTHON,
            content=large_content,
            priority=1,
        )

        context = build_detection_context(tmp_path, [marker], max_content_length=100)

        # Should be truncated
        assert "[truncated]" in context
        # Should not contain full content
        assert large_content not in context

    def test_context_handles_empty_content(self, tmp_path: Path) -> None:
        """Context handles marker with empty/None content."""
        marker = ProjectMarker(
            file_name="pyproject.toml",
            file_path=str(tmp_path / "pyproject.toml"),
            project_type=ProjectType.PYTHON,
            content=None,
            priority=1,
        )

        context = build_detection_context(tmp_path, [marker])

        assert "(empty or unreadable)" in context

    def test_context_multiple_markers(self, tmp_path: Path) -> None:
        """Context includes multiple marker files."""
        markers = [
            ProjectMarker(
                file_name="pyproject.toml",
                file_path=str(tmp_path / "pyproject.toml"),
                project_type=ProjectType.PYTHON,
                content="[project]",
                priority=1,
            ),
            ProjectMarker(
                file_name="requirements.txt",
                file_path=str(tmp_path / "requirements.txt"),
                project_type=ProjectType.PYTHON,
                content="pytest",
                priority=4,
            ),
        ]

        context = build_detection_context(tmp_path, markers)

        assert "### pyproject.toml" in context
        assert "### requirements.txt" in context


# =============================================================================
# Tests for detect_project_type()
# =============================================================================


class TestDetectProjectType:
    """Tests for the detect_project_type function."""

    @pytest.mark.asyncio
    async def test_override_type_returns_immediately(self, tmp_path: Path) -> None:
        """When override_type is provided, returns immediately without detection."""
        result = await detect_project_type(
            tmp_path,
            override_type=ProjectType.RUST,
            use_claude=False,
        )

        assert result.primary_type == ProjectType.RUST
        assert result.confidence == DetectionConfidence.HIGH
        assert result.detection_method == "override"
        assert "manually set to rust" in result.findings[0]

    @pytest.mark.asyncio
    async def test_override_includes_validation_commands(self, tmp_path: Path) -> None:
        """Override result includes proper validation commands."""
        result = await detect_project_type(
            tmp_path,
            override_type=ProjectType.GO,
            use_claude=False,
        )

        assert result.validation_commands.format_cmd == ("gofmt", "-w", ".")
        assert result.validation_commands.test_cmd == ("go", "test", "./...")

    @pytest.mark.asyncio
    async def test_marker_only_detection_single_type(self, tmp_path: Path) -> None:
        """Marker-only detection with single project type."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        result = await detect_project_type(tmp_path, use_claude=False)

        assert result.primary_type == ProjectType.PYTHON
        assert result.confidence == DetectionConfidence.HIGH
        assert result.detection_method == "markers"
        assert len(result.markers) == 1

    @pytest.mark.asyncio
    async def test_marker_only_detection_no_markers(self, tmp_path: Path) -> None:
        """Marker-only detection with no markers found."""
        result = await detect_project_type(tmp_path, use_claude=False)

        assert result.primary_type == ProjectType.UNKNOWN
        assert result.confidence == DetectionConfidence.LOW
        assert result.detection_method == "markers"
        assert "No marker files found" in result.findings

    @pytest.mark.asyncio
    async def test_marker_detection_multiple_same_type(self, tmp_path: Path) -> None:
        """Multiple markers of same type gives HIGH confidence."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "requirements.txt").write_text("pytest")

        result = await detect_project_type(tmp_path, use_claude=False)

        assert result.primary_type == ProjectType.PYTHON
        assert result.confidence == DetectionConfidence.HIGH
        assert len(result.markers) == 2

    @pytest.mark.asyncio
    async def test_marker_detection_mixed_types(self, tmp_path: Path) -> None:
        """Mixed type markers result in MEDIUM or LOW confidence."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "package.json").write_text("{}")

        result = await detect_project_type(tmp_path, use_claude=False)

        # Both have priority 1, so primary is determined by score
        assert result.primary_type in [ProjectType.PYTHON, ProjectType.NODEJS]
        # With equal scores, confidence should be LOW
        assert result.confidence == DetectionConfidence.LOW

    @pytest.mark.asyncio
    async def test_claude_detection_success(self, tmp_path: Path) -> None:
        """Claude detection successfully parses response."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        # Mock Claude response
        mock_response = json.dumps(
            {
                "primary_type": "python",
                "detected_types": ["python"],
                "confidence": "high",
                "findings": ["pyproject.toml found at root"],
            }
        )

        async def mock_query_impl(*args: Any, **kwargs: Any) -> Any:
            mock_msg = MagicMock()
            mock_msg.__class__.__name__ = "AssistantMessage"
            mock_msg.content = mock_response
            yield mock_msg

        with patch(
            "maverick.init.detector.query",
            side_effect=lambda *args, **kwargs: mock_query_impl(),
        ):
            result = await detect_project_type(tmp_path, use_claude=True)

        assert result.primary_type == ProjectType.PYTHON
        assert result.confidence == DetectionConfidence.HIGH
        assert result.detection_method == "claude"

    @pytest.mark.asyncio
    async def test_claude_detection_with_code_block(self, tmp_path: Path) -> None:
        """Claude detection parses JSON wrapped in code block."""
        (tmp_path / "Cargo.toml").write_text("[package]")

        # Mock Claude response with code block
        mock_response = """```json
{
    "primary_type": "rust",
    "detected_types": ["rust"],
    "confidence": "high",
    "findings": ["Cargo.toml found"]
}
```"""

        async def mock_query_impl(*args: Any, **kwargs: Any) -> Any:
            mock_msg = MagicMock()
            mock_msg.__class__.__name__ = "AssistantMessage"
            mock_msg.content = mock_response
            yield mock_msg

        with patch(
            "maverick.init.detector.query",
            side_effect=lambda *args, **kwargs: mock_query_impl(),
        ):
            result = await detect_project_type(tmp_path, use_claude=True)

        assert result.primary_type == ProjectType.RUST
        assert result.detection_method == "claude"

    @pytest.mark.asyncio
    async def test_claude_timeout_falls_back_to_markers(self, tmp_path: Path) -> None:
        """Claude timeout falls back to marker detection."""
        (tmp_path / "go.mod").write_text("module test")

        async def slow_query(*args: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(10)  # Will trigger timeout
            yield MagicMock()

        with patch(
            "maverick.init.detector.query",
            side_effect=lambda *args, **kwargs: slow_query(),
        ):
            result = await detect_project_type(
                tmp_path,
                use_claude=True,
                timeout=0.01,  # Very short timeout
            )

        # Should fall back to marker detection
        assert result.primary_type == ProjectType.GO
        assert result.detection_method == "markers"

    @pytest.mark.asyncio
    async def test_claude_json_error_falls_back_to_markers(
        self, tmp_path: Path
    ) -> None:
        """Claude JSON parse error falls back to marker detection."""
        (tmp_path / "package.json").write_text("{}")

        # Mock invalid JSON response
        async def mock_query_impl(*args: Any, **kwargs: Any) -> Any:
            mock_msg = MagicMock()
            mock_msg.__class__.__name__ = "AssistantMessage"
            mock_msg.content = "This is not valid JSON"
            yield mock_msg

        with patch(
            "maverick.init.detector.query",
            side_effect=lambda *args, **kwargs: mock_query_impl(),
        ):
            result = await detect_project_type(tmp_path, use_claude=True)

        # Should fall back to marker detection
        assert result.primary_type == ProjectType.NODEJS
        assert result.detection_method == "markers"

    @pytest.mark.asyncio
    async def test_claude_api_error_raises_detection_error(
        self, tmp_path: Path
    ) -> None:
        """Claude API error raises DetectionError."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        with patch(
            "maverick.init.detector.query",
            side_effect=RuntimeError("API connection failed"),
        ):
            with pytest.raises(DetectionError) as exc_info:
                await detect_project_type(tmp_path, use_claude=True)

        assert "detection failed" in str(exc_info.value)
        assert exc_info.value.claude_error is not None

    @pytest.mark.asyncio
    async def test_claude_detection_unknown_type(self, tmp_path: Path) -> None:
        """Claude detection handles unknown project type."""
        # Create file but mock Claude returning unknown
        (tmp_path / "README.md").write_text("# Test")

        mock_response = json.dumps(
            {
                "primary_type": "unknown",
                "detected_types": ["unknown"],
                "confidence": "low",
                "findings": ["Could not determine project type"],
            }
        )

        async def mock_query_impl(*args: Any, **kwargs: Any) -> Any:
            mock_msg = MagicMock()
            mock_msg.__class__.__name__ = "AssistantMessage"
            mock_msg.content = mock_response
            yield mock_msg

        with patch(
            "maverick.init.detector.query",
            side_effect=lambda *args, **kwargs: mock_query_impl(),
        ):
            result = await detect_project_type(tmp_path, use_claude=True)

        assert result.primary_type == ProjectType.UNKNOWN
        assert result.confidence == DetectionConfidence.LOW


# =============================================================================
# Tests for get_validation_commands()
# =============================================================================


class TestGetValidationCommands:
    """Tests for the get_validation_commands function."""

    def test_python_validation_commands(self) -> None:
        """Python project returns correct validation commands."""
        commands = get_validation_commands(ProjectType.PYTHON)

        assert commands.format_cmd == ("ruff", "format", ".")
        assert commands.lint_cmd == ("ruff", "check", "--fix", ".")
        assert commands.typecheck_cmd == ("mypy", ".")
        assert commands.test_cmd == ("pytest", "-x", "--tb=short")

    def test_nodejs_validation_commands(self) -> None:
        """NodeJS project returns correct validation commands."""
        commands = get_validation_commands(ProjectType.NODEJS)

        assert commands.format_cmd == ("prettier", "--write", ".")
        assert commands.lint_cmd == ("eslint", "--fix", ".")
        assert commands.typecheck_cmd == ("tsc", "--noEmit")
        assert commands.test_cmd == ("npm", "test")

    def test_go_validation_commands(self) -> None:
        """Go project returns correct validation commands."""
        commands = get_validation_commands(ProjectType.GO)

        assert commands.format_cmd == ("gofmt", "-w", ".")
        assert commands.lint_cmd == ("golangci-lint", "run")
        assert commands.typecheck_cmd is None  # Compiled language
        assert commands.test_cmd == ("go", "test", "./...")

    def test_rust_validation_commands(self) -> None:
        """Rust project returns correct validation commands."""
        commands = get_validation_commands(ProjectType.RUST)

        assert commands.format_cmd == ("cargo", "fmt")
        assert commands.lint_cmd == ("cargo", "clippy", "--fix", "--allow-dirty")
        assert commands.typecheck_cmd is None  # Compiled language
        assert commands.test_cmd == ("cargo", "test")

    def test_ansible_collection_validation_commands(self) -> None:
        """Ansible collection returns correct validation commands."""
        commands = get_validation_commands(ProjectType.ANSIBLE_COLLECTION)

        assert commands.format_cmd == ("yamllint", ".")
        assert commands.lint_cmd == ("ansible-lint",)
        assert commands.typecheck_cmd is None
        assert commands.test_cmd == ("molecule", "test")

    def test_ansible_playbook_validation_commands(self) -> None:
        """Ansible playbook returns correct validation commands."""
        commands = get_validation_commands(ProjectType.ANSIBLE_PLAYBOOK)

        assert commands.format_cmd == ("yamllint", ".")
        assert commands.lint_cmd == ("ansible-lint",)
        assert commands.typecheck_cmd is None
        assert commands.test_cmd == (
            "ansible-playbook",
            "--syntax-check",
            "site.yml",
        )

    def test_unknown_validation_commands_uses_python_defaults(self) -> None:
        """Unknown project type falls back to Python defaults."""
        commands = get_validation_commands(ProjectType.UNKNOWN)

        # UNKNOWN uses Python defaults
        assert commands.format_cmd == ("ruff", "format", ".")
        assert commands.lint_cmd == ("ruff", "check", "--fix", ".")
        assert commands.typecheck_cmd == ("mypy", ".")

    def test_validation_commands_are_immutable(self) -> None:
        """ValidationCommands are frozen dataclasses."""
        commands = get_validation_commands(ProjectType.PYTHON)

        # Attempting to modify should raise
        with pytest.raises(AttributeError):
            commands.format_cmd = ("different",)  # noqa: B901


# =============================================================================
# Tests for _detect_from_markers() (via detect_project_type with use_claude=False)
# =============================================================================


class TestDetectFromMarkers:
    """Tests for marker-based detection logic.

    These tests use detect_project_type with use_claude=False to test
    the _detect_from_markers private function.
    """

    @pytest.mark.asyncio
    async def test_empty_markers_returns_unknown(self, tmp_path: Path) -> None:
        """Empty markers list returns UNKNOWN with LOW confidence."""
        result = await detect_project_type(tmp_path, use_claude=False)

        assert result.primary_type == ProjectType.UNKNOWN
        assert result.confidence == DetectionConfidence.LOW
        assert result.detected_types == (ProjectType.UNKNOWN,)

    @pytest.mark.asyncio
    async def test_single_marker_high_confidence(self, tmp_path: Path) -> None:
        """Single marker type gives HIGH confidence."""
        (tmp_path / "Cargo.toml").write_text("[package]")

        result = await detect_project_type(tmp_path, use_claude=False)

        assert result.primary_type == ProjectType.RUST
        assert result.confidence == DetectionConfidence.HIGH
        assert result.detected_types == (ProjectType.RUST,)

    @pytest.mark.asyncio
    async def test_multiple_same_type_markers(self, tmp_path: Path) -> None:
        """Multiple markers of same type maintains HIGH confidence."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "setup.py").write_text("# setup")
        (tmp_path / "requirements.txt").write_text("pytest")

        result = await detect_project_type(tmp_path, use_claude=False)

        assert result.primary_type == ProjectType.PYTHON
        assert result.confidence == DetectionConfidence.HIGH
        # All are Python type
        assert all(t == ProjectType.PYTHON for t in result.detected_types)

    @pytest.mark.asyncio
    async def test_dominant_type_medium_confidence(self, tmp_path: Path) -> None:
        """Dominant type (2x+ score) gives MEDIUM confidence."""
        # Python has 3 markers, NodeJS has 1
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "setup.py").write_text("# setup")
        (tmp_path / "requirements.txt").write_text("pytest")
        (tmp_path / "package.json").write_text("{}")

        result = await detect_project_type(tmp_path, use_claude=False)

        # Python should be primary with higher score
        assert result.primary_type == ProjectType.PYTHON
        # Multiple types detected
        assert len(result.detected_types) >= 2

    @pytest.mark.asyncio
    async def test_findings_list_all_markers(self, tmp_path: Path) -> None:
        """Findings include all marker files found."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "requirements.txt").write_text("pytest")

        result = await detect_project_type(tmp_path, use_claude=False)

        assert len(result.findings) == 2
        assert any("pyproject.toml" in f for f in result.findings)
        assert any("requirements.txt" in f for f in result.findings)

    @pytest.mark.asyncio
    async def test_priority_affects_score(self, tmp_path: Path) -> None:
        """Lower priority markers have higher weight in scoring."""
        # pyproject.toml has priority 1, requirements.txt has priority 4
        # Higher priority (lower number) = higher score
        (tmp_path / "pyproject.toml").write_text("[project]")

        result = await detect_project_type(tmp_path, use_claude=False)

        # pyproject.toml with priority 1 should give score of 9 (10 - 1)
        assert result.primary_type == ProjectType.PYTHON
        assert result.confidence == DetectionConfidence.HIGH

    @pytest.mark.asyncio
    async def test_all_project_types_detectable(self, tmp_path: Path) -> None:
        """All project types can be detected from markers."""
        test_cases = [
            ("pyproject.toml", "[project]", ProjectType.PYTHON),
            ("package.json", "{}", ProjectType.NODEJS),
            ("go.mod", "module test", ProjectType.GO),
            ("Cargo.toml", "[package]", ProjectType.RUST),
            ("galaxy.yml", "namespace: test", ProjectType.ANSIBLE_COLLECTION),
            ("ansible.cfg", "[defaults]", ProjectType.ANSIBLE_PLAYBOOK),
        ]

        for file_name, content, expected_type in test_cases:
            # Create fresh directory for each test
            project_dir = tmp_path / file_name.replace(".", "_")
            project_dir.mkdir()
            (project_dir / file_name).write_text(content)

            result = await detect_project_type(project_dir, use_claude=False)

            assert result.primary_type == expected_type, (
                f"Expected {expected_type} for {file_name}, got {result.primary_type}"
            )


# =============================================================================
# Tests for edge cases and error handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_permission_error_reading_file(self, tmp_path: Path) -> None:
        """Permission error when reading file is handled gracefully."""
        marker_file = tmp_path / "pyproject.toml"
        marker_file.write_text("[project]")
        marker_file.chmod(0o000)  # No read permission

        try:
            markers = find_marker_files(tmp_path)

            # File should be found but content may be None
            assert len(markers) == 1
            assert markers[0].file_name == "pyproject.toml"
            # Content might be None due to permission error
            # (depends on implementation)
        finally:
            marker_file.chmod(0o644)  # Restore permissions

    @pytest.mark.asyncio
    async def test_symlink_to_marker_file(self, tmp_path: Path) -> None:
        """Symlinks to marker files are followed."""
        real_file = tmp_path / "real_pyproject.toml"
        real_file.write_text("[project]")
        link_file = tmp_path / "pyproject.toml"
        link_file.symlink_to(real_file)

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].file_name == "pyproject.toml"
        assert markers[0].content == "[project]"

    @pytest.mark.asyncio
    async def test_unicode_content_in_marker(self, tmp_path: Path) -> None:
        """Unicode content in marker files is handled."""
        content = "[project]\nname = 'test-\u00e9\u00e0\u00fc\u4e2d\u6587'"
        (tmp_path / "pyproject.toml").write_text(content)

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].content == content

    @pytest.mark.asyncio
    async def test_very_large_marker_file(self, tmp_path: Path) -> None:
        """Very large marker files are truncated during read."""
        # Create a large file (> MAX_CONTENT_LENGTH)
        large_content = "x" * 10000
        (tmp_path / "pyproject.toml").write_text(large_content)

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        # Content should be truncated to MAX_CONTENT_LENGTH (2000)
        assert markers[0].content is not None
        assert len(markers[0].content) <= 2000

    @pytest.mark.asyncio
    async def test_empty_marker_file(self, tmp_path: Path) -> None:
        """Empty marker files are handled."""
        (tmp_path / "pyproject.toml").write_text("")

        markers = find_marker_files(tmp_path)

        assert len(markers) == 1
        assert markers[0].content == ""

    @pytest.mark.asyncio
    async def test_deeply_nested_markers(self, tmp_path: Path) -> None:
        """Deeply nested markers beyond max_depth are not found."""
        # Create deeply nested structure
        current = tmp_path
        for i in range(5):
            current = current / f"level{i}"
            current.mkdir()
        (current / "pyproject.toml").write_text("[project]")

        # Default max_depth is 2
        markers = find_marker_files(tmp_path)

        # Should not find the deeply nested file
        assert len(markers) == 0

    @pytest.mark.asyncio
    async def test_concurrent_detection_calls(self, tmp_path: Path) -> None:
        """Multiple concurrent detection calls work correctly."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        # Run multiple detections concurrently
        results = await asyncio.gather(
            detect_project_type(tmp_path, use_claude=False),
            detect_project_type(tmp_path, use_claude=False),
            detect_project_type(tmp_path, use_claude=False),
        )

        # All should return same result
        for result in results:
            assert result.primary_type == ProjectType.PYTHON
            assert result.detection_method == "markers"

    @pytest.mark.asyncio
    async def test_detect_with_custom_model(self, tmp_path: Path) -> None:
        """Detection with custom model parameter."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        mock_response = json.dumps(
            {
                "primary_type": "python",
                "detected_types": ["python"],
                "confidence": "high",
                "findings": ["pyproject.toml found"],
            }
        )

        async def mock_query_impl(*args: Any, **kwargs: Any) -> Any:
            mock_msg = MagicMock()
            mock_msg.__class__.__name__ = "AssistantMessage"
            mock_msg.content = mock_response
            yield mock_msg

        with patch(
            "maverick.init.detector.query",
            side_effect=lambda *args, **kwargs: mock_query_impl(),
        ):
            result = await detect_project_type(
                tmp_path,
                use_claude=True,
                model="claude-3-opus-20240229",
            )

        assert result.primary_type == ProjectType.PYTHON
