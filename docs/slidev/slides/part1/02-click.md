---
layout: section
class: text-center
---

# 2. Click - Building CLI Applications

<div class="text-lg text-secondary mt-4">
The CLI Framework Powering Maverick
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">7 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Commands & Groups</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Async Integration</span>
  </div>
</div>

<!--
Section 2 covers Click - the Command Line Interface Creation Kit that powers Maverick's CLI.

We'll cover:
1. What is Click and why Maverick chose it
2. Basic Click commands and decorators
3. Command groups for hierarchical CLIs
4. Options deep dive
5. Click context for sharing state
6. Custom decorators for async commands
7. Tour of Maverick's CLI commands
-->

---

## layout: two-cols

# 2.1 What is Click?

<div class="pr-4">

**Click** = **C**ommand **L**ine **I**nterface **C**reation **K**it

A Python library for creating beautiful command-line interfaces with minimal code

<div v-click class="mt-6">

## Why Click?

<div class="space-y-2 text-sm mt-3">

- **Composable**: Build complex CLIs from simple commands
- **Automatic help**: Generated from docstrings and decorators
- **Type coercion**: Arguments validated and converted automatically
- **Testing**: Built-in test runner for CLI testing

</div>

</div>

<div v-click class="mt-6">

## Alternatives Considered

| Library    | Why Not                             |
| ---------- | ----------------------------------- |
| `argparse` | Verbose, no composability           |
| `typer`    | Too magical, type annotation issues |
| `fire`     | Limited customization               |

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Click Philosophy

```
Explicit is better than implicit
```

<div class="text-sm text-muted mt-2">
Click doesn't try to be clever. Each option and argument is explicitly declared, making code easy to read and maintain.
</div>

</div>

<div v-click class="mt-6 p-3 bg-teal/10 border border-teal/30 rounded-lg">

### Maverick Uses Click For

- `maverick fly` - Execute workflows
- `maverick workflow list` - Discover workflows
- `maverick config show` - Configuration management
- `maverick review` - Code review operations
- `maverick status` - Repository status

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Key Files:</strong>
  <div class="font-mono text-xs mt-1">
    src/maverick/main.py<br/>
    src/maverick/cli/commands/fly.py
  </div>
</div>

</div>

<!--
Click stands for "Command Line Interface Creation Kit" and is the most popular Python CLI framework.

We chose Click over alternatives because:
- argparse (stdlib): Very verbose, no command composition, clunky help formatting
- typer: Built on Click but uses type hints for argument declaration, which caused issues with forward references and our async patterns
- fire: Auto-generates CLI from functions, but limited control over help text and validation

Click's explicit decorator-based approach aligns with Maverick's philosophy of clarity over magic. Every option is visible in the function signature.
-->

---

## layout: default

# 2.2 Your First Click Command

<div class="text-secondary text-sm mb-4">
Building commands with decorators
</div>

```python {all|1-3|5-12|14-17|all}
import click

# The @click.command decorator creates a command
@click.command()
@click.option(
    "-n", "--name",
    default="World",
    help="Name to greet."
)
@click.argument("greeting")
def hello(greeting: str, name: str) -> None:
    """Say hello with a custom greeting."""
    click.echo(f"{greeting}, {name}!")

# Entry point
if __name__ == "__main__":
    hello()
```

<div class="grid grid-cols-2 gap-6 mt-6">

<div v-click>

### Usage Examples

```bash
# Basic usage
$ python hello.py Hello
Hello, World!

# With option
$ python hello.py Hi --name Alice
Hi, Alice!

# Short option form
$ python hello.py Greetings -n Bob
Greetings, Bob!
```

</div>

<div v-click>

### Automatic Help

```bash
$ python hello.py --help
Usage: hello.py [OPTIONS] GREETING

  Say hello with a custom greeting.

Options:
  -n, --name TEXT  Name to greet.
  --help           Show this message and exit.
```

</div>

</div>

<!--
Click uses decorators to build commands layer by layer:

1. @click.command() marks a function as a CLI command
2. @click.option() adds optional flags (with defaults)
3. @click.argument() adds positional arguments (required by default)

The function parameters receive the parsed values. Notice how the docstring becomes the command's help text automatically.

Options can have short (-n) and long (--name) forms. Arguments are positional and don't have short forms.
-->

---

## layout: default

# 2.3 Command Groups

<div class="text-secondary text-sm mb-4">
Building hierarchical CLIs like <code>maverick workflow list</code>
</div>

