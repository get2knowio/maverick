# Research: Three-Tier Prompt Configuration

**Branch**: `036-prompt-config` | **Date**: 2026-02-27

## R-001: Where Are Default Prompts Currently Defined?

**Decision**: Agent prompts are scattered across individual agent files as module-level constants.

**Findings**:

| Agent/Generator | File | Constant | Type |
|-----------------|------|----------|------|
| ImplementerAgent | `agents/implementer.py:50` | `IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE` | Template (uses `$skill_guidance`, `$project_conventions`) |
| FixerAgent | `agents/fixer.py:35` | `FIXER_SYSTEM_PROMPT` | Static string with f-string interpolation |
| CuratorAgent | `agents/curator.py:28` | `SYSTEM_PROMPT` | Static string |
| CodeReviewerAgent | `agents/code_reviewer/prompts.py:9` | `SYSTEM_PROMPT` | Static string |
| IssueFixerAgent | `agents/issue_fixer.py:37` | `ISSUE_FIXER_SYSTEM_PROMPT` | Static string |
| CommitMessageGenerator | `agents/generators/commit_message.py:30` | `COMMIT_MESSAGE_SYSTEM_PROMPT` | Static string |
| PRDescriptionGenerator | `agents/generators/pr_description.py:105` | Dynamic `_build_system_prompt()` | Built at instantiation |
| PRTitleGenerator | `agents/generators/pr_title.py:27` | `PR_TITLE_SYSTEM_PROMPT` | Static string |
| CodeAnalyzer | `agents/generators/code_analyzer.py:30` | `SYSTEM_PROMPT_EXPLAIN/REVIEW/SUMMARIZE` | Three variants |
| ErrorExplainer | `agents/generators/error_explainer.py:40` | `SYSTEM_PROMPT` | Static string |
| DependencyExtractor | `agents/generators/dependency_extractor.py:21` | `DEPENDENCY_EXTRACTOR_SYSTEM_PROMPT` | Static string |
| BeadEnricher | `agents/generators/bead_enricher.py:22` | `BEAD_ENRICHER_SYSTEM_PROMPT` | Static string |

**Rationale**: The registry must import these constants by reference (not copy text) per FR-003.

**Alternatives considered**: Centralizing all prompt text into one file — rejected because it would create a massive god-file and lose locality with agent implementations.

## R-002: How Do Agents Receive Prompts?

**Decision**: Two distinct patterns exist that must both be supported.

**Finding 1 — MaverickAgent (interactive agents)**:
- Constructor receives `instructions: str` parameter
- Instructions are appended to Claude Code preset: `{"type": "preset", "preset": "claude_code", "append": instructions}`
- Some agents render templates via `render_prompt()` before passing to constructor (e.g., ImplementerAgent)

**Finding 2 — GeneratorAgent (one-shot generators)**:
- Constructor receives `system_prompt: str` parameter
- System prompt used directly via `query()` with `max_turns=1`
- No preset — full prompt replacement

**Rationale**: FR-013 requires both to participate in the same registry. The registry must track which pattern each entry uses.

## R-003: What Template Rendering Exists?

**Decision**: Reuse `render_prompt()` from `agents/skill_prompts.py` per A-002.

**Implementation**: `render_prompt(base_prompt, project_type, config_path, extra_context)` uses Python `string.Template.safe_substitute()`. Template variables include `$skill_guidance`, `$project_type`, `$project_type_name`, `$project_conventions`.

**Key property**: `safe_substitute()` leaves unmatched placeholders unchanged (no KeyError). This is important — user-supplied suffixes may contain `$` characters that aren't template variables.

## R-004: Does StepConfig Already Have Prompt Fields?

**Decision**: Yes. `StepConfig` (spec 033) already has `prompt_suffix` and `prompt_file` fields.

**Location**: `src/maverick/dsl/executor/config.py:101-102`

```python
class StepConfig(BaseModel):
    prompt_suffix: str | None = None
    prompt_file: str | None = None
```

