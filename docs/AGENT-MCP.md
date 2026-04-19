# Agent-MCP Architecture: Unified Actor Communication via MCP Tool Calls

## Overview

This document captures the architectural direction for Maverick's agent communication layer. The core insight: **MCP tool calls are the outbound mailbox for agent actors.** Agents communicate results to the supervisor by calling schema-enforced MCP tools, not by producing structured JSON in their text responses.

This replaces the fragile pattern of prompt-based schema enforcement ("please output JSON matching this schema...") with protocol-level enforcement where the tool call fails if the schema doesn't match, and the agent self-corrects.

## The Problem

Maverick agents currently communicate structured results in two ways, both fragile:

1. **Inline JSON in text responses** — The agent is asked to produce a JSON block in its conversational output. The executor tries to extract it. Fails across models (Gemini, Codex, even Claude sometimes) because agents naturally produce conversational text, not structured data.

2. **File-based JSON output** — The agent writes JSON to a file via the Write tool. Better than inline, but the file content isn't schema-validated at write time. The coercion layer must handle format mismatches (strings where objects are expected, missing fields, etc.).

Both approaches fight the agent's natural behavior. Agents are good at using tools with defined interfaces. They're unreliable at producing exact JSON schemas in free text.

## The Solution: MCP Tools as Outbound Mailbox

In the actor-mailbox architecture, every agent interaction follows this pattern:

