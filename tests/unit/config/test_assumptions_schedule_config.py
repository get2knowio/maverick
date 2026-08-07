"""Tests for the ``assumptions.schedule`` and ``assumptions.resolution`` config blocks.

See specs/054-assumption-batch-scheduler/data-model.md section 2 and
specs/054-assumption-batch-scheduler/contracts/config-schema.md for the
full ``schedule`` contract. ``assumptions.schedule`` is the delivery-policy
block for ``maverick notify``; the ntfy endpoint itself continues to come
from the existing ``NotificationConfig`` (``notifications:`` block) —
deliberately not duplicated here.

``assumptions.resolution`` (spec 055-learned-assumption-resolution) is a
sibling block gating auto-resolution of low-severity assumption entries;
see specs/055-learned-assumption-resolution/contracts/config-schema.md and
data-model.md's "Config" section for its full contract.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from maverick.assumptions import matching
from maverick.config import (
    AssumptionResolutionConfig,
    AssumptionScheduleConfig,
    AssumptionsConfig,
    AutoResolvePolicyConfig,
    AutoWaivePolicyConfig,
    MaverickConfig,
    QuietHoursConfig,
    load_config,
)
from maverick.exceptions import ConfigError


class TestAssumptionsConfigDefaults:
    """``AssumptionsConfig`` defaults to an inert scheduler (FR-021)."""

    def test_schedule_defaults_to_none(self) -> None:
        config = AssumptionsConfig()
        assert config.schedule is None

    def test_resolution_defaults_to_none(self) -> None:
        """New (055): ``resolution`` absent means auto-resolution is inert."""
        config = AssumptionsConfig()
        assert config.resolution is None

    def test_maverick_config_wires_assumptions_with_default_factory(self) -> None:
        config = MaverickConfig()
        assert isinstance(config.assumptions, AssumptionsConfig)
        assert config.assumptions.schedule is None
        assert config.assumptions.resolution is None

    def test_maverick_config_assumptions_instances_are_independent(self) -> None:
        """``default_factory`` must not share mutable state across instances."""
        a = MaverickConfig()
        b = MaverickConfig()
        assert a.assumptions is not b.assumptions


class TestAssumptionScheduleConfigDefaults:
    """Defaults for the fields that have them (windows is required)."""

    def test_requires_windows(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig()

    def test_defaults_match_contract(self) -> None:
        schedule = AssumptionScheduleConfig(windows=["09:00", "17:00"])
        assert schedule.windows == ["09:00", "17:00"]
        assert schedule.quiet_hours is None
        assert schedule.high_overrides_quiet is True
        assert schedule.min_batch_size == 1
        assert schedule.max_entry_age_hours == 24
        assert schedule.renotify_backoff_hours == [4, 8, 16, 24]
        assert schedule.auto_waive_low is None


class TestWindowsValidation:
    """``windows`` must be a non-empty list of unique ``HH:MM`` strings."""

    def test_empty_windows_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig(windows=[])

    @pytest.mark.parametrize(
        "bad_window",
        ["9:00", "09:0", "24:00", "09:60", "0900", "9am", "09:00:00", ""],
    )
    def test_malformed_window_rejected(self, bad_window: str) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig(windows=[bad_window])

    def test_valid_window_boundaries_accepted(self) -> None:
        schedule = AssumptionScheduleConfig(windows=["00:00", "23:59"])
        assert schedule.windows == ["00:00", "23:59"]

    def test_duplicate_windows_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig(windows=["09:00", "09:00"])

    def test_single_window_accepted(self) -> None:
        schedule = AssumptionScheduleConfig(windows=["09:00"])
        assert schedule.windows == ["09:00"]


class TestQuietHoursConfig:
    """``quiet_hours`` validates HH:MM and rejects ``start == end``."""

    def test_valid_quiet_hours_spanning_midnight(self) -> None:
        quiet = QuietHoursConfig(start="22:00", end="07:00")
        assert quiet.start == "22:00"
        assert quiet.end == "07:00"

    def test_valid_quiet_hours_same_day(self) -> None:
        quiet = QuietHoursConfig(start="01:00", end="05:00")
        assert quiet.start == "01:00"
        assert quiet.end == "05:00"

    def test_start_equals_end_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QuietHoursConfig(start="22:00", end="22:00")

    @pytest.mark.parametrize("field", ["start", "end"])
    def test_malformed_time_rejected(self, field: str) -> None:
        kwargs = {"start": "22:00", "end": "07:00"}
        kwargs[field] = "25:99"
        with pytest.raises(ValidationError):
            QuietHoursConfig(**kwargs)

    def test_quiet_hours_absent_by_default(self) -> None:
        schedule = AssumptionScheduleConfig(windows=["09:00"])
        assert schedule.quiet_hours is None

    def test_quiet_hours_wired_on_schedule(self) -> None:
        schedule = AssumptionScheduleConfig(
            windows=["09:00"],
            quiet_hours=QuietHoursConfig(start="22:00", end="07:00"),
        )
        assert schedule.quiet_hours is not None
        assert schedule.quiet_hours.start == "22:00"
        assert schedule.quiet_hours.end == "07:00"

    def test_quiet_hours_start_equals_end_rejected_via_schedule(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig(
                windows=["09:00"],
                quiet_hours={"start": "22:00", "end": "22:00"},
            )


class TestMinBatchSizeAndMaxEntryAge:
    def test_min_batch_size_ge_one(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig(windows=["09:00"], min_batch_size=0)

    def test_max_entry_age_hours_ge_one(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig(windows=["09:00"], max_entry_age_hours=0)

    def test_min_batch_size_override(self) -> None:
        schedule = AssumptionScheduleConfig(windows=["09:00"], min_batch_size=3)
        assert schedule.min_batch_size == 3

    def test_high_overrides_quiet_override(self) -> None:
        schedule = AssumptionScheduleConfig(windows=["09:00"], high_overrides_quiet=False)
        assert schedule.high_overrides_quiet is False


class TestRenotifyBackoffHours:
    """Non-empty, each ``> 0``, non-decreasing (FR-007)."""

    def test_empty_backoff_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig(windows=["09:00"], renotify_backoff_hours=[])

    def test_non_positive_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig(windows=["09:00"], renotify_backoff_hours=[4, 0, 8])

    def test_negative_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig(windows=["09:00"], renotify_backoff_hours=[-1])

    def test_decreasing_sequence_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig(windows=["09:00"], renotify_backoff_hours=[8, 4])

    def test_non_decreasing_with_repeats_accepted(self) -> None:
        """Non-decreasing allows equal-value repeats (last value repeats indefinitely)."""
        schedule = AssumptionScheduleConfig(windows=["09:00"], renotify_backoff_hours=[4, 4, 8])
        assert schedule.renotify_backoff_hours == [4, 4, 8]

    def test_strictly_increasing_accepted(self) -> None:
        schedule = AssumptionScheduleConfig(windows=["09:00"], renotify_backoff_hours=[2, 6, 12])
        assert schedule.renotify_backoff_hours == [2, 6, 12]

    def test_single_value_accepted(self) -> None:
        schedule = AssumptionScheduleConfig(windows=["09:00"], renotify_backoff_hours=[6])
        assert schedule.renotify_backoff_hours == [6]


class TestAutoWaivePolicyConfig:
    """``enabled: true`` without ``rationale`` is rejected."""

    def test_defaults(self) -> None:
        policy = AutoWaivePolicyConfig()
        assert policy.enabled is False
        assert policy.after_hours == 168
        assert policy.rationale is None

    def test_enabled_without_rationale_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AutoWaivePolicyConfig(enabled=True)

    def test_enabled_with_empty_rationale_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AutoWaivePolicyConfig(enabled=True, rationale="")

    def test_enabled_with_rationale_accepted(self) -> None:
        policy = AutoWaivePolicyConfig(
            enabled=True,
            rationale="accepted-risk: low-severity assumptions expire after a week",
        )
        assert policy.enabled is True
        assert policy.rationale == ("accepted-risk: low-severity assumptions expire after a week")

    def test_disabled_without_rationale_accepted(self) -> None:
        policy = AutoWaivePolicyConfig(enabled=False)
        assert policy.enabled is False
        assert policy.rationale is None

    def test_after_hours_ge_one(self) -> None:
        with pytest.raises(ValidationError):
            AutoWaivePolicyConfig(enabled=True, after_hours=0, rationale="accepted-risk")

    def test_auto_waive_low_absent_by_default_on_schedule(self) -> None:
        schedule = AssumptionScheduleConfig(windows=["09:00"])
        assert schedule.auto_waive_low is None

    def test_auto_waive_low_wired_on_schedule(self) -> None:
        schedule = AssumptionScheduleConfig(
            windows=["09:00"],
            auto_waive_low=AutoWaivePolicyConfig(enabled=True, rationale="accepted-risk"),
        )
        assert schedule.auto_waive_low is not None
        assert schedule.auto_waive_low.enabled is True

    def test_auto_waive_low_enabled_without_rationale_rejected_via_schedule(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionScheduleConfig(
                windows=["09:00"],
                auto_waive_low={"enabled": True},
            )


class TestAutoResolvePolicyConfig:
    """``assumptions.resolution.auto_resolve_low`` (055): double opt-in.

    ``enabled`` defaults to ``False`` and ``confidence_threshold`` defaults
    to ``0.9``, bounded ``[0.75, 1.0]``. The lower bound is pinned to
    ``matching.PRESENTATION_THRESHOLD`` — "auto must be at least as strict
    as presentation" (clarify Q3) — see research.md R8.
    """

    def test_defaults(self) -> None:
        policy = AutoResolvePolicyConfig()
        assert policy.enabled is False
        assert policy.confidence_threshold == 0.9

    def test_enabled_override(self) -> None:
        policy = AutoResolvePolicyConfig(enabled=True)
        assert policy.enabled is True
        # confidence_threshold keeps its default even when enabled is overridden.
        assert policy.confidence_threshold == 0.9

    def test_confidence_threshold_override(self) -> None:
        policy = AutoResolvePolicyConfig(confidence_threshold=0.92)
        assert policy.confidence_threshold == 0.92

    def test_confidence_threshold_below_lower_bound_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AutoResolvePolicyConfig(confidence_threshold=0.5)

    def test_confidence_threshold_lower_boundary_accepted(self) -> None:
        policy = AutoResolvePolicyConfig(confidence_threshold=0.75)
        assert policy.confidence_threshold == 0.75

    def test_confidence_threshold_upper_boundary_accepted(self) -> None:
        policy = AutoResolvePolicyConfig(confidence_threshold=1.0)
        assert policy.confidence_threshold == 1.0

    def test_confidence_threshold_above_upper_bound_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AutoResolvePolicyConfig(confidence_threshold=1.1)

    def test_confidence_threshold_lower_bound_pinned_to_presentation_threshold(self) -> None:
        """Drift-pin (research.md R8): the ``ge`` bound must equal
        ``matching.PRESENTATION_THRESHOLD`` exactly — not merely near it.

        Two-sided check: the constant's own value must be accepted (proves
        the lower bound is not *stricter* than the constant), and one cent
        below it must be rejected (proves the lower bound is not *looser*
        than the constant). Together these pin ``ge=`` to the constant
        without introspecting Pydantic's internal constraint metadata.
        """
        # At-the-constant value is accepted (bound is not stricter than 0.75).
        policy = AutoResolvePolicyConfig(confidence_threshold=matching.PRESENTATION_THRESHOLD)
        assert policy.confidence_threshold == matching.PRESENTATION_THRESHOLD

        # Just below the constant is rejected (bound is not looser than 0.75).
        with pytest.raises(ValidationError):
            AutoResolvePolicyConfig(confidence_threshold=matching.PRESENTATION_THRESHOLD - 0.01)


class TestAssumptionResolutionConfig:
    """``assumptions.resolution``: ``auto_resolve_low`` absent by default."""

    def test_auto_resolve_low_defaults_to_none(self) -> None:
        config = AssumptionResolutionConfig()
        assert config.auto_resolve_low is None

    def test_auto_resolve_low_wired(self) -> None:
        config = AssumptionResolutionConfig(
            auto_resolve_low=AutoResolvePolicyConfig(enabled=True, confidence_threshold=0.92)
        )
        assert config.auto_resolve_low is not None
        assert config.auto_resolve_low.enabled is True
        assert config.auto_resolve_low.confidence_threshold == 0.92

    def test_auto_resolve_low_invalid_threshold_rejected_via_resolution(self) -> None:
        with pytest.raises(ValidationError):
            AssumptionResolutionConfig(auto_resolve_low={"confidence_threshold": 0.5})

    def test_resolution_wired_on_assumptions_config(self) -> None:
        config = AssumptionsConfig(
            resolution=AssumptionResolutionConfig(
                auto_resolve_low=AutoResolvePolicyConfig(enabled=True)
            )
        )
        assert config.resolution is not None
        assert config.resolution.auto_resolve_low is not None
        assert config.resolution.auto_resolve_low.enabled is True

    def test_schedule_and_resolution_independent(self) -> None:
        """Sibling blocks: setting one leaves the other at its own default."""
        config = AssumptionsConfig(
            resolution=AssumptionResolutionConfig(
                auto_resolve_low=AutoResolvePolicyConfig(enabled=True)
            )
        )
        assert config.schedule is None
        assert config.resolution is not None


class TestYamlAndEnvOverrides:
    """Loading through ``load_config`` / env-var precedence."""

    def test_yaml_full_schedule_round_trips(self, clean_env: None, temp_dir: Path) -> None:
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
notifications:
  enabled: true
  topic: my-maverick-topic

assumptions:
  schedule:
    windows: ["09:00", "17:00"]
    quiet_hours:
      start: "22:00"
      end: "07:00"
    high_overrides_quiet: true
    min_batch_size: 1
    max_entry_age_hours: 24
    renotify_backoff_hours: [4, 8, 16, 24]
    auto_waive_low:
      enabled: true
      after_hours: 168
      rationale: "accepted-risk: low-severity assumptions expire after a week"
"""
        )

        config = load_config()
        schedule = config.assumptions.schedule
        assert schedule is not None
        assert schedule.windows == ["09:00", "17:00"]
        assert schedule.quiet_hours is not None
        assert schedule.quiet_hours.start == "22:00"
        assert schedule.quiet_hours.end == "07:00"
        assert schedule.high_overrides_quiet is True
        assert schedule.min_batch_size == 1
        assert schedule.max_entry_age_hours == 24
        assert schedule.renotify_backoff_hours == [4, 8, 16, 24]
        assert schedule.auto_waive_low is not None
        assert schedule.auto_waive_low.enabled is True
        assert schedule.auto_waive_low.after_hours == 168

    def test_yaml_absent_schedule_stays_none(self, clean_env: None, temp_dir: Path) -> None:
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
notifications:
  enabled: false
