"""AgentProviderRegistry — resolves ACP agent provider names to configurations."""

from __future__ import annotations

from maverick.config import AgentProviderConfig, PermissionMode
from maverick.exceptions import ConfigError
from maverick.logging import get_logger

__all__ = ["AgentProviderRegistry"]

logger = get_logger(__name__)

#: Default Claude provider command (zero-config fallback).
#: Uses the ACP bridge (@agentclientprotocol/claude-agent-acp) which wraps
#: Claude Code's Agent SDK and exposes it as an ACP agent over stdio.
_DEFAULT_CLAUDE_COMMAND: list[str] = [
    "claude-agent-acp",
]

#: Default GitHub Copilot provider command.
#: Uses the Copilot CLI's built-in ACP server mode (stdio transport).
#: See https://docs.github.com/en/copilot/reference/acp-server
_DEFAULT_COPILOT_COMMAND: list[str] = [
    "copilot",
    "--acp",
    "--stdio",
]

#: Default Gemini CLI provider command.
#: Uses the experimental ACP mode in the Gemini CLI.
_DEFAULT_GEMINI_COMMAND: list[str] = [
    "gemini",
    "--experimental-acp",
]

#: Default OpenCode provider command.
#: Uses the OpenCode CLI's ACP subcommand (stdio JSON-RPC). Per the
#: OpenCode docs, ``opencode acp`` exposes built-in tools, MCP servers,
#: AGENTS.md project rules, and the OpenCode permissions/agent system.
#:
#: Model selection works the same way it does for Claude: maverick
#: calls the standard ACP ``session/set_model`` RPC after each
#: ``session/new``, and OpenCode honours it. There is no ``--model``
#: launch flag for ``opencode acp`` (the opencode acp subcommand only
#: accepts ``--cwd``, ``--port``, ``--hostname``) and no ``/model``
#: slash command, so per-session switching goes through the standard
#: ACP path. Use opencode's provider/model identifier format in
#: ``default_model`` (e.g. ``anthropic/claude-sonnet-4``,
#: ``openrouter/qwen/qwen-3-coder``).
#:
#: See https://opencode.ai/docs/acp/
_DEFAULT_OPENCODE_COMMAND: list[str] = [
    "opencode",
    "acp",
]

#: Name used for the synthesized default provider
_DEFAULT_PROVIDER_NAME: str = "claude"

#: Known built-in providers with their default commands.
_BUILTIN_PROVIDERS: dict[str, list[str]] = {
    "claude": _DEFAULT_CLAUDE_COMMAND,
    "copilot": _DEFAULT_COPILOT_COMMAND,
    "gemini": _DEFAULT_GEMINI_COMMAND,
    "opencode": _DEFAULT_OPENCODE_COMMAND,
}


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
    def from_config(cls, providers: dict[str, AgentProviderConfig]) -> AgentProviderRegistry:
        """Create registry with built-in provider resolution.

        When no providers are configured, synthesizes a default Claude provider.
        When a provider name matches a built-in (``claude``, ``copilot``) and
        no ``command`` is specified, the built-in command is filled in
        automatically.

        Args:
            providers: Named provider configurations from maverick.yaml.

        Returns:
            Validated AgentProviderRegistry.

        Raises:
            ConfigError: If multiple providers have default=True, or if a
                provider has no command and is not a known built-in.
        """
        if not providers:
            # Zero-config: synthesize default Claude provider
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

        # Resolve built-in commands for providers without explicit commands
        resolved: dict[str, AgentProviderConfig] = {}
        for name, cfg in providers.items():
            if cfg.command is None:
                builtin_cmd = _BUILTIN_PROVIDERS.get(name)
                if builtin_cmd is None:
                    raise ConfigError(
                        message=(
                            f"Agent provider '{name}' has no command and is not "
                            f"a built-in provider. Built-in providers: "
                            f"{list(_BUILTIN_PROVIDERS.keys())}. "
                            f"Provide an explicit 'command' list."
                        ),
                        field="agent_providers",
                        value=name,
                    )
                # Gemini CLI accepts --model at launch; its experimental ACP
                # server does not support session/set_model, so the model must
                # be baked into the spawn command.
                if name == "gemini" and cfg.default_model:
                    builtin_cmd = [*builtin_cmd, "--model", cfg.default_model]
                logger.debug(
                    "agent_provider_registry.resolved_builtin",
                    provider=name,
                    command=builtin_cmd,
                )
                resolved[name] = cfg.model_copy(update={"command": builtin_cmd})
            else:
                resolved[name] = cfg

        return cls(resolved)

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

    def items(self) -> list[tuple[str, AgentProviderConfig]]:
        """All registered providers as (name, config) pairs.

        Returns:
            List of (provider_name, AgentProviderConfig) tuples sorted by name.
        """
        return sorted(self._providers.items(), key=lambda item: item[0])

    def names(self) -> list[str]:
        """All registered provider names.

        Returns:
            Sorted list of registered provider names.
        """
        return sorted(self._providers.keys())
