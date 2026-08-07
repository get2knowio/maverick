# Contract: `protection:` config block (maverick.yaml)

## Shape

```yaml
protection:
  additional_globs:        # optional; gitignore-style patterns, repo-relative
    - "docs/agent-rules/**"
    - "GEMINI.md"
  allowlist:               # optional; exempts matches from protection
    - "AGENTS.md"          # e.g. this repo wants agents maintaining AGENTS.md
```

Both fields default to `[]`. The block itself is optional; **absent block ==
defaults in force**. `maverick init` does not write the block.

## Semantics

- **Default protected set** (always active, not config-expressible, cannot be
  removed except via `allowlist`): files whose basename is `AGENTS.md` or
  `CLAUDE.md` (case-insensitive) at any depth, plus everything under
  `.specify/memory/` at any depth.
- **`additional_globs`**: extends the protected set. Compiled with
  `pathspec` `gitwildmatch` (gitignore semantics: `**` crosses directories,
  `*` does not cross `/`). Matched against resolved repo-relative posix paths.
- **`allowlist`**: exempts matching paths from the *entire* protected set
  (defaults + additional). Evaluated first. Per-path, not a global switch —
  though `allowlist: ["**"]` is the explicit, auditable full opt-out.
- Matching also considers the literal (unresolved) path so a symlink planted
  at a protected location is caught; see `data-model.md` for the decision
  algorithm.

## Loading & degradation (FR-012)

- Stored on `MaverickConfig` as a raw passthrough (`protection: dict | None`,
  like `actors:`); validated lazily by
  `maverick.protection.config.lookup_protection_config(config)`.
- Malformed block shape (non-dict, wrong types) → **defaults + one
  `logger.warning`** (`protection_config_invalid_shape` /
  `protection_config_parse_failed`), never a startup failure — the
  `lookup_tiers_config` idiom.
- An individually invalid pattern inside an otherwise-valid list is dropped
  with a warning naming it; the rest of the block still applies. An invalid
  `allowlist` entry can never disable protection; an invalid
  `additional_globs` entry can never widen the allowlist. Misconfiguration
  narrows toward defaults, never away from them.
- Env override path exists for free via pydantic-settings
  (`MAVERICK_PROTECTION__...`), same as every block.

## Non-goals

No `enabled:` kill-switch (the spec defines none; `allowlist` is the scoped
escape hatch). No per-role or per-workflow scoping — the policy is uniform
(FR-009).
