# Data Model: Context File Protection

**Feature**: 056-context-file-protection

All types live in `src/maverick/protection/` unless noted. Everything is
frozen dataclasses or Pydantic models per Guardrail 3; zero `dict[str, Any]`
crossing public boundaries.

## ProtectionConfig (Pydantic, `protection/config.py`)

The validated form of the `protection:` block
([contracts/protection-config.md](contracts/protection-config.md)).

| Field | Type | Default | Validation |
| --- | --- | --- | --- |
| `additional_globs` | `list[str]` | `[]` | each entry must compile under `pathspec` gitwildmatch; invalid entries dropped with warning |
| `allowlist` | `list[str]` | `[]` | same |

Produced only by `lookup_protection_config(config: MaverickConfig) ->
ProtectionConfig` — never constructed from raw YAML elsewhere. Malformed input
degrades to `ProtectionConfig()` (defaults) with a warning.

## ProtectionPolicy (frozen, `protection/policy.py`)

The effective rule set for one run. Constructed once per squadron open:
`ProtectionPolicy.build(root: Path, config: ProtectionConfig)`.

| Field | Type | Notes |
| --- | --- | --- |
| `root` | `Path` | policy root — the agent's cwd (checkout or spec-chain workspace), resolved |
| `default_rules` | internal constants | basename `agents.md`/`claude.md` case-insensitive; prefix `.specify/memory/` — hardcoded, no user input |
| `extra_spec` | compiled `pathspec.PathSpec` | from `additional_globs` |
| `allow_spec` | compiled `pathspec.PathSpec` | from `allowlist` |

**Decision algorithm** — `decide(path, operation, destination=None) ->
PolicyDecision`:

1. Normalize: literal relpath (posix, from `root`) and resolved relpath
   (`Path.resolve()`, follows symlinks). Outside-root resolution → not
   protected.
2. For each candidate (literal, resolved) of each side (path, destination for
   renames): if `allow_spec` matches → exempt that candidate; else if a
   default rule or `extra_spec` matches → protected.
3. Any side protected → `PolicyDecision(blocked=True, rule=..., reason=...)`.
4. Internal error during evaluation → fail closed for the protected set: a
   best-effort literal-string match against default names decides; on match
   deny, else allow (backstop remains the guarantee) (FR-011).

`PolicyDecision` is a frozen dataclass: `blocked: bool`, `rule: str`
(human-readable matched-rule label), `reason: str`.

## PermissionGate (`protection/policy.py`)

The airframe `PermissionCallback` implementation (Layer 1).

- Knows the file-write tool names per provider family and how to extract
  target path(s) from `tool_args` (`file_path`, `path`, `old_path`/`new_path`,
  notebook variants). Unknown/Bash-like tools → `"allow"` (backstop covers).
- Protected match → `"deny"` with `PolicyDecision.reason`; also appends a
  `BlockRecord(layer="pre-write")` to the collector.
- Own exception → apply step 4 fail-closed rule above.

## SnapshotManifest (frozen, `protection/snapshot.py`)

Captured before each agent execution; held in memory only.

| Field | Type | Notes |
| --- | --- | --- |
| `root` | `Path` | matches policy root |
| `entries` | `Mapping[str, SnapshotEntry]` | key: resolved relpath |

`SnapshotEntry`: `sha256: str`, `content: bytes`, `is_symlink: bool`.
Enumeration: pruned `os.walk` (skips `.git`, `.jj`, `.venv`, `node_modules`,
`.maverick`, symlinked dirs), collecting paths where
`policy.decide(p, "edit")` blocks. Sizes are small (protected sets are a
handful of files); IO via `asyncio.to_thread`.

**Reconcile pass** — `restore_and_report(manifest, policy) ->
list[BlockRecord]`:

| Post-step observation | Action | Recorded operation |
| --- | --- | --- |
| manifest entry missing on disk | rewrite bytes (atomic) | `restore` (detail: inferred `delete`/`rename`) |
| manifest entry hash differs | rewrite bytes (atomic) | `restore` (detail: inferred `edit`) |
| protected-matching path not in manifest | delete file/symlink | `restore` (detail: inferred `create`/`rename`) |
| restore itself fails | error log + error-level event; run continues | `restore` with `detail` noting failure |
| per-step snapshot capture fails | agent step still runs; post-step compare falls back to the baseline manifest captured once at squadron open (research R6) — protected paths are never left unguarded (FR-011) | any restores recorded as usual |

## BlockRecord (frozen, `protection/records.py`)

One prevented/undone write. `to_dict()` is the single projection shared by the
`ContextFileWriteBlocked` event payload and `protection-blocks.json`
([contracts/block-event.md](contracts/block-event.md)) — they cannot drift.

Fields: `agent_role: str`, `workflow: str`, `operation:
Literal["create","edit","delete","rename","restore"]`, `path: str`,
`destination_path: str | None`, `layer: Literal["pre-write","backstop"]`,
`bead_id: str | None`, `detail: str | None`, `timestamp: float`.

## BlockCollector (`protection/records.py`)

Mutable per-squadron sink (the `cost_sink` DI shape): `append(record)`,
`drain() -> list[BlockRecord]`. Agents append; workflows drain at their
boundaries (fly: after each agent-calling action into the `protection_blocks`
state slot; spec-chain: per step into `ChainState.protection_blocks`; others:
at workflow end). Thread-safety is not required (single event loop), but
appends must be safe from within the permission callback mid-execution.

## State extensions (existing models)

| Home | Addition | Lifecycle |
| --- | --- | --- |
| fly Burr state (`burr_graph.py` seed) | `protection_blocks: list[dict]` (serialized `BlockRecord.to_dict()`) | seeded `[]`; extended after agent-calling actions; drained at loop exit into warning + artifact; separate from all fixer-feeding slots (Guardrail 10) |
| `ChainState` (`spec_chain/models.py`) | `protection_blocks: list[dict]` | checkpointed to `spec-chain.json` per transition; survives resume; rendered in `spec.py` summary |
| `maverick/events.py` | `ContextFileWriteBlocked` frozen dataclass | registered in `_EVENT_CLASSES`; see contract |
| `MaverickConfig` (`config.py`) | `protection` raw passthrough (`dict[str, Any]` or `None`, default `None`) | lazily validated via `lookup_protection_config` |

## Relationships

```
MaverickConfig.protection (raw) ──lookup_protection_config──> ProtectionConfig
ProtectionConfig + agent cwd ──ProtectionPolicy.build──> ProtectionPolicy (per run, per root)
Squadron ──injects──> Agent(policy, collector)
Agent execute path:
  Layer 1: session(on_permission=PermissionGate(policy, collector))   [capable providers]
  Layer 2: SnapshotManifest.capture → runtime call → restore_and_report → collector
Workflows: collector ──drain──> state slot / ChainState ──> warning + protection-blocks.json
```
