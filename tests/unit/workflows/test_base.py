"""Unit tests for WorkflowDSLMixin base class.

Tests the common DSL integration utilities used by workflow implementations.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.runners.preflight import (
    PreflightConfig,
    PreflightResult,
    ValidationResult,
)
from maverick.runners.protocols import ValidatableRunner
from maverick.workflows.base import WorkflowDSLMixin


class TestWorkflowDSLMixin:
    """Tests for WorkflowDSLMixin."""

    def test_init_sets_use_dsl_to_false(self) -> None:
        """Test __init__ initializes _use_dsl to False."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            """Concrete implementation for testing."""

            pass

        workflow = ConcreteWorkflow()

        assert hasattr(workflow, "_use_dsl")
        assert workflow._use_dsl is False

    def test_enable_dsl_execution_sets_flag(self) -> None:
        """Test enable_dsl_execution sets _use_dsl to True."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            """Concrete implementation for testing."""

            pass

        workflow = ConcreteWorkflow()

        assert workflow._use_dsl is False

        workflow.enable_dsl_execution()

        assert workflow._use_dsl is True

    def test_load_workflow_calls_builtin_library(self) -> None:
        """Test _load_workflow uses builtin library to load workflow."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            """Concrete implementation for testing."""

            pass

        workflow = ConcreteWorkflow()

        # Mock the builtin library
        mock_library = MagicMock()
        mock_workflow_file = MagicMock()
        mock_workflow_file.name = "test-workflow"
        mock_library.get_workflow.return_value = mock_workflow_file

        with patch(
            "maverick.workflows.base.create_builtin_library", return_value=mock_library
        ):
            result = workflow._load_workflow("test-workflow")

        # Verify library was called correctly
        mock_library.get_workflow.assert_called_once_with("test-workflow")
        assert result == mock_workflow_file

    def test_load_workflow_raises_on_missing_workflow(self) -> None:
        """Test _load_workflow raises KeyError for non-existent workflow."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            """Concrete implementation for testing."""

            pass

        workflow = ConcreteWorkflow()

        # Mock the builtin library to raise KeyError
        mock_library = MagicMock()
        mock_library.get_workflow.side_effect = KeyError("Workflow not found")

        with (
            patch(
                "maverick.workflows.base.create_builtin_library",
                return_value=mock_library,
            ),
            pytest.raises(KeyError, match="Workflow not found"),
        ):
            workflow._load_workflow("non-existent")

    def test_mixin_works_with_inheritance_chain(self) -> None:
        """Test mixin works correctly in an inheritance chain."""

        class BaseWorkflow:
            """Base workflow class."""

            def __init__(self) -> None:
                self.base_attr = "base"

        class ConcreteWorkflow(WorkflowDSLMixin, BaseWorkflow):
            """Concrete implementation with multiple inheritance."""

            def __init__(self) -> None:
                super().__init__()
                self.concrete_attr = "concrete"

        workflow = ConcreteWorkflow()

        # Verify all attributes exist
        assert hasattr(workflow, "_use_dsl")
        assert hasattr(workflow, "base_attr")
        assert hasattr(workflow, "concrete_attr")

        # Verify mixin methods work
        assert workflow._use_dsl is False
        workflow.enable_dsl_execution()
        assert workflow._use_dsl is True


class TestWorkflowDSLMixinDiscoverRunners:
    """Tests for WorkflowDSLMixin._discover_runners()."""

    def test_discover_runners_finds_public_runners(self) -> None:
        """Test _discover_runners finds public runner attributes."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            def __init__(self) -> None:
                super().__init__()
                self.git_runner = self._create_mock_runner("git_runner")
                self.github_runner = self._create_mock_runner("github_runner")

            def _create_mock_runner(self, name: str) -> MagicMock:
                runner = MagicMock(spec=ValidatableRunner)
                runner.__class__.__name__ = name
                runner.validate = AsyncMock(
                    return_value=ValidationResult(success=True, component=name)
                )
                return runner

        workflow = ConcreteWorkflow()
        runners = workflow._discover_runners()

        assert len(runners) == 2
        assert workflow.git_runner in runners
        assert workflow.github_runner in runners

    def test_discover_runners_finds_private_runner_attributes(self) -> None:
        """Test _discover_runners finds private _*_runner attributes."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            def __init__(self) -> None:
                super().__init__()
                self._git_runner = self._create_mock_runner("git_runner")
                self._validation_runner = self._create_mock_runner(
                    "validation_runner")

            def _create_mock_runner(self, name: str) -> MagicMock:
                runner = MagicMock(spec=ValidatableRunner)
                runner.__class__.__name__ = name
                runner.validate = AsyncMock(
                    return_value=ValidationResult(success=True, component=name)
                )
                return runner

        workflow = ConcreteWorkflow()
        runners = workflow._discover_runners()

        assert len(runners) == 2
        assert workflow._git_runner in runners
        assert workflow._validation_runner in runners

    def test_discover_runners_ignores_non_runner_attributes(self) -> None:
        """Test _discover_runners ignores attributes without validate()."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            def __init__(self) -> None:
                super().__init__()
                self.config = {"key": "value"}  # Not a runner
                self.name = "workflow"  # Not a runner
                self.git_runner = self._create_mock_runner("git_runner")

            def _create_mock_runner(self, name: str) -> MagicMock:
                runner = MagicMock(spec=ValidatableRunner)
                runner.__class__.__name__ = name
                runner.validate = AsyncMock(
                    return_value=ValidationResult(success=True, component=name)
                )
                return runner

        workflow = ConcreteWorkflow()
        runners = workflow._discover_runners()

        assert len(runners) == 1
        assert workflow.git_runner in runners

    def test_discover_runners_skips_none_attributes(self) -> None:
        """Test _discover_runners skips None runner attributes."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            def __init__(self) -> None:
                super().__init__()
                self.git_runner = None  # Not set
                self.github_runner = self._create_mock_runner("github_runner")

            def _create_mock_runner(self, name: str) -> MagicMock:
                runner = MagicMock(spec=ValidatableRunner)
                runner.__class__.__name__ = name
                runner.validate = AsyncMock(
                    return_value=ValidationResult(success=True, component=name)
                )
                return runner

        workflow = ConcreteWorkflow()
        runners = workflow._discover_runners()

        assert len(runners) == 1
        assert workflow.github_runner in runners

    def test_discover_runners_avoids_duplicates(self) -> None:
        """Test _discover_runners avoids duplicate runners."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            def __init__(self) -> None:
                super().__init__()
                runner = self._create_mock_runner("shared_runner")
                # Same object via different names
                self.git_runner = runner
                self.alias_runner = runner

            def _create_mock_runner(self, name: str) -> MagicMock:
                runner = MagicMock(spec=ValidatableRunner)
                runner.__class__.__name__ = name
                runner.validate = AsyncMock(
                    return_value=ValidationResult(success=True, component=name)
                )
                return runner

        workflow = ConcreteWorkflow()
        runners = workflow._discover_runners()

        # Should only find one unique runner
        assert len(runners) == 1


