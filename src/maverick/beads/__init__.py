"""Bead generation and management for Maverick.

Public API for creating beads from various sources (SpecKit, etc.)
using the ``bd`` CLI tool.
"""

from __future__ import annotations

from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDefinition, BeadGenerationResult
from maverick.beads.speckit import generate_beads_from_speckit

__all__ = [
    "BeadClient",
    "BeadDefinition",
    "BeadGenerationResult",
    "generate_beads_from_speckit",
]
