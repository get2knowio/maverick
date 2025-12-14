# CLI Interface Contract

**Feature**: 001-maverick-foundation
**Date**: 2025-12-12

## Overview

This document defines the command-line interface contract for Maverick. The CLI uses Click and follows standard Unix conventions.

## Root Command

```
maverick [OPTIONS] [COMMAND]
```

### Global Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--version` | flag | - | Show version and exit |
| `-v, --verbose` | count | 0 | Increase verbosity (-v=info, -vv=debug) |
| `--help` | flag | - | Show help message and exit |

### Behavior

- With no command: Display help message
- `--version`: Display version string and exit (exit code 0)
- `--help`: Display help message and exit (exit code 0)
- Invalid command: Display error and exit (exit code 2)

## Exit Codes

| Code | Meaning | Example |
|------|---------|---------|
| 0 | Success | Command completed normally |
| 1 | General error | ConfigError, MaverickError |
| 2 | Usage error | Invalid option, unknown command |

## Verbosity Levels

| Flag | Level | Logging |
|------|-------|---------|
| (none) | 0 | WARNING and above |
| `-v` | 1 | INFO and above |
| `-vv` | 2 | DEBUG and above |

Verbosity from CLI flag overrides config file setting.

## Output Format

### Standard Output (stdout)
- Command results
- Status messages

### Standard Error (stderr)
- Error messages
- Warning messages
- Debug messages (when `-v` or `-vv`)

## Version Output

```
maverick, version X.Y.Z
```

## Help Output

```
Usage: maverick [OPTIONS] [COMMAND]

  Maverick - AI-powered development workflow orchestration.

Options:
  --version      Show the version and exit.
  -v, --verbose  Increase verbosity (-v, -vv).
  --help         Show this message and exit.

Commands:
  (future commands will be listed here)
```

## Error Output

### Configuration Error
```
Error: Invalid configuration in maverick.yaml
  Field: parallel.max_agents
  Value: 15
  Expected: integer between 1 and 10
```

### Missing File (informational only)
```
INFO: No project configuration found, using defaults.
```

## Future Commands (Out of Scope)

The following commands are planned but not part of this foundation spec:

- `maverick fly` - Full spec-based workflow
- `maverick refuel` - Tech-debt resolution workflow
- `maverick config` - Configuration management
