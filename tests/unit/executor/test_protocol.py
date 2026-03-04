"""Tests for StepExecutor @runtime_checkable Protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from maverick.executor.config import StepExecutorConfig
from maverick.executor.protocol import StepExecutor
from maverick.executor.result import ExecutorResult, UsageMetadata


class _ConformingExecutor:
    """A minimal StepExecutor implementation for testing."""

    async def execute(
        self,
        *,
        step_name: str,
        agent_name: str,
        prompt: Any,
        instructions: str | None = None,
        allowed_tools: list[str] | None = None,
        cwd: Path | None = None,
        output_schema: type[BaseModel] | None = None,
        config: StepExecutorConfig | None = None,
        event_callback: Any | None = None,
    ) -> ExecutorResult:
        return ExecutorResult(
            output="done",
            success=True,
            usage=UsageMetadata(),
            events=(),
        )


class _NonConformingNoExecute:
    """Object with no execute method — should not satisfy StepExecutor."""

    def run(self) -> None:
        pass


class _NonConformingSyncExecute:
    """Object with a sync execute method — satisfies Protocol at isinstance level
    because Python's @runtime_checkable only checks method existence, not signature."""

    def execute(self, **kwargs: Any) -> str:
        return "done"


class TestStepExecutorProtocol:
    """Tests for StepExecutor @runtime_checkable Protocol."""

    def test_conforming_object_satisfies_isinstance(self) -> None:
        """Object with async execute() satisfies isinstance(obj, StepExecutor)."""
        executor = _ConformingExecutor()
        assert isinstance(executor, StepExecutor)

    def test_non_conforming_no_execute_fails_isinstance(self) -> None:
        """Object with no execute() fails isinstance(obj, StepExecutor)."""
        obj = _NonConformingNoExecute()
        assert not isinstance(obj, StepExecutor)

    def test_protocol_is_runtime_checkable(self) -> None:
        """StepExecutor can be used in isinstance() checks (runtime_checkable)."""
        # This would raise TypeError if not runtime_checkable
        assert isinstance(_ConformingExecutor(), StepExecutor)

    def test_claude_executor_satisfies_protocol(self) -> None:
        """ClaudeStepExecutor satisfies isinstance(executor, StepExecutor)."""
        from maverick.executor.claude import ClaudeStepExecutor
        from maverick.registry import ComponentRegistry

        registry = ComponentRegistry()
        executor = ClaudeStepExecutor(registry=registry)
        assert isinstance(executor, StepExecutor)

    def test_protocol_has_execute_method(self) -> None:
        """StepExecutor protocol has an execute method."""
        assert hasattr(StepExecutor, "execute")
