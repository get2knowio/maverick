"""Unit tests for AgentProviderRegistry."""

from __future__ import annotations

import pytest

from maverick.config import AgentProviderConfig, PermissionMode
from maverick.exceptions import ConfigError
from maverick.executor.provider_registry import AgentProviderRegistry

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_CMD_A = ["npx", "agent-a", "--acp"]
_CMD_B = ["npx", "agent-b", "--acp"]
_CMD_C = ["npx", "agent-c", "--acp"]


def _make_provider(
    command: list[str] = _CMD_A,
    *,
    default: bool = False,
    permission_mode: PermissionMode = PermissionMode.AUTO_APPROVE,
) -> AgentProviderConfig:
    return AgentProviderConfig(
        command=command,
        permission_mode=permission_mode,
        default=default,
    )


# ---------------------------------------------------------------------------
# from_config — explicit providers
# ---------------------------------------------------------------------------


class TestFromConfigExplicitProviders:
    def test_single_explicit_default_provider(self) -> None:
        providers = {"alpha": _make_provider(_CMD_A, default=True)}
        registry = AgentProviderRegistry.from_config(providers)
        assert registry.names() == ["alpha"]
        assert registry.default() == ("alpha", providers["alpha"])

    def test_multiple_non_default_providers_with_one_default(self) -> None:
        providers = {
            "alpha": _make_provider(_CMD_A, default=True),
            "beta": _make_provider(_CMD_B, default=False),
            "gamma": _make_provider(_CMD_C, default=False),
        }
        registry = AgentProviderRegistry.from_config(providers)
        assert sorted(registry.names()) == ["alpha", "beta", "gamma"]
        name, cfg = registry.default()
        assert name == "alpha"
        assert cfg is providers["alpha"]

    def test_provider_marked_default_true_is_default(self) -> None:
        providers = {
            "first": _make_provider(_CMD_A, default=False),
            "second": _make_provider(_CMD_B, default=True),
        }
        registry = AgentProviderRegistry.from_config(providers)
        name, cfg = registry.default()
        assert name == "second"
        assert cfg is providers["second"]

    def test_multiple_defaults_raises_config_error(self) -> None:
        providers = {
            "alpha": _make_provider(_CMD_A, default=True),
            "beta": _make_provider(_CMD_B, default=True),
        }
        with pytest.raises(ConfigError):
            AgentProviderRegistry.from_config(providers)


# ---------------------------------------------------------------------------
# from_config — empty dict → synthesize default Claude Code provider
# ---------------------------------------------------------------------------


class TestFromConfigEmpty:
    def test_empty_dict_synthesizes_default_provider(self) -> None:
        registry = AgentProviderRegistry.from_config({})
        # Should have exactly one provider named "claude"
        assert registry.names() == ["claude"]

    def test_synthesized_provider_is_default(self) -> None:
        registry = AgentProviderRegistry.from_config({})
        name, cfg = registry.default()
        assert name == "claude"

    def test_synthesized_provider_has_auto_approve_mode(self) -> None:
        registry = AgentProviderRegistry.from_config({})
        _, cfg = registry.default()
        assert cfg.permission_mode == PermissionMode.AUTO_APPROVE

    def test_synthesized_provider_has_default_true(self) -> None:
        registry = AgentProviderRegistry.from_config({})
        _, cfg = registry.default()
        assert cfg.default is True

    def test_synthesized_provider_command_contains_acp_bridge(self) -> None:
        registry = AgentProviderRegistry.from_config({})
        _, cfg = registry.default()
        # Command should reference the ACP bridge binary
        assert any("claude-agent-acp" in part for part in cfg.command)


# ---------------------------------------------------------------------------
# get(name)
# ---------------------------------------------------------------------------


class TestGet:
    def test_get_existing_provider_returns_config(self) -> None:
        cfg = _make_provider(_CMD_A, default=True)
        registry = AgentProviderRegistry.from_config({"my-provider": cfg})
        result = registry.get("my-provider")
        assert result is cfg

    def test_get_missing_provider_raises_config_error(self) -> None:
        registry = AgentProviderRegistry.from_config(
            {"alpha": _make_provider(_CMD_A, default=True)}
        )
        with pytest.raises(ConfigError):
            registry.get("nonexistent")

    def test_get_missing_provider_error_mentions_provider_name(self) -> None:
        registry = AgentProviderRegistry.from_config(
            {"alpha": _make_provider(_CMD_A, default=True)}
        )
        with pytest.raises(ConfigError) as exc_info:
            registry.get("missing-provider")
        assert "missing-provider" in str(exc_info.value)

    def test_get_each_provider_in_multi_registry(self) -> None:
        providers = {
            "alpha": _make_provider(_CMD_A, default=True),
            "beta": _make_provider(_CMD_B, default=False),
        }
        registry = AgentProviderRegistry.from_config(providers)
        assert registry.get("alpha") is providers["alpha"]
        assert registry.get("beta") is providers["beta"]


# ---------------------------------------------------------------------------
# default()
# ---------------------------------------------------------------------------


