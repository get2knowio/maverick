# Quickstart: Three-Tier Prompt Configuration

**Branch**: `036-prompt-config` | **Date**: 2026-02-27

## Scenario 1: Default Prompts (Zero Config)

All agents work out of the box with no prompt configuration:

```python
from maverick.prompts import build_default_registry, resolve_prompt

# Build registry at startup (imports from agent modules)
registry = build_default_registry()

# Resolve prompt for the implementer step
resolution = resolve_prompt(
    step_name="implement",
    registry=registry,
)

assert resolution.source.value == "default"
assert resolution.override_applied is False
assert "implement" in resolution.text.lower() or len(resolution.text) > 0
```

## Scenario 2: Append Custom Guidance (prompt_suffix)

Add project-specific conventions without losing defaults:

```yaml
# maverick.yaml
prompts:
  implement:
    prompt_suffix: "Always use snake_case for database columns."
```

```python
from maverick.prompts import (
    PromptOverrideConfig,
    build_default_registry,
    resolve_prompt,
)

registry = build_default_registry()

# User override from config
override = PromptOverrideConfig(prompt_suffix="Always use snake_case for database columns.")

resolution = resolve_prompt(
    step_name="implement",
    registry=registry,
    override=override,
)

assert resolution.source.value == "suffix"
assert resolution.override_applied is True
assert "snake_case" in resolution.text
# Default instructions are still present:
assert len(resolution.text) > len("Always use snake_case for database columns.")
```

## Scenario 3: Full Prompt Replacement (prompt_file)

Replace the entire prompt for steps that allow it:

```yaml
# maverick.yaml
prompts:
  pr_description:
    prompt_file: ".maverick/prompts/pr-description.md"
```

```python
from pathlib import Path

from maverick.prompts import (
    OverridePolicy,
    PromptOverrideConfig,
    build_default_registry,
    resolve_prompt,
)

registry = build_default_registry()

# pr_description allows full replacement
assert registry.get_policy("pr_description") == OverridePolicy.REPLACE

override = PromptOverrideConfig(prompt_file=".maverick/prompts/pr-description.md")

resolution = resolve_prompt(
    step_name="pr_description",
    registry=registry,
    override=override,
    project_root=Path("/path/to/project"),
)

assert resolution.source.value == "file"
assert resolution.override_applied is True
```

## Scenario 4: Policy Enforcement (augment_only blocks prompt_file)

Steps with structured output prevent full replacement:

```python
import pytest

from maverick.prompts import (
    OverridePolicy,
    PromptConfigError,
    PromptOverrideConfig,
    build_default_registry,
    resolve_prompt,
)

registry = build_default_registry()

# implement is augment_only — protects structured output contracts
assert registry.get_policy("implement") == OverridePolicy.AUGMENT_ONLY

override = PromptOverrideConfig(prompt_file="custom-implement.md")

with pytest.raises(PromptConfigError, match="does not allow full prompt replacement"):
    resolve_prompt(
        step_name="implement",
        registry=registry,
        override=override,
        project_root=Path("/path/to/project"),
    )
```

## Scenario 5: Provider-Specific Variants

Use provider-optimized prompts when available:

```python
from maverick.prompts import (
    GENERIC_PROVIDER,
    OverridePolicy,
    PromptEntry,
    PromptRegistry,
    resolve_prompt,
)

# Build a registry with a provider-specific variant
entries = {
    ("review", GENERIC_PROVIDER): PromptEntry(
        text="You are a code reviewer.",
        policy=OverridePolicy.AUGMENT_ONLY,
    ),
    ("review", "gemini"): PromptEntry(
        text="You are a code reviewer optimized for Gemini.",
        policy=OverridePolicy.AUGMENT_ONLY,
        provider="gemini",
    ),
}
registry = PromptRegistry(entries)

# With gemini provider — gets the specific variant
resolution = resolve_prompt(
    step_name="review",
    registry=registry,
    provider="gemini",
)
assert "Gemini" in resolution.text
assert resolution.source.value == "provider-variant"

# Without provider — gets the generic default
resolution = resolve_prompt(
    step_name="review",
    registry=registry,
)
assert "Gemini" not in resolution.text
assert resolution.source.value == "default"
```

## Scenario 6: Template Variable Rendering

Prompts with `$variable` placeholders are rendered with project context:

```python
from maverick.prompts import (
    GENERIC_PROVIDER,
    OverridePolicy,
    PromptEntry,
    PromptRegistry,
    resolve_prompt,
)

entries = {
    ("implement", GENERIC_PROVIDER): PromptEntry(
        text="You implement $project_type code. $project_conventions",
        policy=OverridePolicy.AUGMENT_ONLY,
        is_template=True,
    ),
}
registry = PromptRegistry(entries)

resolution = resolve_prompt(
    step_name="implement",
    registry=registry,
    render_context={"project_type": "python", "project_conventions": "Use type hints."},
)

assert "python" in resolution.text
assert "Use type hints" in resolution.text
```

## Scenario 7: Startup Validation

All prompt config is validated at startup, not at runtime:

```python
from pathlib import Path

import pytest

from maverick.prompts import (
    PromptConfigError,
    PromptOverrideConfig,
    build_default_registry,
    validate_prompt_config,
)

registry = build_default_registry()

# Invalid: prompt_file for augment_only step
prompts = {"implement": PromptOverrideConfig(prompt_file="custom.md")}
with pytest.raises(PromptConfigError, match="does not allow full prompt replacement"):
    validate_prompt_config(prompts, registry, project_root=Path.cwd())

# Invalid: unknown step name
prompts = {"nonexistent_step": PromptOverrideConfig(prompt_suffix="test")}
with pytest.raises(PromptConfigError, match="not a registered step"):
    validate_prompt_config(prompts, registry, project_root=Path.cwd())

# Invalid: prompt_file outside project root
prompts = {"pr_description": PromptOverrideConfig(prompt_file="/etc/passwd")}
with pytest.raises(PromptConfigError, match="must be within project root"):
    validate_prompt_config(prompts, registry, project_root=Path.cwd())
```
