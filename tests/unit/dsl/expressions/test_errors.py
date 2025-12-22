"""Unit tests for expression-specific error types.

Tests for ExpressionError, ExpressionSyntaxError, ExpressionEvaluationError,
and ExpressionErrorInfo.
"""

from __future__ import annotations

import pytest

from maverick.dsl.expressions.errors import (
    ExpressionError,
    ExpressionErrorInfo,
    ExpressionEvaluationError,
    ExpressionSyntaxError,
)
from maverick.exceptions import MaverickError


class TestExpressionError:
    """Test suite for ExpressionError base exception."""

    def test_creation_with_message_only(self) -> None:
        """Test creating ExpressionError with message only."""
        error = ExpressionError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.expression is None

    def test_creation_with_message_and_expression(self) -> None:
        """Test creating ExpressionError with message and expression."""
        error = ExpressionError("Invalid syntax", expression="1 + + 2")
        assert str(error) == "Invalid syntax"
        assert error.message == "Invalid syntax"
        assert error.expression == "1 + + 2"

    def test_inherits_from_maverick_error(self) -> None:
        """Test that ExpressionError inherits from MaverickError."""
        error = ExpressionError("Test error")
        assert isinstance(error, MaverickError)
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        """Test that ExpressionError can be raised and caught."""
        with pytest.raises(ExpressionError) as exc_info:
            raise ExpressionError("Test error", expression="x + y")

        assert str(exc_info.value) == "Test error"
        assert exc_info.value.expression == "x + y"

    def test_can_be_caught_as_maverick_error(self) -> None:
        """Test that ExpressionError can be caught as MaverickError."""
        with pytest.raises(MaverickError):
            raise ExpressionError("Test error")

    def test_expression_attribute_accessible(self) -> None:
        """Test that expression attribute is accessible."""
        error = ExpressionError("Error message", expression="test_expr")
        assert hasattr(error, "expression")
        assert error.expression == "test_expr"

    def test_message_attribute_accessible(self) -> None:
        """Test that message attribute is accessible."""
        error = ExpressionError("Error message")
        assert hasattr(error, "message")
        assert error.message == "Error message"


