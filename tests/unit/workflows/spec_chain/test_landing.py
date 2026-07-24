"""Tests for atomic per-step artifact landing
(`maverick.workflows.spec_chain.landing`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.landing import (
    land_step_artifacts,
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


class TestLandStepArtifacts:
    def test_lands_full_feature_dir_into_checkout(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(tmp_path, "001-foo", **{"spec.md": "spec content"})
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        land_step_artifacts(workspace=workspace, checkout=checkout, feature_dir="001-foo")

        landed = checkout / "specs" / "001-foo" / "spec.md"
        assert landed.is_file()
        assert landed.read_text(encoding="utf-8") == "spec content"

    def test_second_landing_overwrites_with_current_content(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(
            tmp_path, "001-foo", **{"spec.md": "v1", "plan.md": "v1 plan"}
        )
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        land_step_artifacts(workspace=workspace, checkout=checkout, feature_dir="001-foo")

        # A later step adds tasks.md and updates plan.md in the workspace.
        (workspace / "specs" / "001-foo" / "plan.md").write_text("v2 plan", encoding="utf-8")
        (workspace / "specs" / "001-foo" / "tasks.md").write_text("v1 tasks", encoding="utf-8")

        land_step_artifacts(workspace=workspace, checkout=checkout, feature_dir="001-foo")

        feature_path = checkout / "specs" / "001-foo"
        assert (feature_path / "spec.md").read_text(encoding="utf-8") == "v1"
        assert (feature_path / "plan.md").read_text(encoding="utf-8") == "v2 plan"
        assert (feature_path / "tasks.md").read_text(encoding="utf-8") == "v1 tasks"

    def test_no_leftover_staging_directories(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(tmp_path, "001-foo", **{"spec.md": "x"})
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        land_step_artifacts(workspace=workspace, checkout=checkout, feature_dir="001-foo")

        specs_dir = checkout / "specs"
        entries = {p.name for p in specs_dir.iterdir()}
        assert entries == {"001-foo"}

    def test_missing_workspace_feature_dir_raises(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        with pytest.raises(FileNotFoundError):
            land_step_artifacts(workspace=workspace, checkout=checkout, feature_dir="001-foo")

    def test_creates_specs_parent_dir_if_absent(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(tmp_path, "001-foo", **{"spec.md": "x"})
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        assert not (checkout / "specs").exists()

        land_step_artifacts(workspace=workspace, checkout=checkout, feature_dir="001-foo")

        assert (checkout / "specs" / "001-foo" / "spec.md").is_file()
