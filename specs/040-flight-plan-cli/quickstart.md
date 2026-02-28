# Quickstart: Flight Plan CLI Command Group

**Branch**: `040-flight-plan-cli` | **Date**: 2026-02-28

## Usage

### Create a new flight plan

```bash
# Create with default output directory (.maverick/flight-plans/)
maverick flight-plan create my-feature

# Create in a custom directory
maverick flight-plan create my-feature --output-dir ./plans
```

**Output**: Creates `my-feature.md` with all sections stubbed out for editing.

### Validate a flight plan

```bash
# Validate a flight plan file
maverick flight-plan validate .maverick/flight-plans/my-feature.md
```

**Output on success**: Confirmation message with checkmark.

**Output on failure**: List of issues with locations, non-zero exit code.

### Discover commands

```bash
# Show available subcommands
maverick flight-plan --help

# Show create options
maverick flight-plan create --help
```

## Typical workflow

```bash
# 1. Scaffold a new flight plan
maverick flight-plan create auth-system

# 2. Edit the plan in your editor
$EDITOR .maverick/flight-plans/auth-system.md

# 3. Validate before using with refuel
maverick flight-plan validate .maverick/flight-plans/auth-system.md

# 4. Use with refuel to create beads
maverick refuel flight-plan .maverick/flight-plans/auth-system.md
```

## Development

### Run tests

```bash
# All unit tests
make test-fast

# Specific test files
uv run pytest tests/unit/flight/test_validator.py -v
uv run pytest tests/unit/flight/test_template.py -v
uv run pytest tests/unit/cli/commands/flight_plan/ -v
uv run pytest tests/integration/cli/test_flight_plan_commands.py -v
```

### Key source files

| File | Purpose |
|------|---------|
| `src/maverick/cli/commands/flight_plan/_group.py` | Click command group definition |
| `src/maverick/cli/commands/flight_plan/create.py` | `create` subcommand |
| `src/maverick/cli/commands/flight_plan/validate_cmd.py` | `validate` subcommand |
| `src/maverick/flight/template.py` | Skeleton flight plan generation |
| `src/maverick/flight/validator.py` | Multi-error validation logic |