- **Inbound to agent**: The supervisor puts a message in the actor's inbox, delivered as a natural-language prompt on the agent's persistent ACP session.
- **Outbound from agent**: The agent calls an MCP tool to deliver a structured message to the supervisor's inbox. The MCP protocol enforces the tool's parameter schema.
- **Deterministic actors**: The supervisor calls a Python function (inbox). The function returns a value (delivered to the supervisor's inbox). No MCP needed.

The MCP server runs in (or alongside) the Maverick orchestrator process. It serves tool definitions that correspond to the messages the supervisor expects. The agent sees these as available tools, calls them naturally, and the protocol guarantees the parameters match the schema.

**Built-in tools** (Read, Write, Edit, Bash, Glob, Grep) are for doing work — interacting with the workspace.
**MCP tools** are for communicating results — sending structured messages to the supervisor.

## Actor Communication Model

### No Outboxes

Classic actor model: actors send messages directly to other actors' inboxes. There is no outbox.

- **Every actor has an inbox** — For agent actors, a prompt on their ACP session. For deterministic actors, a function call.
- **The supervisor has an inbox** — MCP tool calls from agent actors land here. Return values from deterministic actors land here.
- **Nobody has an outbox** — The MCP tool call IS the delivery. The function return IS the delivery.

The supervisor is the only actor that sends to other actors' inboxes. Agents never message each other directly — they always go through the supervisor, which enforces the routing policy. Star topology, not mesh.

### Message Flow Pattern

```
Supervisor reads from its inbox
Supervisor runs routing policy (match on message type)
Supervisor puts message in next actor's inbox
  → Agent actor: prompt on ACP session
  → Deterministic actor: Python function call
Actor processes
Actor delivers result to supervisor's inbox
  → Agent actor: MCP tool call (schema-enforced)
  → Deterministic actor: function return value
Repeat until done.
```

## MCP Server Design

The orchestrator operates a single MCP server process that serves tool definitions to agent sessions. The tools change based on which actor is active and what message the supervisor expects back.

### Tool Registration Per Turn

When the supervisor sends a message to an agent actor's inbox, it also updates the MCP server's available tools to match the expected response:

- After sending IMPLEMENT_REQUEST → MCP serves `submit_implementation(summary, files_changed)`
- After sending REVIEW_REQUEST → MCP serves `submit_review(approved, findings)`
- After sending OUTLINE_REQUEST → MCP serves `submit_outline(work_units)`
- After sending FIX_REQUEST → MCP serves `submit_fix(addressed, contested)`

The agent only sees the tools relevant to its current task. This constrains the response space and makes the agent's job clear: do the work, then call the tool to report.

### Integration with ACP Sessions

ACP sessions accept MCP servers via the `mcp_servers` parameter on `new_session()`:

```python
from acp.schema import McpServerStdio

session = await conn.new_session(
    cwd=workspace_path,
    mcp_servers=[
        McpServerStdio(
            name="maverick-supervisor",
            command="python3",
            args=["-m", "maverick.tools.supervisor_mcp", "--port", port],
            env=[],
        )
    ],
)
```

The MCP server exposes tools via the standard MCP protocol. The agent subprocess discovers and calls them like any other MCP tool.

## Workflow Examples

### Plan (Fan-Out/Fan-In)

```
Supervisor inbox ← start plan (prd_content, plan_name)

# Briefing room — four agents in parallel, each with its own session
Supervisor routes → Scopist inbox: prompt("Analyze scope...")
Supervisor routes → CodebaseAnalyst inbox: prompt("Map modules...")
Supervisor routes → CriteriaWriter inbox: prompt("Draft criteria...")

# Agents work independently, call MCP tools when done
Scopist calls: submit_scope(in_scope=[...], out_scope=[...], boundaries=[...])
CodebaseAnalyst calls: submit_analysis(modules=[...], patterns=[...])
CriteriaWriter calls: submit_criteria(criteria=[...], test_scenarios=[...])

# Supervisor collects partial results, routes when all three arrive
Supervisor routes → Contrarian inbox: prompt("Challenge: {scope} {analysis} {criteria}")

Contrarian calls: submit_challenge(risks=[...], blind_spots=[...])

# Generator synthesizes
Supervisor routes → Generator inbox: prompt("Generate flight plan from briefing")

Generator calls: submit_flight_plan(success_criteria=[...], scope={...})

# Deterministic validation and write
Supervisor routes → PlanValidator inbox: validate(plan)
Supervisor inbox ← return: {passed: true}
Supervisor routes → PlanWriter inbox: write(plan, path)
Done.
```

The fan-out/fan-in pattern is expressed as routing policy:

```python
case MessageType.SUBMIT_SCOPE:
    self._briefing["scope"] = message.payload
    if self._briefing_complete():
        return → Contrarian inbox

case MessageType.SUBMIT_ANALYSIS:
    self._briefing["analysis"] = message.payload
    if self._briefing_complete():
        return → Contrarian inbox

case MessageType.SUBMIT_CRITERIA:
    self._briefing["criteria"] = message.payload
    if self._briefing_complete():
        return → Contrarian inbox
```

### Refuel (Linear with Fix Loops)

```
Supervisor routes → Decomposer inbox: prompt("Decompose this flight plan...")

Decomposer works (reads codebase via built-in tools)
Decomposer calls: submit_outline(work_units=[
    {id: "uid-sync", task: "Implement UID sync", depends_on: [], ...},
    {id: "compose-profiles", task: "Add profile forwarding", ...},
])
Supervisor inbox ← submit_outline(work_units=[...])

Supervisor routes → Decomposer inbox: prompt("Fill in details for all units")

Decomposer calls: submit_details(details=[
    {id: "uid-sync", instructions: "...", acceptance_criteria: [...], ...},
])
Supervisor inbox ← submit_details(details=[...])

Supervisor routes → Validator inbox: validate(specs)
Supervisor inbox ← return: {passed: false, gaps: ["SC-015"]}

Supervisor routes → Decomposer inbox: prompt("Fix: SC-015 not covered")
  ↑ same session — decomposer remembers everything

Decomposer calls: submit_fix(patched_units=[...])
Supervisor inbox ← submit_fix(...)

Supervisor routes → Validator inbox: validate(specs)
Supervisor inbox ← return: {passed: true}

Supervisor routes → BeadCreator inbox: create(specs)
Supervisor inbox ← return: {epic_id: "deacon-xyz", beads: 8}
Done.
```

### Fly (Linear with Fix Loops + Review Negotiation)

```
Supervisor routes → Implementer inbox: prompt("Implement compose profiles...")

Implementer works (writes code via built-in Write/Edit tools)
Implementer calls: submit_implementation(summary="Added profiles field...")
Supervisor inbox ← submit_implementation(...)

Supervisor routes → Gate inbox: validate(cwd)
Supervisor inbox ← return: {passed: true}

Supervisor routes → AC inbox: check(cwd, verification_commands)
Supervisor inbox ← return: {passed: true}

Supervisor routes → Reviewer inbox: prompt("Review the diff...")

Reviewer reads code (via built-in Read/Grep tools)
Reviewer calls: submit_review(approved=false, findings=[
    {severity: "major", file: "compose.rs", line: 120, issue: "Missing error handling"}
])
Supervisor inbox ← submit_review(approved=false, findings=[...])

Supervisor routes → Implementer inbox: prompt("Fix: Missing error handling on compose.rs:120")
  ↑ same session — implementer remembers everything

Implementer fixes the issue (via built-in Edit tool)
Implementer calls: submit_fix(addressed=["F001"], notes="Added anyhow context")
Supervisor inbox ← submit_fix(...)

Supervisor routes → Gate inbox: validate(cwd)
Supervisor inbox ← return: {passed: true}

Supervisor routes → Reviewer inbox: prompt("Check if F001 was addressed")
  ↑ same session — reviewer remembers what it said

Reviewer calls: submit_review(approved=true)
Supervisor inbox ← submit_review(approved=true)

Supervisor routes → Committer inbox: commit(bead_id, title)
Supervisor inbox ← return: {commit_sha: "abc123"}
Done.
```

## Consistent Pattern Across Workflows

| | Plan | Refuel | Fly |
|---|---|---|---|
| **Agent → Supervisor** | MCP tool call | MCP tool call | MCP tool call |
| **Supervisor → Agent** | Prompt on session | Prompt on session | Prompt on session |
| **Supervisor → Deterministic** | Function call | Function call | Function call |
| **Deterministic → Supervisor** | Return value | Return value | Return value |
| **Routing policy** | Fan-out/fan-in + sequential | Linear with fix loops | Linear with fix loops |
| **Session lifetime** | Per agent per plan | Per decomposer per refuel | Per actor per bead |

One communication protocol, three routing policies. The MCP server is the same infrastructure for all of them — it serves different tool definitions depending on which actor is active and what response is expected.

## Three Information Types (Unchanged)

The MCP tool approach reinforces the three information types:

| Type | What | How It Moves |
|------|------|-------------|
| **Beads** | Domain work units | Created by BeadCreator actor, persisted in bd database |
| **Files** | Durable context | Written by agents (built-in Write tool) or supervisor, survives restarts |
| **Messages** | Ephemeral process coordination | Delivered via MCP tool calls (agent→supervisor) or prompts (supervisor→agent), captured in fly report |

MCP tool calls are messages. They're ephemeral — the supervisor processes them and routes the next message. The fly report captures the complete exchange at bead completion for runway learning.

## Implementation Considerations

### MCP Server Lifecycle

- One MCP server instance per supervisor (per bead in fly, per refuel, per plan)
- Passed to `new_session()` via `McpServerStdio` — ACP manages the subprocess
- Server serves tools dynamically based on current turn
- Server writes collected data to a known path for the supervisor to read, OR communicates via stdout/stdin with the orchestrator

### Tool Schema Examples

```json
{
  "name": "submit_review",
  "description": "Submit your code review findings to the supervisor",
  "parameters": {
    "type": "object",
    "properties": {
      "approved": {"type": "boolean", "description": "Whether the code passes review"},
      "findings": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "severity": {"enum": ["critical", "major", "minor"]},
            "file": {"type": "string"},
            "line": {"type": "integer"},
            "issue": {"type": "string"}
          },
          "required": ["severity", "issue"]
        }
      }
    },
    "required": ["approved"]
  }
}
```

### Coexistence with Built-In Tools

Agents use two categories of tools simultaneously:

- **Built-in tools** (Read, Write, Edit, Bash, Glob, Grep) — for doing work in the workspace
- **MCP tools** (submit_implementation, submit_review, etc.) — for sending structured results to the supervisor

These coexist naturally. The agent reads files, writes code, runs tests using built-in tools. When it's done, it calls the MCP tool to report. The built-in tools are workspace interactions; the MCP tools are supervisor interactions.

### Dependency

Requires the `mcp` Python SDK (v1.27.0+) for the server side. The ACP SDK already supports `McpServerStdio` on the client side.

## Relationship to Existing Architecture

This design evolves the actor-mailbox architecture already implemented in fly and refuel:

- **What stays**: Actor protocol, Message/MessageType, supervisor routing policy, persistent ACP sessions, fly reports, deterministic actors
- **What changes**: Agent actors stop producing JSON in text/files and instead call MCP tools. The supervisor's inbox becomes the MCP server. The coercion layer in the refuel supervisor becomes unnecessary.
- **What's eliminated**: `output_schema` on prompts, `output_file_path` pattern, text JSON extraction, schema coercion layer, all the `MalformedResponseError` retry machinery for structured output

## Open Questions

1. **MCP server process model** — One server per supervisor, or one shared server with session routing? Per-supervisor is simpler; shared reduces process count.

2. **Dynamic tool registration** — Can MCP tools be added/removed mid-session, or must they be defined at session creation? If session creation only, each turn may need a new session (losing the persistent-session benefit).

3. **Parallel agent fan-out** — In plan's briefing room, three agents run in parallel, each with their own session. Do they share one MCP server or each get their own? Shared is simpler but needs session-id routing.

4. **Error handling** — When an MCP tool call fails validation, the agent sees the error and retries. But what if the agent can't produce valid parameters after N attempts? Need a circuit breaker at the MCP level.

5. **Testing** — Mock MCP server for unit tests, or test against real MCP with schema validation?
