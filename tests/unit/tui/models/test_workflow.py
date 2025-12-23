"""Unit tests for TUI workflow models."""

from __future__ import annotations

from datetime import datetime

import pytest

from maverick.tui.models import (
    AgentMessage,
    MessageType,
    StageState,
    StageStatus,
    ToolCallInfo,
    ValidationStep,
    ValidationStepStatus,
    WorkflowStage,
)


class TestToolCallInfo:
    """Tests for ToolCallInfo dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ToolCallInfo with required fields."""
        tool_call = ToolCallInfo(
            tool_name="read_file",
            arguments="file_path=/path/to/file",
        )

        assert tool_call.tool_name == "read_file"
        assert tool_call.arguments == "file_path=/path/to/file"
        assert tool_call.result is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ToolCallInfo with all fields."""
        tool_call = ToolCallInfo(
            tool_name="write_file",
            arguments="file_path=/path/to/file, content=...",
            result="File written successfully",
        )

        assert tool_call.tool_name == "write_file"
        assert tool_call.arguments == "file_path=/path/to/file, content=..."
        assert tool_call.result == "File written successfully"

    def test_result_defaults_to_none(self) -> None:
        """Test result defaults to None."""
        tool_call = ToolCallInfo(tool_name="test", arguments="arg=value")
        assert tool_call.result is None

    def test_tool_call_info_is_frozen(self) -> None:
        """Test ToolCallInfo is immutable (frozen)."""
        tool_call = ToolCallInfo(tool_name="test", arguments="args")

        with pytest.raises(Exception):  # FrozenInstanceError
            tool_call.result = "modified"  # type: ignore[misc]


class TestStageState:
    """Tests for StageState dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating StageState with required fields."""
        state = StageState(
            name="setup",
            display_name="Setup",
        )

        assert state.name == "setup"
        assert state.display_name == "Setup"
        assert state.status == StageStatus.PENDING  # default
        assert state.started_at is None  # default
        assert state.completed_at is None  # default
        assert state.error_message is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating StageState with all fields."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 5, 0)

        state = StageState(
            name="validation",
            display_name="Validation",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
            error_message=None,
        )

        assert state.name == "validation"
        assert state.display_name == "Validation"
        assert state.status == StageStatus.COMPLETED
        assert state.started_at == started
        assert state.completed_at == completed
        assert state.error_message is None

    def test_status_defaults_to_pending(self) -> None:
        """Test status defaults to PENDING."""
        state = StageState(name="test", display_name="Test")

        assert state.status == StageStatus.PENDING

    def test_started_at_defaults_to_none(self) -> None:
        """Test started_at defaults to None."""
        state = StageState(name="test", display_name="Test")

        assert state.started_at is None

    def test_completed_at_defaults_to_none(self) -> None:
        """Test completed_at defaults to None."""
        state = StageState(name="test", display_name="Test")

        assert state.completed_at is None

    def test_error_message_defaults_to_none(self) -> None:
        """Test error_message defaults to None."""
        state = StageState(name="test", display_name="Test")

        assert state.error_message is None

    def test_stage_state_with_error(self) -> None:
        """Test StageState with error message."""
        state = StageState(
            name="build",
            display_name="Build",
            status=StageStatus.FAILED,
            error_message="Build failed: syntax error",
        )

        assert state.status == StageStatus.FAILED
        assert state.error_message == "Build failed: syntax error"

    def test_stage_state_is_frozen(self) -> None:
        """Test StageState is immutable (frozen)."""
        state = StageState(name="test", display_name="Test")

        with pytest.raises(Exception):  # FrozenInstanceError
            state.status = StageStatus.COMPLETED  # type: ignore[misc]


# =============================================================================
# WorkflowScreenState Tests
# =============================================================================


class TestWorkflowStage:
    """Tests for WorkflowStage dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating WorkflowStage with required fields."""
        stage = WorkflowStage(
            name="setup", display_name="Setup", status=StageStatus.PENDING
        )

        assert stage.name == "setup"
        assert stage.display_name == "Setup"
        assert stage.status == StageStatus.PENDING
        assert stage.started_at is None  # default
        assert stage.completed_at is None  # default
        assert stage.detail_content is None  # default
        assert stage.error_message is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating WorkflowStage with all fields."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 5, 30)

        stage = WorkflowStage(
            name="implementation",
            display_name="Implementation",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
            detail_content="Implementation details...",
            error_message=None,
        )

        assert stage.name == "implementation"
        assert stage.display_name == "Implementation"
        assert stage.status == StageStatus.COMPLETED
        assert stage.started_at == started
        assert stage.completed_at == completed
        assert stage.detail_content == "Implementation details..."
        assert stage.error_message is None

    def test_duration_seconds_property_with_times(self) -> None:
        """Test duration_seconds property with start and end times."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 5, 30)

        stage = WorkflowStage(
            name="test",
            display_name="Test",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
        )

        assert stage.duration_seconds == 330.0  # 5 minutes 30 seconds

    def test_duration_seconds_property_no_start(self) -> None:
        """Test duration_seconds property when not started."""
        stage = WorkflowStage(
            name="test", display_name="Test", status=StageStatus.PENDING
        )
        assert stage.duration_seconds is None

    def test_duration_seconds_property_no_completion(self) -> None:
        """Test duration_seconds property when not completed."""
        stage = WorkflowStage(
            name="test",
            display_name="Test",
            status=StageStatus.ACTIVE,
            started_at=datetime.now(),
        )
        assert stage.duration_seconds is None

    def test_duration_display_property_seconds(self) -> None:
        """Test duration_display property for durations under 60 seconds."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 0, 45)

        stage = WorkflowStage(
            name="test",
            display_name="Test",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
        )

        assert stage.duration_display == "45s"

    def test_duration_display_property_minutes_seconds(self) -> None:
        """Test duration_display property for durations over 60 seconds."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 2, 30)

        stage = WorkflowStage(
            name="test",
            display_name="Test",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
        )

        assert stage.duration_display == "2m 30s"

    def test_duration_display_property_exact_minutes(self) -> None:
        """Test duration_display property for exact minutes."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 3, 0)

        stage = WorkflowStage(
            name="test",
            display_name="Test",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
        )

        assert stage.duration_display == "3m 0s"

    def test_duration_display_property_no_duration(self) -> None:
        """Test duration_display property when no duration available."""
        stage = WorkflowStage(
            name="test", display_name="Test", status=StageStatus.PENDING
        )
        assert stage.duration_display == ""

    def test_workflow_stage_with_error(self) -> None:
        """Test WorkflowStage with error message."""
        stage = WorkflowStage(
            name="build",
            display_name="Build",
            status=StageStatus.FAILED,
            error_message="Build failed: compilation error",
        )

        assert stage.status == StageStatus.FAILED
        assert stage.error_message == "Build failed: compilation error"

    def test_workflow_stage_is_frozen(self) -> None:
        """Test WorkflowStage is immutable (frozen)."""
        stage = WorkflowStage(
            name="test", display_name="Test", status=StageStatus.PENDING
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            stage.status = StageStatus.COMPLETED  # type: ignore[misc]


class TestValidationStep:
    """Tests for ValidationStep dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ValidationStep with required fields."""
        step = ValidationStep(
            name="format",
            display_name="Format",
            status=ValidationStepStatus.PENDING,
        )

        assert step.name == "format"
        assert step.display_name == "Format"
        assert step.status == ValidationStepStatus.PENDING
        assert step.error_output is None  # default
        assert step.command is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ValidationStep with all fields."""
        step = ValidationStep(
            name="lint",
            display_name="Lint",
            status=ValidationStepStatus.FAILED,
            error_output="Line 42: undefined variable 'x'",
            command="ruff check src/",
        )

        assert step.name == "lint"
        assert step.display_name == "Lint"
        assert step.status == ValidationStepStatus.FAILED
        assert step.error_output == "Line 42: undefined variable 'x'"
        assert step.command == "ruff check src/"

    def test_error_output_defaults_to_none(self) -> None:
        """Test error_output defaults to None."""
        step = ValidationStep(
            name="test", display_name="Test", status=ValidationStepStatus.PASSED
        )
        assert step.error_output is None

    def test_command_defaults_to_none(self) -> None:
        """Test command defaults to None."""
        step = ValidationStep(
            name="test", display_name="Test", status=ValidationStepStatus.PASSED
        )
        assert step.command is None

    def test_different_statuses(self) -> None:
        """Test ValidationStep with different statuses."""
        for status in ValidationStepStatus:
            step = ValidationStep(name="test", display_name="Test", status=status)
            assert step.status == status

    def test_validation_step_is_frozen(self) -> None:
        """Test ValidationStep is immutable (frozen)."""
        step = ValidationStep(
            name="test", display_name="Test", status=ValidationStepStatus.PENDING
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            step.status = ValidationStepStatus.PASSED  # type: ignore[misc]


class TestAgentMessage:
    """Tests for AgentMessage dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating AgentMessage with required fields."""
        timestamp = datetime(2025, 1, 1, 10, 0, 0)
        message = AgentMessage(
            id="msg-001",
            timestamp=timestamp,
            agent_id="agent-1",
            agent_name="CodeReviewer",
            message_type=MessageType.TEXT,
            content="Starting code review...",
        )

        assert message.id == "msg-001"
        assert message.timestamp == timestamp
        assert message.agent_id == "agent-1"
        assert message.agent_name == "CodeReviewer"
        assert message.message_type == MessageType.TEXT
        assert message.content == "Starting code review..."
        assert message.language is None  # default
        assert message.tool_call is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating AgentMessage with all fields."""
        timestamp = datetime(2025, 1, 1, 10, 0, 0)
        tool_call = ToolCallInfo(
            tool_name="read_file",
            arguments="file_path=/src/main.py",
            result="File contents...",
        )

        message = AgentMessage(
            id="msg-002",
            timestamp=timestamp,
            agent_id="agent-2",
            agent_name="Implementer",
            message_type=MessageType.TOOL_CALL,
            content="Reading file...",
            language="python",
            tool_call=tool_call,
        )

        assert message.id == "msg-002"
        assert message.timestamp == timestamp
        assert message.agent_id == "agent-2"
        assert message.agent_name == "Implementer"
        assert message.message_type == MessageType.TOOL_CALL
        assert message.content == "Reading file..."
        assert message.language == "python"
        assert message.tool_call == tool_call

    def test_language_defaults_to_none(self) -> None:
        """Test language defaults to None."""
        message = AgentMessage(
            id="test",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Test",
        )
        assert message.language is None

    def test_tool_call_defaults_to_none(self) -> None:
        """Test tool_call defaults to None."""
        message = AgentMessage(
            id="test",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Test",
        )
        assert message.tool_call is None

    def test_different_message_types(self) -> None:
        """Test AgentMessage with different message types."""
        for msg_type in MessageType:
            message = AgentMessage(
                id=f"msg-{msg_type.value}",
                timestamp=datetime.now(),
                agent_id="agent",
                agent_name="Agent",
                message_type=msg_type,
                content="Test content",
            )
            assert message.message_type == msg_type

    def test_code_message_with_language(self) -> None:
        """Test AgentMessage with CODE type and language."""
        message = AgentMessage(
            id="code-msg",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.CODE,
            content="def foo():\n    pass",
            language="python",
        )

        assert message.message_type == MessageType.CODE
        assert message.language == "python"
        assert "def foo()" in message.content

    def test_agent_message_is_frozen(self) -> None:
        """Test AgentMessage is immutable (frozen)."""
        message = AgentMessage(
            id="test",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Test",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            message.content = "Modified"  # type: ignore[misc]


# =============================================================================
# Widget State Model Tests (012-workflow-widgets)
# =============================================================================
