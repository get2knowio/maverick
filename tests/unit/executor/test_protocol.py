"""Tests for StepExecutor @runtime_checkable Protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from maverick.executor.config import StepConfig
from maverick.executor.protocol import StepExecutor
from maverick.executor.result import ExecutorResult, UsageMetadata


class _ConformingExecutor:
    """A minimal StepExecutor implementation for testing."""

    async def execute_named(
        self,
        *,
        agent: str,
        user_prompt: str,
        step_name: str = "execute_named",
        result_model: type[BaseModel] | None = None,
        cwd: Path | None = None,
        config: StepConfig | None = None,
        timeout: float | None = None,
    ) -> ExecutorResult:
        return ExecutorResult(
            output="done",
            success=True,
            usage=UsageMetadata(),
            events=(),
        )


class _NonConformingNoExecute:
    """Object with no execute_named method — should not satisfy StepExecutor."""

    def run(self) -> None:
        pass


class _NonConformingSyncExecute:
    """Object with a sync execute_named method — satisfies Protocol at
    isinstance level because Python's @runtime_checkable only checks
    method existence, not signature."""

    def execute_named(self, **kwargs: Any) -> str:
        return "done"


class TestStepExecutorProtocol:
    """Tests for StepExecutor @runtime_checkable Protocol."""

    def test_conforming_object_satisfies_isinstance(self) -> None:
        """Object with async execute_named() satisfies isinstance(obj, StepExecutor)."""
        executor = _ConformingExecutor()
        assert isinstance(executor, StepExecutor)

    def test_non_conforming_no_execute_fails_isinstance(self) -> None:
        """Object with no execute_named() fails isinstance(obj, StepExecutor)."""
        obj = _NonConformingNoExecute()
        assert not isinstance(obj, StepExecutor)

    def test_protocol_is_runtime_checkable(self) -> None:
        """StepExecutor can be used in isinstance() checks (runtime_checkable)."""
        # This would raise TypeError if not runtime_checkable
        assert isinstance(_ConformingExecutor(), StepExecutor)

    def test_opencode_executor_satisfies_protocol(self) -> None:
        """OpenCodeStepExecutor satisfies isinstance(executor, StepExecutor)."""
        from maverick.runtime.opencode import OpenCodeStepExecutor

        executor = OpenCodeStepExecutor()
        assert isinstance(executor, StepExecutor)

    def test_protocol_has_execute_named_method(self) -> None:
        """StepExecutor protocol has an execute_named method."""
        assert hasattr(StepExecutor, "execute_named")
