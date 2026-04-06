"""InboxActor — Thespian actor that receives messages from MCP servers.

The supervisor creates this actor with globalName='supervisor-inbox'.
MCP server subprocesses discover it by name and send tool call data
as Thespian messages. The supervisor reads from it via ask().

This actor runs in its own OS process (multiprocTCPBase) and
accumulates messages until the supervisor polls for them.
"""

from thespian.actors import Actor


class InboxActor(Actor):
    """Accumulates messages from MCP server subprocesses.

    Message protocol:
    - dict with "tool" key: queued for supervisor to retrieve
    - "get_latest" string: returns and removes the oldest pending message
    - "get_all" string: returns and removes all pending messages
    - "shutdown" string: prepares for clean shutdown
    """

    def __init__(self) -> None:
        super().__init__()
        self._pending: list[dict] = []

    def receiveMessage(self, message: object, sender: object) -> None:
        if message == "get_latest":
            if self._pending:
                self.send(sender, self._pending.pop(0))
            else:
                self.send(sender, None)

        elif message == "get_all":
            msgs = list(self._pending)
            self._pending.clear()
            self.send(sender, msgs)

        elif message == "pending_count":
            self.send(sender, len(self._pending))

        elif message == "shutdown":
            self._pending.clear()
            self.send(sender, {"status": "shutdown"})

        elif isinstance(message, dict) and "tool" in message:
            self._pending.append(message)
            self.send(sender, {"status": "received", "pending": len(self._pending)})

        else:
            # Unknown message — ignore
            pass
