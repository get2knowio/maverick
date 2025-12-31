"""Async helper utilities for testing.

This module provides utilities for testing async code, particularly
async generators used in workflows and agent interactions.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class AsyncGeneratorCapture(Generic[T]):
    """Utility to collect all items from an async generator for assertion.

    Captures items yielded by an async generator along with completion status
    and any errors raised during iteration.

    Attributes:
        items: List of captured items from the generator
        error: Exception raised by the generator, if any
        completed: Whether the generator finished normally (without error)

    Example:
        >>> @pytest.mark.asyncio
        ... async def test_workflow_events():
        ...     workflow = ValidationWorkflow(stages=[...])
        ...     capture = await AsyncGeneratorCapture.capture(workflow.run())
        ...     assert capture.completed
        ...     assert len(capture) >= 2
        ...     assert any(isinstance(e, WorkflowComplete) for e in capture)
    """

    items: list[T] = field(default_factory=list)
    error: Exception | None = None
    completed: bool = False

    @classmethod
    async def capture(cls, gen: AsyncGenerator[T, None]) -> AsyncGeneratorCapture[T]:
        """Collect all items from an async generator.

        Iterates through the async generator, collecting all yielded items.
        If the generator raises an exception, it is captured in the error
        attribute and the items collected up to that point are preserved.

        Args:
            gen: The async generator to capture items from

        Returns:
            AsyncGeneratorCapture instance with all captured items

        Example:
            >>> async def my_generator():
            ...     yield 1
            ...     yield 2
            ...     yield 3
            >>> capture = await AsyncGeneratorCapture.capture(my_generator())
            >>> list(capture)
            [1, 2, 3]
        """
        result = cls()
        try:
            async for item in gen:
                result.items.append(item)
            result.completed = True
        except Exception as e:
            result.error = e
        return result

    def __len__(self) -> int:
        """Return the number of captured items."""
        return len(self.items)

    def __iter__(self) -> Iterator[T]:
        """Iterate over captured items."""
        return iter(self.items)

    def __getitem__(self, index: int) -> T:
        """Get item by index."""
        return self.items[index]

    def filter_by_type(self, item_type: type) -> list[T]:
        """Filter captured items by type.

        Args:
            item_type: The type to filter by

        Returns:
            List of items matching the specified type
        """
        return [item for item in self.items if isinstance(item, item_type)]

    def first_of_type(self, item_type: type) -> T | None:
        """Get the first item of a specific type.

        Args:
            item_type: The type to search for

        Returns:
            First item matching the type, or None if not found
        """
        for item in self.items:
            if isinstance(item, item_type):
                return item
        return None

    def last_of_type(self, item_type: type) -> T | None:
        """Get the last item of a specific type.

        Args:
            item_type: The type to search for

        Returns:
            Last item matching the type, or None if not found
        """
        for item in reversed(self.items):
            if isinstance(item, item_type):
                return item
        return None
