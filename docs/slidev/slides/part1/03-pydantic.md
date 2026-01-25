---
layout: section
class: text-center
---

# 3. Pydantic - Data Validation & Configuration

<div class="text-lg text-secondary mt-4">
Runtime validation and type-safe configuration
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">8 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Pydantic v2</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Config Layering</span>
  </div>
</div>

<!--
Section 3 covers Pydantic - the data validation library that powers Maverick's configuration and workflow schema system.

We'll cover:
1. Why Pydantic and its benefits
2. BaseModel basics
3. Field configuration
4. Field validators
5. Model validators
6. Nested models and discriminated unions
7. Pydantic Settings for environment variables
8. Configuration layering in Maverick
-->

---

## layout: two-cols

# 3.1 Why Pydantic?

<div class="pr-4">

**Pydantic** provides runtime data validation using Python type hints

<div v-click class="mt-4">

## Key Benefits

<div class="space-y-2 text-sm mt-3">

- **Runtime Validation**: Catch errors when data arrives, not later
- **Type Coercion**: Auto-converts `"42"` → `42` when appropriate
- **IDE Support**: Full autocompletion from type hints
- **Serialization**: Easy JSON/YAML round-tripping
- **Error Messages**: Clear, actionable validation errors

</div>

</div>

<div v-click class="mt-4">

## Pydantic v2 Improvements

<div class="text-sm space-y-1 mt-2">

- **5-50x faster** validation (Rust core)
- Cleaner validator decorator syntax
- Better generics and type support
- Strict mode for no coercion

</div>

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Maverick Uses Pydantic For

```python
# Configuration (config.py)
class MaverickConfig(BaseSettings):
    github: GitHubConfig
    validation: ValidationConfig
    model: ModelConfig

# Workflow Schema (schema.py)
class WorkflowFile(BaseModel):
    version: str
    name: str
    steps: list[StepRecordUnion]
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Key Files:</strong>
  <div class="font-mono text-xs mt-1">
    src/maverick/config.py<br/>
    src/maverick/dsl/serialization/schema.py
  </div>
</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Note:</strong> Maverick uses Pydantic v2 syntax.
  <div class="text-xs mt-1">Watch for <code>@field_validator</code> vs old <code>@validator</code></div>
</div>

</div>

<!--
Pydantic bridges the gap between type hints (which Python ignores at runtime) and actual validation. When you define a model with type hints, Pydantic enforces those types when data is loaded.

Key v2 improvements for Maverick:
- Much faster validation (critical for workflow parsing)
- Cleaner @field_validator and @model_validator decorators
- Better support for discriminated unions (used for step types)

Maverick uses Pydantic for two main purposes:
1. Configuration management (MaverickConfig hierarchy)
2. Workflow schema validation (WorkflowFile and step types)
-->

---

## layout: default

# 3.2 BaseModel Basics

<div class="text-secondary text-sm mb-4">
Defining models with automatic validation and serialization
</div>

```python {all|1-8|10-17|19-26|all}
from pydantic import BaseModel

class GitHubConfig(BaseModel):
    """Settings for GitHub integration."""

    owner: str | None = None
    repo: str | None = None
    default_branch: str = "main"

# Creating instances - validation happens automatically
config = GitHubConfig(owner="get2knowio", repo="maverick")
print(config.owner)          # "get2knowio"
print(config.default_branch) # "main" (used default)

# Type coercion in action
config2 = GitHubConfig(owner=123)  # Coerced: 123 → "123"
print(config2.owner)               # "123" (string)

# Validation errors
try:
    GitHubConfig(owner=["not", "a", "string"])
except ValidationError as e:
    print(e)
    # 1 validation error for GitHubConfig
    # owner
    #   Input should be a valid string [type=string_type]
```

<div v-click class="mt-4 grid grid-cols-3 gap-4 text-sm">
  <div class="p-2 bg-slate-800 rounded">
    <strong>model_dump()</strong>
    <div class="text-xs text-muted">→ dict</div>
  </div>
  <div class="p-2 bg-slate-800 rounded">
    <strong>model_dump_json()</strong>
    <div class="text-xs text-muted">→ JSON string</div>
  </div>
  <div class="p-2 bg-slate-800 rounded">
    <strong>model_validate()</strong>
    <div class="text-xs text-muted">dict → model</div>
  </div>
</div>

<!--
BaseModel is the foundation of Pydantic. Inherit from it to get:

1. Automatic validation when creating instances
2. Type coercion (string "42" becomes int 42)
3. Clear error messages for invalid data
4. Serialization methods (to_dict, to_json)

Notice that:
- Fields with defaults are optional
- Fields without defaults are required
- Type coercion happens automatically (123 → "123")
- Invalid data raises ValidationError with details

The v2 serialization methods:
- model_dump() replaces .dict()
- model_dump_json() replaces .json()
- model_validate() replaces .parse_obj()
-->

---

## layout: default

# 3.3 Field Configuration

<div class="text-secondary text-sm mb-4">
Using <code>Field()</code> for defaults, constraints, and documentation
</div>

```python {all|1-7|9-16|18-26|all}
from pydantic import BaseModel, Field

