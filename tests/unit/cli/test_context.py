"""Unit tests for CLI context module.

Tests the CLI context management, exit codes, and utilities:
- ExitCode enum
- CLIContext dataclass
- async_command decorator
"""

from __future__ import annotations

import asyncio
from enum import IntEnum
from pathlib import Path

import pytest

from maverick.cli.context import (
    CLIContext,
    ExitCode,
    async_command,
)
from maverick.config import MaverickConfig

# =============================================================================
# ExitCode Tests
# =============================================================================


class TestExitCode:
    """Tests for ExitCode enum."""

    def test_exit_code_success_value(self) -> None:
        """Test ExitCode.SUCCESS has value 0."""
        assert ExitCode.SUCCESS == 0
        assert ExitCode.SUCCESS.value == 0

    def test_exit_code_failure_value(self) -> None:
        """Test ExitCode.FAILURE has value 1."""
        assert ExitCode.FAILURE == 1
        assert ExitCode.FAILURE.value == 1

    def test_exit_code_partial_value(self) -> None:
        """Test ExitCode.PARTIAL has value 2."""
        assert ExitCode.PARTIAL == 2
        assert ExitCode.PARTIAL.value == 2

    def test_exit_code_interrupted_value(self) -> None:
        """Test ExitCode.INTERRUPTED has value 130 (128 + SIGINT)."""
        assert ExitCode.INTERRUPTED == 130
        assert ExitCode.INTERRUPTED.value == 130

    def test_exit_code_is_int_enum(self) -> None:
        """Test ExitCode inherits from IntEnum."""
        assert isinstance(ExitCode.SUCCESS, int)
        assert isinstance(ExitCode.FAILURE, int)
        assert issubclass(ExitCode, IntEnum)

    def test_exit_code_integer_comparison(self) -> None:
        """Test ExitCode can be compared to integers."""
        assert ExitCode.SUCCESS == 0
        assert ExitCode.FAILURE == 1
        assert ExitCode.PARTIAL == 2
        assert ExitCode.INTERRUPTED == 130

    def test_exit_code_from_integer(self) -> None:
        """Test creating ExitCode from integer value."""
        assert ExitCode(0) == ExitCode.SUCCESS
        assert ExitCode(1) == ExitCode.FAILURE
        assert ExitCode(2) == ExitCode.PARTIAL
        assert ExitCode(130) == ExitCode.INTERRUPTED

    def test_exit_code_invalid_value_raises(self) -> None:
        """Test invalid integer raises ValueError."""
        with pytest.raises(ValueError):
            ExitCode(3)

        with pytest.raises(ValueError):
            ExitCode(99)

    def test_exit_code_iteration(self) -> None:
        """Test ExitCode is iterable."""
        codes = list(ExitCode)

        assert len(codes) == 4
        assert ExitCode.SUCCESS in codes
        assert ExitCode.FAILURE in codes
        assert ExitCode.PARTIAL in codes
        assert ExitCode.INTERRUPTED in codes

    def test_exit_code_membership(self) -> None:
        """Test ExitCode membership checks."""
        assert ExitCode.SUCCESS in ExitCode
        assert ExitCode.INTERRUPTED in ExitCode

    def test_exit_code_name_attribute(self) -> None:
        """Test ExitCode has name attribute."""
        assert ExitCode.SUCCESS.name == "SUCCESS"
        assert ExitCode.FAILURE.name == "FAILURE"
        assert ExitCode.PARTIAL.name == "PARTIAL"
        assert ExitCode.INTERRUPTED.name == "INTERRUPTED"

    def test_exit_code_all_members(self) -> None:
        """Test all ExitCode members are present."""
        expected_codes = {0, 1, 2, 130}
        actual_codes = {code.value for code in ExitCode}

        assert actual_codes == expected_codes

    def test_exit_code_unique_values(self) -> None:
        """Test each ExitCode has unique value."""
        values = [code.value for code in ExitCode]

        assert len(values) == len(set(values))

    def test_exit_code_can_be_used_as_return_value(self) -> None:
        """Test ExitCode can be used as function return value."""

        def mock_cli_command() -> int:
            return ExitCode.SUCCESS

        result = mock_cli_command()
        assert result == 0

    def test_exit_code_hashable(self) -> None:
        """Test ExitCode members are hashable."""
        code_set = {ExitCode.SUCCESS, ExitCode.FAILURE, ExitCode.SUCCESS}

        # Should deduplicate
        assert len(code_set) == 2

    def test_exit_code_identity(self) -> None:
        """Test ExitCode members are singletons."""
        code1 = ExitCode.SUCCESS
        code2 = ExitCode.SUCCESS

        # Should be same object
        assert code1 is code2


# =============================================================================
# CLIContext Tests
# =============================================================================


@pytest.fixture
def mock_config() -> MaverickConfig:
    """Create a mock MaverickConfig for testing."""
    return MaverickConfig()


