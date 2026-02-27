# Data Model: Three-Tier Prompt Configuration

**Branch**: `036-prompt-config` | **Date**: 2026-02-27

## Core Entities

### OverridePolicy (Enum)

```python
class OverridePolicy(str, Enum):
    AUGMENT_ONLY = "augment_only"  # Only prompt_suffix allowed
    REPLACE = "replace"            # prompt_file (full replacement) allowed
```

**Rules**:
- Default for new entries: `AUGMENT_ONLY` (safe by default)
- `augment_only` steps: structured output consumed by downstream parsing
- `replace` steps: free-form text output not consumed programmatically

### PromptEntry (Frozen Dataclass)

```python
@dataclass(frozen=True, slots=True)
class PromptEntry:
    text: str                              # Default prompt/instructions text
    policy: OverridePolicy                 # Override policy for this step
    provider: str = GENERIC_PROVIDER       # Provider key (default: generic)
    is_template: bool = False              # Whether text contains $-variables
```

**Fields**:
- `text`: The raw prompt text (may contain `$variable` template placeholders if `is_template=True`)
- `policy`: Governs whether users can fully replace this prompt or only append to it
- `provider`: Provider identifier; `GENERIC_PROVIDER = "__generic__"` is the default sentinel
- `is_template`: Whether `render_prompt()` should be called on the text before use

**Identity**: Uniquely identified by `(step_name, provider)` in the registry.

### PromptRegistry (Immutable Mapping)

```python
class PromptRegistry:
    """Immutable mapping of (step_name, provider) → PromptEntry."""

    _entries: dict[tuple[str, str], PromptEntry]  # Set once at construction
```

**Methods**:
- `get(step_name, provider=GENERIC_PROVIDER) → PromptEntry` — Look up with fallback to generic
- `get_policy(step_name) → OverridePolicy` — Shortcut for override policy lookup
- `has(step_name, provider=GENERIC_PROVIDER) → bool` — Existence check
- `step_names() → frozenset[str]` — All registered step names
- `validate_override(step_name, override) → None` — Raise if override violates policy

**Lifecycle**: Created once at startup via `build_default_registry()`. Immutable after construction (no add/remove/update methods).

**Invariants**:
- Every step name MUST have at least one entry with `provider=GENERIC_PROVIDER`
- No duplicate `(step_name, provider)` keys
- Empty registry raises `PromptConfigError` at construction

### PromptOverrideConfig (Pydantic Model — Config Section)

```python
class PromptOverrideConfig(BaseModel):
    prompt_suffix: str | None = None    # Inline text appended to default
    prompt_file: str | None = None      # Path to replacement/override file
```

**Validation rules**:
- `prompt_suffix` and `prompt_file` are mutually exclusive (Pydantic `model_validator`)
- At least one must be set (otherwise the entry is a no-op and should be omitted)
- `prompt_file` paths validated at workflow startup (exist, readable, within project root)

**Configuration location**: `maverick.yaml` under `prompts:` key:
```yaml
prompts:
  implement:
    prompt_suffix: "Always use snake_case for database columns."
  pr_description:
    prompt_file: ".maverick/prompts/pr-description.md"
```

### PromptResolution (Frozen Dataclass — resolve_prompt output)

```python
@dataclass(frozen=True, slots=True)
class PromptResolution:
    text: str                          # Final resolved prompt text
    source: PromptSource               # How it was resolved
    step_name: str                     # Which step this is for
    provider: str                      # Which provider was matched
    override_applied: bool             # Whether user override was applied

    def to_dict(self) -> dict[str, Any]: ...
```

### PromptSource (Enum)

```python
class PromptSource(str, Enum):
    DEFAULT = "default"                 # Registry default, no override
    SUFFIX = "suffix"                   # Default + user suffix appended
    FILE = "file"                       # Full replacement from file
    PROVIDER_VARIANT = "provider-variant"  # Provider-specific default selected (no override applied)
```

## Relationships

```
MaverickConfig
  ├── prompts: dict[str, PromptOverrideConfig]   # User overrides
  └── steps: dict[str, StepConfig]               # StepConfig also has prompt fields
        └── prompt_suffix / prompt_file           # From spec 033

PromptRegistry
  └── entries: dict[(step_name, provider), PromptEntry]
        └── PromptEntry(text, policy, provider, is_template)

resolve_prompt(step_name, provider, registry, override, project_root, render_context)
  ├── Input: PromptRegistry + PromptOverrideConfig
  └── Output: PromptResolution(text, source, step_name, provider, override_applied)
```

## Resolution Algorithm

```
resolve_prompt(step_name, provider, registry, override, project_root, render_context):
  1. Look up (step_name, provider) in registry
     - If not found, fall back to (step_name, GENERIC_PROVIDER)
     - If still not found, raise PromptConfigError
     - If provider-specific found, set source = PROVIDER_VARIANT
     - Else set source = DEFAULT

  2. base_text = entry.text
     - If entry.is_template, apply render_prompt(base_text, **render_context)

  3. If override is None:
     - Return PromptResolution(text=base_text, source=source, override_applied=False)

  4. If override.prompt_file is set:
     - Validate entry.policy == REPLACE, else raise PromptConfigError
     - Validate file path within project_root
     - Read file contents
     - If entry.is_template, apply render_prompt(file_contents, **render_context)
     - Return PromptResolution(text=file_contents, source=FILE, override_applied=True)

  5. If override.prompt_suffix is set:
     - If suffix is empty string, return as if no override
     - separator = "\n\n---\n\n## Project-Specific Instructions\n\n"
     - resolved = base_text + separator + suffix
     - If entry.is_template, apply render_prompt on suffix portion
     - Return PromptResolution(text=resolved, source=SUFFIX, override_applied=True)
```

## Default Registry Entries

| Step Name | Agent/Generator | Policy | is_template |
|-----------|----------------|--------|-------------|
| `implement` | ImplementerAgent | `augment_only` | `True` |
| `review` | CodeReviewerAgent | `augment_only` | `False` |
| `fix` | FixerAgent | `augment_only` | `False` |
| `issue_fix` | IssueFixerAgent | `augment_only` | `False` |
| `curator` | CuratorAgent | `augment_only` | `False` |
| `commit_message` | CommitMessageGenerator | `replace` | `False` |
| `pr_description` | PRDescriptionGenerator | `replace` | `False` |
| `pr_title` | PRTitleGenerator | `replace` | `False` |
| `code_analyze` | CodeAnalyzer | `replace` | `False` |
| `error_explain` | ErrorExplainer | `replace` | `False` |
| `dependency_extract` | DependencyExtractor | `replace` | `False` |
| `bead_enrich` | BeadEnricher | `replace` | `False` |

## Error Types

```python
class PromptConfigError(ConfigError):
    """Raised for prompt configuration or resolution errors."""
```

Specific error scenarios:
- Missing default prompt for step_name → `PromptConfigError("No default prompt registered for step '{step_name}'")`
- Policy violation (prompt_file on augment_only) → `PromptConfigError("Step '{step_name}' does not allow full prompt replacement (policy: augment_only)")`
- Missing prompt_file → `PromptConfigError("Prompt file not found: {path}")`
- File outside project root → `PromptConfigError("Prompt file must be within project root: {path}")`
- Both suffix and file configured → `PromptConfigError("Cannot configure both prompt_suffix and prompt_file for step '{step_name}'")`
