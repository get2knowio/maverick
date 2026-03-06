"""AgentProviderRegistry — resolves ACP agent provider names to configurations."""

from __future__ import annotations

from maverick.config import AgentProviderConfig, PermissionMode
from maverick.exceptions import ConfigError
from maverick.logging import get_logger

__all__ = ["AgentProviderRegistry"]

logger = get_logger(__name__)

#: Default Claude Code provider command (zero-config fallback)
#: Uses the Zed ACP bridge (@zed-industries/claude-agent-acp) which wraps
#: Claude Code's Agent SDK and exposes it as an ACP agent over stdio.
_DEFAULT_CLAUDE_COMMAND: list[str] = [
    "claude-agent-acp",
]

#: Name used for the synthesized default Claude Code provider
_DEFAULT_PROVIDER_NAME: str = "claude"


class AgentProviderRegistry:
    """Resolves provider names to ACP agent configurations (FR-015).

    Validates exactly one default provider exists. Synthesizes a default
    Claude Code provider when no providers are configured (zero-config mode).

    Args:
        providers: Validated provider name → config mapping.

    Raises:
        ConfigError: If multiple providers have default=True.
    """

    def __init__(self, providers: dict[str, AgentProviderConfig]) -> None:
        # Validate exactly one default
        defaults = [name for name, cfg in providers.items() if cfg.default]
        if len(defaults) > 1:
            raise ConfigError(
                message=(
                    f"Multiple default agent providers configured: {defaults}. "
                    "Exactly one provider must have default=true."
                ),
                field="agent_providers",
            )
        if len(defaults) == 0 and providers:
            raise ConfigError(
                message=(
                    f"No default agent provider configured among: "
                    f"{list(providers.keys())}. "
                    "Exactly one provider must have default=true."
                ),
                field="agent_providers",
            )
        self._providers = dict(providers)
        self._default_name: str = defaults[0] if defaults else _DEFAULT_PROVIDER_NAME

    @classmethod
    def from_config(
        cls, providers: dict[str, AgentProviderConfig]
    ) -> AgentProviderRegistry:
        """Create registry, synthesizing default Claude Code provider when empty.

        Args:
            providers: Named provider configurations from maverick.yaml.

        Returns:
            Validated AgentProviderRegistry.

        Raises:
            ConfigError: If multiple providers have default=True.
        """
        if not providers:
            # Zero-config: synthesize default Claude Code provider
            default_provider = AgentProviderConfig(
                command=_DEFAULT_CLAUDE_COMMAND,
                permission_mode=PermissionMode.AUTO_APPROVE,
                default=True,
            )
            logger.debug(
                "agent_provider_registry.synthesized_default",
                provider=_DEFAULT_PROVIDER_NAME,
                command=_DEFAULT_CLAUDE_COMMAND,
            )
            return cls({_DEFAULT_PROVIDER_NAME: default_provider})

        return cls(providers)

    def get(self, name: str) -> AgentProviderConfig:
        """Look up a provider by name.

        Args:
            name: Provider name to look up.

        Returns:
            AgentProviderConfig for the named provider.

        Raises:
            ConfigError: If provider name not found.
        """
        if name not in self._providers:
            raise ConfigError(
                message=(
                    f"Unknown agent provider '{name}'. "
                    f"Available providers: {list(self._providers.keys())}"
                ),
                field="agent_providers",
                value=name,
            )
        return self._providers[name]

    def default(self) -> tuple[str, AgentProviderConfig]:
        """Return (name, config) of the default provider.

        Returns:
            Tuple of (provider_name, AgentProviderConfig).
        """
        return self._default_name, self._providers[self._default_name]

    def names(self) -> list[str]:
        """All registered provider names.

        Returns:
            Sorted list of registered provider names.
        """
        return sorted(self._providers.keys())