class TestCLIContext:
    """Tests for CLIContext dataclass."""

    def test_cli_context_default_values(self, mock_config: MaverickConfig) -> None:
        """Test CLIContext creation with default values."""
        ctx = CLIContext(config=mock_config)

        assert ctx.config is mock_config
        assert ctx.config_path is None
        assert ctx.verbosity == 0
        assert ctx.quiet is False

    def test_cli_context_with_custom_values(self, mock_config: MaverickConfig) -> None:
        """Test CLIContext creation with custom values."""
        config_path = Path("/custom/config.yaml")
        ctx = CLIContext(
            config=mock_config,
            config_path=config_path,
            verbosity=2,
            quiet=True,
        )

        assert ctx.config is mock_config
        assert ctx.config_path == config_path
        assert ctx.verbosity == 2
        assert ctx.quiet is True

    def test_cli_context_is_frozen(self, mock_config: MaverickConfig) -> None:
        """Test CLIContext dataclass is frozen (immutable)."""
        ctx = CLIContext(config=mock_config)

        with pytest.raises(AttributeError):
            ctx.verbosity = 1  # type: ignore[misc]

        with pytest.raises(AttributeError):
            ctx.quiet = True  # type: ignore[misc]

    def test_cli_context_verbosity_levels(self, mock_config: MaverickConfig) -> None:
        """Test CLIContext with different verbosity levels."""
        ctx0 = CLIContext(config=mock_config, verbosity=0)
        ctx1 = CLIContext(config=mock_config, verbosity=1)
        ctx2 = CLIContext(config=mock_config, verbosity=2)

        assert ctx0.verbosity == 0
        assert ctx1.verbosity == 1
        assert ctx2.verbosity == 2

    def test_cli_context_with_path_types(self, mock_config: MaverickConfig) -> None:
        """Test CLIContext accepts Path objects."""
        path_obj = Path("/path/to/config.yaml")
        ctx = CLIContext(config=mock_config, config_path=path_obj)

        assert ctx.config_path == path_obj
        assert isinstance(ctx.config_path, Path)

    def test_cli_context_has_slots(self, mock_config: MaverickConfig) -> None:
        """Test CLIContext uses slots for memory efficiency."""
        ctx = CLIContext(config=mock_config)

        # Should not be able to add arbitrary attributes (frozen=True prevents this)
        with pytest.raises((AttributeError, TypeError)):
            ctx.new_attribute = "value"  # type: ignore[attr-defined]


# =============================================================================
# async_command Decorator Tests
# =============================================================================


class TestAsyncCommand:
    """Tests for async_command decorator."""

    def test_async_command_wraps_async_function(self) -> None:
        """Test async_command wraps an async function correctly."""

        @async_command
        async def example_command() -> str:
            """Example async command."""
            await asyncio.sleep(0)
            return "success"

        result = example_command()
        assert result == "success"

    def test_async_command_preserves_function_name(self) -> None:
        """Test async_command preserves the function name."""

        @async_command
        async def my_function() -> None:
            """My function."""
            pass

        assert my_function.__name__ == "my_function"

    def test_async_command_preserves_docstring(self) -> None:
        """Test async_command preserves the function docstring."""

        @async_command
        async def documented_function() -> None:
            """This is the docstring."""
            pass

        assert documented_function.__doc__ == "This is the docstring."

    def test_async_command_with_arguments(self) -> None:
        """Test async_command works with functions that take arguments."""

        @async_command
        async def add_numbers(a: int, b: int) -> int:
            """Add two numbers."""
            await asyncio.sleep(0)
            return a + b

        result = add_numbers(2, 3)
        assert result == 5

    def test_async_command_with_keyword_arguments(self) -> None:
        """Test async_command works with keyword arguments."""

        @async_command
        async def greet(name: str, greeting: str = "Hello") -> str:
            """Greet someone."""
            await asyncio.sleep(0)
            return f"{greeting}, {name}!"

        result = greet("Alice", greeting="Hi")
        assert result == "Hi, Alice!"

    def test_async_command_with_return_value(self) -> None:
        """Test async_command returns the async function's return value."""

        @async_command
        async def get_number() -> int:
            """Get a number."""
            await asyncio.sleep(0)
            return 42

        result = get_number()
        assert result == 42

    def test_async_command_propagates_exceptions(self) -> None:
        """Test async_command propagates exceptions from async function."""

        @async_command
        async def failing_command() -> None:
            """Command that raises an exception."""
            await asyncio.sleep(0)
            raise ValueError("Something went wrong")

        with pytest.raises(ValueError, match="Something went wrong"):
            failing_command()

    def test_async_command_with_none_return(self) -> None:
        """Test async_command works with functions that return None."""

        @async_command
        async def void_command() -> None:
            """Command that returns nothing."""
            await asyncio.sleep(0)

        result = void_command()
        assert result is None

    def test_async_command_runs_coroutine_to_completion(self) -> None:
        """Test async_command runs the coroutine to completion."""
        executed = []

        @async_command
        async def multi_step_command() -> None:
            """Command with multiple steps."""
            executed.append("start")
            await asyncio.sleep(0)
            executed.append("middle")
            await asyncio.sleep(0)
            executed.append("end")

        multi_step_command()

        assert executed == ["start", "middle", "end"]

    def test_async_command_with_multiple_decorators(self) -> None:
        """Test async_command can be used with other decorators."""

        def uppercase_result(func):  # type: ignore[no-untyped-def]
            """Decorator to uppercase string results."""

            def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
                result = func(*args, **kwargs)
                if isinstance(result, str):
                    return result.upper()
                return result

            return wrapper

        @uppercase_result
        @async_command
        async def get_message() -> str:
            """Get a message."""
            await asyncio.sleep(0)
            return "hello"

        result = get_message()
        assert result == "HELLO"


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for CLI context components."""

    def test_async_command_with_exit_code(self) -> None:
        """Test async_command can return ExitCode."""

        @async_command
        async def command_with_exit_code() -> int:
            """Command that returns an exit code."""
            await asyncio.sleep(0)
            return ExitCode.SUCCESS

        result = command_with_exit_code()
        assert result == 0
        assert result == ExitCode.SUCCESS