class ModelConfig(BaseModel):
    """Settings for Claude model selection."""

    model_id: str = "claude-sonnet-4-20250514"
    max_tokens: int = Field(default=64000, gt=0, le=200000)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)

class ValidationConfig(BaseModel):
    """Settings for validation commands."""

    format_cmd: list[str] = Field(default_factory=lambda: ["ruff", "format", "."])
    lint_cmd: list[str] = Field(default_factory=lambda: ["ruff", "check", "--fix", "."])
    timeout_seconds: int = Field(default=300, ge=30, le=600)
    max_errors: int = Field(default=50, ge=1, le=500)

class WorkflowFile(BaseModel):
    """Top-level workflow file schema."""

    version: str = Field(..., pattern=r"^\d+\.\d+$", description="Schema version")
    name: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9-]{0,63}$",
        description="Workflow identifier (lowercase, hyphens allowed)",
    )
    description: str = ""
```

<div v-click class="mt-4 grid grid-cols-4 gap-3 text-xs">
  <div class="p-2 bg-teal/10 border border-teal/30 rounded"><strong>gt, ge, lt, le</strong><br/>Numeric constraints</div>
  <div class="p-2 bg-brass/10 border border-brass/30 rounded"><strong>min_length, max_length</strong><br/>String/list length</div>
  <div class="p-2 bg-coral/10 border border-coral/30 rounded"><strong>pattern</strong><br/>Regex validation</div>
  <div class="p-2 bg-purple-500/10 border border-purple-500/30 rounded"><strong>default_factory</strong><br/>Mutable defaults</div>
</div>

<!--
Field() provides fine-grained control over field behavior:

Constraints:
- gt/ge/lt/le: Greater/less than (or equal) for numbers
- min_length/max_length: String and list length limits
- pattern: Regex pattern matching for strings

Defaults:
- default: Simple default value
- default_factory: Callable for mutable defaults (lists, dicts)
- ... (ellipsis): Required field, no default

Documentation:
- description: Shows in schema and error messages
- title: Alternative field name for display
- examples: Example values for documentation

The pattern constraint is powerful - we use it to enforce workflow naming conventions and version format.
-->

---

## layout: default

# 3.4 Field Validators

<div class="text-secondary text-sm mb-4">
Custom validation logic per field with <code>@field_validator</code>
</div>

```python {all|1-12|14-26|all}
from pathlib import Path
from pydantic import BaseModel, Field, field_validator

class ValidationConfig(BaseModel):
    """Settings for validation commands."""

    timeout_seconds: int = Field(default=300, ge=30, le=600)
    project_root: Path | None = None

    @field_validator("project_root")
    @classmethod
    def check_project_root_exists(cls, v: Path | None) -> Path | None:
        """Warn if project_root path doesn't exist."""
        if v is not None and not v.exists():
            logger.warning(
                f"Configured project_root does not exist: {v}. "
                "Validation commands may fail."
            )
        return v

class StepRecord(BaseModel):
    """Base schema for step definitions."""

    name: str = Field(..., min_length=1)

    @field_validator("name")
    @classmethod
    def validate_name_format(cls, v: str) -> str:
        """Ensure step name is valid."""
        if not v.strip():
            raise ValueError("Step name cannot be empty or whitespace")
        return v
```

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">v2 Syntax:</strong> <code>@field_validator</code> + <code>@classmethod</code> is required in Pydantic v2
  <div class="text-xs mt-1">v1 used <code>@validator</code> without <code>@classmethod</code></div>
</div>

<!--
Field validators let you add custom validation logic beyond type checking:

Key patterns:
1. Return the value (possibly modified)
2. Raise ValueError for validation failures
3. Use logger.warning for non-fatal issues

Important v2 changes:
- Must use @field_validator (not @validator)
- Must add @classmethod decorator
- First param is cls, not self
- Value is first positional arg after cls

Validator use cases in Maverick:
- Check file paths exist
- Normalize string values (strip whitespace)
- Validate against external systems
-->

---

## layout: default

# 3.5 Model Validators

<div class="text-secondary text-sm mb-4">
Cross-field validation with <code>@model_validator</code>
</div>

```python {all|1-15|17-30|all}
from typing import Self
from pydantic import BaseModel, model_validator

