"""Tests for ``cli.common.resolve_publish_branch_label``.

The CLI helpers ``maverick plan generate`` and ``maverick refuel`` use
this to label the post-finalize "published to user repo" message with the
**destination branch** (typically ``main`` or a feature branch) instead of
the temporary ``maverick/<project>`` transport bookmark, which has been
deleted by ``finalize`` by the time the message prints.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.cli.common import resolve_publish_branch_label


@pytest.mark.asyncio
async def test_returns_branch_name_from_repo() -> None:
    """``VcsRepository.current_branch`` is async — helper awaits it."""
    repo = MagicMock()
    repo.current_branch = AsyncMock(return_value="main")
    with patch(
        "maverick.vcs.factory.create_vcs_repository",
        return_value=repo,
    ):
        label = await resolve_publish_branch_label(Path("/tmp/fake-repo"))
    assert label == "main"


@pytest.mark.asyncio
async def test_returns_feature_branch_name() -> None:
    """Confirms the helper returns whatever the backend reports — not
    just hard-coded ``main`` recovery."""
    repo = MagicMock()
    repo.current_branch = AsyncMock(return_value="feature-x")
    with patch(
        "maverick.vcs.factory.create_vcs_repository",
        return_value=repo,
    ):
        label = await resolve_publish_branch_label(Path("/tmp/fake-repo"))
    assert label == "feature-x"


@pytest.mark.asyncio
async def test_falls_back_to_generic_label_on_factory_failure() -> None:
    """An unexpected error during repo construction must not break the
    success path — return a generic label and let the user keep going."""
    with patch(
        "maverick.vcs.factory.create_vcs_repository",
        side_effect=RuntimeError("boom"),
    ):
        label = await resolve_publish_branch_label(Path("/tmp/no-such-repo"))
    assert label == "current branch"


@pytest.mark.asyncio
async def test_falls_back_to_generic_label_on_branch_failure() -> None:
    """Detached HEAD or other branch-resolution errors fall back too."""
    repo = MagicMock()
    repo.current_branch = AsyncMock(side_effect=RuntimeError("detached"))
    with patch(
        "maverick.vcs.factory.create_vcs_repository",
        return_value=repo,
    ):
        label = await resolve_publish_branch_label(Path("/tmp/fake-repo"))
    assert label == "current branch"


@pytest.mark.asyncio
async def test_empty_branch_name_falls_back_to_generic_label() -> None:
    """Empty/whitespace branch name → generic label, never an empty string."""
    repo = MagicMock()
    repo.current_branch = AsyncMock(return_value="   ")
    with patch(
        "maverick.vcs.factory.create_vcs_repository",
        return_value=repo,
    ):
        label = await resolve_publish_branch_label(Path("/tmp/fake-repo"))
    assert label == "current branch"


@pytest.mark.asyncio
async def test_strips_whitespace_from_branch_name() -> None:
    """Backends sometimes return trailing newlines from CLI output."""
    repo = MagicMock()
    repo.current_branch = AsyncMock(return_value="main\n")
    with patch(
        "maverick.vcs.factory.create_vcs_repository",
        return_value=repo,
    ):
        label = await resolve_publish_branch_label(Path("/tmp/fake-repo"))
    assert label == "main"
