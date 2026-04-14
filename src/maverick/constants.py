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

#: Latest Claude Sonnet 4.6 model (balanced performance and cost)
CLAUDE_SONNET_LATEST: str = "claude-sonnet-4-6-20250514"

#: Latest Claude Opus 4.6 model (most capable, highest cost)
CLAUDE_OPUS_LATEST: str = "claude-opus-4-6-20250514"

#: Default model for Maverick agents and workflows.
#: Uses the semantic alias "sonnet" so the ACP provider resolves to
#: whatever its latest Sonnet version is at runtime.
DEFAULT_MODEL: str = "sonnet"

# =============================================================================
# Model Type Mapping
# =============================================================================

ModelType = Literal["haiku", "sonnet", "opus"]

# =============================================================================
# Model Capabilities
# =============================================================================

#: Maximum output tokens for Claude models
MAX_OUTPUT_TOKENS: int = 64000


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
        >>> get_latest_model("sonnet")
        'claude-sonnet-4-6-20250514'
    """
    _latest: dict[ModelType, str] = {
        "haiku": CLAUDE_HAIKU_LATEST,
        "sonnet": CLAUDE_SONNET_LATEST,
        "opus": CLAUDE_OPUS_LATEST,
    }
    return _latest[model_type]


def get_model_type(model_id: str) -> ModelType | None:
    """Determine the model type from a model ID.

    Args:
        model_id: Claude model identifier.

    Returns:
        Model type ("haiku", "sonnet", or "opus") if recognized, None otherwise.

    Example:
        >>> get_model_type("claude-sonnet-4-6-20250514")
        'sonnet'
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


#: Default directory for checkpoint persistence
CHECKPOINT_DIR: str = ".maverick/checkpoints"