class NotificationConfig(BaseModel):
    """Settings for ntfy-based push notifications."""

    enabled: bool = False
    server: str = "https://ntfy.sh"
    topic: str | None = None

    @model_validator(mode="after")
    def check_topic_when_enabled(self) -> Self:
        """Ensure topic is set when notifications are enabled."""
        if self.enabled and self.topic is None:
            logger.warning(
                "Notifications enabled but no topic specified."
            )
        return self

class InputDefinition(BaseModel):
    """Workflow input parameter declaration."""

    type: InputType
    required: bool = True
    default: Any = None

    @model_validator(mode="after")
    def validate_default_consistency(self) -> InputDefinition:
        """Ensure required/default consistency."""
        if self.required and self.default is not None:
            raise ValueError("Required inputs cannot have default values")
        return self
```

<div v-click class="mt-4 grid grid-cols-2 gap-4 text-sm">
  <div class="p-3 bg-teal/10 border border-teal/30 rounded">
    <strong class="text-teal">mode="before"</strong>
    <div class="text-xs mt-1">Runs before field validation. Receives raw input dict. Use for data transformation.</div>
  </div>
  <div class="p-3 bg-brass/10 border border-brass/30 rounded">
    <strong class="text-brass">mode="after"</strong>
    <div class="text-xs mt-1">Runs after field validation. Has access to <code>self</code>. Use for cross-field checks.</div>
  </div>
</div>

<!--
Model validators run on the entire model, allowing cross-field validation:

mode="before":
- Receives raw input (dict)
- Runs BEFORE individual field validation
- Use for transforming input data structure
- Return modified dict

mode="after":
- Receives validated model instance (self)
- Runs AFTER all field validation
- Use for cross-field consistency checks
- Return self or raise ValueError

In Maverick:
- NotificationConfig checks topic is set when enabled
- InputDefinition ensures required fields don't have defaults
- Both use mode="after" for field access
-->

---

## layout: default

# 3.6 Nested Models

<div class="text-secondary text-sm mb-4">
Composing models and discriminated unions for step types
</div>

```python {all|1-16|18-31|all}
from typing import Annotated, Literal
from pydantic import BaseModel, Field

class PythonStepRecord(StepRecord):
    """Python callable step."""
    type: Literal[StepType.PYTHON] = StepType.PYTHON
    action: str
    args: list[Any] = Field(default_factory=list)

class AgentStepRecord(StepRecord):
    """Agent invocation step."""
    type: Literal[StepType.AGENT] = StepType.AGENT
    agent: str
    context: dict[str, Any] | str = Field(default_factory=dict)

# Discriminated union - Pydantic auto-selects correct type based on 'type' field
StepRecordUnion = Annotated[
    PythonStepRecord
    | AgentStepRecord
    | ValidateStepRecord
    | BranchStepRecord
    | LoopStepRecord
    | CheckpointStepRecord,
    Field(discriminator="type"),
]

class WorkflowFile(BaseModel):
    """Top-level workflow file schema."""
    version: str
    name: str
    steps: list[StepRecordUnion]  # Each step auto-validated to correct type
```

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Discriminated Union:</strong> When parsing YAML with <code>type: "agent"</code>, Pydantic automatically creates an <code>AgentStepRecord</code>
</div>

<!--
Pydantic excels at nested models and discriminated unions:

Nested Models:
- Models can contain other models as fields
- MaverickConfig contains GitHubConfig, ValidationConfig, etc.
- Validation cascades through the entire tree

Discriminated Unions:
- Union of types with a common discriminator field
- Pydantic uses the discriminator value to pick the right type
- Perfect for our workflow step types

How it works:
1. YAML has {"type": "agent", "agent": "implementer"}
2. Pydantic sees type="agent"
3. Routes to AgentStepRecord for validation
4. Returns properly typed AgentStepRecord instance

This eliminates manual type dispatch code!
-->

---

## layout: default

# 3.7 Pydantic Settings

<div class="text-secondary text-sm mb-4">
Environment variables and <code>.env</code> files with <code>BaseSettings</code>
</div>

```python {all|1-12|14-26|all}
from pydantic_settings import BaseSettings, SettingsConfigDict

