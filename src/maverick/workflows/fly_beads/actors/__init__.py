"""Actor-mailbox orchestration for fly bead processing.

This package implements the actor model for Maverick's fly phase.
Each bead is processed by a set of actors (implementer, reviewer,
gate, etc.) coordinated by a BeadSupervisor that routes messages
between them.

Key types:
- Actor: Protocol for all actors
- Message: Ephemeral process coordination between actors
- MessageType: Typed message categories
"""

from maverick.workflows.fly_beads.actors.protocol import (
    Actor,
    Message,
    MessageType,
)

__all__ = ["Actor", "Message", "MessageType"]
