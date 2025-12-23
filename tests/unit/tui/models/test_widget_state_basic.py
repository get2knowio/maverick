"""Unit tests for TUI basic widget state models."""

from __future__ import annotations

from datetime import datetime

import pytest

from maverick.tui.models import (
    AgentMessage,
    AgentOutputState,
    MessageType,
    StageStatus,
    WorkflowProgressState,
    WorkflowStage,
)


class TestAgentOutputState:
    """Tests for AgentOutputState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating AgentOutputState with default values."""
        state = AgentOutputState()

        assert state.messages == []
        assert state.max_messages == 1000
        assert state.auto_scroll is True
        assert state.search_query is None
        assert state.search_matches == []
        assert state.filter_agent is None
        assert state.truncated is False

    def test_creation_with_custom_values(self) -> None:
        """Test creating AgentOutputState with custom values."""
        message = AgentMessage(
            id="msg-1",
            timestamp=datetime.now(),
            agent_id="agent-1",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Test",
        )

        state = AgentOutputState(
            messages=[message],
            max_messages=500,
            auto_scroll=False,
            search_query="test",
            search_matches=[0],
            filter_agent="agent-1",
            truncated=True,
        )

        assert len(state.messages) == 1
        assert state.max_messages == 500
        assert state.auto_scroll is False
        assert state.search_query == "test"
        assert state.search_matches == [0]
        assert state.filter_agent == "agent-1"
        assert state.truncated is True

    def test_add_message_method(self) -> None:
        """Test add_message method adds messages."""
        state = AgentOutputState()

        msg1 = AgentMessage(
            id="msg-1",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="First",
        )
        msg2 = AgentMessage(
            id="msg-2",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Second",
        )

        state.add_message(msg1)
        state.add_message(msg2)

        assert len(state.messages) == 2
        assert state.messages[0] == msg1
        assert state.messages[1] == msg2

    def test_add_message_respects_max_messages(self) -> None:
        """Test add_message maintains buffer limit."""
        state = AgentOutputState(max_messages=3)

        # Add 5 messages
        for i in range(5):
            msg = AgentMessage(
                id=f"msg-{i}",
                timestamp=datetime.now(),
                agent_id="agent",
                agent_name="Agent",
                message_type=MessageType.TEXT,
                content=f"Message {i}",
            )
            state.add_message(msg)

        # Should keep only last 3
        assert len(state.messages) == 3
        assert state.messages[0].content == "Message 2"
        assert state.messages[1].content == "Message 3"
        assert state.messages[2].content == "Message 4"
        assert state.truncated is True

    def test_filtered_messages_property_no_filter(self) -> None:
        """Test filtered_messages property with no filter."""
        msg1 = AgentMessage(
            id="msg-1",
            timestamp=datetime.now(),
            agent_id="agent-1",
            agent_name="Agent1",
            message_type=MessageType.TEXT,
            content="Test",
        )
        msg2 = AgentMessage(
            id="msg-2",
            timestamp=datetime.now(),
            agent_id="agent-2",
            agent_name="Agent2",
            message_type=MessageType.TEXT,
            content="Test",
        )

        state = AgentOutputState(messages=[msg1, msg2])
        assert len(state.filtered_messages) == 2

    def test_filtered_messages_property_with_agent_filter(self) -> None:
        """Test filtered_messages property with agent filter."""
        msg1 = AgentMessage(
            id="msg-1",
            timestamp=datetime.now(),
            agent_id="agent-1",
            agent_name="Agent1",
            message_type=MessageType.TEXT,
            content="Test",
        )
        msg2 = AgentMessage(
            id="msg-2",
            timestamp=datetime.now(),
            agent_id="agent-2",
            agent_name="Agent2",
            message_type=MessageType.TEXT,
            content="Test",
        )
        msg3 = AgentMessage(
            id="msg-3",
            timestamp=datetime.now(),
            agent_id="agent-1",
            agent_name="Agent1",
            message_type=MessageType.TEXT,
            content="Test",
        )

        state = AgentOutputState(messages=[msg1, msg2, msg3], filter_agent="agent-1")

        filtered = state.filtered_messages
        assert len(filtered) == 2
        assert filtered[0] == msg1
        assert filtered[1] == msg3

    def test_is_empty_property_when_empty(self) -> None:
        """Test is_empty property when no messages."""
        state = AgentOutputState()
        assert state.is_empty is True

    def test_is_empty_property_when_not_empty(self) -> None:
        """Test is_empty property when messages exist."""
        msg = AgentMessage(
            id="msg-1",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Test",
        )
        state = AgentOutputState(messages=[msg])
        assert state.is_empty is False

    def test_agent_output_state_is_mutable(self) -> None:
        """Test AgentOutputState is mutable (not frozen)."""
        state = AgentOutputState()

        # Should allow modification
        state.auto_scroll = False
        assert state.auto_scroll is False

        state.search_query = "test"
        assert state.search_query == "test"


