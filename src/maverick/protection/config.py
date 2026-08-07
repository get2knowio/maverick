"""``lookup_protection_config`` — lenient loader for the ``protection:`` block.

Follows the ``lookup_tiers_config`` idiom (``maverick.config``): malformed
input degrades to defaults with a warning, never a startup failure. See
``specs/056-context-file-protection/contracts/protection-config.md``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from maverick.config import MaverickConfig
from maverick.logging import get_logger

__all__ = ["ProtectionConfig", "lookup_protection_config"]

logger = get_logger(__name__)


class ProtectionConfig(BaseModel):
    """The validated form of the ``protection:`` block.

    Produced only by :func:`lookup_protection_config` — never constructed
    from raw YAML elsewhere. Pattern-compilation validity (whether an
    entry is a valid ``pathspec`` gitwildmatch pattern) is a
    ``ProtectionPolicy``-construction-time concern, not validated here —
    this model only validates shape (a list of strings).

    Attributes:
        additional_globs: Gitignore-style patterns, repo-relative, that
            extend the default protected set.
        allowlist: Gitignore-style patterns that exempt matching paths
            from the entire protected set (defaults + additional).
    """

    additional_globs: list[str] = Field(default_factory=list)
    allowlist: list[str] = Field(default_factory=list)


def lookup_protection_config(config: MaverickConfig) -> ProtectionConfig:
    """Parse ``config.protection`` into its typed :class:`ProtectionConfig`.

    Follows the ``lookup_tiers_config`` idiom (``maverick.config``):
    malformed input degrades to defaults with a ``logger.warning`` rather
    than raising — a typo in the ``protection:`` block must not take down
    workflow startup (FR-012).

    Args:
        config: Loaded :class:`~maverick.config.MaverickConfig`.

    Returns:
        The parsed :class:`ProtectionConfig` when ``config.protection`` is
        present and valid; ``ProtectionConfig()`` (defaults) otherwise.
    """
    raw = config.protection
    if raw is None:
        return ProtectionConfig()
    if not isinstance(raw, dict):
        logger.warning("protection_config_invalid_shape", got=type(raw).__name__)
        return ProtectionConfig()
    try:
        return ProtectionConfig.model_validate(raw)
    except ValidationError as exc:
        logger.warning("protection_config_parse_failed", error=str(exc))
        return ProtectionConfig()
