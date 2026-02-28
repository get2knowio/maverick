# CLI Interface Contract: flight-plan command group

## Commands

### `maverick flight-plan`

```
Usage: maverick flight-plan [OPTIONS] COMMAND [ARGS]...

  Create and validate flight plan files.

Options:
  --help  Show this message and exit.

Commands:
  create    Create a new flight plan from a template.
  validate  Validate a flight plan file for structural issues.
```

**Behavior**: When invoked without a subcommand, displays help text.

### `maverick flight-plan create`

```
Usage: maverick flight-plan create [OPTIONS] NAME

  Create a new flight plan from a template.

Arguments:
  NAME  Plan name (kebab-case: lowercase letters, digits, hyphens).  [required]

Options:
  --output-dir TEXT  Output directory for the flight plan file.
                     [default: .maverick/flight-plans/]
  --help             Show this message and exit.
```

**Exit codes**:
- 0: File created successfully
- 1: Validation error (bad name), file exists, I/O error

### `maverick flight-plan validate`

```
Usage: maverick flight-plan validate [OPTIONS] FILE_PATH

  Validate a flight plan file for structural issues.

Arguments:
  FILE_PATH  Path to the flight plan file to validate.  [required]

Options:
  --help  Show this message and exit.
```

**Exit codes**:
- 0: File is valid (no issues found)
- 1: Validation issues found, or file not found

## Module Interfaces

### `maverick.flight.validator`

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True, slots=True)
class ValidationIssue:
    location: str
    message: str

def validate_flight_plan_file(path: Path) -> list[ValidationIssue]: ...
```

### `maverick.flight.template`

```python
from datetime import date

def generate_skeleton(name: str, created: date) -> str: ...
```