class TestExpressionSyntaxError:
    """Test suite for ExpressionSyntaxError."""

    def test_creation_with_basic_fields(self) -> None:
        """Test creating ExpressionSyntaxError with basic fields."""
        error = ExpressionSyntaxError(
            "Unexpected token",
            expression="x + + y",
        )
        assert error.expression == "x + + y"
        assert error.position == 0
        assert "Unexpected token: x + + y" in str(error)

    def test_creation_with_position(self) -> None:
        """Test creating ExpressionSyntaxError with position."""
        error = ExpressionSyntaxError(
            "Unexpected token",
            expression="x + + y",
            position=4,
        )
        assert error.expression == "x + + y"
        assert error.position == 4
        # Should include position indicator
        assert "at position 4" in str(error)
        assert "x + + y" in str(error)
        assert "    ^" in str(error)  # Caret pointing to position

    def test_position_indicator_formatting(self) -> None:
        """Test that position indicator is formatted correctly."""
        error = ExpressionSyntaxError(
            "Invalid operator",
            expression="foo + bar",
            position=6,
        )
        error_str = str(error)
        # Check that caret is at the right position
        assert "Invalid operator at position 6" in error_str
        assert "foo + bar" in error_str
        assert "      ^" in error_str  # 6 spaces before caret

    def test_inherits_from_expression_error(self) -> None:
        """Test that ExpressionSyntaxError inherits from ExpressionError."""
        error = ExpressionSyntaxError("Test", expression="test")
        assert isinstance(error, ExpressionError)
        assert isinstance(error, MaverickError)
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        """Test that ExpressionSyntaxError can be raised and caught."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            raise ExpressionSyntaxError(
                "Syntax error",
                expression="1 + 2 + + 3",
                position=8,
            )

        assert exc_info.value.expression == "1 + 2 + + 3"
        assert exc_info.value.position == 8

    def test_can_be_caught_as_expression_error(self) -> None:
        """Test that ExpressionSyntaxError can be caught as ExpressionError."""
        with pytest.raises(ExpressionError):
            raise ExpressionSyntaxError("Test", expression="test")

    def test_position_zero_formatting(self) -> None:
        """Test formatting when position is zero (default)."""
        error = ExpressionSyntaxError("Bad syntax", expression="invalid")
        error_str = str(error)
        # Position 0 should not show position indicator
        assert "Bad syntax: invalid" in error_str
        assert "at position" not in error_str

    def test_position_attribute_accessible(self) -> None:
        """Test that position attribute is accessible."""
        error = ExpressionSyntaxError("Test", expression="test", position=5)
        assert hasattr(error, "position")
        assert error.position == 5

    def test_multiline_expression_with_position(self) -> None:
        """Test position indicator with single-line expression."""
        error = ExpressionSyntaxError(
            "Missing closing bracket",
            expression="(x + y * z",
            position=0,
        )
        # Position 0 should not show caret
        assert "Missing closing bracket: (x + y * z" in str(error)


class TestExpressionEvaluationError:
    """Test suite for ExpressionEvaluationError."""

    def test_creation_with_message_and_expression(self) -> None:
        """Test creating ExpressionEvaluationError with message and expression."""
        error = ExpressionEvaluationError(
            "Undefined variable 'x'",
            expression="x + y",
        )
        assert error.expression == "x + y"
        assert error.context_vars == ()
        assert "Undefined variable 'x'" in str(error)
        assert "x + y" in str(error)

    def test_creation_with_context_vars(self) -> None:
        """Test creating ExpressionEvaluationError with context variables."""
        error = ExpressionEvaluationError(
            "Undefined variable 'z'",
            expression="z * 2",
            context_vars=("x", "y", "foo"),
        )
        assert error.expression == "z * 2"
        assert error.context_vars == ("x", "y", "foo")
        # Should show available variables
        error_str = str(error)
        assert "Undefined variable 'z'" in error_str
        assert "z * 2" in error_str
        assert "Available variables:" in error_str
        assert "foo" in error_str
        assert "x" in error_str
        assert "y" in error_str

    def test_context_vars_sorted_in_message(self) -> None:
        """Test that context variables are sorted in error message."""
        error = ExpressionEvaluationError(
            "Error",
            expression="test",
            context_vars=("zebra", "apple", "banana"),
        )
        error_str = str(error)
        # Variables should be sorted alphabetically
        assert "apple, banana, zebra" in error_str

    def test_inherits_from_expression_error(self) -> None:
        """Test that ExpressionEvaluationError inherits from ExpressionError."""
        error = ExpressionEvaluationError("Test", expression="test")
        assert isinstance(error, ExpressionError)
        assert isinstance(error, MaverickError)
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        """Test that ExpressionEvaluationError can be raised and caught."""
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            raise ExpressionEvaluationError(
                "Division by zero",
                expression="x / 0",
                context_vars=("x",),
            )

        assert exc_info.value.expression == "x / 0"
        assert exc_info.value.context_vars == ("x",)

    def test_can_be_caught_as_expression_error(self) -> None:
        """Test that ExpressionEvaluationError can be caught as ExpressionError."""
        with pytest.raises(ExpressionError):
            raise ExpressionEvaluationError("Test", expression="test")

    def test_empty_context_vars(self) -> None:
        """Test error message with empty context variables."""
        error = ExpressionEvaluationError(
            "Undefined variable",
            expression="unknown",
            context_vars=(),
        )
        error_str = str(error)
        assert "Undefined variable in expression: unknown" in error_str
        assert "Available variables:" not in error_str

    def test_context_vars_attribute_accessible(self) -> None:
        """Test that context_vars attribute is accessible."""
        error = ExpressionEvaluationError(
            "Test",
            expression="test",
            context_vars=("a", "b"),
        )
        assert hasattr(error, "context_vars")
        assert error.context_vars == ("a", "b")

    def test_single_context_var(self) -> None:
        """Test error message with single context variable."""
        error = ExpressionEvaluationError(
            "Type mismatch",
            expression="x + y",
            context_vars=("x",),
        )
        error_str = str(error)
        assert "Available variables: x" in error_str


class TestExpressionErrorInfo:
    """Test suite for ExpressionErrorInfo frozen dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating ExpressionErrorInfo with all fields."""
        info = ExpressionErrorInfo(
            expression="x + y",
            message="Syntax error",
            position=3,
        )
        assert info.expression == "x + y"
        assert info.message == "Syntax error"
        assert info.position == 3

    def test_creation_with_default_position(self) -> None:
        """Test creating ExpressionErrorInfo with default position."""
        info = ExpressionErrorInfo(
            expression="test",
            message="Error message",
        )
        assert info.expression == "test"
        assert info.message == "Error message"
        assert info.position == 0

    def test_is_frozen(self) -> None:
        """Test that ExpressionErrorInfo is immutable (frozen)."""
        info = ExpressionErrorInfo(
            expression="test",
            message="error",
        )
        # Dataclass is frozen, so assignment should raise an error
        with pytest.raises((AttributeError, TypeError)):
            info.expression = "modified"

    def test_all_fields_accessible(self) -> None:
        """Test that all fields are accessible."""
        info = ExpressionErrorInfo(
            expression="foo + bar",
            message="Invalid operation",
            position=5,
        )
        assert hasattr(info, "expression")
        assert hasattr(info, "message")
        assert hasattr(info, "position")
        assert info.expression == "foo + bar"
        assert info.message == "Invalid operation"
        assert info.position == 5

    def test_equality(self) -> None:
        """Test that ExpressionErrorInfo instances can be compared."""
        info1 = ExpressionErrorInfo(
            expression="test",
            message="error",
            position=1,
        )
        info2 = ExpressionErrorInfo(
            expression="test",
            message="error",
            position=1,
        )
        info3 = ExpressionErrorInfo(
            expression="different",
            message="error",
            position=1,
        )
        assert info1 == info2
        assert info1 != info3

    def test_hashable(self) -> None:
        """Test that ExpressionErrorInfo is hashable."""
        info1 = ExpressionErrorInfo(expression="test", message="error")
        info2 = ExpressionErrorInfo(expression="test", message="error")

        # Should be able to use in sets and as dict keys
        error_set = {info1, info2}
        assert len(error_set) == 1  # Same values, same hash

        error_dict = {info1: "value"}
        assert error_dict[info2] == "value"

    def test_repr(self) -> None:
        """Test that ExpressionErrorInfo has useful repr."""
        info = ExpressionErrorInfo(
            expression="x + y",
            message="Test error",
            position=2,
        )
        repr_str = repr(info)
        assert "ExpressionErrorInfo" in repr_str
        assert "x + y" in repr_str
        assert "Test error" in repr_str
        assert "2" in repr_str

    def test_zero_position(self) -> None:
        """Test ExpressionErrorInfo with position zero."""
        info = ExpressionErrorInfo(
            expression="expr",
            message="msg",
            position=0,
        )
        assert info.position == 0

    def test_large_position(self) -> None:
        """Test ExpressionErrorInfo with large position value."""
        info = ExpressionErrorInfo(
            expression="very long expression",
            message="error at end",
            position=100,
        )
        assert info.position == 100


class TestExceptionHierarchy:
    """Test suite for exception inheritance hierarchy."""

    def test_all_expression_errors_inherit_from_expression_error(self) -> None:
        """Test that all expression exception types inherit from ExpressionError."""
        syntax_error = ExpressionSyntaxError("test", expression="test")
        eval_error = ExpressionEvaluationError("test", expression="test")

        assert isinstance(syntax_error, ExpressionError)
        assert isinstance(eval_error, ExpressionError)

    def test_all_expression_errors_inherit_from_maverick_error(self) -> None:
        """Test that all expression exception types inherit from MaverickError."""
        base_error = ExpressionError("test")
        syntax_error = ExpressionSyntaxError("test", expression="test")
        eval_error = ExpressionEvaluationError("test", expression="test")

        assert isinstance(base_error, MaverickError)
        assert isinstance(syntax_error, MaverickError)
        assert isinstance(eval_error, MaverickError)

    def test_can_catch_all_as_expression_error(self) -> None:
        """Test that all expression errors can be caught as ExpressionError."""
        errors = [
            ExpressionError("base error"),
            ExpressionSyntaxError("syntax", expression="test"),
            ExpressionEvaluationError("eval", expression="test"),
        ]

        for error in errors:
            with pytest.raises(ExpressionError):
                raise error

    def test_can_catch_all_as_maverick_error(self) -> None:
        """Test that all expression errors can be caught as MaverickError."""
        errors = [
            ExpressionError("base error"),
            ExpressionSyntaxError("syntax", expression="test"),
            ExpressionEvaluationError("eval", expression="test"),
        ]

        for error in errors:
            with pytest.raises(MaverickError):
                raise error

    def test_specific_error_types_are_distinct(self) -> None:
        """Test that specific error types can be distinguished."""
        syntax_error = ExpressionSyntaxError("test", expression="test")
        eval_error = ExpressionEvaluationError("test", expression="test")

        assert not isinstance(syntax_error, ExpressionEvaluationError)
        assert not isinstance(eval_error, ExpressionSyntaxError)


class TestErrorUsagePatterns:
    """Test suite for common error usage patterns."""

    def test_catch_specific_then_general(self) -> None:
        """Test catching specific error before general error."""

        def raise_syntax_error() -> None:
            raise ExpressionSyntaxError("bad syntax", expression="x +")

        # Should catch as specific type
        with pytest.raises(ExpressionSyntaxError):
            raise_syntax_error()

        # Should also catch as general type
        with pytest.raises(ExpressionError):
            raise_syntax_error()

    def test_error_context_preservation(self) -> None:
        """Test that error context is preserved through catch/raise."""
        try:
            raise ExpressionSyntaxError(
                "Invalid token",
                expression="foo + + bar",
                position=6,
            )
        except ExpressionError as e:
            assert e.expression == "foo + + bar"
            assert isinstance(e, ExpressionSyntaxError)
            assert e.position == 6

    def test_creating_error_info_from_exception(self) -> None:
        """Test creating ExpressionErrorInfo from exception data."""
        error = ExpressionSyntaxError(
            "Syntax error",
            expression="test + + value",
            position=7,
        )

        # Create info object from exception
        # Note: error.message contains the formatted message with position indicator
        info = ExpressionErrorInfo(
            expression=error.expression or "",
            message=error.message,
            position=error.position,
        )

        assert info.expression == "test + + value"
        # The message is formatted with position context
        assert "Syntax error" in info.message
        assert "position 7" in info.message
        assert info.position == 7

    def test_multiple_errors_in_sequence(self) -> None:
        """Test handling multiple different error types."""
        errors_raised = []

        try:
            raise ExpressionSyntaxError("syntax", expression="test")
        except ExpressionError as e:
            errors_raised.append(type(e).__name__)

        try:
            raise ExpressionEvaluationError("eval", expression="test")
        except ExpressionError as e:
            errors_raised.append(type(e).__name__)

        assert errors_raised == ["ExpressionSyntaxError", "ExpressionEvaluationError"]
