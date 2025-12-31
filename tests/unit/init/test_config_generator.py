"""Tests for config_generator module."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.exceptions.init import ConfigExistsError, ConfigWriteError
from maverick.init.config_generator import generate_config, write_config
from maverick.init.models import (
    DetectionConfidence,
    GitRemoteInfo,
    InitConfig,
    ProjectDetectionResult,
    ProjectType,
)


class TestGenerateConfig:
    """Tests for generate_config function."""

    def test_generate_config_with_detection(self) -> None:
        """Generate config using detection result."""
        git_info = GitRemoteInfo(owner="acme", repo="project")
        detection = ProjectDetectionResult(
            primary_type=ProjectType.PYTHON,
            confidence=DetectionConfidence.HIGH,
        )

        config = generate_config(git_info=git_info, detection=detection)

        # Verify GitHub config from git_info
        assert config.github.owner == "acme"
        assert config.github.repo == "project"
        assert config.github.default_branch == "main"

        # Verify validation config uses Python defaults
        assert config.validation.format_cmd == ["ruff", "format", "."]
        assert config.validation.lint_cmd == ["ruff", "check", "--fix", "."]
        assert config.validation.typecheck_cmd == ["mypy", "."]
        assert config.validation.test_cmd == ["pytest", "-x", "--tb=short"]

    def test_generate_config_with_explicit_project_type(self) -> None:
        """Explicit project_type overrides detection.primary_type."""
        git_info = GitRemoteInfo(owner="acme", repo="project")
        detection = ProjectDetectionResult(
            primary_type=ProjectType.PYTHON,
            confidence=DetectionConfidence.HIGH,
        )

        # Override with NodeJS
        config = generate_config(
            git_info=git_info,
            detection=detection,
            project_type=ProjectType.NODEJS,
        )

        # Verify NodeJS validation commands are used
        assert config.validation.format_cmd == ["prettier", "--write", "."]
        assert config.validation.lint_cmd == ["eslint", "--fix", "."]
        assert config.validation.typecheck_cmd == ["tsc", "--noEmit"]
        assert config.validation.test_cmd == ["npm", "test"]

    def test_generate_config_no_detection_no_type_uses_python_defaults(self) -> None:
        """When detection and project_type are None, use Python defaults."""
        git_info = GitRemoteInfo(owner="acme", repo="project")

        config = generate_config(git_info=git_info, detection=None)

        # Verify Python defaults are used
        assert config.validation.format_cmd == ["ruff", "format", "."]
        assert config.validation.lint_cmd == ["ruff", "check", "--fix", "."]
        assert config.validation.typecheck_cmd == ["mypy", "."]
        assert config.validation.test_cmd == ["pytest", "-x", "--tb=short"]

    def test_generate_config_no_detection_with_type(self) -> None:
        """When detection is None but type is provided, use that type."""
        git_info = GitRemoteInfo(owner="acme", repo="project")

        config = generate_config(
            git_info=git_info,
            detection=None,
            project_type=ProjectType.RUST,
        )

        # Verify Rust validation commands are used
        assert config.validation.format_cmd == ["cargo", "fmt"]
        expected_lint = ["cargo", "clippy", "--fix", "--allow-dirty"]
        assert config.validation.lint_cmd == expected_lint
        assert config.validation.typecheck_cmd is None  # Compiled language
        assert config.validation.test_cmd == ["cargo", "test"]

    def test_generate_config_empty_git_info(self) -> None:
        """Handle GitRemoteInfo with no owner/repo."""
        git_info = GitRemoteInfo()
        detection = ProjectDetectionResult(
            primary_type=ProjectType.PYTHON,
            confidence=DetectionConfidence.HIGH,
        )

        config = generate_config(git_info=git_info, detection=detection)

        assert config.github.owner is None
        assert config.github.repo is None
        assert config.github.default_branch == "main"

    def test_generate_config_go_project(self) -> None:
        """Generate config for Go project."""
        git_info = GitRemoteInfo(owner="acme", repo="goproject")
        detection = ProjectDetectionResult(
            primary_type=ProjectType.GO,
            confidence=DetectionConfidence.HIGH,
        )

        config = generate_config(git_info=git_info, detection=detection)

        assert config.validation.format_cmd == ["gofmt", "-w", "."]
        assert config.validation.lint_cmd == ["golangci-lint", "run"]
        assert config.validation.typecheck_cmd is None  # Compiled language
        assert config.validation.test_cmd == ["go", "test", "./..."]

    def test_generate_config_ansible_collection(self) -> None:
        """Generate config for Ansible collection."""
        git_info = GitRemoteInfo(owner="acme", repo="ansible-collection")
        detection = ProjectDetectionResult(
            primary_type=ProjectType.ANSIBLE_COLLECTION,
            confidence=DetectionConfidence.HIGH,
        )

        config = generate_config(git_info=git_info, detection=detection)

        assert config.validation.format_cmd == ["yamllint", "."]
        assert config.validation.lint_cmd == ["ansible-lint"]
        assert config.validation.typecheck_cmd is None
        assert config.validation.test_cmd == ["molecule", "test"]

    def test_generate_config_unknown_type_uses_python_defaults(self) -> None:
        """Unknown project type falls back to Python defaults."""
        git_info = GitRemoteInfo(owner="acme", repo="unknown")
        detection = ProjectDetectionResult(
            primary_type=ProjectType.UNKNOWN,
            confidence=DetectionConfidence.LOW,
        )

        config = generate_config(git_info=git_info, detection=detection)

        # UNKNOWN falls back to Python defaults
        assert config.validation.format_cmd == ["ruff", "format", "."]
        assert config.validation.lint_cmd == ["ruff", "check", "--fix", "."]

    def test_generate_config_model_defaults(self) -> None:
        """Verify model config has expected defaults."""
        git_info = GitRemoteInfo()

        config = generate_config(git_info=git_info, detection=None)

        assert config.model.model_id == "claude-sonnet-4-5-20250929"
        assert config.model.max_tokens == 64000
        assert config.model.temperature == 0.0

    def test_generate_config_to_yaml(self) -> None:
        """Generated config should serialize to valid YAML."""
        git_info = GitRemoteInfo(owner="test", repo="repo")
        detection = ProjectDetectionResult(
            primary_type=ProjectType.PYTHON,
            confidence=DetectionConfidence.HIGH,
        )

        config = generate_config(git_info=git_info, detection=detection)
        yaml_output = config.to_yaml()

        # Verify YAML contains expected sections
        assert "github:" in yaml_output
        assert "owner: test" in yaml_output
        assert "repo: repo" in yaml_output
        assert "validation:" in yaml_output
        assert "model:" in yaml_output


class TestWriteConfig:
    """Tests for write_config function."""

    def test_write_config_creates_file(self, tmp_path: Path) -> None:
        """write_config creates file with correct content."""
        config = InitConfig()
        output_path = tmp_path / "maverick.yaml"

        write_config(config, output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert "github:" in content
        assert "validation:" in content
        assert "model:" in content

    def test_write_config_raises_if_exists(self, tmp_path: Path) -> None:
        """write_config raises ConfigExistsError if file exists and force=False."""
        config = InitConfig()
        output_path = tmp_path / "maverick.yaml"
        output_path.write_text("existing content")

        with pytest.raises(ConfigExistsError) as exc_info:
            write_config(config, output_path, force=False)

        assert exc_info.value.config_path == output_path

    def test_write_config_force_overwrites(self, tmp_path: Path) -> None:
        """write_config with force=True overwrites existing file."""
        config = InitConfig()
        output_path = tmp_path / "maverick.yaml"
        output_path.write_text("existing content")

        write_config(config, output_path, force=True)

        content = output_path.read_text()
        assert "existing content" not in content
        assert "github:" in content

    def test_write_config_io_error_raises_config_write_error(
        self, tmp_path: Path
    ) -> None:
        """write_config raises ConfigWriteError on I/O errors."""
        config = InitConfig()
        # Use a path that cannot be written (directory)
        output_path = tmp_path / "subdir"
        output_path.mkdir()

        with pytest.raises(ConfigWriteError) as exc_info:
            write_config(config, output_path, force=True)

        assert exc_info.value.config_path == output_path
        assert exc_info.value.cause is not None

    def test_write_config_permission_error(self, tmp_path: Path) -> None:
        """write_config raises ConfigWriteError on permission errors."""
        config = InitConfig()
        output_path = tmp_path / "readonly.yaml"
        output_path.write_text("readonly")
        output_path.chmod(0o444)  # Read-only

        try:
            with pytest.raises(ConfigWriteError) as exc_info:
                write_config(config, output_path, force=True)

            assert exc_info.value.config_path == output_path
        finally:
            # Restore permissions for cleanup
            output_path.chmod(0o644)