```python {all|1-8|10-18|20-26|all}
import click

@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Maverick - AI-powered development workflow orchestration."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

@cli.command("list")  # maverick workflow list
@click.option("--format", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def workflow_list(ctx: click.Context, format: str) -> None:
    """List all discovered workflows."""
    if ctx.obj["verbose"]:
        click.echo("Discovering workflows...")
    # ... list workflows

@cli.command("run")  # maverick workflow run <name>
@click.argument("name")
@click.pass_context
def workflow_run(ctx: click.Context, name: str) -> None:
    """Run a workflow by name."""
    click.echo(f"Running workflow: {name}")

cli.add_command(workflow_list)
cli.add_command(workflow_run)
```

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Result:</strong> <code>cli workflow list --format json</code> and <code>cli workflow run feature</code>
</div>

<!--
Command groups create hierarchical CLIs where commands can have subcommands:

1. @click.group() creates a group that can contain other commands
2. @cli.command() adds a command to the group
3. @click.pass_context passes the Click context to share state between commands

The ctx.ensure_object(dict) pattern creates a dictionary in the context for storing shared data. Subcommands can access this via ctx.obj.

In Maverick, the main cli group in main.py uses this pattern to share configuration and verbosity settings with all subcommands.
-->

---

## layout: two-cols

# 2.4 Options Deep Dive

<div class="pr-4">

### Type Conversion

```python
@click.option("--count", type=int, default=1)
@click.option("--rate", type=float, default=1.0)
@click.option("--enabled/--disabled", default=True)
@click.option(
    "--format",
    type=click.Choice(["json", "yaml", "table"]),
    default="table",
)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
)
```

<div v-click class="mt-4">

### Multiple Values

```python
# Can be specified multiple times
@click.option(
    "-i", "--input",
    multiple=True,
    help="Input values (can repeat)."
)
def cmd(input: tuple[str, ...]) -> None:
    for val in input:
        process(val)
```

```bash
$ maverick fly feature -i x=1 -i y=2
```

</div>

</div>

::right::

<div class="pl-4">

<div v-click>

### Flag Options

```python
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview without executing."
)
@click.option(
    "--verbose/--quiet",  # Boolean toggle
    default=False,
)
@click.option(
    "-v", "--verbose",
    count=True,  # -v, -vv, -vvv
    help="Increase verbosity."
)
```

</div>

<div v-click class="mt-4">

### Maverick Example

```python
# From fly.py
@click.option(
    "--restart",
    is_flag=True,
    default=False,
    help="Ignore checkpoint, restart fresh."
)
@click.option(
    "--step",
    "only_step",  # Parameter name differs
    default=None,
    help="Run only specified step."
)
```

</div>

</div>

<!--
Click options are very flexible:

Type Conversion:
- Built-in types: int, float, bool, str
- click.Choice for enumerations with validation
- click.Path for file system paths with optional existence checks
- path_type=Path returns pathlib.Path objects

Multiple Values:
- multiple=True allows repeating the option
- The function receives a tuple of all values
- Used extensively in maverick fly for input parameters

Flags:
- is_flag=True for simple boolean flags (--dry-run)
- --option/--no-option pattern for explicit boolean toggle
- count=True for verbosity levels (-v, -vv, -vvv)
-->

---

## layout: default

# 2.5 Click Context

<div class="text-secondary text-sm mb-4">
Sharing state between commands with <code>@click.pass_context</code>
</div>

<div class="grid grid-cols-2 gap-6">

<div>

### Setting Context

```python {all|7-12|13-20}
from dataclasses import dataclass

@dataclass
class CLIContext:
    config: MaverickConfig
    verbosity: int = 0
    quiet: bool = False

@click.group()
@click.option("-v", "--verbose", count=True)
@click.option("-q", "--quiet", is_flag=True)
@click.pass_context
def cli(ctx: click.Context, verbose: int, quiet: bool) -> None:
    """Main CLI entry point."""
    ctx.ensure_object(dict)

    # Store typed context
    ctx.obj["cli_ctx"] = CLIContext(
        config=load_config(),
        verbosity=verbose,
        quiet=quiet,
    )
```

</div>

<div v-click>

### Using Context

```python
@cli.command()
@click.pass_context
def fly(ctx: click.Context) -> None:
    """Execute a workflow."""
    # Access typed context
    cli_ctx: CLIContext = ctx.obj["cli_ctx"]

    if cli_ctx.verbosity > 0:
        click.echo("Verbose mode enabled")

    if not cli_ctx.quiet:
        click.echo("Starting workflow...")

    # Access configuration
    timeout = cli_ctx.config.timeout
```

