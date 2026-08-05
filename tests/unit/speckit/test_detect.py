"""Tests for maverick.speckit.detect (resolution + version gate)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maverick.speckit.detect import (
    SUPPORTED_SPECKIT_RANGE,
    check_template_compatibility,
    resolve_feature,
)
from maverick.speckit.errors import AmbiguousFeatureError


class TestResolveFeatureNameForms:
    def test_exact_directory_name(self, speckit_feature_dir: Path, temp_dir: Path) -> None:
        resolution = resolve_feature("048-sample-feature", cwd=temp_dir)
        assert resolution.mode == "speckit"
        assert resolution.speckit_dir == speckit_feature_dir

    def test_nnn_prefix(self, speckit_feature_dir: Path, temp_dir: Path) -> None:
        resolution = resolve_feature("048", cwd=temp_dir)
        assert resolution.mode == "speckit"
        assert resolution.speckit_dir == speckit_feature_dir

    def test_exact_suffix(self, speckit_feature_dir: Path, temp_dir: Path) -> None:
        resolution = resolve_feature("sample-feature", cwd=temp_dir)
        assert resolution.mode == "speckit"
        assert resolution.speckit_dir == speckit_feature_dir

    def test_multiple_candidates_raise_ambiguous_feature_error(self, temp_dir: Path) -> None:
        for name in ["048-sample-feature", "048-other-feature"]:
            d = temp_dir / "specs" / name
            d.mkdir(parents=True)
            (d / "spec.md").write_text("# Feature Specification: X\n")
            (d / "tasks.md").write_text("## Phase 1: Setup\n\n- [ ] T001 A thing\n")

        with pytest.raises(AmbiguousFeatureError) as exc_info:
            resolve_feature("048", cwd=temp_dir)
        assert len(exc_info.value.candidates) == 2

    def test_missing_spec_or_tasks_not_a_candidate(self, temp_dir: Path) -> None:
        d = temp_dir / "specs" / "048-partial"
        d.mkdir(parents=True)
        (d / "spec.md").write_text("# Feature Specification: X\n")
        # no tasks.md

        resolution = resolve_feature("048", cwd=temp_dir)
        assert resolution.mode == "unresolved"


class TestResolveFeatureClassicMode:
    def test_classic_flight_plan_only(self, temp_dir: Path) -> None:
        plan_dir = temp_dir / ".maverick" / "plans" / "my-feature"
        plan_dir.mkdir(parents=True)
        (plan_dir / "flight-plan.md").write_text("---\nname: my-feature\n---\n")

        resolution = resolve_feature("my-feature", cwd=temp_dir)
        assert resolution.mode == "classic"
        assert resolution.flight_plan_path == plan_dir / "flight-plan.md"

    def test_neither_matches_is_unresolved(self, temp_dir: Path) -> None:
        resolution = resolve_feature("nonexistent", cwd=temp_dir)
        assert resolution.mode == "unresolved"
        assert resolution.speckit_dir is None
        assert resolution.flight_plan_path is None

    def test_both_match_is_ambiguous(self, speckit_feature_dir: Path, temp_dir: Path) -> None:
        plan_dir = temp_dir / ".maverick" / "plans" / "048-sample-feature"
        plan_dir.mkdir(parents=True)
        (plan_dir / "flight-plan.md").write_text("---\nname: 048-sample-feature\n---\n")

        resolution = resolve_feature("048-sample-feature", cwd=temp_dir)
        assert resolution.mode == "ambiguous"
        assert resolution.speckit_dir is not None
        assert resolution.flight_plan_path is not None


class TestTemplateCompatibility:
    def test_supported_version(self, temp_dir: Path) -> None:
        specify_dir = temp_dir / ".specify"
        specify_dir.mkdir(parents=True)
        (specify_dir / "init-options.json").write_text(json.dumps({"speckit_version": "0.14.0"}))

        compat = check_template_compatibility(temp_dir)
        assert compat.status == "supported"
        assert compat.vendored_version == "0.14.0"
        assert compat.supported_range == SUPPORTED_SPECKIT_RANGE

    def test_unsupported_version(self, temp_dir: Path) -> None:
        specify_dir = temp_dir / ".specify"
        specify_dir.mkdir(parents=True)
        (specify_dir / "init-options.json").write_text(json.dumps({"speckit_version": "0.99.0"}))

        compat = check_template_compatibility(temp_dir)
        assert compat.status == "unsupported"
        assert compat.vendored_version == "0.99.0"

    def test_missing_file_is_unknown(self, temp_dir: Path) -> None:
        compat = check_template_compatibility(temp_dir)
        assert compat.status == "unknown"
        assert compat.vendored_version is None

    def test_missing_field_is_unknown(self, temp_dir: Path) -> None:
        specify_dir = temp_dir / ".specify"
        specify_dir.mkdir(parents=True)
        (specify_dir / "init-options.json").write_text(json.dumps({"ai": "claude"}))

        compat = check_template_compatibility(temp_dir)
        assert compat.status == "unknown"

    def test_boundary_below_range_is_unsupported(self, temp_dir: Path) -> None:
        specify_dir = temp_dir / ".specify"
        specify_dir.mkdir(parents=True)
        (specify_dir / "init-options.json").write_text(json.dumps({"speckit_version": "0.13.9"}))

        compat = check_template_compatibility(temp_dir)
        assert compat.status == "unsupported"

    def test_boundary_at_upper_exclusive_is_unsupported(self, temp_dir: Path) -> None:
        specify_dir = temp_dir / ".specify"
        specify_dir.mkdir(parents=True)
        (specify_dir / "init-options.json").write_text(json.dumps({"speckit_version": "0.17.0"}))

        compat = check_template_compatibility(temp_dir)
        assert compat.status == "unsupported"

    @pytest.mark.parametrize("version", ["0.14.0", "0.15.2", "0.16.0"])
    def test_verified_versions_are_supported(self, temp_dir: Path, version: str) -> None:
        specify_dir = temp_dir / ".specify"
        specify_dir.mkdir(parents=True)
        (specify_dir / "init-options.json").write_text(json.dumps({"speckit_version": version}))

        compat = check_template_compatibility(temp_dir)
        assert compat.status == "supported"