"""
        )

        config = load_config()
        assert config.assumptions.schedule is None

    def test_yaml_full_resolution_round_trips(self, clean_env: None, temp_dir: Path) -> None:
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
assumptions:
  resolution:
    auto_resolve_low:
      enabled: true
      confidence_threshold: 0.92
"""
        )

        config = load_config()
        resolution = config.assumptions.resolution
        assert resolution is not None
        assert resolution.auto_resolve_low is not None
        assert resolution.auto_resolve_low.enabled is True
        assert resolution.auto_resolve_low.confidence_threshold == 0.92

    def test_yaml_absent_resolution_stays_none(self, clean_env: None, temp_dir: Path) -> None:
        """Absent ``assumptions.resolution`` block ⇒ ``config.assumptions.resolution is None``.

        Suggestions remain fully functional (they require no config);
        only auto-resolution is inert.
        """
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
notifications:
  enabled: false
"""
        )

        config = load_config()
        assert config.assumptions.resolution is None

    def test_yaml_resolution_block_present_auto_resolve_low_absent_stays_none(
        self, clean_env: None, temp_dir: Path
    ) -> None:
        """Block present but ``auto_resolve_low`` omitted behaves like absent."""
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
assumptions:
  resolution: {}
"""
        )

        config = load_config()
        resolution = config.assumptions.resolution
        assert resolution is not None
        assert resolution.auto_resolve_low is None

    def test_yaml_invalid_confidence_threshold_fails_config_load(
        self, clean_env: None, temp_dir: Path
    ) -> None:
        """FR-016: violating the ``confidence_threshold`` bounds fails config load.

        ``load_config`` wraps every Pydantic ``ValidationError`` into a
        ``ConfigError`` at the CLI boundary (see
        ``tests/unit/test_config.py::test_invalid_config_raises_config_error``
        for the established, codebase-wide contract) — this block is no
        exception.
        """
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
assumptions:
  resolution:
    auto_resolve_low:
      enabled: true
      confidence_threshold: 0.5
