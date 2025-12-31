"""Maverick constants including Claude model identifiers.

This module provides a single source of truth for Claude model identifiers
and other constants used throughout Maverick. Update these constants when
new model versions are released to automatically propagate changes across
the codebase.
"""

from __future__ import annotations

from typing import Literal

# =============================================================================
# Latest Model Versions
# =============================================================================

#: Latest Claude Haiku 4.5 model (fastest, most cost-effective)
CLAUDE_HAIKU_LATEST: str = "claude-haiku-4-5-20251001"

#: Latest Claude Sonnet 4.5 model (balanced performance and cost)
CLAUDE_SONNET_LATEST: str = "claude-sonnet-4-5-20250929"

#: Latest Claude Opus 4.5 model (most capable, highest cost)
CLAUDE_OPUS_LATEST: str = "claude-opus-4-5-20251101"

#: Default model for Maverick agents and workflows
DEFAULT_MODEL: str = CLAUDE_SONNET_LATEST

# =============================================================================
# Model Type Mapping
# =============================================================================

ModelType = Literal["haiku", "sonnet", "opus"]

#: Map model type names to their latest versions
LATEST_MODELS: dict[ModelType, str] = {
    "haiku": CLAUDE_HAIKU_LATEST,
    "sonnet": CLAUDE_SONNET_LATEST,
    "opus": CLAUDE_OPUS_LATEST,
}

# =============================================================================
# Model Capabilities
# =============================================================================

#: Maximum output tokens for all Claude 4.5 variants
MAX_OUTPUT_TOKENS: int = 64000

#: Context window size for all Claude 4.5 variants
CONTEXT_WINDOW_TOKENS: int = 200000


# =============================================================================
# Helper Functions
# =============================================================================


def get_latest_model(model_type: ModelType) -> str:
    """Get the latest model ID for a given model type.

    Args:
        model_type: Type of model ("haiku", "sonnet", or "opus").

    Returns:
        Latest model ID for the specified type.

    Example:
        >>> get_latest_model("haiku")
        'claude-haiku-4-5-20251001'
    """
    return LATEST_MODELS[model_type]


def is_latest_model(model_id: str) -> bool:
    """Check if a model ID is one of the latest versions.

    Args:
        model_id: Claude model identifier to check.

    Returns:
        True if the model ID is a latest version.

    Example:
        >>> is_latest_model("claude-sonnet-4-5-20250929")
        True
        >>> is_latest_model("claude-sonnet-3-5-20240620")
        False
    """
    return model_id in LATEST_MODELS.values()


def get_model_type(model_id: str) -> ModelType | None:
    """Determine the model type from a model ID.

    Args:
        model_id: Claude model identifier.

    Returns:
        Model type ("haiku", "sonnet", or "opus") if recognized, None otherwise.

    Example:
        >>> get_model_type("claude-haiku-4-5-20251001")
        'haiku'
        >>> get_model_type("unknown-model")
        None
    """
    model_lower = model_id.lower()
    if "haiku" in model_lower:
        return "haiku"
    elif "sonnet" in model_lower:
        return "sonnet"
    elif "opus" in model_lower:
        return "opus"
    return None