class TestWorkflowDSLMixinRunPreflight:
    """Tests for WorkflowDSLMixin.run_preflight()."""

    @pytest.fixture
    def mock_runner(self) -> MagicMock:
        """Create a mock runner that passes validation."""
        runner = MagicMock(spec=ValidatableRunner)
        runner.__class__.__name__ = "MockRunner"
        runner.validate = AsyncMock(
            return_value=ValidationResult(
                success=True,
                component="MockRunner",
                duration_ms=50,
            )
        )
        return runner

    @pytest.fixture
    def failing_runner(self) -> MagicMock:
        """Create a mock runner that fails validation."""
        runner = MagicMock(spec=ValidatableRunner)
        runner.__class__.__name__ = "FailingRunner"
        runner.validate = AsyncMock(
            return_value=ValidationResult(
                success=False,
                component="FailingRunner",
                errors=("Validation failed",),
                duration_ms=30,
            )
        )
        return runner

    @pytest.mark.asyncio
    async def test_run_preflight_with_provided_runners(
        self, mock_runner: MagicMock
    ) -> None:
        """Test run_preflight uses provided runners."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            pass

        workflow = ConcreteWorkflow()

        # Patch config loading to avoid filesystem access
        with patch.object(
            workflow,
            "_load_preflight_config",
            return_value=MagicMock(
                timeout_per_check=5.0,
                fail_on_warning=False,
                custom_tools=[],
            ),
        ):
            result = await workflow.run_preflight(
                runners=[mock_runner],
                include_custom_tools=False,
            )

        assert result.success is True
        assert len(result.results) == 1
        mock_runner.validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_preflight_discovers_runners_when_none_provided(self) -> None:
        """Test run_preflight discovers runners from workflow attributes."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            def __init__(self) -> None:
                super().__init__()
                runner = MagicMock(spec=ValidatableRunner)
                runner.__class__.__name__ = "DiscoveredRunner"
                runner.validate = AsyncMock(
                    return_value=ValidationResult(
                        success=True,
                        component="DiscoveredRunner",
                        duration_ms=40,
                    )
                )
                self.discovered_runner = runner

        workflow = ConcreteWorkflow()

        with patch.object(
            workflow,
            "_load_preflight_config",
            return_value=MagicMock(
                timeout_per_check=5.0,
                fail_on_warning=False,
                custom_tools=[],
            ),
        ):
            result = await workflow.run_preflight(include_custom_tools=False)

        assert result.success is True
        assert len(result.results) == 1
        workflow.discovered_runner.validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_preflight_raises_on_failure(
        self, failing_runner: MagicMock
    ) -> None:
        """Test run_preflight raises PreflightValidationError on failure."""
        from maverick.exceptions import PreflightValidationError

        class ConcreteWorkflow(WorkflowDSLMixin):
            pass

        workflow = ConcreteWorkflow()

        with patch.object(
            workflow,
            "_load_preflight_config",
            return_value=MagicMock(
                timeout_per_check=5.0,
                fail_on_warning=False,
                custom_tools=[],
            ),
        ):
            with pytest.raises(PreflightValidationError) as exc_info:
                await workflow.run_preflight(
                    runners=[failing_runner],
                    include_custom_tools=False,
                )

        assert "FailingRunner" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_preflight_uses_custom_timeout(
        self, mock_runner: MagicMock
    ) -> None:
        """Test run_preflight uses provided timeout."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            pass

        workflow = ConcreteWorkflow()

        with patch.object(
            workflow,
            "_load_preflight_config",
            return_value=MagicMock(
                timeout_per_check=5.0,
                fail_on_warning=False,
                custom_tools=[],
            ),
        ):
            result = await workflow.run_preflight(
                runners=[mock_runner],
                timeout_per_check=1.0,
                include_custom_tools=False,
            )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_run_preflight_with_no_runners_succeeds(self) -> None:
        """Test run_preflight with no runners returns success."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            pass

        workflow = ConcreteWorkflow()

        with patch.object(
            workflow,
            "_load_preflight_config",
            return_value=MagicMock(
                timeout_per_check=5.0,
                fail_on_warning=False,
                custom_tools=[],
            ),
        ):
            result = await workflow.run_preflight(
                runners=[],
                include_custom_tools=False,
            )

        assert result.success is True
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_run_preflight_aggregates_multiple_failures(self) -> None:
        """Test run_preflight aggregates all failures."""
        from maverick.exceptions import PreflightValidationError

        failing1 = MagicMock(spec=ValidatableRunner)
        failing1.__class__.__name__ = "FailingRunner1"
        failing1.validate = AsyncMock(
            return_value=ValidationResult(
                success=False,
                component="FailingRunner1",
                errors=("Error 1",),
                duration_ms=10,
            )
        )

        failing2 = MagicMock(spec=ValidatableRunner)
        failing2.__class__.__name__ = "FailingRunner2"
        failing2.validate = AsyncMock(
            return_value=ValidationResult(
                success=False,
                component="FailingRunner2",
                errors=("Error 2",),
                duration_ms=20,
            )
        )

        class ConcreteWorkflow(WorkflowDSLMixin):
            pass

        workflow = ConcreteWorkflow()

        with patch.object(
            workflow,
            "_load_preflight_config",
            return_value=MagicMock(
                timeout_per_check=5.0,
                fail_on_warning=False,
                custom_tools=[],
            ),
        ):
            with pytest.raises(PreflightValidationError) as exc_info:
                await workflow.run_preflight(
                    runners=[failing1, failing2],
                    include_custom_tools=False,
                )

        # Both errors should be in exception message
        error_msg = str(exc_info.value)
        assert "FailingRunner1" in error_msg
        assert "FailingRunner2" in error_msg

    @pytest.mark.asyncio
    async def test_run_preflight_includes_custom_tools_when_enabled(self) -> None:
        """Test run_preflight includes custom tools from config."""
        from maverick.config import CustomToolConfig

        class ConcreteWorkflow(WorkflowDSLMixin):
            pass

        workflow = ConcreteWorkflow()

        custom_tool = CustomToolConfig(
            name="pytest",
            command="pytest",
            required=False,
            hint="Install with: pip install pytest",
        )

        with (
            patch.object(
                workflow,
                "_load_preflight_config",
                return_value=MagicMock(
                    timeout_per_check=5.0,
                    fail_on_warning=False,
                    custom_tools=[custom_tool],
                ),
            ),
            patch("shutil.which", return_value="/usr/bin/pytest"),
        ):
            result = await workflow.run_preflight(
                runners=[],
                include_custom_tools=True,
            )

        assert result.success is True
        # Should have the custom tool result (component is "CustomTools")
        assert len(result.results) == 1
        assert result.results[0].component == "CustomTools"

    @pytest.mark.asyncio
    async def test_run_preflight_excludes_custom_tools_when_disabled(self) -> None:
        """Test run_preflight excludes custom tools when disabled."""
        from maverick.config import CustomToolConfig

        class ConcreteWorkflow(WorkflowDSLMixin):
            pass

        workflow = ConcreteWorkflow()

        custom_tool = CustomToolConfig(
            name="pytest",
            command="pytest",
            required=False,
        )

        with patch.object(
            workflow,
            "_load_preflight_config",
            return_value=MagicMock(
                timeout_per_check=5.0,
                fail_on_warning=False,
                custom_tools=[custom_tool],
            ),
        ):
            result = await workflow.run_preflight(
                runners=[],
                include_custom_tools=False,
            )

        assert result.success is True
        # Should have no results (no runners, no custom tools)
        assert len(result.results) == 0


