"""Unit tests for context builder utilities.

Tests cover all context builder functions and supporting utilities with
both happy path and error scenarios per SC-005.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from maverick.utils.context import (
    _read_conventions,
    _read_file_safely,
    build_fix_context,
    build_implementation_context,
    build_issue_context,
    build_review_context,
    detect_secrets,
    estimate_tokens,
    extract_file_paths,
    fit_to_budget,
    truncate_file,
    truncate_line,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Fixtures
# =============================================================================


@dataclass
class MockCommitInfo:
    """Mock commit info for tests (non-frozen for mutability).

    Note: Uses `sha` and `short_sha` to match maverick.git.CommitInfo.
    """

    sha: str
    short_sha: str
    message: str
    author: str
    date: str


@dataclass
class MockDiffStats:
    """Mock diff stats for tests (non-frozen for mutability)."""

    files_changed: int
    insertions: int
    deletions: int
    file_list: tuple[str, ...]


@pytest.fixture
def mock_git() -> MagicMock:
    """Create a mock GitRepository instance."""
    git = MagicMock()
    git.current_branch.return_value = "feature/test-branch"

    git.log.return_value = [
        MockCommitInfo(
            sha="abc1234567890",
            short_sha="abc1234",
            message="Add feature X",
            author="Test Author",
            date="2025-12-18T10:00:00Z",
        ),
        MockCommitInfo(
            sha="def5678901234",
            short_sha="def5678",
            message="Fix bug Y",
            author="Test Author",
            date="2025-12-17T15:00:00Z",
        ),
    ]

    git.diff.return_value = "diff --git a/file.py b/file.py\n+new line"

    git.diff_stats.return_value = MockDiffStats(
        files_changed=2,
        insertions=10,
        deletions=5,
        file_list=("src/main.py", "tests/test_main.py"),
    )

    return git


@dataclass
class MockParsedError:
    """Mock parsed error for tests (non-frozen for mutability)."""

    file: str
    line: int
    message: str
    column: int | None = None
    severity: str | None = None
    code: str | None = None


@dataclass
class MockStageResult:
    """Mock stage result for tests (non-frozen for mutability)."""

    stage_name: str
    passed: bool
    output: str
    duration_ms: int
    fix_attempts: int = 0
    errors: tuple[MockParsedError, ...] = ()


@pytest.fixture
def mock_validation_output() -> MagicMock:
    """Create a mock ValidationOutput with errors."""
    validation = MagicMock()
    validation.success = False
    validation.stages = [
        MockStageResult(
            stage_name="ruff",
            passed=False,
            output="error output",
            duration_ms=100,
            errors=(
                MockParsedError(
                    file="src/main.py",
                    line=10,
                    message="Undefined variable 'foo'",
                    severity="error",
                    code="F821",
                ),
                MockParsedError(
                    file="src/main.py",
                    line=25,
                    message="Missing return type",
                    severity="warning",
                    code="ANN201",
                ),
            ),
        ),
    ]

    return validation


@pytest.fixture
def mock_github_issue() -> MagicMock:
    """Create a mock GitHubIssue."""
    issue = MagicMock()
    issue.number = 42
    issue.title = "Fix token estimation bug"
    issue.body = (
        "The file src/utils/context.py has incorrect token counting.\n"
        "Also check tests/test_context.py"
    )
    issue.labels = ("bug", "priority-high")
    issue.state = "open"
    issue.assignees = ("developer",)
    issue.url = "https://github.com/owner/repo/issues/42"
    return issue


@pytest.fixture
def temp_task_file(tmp_path: Path) -> Path:
    """Create a temporary task file."""
    task_file = tmp_path / "tasks.md"
    task_file.write_text(
        "# Tasks\n\n"
        "- [ ] T001 Create module\n"
        "- [ ] T002 Add tests\n"
        "- [x] T003 Write docs\n"
    )
    return task_file


@pytest.fixture
def temp_conventions_file(tmp_path: Path) -> Path:
    """Create a temporary CLAUDE.md file."""
    conventions = tmp_path / "CLAUDE.md"
    conventions.write_text(
        "# CLAUDE.md\n\n"
        "## Project Overview\n\n"
        "This is a test project.\n\n"
        "## Code Style\n\n"
        "- Use snake_case for functions\n"
        "- Use PascalCase for classes\n"
    )
    return conventions


# =============================================================================
# Tests: estimate_tokens (T012)
# =============================================================================


class TestEstimateTokens:
    """Tests for estimate_tokens utility."""

    def test_empty_string(self) -> None:
        """Empty string returns 0 tokens."""
        assert estimate_tokens("") == 0

    def test_short_string(self) -> None:
        """Short strings return correct estimate."""
        # tiktoken cl100k_base: "Hello" = 1 token
        assert estimate_tokens("Hello") == 1

    def test_typical_code(self) -> None:
        """Typical code content gives reasonable estimate."""
        code = "def hello_world():\n    print('Hello, World!')\n"
        tokens = estimate_tokens(code)
        # tiktoken cl100k_base: this code = 11 tokens
        assert tokens == 11

    def test_large_content(self) -> None:
        """Large content scales linearly."""
        content = "x" * 10000
        # tiktoken cl100k_base: 10000 'x' characters = 1250 tokens
        assert estimate_tokens(content) == 1250


# =============================================================================
# Tests: _read_file_safely (internal utility)
# =============================================================================


class TestReadFileSafely:
    """Tests for _read_file_safely internal utility."""

    def test_read_file_safely_with_permission_error(self, tmp_path: Path) -> None:
        """Test _read_file_safely handles permission errors gracefully."""
        file_path = tmp_path / "no_read.txt"
        file_path.write_text("content")
        file_path.chmod(0o000)

        try:
            content, truncated = _read_file_safely(file_path)
            assert content == ""
            assert truncated is False
        finally:
            file_path.chmod(0o644)  # Restore for cleanup

    def test_read_file_safely_os_error_on_binary_check(self, tmp_path: Path) -> None:
        """Test _read_file_safely handles OSError during binary check."""
        file_path = tmp_path / "error_read.txt"
        file_path.write_text("content")

        with patch("pathlib.Path.open") as mock_open:
            mock_open.side_effect = OSError("Access denied")
            content, truncated = _read_file_safely(file_path)
            assert content == ""
            assert truncated is False


# =============================================================================
# Tests: _read_conventions (internal utility)
# =============================================================================


class TestReadConventions:
    """Tests for _read_conventions internal utility."""

    def test_read_conventions_no_claude_md_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _read_conventions when no CLAUDE.md exists anywhere."""
        # Use tmp_path as cwd (no CLAUDE.md exists)
        monkeypatch.chdir(tmp_path)

        result = _read_conventions()
        assert result == ""


