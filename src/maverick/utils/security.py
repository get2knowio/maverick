"""Security utilities for scrubbing secrets from text.

This module re-exports ``scrub_secrets`` and ``is_potentially_secret`` from the
canonical location at ``maverick.utils.secrets``.  All pattern definitions live
there; this shim exists only for backward-compatible imports.
"""

from __future__ import annotations

from maverick.utils.secrets import is_potentially_secret, scrub_secrets

__all__ = [
    "is_potentially_secret",
    "scrub_secrets",
]
