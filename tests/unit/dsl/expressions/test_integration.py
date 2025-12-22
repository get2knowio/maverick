"""Integration tests for expression parser and evaluator.

This module contains tests that demonstrate the complete workflow of parsing
and evaluating expressions, showing the integration between the parser and
evaluator components.
"""

from __future__ import annotations

import pytest

from maverick.dsl.expressions import (
    ExpressionEvaluationError,
    ExpressionEvaluator,
    parse_expression,
)


class TestParseAndEvaluate:
    """Test the complete parse-and-evaluate workflow."""

    def test_simple_input_expression(self) -> None:
        """Parse and evaluate a simple input expression."""
        # Parse the expression
        expr = parse_expression("${{ inputs.name }}")

        # Create evaluator with context
        evaluator = ExpressionEvaluator(
            inputs={"name": "Alice"},
            step_outputs={},
        )

        # Evaluate the expression
        result = evaluator.evaluate(expr)
        assert result == "Alice"

    def test_simple_step_expression(self) -> None:
        """Parse and evaluate a simple step output expression."""
        expr = parse_expression("${{ steps.analyze.output }}")

        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={"analyze": {"output": "analysis complete"}},
        )

        result = evaluator.evaluate(expr)
        assert result == "analysis complete"

    def test_nested_field_expression(self) -> None:
        """Parse and evaluate a nested field expression."""
        expr = parse_expression("${{ steps.fetch.output.data.count }}")

        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "fetch": {
                    "output": {
                        "data": {
                            "count": 42,
                        }
                    }
                }
            },
        )

        result = evaluator.evaluate(expr)
        assert result == 42

    def test_negated_expression(self) -> None:
        """Parse and evaluate a negated expression."""
        expr = parse_expression("${{ not inputs.dry_run }}")

        evaluator = ExpressionEvaluator(
            inputs={"dry_run": False},
            step_outputs={},
        )

        result = evaluator.evaluate(expr)
        assert result is True

    def test_array_index_expression(self) -> None:
        """Parse and evaluate an array index expression."""
        expr = parse_expression("${{ inputs.items[2] }}")

        evaluator = ExpressionEvaluator(
            inputs={"items": ["a", "b", "c", "d"]},
            step_outputs={},
        )

        result = evaluator.evaluate(expr)
        assert result == "c"

    def test_template_string_evaluation(self) -> None:
        """Parse and evaluate multiple expressions in a template string."""
        evaluator = ExpressionEvaluator(
            inputs={"user": "Bob", "count": 5},
            step_outputs={
                "process": {
                    "output": {
                        "status": "complete",
                    }
                }
            },
        )

        template = (
            "User ${{ inputs.user }} processed ${{ inputs.count }} items. "
            "Status: ${{ steps.process.output.status }}"
        )

        result = evaluator.evaluate_string(template)
        assert result == "User Bob processed 5 items. Status: complete"

    def test_complex_workflow_scenario(self) -> None:
        """Simulate a realistic workflow scenario with multiple steps."""
        # Simulate workflow context
        inputs = {
            "repo": "maverick",
            "branch": "main",
            "dry_run": False,
        }

        step_outputs = {
            "clone": {
                "output": {
                    "path": "/tmp/maverick",
                    "commit": "abc123",
                }
            },
            "analyze": {
                "output": {
                    "files_changed": 12,
                    "tests_passed": True,
                }
            },
            "validate": {
                "output": {
                    "errors": [],
                    "warnings": ["line too long in file.py"],
                }
            },
        }

        evaluator = ExpressionEvaluator(
            inputs=inputs,
            step_outputs=step_outputs,
        )

        # Evaluate various expressions from the workflow
        assert evaluator.evaluate(parse_expression("${{ inputs.repo }}")) == "maverick"
        assert (
            evaluator.evaluate(parse_expression("${{ steps.clone.output.commit }}"))
            == "abc123"
        )
        expr = parse_expression("${{ steps.analyze.output.files_changed }}")
        assert evaluator.evaluate(expr) == 12

        expr = parse_expression("${{ steps.analyze.output.tests_passed }}")
        assert evaluator.evaluate(expr) is True
        assert evaluator.evaluate(parse_expression("${{ not inputs.dry_run }}")) is True

        # Evaluate template strings
        message = evaluator.evaluate_string(
            "Analyzed ${{ inputs.repo }} on branch ${{ inputs.branch }}: "
            "${{ steps.analyze.output.files_changed }} files changed"
        )
        assert message == "Analyzed maverick on branch main: 12 files changed"

    def test_error_handling_integration(self) -> None:
        """Test that parser and evaluator errors work together."""
        evaluator = ExpressionEvaluator(
            inputs={"name": "Alice"},
            step_outputs={},
        )

        # Parse valid expression but evaluate with missing key
        expr = parse_expression("${{ inputs.missing }}")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)

        assert "missing" in str(exc_info.value)
        assert "inputs" in str(exc_info.value)

    def test_bracket_notation_dict_access(self) -> None:
        """Parse and evaluate bracket notation for dict access."""
        expr = parse_expression("${{ steps.fetch.output['user-name'] }}")

        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "fetch": {
                    "output": {
                        "user-name": "john_doe",
                    }
                }
            },
        )

        result = evaluator.evaluate(expr)
        assert result == "john_doe"

    def test_deeply_nested_with_mixed_access(self) -> None:
        """Parse and evaluate deeply nested path with mixed dot and bracket notation."""
        expr = parse_expression("${{ steps.api.output.users[0].name }}")

        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "api": {
                    "output": {
                        "users": [
                            {"name": "Alice", "age": 30},
                            {"name": "Bob", "age": 25},
                        ]
                    }
                }
            },
        )

        result = evaluator.evaluate(expr)
        assert result == "Alice"