<div class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Key File:</strong>
  <div class="font-mono text-xs mt-1">
    src/maverick/cli/context.py
  </div>
</div>

</div>

</div>

<!--
Click's context system allows sharing state between parent and child commands:

1. Parent commands (groups) set up context via ctx.obj
2. Child commands access context via @click.pass_context
3. Use ctx.ensure_object(dict) to initialize ctx.obj safely

Maverick uses a typed CLIContext dataclass to provide type-safe access to shared state. This avoids string-key dictionary access and enables IDE autocompletion.

The context flows from:
cli (main.py) → fly (fly.py) → internal functions

This pattern replaces global variables with explicit context passing - a core Maverick principle.
-->

---

## layout: default

# 2.6 Custom Decorators

<div class="text-secondary text-sm mb-4">
Building <code>@async_command</code> to bridge Click with async functions
</div>

```python {all|1-3|5-20|22-32}
import asyncio
import functools
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

def async_command(f: F) -> F:
    """Decorator to run async Click commands with asyncio.run().

    This bridges Click's synchronous interface to async workflow functions.

    Example:
        @cli.command()
        @async_command
        async def fly(ctx: click.Context, branch: str) -> None:
            await workflow.execute()
    """
    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(f(*args, **kwargs))

    return wrapper  # type: ignore[return-value]
```

<div v-click class="grid grid-cols-2 gap-6 mt-4">

<div class="p-3 bg-red-900/20 border border-red-700/50 rounded-lg text-sm">
  <strong class="text-red-400">Without @async_command:</strong>
  <div class="text-xs mt-1">Click calls sync function → can't <code>await</code></div>
</div>

<div class="p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">With @async_command:</strong>
  <div class="text-xs mt-1">Wrapper calls <code>asyncio.run()</code> → async works!</div>
</div>

</div>

<!--
Click is fundamentally synchronous - commands are regular functions, not async coroutines. But Maverick is async-first, with workflows, agents, and I/O all using async/await.

The @async_command decorator bridges this gap:
1. It wraps an async function
2. When Click calls the wrapper, it uses asyncio.run() to execute the coroutine
3. The async function can then await other coroutines normally

This is defined in src/maverick/cli/context.py and used on commands like fly, review, etc.

Important: The decorator must be applied AFTER @click decorators but BEFORE the async def - decorator order matters in Python (bottom to top execution).
-->

---

## layout: default

# 2.7 Maverick CLI Tour

<div class="text-secondary text-sm mb-4">
Walkthrough of the main commands: <code>fly</code>, <code>workflow</code>, <code>config</code>
</div>

<div class="grid grid-cols-2 gap-6">

<div>

### maverick fly

```bash
# Execute a workflow from library
$ maverick fly feature \
    -i branch_name=001-foo \
    -i skip_review=true

# Execute from file
$ maverick fly ./my-workflow.yaml

# Preview mode
$ maverick fly feature --dry-run

# Restart (ignore checkpoint)
$ maverick fly feature --restart

# Run specific step only
$ maverick fly feature --step init
```

<div v-click class="mt-4">

### maverick workflow

```bash
# List all discovered workflows
$ maverick workflow list

# Show workflow details
$ maverick workflow show feature

# Validate a workflow file
$ maverick workflow validate ./custom.yaml
```

</div>

</div>

<div>

<div v-click>

### maverick config

```bash
# Show current configuration
$ maverick config show

# Show specific setting
$ maverick config get timeout

# Set a value
$ maverick config set timeout 300
```

</div>

<div v-click class="mt-4">

### maverick review

```bash
# Review current branch changes
$ maverick review

# Review with auto-fix
$ maverick review --fix
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg">

### CLI Structure

```
maverick
├── fly         # Primary workflow execution
├── workflow    # Workflow management
│   ├── list
│   ├── show
│   └── validate
├── config      # Configuration
├── review      # Code review
└── status      # Repository status
```

</div>

</div>

</div>

<!--
Let's tour Maverick's main CLI commands:

maverick fly: The primary command for executing workflows
- Takes a workflow name or file path
- -i/--input for key=value input parameters
- --dry-run for preview mode
- --restart to ignore checkpoints
- --step to run only one step

maverick workflow: Workflow management
- list: Discover workflows from builtin, user, project locations
- show: Display workflow details (steps, inputs, outputs)
- validate: Check workflow syntax and references

maverick config: Configuration management
- show: Display merged configuration
- get/set: Read/write specific values

maverick review: Code review operations
- Triggers AI review of current changes
- --fix enables auto-fixing of issues

The tree structure shows how Click groups create the hierarchical CLI we use.
-->
