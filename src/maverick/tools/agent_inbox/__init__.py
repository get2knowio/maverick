"""Typed Pydantic payloads carried by every mailbox actor's structured output.

Originally the agent_inbox package hosted both these payload models and
an MCP gateway / schema-emitter that exposed them as tools. The
gateway, schemas, and subprocess quota are gone (Phase 4 of the
OpenCode migration); the Pydantic models live on as the canonical
typed-response shapes the actors return via OpenCode's
``StructuredOutput`` tool.

Phase 6 will move ``models.py`` to a top-level ``maverick.payloads``
module and delete this package directory entirely.
"""
