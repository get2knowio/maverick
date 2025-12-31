# Research: Maverick Foundation

**Feature**: 001-maverick-foundation
**Date**: 2025-12-12

## Overview

Research findings for the Maverick foundation implementation, covering pyproject.toml configuration, Pydantic settings management, and Click CLI patterns.

## Decision 1: Build Backend

**Decision**: Use Hatchling as the build backend

**Rationale**:
- Fully embraces PEP 621 with clean pyproject.toml-only configuration
- Superior defaults: uses .gitignore for source distributions
- Produces reproducible builds by default (wheels and sdists)
- Simpler configuration without needing setup.py or MANIFEST.in
- Auto-detects src layout without manual configuration
- Growing adoption (6.5% of PyPI packages in 2025)

**Alternatives Considered**:
- **Setuptools**: Still dominates PyPI but less ergonomic for pure Python projects; requires more configuration for src layout
- **uv_build**: Fast builds but less mature ecosystem
- **Poetry**: More opinionated, uses poetry.lock instead of standard lock files

**Configuration**:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

## Decision 2: Pydantic Configuration Pattern

**Decision**: Use pydantic-settings with custom `settings_customise_sources()` for multi-source config

**Rationale**:
- Provides type validation and clear error messages
- Supports nested models with `env_nested_delimiter='__'`
- Enables custom source priority (defaults → user → project → env)
- YamlConfigSettingsSource requires manual integration via `settings_customise_sources()`
- SecretStr type prevents accidental exposure of sensitive data

**Alternatives Considered**:
- **Plain Pydantic BaseModel + yaml.safe_load()**: Simpler but loses env var integration
- **Dynaconf**: Feature-rich but heavier dependency; Pydantic already in stack
- **python-dotenv only**: No validation, no type safety

**Key Implementation Notes**:
1. Must override `settings_customise_sources()` - setting `yaml_file` in model_config alone doesn't work
2. Use `env_nested_delimiter='__'` for nested config (e.g., `MAVERICK_GITHUB__OWNER`)
3. Use `env_prefix='MAVERICK_'` for all environment variables
4. Use `SecretStr` for any future API key fields
5. Add `extra="ignore"` to handle undefined env vars gracefully

**Source Priority (Highest to Lowest)**:
1. Environment variables (`MAVERICK_*`)
2. Project config (`maverick.yaml` in current directory)
3. User config (`~/.config/maverick/config.yaml`)
4. Built-in defaults

## Decision 3: Click CLI Structure

**Decision**: Use Click group with verbosity count option and version_option decorator

**Rationale**:
- Entry points via `[project.scripts]` are the modern standard
- `count=True` option enables `-v`, `-vv`, `-vvv` patterns naturally
- `click.version_option()` is eager and exits cleanly
- Context object (`ctx.obj`) provides clean state sharing without globals

**Alternatives Considered**:
- **argparse**: More verbose, less composable
- **typer**: Built on Click but adds type hint magic that may conflict with existing patterns
- **fire**: Auto-generates CLI but less control over structure

**Key Implementation Notes**:
1. Use `@click.option('-v', '--verbose', count=True)` for verbosity
2. Map verbosity to logging: `level = max(10, 30 - (verbose * 10))`
   - 0 (default): WARNING (30)
   - 1 (-v): INFO (20)
   - 2 (-vv): DEBUG (10)
3. Configure logging early in the CLI group before subcommands
4. Use `ctx.ensure_object(dict)` for shared state
5. Use `click.echo()` for output instead of `print()`

**Exit Code Convention**:
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (ClickException, ConfigError) |
| 2 | Usage error (UsageError, BadParameter) |

## Decision 4: Dependency Version Strategy

**Decision**: Use minimum version pins with upper bounds for major versions

**Rationale**:
- Minimum pins document compatibility assumptions
- Upper bounds prevent unexpected major version breaking changes
- Allows users' lock files to handle exact pinning
- Format: `package>=X.Y.Z,<X+1` (e.g., `click>=8.1.0,<9`)

**Alternatives Considered**:
- **Exact pins**: Too restrictive, causes dependency conflicts
- **No upper bounds**: Risk of breaking changes from major updates
- **Compatible release (~=)**: Less explicit than explicit ranges

**Dependencies for Foundation**:
```toml
dependencies = [
    "click>=8.1.0,<9",
    "pydantic>=2.0,<3",
    "pydantic-settings>=2.0,<3",
    "pyyaml>=6.0,<7",
]
```

**Development Dependencies (PEP 735 dependency groups)**:
```toml
[dependency-groups]
test = [
    "pytest>=7.0.0,<8",
    "pytest-asyncio>=0.21.0,<1",
    "pytest-cov>=4.0.0,<5",
]
lint = [
    "ruff>=0.1.0,<1",
    "mypy>=1.0.0,<2",
]
dev = [
    {include-group = "test"},
    {include-group = "lint"},
]
```

## Decision 5: Exception Hierarchy

**Decision**: Define `MaverickError` base class with `ConfigError` subclass

**Rationale**:
- Enables consistent error handling at CLI boundaries
- Allows catching all Maverick errors with single except clause
- `ConfigError` provides specific handling for config validation failures
- Aligns with constitution principle IV (Fail Gracefully)

**Hierarchy**:
```
MaverickError (base)
└── ConfigError (configuration loading, parsing, validation)
```

**Future Extensions** (out of scope for foundation):
```
MaverickError
├── ConfigError
├── AgentError
└── WorkflowError
```

## Decision 6: Logging Configuration

**Decision**: Use standard library logging with verbosity-based level configuration

**Rationale**:
- No external dependencies
- Integrates cleanly with Click via callback
- Constitution principle VII (Simplicity): no `print()` for output
- Constitution principle II (Separation of Concerns): logging separate from TUI

**Alternatives Considered**:
- **click-log**: Cleaner decorators but adds dependency
- **structlog**: More powerful but overkill for CLI foundation
- **loguru**: Nice API but non-standard

**Configuration**:
```python
import logging

level = max(10, 30 - (verbose * 10))
logging.basicConfig(
    level=level,
    format='%(levelname)s: %(message)s'
)
```

## Sources

- [Pydantic Settings Management](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Click CLI Documentation](https://click.palletsprojects.com/en/stable/)
- [Python Packaging User Guide - pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [PEP 621 - Project Metadata](https://peps.python.org/pep-0621/)
- [PEP 735 - Dependency Groups](https://peps.python.org/pep-0735/)
- [Hatch Documentation](https://hatch.pypa.io/)
