"""Tests for the landing guard (056-context-file-protection T017):
``land_step_artifacts`` refuses to copy protected-matching paths into the
checkout. Belt-and-braces per research.md R10 — landing only ever
touches ``specs/<feature_dir>/**``, so this only bites on a configured
``additional_globs`` pattern reaching under that tree.
"""

from __future__ import annotations

from pathlib import Path

from maverick.config import MaverickConfig
from maverick.workflows.spec_chain.landing import land_step_artifacts


def _make_workspace_feature(tmp_path: Path, feature_dir: str, **files: str) -> Path:
    workspace = tmp_path / "workspace"
    feature_path = workspace / "specs" / feature_dir
    feature_path.mkdir(parents=True)
    for name, content in files.items():
        (feature_path / name).write_text(content, encoding="utf-8")
    return workspace


class TestDefaultProtectionAppliesRegardlessOfConfig:
    def test_no_config_still_applies_default_protection(self, tmp_path: Path) -> None:
        """``config=None`` degrades to defaults-only protection, never
        'no protection' (per the docstring contract)."""
        workspace = _make_workspace_feature(
            tmp_path,
            "001-foo",
            **{"spec.md": "# spec", "AGENTS.md": "agent instructions smuggled in"},
        )
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        land_step_artifacts(workspace=workspace, checkout=checkout, feature_dir="001-foo")

        dest = checkout / "specs" / "001-foo"
        assert (dest / "spec.md").is_file()
        assert not (dest / "AGENTS.md").exists()


class TestConfiguredAdditionalGlobsStripped:
    def test_additional_glob_under_specs_is_stripped(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(
            tmp_path,
            "001-foo",
            **{"spec.md": "# spec", "secret-notes.md": "should never land"},
        )
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        config = MaverickConfig(protection={"additional_globs": ["specs/001-foo/secret-notes.md"]})

        land_step_artifacts(
            workspace=workspace, checkout=checkout, feature_dir="001-foo", config=config
        )

        dest = checkout / "specs" / "001-foo"
        assert (dest / "spec.md").is_file()
        assert not (dest / "secret-notes.md").exists()

    def test_unrelated_glob_does_not_affect_other_files(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(
            tmp_path,
            "001-foo",
            **{"spec.md": "# spec", "plan.md": "# plan"},
        )
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        config = MaverickConfig(protection={"additional_globs": ["docs/other/**"]})

        land_step_artifacts(
            workspace=workspace, checkout=checkout, feature_dir="001-foo", config=config
        )

        dest = checkout / "specs" / "001-foo"
        assert (dest / "spec.md").is_file()
        assert (dest / "plan.md").is_file()


class TestNormalArtifactsSurviveLanding:
    def test_ordinary_spec_kit_artifacts_all_land(self, tmp_path: Path) -> None:
        workspace = _make_workspace_feature(
            tmp_path,
            "001-foo",
            **{"spec.md": "# spec", "plan.md": "# plan", "tasks.md": "# tasks"},
        )
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        land_step_artifacts(
            workspace=workspace,
            checkout=checkout,
            feature_dir="001-foo",
            config=MaverickConfig(),
        )

        dest = checkout / "specs" / "001-foo"
        assert {p.name for p in dest.iterdir()} == {"spec.md", "plan.md", "tasks.md"}