class TestRealWorldUseCases:
    """Test real-world use cases for expression evaluation."""

    def test_conditional_message_generation(self) -> None:
        """Generate conditional messages based on workflow state."""
        evaluator = ExpressionEvaluator(
            inputs={"notify": True, "channel": "slack"},
            step_outputs={
                "test": {"output": {"passed": True, "count": 42}},
            },
        )

        # Simulate conditional logic (would be done by workflow engine)
        should_notify = evaluator.evaluate(parse_expression("${{ inputs.notify }}"))

        if should_notify:
            message = evaluator.evaluate_string(
                "Tests passed: ${{ steps.test.output.passed }}, "
                "count: ${{ steps.test.output.count }}"
            )
            assert message == "Tests passed: True, count: 42"

    def test_dynamic_file_path_generation(self) -> None:
        """Generate dynamic file paths from workflow context."""
        evaluator = ExpressionEvaluator(
            inputs={
                "project": "maverick",
                "version": "1.0.0",
            },
            step_outputs={
                "build": {
                    "output": {
                        "timestamp": "20250115",
                    }
                }
            },
        )

        path = evaluator.evaluate_string(
            "/artifacts/${{ inputs.project }}-${{ inputs.version }}-"
            "${{ steps.build.output.timestamp }}.tar.gz"
        )

        assert path == "/artifacts/maverick-1.0.0-20250115.tar.gz"

    def test_error_message_formatting(self) -> None:
        """Format error messages with context from workflow."""
        evaluator = ExpressionEvaluator(
            inputs={"file": "test.py"},
            step_outputs={
                "lint": {
                    "output": {
                        "errors": 3,
                        "warnings": 5,
                    }
                }
            },
        )

        error_msg = evaluator.evaluate_string(
            "Linting failed for ${{ inputs.file }}: "
            "${{ steps.lint.output.errors }} errors, "
            "${{ steps.lint.output.warnings }} warnings"
        )

        assert error_msg == "Linting failed for test.py: 3 errors, 5 warnings"

    def test_multi_step_pipeline_data_flow(self) -> None:
        """Simulate data flowing through a multi-step pipeline."""
        evaluator = ExpressionEvaluator(
            inputs={
                "source": "github.com/user/repo",
            },
            step_outputs={
                "fetch": {
                    "output": {
                        "files": ["file1.py", "file2.py"],
                    }
                },
                "analyze": {
                    "output": {
                        "complexity": {"file1.py": 5, "file2.py": 8},
                    }
                },
                "report": {
                    "output": {
                        "summary": "Analysis complete",
                    }
                },
            },
        )

        # Access data from different pipeline stages
        source = evaluator.evaluate(parse_expression("${{ inputs.source }}"))
        files = evaluator.evaluate(parse_expression("${{ steps.fetch.output.files }}"))
        first_file = evaluator.evaluate(
            parse_expression("${{ steps.fetch.output.files[0] }}")
        )
        summary = evaluator.evaluate(
            parse_expression("${{ steps.report.output.summary }}")
        )

        assert source == "github.com/user/repo"
        assert files == ["file1.py", "file2.py"]
        assert first_file == "file1.py"
        assert summary == "Analysis complete"