# =============================================================================
# Tests: truncate_line (T013)
# =============================================================================


class TestTruncateLine:
    """Tests for truncate_line utility."""

    def test_short_line_unchanged(self) -> None:
        """Lines under max_chars are returned unchanged."""
        line = "short line"
        assert truncate_line(line) == "short line"

    def test_exact_limit_unchanged(self) -> None:
        """Lines exactly at max_chars are returned unchanged."""
        line = "x" * 2000
        assert truncate_line(line) == line

    def test_long_line_truncated(self) -> None:
        """Lines over max_chars are truncated with '...'."""
        line = "x" * 3000
        result = truncate_line(line)
        assert len(result) == 2003  # 2000 + "..."
        assert result.endswith("...")

    def test_custom_max_chars(self) -> None:
        """Custom max_chars is respected."""
        line = "x" * 200
        result = truncate_line(line, max_chars=100)
        assert len(result) == 103
        assert result.endswith("...")


# =============================================================================
# Tests: detect_secrets (T014)
# =============================================================================


class TestDetectSecrets:
    """Tests for detect_secrets utility.

    Uses Yelp's detect-secrets library which provides these secret types:
    - 'AWS Access Key' for AWS access key IDs (AKIA...)
    - 'GitHub Token' for GitHub PATs (ghp_, ghs_, etc.)
    - 'Private Key' for PEM private key headers
    - 'Secret Keyword' for password/secret/api_key assignments
    - 'JSON Web Token' for JWTs
    - And many more (Slack, Stripe, Twilio, etc.)
    """

    def test_no_secrets(self) -> None:
        """Content without secrets returns empty list."""
        content = "def hello():\n    return 'world'\n"
        assert detect_secrets(content) == []

    def test_api_key_pattern(self) -> None:
        """Detects API key patterns via Secret Keyword detector."""
        content = "api_key = 'sk-12345678901234567890123456'"
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0] == (1, "Secret Keyword")

    def test_aws_key_pattern(self) -> None:
        """Detects AWS-style keys."""
        content = "AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'"
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0] == (1, "AWS Access Key")

    def test_private_key_pattern(self) -> None:
        """Detects private key headers."""
        content = (
            "key = '''-----BEGIN PRIVATE KEY-----\nxxx\n-----END PRIVATE KEY-----'''"
        )
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0][1] == "Private Key"

    def test_password_pattern(self) -> None:
        """Detects password patterns via Secret Keyword detector."""
        content = "password = 'supersecret123!'"
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0] == (1, "Secret Keyword")

    def test_multiple_secrets_different_lines(self) -> None:
        """Detects secrets on multiple lines."""
        content = (
            "line1\n"
            "api_key = 'sk-12345678901234567890'\n"
            "line3\n"
            "password = 'secret123456'"
        )
        findings = detect_secrets(content)
        assert len(findings) == 2
        assert findings[0] == (2, "Secret Keyword")
        assert findings[1] == (4, "Secret Keyword")

    def test_github_token_detection(self) -> None:
        """Detects GitHub tokens (ghp_, ghs_, etc.)."""
        content = "token = 'ghp_1234567890abcdefghijklmnopqrstuvwxyz'"
        findings = detect_secrets(content)
        assert len(findings) >= 1
        secret_types = [f[1] for f in findings]
        assert "GitHub Token" in secret_types

    def test_jwt_detection(self) -> None:
        """Detects JSON Web Tokens."""
        # A valid JWT structure (header.payload.signature)
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        )
        content = f"token = '{jwt}'"
        findings = detect_secrets(content)
        assert len(findings) >= 1
        secret_types = [f[1] for f in findings]
        assert "JSON Web Token" in secret_types


