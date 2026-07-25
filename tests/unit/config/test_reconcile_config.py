"""Tests for the ``reconcile.*`` round-budget settings in MaverickConfig.

See specs/051-reconcile-changed-answers/data-model.md section 5 for the
contract: ``resolution_rounds`` bounds the conflict-resolution loop and
``semantic_rounds`` bounds the semantic-dependents loop, each per changed
answer being reconciled.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from maverick.config import ReconcileConfig, load_config


def test_defaults() -> None:
    """Defaults must match data-model.md section 5 (both budgets = 3)."""
    config = ReconcileConfig()
    assert config.resolution_rounds == 3
    assert config.semantic_rounds == 3
    assert config.mid_flight is True


@pytest.mark.parametrize(
    "field",
    ["resolution_rounds", "semantic_rounds"],
)
def test_rejects_zero(field: str) -> None:
    """``ge=1`` — a zero round budget is invalid for either loop."""
    with pytest.raises(ValidationError):
        ReconcileConfig(**{field: 0})


def test_yaml_override(clean_env: None, temp_dir: Path) -> None:
    """A ``reconcile:`` section in maverick.yaml overrides the default."""
    os.chdir(temp_dir)

    config_path = temp_dir / "maverick.yaml"
    config_path.write_text(
        """
reconcile:
  resolution_rounds: 5
"""
    )

    config = load_config()
    assert config.reconcile.resolution_rounds == 5
    # Untouched field keeps its default.
    assert config.reconcile.semantic_rounds == 3


def test_env_var_override(
    clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``MAVERICK_RECONCILE__RESOLUTION_ROUNDS`` overrides via env nesting."""
    os.chdir(temp_dir)
    monkeypatch.setenv("MAVERICK_RECONCILE__RESOLUTION_ROUNDS", "7")

    config = load_config()
    assert config.reconcile.resolution_rounds == 7


def test_mid_flight_defaults_true() -> None:
    """``mid_flight`` defaults to True (052 research R9: opt-out kill-switch)."""
    config = ReconcileConfig()
    assert config.mid_flight is True


def test_mid_flight_yaml_override_false(clean_env: None, temp_dir: Path) -> None:
    """``reconcile.mid_flight: false`` in maverick.yaml disables the fly trigger."""
    os.chdir(temp_dir)

    config_path = temp_dir / "maverick.yaml"
    config_path.write_text(
        """
reconcile:
  mid_flight: false
"""
    )

    config = load_config()
    assert config.reconcile.mid_flight is False
    # Untouched fields keep their defaults.
    assert config.reconcile.resolution_rounds == 3
    assert config.reconcile.semantic_rounds == 3