"""
        )

        with pytest.raises(ConfigError):
            load_config()

    def test_env_override_auto_resolve_low_enabled(
        self, clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
assumptions:
  resolution:
    auto_resolve_low:
      enabled: false
"""
        )
        monkeypatch.setenv("MAVERICK_ASSUMPTIONS__RESOLUTION__AUTO_RESOLVE_LOW__ENABLED", "true")

        config = load_config()
        assert config.assumptions.resolution is not None
        assert config.assumptions.resolution.auto_resolve_low is not None
        assert config.assumptions.resolution.auto_resolve_low.enabled is True

    def test_env_override_min_batch_size(
        self, clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
assumptions:
  schedule:
    windows: ["09:00"]
"""
        )
        monkeypatch.setenv("MAVERICK_ASSUMPTIONS__SCHEDULE__MIN_BATCH_SIZE", "5")

        config = load_config()
        assert config.assumptions.schedule is not None
        assert config.assumptions.schedule.min_batch_size == 5

    def test_env_override_windows_list(
        self, clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
assumptions:
  schedule:
    windows: ["09:00"]
"""
        )
        monkeypatch.setenv("MAVERICK_ASSUMPTIONS__SCHEDULE__WINDOWS", '["08:00", "20:00"]')

        config = load_config()
        assert config.assumptions.schedule is not None
        assert config.assumptions.schedule.windows == ["08:00", "20:00"]

    def test_env_override_high_overrides_quiet(
        self, clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
assumptions:
  schedule:
    windows: ["09:00"]
"""
        )
        monkeypatch.setenv("MAVERICK_ASSUMPTIONS__SCHEDULE__HIGH_OVERRIDES_QUIET", "false")

        config = load_config()
        assert config.assumptions.schedule is not None
        assert config.assumptions.schedule.high_overrides_quiet is False


class TestExports:
    """New models are part of the public ``maverick.config`` surface."""

    def test_all_exports(self) -> None:
        from maverick import config as config_module

        for name in (
            "AssumptionsConfig",
            "AssumptionScheduleConfig",
            "QuietHoursConfig",
            "AutoWaivePolicyConfig",
            "AssumptionResolutionConfig",
            "AutoResolvePolicyConfig",
        ):
            assert name in config_module.__all__
            assert hasattr(config_module, name)