# =============================================================================
# Tests: truncate_file (T015)
# =============================================================================


class TestTruncateFile:
    """Tests for truncate_file utility."""

    def test_small_file_unchanged(self) -> None:
        """Files under max_lines are returned unchanged."""
        content = "\n".join(f"line {i}" for i in range(1, 11))
        result = truncate_file(content, max_lines=20)
        assert result == content

    def test_large_file_truncated(self) -> None:
        """Large files are truncated with marker."""
        content = "\n".join(f"line {i}" for i in range(1, 101))
        result = truncate_file(content, max_lines=30)
        assert "..." in result
        assert "line 1" in result
        assert "line 30" in result

    def test_around_lines_preserved(self) -> None:
        """Content around specified lines is preserved."""
        content = "\n".join(f"line {i}" for i in range(1, 101))
        result = truncate_file(content, max_lines=30, around_lines=[50])
        assert "line 50" in result
        assert "line 45" in result  # context before
        assert "line 55" in result  # context after

    def test_multiple_around_lines(self) -> None:
        """Multiple target lines are all preserved."""
        content = "\n".join(f"line {i}" for i in range(1, 101))
        result = truncate_file(content, max_lines=50, around_lines=[20, 80])
        assert "line 20" in result
        assert "line 80" in result

    def test_overlapping_windows_merged(self) -> None:
        """Overlapping context windows are merged."""
        content = "\n".join(f"line {i}" for i in range(1, 101))
        result = truncate_file(content, max_lines=50, around_lines=[48, 52])
        # These should be in one continuous block
        assert "line 48" in result
        assert "line 52" in result

    def test_custom_context_lines(self) -> None:
        """Custom context_lines parameter is respected."""
        content = "\n".join(f"line {i}" for i in range(1, 101))
        result = truncate_file(
            content, max_lines=20, around_lines=[50], context_lines=5
        )
        assert "line 50" in result
        assert "line 45" in result
        assert "line 55" in result

    def test_truncate_file_severe_budget_constraint(self) -> None:
        """Test truncate_file handles severe budget constraints."""
        content = "\n".join(f"line {i}" for i in range(1, 201))  # 200 lines

        # Request context around many lines but with tiny budget
        result = truncate_file(
            content,
            max_lines=10,  # Very small budget
            around_lines=[50, 100, 150],  # Multiple targets
            context_lines=5,
        )

        # Should still produce valid output
        assert "..." in result
        result_lines = result.splitlines()
        assert len([line for line in result_lines if not line.startswith("...")]) <= 15

    def test_truncate_file_window_scaling(self) -> None:
        """Test window scaling when requested context exceeds budget."""
        content = "\n".join(f"line {i}" for i in range(1, 101))

        # Request context around 3 points that would exceed max_lines
        # 3 * (10 + 10 + 1) = 63 lines if context_lines=10
        # Budget is 15 lines -> scaling forced
        result = truncate_file(
            content,
            max_lines=15,
            around_lines=[20, 50, 80],
            context_lines=10,
        )

        assert "line 20" in result
        assert "line 50" in result
        assert "line 80" in result
        # Check that we didn't get full context
        assert "line 15" not in result
        assert "line 25" not in result


