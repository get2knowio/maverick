"""Unit tests for the hidden spec-chain jj workspace helper.

Contract under test (`maverick.workspace.spec_chain.prepare_workspace`):

- Location: ``<home>/.maverick/workspaces/<project-slug>/spec-chain/<feature>/`` —
  per-feature, so two features never share a workspace directory.
- Creation goes through the injected ``JjClient`` (``workspace_add`` /
  ``workspace_forget``); the helper never shells out to jj itself.
- ``reuse=True`` (an active, resumable chain) reuses an existing on-disk
  workspace directory as-is: no ``workspace_add``, no ``workspace_forget``, no
  wipe.
- ``reuse=False`` (a completed or freshly-started chain) starts clean: if a
  stale directory is already on disk, it is forgotten (``workspace_forget``)
  and removed before a fresh ``workspace_add`` recreates it. If nothing is on
  disk yet, only ``workspace_add`` runs.
- The PRD file (which may be untracked in the user's checkout) is always
  copied into the workspace, under ``<workspace>/inputs/<prd_path.name>``,
  before the function returns — regardless of which branch above ran.
- ``JjError`` raised by the injected client surfaces as
  ``SpecChainWorkspaceError``.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest

from maverick.exceptions import JjError, SpecChainWorkspaceError
from maverick.jj.client import JjClient
from maverick.workspace.spec_chain import prepare_workspace

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """Fake ``~`` so tests never touch the real home directory."""
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    return fake_home


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """Fake user checkout (``cwd``) — just needs to exist and have a name."""
    repo_dir = tmp_path / "checkouts" / "maverick"
    repo_dir.mkdir(parents=True)
    return repo_dir


@pytest.fixture
def prd_path(tmp_path: Path) -> Path:
    """An untracked PRD file living in the user's checkout."""
    prd = tmp_path / "prd-scratch" / "feature-prd.md"
    prd.parent.mkdir(parents=True)
    prd.write_text("# Feature PRD\n\nSome untracked content.\n", encoding="utf-8")
    return prd


@pytest.fixture
def mock_jj_client() -> AsyncMock:
    """A stubbed JjClient — no real jj repo involved in this unit test."""
    client = AsyncMock(spec=JjClient)

    # workspace_add should behave like the real client: return the resolved
    # target path, and actually materialize the directory on disk (the way
    # `jj workspace add` would), so downstream PRD-copy assertions can run
    # against a real filesystem path.
    async def _workspace_add(target: Path) -> Path:
        target.mkdir(parents=True, exist_ok=False)
        return target.resolve()

    client.workspace_add.side_effect = _workspace_add
    return client


def _workspace_dir(home: Path, checkout: Path, feature: str) -> Path:
    """Compute the expected workspace path per the R3 contract."""
    return home / ".maverick" / "workspaces" / checkout.name / "spec-chain" / feature


# ---------------------------------------------------------------------------
# Fresh-run creation
# ---------------------------------------------------------------------------


class TestFreshRunCreation:
    async def test_creates_workspace_via_workspace_add(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        expected = _workspace_dir(home, checkout, "050-headless-spec-chain")

        result = await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )

        assert result == expected
        mock_jj_client.workspace_add.assert_awaited_once_with(expected)

    async def test_no_forget_or_rmtree_when_nothing_stale(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )

        mock_jj_client.workspace_forget.assert_not_awaited()

    async def test_workspace_path_is_outside_the_checkout(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        result = await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )

        assert checkout not in result.parents
        assert result.is_relative_to(home)


# ---------------------------------------------------------------------------
# Resume / reuse of an active chain
# ---------------------------------------------------------------------------


class TestResumeReuseActiveChain:
    async def test_reuses_existing_directory_without_workspace_add(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        existing = _workspace_dir(home, checkout, "050-headless-spec-chain")
        existing.mkdir(parents=True)
        sentinel = existing / "specs" / "050-headless-spec-chain" / "spec.md"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("already-written spec content", encoding="utf-8")

        result = await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=True,
            jj_client=mock_jj_client,
            home=home,
        )

        assert result == existing
        mock_jj_client.workspace_add.assert_not_awaited()
        mock_jj_client.workspace_forget.assert_not_awaited()
        # Existing content must survive untouched.
        assert sentinel.read_text(encoding="utf-8") == "already-written spec content"

    async def test_reuse_with_no_existing_directory_falls_back_to_creation(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        """reuse=True but nothing on disk (e.g. state says active but the
        directory vanished) — must still succeed by creating a workspace,
        not raise or silently no-op."""
        expected = _workspace_dir(home, checkout, "050-headless-spec-chain")
        assert not expected.exists()

        result = await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=True,
            jj_client=mock_jj_client,
            home=home,
        )

        assert result == expected
        mock_jj_client.workspace_add.assert_awaited_once_with(expected)
        mock_jj_client.workspace_forget.assert_not_awaited()


