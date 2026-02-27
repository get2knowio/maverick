"""Tests for validate_prompt_config() — T016."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.prompts.config import PromptOverrideConfig
from maverick.prompts.models import (
    GENERIC_PROVIDER,
    OverridePolicy,
    PromptConfigError,
    PromptEntry,
)
from maverick.prompts.registry import PromptRegistry


@pytest.fixture()
def validation_registry() -> PromptRegistry:
    """Registry for validation testing."""
    return PromptRegistry(
        {
            ("implement", GENERIC_PROVIDER): PromptEntry(
                text="Implement code.",
                policy=OverridePolicy.AUGMENT_ONLY,
            ),
            ("pr_description", GENERIC_PROVIDER): PromptEntry(
                text="Generate PR description.",
                policy=OverridePolicy.REPLACE,
            ),
        }
    )


class TestValidatePromptConfig:
    """Tests for validate_prompt_config()."""

    def test_unknown_step_raises_error(
        self, validation_registry: PromptRegistry, tmp_path: Path
    ) -> None:
        from maverick.prompts.validation import validate_prompt_config

        prompts = {
            "nonexistent_step": PromptOverrideConfig(prompt_suffix="test"),
        }
        with pytest.raises(PromptConfigError, match="not a registered step"):
            validate_prompt_config(prompts, validation_registry, project_root=tmp_path)

    def test_policy_violation_raises_error(
        self, validation_registry: PromptRegistry, tmp_path: Path
    ) -> None:
        from maverick.prompts.validation import validate_prompt_config

        prompts = {
            "implement": PromptOverrideConfig(prompt_file="custom.md"),
        }
        with pytest.raises(
            PromptConfigError, match="does not allow full prompt replacement"
        ):
            validate_prompt_config(prompts, validation_registry, project_root=tmp_path)

    def test_missing_prompt_file_raises_error(
        self, validation_registry: PromptRegistry, tmp_path: Path
    ) -> None:
        from maverick.prompts.validation import validate_prompt_config

        prompts = {
            "pr_description": PromptOverrideConfig(prompt_file="nonexistent.md"),
        }
        with pytest.raises(PromptConfigError, match="Prompt file not found"):
            validate_prompt_config(prompts, validation_registry, project_root=tmp_path)

    def test_absolute_path_rejected(
        self, validation_registry: PromptRegistry, tmp_path: Path
    ) -> None:
        from maverick.prompts.validation import validate_prompt_config

        prompts = {
            "pr_description": PromptOverrideConfig(prompt_file="/etc/passwd"),
        }
        with pytest.raises(PromptConfigError, match="Absolute paths are not allowed"):
            validate_prompt_config(prompts, validation_registry, project_root=tmp_path)

    def test_traversal_outside_root_rejected(
        self, validation_registry: PromptRegistry, tmp_path: Path
    ) -> None:
        from maverick.prompts.validation import validate_prompt_config

        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "evil.md").write_text("evil")
        project_root = tmp_path / "project"
        project_root.mkdir()
        prompts = {
            "pr_description": PromptOverrideConfig(prompt_file="../outside/evil.md"),
        }
        with pytest.raises(PromptConfigError, match="must be within project root"):
            validate_prompt_config(
                prompts, validation_registry, project_root=project_root
            )

    def test_valid_config_passes(
        self, validation_registry: PromptRegistry, tmp_path: Path
    ) -> None:
        from maverick.prompts.validation import validate_prompt_config

        (tmp_path / "custom-pr.md").write_text("Custom prompt")
        prompts = {
            "implement": PromptOverrideConfig(prompt_suffix="Use snake_case."),
            "pr_description": PromptOverrideConfig(prompt_file="custom-pr.md"),
        }
        validate_prompt_config(prompts, validation_registry, project_root=tmp_path)

    def test_empty_config_passes(
        self, validation_registry: PromptRegistry, tmp_path: Path
    ) -> None:
        from maverick.prompts.validation import validate_prompt_config

        validate_prompt_config({}, validation_registry, project_root=tmp_path)