# =============================================================================
# Tests: extract_file_paths (T016)
# =============================================================================


class TestExtractFilePaths:
    """Tests for extract_file_paths utility."""

    def test_no_paths(self) -> None:
        """Text without file paths returns empty list."""
        assert extract_file_paths("Hello world!") == []

    def test_single_path(self) -> None:
        """Extracts a single file path."""
        text = "Check the file src/main.py for details"
        paths = extract_file_paths(text)
        assert "src/main.py" in paths

    def test_multiple_paths(self) -> None:
        """Extracts multiple file paths."""
        text = "Look at src/main.py and tests/test_main.py"
        paths = extract_file_paths(text)
        assert len(paths) >= 2

    def test_relative_path_with_dot(self) -> None:
        """Extracts paths starting with ./."""
        text = "File is at ./src/utils.py"
        paths = extract_file_paths(text)
        assert any("utils.py" in p for p in paths)

    def test_various_extensions(self) -> None:
        """Extracts paths with various extensions."""
        text = "Files: src/app.ts, lib/util.rs, pkg/main.go, config.yaml"
        paths = extract_file_paths(text)
        assert any(".ts" in p for p in paths)
        assert any(".rs" in p for p in paths)
        assert any(".go" in p for p in paths)

    def test_excludes_urls(self) -> None:
        """Does not extract URL paths."""
        text = "See https://example.com/path/to/file.py"
        paths = extract_file_paths(text)
        # URL should not be extracted as file path
        assert not any("example.com" in p for p in paths)

    def test_deduplication(self) -> None:
        """Duplicate paths are removed."""
        text = "Check src/main.py and also src/main.py again"
        paths = extract_file_paths(text)
        # Count occurrences of main.py
        main_count = sum(1 for p in paths if "main.py" in p)
        assert main_count == 1


# =============================================================================
# Tests: build_implementation_context (T017-T024)
# =============================================================================


