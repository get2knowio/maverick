# feat(cli): unified maverick init with Claude-powered project detection and preflight API validation

**Labels:** `enhancement`, `cli`, `priority:high`

## Summary

Replace `maverick config init` with a comprehensive `maverick init` command that:
1. Validates all prerequisites (git, gh, GitHub auth, Anthropic API)
2. Uses Claude to analyze the project and derive configuration values
3. Prints all findings used to populate the config file

Additionally, add Anthropic API validation to workflow preflight checks.

## Design Decisions

- **No interactive prompts** - Derive everything automatically, print findings
- **Simple API validation** - "echo ok" style minimal call
- **No caching** - Always fresh detection
- **Preflight includes API check** - Workflows validate Claude access before starting

## Proposed Solution

### New Command: `maverick init`

```bash
maverick init [--force] [--type TYPE] [--no-detect]
```

### Output Format

```
$ maverick init

══════════════════════════════════════════════════════════════════
                        Maverick Init
══════════════════════════════════════════════════════════════════

[1/4] Dependencies
  ✓ git 2.43.0 (/usr/bin/git)
  ✓ gh 2.40.0 (/usr/bin/gh)
  ✓ GitHub: authenticated as @username

[2/4] Anthropic API
  ✓ ANTHROPIC_API_KEY: sk-ant-...XXXX (redacted)
  ✓ Model access: claude-sonnet-4-20250514 (ok)

[3/4] Repository Analysis
  ✓ Git remote: github.com/acme/ansible-collection
  ✓ Owner: acme
  ✓ Repo: ansible-collection
  ✓ Default branch: main
  ✓ Current branch: feature/new-role

[4/4] Project Detection (via Claude)
  Analyzed: 47 files, 12 directories

  Findings:
    • galaxy.yml present → Ansible Collection
    • roles/ directory with 5 roles
    • molecule/ directory → molecule testing configured
    • .yamllint.yml present → yamllint configured
    • No Python source code detected

  Project type: Ansible Collection (confidence: high)

  Derived validation commands:
    format:    yamllint --strict .
    lint:      ansible-lint
    typecheck: (none)
    test:      molecule test

══════════════════════════════════════════════════════════════════

Generated: ./maverick.yaml

github:
  owner: acme
  repo: ansible-collection
  default_branch: main
notifications:
  enabled: false
  server: https://ntfy.sh
  topic: null
validation:
  format_cmd: [yamllint, --strict, .]
  lint_cmd: [ansible-lint]
  typecheck_cmd: []
  test_cmd: [molecule, test]
  timeout_seconds: 600
  max_errors: 50
model:
  model_id: claude-sonnet-4-20250514
  max_tokens: 8192
  temperature: 0.0
parallel:
  max_agents: 3
  max_tasks: 5
verbosity: warning

══════════════════════════════════════════════════════════════════
Ready! Run 'maverick fly <branch>' to start a workflow.
```

### Preflight API Validation

Add Anthropic API check to existing preflight infrastructure:

**Current preflight checks** (`src/maverick/config.py` - `PreflightValidationConfig`):
- Git repository validation
- GitHub CLI authentication
- Required files present

**New preflight check**:
```python
async def check_anthropic_api() -> PreflightResult:
    """Validate Anthropic API access before workflow execution.

    Makes minimal API call to verify credentials are valid and
    model is accessible. Called at workflow start, not cached.
    """
```

**Workflow startup output:**
```
$ maverick fly feature/new-role

Preflight checks:
  ✓ Git repository valid
  ✓ GitHub authenticated
  ✓ Anthropic API accessible
  ✓ Task file found

Starting FlyWorkflow...
```

**Preflight failure:**
```
$ maverick fly feature/new-role

Preflight checks:
  ✓ Git repository valid
  ✓ GitHub authenticated
  ✗ Anthropic API: invalid API key

Error: Preflight check failed. Fix issues and retry.
```

## Implementation

### New/Modified Files

| File | Change |
|------|--------|
| `src/maverick/cli/commands/init.py` | New - unified init command |
| `src/maverick/cli/validators.py` | Add `check_anthropic_api()` |
| `src/maverick/preflight.py` | New - preflight check orchestration |
| `src/maverick/project_detector.py` | New - Claude-powered detection |
| `src/maverick/workflows/fly/workflow.py` | Add preflight checks at start |
| `src/maverick/workflows/refuel/workflow.py` | Add preflight checks at start |
| `src/maverick/cli/commands/config.py` | Deprecate `config init` |

### Project Detection Prompt (for Claude)

```
Analyze this project structure and determine the project type and appropriate validation tools.

Directory structure:
{tree_output}

Key file contents:
{file_contents}

Respond with JSON:
{
  "project_type": "ansible|python|node|go|rust|unknown",
  "confidence": "high|medium|low",
  "findings": ["finding 1", "finding 2"],
  "validation": {
    "format_cmd": ["cmd", "arg1"],
    "lint_cmd": ["cmd", "arg1"],
    "typecheck_cmd": [],
    "test_cmd": ["cmd", "arg1"]
  },
  "timeout_seconds": 300
}
```

### Repository Derivation Logic

```python
def derive_repo_info() -> RepoInfo:
    """Derive GitHub owner/repo from git remote."""
    # Parse: git@github.com:owner/repo.git
    # Parse: https://github.com/owner/repo.git
    # Fallback: leave null with warning
```

## Acceptance Criteria

- [ ] `maverick init` validates git, gh, gh auth, and Anthropic API
- [ ] `maverick init` derives owner/repo from git remote
- [ ] `maverick init` uses Claude to detect project type
- [ ] All findings printed before config generation
- [ ] No interactive prompts (fully automatic)
- [ ] `--type` flag overrides Claude detection
- [ ] `--no-detect` skips Claude call, uses marker-based heuristics
- [ ] `--force` overwrites existing maverick.yaml
- [ ] `maverick config init` shows deprecation warning
- [ ] `maverick fly` runs preflight check including Anthropic API
- [ ] `maverick refuel` runs preflight check including Anthropic API
- [ ] Preflight failures block workflow with clear error message

## Project Type Matrix

| Type | Markers | format | lint | typecheck | test | timeout |
|------|---------|--------|------|-----------|------|---------|
| Python | pyproject.toml, setup.py | ruff format | ruff check --fix | mypy | pytest | 300 |
| Ansible Collection | galaxy.yml | yamllint | ansible-lint | - | molecule test | 600 |
| Ansible Playbook | site.yml, ansible.cfg | yamllint | ansible-lint | - | ansible-playbook --check | 300 |
| Node.js | package.json | prettier --write | eslint --fix | tsc --noEmit | npm test | 300 |
| Go | go.mod | gofmt -w | golangci-lint run | - | go test ./... | 300 |
| Rust | Cargo.toml | cargo fmt | cargo clippy --fix | - | cargo test | 300 |

## Error States

| Condition | Behavior |
|-----------|----------|
| No git remote | owner/repo left as null, warning printed |
| ANTHROPIC_API_KEY unset | Error, suggest export command |
| API key invalid | Error, suggest checking key |
| Model not accessible | Error, suggest checking plan/permissions |
| Unknown project type | Use Python defaults, print warning |
| maverick.yaml exists | Error unless --force |

## Related

- Supersedes the hardcoded Python defaults in current `config init`
- Uses existing `check_dependencies()`, `check_git_auth()` infrastructure from `cli/validators.py`