# ---------------------------------------------------------------------------
# Forget + recreate of a completed (or stale) chain
# ---------------------------------------------------------------------------


class TestForgetAndRecreateCompletedChain:
    async def test_forgets_then_recreates_in_order(
        self,
        home: Path,
        checkout: Path,
        prd_path: Path,
        mock_jj_client: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        stale = _workspace_dir(home, checkout, "050-headless-spec-chain")
        stale.mkdir(parents=True)
        (stale / "leftover.txt").write_text("stale", encoding="utf-8")

        calls: list[str] = []

        async def _forget(name: str) -> None:
            calls.append(f"forget:{name}")

        async def _add(target: Path) -> Path:
            calls.append(f"add:{target}")
            target.mkdir(parents=True, exist_ok=False)
            return target.resolve()

        mock_jj_client.workspace_forget.side_effect = _forget
        mock_jj_client.workspace_add.side_effect = _add

        real_rmtree = shutil.rmtree

        def _tracking_rmtree(path: object, *args: object, **kwargs: object) -> None:
            calls.append(f"rmtree:{path}")
            real_rmtree(path, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr("maverick.workspace.spec_chain.shutil.rmtree", _tracking_rmtree)

        result = await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )

        assert result == stale
        # forget must precede rmtree must precede add — a fresh workspace_add
        # cannot target a path jj still thinks is occupied, and rmtree must
        # not delete a directory jj hasn't released yet.
        forget_idx = calls.index("forget:050-headless-spec-chain")
        rmtree_idx = next(i for i, c in enumerate(calls) if c.startswith("rmtree:"))
        add_idx = next(i for i, c in enumerate(calls) if c.startswith("add:"))
        assert forget_idx < rmtree_idx < add_idx

        # The old content must be gone — workspace_add repopulated the dir
        # from scratch via jj, not by preserving the stale leftovers.
        assert not (stale / "leftover.txt").exists()

    async def test_directory_does_not_exist_when_workspace_add_invoked(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        stale = _workspace_dir(home, checkout, "050-headless-spec-chain")
        stale.mkdir(parents=True)
        (stale / "leftover.txt").write_text("stale", encoding="utf-8")

        observed_exists_at_add_time: list[bool] = []

        async def _add(target: Path) -> Path:
            observed_exists_at_add_time.append(target.exists())
            target.mkdir(parents=True, exist_ok=False)
            return target.resolve()

        mock_jj_client.workspace_add.side_effect = _add

        await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )

        assert observed_exists_at_add_time == [False]
        mock_jj_client.workspace_forget.assert_awaited_once_with("050-headless-spec-chain")

    async def test_no_forget_when_nothing_stale_on_fresh_start(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        """A freshly-started chain (never run before) has no stale directory
        to forget — only workspace_add should run."""
        await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )

        mock_jj_client.workspace_forget.assert_not_awaited()
        mock_jj_client.workspace_add.assert_awaited_once()


# ---------------------------------------------------------------------------
# PRD copy-in
# ---------------------------------------------------------------------------


class TestPrdCopyIn:
    async def test_copies_prd_into_new_workspace(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        result = await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )

        copied = result / "inputs" / prd_path.name
        assert copied.exists()
        assert copied.read_text(encoding="utf-8") == prd_path.read_text(encoding="utf-8")

    async def test_copies_prd_into_reused_workspace(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        existing = _workspace_dir(home, checkout, "050-headless-spec-chain")
        existing.mkdir(parents=True)

        result = await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=True,
            jj_client=mock_jj_client,
            home=home,
        )

        copied = result / "inputs" / prd_path.name
        assert copied.exists()
        assert copied.read_text(encoding="utf-8") == prd_path.read_text(encoding="utf-8")

    async def test_prd_copy_reflects_current_content_on_reuse(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        """Even when reusing a workspace, the PRD copy must be refreshed —
        the caller may resume with edited PRD content."""
        existing = _workspace_dir(home, checkout, "050-headless-spec-chain")
        existing.mkdir(parents=True)
        stale_copy = existing / "inputs"
        stale_copy.mkdir(parents=True)
        (stale_copy / prd_path.name).write_text("old content", encoding="utf-8")

        prd_path.write_text("brand new content", encoding="utf-8")

        result = await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=True,
            jj_client=mock_jj_client,
            home=home,
        )

        copied = result / "inputs" / prd_path.name
        assert copied.read_text(encoding="utf-8") == "brand new content"


# ---------------------------------------------------------------------------
# Per-feature path isolation
# ---------------------------------------------------------------------------


class TestPerFeatureIsolation:
    async def test_different_features_get_different_paths(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        result_a = await prepare_workspace(
            cwd=checkout,
            feature="050-headless-spec-chain",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )
        result_b = await prepare_workspace(
            cwd=checkout,
            feature="051-other-feature",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )

        assert result_a != result_b
        assert "050-headless-spec-chain" in result_a.parts
        assert "051-other-feature" in result_b.parts

    async def test_halted_feature_a_untouched_by_fresh_run_of_feature_b(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        """A halted, resumable feature-A workspace must survive a completely
        unrelated fresh run of feature B: no jj ops referencing feature A's
        path, and its on-disk content is left alone."""
        feature_a_dir = _workspace_dir(home, checkout, "feature-a")
        feature_a_dir.mkdir(parents=True)
        (feature_a_dir / "resumable-marker.txt").write_text("do not touch", encoding="utf-8")

        await prepare_workspace(
            cwd=checkout,
            feature="feature-b",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )

        # feature A's directory and content are untouched.
        assert (feature_a_dir / "resumable-marker.txt").read_text(
            encoding="utf-8"
        ) == "do not touch"

        # No jj call ever referenced feature A's path or workspace name.
        for c in mock_jj_client.workspace_add.await_args_list:
            assert "feature-a" not in str(c)
        for c in mock_jj_client.workspace_forget.await_args_list:
            assert "feature-a" not in str(c)

    async def test_two_features_produce_independent_jj_calls(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        expected_a = _workspace_dir(home, checkout, "feature-a")
        expected_b = _workspace_dir(home, checkout, "feature-b")

        await prepare_workspace(
            cwd=checkout,
            feature="feature-a",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )
        await prepare_workspace(
            cwd=checkout,
            feature="feature-b",
            prd_path=prd_path,
            reuse=False,
            jj_client=mock_jj_client,
            home=home,
        )

        assert mock_jj_client.workspace_add.await_args_list == [
            call(expected_a),
            call(expected_b),
        ]


# ---------------------------------------------------------------------------
# Workspace-creation failure propagation
# ---------------------------------------------------------------------------


class TestWorkspaceCreationFailurePropagation:
    async def test_jj_error_on_workspace_add_becomes_spec_chain_workspace_error(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        mock_jj_client.workspace_add.side_effect = JjError(
            "jj workspace add failed: target exists"
        )

        with pytest.raises(SpecChainWorkspaceError):
            await prepare_workspace(
                cwd=checkout,
                feature="050-headless-spec-chain",
                prd_path=prd_path,
                reuse=False,
                jj_client=mock_jj_client,
                home=home,
            )

    async def test_jj_error_on_workspace_forget_becomes_spec_chain_workspace_error(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        stale = _workspace_dir(home, checkout, "050-headless-spec-chain")
        stale.mkdir(parents=True)

        mock_jj_client.workspace_forget.side_effect = JjError(
            "jj workspace forget failed: unknown workspace"
        )

        with pytest.raises(SpecChainWorkspaceError):
            await prepare_workspace(
                cwd=checkout,
                feature="050-headless-spec-chain",
                prd_path=prd_path,
                reuse=False,
                jj_client=mock_jj_client,
                home=home,
            )

    async def test_original_jj_error_is_chained(
        self, home: Path, checkout: Path, prd_path: Path, mock_jj_client: AsyncMock
    ) -> None:
        underlying = JjError("boom")
        mock_jj_client.workspace_add.side_effect = underlying

        with pytest.raises(SpecChainWorkspaceError) as exc_info:
            await prepare_workspace(
                cwd=checkout,
                feature="050-headless-spec-chain",
                prd_path=prd_path,
                reuse=False,
                jj_client=mock_jj_client,
                home=home,
            )

        assert exc_info.value.__cause__ is underlying