class TestWorkflowDSLMixinLoadPreflightConfig:
    """Tests for WorkflowDSLMixin._load_preflight_config()."""

    def test_load_preflight_config_returns_default_when_no_config(self) -> None:
        """Test _load_preflight_config returns defaults when load_config fails."""
        from maverick import config as config_module

        class ConcreteWorkflow(WorkflowDSLMixin):
            pass

        workflow = ConcreteWorkflow()

        # Patch load_config to raise an exception (simulating no config)
        with patch.object(
            config_module,
            "load_config",
            side_effect=FileNotFoundError("No config found"),
        ):
            config = workflow._load_preflight_config()

        from maverick.config import PreflightValidationConfig

        assert isinstance(config, PreflightValidationConfig)
        assert config.timeout_per_check == 5.0
        assert config.fail_on_warning is False
        assert config.custom_tools == []

    def test_load_preflight_config_uses_config_values(self) -> None:
        """Test _load_preflight_config uses values from maverick.yaml."""
        from maverick.config import (
            CustomToolConfig,
            MaverickConfig,
            PreflightValidationConfig,
        )

        class ConcreteWorkflow(WorkflowDSLMixin):
            pass

        workflow = ConcreteWorkflow()

        custom_tool = CustomToolConfig(
            name="ruff",
            command="ruff",
            required=True,
        )
        mock_preflight_config = PreflightValidationConfig(
            timeout_per_check=10.0,
            fail_on_warning=True,
            custom_tools=[custom_tool],
        )
        mock_maverick_config = MagicMock(spec=MaverickConfig)
        mock_maverick_config.preflight = mock_preflight_config

        from maverick import config as config_module

        with patch.object(
            config_module,
            "load_config",
            return_value=mock_maverick_config,
        ):
            config = workflow._load_preflight_config()

        assert config.timeout_per_check == 10.0
        assert config.fail_on_warning is True
        assert len(config.custom_tools) == 1
        assert config.custom_tools[0].name == "ruff"

    def test_load_preflight_config_handles_missing_preflight_section(self) -> None:
        """Test _load_preflight_config handles config without preflight section."""
        from maverick.config import MaverickConfig

        class ConcreteWorkflow(WorkflowDSLMixin):
            pass

        workflow = ConcreteWorkflow()

        mock_maverick_config = MagicMock(spec=MaverickConfig)
        mock_maverick_config.preflight = None

        from maverick import config as config_module

        with patch.object(
            config_module,
            "load_config",
            return_value=mock_maverick_config,
        ):
            config = workflow._load_preflight_config()

        # When preflight is None, it should return None (the actual value from config)
        assert config is None
