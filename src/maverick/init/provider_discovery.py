"""ACP provider discovery for maverick init.

Probes for installed ACP providers by checking if their binaries are on PATH.
Results are used to populate the ``agent_providers`` section of the generated
``maverick.yaml``.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from typing import Any

from maverick.executor.provider_registry import _BUILTIN_PROVIDERS
from maverick.logging import get_logger

__all__ = [
    "PROVIDER_PREFERENCE_ORDER",
    "ProviderDiscoveryResult",
    "ProviderProbeResult",
    "discover_providers",
]

logger = get_logger(__name__)

#: Preference order for auto-selecting the default provider.
PROVIDER_PREFERENCE_ORDER: tuple[str, ...] = ("claude", "copilot", "gemini")

#: Human-readable display names for built-in providers.
_DISPLAY_NAMES: dict[str, str] = {
    "claude": "Claude",
    "copilot": "GitHub Copilot",
    "gemini": "Gemini",
}


@dataclass(frozen=True, slots=True)
class ProviderProbeResult:
    """Result of probing a single ACP provider.

    Attributes:
        name: Provider identifier (e.g. ``"claude"``).
        display_name: Human-readable name (e.g. ``"Claude"``).
        binary: Binary name checked on PATH (e.g. ``"claude-agent-acp"``).
        found: Whether the binary was found on PATH.
        error: Error message if the probe failed unexpectedly.
    """

    name: str
    display_name: str
    binary: str
    found: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {
            "name": self.name,
            "display_name": self.display_name,
            "binary": self.binary,
            "found": self.found,
        }
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass(frozen=True, slots=True)
class ProviderDiscoveryResult:
    """Aggregate result of ACP provider discovery.

    Attributes:
        providers: Probe results for all checked providers.
        default_provider: Name of the auto-selected default provider,
            or ``None`` if no providers were found.
        duration_ms: Total discovery time in milliseconds.
    """

    providers: tuple[ProviderProbeResult, ...]
    default_provider: str | None
    duration_ms: int = 0

    @property
    def found_providers(self) -> tuple[ProviderProbeResult, ...]:
        """Return only the providers that were found on PATH."""
        return tuple(p for p in self.providers if p.found)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "providers": [p.to_dict() for p in self.providers],
            "default_provider": self.default_provider,
            "duration_ms": self.duration_ms,
        }


async def discover_providers() -> ProviderDiscoveryResult:
    """Probe for installed ACP providers via ``shutil.which()``.

    Checks each built-in provider binary in :data:`PROVIDER_PREFERENCE_ORDER`.
    The first found provider becomes the default.

    Returns:
        Discovery result with probe outcomes and auto-selected default.
    """
    start = time.monotonic()
    probes: list[ProviderProbeResult] = []
    default_provider: str | None = None

    for name in PROVIDER_PREFERENCE_ORDER:
        command = _BUILTIN_PROVIDERS.get(name)
        if command is None:
            continue

        binary = command[0]
        display_name = _DISPLAY_NAMES.get(name, name)

        try:
            found = shutil.which(binary) is not None
        except Exception as exc:
            logger.debug("provider_probe_error", provider=name, error=str(exc))
            probes.append(
                ProviderProbeResult(
                    name=name,
                    display_name=display_name,
                    binary=binary,
                    found=False,
                    error=str(exc),
                )
            )
            continue

        if found and default_provider is None:
            default_provider = name

        probes.append(
            ProviderProbeResult(
                name=name,
                display_name=display_name,
                binary=binary,
                found=found,
            )
        )
        logger.debug(
            "provider_probed",
            provider=name,
            binary=binary,
            found=found,
        )

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return ProviderDiscoveryResult(
        providers=tuple(probes),
        default_provider=default_provider,
        duration_ms=elapsed_ms,
    )