class MaverickConfig(BaseSettings):
    """Root configuration object."""

    model_config = SettingsConfigDict(
        env_prefix="MAVERICK_",         # MAVERICK_VERBOSITY=debug
        env_nested_delimiter="__",      # MAVERICK_GITHUB__OWNER=get2knowio
        extra="ignore",                 # Ignore unknown fields
    )

    github: GitHubConfig = Field(default_factory=GitHubConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    verbosity: Literal["error", "warning", "info", "debug"] = "warning"

# Environment variable examples:
# MAVERICK_VERBOSITY=debug                    → verbosity = "debug"
# MAVERICK_GITHUB__OWNER=myorg               → github.owner = "myorg"
# MAVERICK_GITHUB__DEFAULT_BRANCH=develop    → github.default_branch = "develop"
# MAVERICK_MODEL__TEMPERATURE=0.7            → model.temperature = 0.7

# Automatic loading from environment
config = MaverickConfig()  # Reads from env vars automatically!
print(config.verbosity)    # "debug" if MAVERICK_VERBOSITY=debug
```

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Package:</strong> <code>pydantic-settings</code> is separate from <code>pydantic</code> in v2
</div>

<!--
pydantic-settings (separate package in v2) provides environment variable integration:

SettingsConfigDict options:
- env_prefix: Prefix for all env vars (MAVERICK_)
- env_nested_delimiter: Separator for nested fields (__)
- extra: How to handle unknown fields

Nested field access:
- MAVERICK_GITHUB__OWNER accesses github.owner
- Double underscore (__) separates levels

Priority (default):
1. Init values (passed to constructor)
2. Environment variables
3. .env file
4. Field defaults

We customize this in Maverick to add YAML config files to the chain.
-->

---

## layout: two-cols

# 3.8 Config Layering in Maverick

<div class="pr-4">

### Priority Order (Highest → Lowest)

<div class="space-y-2 mt-4 text-sm">

<div v-click class="flex items-center gap-2">
  <span class="w-6 h-6 flex items-center justify-center bg-red-500/20 text-red-400 rounded font-bold text-xs">1</span>
  <div>
    <strong>Environment Variables</strong>
    <div class="text-xs text-muted">MAVERICK_VERBOSITY=debug</div>
  </div>
</div>

<div v-click class="flex items-center gap-2">
  <span class="w-6 h-6 flex items-center justify-center bg-orange-500/20 text-orange-400 rounded font-bold text-xs">2</span>
  <div>
    <strong>Project Config</strong>
    <div class="text-xs text-muted">./maverick.yaml</div>
  </div>
</div>

<div v-click class="flex items-center gap-2">
  <span class="w-6 h-6 flex items-center justify-center bg-yellow-500/20 text-yellow-400 rounded font-bold text-xs">3</span>
  <div>
    <strong>User Config</strong>
    <div class="text-xs text-muted">~/.config/maverick/config.yaml</div>
  </div>
</div>

<div v-click class="flex items-center gap-2">
  <span class="w-6 h-6 flex items-center justify-center bg-green-500/20 text-green-400 rounded font-bold text-xs">4</span>
  <div>
    <strong>Built-in Defaults</strong>
    <div class="text-xs text-muted">Pydantic Field() defaults</div>
  </div>
</div>

</div>

</div>

::right::

<div class="pl-4">

<div v-click class="mt-4">

### Custom Settings Source

```python
@classmethod
def settings_customise_sources(
    cls,
    settings_cls: type[BaseSettings],
    init_settings: PydanticBaseSettingsSource,
    env_settings: PydanticBaseSettingsSource,
    dotenv_settings: PydanticBaseSettingsSource,
    file_secret_settings: PydanticBaseSettingsSource,
) -> tuple[PydanticBaseSettingsSource, ...]:
    """Customize settings source order."""
    user_config = get_user_config_path()
    project_config = Path.cwd() / "maverick.yaml"

    return (
        env_settings,              # Highest
        YamlConfigSource(settings_cls, project_config),
        YamlConfigSource(settings_cls, user_config),
        # Defaults are implicit  # Lowest
    )
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Result:</strong> Users can set global defaults in <code>~/.config/maverick/config.yaml</code>, override per-project in <code>./maverick.yaml</code>, and override at runtime with env vars.
</div>

</div>

<!--
Maverick implements a four-tier configuration hierarchy:

1. Environment variables (highest priority)
   - For CI/CD and temporary overrides
   - MAVERICK_VERBOSITY=debug

2. Project config (./maverick.yaml)
   - Project-specific settings
   - Committed to version control

3. User config (~/.config/maverick/config.yaml)
   - Personal defaults across projects
   - API keys, editor preferences

4. Built-in defaults (lowest priority)
   - Sensible defaults in code
   - Works out of the box

The settings_customise_sources() method is the key - it lets us inject our YAML sources into the pydantic-settings chain.

This pattern is powerful: set defaults once, override where needed.
-->
