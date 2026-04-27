"""Tests for maverick.init.provider_discovery."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from maverick.init.provider_discovery import (
    PROVIDER_PREFERENCE_ORDER,
    ProviderDiscoveryResult,
    ProviderProbeResult,
    discover_providers,
)

# ---------------------------------------------------------------------------
# ProviderProbeResult
# ---------------------------------------------------------------------------


class TestProviderProbeResult:
    def test_to_dict_found(self) -> None:
        probe = ProviderProbeResult(
            name="claude",
            display_name="Claude",
            binary="claude-agent-acp",
            found=True,
        )
        d = probe.to_dict()
        assert d == {
            "name": "claude",
            "display_name": "Claude",
            "binary": "claude-agent-acp",
            "found": True,
        }
        assert "error" not in d

    def test_to_dict_with_error(self) -> None:
        probe = ProviderProbeResult(
            name="gemini",
            display_name="Gemini",
            binary="gemini",
            found=False,
            error="permission denied",
        )
        d = probe.to_dict()
        assert d["error"] == "permission denied"
        assert d["found"] is False

    def test_frozen(self) -> None:
        probe = ProviderProbeResult(
            name="claude",
            display_name="Claude",
            binary="claude-agent-acp",
            found=True,
        )
        with pytest.raises(AttributeError):
            probe.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProviderDiscoveryResult
# ---------------------------------------------------------------------------


class TestProviderDiscoveryResult:
    def test_found_providers_filters_correctly(self) -> None:
        result = ProviderDiscoveryResult(
            providers=(
                ProviderProbeResult("claude", "Claude", "claude-agent-acp", True),
                ProviderProbeResult("copilot", "GitHub Copilot", "copilot", False),
                ProviderProbeResult("gemini", "Gemini", "gemini", True),
            ),
            default_provider="claude",
        )
        found = result.found_providers
        assert len(found) == 2
        assert found[0].name == "claude"
        assert found[1].name == "gemini"

    def test_found_providers_empty(self) -> None:
        result = ProviderDiscoveryResult(
            providers=(ProviderProbeResult("claude", "Claude", "claude-agent-acp", False),),
            default_provider=None,
        )
        assert result.found_providers == ()

    def test_to_dict(self) -> None:
        result = ProviderDiscoveryResult(
            providers=(ProviderProbeResult("claude", "Claude", "claude-agent-acp", True),),
            default_provider="claude",
            duration_ms=5,
        )
        d = result.to_dict()
        assert d["default_provider"] == "claude"
        assert d["duration_ms"] == 5
        assert len(d["providers"]) == 1
        assert d["providers"][0]["name"] == "claude"


# ---------------------------------------------------------------------------
# discover_providers()
# ---------------------------------------------------------------------------


class TestDiscoverProviders:
    @pytest.mark.asyncio
    async def test_all_providers_found(self) -> None:
        with patch("maverick.init.provider_discovery.shutil.which", return_value="/usr/bin/x"):
            result = await discover_providers()

        assert len(result.providers) == len(PROVIDER_PREFERENCE_ORDER)
        assert all(p.found for p in result.providers)
        assert result.default_provider == "claude"

    @pytest.mark.asyncio
    async def test_no_providers_found(self) -> None:
        with patch("maverick.init.provider_discovery.shutil.which", return_value=None):
            result = await discover_providers()

        assert len(result.providers) == len(PROVIDER_PREFERENCE_ORDER)
        assert not any(p.found for p in result.providers)
        assert result.default_provider is None
        assert result.found_providers == ()

    @pytest.mark.asyncio
    async def test_only_claude_found(self) -> None:
        def which_side_effect(binary: str) -> str | None:
            return "/usr/bin/claude-agent-acp" if binary == "claude-agent-acp" else None

        with patch(
            "maverick.init.provider_discovery.shutil.which",
            side_effect=which_side_effect,
        ):
            result = await discover_providers()

        assert len(result.found_providers) == 1
        assert result.found_providers[0].name == "claude"
        assert result.default_provider == "claude"

    @pytest.mark.asyncio
    async def test_copilot_and_gemini_found_copilot_default(self) -> None:
        """Copilot is preferred over Gemini per PROVIDER_PREFERENCE_ORDER."""

        def which_side_effect(binary: str) -> str | None:
            if binary in ("copilot", "gemini"):
                return f"/usr/bin/{binary}"
            return None

        with patch(
            "maverick.init.provider_discovery.shutil.which",
            side_effect=which_side_effect,
        ):
            result = await discover_providers()

        assert len(result.found_providers) == 2
        assert result.default_provider == "copilot"

    @pytest.mark.asyncio
    async def test_claude_preferred_over_copilot(self) -> None:
        """Claude takes priority over Copilot when both are available."""
        with patch("maverick.init.provider_discovery.shutil.which", return_value="/usr/bin/x"):
            result = await discover_providers()

        assert result.default_provider == "claude"

    @pytest.mark.asyncio
    async def test_probe_order_matches_preference(self) -> None:
        with patch("maverick.init.provider_discovery.shutil.which", return_value=None):
            result = await discover_providers()

        names = [p.name for p in result.providers]
        assert names == list(PROVIDER_PREFERENCE_ORDER)

    @pytest.mark.asyncio
    async def test_which_exception_handled_gracefully(self) -> None:
        """shutil.which raising an exception should not crash discovery."""

        def which_side_effect(binary: str) -> str | None:
            if binary == "claude-agent-acp":
                raise OSError("permission denied")
            return "/usr/bin/copilot" if binary == "copilot" else None

        with patch(
            "maverick.init.provider_discovery.shutil.which",
            side_effect=which_side_effect,
        ):
            result = await discover_providers()

        claude_probe = next(p for p in result.providers if p.name == "claude")
        assert claude_probe.found is False
        assert claude_probe.error == "permission denied"
        assert result.default_provider == "copilot"

    @pytest.mark.asyncio
    async def test_duration_ms_populated(self) -> None:
        with patch("maverick.init.provider_discovery.shutil.which", return_value=None):
            result = await discover_providers()

        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_correct_binaries_probed(self) -> None:
        """Verify the correct binary name is used for each provider."""
        with patch("maverick.init.provider_discovery.shutil.which", return_value=None):
            result = await discover_providers()

        binaries = {p.name: p.binary for p in result.providers}
        assert binaries["claude"] == "claude-agent-acp"
        assert binaries["copilot"] == "copilot"
        assert binaries["gemini"] == "gemini"
        assert binaries["opencode"] == "opencode"

    @pytest.mark.asyncio
    async def test_display_names(self) -> None:
        with patch("maverick.init.provider_discovery.shutil.which", return_value=None):
            result = await discover_providers()

        names = {p.name: p.display_name for p in result.providers}
        assert names["claude"] == "Claude"
        assert names["copilot"] == "GitHub Copilot"
        assert names["gemini"] == "Gemini"
        assert names["opencode"] == "OpenCode"

    @pytest.mark.asyncio
    async def test_opencode_does_not_displace_claude_as_default(self) -> None:
        """When both claude and opencode are installed, claude wins.

        opencode is appended last in PROVIDER_PREFERENCE_ORDER so existing
        users who add the opencode binary don't suddenly find their default
        provider switched out from under them.
        """

        def _which(binary: str) -> str | None:
            return (
                f"/usr/local/bin/{binary}"
                if binary
                in {
                    "claude-agent-acp",
                    "opencode",
                }
                else None
            )

        with patch(
            "maverick.init.provider_discovery.shutil.which",
            side_effect=_which,
        ):
            result = await discover_providers()
        assert result.default_provider == "claude"

    @pytest.mark.asyncio
    async def test_opencode_becomes_default_when_alone(self) -> None:
        """If opencode is the only installed provider, it becomes default."""

        def _which(binary: str) -> str | None:
            return f"/usr/local/bin/{binary}" if binary == "opencode" else None

        with patch(
            "maverick.init.provider_discovery.shutil.which",
            side_effect=_which,
        ):
            result = await discover_providers()
        assert result.default_provider == "opencode"