**Existing validation**: `prompt_suffix` and `prompt_file` are already mutually exclusive via Pydantic `model_validator` at lines 146-163.

**Existing resolution**: `resolve_step_config()` (lines 250-427) implements 4-layer precedence: inline config → project steps config → agent config → global model config.

**Impact on design**: The `prompts:` YAML section (FR-016) will be a user-friendly alias that feeds into the same StepConfig resolution chain. This avoids duplicating resolution logic.

## R-005: How Will the `prompts:` Config Section Integrate?

**Decision**: Add `prompts: dict[str, PromptOverrideConfig]` to `MaverickConfig`. During validation, merge into the `steps:` dict to leverage existing resolution.

**Design**:
1. Parse `prompts:` YAML key into `dict[str, PromptOverrideConfig]` (Pydantic model with prompt_suffix/prompt_file)
2. In a `model_validator`, merge each `prompts:` entry into `steps:` (creating StepConfig if needed)
3. If both `prompts:` and `steps:` configure prompts for the same step, raise `ConfigError`
4. The existing `resolve_step_config()` then picks up prompt overrides automatically

**Rationale**: Minimizes new code; reuses the battle-tested 4-layer resolution.

**Alternatives considered**: Separate resolution chain for prompts — rejected because it duplicates the precedence logic and creates two sources of truth.

## R-006: How Will the Registry Be Populated?

**Decision**: A `build_default_registry()` function imports agent prompt constants by reference.

**Design**:
```python
def build_default_registry() -> PromptRegistry:
    entries = {}
    # Import from agent modules (no text duplication)
    from maverick.agents.implementer import IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE
    entries[("implement", GENERIC)] = PromptEntry(
        text=IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE,
        policy=OverridePolicy.AUGMENT_ONLY,
    )
    # ... etc for each agent/generator
    return PromptRegistry(entries)
```

**Step name mapping**: The registry uses canonical role names that map to agent/generator names:

| Registry Key | Agent/Generator | Policy |
|-------------|-----------------|--------|
| `implement` | ImplementerAgent | `augment_only` |
| `review` | CodeReviewerAgent | `augment_only` |
| `fix` | FixerAgent | `augment_only` |
| `issue_fix` | IssueFixerAgent | `augment_only` |
| `curator` | CuratorAgent | `augment_only` |
| `commit_message` | CommitMessageGenerator | `replace` |
| `pr_description` | PRDescriptionGenerator | `replace` |
| `pr_title` | PRTitleGenerator | `replace` |
| `code_analyze` | CodeAnalyzer | `replace` |
| `error_explain` | ErrorExplainer | `replace` |
| `dependency_extract` | DependencyExtractor | `replace` |
| `bead_enrich` | BeadEnricher | `replace` |

**Rationale**: Using role names (not class names) keeps the user-facing config intuitive.

## R-007: Integration Points for resolve_prompt()

**Decision**: Call `resolve_prompt()` in two places — the agent step handler and the generate step handler.

**Agent step integration** (`handlers/agent_step.py`):
- After resolving agent context, before calling `StepExecutor.execute()`
- Resolved instructions passed as `instructions` parameter (already accepted but not yet wired)

**Generator step integration** (`handlers/generate_step.py`):
- After instantiating the generator, override its `system_prompt` with resolved prompt
- Use a setter or constructor parameter

**Dispatch handler** (`handlers/dispatch.py`):
- Already builds instructions from intent + prompt_suffix + prompt_file (lines 132-167)
- Integrate with resolve_prompt() for consistency

## R-008: Security Considerations for prompt_file

**Decision**: Restrict to project root; reject absolute paths and traversal.

**Implementation**: In `resolve_prompt()` or config validation:
1. Resolve path relative to project root
2. Call `Path.resolve()` to canonicalize
3. Verify resolved path starts with project root prefix
4. Raise `ConfigError` if outside project root

**Rationale**: Prevents reading `/etc/passwd` or other sensitive files via `../` traversal.