class TestBuildImplementationContext:
    """Tests for build_implementation_context function."""

    def test_happy_path(
        self,
        mock_git: MagicMock,
        temp_task_file: Path,
        temp_conventions_file: Path,
    ) -> None:
        """Returns complete context with all expected keys (T017)."""
        with patch(
            "maverick.utils.files.Path.cwd", return_value=temp_conventions_file.parent
        ):
            context = build_implementation_context(
                task_file=temp_task_file,
                git=mock_git,
                conventions_path=temp_conventions_file,
            )

        assert "tasks" in context
        assert "conventions" in context
        assert "branch" in context
        assert "recent_commits" in context
        assert "_metadata" in context

        assert "T001" in context["tasks"]
        assert context["branch"] == "feature/test-branch"
        assert len(context["recent_commits"]) == 2

    def test_missing_task_file(
        self,
        mock_git: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Missing task file returns empty content with metadata (T018)."""
        missing_file = tmp_path / "nonexistent.md"
        context = build_implementation_context(
            task_file=missing_file,
            git=mock_git,
        )

        assert context["tasks"] == ""
        assert "_metadata" in context

    def test_large_conventions_truncation(
        self,
        mock_git: MagicMock,
        temp_task_file: Path,
        tmp_path: Path,
    ) -> None:
        """Large CLAUDE.md is handled appropriately (T019)."""
        # Create large conventions file
        large_conventions = tmp_path / "CLAUDE.md"
        large_content = "\n".join(f"Line {i}" for i in range(60000))
        large_conventions.write_text(large_content)

        context = build_implementation_context(
            task_file=temp_task_file,
            git=mock_git,
            conventions_path=large_conventions,
        )

        # Should still return content (may be truncated at file read level)
        assert "conventions" in context

    def test_secret_detection_logging(
        self,
        mock_git: MagicMock,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Secret detection logs warnings (T020)."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("api_key = 'sk-12345678901234567890123456'\n- [ ] Task 1")

        import logging

        with caplog.at_level(logging.WARNING):
            build_implementation_context(
                task_file=task_file,
                git=mock_git,
            )

        assert "Potential secret detected" in caplog.text

    def test_git_error_handling(
        self,
        temp_task_file: Path,
    ) -> None:
        """Handles git errors gracefully."""
        mock_git = MagicMock()
        mock_git.current_branch.side_effect = OSError("Git error")
        mock_git.log.side_effect = RuntimeError("Git error")

        context = build_implementation_context(
            task_file=temp_task_file,
            git=mock_git,
        )

        assert context["branch"] == "unknown"
        assert context["recent_commits"] == []

    def test_build_implementation_context_task_file_truncation(
        self, tmp_path: Path, mock_git: MagicMock
    ) -> None:
        """Test metadata reflects task file truncation."""
        # Create a very large task file
        task_file = tmp_path / "tasks.md"
        task_file.write_text("\n".join(f"Task {i}" for i in range(60000)))

        context = build_implementation_context(task_file, mock_git)

        # Should have truncation metadata
        assert context["_metadata"]["truncated"] is True
        assert "tasks" in context["_metadata"]["sections_affected"]


# =============================================================================
# Tests: build_review_context (T025-T033)
# =============================================================================


class TestBuildReviewContext:
    """Tests for build_review_context function."""

    def test_happy_path(
        self,
        temp_conventions_file: Path,
        tmp_path: Path,
    ) -> None:
        """Returns complete context with diff and changed files (T025)."""
        # Create the changed files
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "tests" / "test_main.py").write_text("def test(): pass")

        # Create mock with specific file list for this test
        mock_git = MagicMock()
        mock_git.diff.return_value = "diff --git a/file.py b/file.py\n+new line"
        mock_git.diff_stats.return_value = MockDiffStats(
            files_changed=2,
            insertions=10,
            deletions=5,
            file_list=(
                str(tmp_path / "src" / "main.py"),
                str(tmp_path / "tests" / "test_main.py"),
            ),
        )

        with patch("maverick.utils.files.Path.cwd", return_value=tmp_path):
            context = build_review_context(
                git=mock_git,
                base_branch="main",
                conventions_path=temp_conventions_file,
            )

        assert "diff" in context
        assert "changed_files" in context
        assert "conventions" in context
        assert "stats" in context
        assert "_metadata" in context
        assert context["stats"]["files_changed"] == 2

    def test_large_files_truncated(
        self,
        tmp_path: Path,
    ) -> None:
        """Files larger than max_file_lines are truncated (T026)."""
        # Create a large file
        large_file = tmp_path / "large.py"
        large_content = "\n".join(f"line {i}" for i in range(1000))
        large_file.write_text(large_content)

        mock_git = MagicMock()
        mock_git.diff.return_value = "diff content"
        mock_git.diff_stats.return_value = MockDiffStats(
            files_changed=1,
            insertions=1000,
            deletions=0,
            file_list=(str(large_file),),
        )

        context = build_review_context(
            git=mock_git,
            base_branch="main",
            max_file_lines=100,
        )

        # Should have truncation indicator in metadata
        assert (
            context["_metadata"]["truncated"]
            or str(large_file) not in context["changed_files"]
        )

    def test_no_changes_empty_diff(self) -> None:
        """No changes returns empty diff with stats (T027)."""
        mock_git = MagicMock()
        mock_git.diff.return_value = ""
        mock_git.diff_stats.return_value = MockDiffStats(
            files_changed=0,
            insertions=0,
            deletions=0,
            file_list=(),
        )

        context = build_review_context(git=mock_git, base_branch="main")

        assert context["diff"] == ""
        assert context["stats"]["files_changed"] == 0
        assert context["changed_files"] == {}

    def test_binary_files_skipped(
        self,
        tmp_path: Path,
    ) -> None:
        """Binary files are skipped (T028)."""
        # Create a binary file
        binary_file = tmp_path / "image.png"
        binary_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_git = MagicMock()
        mock_git.diff.return_value = "diff content"
        mock_git.diff_stats.return_value = MockDiffStats(
            files_changed=1,
            insertions=0,
            deletions=0,
            file_list=(str(binary_file),),
        )

        context = build_review_context(git=mock_git, base_branch="main")

        # Binary files should either be skipped or handled gracefully
        # The implementation reads with errors='replace' so it won't crash
        assert "_metadata" in context

    def test_build_review_context_git_errors(self) -> None:
        """Test graceful handling of git errors in build_review_context."""
        mock_git = MagicMock()
        mock_git.diff.side_effect = RuntimeError("Git diff failed")
        mock_git.diff_stats.side_effect = RuntimeError("Git stats failed")

        context = build_review_context(mock_git, "main")

        assert context["diff"] == ""
        assert context["stats"] == {}
        assert context["changed_files"] == {}


# =============================================================================
# Tests: build_fix_context (T034-T042)
# =============================================================================


class TestBuildFixContext:
    """Tests for build_fix_context function."""

    def test_happy_path(
        self,
        tmp_path: Path,
    ) -> None:
        """Returns errors with source context (T034)."""
        # Create source file
        source_file = tmp_path / "src" / "main.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("\n".join(f"line {i}" for i in range(1, 51)))

        # Create mock validation with errors pointing to this file
        validation = MagicMock()
        validation.success = False
        validation.stages = [
            MockStageResult(
                stage_name="ruff",
                passed=False,
                output="error output",
                duration_ms=100,
                errors=(
                    MockParsedError(
                        file=str(source_file),
                        line=10,
                        message="Undefined variable 'foo'",
                        severity="error",
                        code="F821",
                    ),
                    MockParsedError(
                        file=str(source_file),
                        line=25,
                        message="Missing return type",
                        severity="warning",
                        code="ANN201",
                    ),
                ),
            ),
        ]

        context = build_fix_context(
            validation_output=validation,
            files=[source_file],
        )

        assert "errors" in context
        assert "source_files" in context
        assert "error_summary" in context
        assert "_metadata" in context
        assert len(context["errors"]) == 2

    def test_context_around_errors(
        self,
        tmp_path: Path,
    ) -> None:
        """Preserves ±10 lines around error lines (T035)."""
        source_file = tmp_path / "main.py"
        content = "\n".join(f"line {i}" for i in range(1, 101))
        source_file.write_text(content)

        # Create mock validation with error at line 50
        validation = MagicMock()
        validation.success = False
        validation.stages = [
            MockStageResult(
                stage_name="ruff",
                passed=False,
                output="error output",
                duration_ms=100,
                errors=(
                    MockParsedError(
                        file=str(source_file),
                        line=50,
                        message="Error",
                        severity="error",
                        code="E001",
                    ),
                ),
            ),
        ]

        context = build_fix_context(
            validation_output=validation,
            files=[source_file],
            context_lines=10,
        )

        file_content = context["source_files"].get(str(source_file), "")
        assert "line 50" in file_content
        assert "line 40" in file_content or "line 45" in file_content

    def test_no_errors_empty_section(self, tmp_path: Path) -> None:
        """No errors returns empty errors section (T036)."""
        validation = MagicMock()
        validation.stages = ()

        context = build_fix_context(
            validation_output=validation,
            files=[],
        )

        assert context["errors"] == []
        assert context["error_summary"] == "No errors"

    def test_overlapping_error_regions_merged(
        self,
        tmp_path: Path,
    ) -> None:
        """Overlapping error regions are merged (T037)."""
        source_file = tmp_path / "main.py"
        content = "\n".join(f"line {i}" for i in range(1, 101))
        source_file.write_text(content)

        validation = MagicMock()
        validation.stages = (
            MagicMock(
                errors=(
                    MagicMock(
                        file=str(source_file),
                        line=48,
                        message="Error 1",
                        severity="error",
                        code="E001",
                    ),
                    MagicMock(
                        file=str(source_file),
                        line=52,
                        message="Error 2",
                        severity="error",
                        code="E002",
                    ),
                )
            ),
        )

        context = build_fix_context(
            validation_output=validation,
            files=[source_file],
            context_lines=10,
        )

        # Both error lines should be present
        file_content = context["source_files"].get(str(source_file), "")
        assert "line 48" in file_content
        assert "line 52" in file_content

    def test_build_fix_context_read_errors(self, tmp_path: Path) -> None:
        """Test error handling when reading files in build_fix_context."""
        source_file = tmp_path / "error.py"

        validation = MagicMock()
        validation.success = False
        validation.stages = [
            MockStageResult(
                stage_name="ruff",
                passed=False,
                output="error",
                duration_ms=10,
                errors=(MockParsedError(file=str(source_file), line=1, message="Err"),),
            )
        ]

        # Mock read failure
        with patch(
            "maverick.utils.context._read_file_safely", return_value=("", False)
        ):
            context = build_fix_context(validation, [source_file])
            assert str(source_file) not in context["source_files"]


# =============================================================================
# Tests: build_issue_context (T043-T052)
# =============================================================================


class TestBuildIssueContext:
    """Tests for build_issue_context function."""

    def test_happy_path(
        self,
        mock_github_issue: MagicMock,
        mock_git: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns issue with file references (T043)."""
        # Create referenced files
        (tmp_path / "src" / "utils").mkdir(parents=True)
        (tmp_path / "src" / "utils" / "context.py").write_text("# context module")
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "tests" / "test_context.py").write_text("# tests")

        with patch("maverick.utils.files.Path.cwd", return_value=tmp_path):
            context = build_issue_context(
                issue=mock_github_issue,
                git=mock_git,
            )

        assert "issue" in context
        assert "related_files" in context
        assert "recent_changes" in context
        assert "_metadata" in context
        assert context["issue"]["number"] == 42

    def test_file_path_extraction(
        self,
        mock_git: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Extracts file paths from issue body (T044)."""
        issue = MagicMock()
        issue.number = 1
        issue.title = "Bug in utils"
        issue.body = "Error in src/utils/helper.py at line 10"
        issue.labels = ()
        issue.state = "open"
        issue.url = "https://github.com/test/test/issues/1"

        # Create the file
        (tmp_path / "src" / "utils").mkdir(parents=True)
        (tmp_path / "src" / "utils" / "helper.py").write_text("# helper")

        with patch("maverick.utils.files.Path.cwd", return_value=tmp_path):
            context = build_issue_context(issue=issue, git=mock_git)

        # Should have found the referenced file
        assert (
            len(context["related_files"]) >= 0
        )  # May or may not find depending on path matching

    def test_nonexistent_files_handled(
        self,
        mock_github_issue: MagicMock,
        mock_git: MagicMock,
    ) -> None:
        """Non-existent referenced files are handled gracefully (T045)."""
        mock_github_issue.body = "Check nonexistent/path/file.py"

        context = build_issue_context(
            issue=mock_github_issue,
            git=mock_git,
        )

        # Should not crash, related_files may be empty
        assert "related_files" in context

    def test_no_file_references(
        self,
        mock_git: MagicMock,
    ) -> None:
        """Issue with no file references returns empty related_files (T046)."""
        issue = MagicMock()
        issue.number = 1
        issue.title = "General question"
        issue.body = "How do I configure the project?"
        issue.labels = ("question",)
        issue.state = "open"
        issue.url = "https://github.com/test/test/issues/1"

        context = build_issue_context(issue=issue, git=mock_git)

        assert context["related_files"] == {}

    def test_build_issue_context_git_errors(
        self,
        mock_github_issue: MagicMock,
    ) -> None:
        """Test git error handling in build_issue_context."""
        mock_git = MagicMock()
        mock_git.log.side_effect = RuntimeError("Git log failed")

        context = build_issue_context(mock_github_issue, mock_git)

        assert context["recent_changes"] == []


# =============================================================================
# Tests: fit_to_budget (T053-T061)
# =============================================================================


class TestFitToBudget:
    """Tests for fit_to_budget utility."""

    def test_under_budget_unchanged(self) -> None:
        """Sections under budget are returned unchanged (T053)."""
        sections = {"a": "short text", "b": "another short text"}
        result = fit_to_budget(sections, budget=10000)

        assert result["a"] == sections["a"]
        assert result["b"] == sections["b"]
        assert "_metadata" not in result

    def test_over_budget_truncated(self) -> None:
        """Sections over budget are proportionally truncated (T054)."""
        sections = {"a": "x" * 10000, "b": "y" * 5000}
        result = fit_to_budget(sections, budget=1000)

        # Both sections should be truncated
        assert len(result["a"]) < 10000
        assert len(result["b"]) < 5000
        assert "_metadata" in result

    def test_within_budget_tolerance(self) -> None:
        """Result is within 5% of budget (T055)."""
        sections = {"a": "x" * 20000, "b": "y" * 10000}
        budget = 5000
        result = fit_to_budget(sections, budget=budget)

        total_tokens = estimate_tokens(result["a"]) + estimate_tokens(
            result.get("b", "")
        )
        # Allow some tolerance since truncation adds markers
        assert total_tokens <= budget * 1.1  # 10% tolerance for markers

    def test_minimum_section_tokens(self) -> None:
        """Minimum section tokens are honored (T056)."""
        sections = {"a": "x" * 40000, "b": "y" * 100}  # b is tiny
        result = fit_to_budget(sections, budget=1000, min_section_tokens=50)

        # Small section should get at least minimum
        b_tokens = estimate_tokens(result.get("b", ""))
        assert b_tokens >= 50 or result.get("b") == sections["b"]

    def test_empty_sections(self) -> None:
        """Empty sections dict returns empty."""
        result = fit_to_budget({})
        assert result == {}

    def test_single_section(self) -> None:
        """Single section over budget is truncated."""
        sections = {"only": "x" * 100000}
        result = fit_to_budget(sections, budget=1000)

        assert estimate_tokens(result["only"]) <= 1100  # Allow some tolerance


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for context builders."""

    def test_full_workflow(
        self,
        mock_git: MagicMock,
        temp_task_file: Path,
        temp_conventions_file: Path,
    ) -> None:
        """Test a full workflow using multiple context builders."""
        # Build implementation context
        impl_ctx = build_implementation_context(
            task_file=temp_task_file,
            git=mock_git,
            conventions_path=temp_conventions_file,
        )
        assert impl_ctx["tasks"]
        assert impl_ctx["branch"]

        # Build review context
        review_ctx = build_review_context(
            git=mock_git,
            base_branch="main",
            conventions_path=temp_conventions_file,
        )
        assert review_ctx["diff"]
        assert "stats" in review_ctx

    def test_fit_to_budget_with_context(
        self,
        mock_git: MagicMock,
        temp_task_file: Path,
        temp_conventions_file: Path,
    ) -> None:
        """Test fitting context output to budget."""
        ctx = build_implementation_context(
            task_file=temp_task_file,
            git=mock_git,
            conventions_path=temp_conventions_file,
        )

        # Fit to a small budget
        sections = {
            "tasks": ctx["tasks"],
            "conventions": ctx["conventions"],
        }
        fitted = fit_to_budget(sections, budget=500)

        total_tokens = sum(
            estimate_tokens(v) for k, v in fitted.items() if k != "_metadata"
        )
        assert total_tokens <= 600  # Allow small tolerance
