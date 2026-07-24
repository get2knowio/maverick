"""Unit tests for the reconcile-support jj actions.

Tests the four jj action wrappers added for the reconcile workflow
(specs/051-reconcile-changed-answers, research R4):
- jj_new_child
- jj_squash_into
- jj_list_conflicts
- jj_check_mutability
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from maverick.jj.client import JjClient
from maverick.jj.errors import JjError
from maverick.jj.models import JjChangeInfo, JjLogResult, JjNewResult, JjSquashResult
from maverick.library.actions.jj import (
    jj_check_mutability,
    jj_list_conflicts,
    jj_new_child,
    jj_squash_into,
)

MOCK_CLIENT = "maverick.library.actions.jj._make_client"


def make_mock_client() -> AsyncMock:
    """Create a mock JjClient with all methods as AsyncMock."""
    client = AsyncMock(spec=JjClient)
    client.cwd = None
    client._runner = AsyncMock()
    return client


class TestJjNewChild:
    """Tests for jj_new_child action."""

    @pytest.mark.asyncio
    async def test_creates_child_of_parent(self) -> None:
        """Test creates a new empty change with the given parent."""
        mock_client = make_mock_client()
        mock_client.new.return_value = JjNewResult(success=True, change_id="kabc")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_new_child("ktarget")

        assert result["success"] is True
        assert result["change_id"] == "kabc"
        assert result["error"] is None
        mock_client.new.assert_called_once_with(parents=["ktarget"])

    @pytest.mark.asyncio
    async def test_empty_change_id_becomes_none(self) -> None:
        """Empty string change_id is normalised to None."""
        mock_client = make_mock_client()
        mock_client.new.return_value = JjNewResult(success=True, change_id="")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_new_child("ktarget")

        assert result["success"] is True
        assert result["change_id"] is None

    @pytest.mark.asyncio
    async def test_handles_jj_error(self) -> None:
        """Test JjError is caught and reported without raising."""
        mock_client = make_mock_client()
        mock_client.new.side_effect = JjError("no such revision")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_new_child("bad-target")

        assert result["success"] is False
        assert result["change_id"] is None
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_handles_os_error(self) -> None:
        """Test OSError is caught and reported without raising."""
        mock_client = make_mock_client()
        mock_client.new.side_effect = OSError("jj not found")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_new_child("ktarget")

        assert result["success"] is False
        assert result["error"] is not None


class TestJjSquashInto:
    """Tests for jj_squash_into action."""

    @pytest.mark.asyncio
    async def test_squashes_revision_into_target(self) -> None:
        """Test squashes the given revision into the given target."""
        mock_client = make_mock_client()
        mock_client.squash.return_value = JjSquashResult(success=True)

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_squash_into("kchild", "ktarget")

        assert result["success"] is True
        assert result["error"] is None
        mock_client.squash.assert_called_once_with(revision="kchild", into="ktarget")

    @pytest.mark.asyncio
    async def test_handles_jj_error(self) -> None:
        """Test JjError is caught and reported without raising."""
        mock_client = make_mock_client()
        mock_client.squash.side_effect = JjError("squash failed: conflict")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_squash_into("kchild", "ktarget")

        assert result["success"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_handles_os_error(self) -> None:
        """Test OSError is caught and reported without raising."""
        mock_client = make_mock_client()
        mock_client.squash.side_effect = OSError("jj not found")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_squash_into("kchild", "ktarget")

        assert result["success"] is False
        assert result["error"] is not None


class TestJjListConflicts:
    """Tests for jj_list_conflicts action."""

    @pytest.mark.asyncio
    async def test_returns_conflicted_change_ids(self) -> None:
        """Test returns change IDs in the order jj returned them."""
        mock_client = make_mock_client()
        mock_client.log.return_value = JjLogResult(
            success=True,
            output="",
            changes=(
                JjChangeInfo(change_id="kabc", commit_id="c1", description="d1"),
                JjChangeInfo(change_id="kdef", commit_id="c2", description="d2"),
            ),
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_list_conflicts("descendants(ktarget)")

        assert result["success"] is True
        assert result["change_ids"] == ("kabc", "kdef")
        assert result["error"] is None
        mock_client.log.assert_called_once_with(
            revset="descendants(ktarget) & conflicts()",
            limit=1000,
        )

    @pytest.mark.asyncio
    async def test_no_conflicts_returns_empty_tuple(self) -> None:
        """Test an empty result set yields an empty tuple, not a failure."""
        mock_client = make_mock_client()
        mock_client.log.return_value = JjLogResult(success=True, output="", changes=())

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_list_conflicts("descendants(ktarget)")

        assert result["success"] is True
        assert result["change_ids"] == ()

    @pytest.mark.asyncio
    async def test_handles_jj_error(self) -> None:
        """Test JjError is caught and reported without raising."""
        mock_client = make_mock_client()
        mock_client.log.side_effect = JjError("bad revset")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_list_conflicts("descendants(ktarget)")

        assert result["success"] is False
        assert result["change_ids"] == ()
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_handles_os_error(self) -> None:
        """Test OSError is caught and reported without raising."""
        mock_client = make_mock_client()
        mock_client.log.side_effect = OSError("jj not found")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_list_conflicts("descendants(ktarget)")

        assert result["success"] is False
        assert result["error"] is not None


class TestJjCheckMutability:
    """Tests for jj_check_mutability action."""

    @pytest.mark.asyncio
    async def test_mutable_when_query_returns_no_changes(self) -> None:
        """Test mutable=True when neither target nor descendants are immutable."""
        mock_client = make_mock_client()
        mock_client.log.return_value = JjLogResult(success=True, output="", changes=())

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_check_mutability("ktarget")

        assert result["success"] is True
        assert result["mutable"] is True
        assert result["immutable_change_ids"] == ()
        assert result["error"] is None
        mock_client.log.assert_called_once_with(
            revset=("(::ktarget & immutable() & ktarget) | (descendants(ktarget) & immutable())"),
            limit=1000,
        )

    @pytest.mark.asyncio
    async def test_immutable_when_query_returns_changes(self) -> None:
        """Test mutable=False with the offending change IDs surfaced."""
        mock_client = make_mock_client()
        mock_client.log.return_value = JjLogResult(
            success=True,
            output="",
            changes=(JjChangeInfo(change_id="kmain", commit_id="c1", description="main"),),
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_check_mutability("ktarget")

        assert result["success"] is True
        assert result["mutable"] is False
        assert result["immutable_change_ids"] == ("kmain",)
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_handles_jj_error(self) -> None:
        """Test JjError is caught and reported without raising (not mutable)."""
        mock_client = make_mock_client()
        mock_client.log.side_effect = JjError("bad revset")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_check_mutability("ktarget")

        assert result["success"] is False
        assert result["mutable"] is False
        assert result["immutable_change_ids"] == ()
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_handles_os_error(self) -> None:
        """Test OSError is caught and reported without raising."""
        mock_client = make_mock_client()
        mock_client.log.side_effect = OSError("jj not found")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_check_mutability("ktarget")

        assert result["success"] is False
        assert result["mutable"] is False
        assert result["error"] is not None