class TestDefault:
    def test_default_returns_name_and_config_tuple(self) -> None:
        cfg = _make_provider(_CMD_A, default=True)
        registry = AgentProviderRegistry.from_config({"main": cfg})
        result = registry.default()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_default_returns_correct_name(self) -> None:
        providers = {
            "primary": _make_provider(_CMD_A, default=True),
            "secondary": _make_provider(_CMD_B, default=False),
        }
        registry = AgentProviderRegistry.from_config(providers)
        name, _ = registry.default()
        assert name == "primary"

    def test_default_returns_correct_config(self) -> None:
        primary_cfg = _make_provider(_CMD_A, default=True)
        registry = AgentProviderRegistry.from_config({"primary": primary_cfg})
        _, cfg = registry.default()
        assert cfg is primary_cfg

    def test_synthesized_single_provider_is_default(self) -> None:
        # When only one provider exists but no explicit default=True,
        # the synthesized provider has default=True so it still works.
        registry = AgentProviderRegistry.from_config({})
        name, cfg = registry.default()
        assert name == "claude"
        assert cfg.default is True

    def test_multiple_providers_default_is_the_one_marked_true(self) -> None:
        providers = {
            "a": _make_provider(_CMD_A, default=False),
            "b": _make_provider(_CMD_B, default=True),
            "c": _make_provider(_CMD_C, default=False),
        }
        registry = AgentProviderRegistry.from_config(providers)
        name, cfg = registry.default()
        assert name == "b"
        assert cfg is providers["b"]


# ---------------------------------------------------------------------------
# items()
# ---------------------------------------------------------------------------


class TestItems:
    def test_items_returns_sorted_tuples(self) -> None:
        providers = {
            "zebra": _make_provider(_CMD_A, default=True),
            "alpha": _make_provider(_CMD_B, default=False),
        }
        registry = AgentProviderRegistry.from_config(providers)
        items = registry.items()
        assert len(items) == 2
        assert items[0][0] == "alpha"
        assert items[1][0] == "zebra"
        assert items[0][1] is providers["alpha"]
        assert items[1][1] is providers["zebra"]

    def test_items_single_provider(self) -> None:
        cfg = _make_provider(_CMD_A, default=True)
        registry = AgentProviderRegistry.from_config({"solo": cfg})
        items = registry.items()
        assert items == [("solo", cfg)]

    def test_items_synthesized_registry(self) -> None:
        registry = AgentProviderRegistry.from_config({})
        items = registry.items()
        assert len(items) == 1
        assert items[0][0] == "claude"

    def test_items_returns_list_of_tuples(self) -> None:
        registry = AgentProviderRegistry.from_config(
            {"alpha": _make_provider(_CMD_A, default=True)}
        )
        items = registry.items()
        assert isinstance(items, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in items)


# ---------------------------------------------------------------------------
# names()
# ---------------------------------------------------------------------------


class TestNames:
    def test_names_returns_sorted_list(self) -> None:
        providers = {
            "zebra": _make_provider(_CMD_A, default=True),
            "alpha": _make_provider(_CMD_B, default=False),
            "mango": _make_provider(_CMD_C, default=False),
        }
        registry = AgentProviderRegistry.from_config(providers)
        assert registry.names() == ["alpha", "mango", "zebra"]

    def test_names_single_provider(self) -> None:
        registry = AgentProviderRegistry.from_config(
            {"solo": _make_provider(_CMD_A, default=True)}
        )
        assert registry.names() == ["solo"]

    def test_names_synthesized_registry(self) -> None:
        registry = AgentProviderRegistry.from_config({})
        assert registry.names() == ["claude"]

    def test_names_returns_list_type(self) -> None:
        registry = AgentProviderRegistry.from_config(
            {"alpha": _make_provider(_CMD_A, default=True)}
        )
        assert isinstance(registry.names(), list)


# ---------------------------------------------------------------------------
# __init__ validation
# ---------------------------------------------------------------------------


class TestInit:
    def test_multiple_defaults_raises_config_error_via_init(self) -> None:
        providers = {
            "x": _make_provider(_CMD_A, default=True),
            "y": _make_provider(_CMD_B, default=True),
        }
        with pytest.raises(ConfigError):
            AgentProviderRegistry(providers)

    def test_multiple_defaults_error_mentions_field(self) -> None:
        providers = {
            "x": _make_provider(_CMD_A, default=True),
            "y": _make_provider(_CMD_B, default=True),
        }
        with pytest.raises(ConfigError) as exc_info:
            AgentProviderRegistry(providers)
        assert exc_info.value.field == "agent_providers"

    def test_no_default_provider_raises_config_error(self) -> None:
        # No provider has default=True; __init__ must raise ConfigError rather
        # than silently falling back to "claude" (which would cause a KeyError
        # in default() if "claude" is not registered).
        providers = {
            "alpha": _make_provider(_CMD_A, default=False),
        }
        with pytest.raises(ConfigError) as exc_info:
            AgentProviderRegistry(providers)
        assert exc_info.value.field == "agent_providers"

    def test_no_default_provider_error_mentions_providers(self) -> None:
        # Error message should list the available provider names.
        providers = {
            "alpha": _make_provider(_CMD_A, default=False),
            "beta": _make_provider(_CMD_B, default=False),
        }
        with pytest.raises(ConfigError) as exc_info:
            AgentProviderRegistry(providers)
        error_message = str(exc_info.value)
        assert "alpha" in error_message or "beta" in error_message
