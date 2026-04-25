"""ACP session model resolution helpers.

Maps semantic model names from ``maverick.yaml`` (e.g. ``"sonnet"``,
``"opus"``) to the provider's actual model IDs as advertised on the
ACP session — which differ across providers and versions.
"""

from __future__ import annotations

from typing import Any

from maverick.constants import get_model_type


def resolve_model_for_provider(
    requested_model: str,
    session: Any,
) -> str:
    """Map a semantic model name to the ACP provider's actual model ID.

    ACP providers (notably Claude Code) advertise models with short IDs like
    ``"default"`` and ``"opus"`` (or ``"default"`` and ``"sonnet"``).  The
    identity behind ``"default"`` changes between sessions.  This function
    lets ``maverick.yaml`` use stable semantic names (``"sonnet"``,
    ``"opus"``, or full model IDs like ``"claude-sonnet-4-5-20250929"``) and
    resolves them to whatever ID the provider currently exposes.

    Resolution steps:
    1. If ``requested_model`` is already in the available IDs → return as-is.
    2. Determine the *model type* (haiku / sonnet / opus) from the request.
    3. Scan each available model's ``name`` and ``description`` fields for a
       case-insensitive match on the type. Real Claude Code sessions advertise
       e.g. ``name="Default (recommended)"``,
       ``description="Opus 4.7 with 1M context …"`` — the floating "default"
       slot is identified only by description.
    4. If no match is found, return the original ``requested_model`` unchanged
       (the caller's existing validation will raise if it's truly invalid).

    Args:
        requested_model: Model identifier from maverick.yaml / StepConfig.
        session: ACP NewSessionResponse with ``models`` attribute.

    Returns:
        The provider model ID to pass to ``set_session_model``.
    """
    available_ids = get_available_model_ids(session)
    if not available_ids or requested_model in available_ids:
        return requested_model

    # Determine what model *type* the user is asking for.
    model_type = get_model_type(requested_model)
    if model_type is None:
        return requested_model

    # Match by human-readable name or description. Both are scanned because
    # providers vary: some put the model family in `name` (e.g.
    # "Claude Opus 4.6"), others put it only in `description` (Claude Code's
    # "Default (recommended)" / "Opus 4.7 with 1M context …").
    models_state = getattr(session, "models", None)
    if models_state:
        for m in getattr(models_state, "available_models", []):
            mid = getattr(m, "model_id", None)
            if not mid:
                continue
            haystack = " ".join(
                str(getattr(m, attr, None) or "") for attr in ("name", "description")
            ).lower()
            if model_type in haystack:
                return str(mid)

    return requested_model


def resolve_model_label(
    session: Any,
    resolved_model: str | None,
) -> str | None:
    """Build a human-readable model label from the ACP session.

    Prefers the ``name`` field from ``ModelInfo`` (e.g. "Claude Opus 4.6")
    over the bare ``model_id`` (e.g. "opus"). Falls back to
    ``current_model_id`` when no explicit model was requested.

    Args:
        session: ACP NewSessionResponse.
        resolved_model: Model ID explicitly set on the session, or None.

    Returns:
        Display label like "Claude Opus 4.6", or None if unavailable.
    """
    models_state = getattr(session, "models", None)
    if not models_state:
        return resolved_model or None

    model_id = resolved_model or getattr(
        models_state,
        "current_model_id",
        None,
    )
    if not model_id:
        return None

    for m in getattr(models_state, "available_models", []):
        if getattr(m, "model_id", None) == model_id:
            name = getattr(m, "name", None)
            if name:
                return str(name)
            break

    return model_id


def get_available_model_ids(session: Any) -> set[str]:
    """Extract available model IDs from a NewSessionResponse.

    Checks both ``session.models.available_models`` and
    ``session.config_options`` (config_id="model") since providers
    may advertise models in either or both locations.

    Args:
        session: ACP NewSessionResponse.

    Returns:
        Set of model ID strings, or empty set if unavailable.
    """
    ids: set[str] = set()
    # Source 1: models.available_models (unstable but common)
    models = getattr(session, "models", None)
    if models:
        for m in getattr(models, "available_models", []):
            model_id = getattr(m, "model_id", None)
            if model_id:
                ids.add(model_id)
    # Source 2: config_options with id="model"
    config_options = getattr(session, "config_options", None)
    if config_options:
        for opt in config_options:
            root = getattr(opt, "root", opt)
            if getattr(root, "id", None) == "model":
                for o in getattr(root, "options", []):
                    val = getattr(o, "value", None)
                    if val:
                        ids.add(val)
    return ids