class TestWorkflowProgressState:
    """Tests for WorkflowProgressState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating WorkflowProgressState with default values."""
        state = WorkflowProgressState()

        assert state.stages == ()
        assert state.loading is False
        assert state.expanded_stage is None

    def test_creation_with_custom_values(self) -> None:
        """Test creating WorkflowProgressState with custom values."""
        stage1 = WorkflowStage(
            name="setup", display_name="Setup", status=StageStatus.COMPLETED
        )
        stage2 = WorkflowStage(
            name="build", display_name="Build", status=StageStatus.ACTIVE
        )

        state = WorkflowProgressState(
            stages=(stage1, stage2), loading=True, expanded_stage="setup"
        )

        assert len(state.stages) == 2
        assert state.loading is True
        assert state.expanded_stage == "setup"

    def test_current_stage_property_with_active_stage(self) -> None:
        """Test current_stage property returns active stage."""
        stage1 = WorkflowStage(
            name="setup", display_name="Setup", status=StageStatus.COMPLETED
        )
        stage2 = WorkflowStage(
            name="build", display_name="Build", status=StageStatus.ACTIVE
        )
        stage3 = WorkflowStage(
            name="test", display_name="Test", status=StageStatus.PENDING
        )

        state = WorkflowProgressState(stages=(stage1, stage2, stage3))

        assert state.current_stage == stage2
        assert state.current_stage.status == StageStatus.ACTIVE

    def test_current_stage_property_no_active_stage(self) -> None:
        """Test current_stage property when no stage is active."""
        stage1 = WorkflowStage(
            name="setup", display_name="Setup", status=StageStatus.COMPLETED
        )
        stage2 = WorkflowStage(
            name="build", display_name="Build", status=StageStatus.PENDING
        )

        state = WorkflowProgressState(stages=(stage1, stage2))
        assert state.current_stage is None

    def test_current_stage_property_empty_stages(self) -> None:
        """Test current_stage property with no stages."""
        state = WorkflowProgressState()
        assert state.current_stage is None

    def test_is_empty_property_when_empty(self) -> None:
        """Test is_empty property when no stages."""
        state = WorkflowProgressState()
        assert state.is_empty is True

    def test_is_empty_property_when_not_empty(self) -> None:
        """Test is_empty property when stages exist."""
        stage = WorkflowStage(
            name="setup", display_name="Setup", status=StageStatus.PENDING
        )
        state = WorkflowProgressState(stages=(stage,))
        assert state.is_empty is False

    def test_is_empty_property_when_loading(self) -> None:
        """Test is_empty property when loading."""
        state = WorkflowProgressState(loading=True)
        assert state.is_empty is False

    def test_workflow_progress_state_is_frozen(self) -> None:
        """Test WorkflowProgressState is immutable (frozen)."""
        state = WorkflowProgressState()

        with pytest.raises(Exception):  # FrozenInstanceError
            state.loading = True  # type: ignore[misc]
