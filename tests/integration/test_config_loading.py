from __future__ import annotations

import os
from pathlib import Path

import pytest


class TestConfigLoadingIntegration:
    """Integration tests for the full configuration loading flow."""

    def test_full_config_hierarchy(
        self,
        clean_env: None,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test complete config hierarchy: defaults -> user -> project -> env."""
        os.chdir(temp_dir)

        # 1. Create user config (some values)
        user_config_dir = temp_dir / ".config" / "maverick"
        user_config_dir.mkdir(parents=True)
        user_config_path = user_config_dir / "config.yaml"
        user_config_path.write_text("""
github:
  owner: "user-level-org"
notifications:
  server: "https://user-ntfy.example.com"
model:
  max_tokens: 2048
  temperature: 0.1
verbosity: "info"
""")

        # 2. Create project config (overrides some user values)
        project_config_path = temp_dir / "maverick.yaml"
        project_config_path.write_text("""
github:
  owner: "project-level-org"
  repo: "my-repo"
model:
  max_tokens: 4096
""")

        # 3. Set environment variables (highest priority)
        os.environ["MAVERICK_MODEL__MAX_TOKENS"] = "8192"

        # Patch home directory
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        from maverick.config import load_config

        config = load_config()

        # Verify hierarchy:
        # - github.owner: project overrides user -> "project-level-org"
        assert config.github.owner == "project-level-org"
        # - github.repo: only in project -> "my-repo"
        assert config.github.repo == "my-repo"
        # - notifications.server: only in user -> "https://user-ntfy.example.com"
        assert config.notifications.server == "https://user-ntfy.example.com"
        # - model.max_tokens: env overrides project -> 8192
        assert config.model.max_tokens == 8192
        # - model.temperature: only in user -> 0.1
        assert config.model.temperature == 0.1
        # - verbosity: only in user -> "info"
        assert config.verbosity == "info"
        # - parallel.max_agents: default -> 3
        assert config.parallel.max_agents == 3

    def test_defaults_only(
        self, clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that defaults work when no config files exist."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        from maverick.config import MaverickConfig, load_config

        config = load_config()

        # All defaults should be applied
        assert isinstance(config, MaverickConfig)
        assert config.github.owner is None
        assert config.github.default_branch == "main"
        assert config.notifications.enabled is False
        assert config.model.model_id == "claude-sonnet-4-5-20250929"
        assert config.model.max_tokens == 64000
        assert config.parallel.max_agents == 3
        assert config.verbosity == "warning"


class TestStepConfigFromYaml:
    """Integration tests for step config loaded from workflow YAML."""

    def test_workflow_with_step_config(self) -> None:
        """Workflow YAML with config field loads correctly."""
        from maverick.dsl.serialization.schema import WorkflowFile

        yaml_content = """
version: "1.0"
name: test-config
steps:
  - name: review
    type: agent
    agent: reviewer
    config:
      mode: agent
      autonomy: consultant
      temperature: 0.3
      prompt_suffix: "Focus on performance"
"""
        workflow = WorkflowFile.from_yaml(yaml_content)
        step = workflow.steps[0]
        assert step.config is not None
        assert step.config["mode"] == "agent"
        assert step.config["autonomy"] == "consultant"
        assert step.config["temperature"] == 0.3
        assert step.config["prompt_suffix"] == "Focus on performance"

    def test_workflow_with_prompt_file_config(self) -> None:
        """Workflow YAML with prompt_file loads correctly."""
        from maverick.dsl.serialization.schema import WorkflowFile

        yaml_content = """
version: "1.0"
name: test-prompt-file
steps:
  - name: review
    type: agent
    agent: reviewer
    config:
      prompt_file: "./prompts/security.md"
"""
        workflow = WorkflowFile.from_yaml(yaml_content)
        step = workflow.steps[0]
        assert step.config == {"prompt_file": "./prompts/security.md"}

    def test_workflow_with_legacy_executor_config(self) -> None:
        """Legacy executor_config still works with deprecation."""
        from maverick.dsl.serialization.schema import WorkflowFile

        yaml_content = """
version: "1.0"
name: test-legacy
steps:
  - name: implement
    type: agent
    agent: implementer
    executor_config:
      timeout: 600
      model: claude-opus-4-6
"""
        workflow = WorkflowFile.from_yaml(yaml_content)
        step = workflow.steps[0]
        # executor_config should be migrated to config with model→model_id
        assert step.config is not None
        assert step.config["timeout"] == 600
        assert step.config["model_id"] == "claude-opus-4-6"
        assert "model" not in step.config

    def test_workflow_with_deterministic_step_config(self) -> None:
        """Deterministic step (python type) can have config with timeout."""
        from maverick.dsl.serialization.schema import WorkflowFile

        yaml_content = """
version: "1.0"
name: test-deterministic
steps:
  - name: lint
    type: python
    action: run_linter
    config:
      timeout: 60
"""
        workflow = WorkflowFile.from_yaml(yaml_content)
        step = workflow.steps[0]
        assert step.config == {"timeout": 60}


class TestFourLayerStepConfigResolution:
    """Integration test: full 4-layer step config resolution."""

    def test_full_four_layer_resolution(
        self,
        clean_env: None,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify inline > project steps > agent config > global model precedence."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Create maverick.yaml with model, agents, and steps
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text("""
model:
  model_id: global-model
  temperature: 0.1
  max_tokens: 4000

agents:
  reviewer:
    model_id: agent-model
    temperature: 0.3

steps:
  review_code:
    autonomy: consultant
    timeout: 300
    temperature: 0.5
""")

        from maverick.config import load_config
        from maverick.dsl.executor.config import resolve_step_config
        from maverick.dsl.types import AutonomyLevel, StepMode, StepType

        config = load_config()

        # Resolve with inline override for temperature
        result = resolve_step_config(
            inline_config={"temperature": 0.9},
            project_step_config=config.steps.get("review_code"),
            agent_config=config.agents.get("reviewer"),
            global_model=config.model,
            step_type=StepType.AGENT,
            step_name="review_code",
        )

        # Verify 4-layer precedence:
        assert (
            result.temperature == 0.9
        )  # inline wins (over project 0.5, agent 0.3, global 0.1)
        assert result.autonomy == AutonomyLevel.CONSULTANT  # from project steps
        assert result.timeout == 300  # from project steps
        assert result.model_id == "agent-model"  # agent (project steps had no model_id)
        assert result.max_tokens == 4000  # from global
        assert result.mode == StepMode.AGENT  # inferred from step_type
        assert result.provider == "claude"  # default

    def test_no_project_steps_falls_through(
        self,
        clean_env: None,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no project steps exist, resolution still works."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        config_path = temp_dir / "maverick.yaml"
        config_path.write_text("""
model:
  model_id: global-model
  temperature: 0.2
""")

        from maverick.config import load_config
        from maverick.dsl.executor.config import resolve_step_config
        from maverick.dsl.types import StepType

        config = load_config()

        result = resolve_step_config(
            inline_config=None,
            project_step_config=config.steps.get("nonexistent_step"),
            agent_config=None,
            global_model=config.model,
            step_type=StepType.AGENT,
            step_name="some_step",
        )

        assert result.model_id == "global-model"
        assert result.temperature == 0.2
