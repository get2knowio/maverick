"""Tests for the ``protection:`` config block (056-context-file-protection).

See specs/056-context-file-protection/contracts/protection-config.md for the
full contract and specs/056-context-file-protection/data-model.md's
"ProtectionConfig" section. ``ProtectionConfig`` is the validated form of the
raw ``protection`` passthrough on ``MaverickConfig``; ``lookup_protection_config``
is the lenient loader that mirrors ``maverick.config.lookup_tiers_config``:
malformed input degrades to defaults with a warning, never a startup failure.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from maverick.config import MaverickConfig, load_config
from maverick.protection.config import ProtectionConfig, lookup_protection_config


class TestProtectionConfigDefaults:
    """``ProtectionConfig`` defaults to an empty (no-op) block."""

    def test_defaults(self) -> None:
        config = ProtectionConfig()
        assert config.additional_globs == []
        assert config.allowlist == []

    def test_maverick_config_protection_defaults_to_none(self) -> None:
        config = MaverickConfig()
        assert config.protection is None


class TestLookupProtectionConfig:
    """``lookup_protection_config`` — lenient loader, ``lookup_tiers_config`` idiom."""

    def test_absent_block_returns_defaults_no_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = MaverickConfig()
        assert config.protection is None

        with caplog.at_level(logging.WARNING):
            result = lookup_protection_config(config)

        assert result == ProtectionConfig()
        assert result.additional_globs == []
        assert result.allowlist == []
        assert "protection_config" not in caplog.text

    def test_non_dict_shape_degrades_to_defaults_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Bypass YAML/pydantic-settings entirely — construct directly with a
        # non-dict value to exercise the "invalid shape" degrade path.
        config = MaverickConfig.model_construct(protection=["oops"])

        with caplog.at_level(logging.WARNING):
            result = lookup_protection_config(config)

        assert result == ProtectionConfig()
        assert "protection_config_invalid_shape" in caplog.text

    def test_wrong_typed_field_degrades_to_defaults_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = MaverickConfig.model_construct(protection={"additional_globs": "not-a-list"})

        with caplog.at_level(logging.WARNING):
            result = lookup_protection_config(config)

        assert result == ProtectionConfig()
        assert "protection_config_parse_failed" in caplog.text

    def test_valid_dict_parses(self) -> None:
        config = MaverickConfig.model_construct(
            protection={
                "additional_globs": ["docs/agent-rules/**", "GEMINI.md"],
                "allowlist": ["AGENTS.md"],
            }
        )

        result = lookup_protection_config(config)

        assert result.additional_globs == ["docs/agent-rules/**", "GEMINI.md"]
        assert result.allowlist == ["AGENTS.md"]


class TestYamlAndEnvOverrides:
    """Loading through ``load_config`` / env-var precedence."""

    def test_yaml_full_block_round_trips(self, clean_env: None, temp_dir: Path) -> None:
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
protection:
  additional_globs:
    - "docs/agent-rules/**"
    - "GEMINI.md"
  allowlist:
    - "AGENTS.md"
"""
        )

        config = load_config()
        assert config.protection == {
            "additional_globs": ["docs/agent-rules/**", "GEMINI.md"],
            "allowlist": ["AGENTS.md"],
        }

        parsed = lookup_protection_config(config)
        assert parsed.additional_globs == ["docs/agent-rules/**", "GEMINI.md"]
        assert parsed.allowlist == ["AGENTS.md"]

    def test_yaml_absent_block_stays_none(self, clean_env: None, temp_dir: Path) -> None:
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
notifications:
  enabled: false
"""
        )

        config = load_config()
        assert config.protection is None
        assert lookup_protection_config(config) == ProtectionConfig()

    def test_yaml_malformed_scalar_block_does_not_raise(
        self, clean_env: None, temp_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A plain scalar (not a mapping) for ``protection:`` must not fail
        config load (FR-012) — it degrades to defaults with a warning at
        ``lookup_protection_config`` time.
        """
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
protection: "not-a-dict"
"""
        )

        config = load_config()
        assert config.protection == "not-a-dict"

        with caplog.at_level(logging.WARNING):
            result = lookup_protection_config(config)

        assert result == ProtectionConfig()
        assert "protection_config_invalid_shape" in caplog.text

    def test_env_override(
        self, clean_env: None, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env-var override for a raw ``dict[str, Any] | None`` field.

        Unlike a typed nested ``BaseModel`` field (e.g.
        ``assumptions.schedule``), pydantic-settings' ``__``-delimited
        nested-key parsing (``MAVERICK_PROTECTION__ADDITIONAL_GLOBS=...``)
        does not cleanly resolve into a raw ``dict[str, Any]``-typed field:
        empirically it *does* set the nested key, but the leaf value is
        left as an unparsed string (``{"additional_globs":
        '["docs/**"]'}``) rather than a real list — nested-env leaf
        decoding is only wired for fields whose annotation is itself a
        ``BaseModel`` pydantic-settings can introspect field-by-field.
        The whole ``MAVERICK_PROTECTION`` var as one JSON object, however,
        round-trips correctly — pydantic-settings JSON-decodes the entire
        value for any complex-typed field, and the field's
        ``mode="wrap"`` validator (``_protection_lenient_shape``) lets a
        well-formed decoded dict validate normally.
        """
        os.chdir(temp_dir)
        config_path = temp_dir / "maverick.yaml"
        config_path.write_text(
            """
protection:
  additional_globs: ["placeholder/**"]
"""
        )
        monkeypatch.setenv(
            "MAVERICK_PROTECTION",
            '{"additional_globs": ["docs/**"], "allowlist": ["AGENTS.md"]}',
        )

        config = load_config()
        assert config.protection == {
            "additional_globs": ["docs/**"],
            "allowlist": ["AGENTS.md"],
        }

        parsed = lookup_protection_config(config)
        assert parsed.additional_globs == ["docs/**"]
        assert parsed.allowlist == ["AGENTS.md"]


class TestExports:
    """``maverick.protection.config.__all__`` surface."""

    def test_all_exports(self) -> None:
        from maverick.protection import config as protection_config_module

        for name in ("ProtectionConfig", "lookup_protection_config"):
            assert name in protection_config_module.__all__
            assert hasattr(protection_config_module, name)
