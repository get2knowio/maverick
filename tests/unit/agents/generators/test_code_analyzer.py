"""Unit tests for CodeAnalyzer generator."""

from __future__ import annotations

from unittest.mock import patch

from maverick.agents.generators.base import DEFAULT_MODEL, MAX_SNIPPET_SIZE
from maverick.agents.generators.code_analyzer import CodeAnalyzer


class TestCodeAnalyzerConstruction:
    """Tests for CodeAnalyzer construction."""

    def test_construction_with_defaults(self) -> None:
        """Test successful construction with default model."""
        analyzer = CodeAnalyzer()

        assert analyzer.name == "code-analyzer"
        assert analyzer.model == DEFAULT_MODEL

    def test_construction_with_custom_model(self) -> None:
        """Test construction with custom model."""
        analyzer = CodeAnalyzer(model="claude-opus-4-5-20250929")

        assert analyzer.model == "claude-opus-4-5-20250929"


class TestCodeAnalyzerPromptBuilding:
    """Tests for CodeAnalyzer.build_prompt() method."""

    def test_prompt_includes_code(self) -> None:
        """Test that the code is included in the prompt."""
        analyzer = CodeAnalyzer()

        code = "def factorial(n): return 1 if n == 0 else n * factorial(n-1)"
        prompt = analyzer.build_prompt({"code": code, "analysis_type": "explain"})

        assert "factorial" in prompt

    def test_explain_prompt_includes_explain_instruction(self) -> None:
        """Test that explain analysis type produces correct instruction."""
        analyzer = CodeAnalyzer()

        prompt = analyzer.build_prompt(
            {"code": "print('hello')", "analysis_type": "explain"}
        )

        assert "explain" in prompt.lower()

    def test_review_prompt_includes_review_instruction(self) -> None:
        """Test that review analysis type produces correct instruction."""
        analyzer = CodeAnalyzer()

        prompt = analyzer.build_prompt(
            {"code": "print('hello')", "analysis_type": "review"}
        )

        assert "review" in prompt.lower()

    def test_summarize_prompt_includes_summarize_instruction(self) -> None:
        """Test that summarize analysis type produces correct instruction."""
        analyzer = CodeAnalyzer()

        prompt = analyzer.build_prompt(
            {"code": "print('hello')", "analysis_type": "summarize"}
        )

        assert "summar" in prompt.lower()

    def test_invalid_analysis_type_defaults_to_explain(self) -> None:
        """Test that invalid analysis_type defaults to 'explain' mode."""
        analyzer = CodeAnalyzer()

        prompt = analyzer.build_prompt(
            {"code": "print('hello')", "analysis_type": "invalid_type"}
        )

        # Should produce explain-type prompt
        assert "explain" in prompt.lower()
        assert "invalid_type" not in prompt

    def test_missing_analysis_type_defaults_to_explain(self) -> None:
        """Test that missing analysis_type defaults to 'explain'."""
        analyzer = CodeAnalyzer()

        prompt = analyzer.build_prompt({"code": "print('hello')"})

        assert "explain" in prompt.lower()

    def test_language_hint_appears_in_prompt(self) -> None:
        """Test that optional language parameter is included in prompt."""
        analyzer = CodeAnalyzer()

        prompt = analyzer.build_prompt(
            {
                "code": "def hello(): pass",
                "analysis_type": "explain",
                "language": "Python",
            }
        )

        assert "python" in prompt.lower()

    def test_empty_code_produces_prompt(self) -> None:
        """Test that empty code still produces a prompt (no build_prompt validation)."""
        analyzer = CodeAnalyzer()

        prompt = analyzer.build_prompt({"code": "", "analysis_type": "explain"})

        assert isinstance(prompt, str)

    def test_truncation_at_10kb_with_warning(self) -> None:
        """Test that code exceeding MAX_SNIPPET_SIZE is truncated with warning."""
        analyzer = CodeAnalyzer()

        # Create code larger than MAX_SNIPPET_SIZE
        large_code = "# " + ("x" * MAX_SNIPPET_SIZE)

        with patch("maverick.agents.generators.base.logger") as mock_logger:
            prompt = analyzer.build_prompt(
                {"code": large_code, "analysis_type": "explain"}
            )

            # Should log a WARNING about truncation
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "code" in str(call_args).lower()

        assert len(prompt) > 0

    def test_truncation_logs_at_warning_level(self) -> None:
        """Test that truncation is logged at WARNING level per FR-017."""
        analyzer = CodeAnalyzer()

        # Create oversized code
        large_code = "x" * (MAX_SNIPPET_SIZE + 1000)

        with patch("maverick.agents.generators.base.logger") as mock_logger:
            analyzer.build_prompt({"code": large_code, "analysis_type": "explain"})

            # Verify WARNING was called for truncation
            assert mock_logger.warning.called
            warning_msg = str(mock_logger.warning.call_args)
            assert "truncat" in warning_msg.lower()
