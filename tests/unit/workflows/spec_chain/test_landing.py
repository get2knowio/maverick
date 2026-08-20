"""Tests for spec-chain artifact resolution and verification
(`maverick.workflows.spec_chain.landing`).

Landing itself (moving artifacts from workspace to checkout) migrated to
the shared isolation primitive's `IsolationSession.fold_back()`
(057-isolated-bead-workspaces) — see `tests/integration/workspace/
test_foldback.py` for that mechanism's own coverage, and `tests/
integration/spec_chain/test_migration_parity.py` for the fold-back-scoped-
to-specs-dir consumer contract (contract M7). What remains here is
chain-specific: resolving which `specs/NNN-<feature>` directory `specify`
allocated, and verifying a step's required artifacts exist.
"""

from __future__ import annotations

from pathlib import Path

from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.landing import (
    resolve_feature_dir,
    verify_step_artifacts,
)


def _make_workspace_feature(tmp_path: Path, feature_dir: str, **files: str) -> Path:
    workspace = tmp_path / "workspace"
    feature_path = workspace / "specs" / feature_dir
    feature_path.mkdir(parents=True)
    for name, content in files.items():
        (feature_path / name).write_text(content, encoding="utf-8")
    return workspace


class TestResolveFeatureDir:
    def test_single_new_dir_is_resolved(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        (workspace / "specs" / "001-existing").mkdir(parents=True)
        (workspace / "specs" / "002-new-feature").mkdir(parents=True)

        result = resolve_feature_dir(workspace=workspace, checkout_specs_before={"001-existing"})
        assert result == "002-new-feature"

    def test_no_specs_dir_returns_none(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        assert resolve_feature_dir(workspace=workspace, checkout_specs_before=set()) is None

    def test_no_new_dirs_returns_none(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        (workspace / "specs" / "001-existing").mkdir(parents=True)
        result = resolve_feature_dir(workspace=workspace, checkout_specs_before={"001-existing"})
        assert result is None

    def test_ambiguous_diff_falls_back_to_feature_json(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        (workspace / "specs" / "002-candidate-a").mkdir(parents=True)
        (workspace / "specs" / "003-candidate-b").mkdir(parents=True)
        specify_dir = workspace / ".specify"
        specify_dir.mkdir(parents=True)
        (specify_dir / "feature.json").write_text(
            '{"feature_directory": "specs/003-candidate-b"}', encoding="utf-8"
        )

        result = resolve_feature_dir(workspace=workspace, checkout_specs_before=set())
        assert result == "003-candidate-b"

    def test_ambiguous_diff_with_no_feature_json_returns_none(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        (workspace / "specs" / "002-candidate-a").mkdir(parents=True)
        (workspace / "specs" / "003-candidate-b").mkdir(parents=True)

        result = resolve_feature_dir(workspace=workspace, checkout_specs_before=set())
        assert result is None

    def test_malformed_feature_json_does_not_raise(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        (workspace / "specs" / "002-candidate-a").mkdir(parents=True)
        (workspace / "specs" / "003-candidate-b").mkdir(parents=True)
        specify_dir = workspace / ".specify"
        specify_dir.mkdir(parents=True)
        (specify_dir / "feature.json").write_text("not valid json{{{", encoding="utf-8")

        result = resolve_feature_dir(workspace=workspace, checkout_specs_before=set())
        assert result is None


class TestVerifyStepArtifacts:
    def test_specify_verified_when_spec_md_exists(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(tmp_path, "001-foo", **{"spec.md": "content"})
        result = verify_step_artifacts(
            workspace=workspace, feature_dir="001-foo", step=ChainStep.SPECIFY
        )
        assert result == ["spec.md"]

    def test_specify_fails_verification_when_spec_md_missing(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(tmp_path, "001-foo")
        result = verify_step_artifacts(
            workspace=workspace, feature_dir="001-foo", step=ChainStep.SPECIFY
        )
        assert result == []

    def test_plan_requires_plan_md(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(
            tmp_path, "001-foo", **{"spec.md": "x", "plan.md": "y"}
        )
        result = verify_step_artifacts(
            workspace=workspace, feature_dir="001-foo", step=ChainStep.PLAN
        )
        assert result == ["plan.md"]

    def test_tasks_requires_tasks_md(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(tmp_path, "001-foo", **{"tasks.md": "z"})
        result = verify_step_artifacts(
            workspace=workspace, feature_dir="001-foo", step=ChainStep.TASKS
        )
        assert result == ["tasks.md"]

    def test_analyze_requires_no_new_artifact(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(tmp_path, "001-foo")
        result = verify_step_artifacts(
            workspace=workspace, feature_dir="001-foo", step=ChainStep.ANALYZE
        )
        assert result == []

    def test_missing_feature_dir_entirely_returns_empty(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        result = verify_step_artifacts(
            workspace=workspace, feature_dir="001-foo", step=ChainStep.SPECIFY
        )
        assert result == []
