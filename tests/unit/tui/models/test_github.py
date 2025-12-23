"""Unit tests for TUI GitHub models."""

from __future__ import annotations

import pytest

from maverick.tui.models import (
    CheckStatus,
    PRInfo,
    PRState,
    StatusCheck,
)


class TestStatusCheck:
    """Tests for StatusCheck dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating StatusCheck with required fields."""
        check = StatusCheck(name="CI / build", status=CheckStatus.PASSING)

        assert check.name == "CI / build"
        assert check.status == CheckStatus.PASSING
        assert check.url is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating StatusCheck with all fields."""
        check = StatusCheck(
            name="CI / test",
            status=CheckStatus.FAILING,
            url="https://github.com/org/repo/runs/123",
        )

        assert check.name == "CI / test"
        assert check.status == CheckStatus.FAILING
        assert check.url == "https://github.com/org/repo/runs/123"

    def test_url_defaults_to_none(self) -> None:
        """Test url defaults to None."""
        check = StatusCheck(name="lint", status=CheckStatus.PASSING)
        assert check.url is None

    def test_different_statuses(self) -> None:
        """Test StatusCheck with different statuses."""
        for status in CheckStatus:
            check = StatusCheck(name="test", status=status)
            assert check.status == status

    def test_status_check_is_frozen(self) -> None:
        """Test StatusCheck is immutable (frozen)."""
        check = StatusCheck(name="test", status=CheckStatus.PENDING)

        with pytest.raises(Exception):  # FrozenInstanceError
            check.status = CheckStatus.PASSING  # type: ignore[misc]


class TestPRInfo:
    """Tests for PRInfo dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating PRInfo with required fields."""
        pr = PRInfo(
            number=123,
            title="Add new feature",
            description="This PR adds a new feature to the app",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/123",
        )

        assert pr.number == 123
        assert pr.title == "Add new feature"
        assert pr.description == "This PR adds a new feature to the app"
        assert pr.state == PRState.OPEN
        assert pr.url == "https://github.com/org/repo/pull/123"
        assert pr.checks == ()  # default
        assert pr.branch == ""  # default
        assert pr.base_branch == "main"  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating PRInfo with all fields."""
        check1 = StatusCheck(name="CI / build", status=CheckStatus.PASSING)
        check2 = StatusCheck(name="CI / test", status=CheckStatus.FAILING)

        pr = PRInfo(
            number=456,
            title="Fix bug",
            description="Fixes issue #123",
            state=PRState.MERGED,
            url="https://github.com/org/repo/pull/456",
            checks=(check1, check2),
            branch="feature/bug-fix",
            base_branch="develop",
        )

        assert pr.number == 456
        assert pr.title == "Fix bug"
        assert pr.description == "Fixes issue #123"
        assert pr.state == PRState.MERGED
        assert len(pr.checks) == 2
        assert pr.branch == "feature/bug-fix"
        assert pr.base_branch == "develop"

    def test_checks_defaults_to_empty_tuple(self) -> None:
        """Test checks defaults to empty tuple."""
        pr = PRInfo(
            number=1,
            title="Test",
            description="Test PR",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )
        assert pr.checks == ()

    def test_branch_defaults_to_empty_string(self) -> None:
        """Test branch defaults to empty string."""
        pr = PRInfo(
            number=1,
            title="Test",
            description="Test PR",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )
        assert pr.branch == ""

    def test_base_branch_defaults_to_main(self) -> None:
        """Test base_branch defaults to 'main'."""
        pr = PRInfo(
            number=1,
            title="Test",
            description="Test PR",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )
        assert pr.base_branch == "main"

    def test_description_preview_property_short_description(self) -> None:
        """Test description_preview with short description."""
        pr = PRInfo(
            number=1,
            title="Test",
            description="This is a short description",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )
        assert pr.description_preview == "This is a short description"

    def test_description_preview_property_long_description(self) -> None:
        """Test description_preview with long description."""
        long_desc = "This is a very long description " * 20  # > 200 chars
        pr = PRInfo(
            number=1,
            title="Test",
            description=long_desc,
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )

        preview = pr.description_preview
        assert len(preview) <= 204  # 200 + "..."
        assert preview.endswith("...")
        assert preview in long_desc or long_desc.startswith(preview[:-3])

    def test_description_preview_property_exactly_200_chars(self) -> None:
        """Test description_preview with exactly 200 characters."""
        desc = "x" * 200
        pr = PRInfo(
            number=1,
            title="Test",
            description=desc,
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )
        assert pr.description_preview == desc

    def test_different_states(self) -> None:
        """Test PRInfo with different states."""
        for state in PRState:
            pr = PRInfo(
                number=1,
                title="Test",
                description="Test",
                state=state,
                url="https://github.com/org/repo/pull/1",
            )
            assert pr.state == state

    def test_pr_info_is_frozen(self) -> None:
        """Test PRInfo is immutable (frozen)."""
        pr = PRInfo(
            number=1,
            title="Test",
            description="Test",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            pr.state = PRState.MERGED  # type: ignore[misc]
